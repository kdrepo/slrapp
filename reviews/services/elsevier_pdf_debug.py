import re
import time
from pathlib import Path
from urllib.parse import quote

import requests
from django.conf import settings

from reviews.models import Paper, Review


def run_elsevier_pdf_debug(review_id, progress_callback=None, stop_check=None):
    review = Review.objects.get(pk=review_id)
    papers = list(
        review.papers.filter(ta_decision=Paper.TADecision.INCLUDED, fulltext_retrieved=False).order_by('id')
    )

    delay_seconds = float(getattr(settings, 'ELSEVIER_DEBUG_DELAY_SECONDS', 1.5))
    downloaded = 0
    failed = 0
    stopped = False

    _emit(
        progress_callback,
        {
            'event': 'started',
            'review_id': review.id,
            'targeted': len(papers),
            'message': f'Started Elsevier debug for {len(papers)} papers.',
        },
    )

    for index, paper in enumerate(papers, start=1):
        if _should_stop(stop_check):
            stopped = True
            _emit(
                progress_callback,
                {
                    'event': 'stopped',
                    'paper_id': paper.id,
                    'index': index,
                    'targeted': len(papers),
                    'title': paper.title,
                    'message': 'Stop requested by user. Halting run.',
                },
            )
            break

        _emit(
            progress_callback,
            {
                'event': 'processing',
                'paper_id': paper.id,
                'index': index,
                'targeted': len(papers),
                'title': paper.title,
                'doi': paper.doi,
                'eid': paper.scopus_id,
                'message': f'Processing paper {paper.id} ({index}/{len(papers)}).',
            },
        )

        result = _download_from_elsevier(paper=paper, delay_seconds=delay_seconds)

        if result.get('ok'):
            downloaded += 1
            paper.fulltext_retrieved = True
            paper.pdf_source = 'elsevier_debug'
            paper.pdf_path.name = result['relative_path']
            paper.save(update_fields=['fulltext_retrieved', 'pdf_source', 'pdf_path'])
            _emit(
                progress_callback,
                {
                    'event': 'downloaded',
                    'paper_id': paper.id,
                    'title': paper.title,
                    'path': result['relative_path'],
                    'index': index,
                    'targeted': len(papers),
                    'message': result.get('message') or 'Downloaded from Elsevier.',
                },
            )
        else:
            failed += 1
            _emit(
                progress_callback,
                {
                    'event': 'failed',
                    'paper_id': paper.id,
                    'title': paper.title,
                    'index': index,
                    'targeted': len(papers),
                    'error_type': result.get('error_type', 'unknown_error'),
                    'status_code': result.get('status_code'),
                    'message': result.get('message', 'Download failed.'),
                },
            )

    summary = {
        'review_id': review.id,
        'targeted': len(papers),
        'downloaded': downloaded,
        'failed': failed,
        'stopped': stopped,
    }
    completed_msg = 'Elsevier debug stopped by user.' if stopped else 'Elsevier debug completed.'
    _emit(progress_callback, {'event': 'completed', **summary, 'message': completed_msg})
    return summary


def _should_stop(stop_check):
    if not stop_check:
        return False
    try:
        return bool(stop_check())
    except Exception:
        return False


def _download_from_elsevier(paper, delay_seconds):
    api_key = (getattr(settings, 'ELSEVIER_API_KEY', '') or '').strip()
    inst_token = (getattr(settings, 'ELSEVIER_INSTTOKEN', '') or '').strip()

    if not api_key or not inst_token:
        return {
            'ok': False,
            'error_type': 'missing_credentials',
            'message': 'ELSEVIER_API_KEY or ELSEVIER_INSTTOKEN missing in environment.',
        }

    headers = {
        'X-ELS-APIKey': api_key,
        'X-ELS-Insttoken': inst_token,
        'Accept': 'application/pdf',
    }

    timeout = float(getattr(settings, 'ELSEVIER_DEBUG_TIMEOUT_SECONDS', 30))

    doi = (paper.doi or '').strip()
    eid = (paper.scopus_id or '').strip()

    attempts = []
    if doi:
        encoded_doi = quote(doi, safe='')
        attempts.append(('doi', f'https://api.elsevier.com/content/article/doi/{encoded_doi}?view=FULL'))
    if eid:
        encoded_eid = quote(eid, safe='')
        attempts.append(('eid', f'https://api.elsevier.com/content/article/eid/{encoded_eid}?view=FULL'))

    if not attempts:
        return {'ok': False, 'error_type': 'missing_identifiers', 'message': 'Paper has no DOI or EID.'}

    for id_type, url in attempts:
        result = _request_pdf(url=url, headers=headers, timeout=timeout, delay_seconds=delay_seconds)
        if result.get('ok'):
            filename = _safe_filename(paper)
            relative_path = _save_pdf(review_id=paper.review_id, filename=filename, content=result['content'])
            return {
                'ok': True,
                'relative_path': relative_path,
                'message': f'Downloaded via {id_type} endpoint.',
            }

        if result.get('error_type') in {'auth_failed', 'forbidden'}:
            return {
                'ok': False,
                'error_type': result['error_type'],
                'status_code': result.get('status_code'),
                'message': f'{id_type.upper()} request failed due to auth/institution token issue.',
            }

    return {
        'ok': False,
        'error_type': 'not_found_or_unavailable',
        'message': 'DOI and EID attempts both failed for Elsevier full-text.',
    }


def _request_pdf(url, headers, timeout, delay_seconds):
    time.sleep(max(delay_seconds, 0.0))

    try:
        response = requests.get(url, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        return {'ok': False, 'error_type': 'request_error', 'message': str(exc)}

    if response.status_code == 200:
        content_type = (response.headers.get('Content-Type') or '').lower()
        content = response.content or b''
        if b'%PDF' in content[:1024] or 'pdf' in content_type:
            return {'ok': True, 'content': content}
        return {'ok': False, 'error_type': 'not_pdf', 'status_code': 200, 'message': f'Expected PDF but got {content_type}'}

    if response.status_code in {401, 403}:
        return {'ok': False, 'error_type': 'auth_failed' if response.status_code == 401 else 'forbidden', 'status_code': response.status_code}

    if response.status_code == 404:
        return {'ok': False, 'error_type': 'not_found', 'status_code': 404}

    if response.status_code == 429:
        time.sleep(30)
        try:
            retry = requests.get(url, headers=headers, timeout=timeout)
        except requests.RequestException as exc:
            return {'ok': False, 'error_type': 'rate_limited_retry_error', 'status_code': 429, 'message': str(exc)}

        if retry.status_code == 200:
            content_type = (retry.headers.get('Content-Type') or '').lower()
            content = retry.content or b''
            if b'%PDF' in content[:1024] or 'pdf' in content_type:
                return {'ok': True, 'content': content}
            return {'ok': False, 'error_type': 'not_pdf', 'status_code': 200, 'message': f'Retry returned non-PDF ({content_type})'}

        return {'ok': False, 'error_type': 'rate_limited', 'status_code': retry.status_code, 'message': 'Retry after 429 did not succeed.'}

    return {'ok': False, 'error_type': 'http_error', 'status_code': response.status_code, 'message': f'HTTP {response.status_code}'}


def _safe_filename(paper):
    base = (paper.doi or paper.title or f'paper_{paper.id}').strip()
    base = re.sub(r'[^A-Za-z0-9._-]+', '_', base)
    base = base.strip('._-') or f'paper_{paper.id}'
    return f'{paper.id}_{base}.pdf'


def _save_pdf(review_id, filename, content):
    relative_dir = Path('pdfs') / str(review_id)
    target_dir = Path(settings.MEDIA_ROOT) / relative_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / filename
    with open(target_path, 'wb') as handle:
        handle.write(content)

    return str(relative_dir / filename).replace('\\', '/')


def _emit(callback, payload):
    line = f"[ElsevierPDFDebug] {payload.get('event', 'event')} | {payload.get('message', '')}"
    print(line)

    if callback:
        try:
            callback(payload)
        except Exception as exc:
            print(f'[ElsevierPDFDebug] callback_error | {exc}')
