import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.conf import settings

from reviews.models import Paper, Review


def retrieve_pdfs_for_review(review_id, progress_callback=None, paper_ids=None, stop_check=None):
    review = Review.objects.get(pk=review_id)
    qs = review.papers.filter(ta_decision=Paper.TADecision.INCLUDED, fulltext_retrieved=False)
    if paper_ids:
        qs = qs.filter(id__in=paper_ids)
    papers = list(qs.order_by('id'))

    delay_seconds = float(getattr(settings, 'PDF_RETRIEVAL_DELAY_SECONDS', 1.0))
    downloaded = 0
    abstract_only = 0
    skipped = 0
    processed_ids = []

    _emit(
        progress_callback,
        {
            'event': 'started',
            'review_id': review.id,
            'targeted': len(papers),
            'paper_ids': [paper.id for paper in papers],
        },
    )

    for index, paper in enumerate(papers, start=1):
        if stop_check and stop_check():
            _emit(
                progress_callback,
                {
                    'event': 'stopped',
                    'review_id': review.id,
                    'processed_ids': list(processed_ids),
                    'remaining_paper_ids': [item.id for item in papers if item.id not in set(processed_ids)],
                },
            )
            break

        try:
            _emit(
                progress_callback,
                {
                    'event': 'processing',
                    'paper_id': paper.id,
                    'title': paper.title,
                    'index': index,
                    'targeted': len(papers),
                },
            )

            if paper.pdf_path:
                skipped += 1
                processed_ids.append(paper.id)
                _emit(
                    progress_callback,
                    {
                        'event': 'skipped_existing',
                        'paper_id': paper.id,
                        'title': paper.title,
                        'index': index,
                        'targeted': len(papers),
                        'status_code': None,
                        'error_message': '',
                    },
                )
                continue

            doi = (paper.doi or '').strip()
            elsevier_result = {'ok': False, 'status_code': None, 'error_message': 'DOI missing for Elsevier attempt.'}
            unpaywall_result = {'ok': False, 'status_code': None, 'error_message': 'DOI missing for Unpaywall attempt.'}

            if doi:
                elsevier_result = _try_elsevier_pdf(doi=doi, delay_seconds=delay_seconds)

            if elsevier_result.get('ok'):
                relative_path = _save_pdf_bytes(review_id=review.id, paper_id=paper.id, pdf_bytes=elsevier_result['pdf_bytes'])
                paper.pdf_path.name = relative_path
                paper.fulltext_retrieved = True
                paper.pdf_source = 'elsevier'
                paper.save(update_fields=['pdf_path', 'fulltext_retrieved', 'pdf_source'])
                downloaded += 1
                processed_ids.append(paper.id)
                _emit(
                    progress_callback,
                    {
                        'event': 'downloaded',
                        'paper_id': paper.id,
                        'title': paper.title,
                        'source': 'elsevier',
                        'index': index,
                        'targeted': len(papers),
                        'status_code': elsevier_result.get('status_code'),
                        'error_message': '',
                    },
                )
                continue

            if doi:
                unpaywall_result = _try_unpaywall_pdf(doi=doi, delay_seconds=delay_seconds)

            if unpaywall_result.get('ok'):
                relative_path = _save_pdf_bytes(review_id=review.id, paper_id=paper.id, pdf_bytes=unpaywall_result['pdf_bytes'])
                paper.pdf_path.name = relative_path
                paper.fulltext_retrieved = True
                paper.pdf_source = 'unpaywall'
                paper.save(update_fields=['pdf_path', 'fulltext_retrieved', 'pdf_source'])
                downloaded += 1
                processed_ids.append(paper.id)
                _emit(
                    progress_callback,
                    {
                        'event': 'downloaded',
                        'paper_id': paper.id,
                        'title': paper.title,
                        'source': 'unpaywall',
                        'index': index,
                        'targeted': len(papers),
                        'status_code': unpaywall_result.get('status_code'),
                        'error_message': '',
                    },
                )
                continue

            paper.fulltext_retrieved = False
            paper.pdf_source = 'abstract_only'
            paper.save(update_fields=['fulltext_retrieved', 'pdf_source'])
            abstract_only += 1
            processed_ids.append(paper.id)

            final_status_code = unpaywall_result.get('status_code') or elsevier_result.get('status_code')
            final_error_message = (
                f"Elsevier: {elsevier_result.get('error_message', '')} | "
                f"Unpaywall: {unpaywall_result.get('error_message', '')}"
            ).strip()

            _emit(
                progress_callback,
                {
                    'event': 'failed',
                    'paper_id': paper.id,
                    'title': paper.title,
                    'source': 'abstract_only',
                    'index': index,
                    'targeted': len(papers),
                    'status_code': final_status_code,
                    'error_message': final_error_message,
                },
            )
        except Exception as exc:
            paper.fulltext_retrieved = False
            paper.pdf_source = 'abstract_only'
            paper.save(update_fields=['fulltext_retrieved', 'pdf_source'])
            abstract_only += 1
            processed_ids.append(paper.id)
            _emit(
                progress_callback,
                {
                    'event': 'failed',
                    'paper_id': paper.id,
                    'title': paper.title,
                    'source': 'abstract_only',
                    'index': index,
                    'targeted': len(papers),
                    'status_code': None,
                    'error_message': f'Unhandled error: {exc.__class__.__name__}: {exc}',
                },
            )

    remaining_ids = [paper.id for paper in papers if paper.id not in set(processed_ids)]
    result = {
        'review_id': review.id,
        'targeted': len(papers),
        'downloaded': downloaded,
        'abstract_only': abstract_only,
        'skipped_existing': skipped,
        'processed_ids': processed_ids,
        'remaining_paper_ids': remaining_ids,
        'stopped': bool(stop_check and stop_check()),
    }
    _emit(progress_callback, {'event': 'completed', **result})
    return result


def _emit(callback, payload):
    if not callback:
        return
    try:
        callback(payload)
    except Exception:
        return


def _try_elsevier_pdf(doi, delay_seconds):
    api_key = (getattr(settings, 'ELSEVIER_API_KEY', '') or '').strip()
    if not api_key:
        return {'ok': False, 'status_code': None, 'error_message': 'ELSEVIER_API_KEY is missing.'}

    encoded_doi = quote(doi, safe='')
    url = f'https://api.elsevier.com/content/article/doi/{encoded_doi}?httpAccept=application/pdf'
    headers = {
        'X-ELS-APIKey': api_key,
        'Accept': 'application/pdf',
    }
    return _fetch_pdf_bytes(url=url, headers=headers, delay_seconds=delay_seconds)


def _try_unpaywall_pdf(doi, delay_seconds):
    email = (getattr(settings, 'UNPAYWALL_EMAIL', '') or '').strip()
    if not email:
        return {'ok': False, 'status_code': None, 'error_message': 'UNPAYWALL_EMAIL is missing.'}

    encoded_doi = quote(doi, safe='')
    meta_url = f'https://api.unpaywall.org/v2/{encoded_doi}?email={quote(email, safe="@.")}'
    meta_result = _fetch_json(url=meta_url, headers={'Accept': 'application/json'}, delay_seconds=delay_seconds)
    if not meta_result.get('ok'):
        return {
            'ok': False,
            'status_code': meta_result.get('status_code'),
            'error_message': meta_result.get('error_message', 'Unpaywall metadata lookup failed.'),
        }

    payload = meta_result.get('payload') or {}
    locations = []
    best_location = payload.get('best_oa_location')
    if isinstance(best_location, dict):
        locations.append(best_location)
    if isinstance(payload.get('oa_locations'), list):
        locations.extend([loc for loc in payload.get('oa_locations') if isinstance(loc, dict)])

    if not locations:
        return {'ok': False, 'status_code': 200, 'error_message': 'No OA locations found in Unpaywall.'}

    last_error = {'status_code': 200, 'error_message': 'No downloadable PDF URL in OA locations.'}
    for location in locations:
        if not location.get('is_oa', True):
            continue
        pdf_url = (location.get('url_for_pdf') or location.get('url') or '').strip()
        if not pdf_url:
            continue
        pdf_result = _fetch_pdf_bytes(url=pdf_url, headers={'Accept': 'application/pdf'}, delay_seconds=delay_seconds)
        if pdf_result.get('ok'):
            return pdf_result
        last_error = {
            'status_code': pdf_result.get('status_code'),
            'error_message': pdf_result.get('error_message', 'Failed to fetch OA PDF URL.'),
        }

    return {'ok': False, **last_error}


def _fetch_json(url, headers, delay_seconds):
    time.sleep(max(delay_seconds, 0.0))
    request = Request(url=url, headers=headers or {}, method='GET')
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode('utf-8', errors='ignore')
            return {'ok': True, 'status_code': response.getcode(), 'payload': json.loads(raw)}
    except HTTPError as exc:
        return {'ok': False, 'status_code': exc.code, 'error_message': f'HTTPError: {exc}'}
    except URLError as exc:
        return {'ok': False, 'status_code': None, 'error_message': f'URLError: {exc}'}
    except TimeoutError as exc:
        return {'ok': False, 'status_code': None, 'error_message': f'TimeoutError: {exc}'}
    except json.JSONDecodeError as exc:
        return {'ok': False, 'status_code': None, 'error_message': f'JSONDecodeError: {exc}'}
    except Exception as exc:
        return {'ok': False, 'status_code': None, 'error_message': f'UnexpectedError: {exc.__class__.__name__}: {exc}'}


def _fetch_pdf_bytes(url, headers, delay_seconds):
    time.sleep(max(delay_seconds, 0.0))
    request = Request(url=url, headers=headers or {}, method='GET')
    try:
        with urlopen(request, timeout=45) as response:
            content_type = (response.headers.get('Content-Type') or '').lower()
            body = response.read()
            if b'%PDF' not in body[:1024] and 'pdf' not in content_type:
                return {
                    'ok': False,
                    'status_code': response.getcode(),
                    'error_message': f'Non-PDF response Content-Type: {content_type}',
                }
            return {'ok': True, 'status_code': response.getcode(), 'pdf_bytes': body}
    except HTTPError as exc:
        return {'ok': False, 'status_code': exc.code, 'error_message': f'HTTPError: {exc}'}
    except URLError as exc:
        return {'ok': False, 'status_code': None, 'error_message': f'URLError: {exc}'}
    except TimeoutError as exc:
        return {'ok': False, 'status_code': None, 'error_message': f'TimeoutError: {exc}'}
    except Exception as exc:
        return {'ok': False, 'status_code': None, 'error_message': f'UnexpectedError: {exc.__class__.__name__}: {exc}'}


def _save_pdf_bytes(review_id, paper_id, pdf_bytes):
    from pathlib import Path

    relative_dir = Path('pdfs') / str(review_id)
    target_dir = Path(settings.MEDIA_ROOT) / relative_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = f'{paper_id}.pdf'
    absolute_path = target_dir / filename
    with open(absolute_path, 'wb') as handle:
        handle.write(pdf_bytes)

    return str(relative_dir / filename).replace('\\', '/')
