import json
import os
import time
from json import JSONDecodeError

import requests
from django.conf import settings
from django.utils import timezone

from reviews.models import LitPaper, LitReview
from reviews.services.prompt_loader import render_prompt_template


DEFAULT_PROMPT = """You are a research paper analyst for a literature review workflow.

Read the paper text and return one JSON object with this exact structure:
{
  "title": "",
  "authors": [""],
  "year": null,
  "source": "",
  "core_claim": "",
  "background": "",
  "methodology": {
    "type": "",
    "description": "",
    "sample": null
  },
  "key_findings": [""],
  "limitations": [""],
  "key_concepts": [""],
  "stance": "supports|challenges|nuances|reviews",
  "quality_category": "A|B|C|D",
  "quotable": "",
  "citation": null
}

Return only valid JSON.

Research context:
{research_context}

Research questions:
{research_questions_block}

Paper title (if available):
{paper_title}

Paper text:
{mineru_full_paper_text}
"""

JSON_CORRECTION_FALLBACK = """Your previous response was not valid JSON.
Return ONLY one valid JSON object using the required schema.
Original response:
{raw_response}
"""


def run_lit_per_paper_extraction_for_review(review_id, progress_callback=None, stop_check=None, retry_failed_only=False):
    review = LitReview.objects.get(pk=review_id)
    papers = _eligible_papers(review=review, retry_failed_only=retry_failed_only)
    _emit(progress_callback, {'event': 'started', 'targeted': len(papers), 'paper_ids': [p.id for p in papers]})

    done = 0
    failed = 0
    processed_ids = []

    for idx, paper in enumerate(papers, start=1):
        if stop_check and stop_check():
            _emit(progress_callback, {'event': 'stopped', 'processed_ids': list(processed_ids)})
            break

        _emit(
            progress_callback,
            {'event': 'processing', 'paper_id': paper.id, 'title': paper.title, 'index': idx, 'targeted': len(papers)},
        )

        try:
            paper.per_paper_extraction_status = 'running'
            paper.per_paper_extraction_error = ''
            paper.per_paper_extraction_updated_at = timezone.now()
            paper.save(
                update_fields=[
                    'per_paper_extraction_status',
                    'per_paper_extraction_error',
                    'per_paper_extraction_updated_at',
                ]
            )

            payload = _extract_for_paper(
                review=review,
                paper=paper,
                paper_text=(paper.mineru_markdown or '').strip(),
            )
            _save_payload(paper=paper, payload=payload)
            done += 1
            processed_ids.append(paper.id)
            _emit(
                progress_callback,
                {
                    'event': 'done',
                    'paper_id': paper.id,
                    'title': paper.title,
                    'quality_category': payload.get('quality_category') or '',
                    'stance': payload.get('stance') or '',
                },
            )
        except Exception as exc:
            failed += 1
            processed_ids.append(paper.id)
            paper.per_paper_extraction_status = 'failed'
            paper.per_paper_extraction_error = f'{exc.__class__.__name__}: {exc}'
            paper.per_paper_extraction_updated_at = timezone.now()
            paper.save(
                update_fields=[
                    'per_paper_extraction_status',
                    'per_paper_extraction_error',
                    'per_paper_extraction_updated_at',
                ]
            )
            _emit(
                progress_callback,
                {
                    'event': 'failed',
                    'paper_id': paper.id,
                    'title': paper.title,
                    'error_code': exc.__class__.__name__,
                    'error_message': str(exc),
                },
            )

        delay_seconds = float(getattr(settings, 'DEEPSEEK_REQUEST_DELAY_SECONDS', 1.0))
        if delay_seconds > 0:
            time.sleep(delay_seconds)

    remaining = [p.id for p in papers if p.id not in set(processed_ids)]
    return {
        'targeted': len(papers),
        'processed': len(processed_ids),
        'done': done,
        'failed': failed,
        'processed_ids': processed_ids,
        'remaining_paper_ids': remaining,
        'stopped': bool(stop_check and stop_check()),
    }


def _eligible_papers(review, retry_failed_only=False):
    qs = review.papers.filter(fulltext_retrieved=True).order_by('id')
    if retry_failed_only:
        qs = qs.filter(per_paper_extraction_status='failed')
    else:
        qs = qs.exclude(per_paper_extraction_status='done')

    papers = []
    for paper in qs:
        if (paper.mineru_markdown or '').strip():
            papers.append(paper)
    return papers


def _extract_for_paper(*, review, paper, paper_text):
    if not paper_text:
        raise RuntimeError('No MinerU markdown text found for this paper.')

    questions = review.research_questions if isinstance(review.research_questions, list) else []
    questions = [str(item).strip() for item in questions if str(item).strip()]
    if not questions and str(review.research_question or '').strip():
        questions = [str(review.research_question).strip()]
    questions_block = '\n'.join(f'- {question}' for question in questions) or '- (not provided)'

    fallback_prompt = _fill_prompt_template(
        DEFAULT_PROMPT,
        {
            'research_context': str(review.research_context or '').strip() or '(not provided)',
            'research_questions_block': questions_block,
            'paper_title': str(paper.title or '').strip() or '(not provided)',
            'mineru_full_paper_text': paper_text,
        },
    )

    prompt = render_prompt_template(
        'lr_stage_4_per_paper_extraction.md',
        context={
            'research_context': str(review.research_context or '').strip() or '(not provided)',
            'research_questions_block': questions_block,
            'paper_title': str(paper.title or '').strip() or '(not provided)',
            'mineru_full_paper_text': paper_text,
        },
        fallback=fallback_prompt,
    )

    raw = _call_deepseek(prompt)
    try:
        payload = _extract_json(raw)
    except JSONDecodeError:
        correction = render_prompt_template(
            'lr_stage_4_per_paper_json_correction.md',
            context={'raw_response': raw},
            fallback=JSON_CORRECTION_FALLBACK.format(raw_response=raw),
        )
        corrected = _call_deepseek(correction)
        payload = _extract_json(corrected)

    return _normalize_payload(payload)


def _normalize_payload(payload):
    if not isinstance(payload, dict):
        raise RuntimeError('Model output is not a JSON object.')

    def _as_str(value):
        if value is None:
            return ''
        return str(value).strip()

    def _as_list_of_str(value, max_items=12):
        if not isinstance(value, list):
            return []
        out = []
        for item in value:
            text = _as_str(item)
            if text:
                out.append(text)
            if len(out) >= max_items:
                break
        return out

    title = _as_str(payload.get('title'))
    authors = _as_list_of_str(payload.get('authors'), max_items=30)
    source = _as_str(payload.get('source'))
    core_claim = _as_str(payload.get('core_claim'))
    background = _as_str(payload.get('background'))
    key_findings = _as_list_of_str(payload.get('key_findings'), max_items=10)
    limitations = _as_list_of_str(payload.get('limitations'), max_items=10)
    key_concepts = _as_list_of_str(payload.get('key_concepts'), max_items=20)
    stance = _as_str(payload.get('stance')).lower()
    quotable = _as_str(payload.get('quotable'))
    citation = _as_str(payload.get('citation'))

    try:
        year_raw = payload.get('year')
        year = int(year_raw) if year_raw not in (None, '') else None
    except (TypeError, ValueError):
        year = None

    methodology = payload.get('methodology')
    if not isinstance(methodology, dict):
        methodology = {}
    methodology_out = {
        'type': _as_str(methodology.get('type')).lower(),
        'description': _as_str(methodology.get('description')),
        'sample': _as_str(methodology.get('sample')),
    }
    if not methodology_out['sample']:
        methodology_out['sample'] = None

    if stance not in {'supports', 'challenges', 'nuances', 'reviews'}:
        stance = 'nuances'

    quality_category = _as_str(payload.get('quality_category')).upper()
    if quality_category not in {'A', 'B', 'C', 'D'}:
        quality_category = 'C'

    normalized = {
        'title': title or None,
        'authors': authors,
        'year': year,
        'source': source or None,
        'core_claim': core_claim or None,
        'background': background or None,
        'methodology': methodology_out,
        'key_findings': key_findings,
        'limitations': limitations,
        'key_concepts': key_concepts,
        'stance': stance,
        'quality_category': quality_category,
        'quotable': quotable or None,
        'citation': citation or None,
    }

    if not normalized['core_claim']:
        raise RuntimeError('Extraction missing core_claim.')
    if not normalized['key_findings']:
        raise RuntimeError('Extraction missing key_findings.')

    return normalized


def _save_payload(*, paper, payload):
    paper.per_paper_extraction = payload
    paper.per_paper_quality_category = str(payload.get('quality_category') or '').upper()
    paper.per_paper_extraction_status = 'done'
    paper.per_paper_extraction_error = ''
    paper.per_paper_extraction_updated_at = timezone.now()

    payload_citation = str(payload.get('citation') or '').strip()
    if payload_citation and not str(paper.citation_apa or '').strip():
        paper.citation_apa = payload_citation
        paper.citation_status = paper.citation_status or 'done'
        paper.citation_source = paper.citation_source or 'stage4_extract'
        update_fields = [
            'per_paper_extraction',
            'per_paper_quality_category',
            'per_paper_extraction_status',
            'per_paper_extraction_error',
            'per_paper_extraction_updated_at',
            'citation_apa',
            'citation_status',
            'citation_source',
        ]
    else:
        update_fields = [
            'per_paper_extraction',
            'per_paper_quality_category',
            'per_paper_extraction_status',
            'per_paper_extraction_error',
            'per_paper_extraction_updated_at',
        ]

    paper.save(update_fields=update_fields)


def _call_deepseek(prompt):
    api_key = getattr(settings, 'DEEPSEEK_API_KEY', '') or os.getenv('DEEPSEEK_API_KEY', '')
    if not api_key:
        raise RuntimeError('DEEPSEEK_API_KEY is not configured.')

    base_url = (getattr(settings, 'DEEPSEEK_BASE_URL', '') or os.getenv('DEEPSEEK_BASE_URL', '') or 'https://api.deepseek.com').rstrip('/')
    model_name = (
        getattr(settings, 'DEEPSEEK_LR_PER_PAPER_MODEL', '')
        or os.getenv('DEEPSEEK_LR_PER_PAPER_MODEL', '')
        or 'deepseek-reasoner'
    )
    timeout_seconds = float(getattr(settings, 'DEEPSEEK_TIMEOUT_SECONDS', 90))

    response = requests.post(
        f'{base_url}/chat/completions',
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        json={
            'model': model_name,
            'messages': [
                {'role': 'system', 'content': 'Return only valid JSON.'},
                {'role': 'user', 'content': prompt},
            ],
            'temperature': 0.0,
        },
        timeout=timeout_seconds,
    )
    if response.status_code >= 400:
        raise RuntimeError(f'DeepSeek HTTP {response.status_code}: {response.text[:1000]}')

    data = response.json()
    choices = data.get('choices') or []
    if not choices:
        raise RuntimeError('DeepSeek response missing choices.')

    message = choices[0].get('message') or {}
    content = message.get('content')
    if isinstance(content, list):
        merged = []
        for part in content:
            if isinstance(part, dict) and part.get('type') == 'text':
                merged.append(part.get('text') or '')
            elif isinstance(part, str):
                merged.append(part)
        content = '\n'.join(merged)

    text = (content or '').strip()
    if not text:
        raise RuntimeError('DeepSeek returned empty content.')
    return text


def _extract_json(raw_text):
    text = (raw_text or '').strip()
    if text.startswith('```'):
        text = text.strip('`')
        text = text.replace('json\n', '', 1).strip()

    try:
        return json.loads(text)
    except JSONDecodeError:
        decoder = json.JSONDecoder()
        for idx, char in enumerate(text):
            if char not in '[{':
                continue
            try:
                parsed, _ = decoder.raw_decode(text[idx:])
                return parsed
            except JSONDecodeError:
                continue
        raise


def _emit(callback, payload):
    if not callback:
        return
    try:
        callback(payload)
    except Exception:
        return


def _fill_prompt_template(template, values):
    text = str(template or '')
    for key, value in (values or {}).items():
        text = text.replace('{' + str(key) + '}', str(value))
    return text
