import io
import os
import re
import time
import zipfile
from dataclasses import dataclass

import requests
from django.conf import settings

from reviews.models import Paper, Review


@dataclass
class MinerUParseResult:
    ok: bool
    status: str
    error: str
    markdown_chars: int
    batch_id: str


class MinerUError(RuntimeError):
    pass


def parse_pdf_to_markdown(paper_id):
    paper = Paper.objects.select_related('review').get(pk=paper_id)

    if paper.ta_decision != Paper.TADecision.INCLUDED:
        raise ValueError(f'Paper {paper.id} is not in included category.')
    if not paper.fulltext_retrieved:
        raise ValueError(f'Paper {paper.id} has no retrieved fulltext.')
    if not paper.pdf_path:
        raise ValueError(f'Paper {paper.id} has empty pdf_path.')

    absolute_pdf_path = _absolute_pdf_path(str(paper.pdf_path))
    if not os.path.exists(absolute_pdf_path):
        raise FileNotFoundError(f'PDF file missing on disk: {absolute_pdf_path}')

    headers = _mineru_json_headers()
    file_name = os.path.basename(absolute_pdf_path)

    batch_url = f"{_mineru_base_url()}/file-urls/batch"
    payload = {
        'files': [{'name': file_name, 'data_id': f'paper_{paper.id}'}],
        'model_version': getattr(settings, 'MINERU_MODEL_VERSION', 'vlm'),
    }

    upload_res = requests.post(batch_url, headers=headers, json=payload, timeout=_mineru_timeout_seconds())
    if upload_res.status_code != 200:
        raise MinerUError(f'Upload URL request failed HTTP {upload_res.status_code}: {upload_res.text[:300]}')

    upload_data = upload_res.json()
    if upload_data.get('code') != 0:
        raise MinerUError(f"MinerU URL request rejected: {upload_data.get('msg', 'Unknown error')}")

    data = upload_data.get('data') or {}
    batch_id = str(data.get('batch_id') or '').strip()
    file_urls = data.get('file_urls') or []
    if not batch_id or not file_urls:
        raise MinerUError('MinerU did not return batch_id/file_urls.')

    upload_url = str(file_urls[0])
    with open(absolute_pdf_path, 'rb') as handle:
        put_res = requests.put(upload_url, data=handle, timeout=_mineru_timeout_seconds())
    if put_res.status_code not in {200, 201}:
        raise MinerUError(f'File upload failed HTTP {put_res.status_code}: {put_res.text[:300]}')

    result_url = f"{_mineru_base_url()}/extract-results/batch/{batch_id}"
    max_polls = int(getattr(settings, 'MINERU_MAX_POLLS', 60))
    poll_delay = float(getattr(settings, 'MINERU_POLL_INTERVAL_SECONDS', 5.0))

    zip_url = ''
    for _ in range(max_polls):
        poll_res = requests.get(result_url, headers=headers, timeout=_mineru_timeout_seconds())
        if poll_res.status_code != 200:
            raise MinerUError(f'Polling failed HTTP {poll_res.status_code}: {poll_res.text[:300]}')

        poll_data = poll_res.json()
        if poll_data.get('code') != 0:
            raise MinerUError(f"MinerU polling rejected: {poll_data.get('msg', 'Unknown error')}")

        extract_result = ((poll_data.get('data') or {}).get('extract_result') or [])
        if not extract_result:
            time.sleep(poll_delay)
            continue

        item = extract_result[0] or {}
        state = str(item.get('state') or '').strip().lower()

        if state == 'done':
            zip_url = str(item.get('full_zip_url') or '').strip()
            break
        if state == 'failed':
            err_msg = str(item.get('err_msg') or 'MinerU processing failed')
            raise MinerUError(err_msg)

        time.sleep(poll_delay)

    if not zip_url:
        raise MinerUError('MinerU polling timed out before completion.')

    zip_response = requests.get(zip_url, timeout=_mineru_timeout_seconds())
    if zip_response.status_code != 200:
        raise MinerUError(f'ZIP download failed HTTP {zip_response.status_code}: {zip_response.text[:300]}')

    markdown_content = _extract_full_md(zip_response.content)
    markdown_content = _clean_mineru_markdown(markdown_content)

    paper.mineru_markdown = markdown_content
    paper.mineru_parsed = True
    paper.processed_pdf_mineru = True
    paper.mineru_batch_id = batch_id
    paper.mineru_status = 'done'
    paper.mineru_error = ''
    paper.ref_delete_done = True
    paper.save(
        update_fields=[
            'mineru_markdown',
            'mineru_parsed',
            'processed_pdf_mineru',
            'mineru_batch_id',
            'mineru_status',
            'mineru_error',
            'ref_delete_done',
        ]
    )

    return MinerUParseResult(
        ok=True,
        status='done',
        error='',
        markdown_chars=len(markdown_content or ''),
        batch_id=batch_id,
    )


def parse_review_pdfs_with_mineru(review_id, retry_failed_only=False, progress_callback=None, stop_check=None):
    review = Review.objects.get(pk=review_id)

    papers_qs = review.papers.filter(
        ta_decision=Paper.TADecision.INCLUDED,
        fulltext_retrieved=True,
    ).exclude(pdf_path='').order_by('id')

    if retry_failed_only:
        papers_qs = papers_qs.filter(processed_pdf_mineru=False)
    else:
        papers_qs = papers_qs.filter(processed_pdf_mineru=False)

    papers = list(papers_qs)

    _emit(progress_callback, {
        'event': 'started',
        'targeted': len(papers),
        'paper_ids': [paper.id for paper in papers],
    })

    processed = 0
    done = 0
    failed = 0
    processed_ids = []

    for idx, paper in enumerate(papers, start=1):
        if stop_check and stop_check():
            _emit(progress_callback, {'event': 'stopped', 'processed_ids': list(processed_ids)})
            break

        _emit(progress_callback, {
            'event': 'processing',
            'paper_id': paper.id,
            'title': paper.title,
            'index': idx,
            'targeted': len(papers),
        })

        try:
            result = parse_pdf_to_markdown(paper.id)
            processed += 1
            done += 1
            processed_ids.append(paper.id)

            _emit(progress_callback, {
                'event': 'done',
                'paper_id': paper.id,
                'title': paper.title,
                'batch_id': result.batch_id,
                'markdown_chars': result.markdown_chars,
            })
        except Exception as exc:
            processed += 1
            failed += 1
            processed_ids.append(paper.id)
            paper.mineru_parsed = False
            paper.processed_pdf_mineru = False
            paper.mineru_status = 'failed'
            paper.mineru_error = f'{exc.__class__.__name__}: {exc}'
            paper.save(update_fields=['mineru_parsed', 'processed_pdf_mineru', 'mineru_status', 'mineru_error'])

            _emit(progress_callback, {
                'event': 'failed',
                'paper_id': paper.id,
                'title': paper.title,
                'error_message': f'{exc.__class__.__name__}: {exc}',
            })

        time.sleep(float(getattr(settings, 'MINERU_REQUEST_DELAY_SECONDS', 1.0)))

    remaining = [paper.id for paper in papers if paper.id not in set(processed_ids)]

    summary = {
        'targeted': len(papers),
        'processed': processed,
        'done': done,
        'failed': failed,
        'processed_ids': processed_ids,
        'remaining_paper_ids': remaining,
        'stopped': bool(stop_check and stop_check()),
    }
    _emit(progress_callback, {'event': 'completed', **summary})
    return summary


def clean_existing_mineru_references(review_id, progress_callback=None, stop_check=None):
    review = Review.objects.get(pk=review_id)
    papers = list(
        review.papers.filter(
            ta_decision=Paper.TADecision.INCLUDED,
            fulltext_retrieved=True,
            processed_pdf_mineru=True,
            mineru_parsed=True,
            ref_delete_done=False,
        ).exclude(mineru_markdown='').order_by('id')
    )

    _emit(progress_callback, {
        'event': 'started',
        'targeted': len(papers),
        'paper_ids': [paper.id for paper in papers],
    })

    processed = 0
    done = 0
    failed = 0
    processed_ids = []

    for idx, paper in enumerate(papers, start=1):
        if stop_check and stop_check():
            _emit(progress_callback, {'event': 'stopped', 'processed_ids': list(processed_ids)})
            break

        _emit(progress_callback, {
            'event': 'processing',
            'paper_id': paper.id,
            'title': paper.title,
            'index': idx,
            'targeted': len(papers),
        })

        try:
            cleaned = _clean_mineru_markdown(paper.mineru_markdown or '')
            paper.mineru_markdown = cleaned
            paper.ref_delete_done = True
            paper.save(update_fields=['mineru_markdown', 'ref_delete_done'])

            processed += 1
            done += 1
            processed_ids.append(paper.id)
            _emit(progress_callback, {
                'event': 'done',
                'paper_id': paper.id,
                'title': paper.title,
                'batch_id': paper.mineru_batch_id,
                'markdown_chars': len(cleaned or ''),
            })
        except Exception as exc:
            processed += 1
            failed += 1
            processed_ids.append(paper.id)
            _emit(progress_callback, {
                'event': 'failed',
                'paper_id': paper.id,
                'title': paper.title,
                'error_message': f'{exc.__class__.__name__}: {exc}',
            })

    remaining = [paper.id for paper in papers if paper.id not in set(processed_ids)]
    summary = {
        'targeted': len(papers),
        'processed': processed,
        'done': done,
        'failed': failed,
        'processed_ids': processed_ids,
        'remaining_paper_ids': remaining,
        'stopped': bool(stop_check and stop_check()),
    }
    _emit(progress_callback, {'event': 'completed', **summary})
    return summary


def _emit(callback, payload):
    if not callback:
        return
    try:
        callback(payload)
    except Exception:
        return


def _absolute_pdf_path(pdf_field_value):
    if os.path.isabs(pdf_field_value):
        return pdf_field_value
    return os.path.join(settings.MEDIA_ROOT, pdf_field_value)


def _extract_full_md(zip_bytes):
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zip_file:
        if 'full.md' not in zip_file.namelist():
            raise MinerUError("'full.md' not found in MinerU zip output.")
        return zip_file.read('full.md').decode('utf-8', errors='replace')



def _clean_mineru_markdown(markdown_text):
    cleaned = _strip_abstract_section(markdown_text)
    cleaned = _strip_reference_section(cleaned)
    return cleaned


def _strip_abstract_section(markdown_text):
    text = (markdown_text or '').replace('\r\n', '\n').replace('\r', '\n')
    if not text.strip():
        return ''

    lines = text.split('\n')
    heading_pattern = re.compile(r'^\s{0,3}(#{1,6})\s*(.+?)\s*#*\s*$')

    start_idx = None
    start_level = None
    for idx, line in enumerate(lines):
        m = heading_pattern.match(line)
        if not m:
            continue
        level = len(m.group(1))
        heading_text = (m.group(2) or '').strip().lower()
        if heading_text in {'abstract', 'summary'}:
            start_idx = idx
            start_level = level
            break

    if start_idx is None:
        return markdown_text

    end_idx = len(lines)
    for idx in range(start_idx + 1, len(lines)):
        m = heading_pattern.match(lines[idx])
        if not m:
            continue
        level = len(m.group(1))
        if level <= start_level:
            end_idx = idx
            break

    kept = lines[:start_idx] + lines[end_idx:]
    return '\n'.join(kept).strip()
def _strip_reference_section(markdown_text):
    text = (markdown_text or '').replace('\r\n', '\n').replace('\r', '\n')
    if not text.strip():
        return ''

    lines = text.split('\n')
    keyword_pattern = re.compile(r'^\s*(references|bibliography|works cited|literature cited)\s*[::]?\s*$', re.IGNORECASE)
    atx_pattern = re.compile(r'^\s{0,3}#{1,6}\s*(references|bibliography|works cited|literature cited)\s*#*\s*$', re.IGNORECASE)

    cutoff = None
    for idx, line in enumerate(lines):
        if atx_pattern.match(line):
            cutoff = idx
            break

        if keyword_pattern.match(line):
            next_line = lines[idx + 1].strip() if idx + 1 < len(lines) else ''
            if re.match(r'^[-=]{3,}\s*$', next_line) or idx >= max(0, len(lines) - 80):
                cutoff = idx
                break

    if cutoff is None:
        return markdown_text

    return '\n'.join(lines[:cutoff]).rstrip()


def _mineru_base_url():
    return (getattr(settings, 'MINERU_BASE_URL', 'https://mineru.net/api/v4') or 'https://mineru.net/api/v4').rstrip('/')


def _mineru_timeout_seconds():
    return float(getattr(settings, 'MINERU_TIMEOUT_SECONDS', 30.0))


def _mineru_json_headers():
    token = (getattr(settings, 'MINERU_API_TOKEN', '') or '').strip()
    if not token:
        raise MinerUError('MINERU_API_TOKEN is not configured.')
    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
    }



