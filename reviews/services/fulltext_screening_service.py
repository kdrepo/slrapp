import json
import os
from json import JSONDecodeError

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from reviews.models import Paper, Review
from reviews.services.prompt_loader import render_prompt_template

FULLTEXT_SCREENING_PROMPT_FALLBACK = '''Your role: You are a full-text screener for a systematic literature review.
You have already passed title-and-abstract screening.
Read the full paper and make a final inclusion or exclusion decision against the provided review context.

{context_block}

Decision rules:
- Include only when the paper directly addresses one or more listed research questions and satisfies inclusion criteria.
- Exclude when criteria are not met or RQ linkage is only incidental.
- Use only evidence from the provided full text.

Output Format
Return ONLY JSON object:
{
  "full_text_decision": "included" | "excluded",
  "exclusion_reason": "..." | null,
  "rq_tags": ["RQ1", "RQ3"],
  "rq_findings_map": {
    "RQ1": "1-2 sentence evidence-grounded summary for this RQ",
    "RQ3": "1-2 sentence evidence-grounded summary for this RQ"
  },
  "notes": "Any quality concerns, scope limitations, data extraction flags, or uncertainty"
}

Rules for rq_tags and rq_findings_map:
- rq_tags must reference only RQ IDs provided in the context block (e.g., RQ1, RQ2, RQ3).
- Include only RQs that are directly supported by findings in the paper.
- If excluded and no RQ is directly addressed, return an empty array for rq_tags and an empty object for rq_findings_map.

Paper Title: {paper_title}

PAPER FULL TEXT:
{paper_text}
'''

JSON_CORRECTION_PROMPT_FALLBACK = (
    'Your previous response was not valid JSON. Return ONLY valid JSON object from that response, no markdown fences.\n'
    'Original response:\n{raw_response}'
)


def run_full_text_screening_for_review(review_id, progress_callback=None, stop_check=None, retry_failed_only=False):
    review = Review.objects.get(pk=review_id)
    chunk_size = max(1, int(getattr(settings, 'FULLTEXT_SCREENING_CHUNK_SIZE', 5)))
    model_name = getattr(settings, 'DEEPSEEK_FULLTEXT_MODEL', 'deepseek-reasoner')

    papers = _eligible_papers_for_screening(review, retry_failed_only=retry_failed_only)
    _emit(progress_callback, {'event': 'started', 'targeted': len(papers), 'paper_ids': [p.id for p in papers], 'chunk_size': chunk_size})

    processed_ids = []
    done = 0
    failed = 0

    for chunk_start in range(0, len(papers), chunk_size):
        if stop_check and stop_check():
            _emit(progress_callback, {'event': 'stopped', 'processed_ids': list(processed_ids)})
            break

        chunk = papers[chunk_start:chunk_start + chunk_size]
        for paper in chunk:
            if stop_check and stop_check():
                _emit(progress_callback, {'event': 'stopped', 'processed_ids': list(processed_ids)})
                break

            _emit(progress_callback, {'event': 'processing', 'paper_id': paper.id, 'title': paper.title})

            try:
                payload = _screen_one_paper_deepseek(review, paper, model_name=model_name)
                _save_full_text_result(paper, payload, provider='deepseek', model_name=model_name)
                done += 1
                processed_ids.append(paper.id)
                _emit(progress_callback, {
                    'event': 'done',
                    'paper_id': paper.id,
                    'title': paper.title,
                    'decision': paper.full_text_decision,
                })
            except Exception as exc:
                failed += 1
                processed_ids.append(paper.id)
                paper.full_text_screening_status = 'failed'
                paper.full_text_screening_error = f'{exc.__class__.__name__}: {exc}'
                paper.full_text_screening_provider = 'deepseek'
                paper.full_text_screening_model = model_name
                paper.save(update_fields=['full_text_screening_status', 'full_text_screening_error', 'full_text_screening_provider', 'full_text_screening_model'])
                _emit(progress_callback, {'event': 'failed', 'paper_id': paper.id, 'title': paper.title, 'error_code': exc.__class__.__name__, 'error_message': str(exc)})

    remaining = [p.id for p in papers if p.id not in set(processed_ids)]
    return {
        'targeted': len(papers),
        'processed': len(processed_ids),
        'done': done,
        'failed': failed,
        'processed_ids': processed_ids,
        'remaining_paper_ids': remaining,
        'stopped': bool(stop_check and stop_check()),
        'chunk_size': chunk_size,
    }


def _eligible_papers_for_screening(review, retry_failed_only=False):
    qs = review.papers.filter(
        ta_decision=Paper.TADecision.INCLUDED,
        fulltext_retrieved=True,
    ).order_by('id')

    if retry_failed_only:
        qs = qs.filter(Q(full_text_screening_status='failed') | Q(full_text_decision=Paper.FullTextDecision.MANUAL_FLAG))
    else:
        qs = qs.filter(full_text_decision=Paper.FullTextDecision.NOT_SCREENED)

    papers = []
    for paper in qs:
        if (paper.mineru_markdown or '').strip():
            papers.append(paper)
    return papers


def _build_context_block(review):
    rqs = list(review.research_questions.order_by('id'))
    if rqs:
        rq_lines = '\n'.join(
            f'RQ{index + 1}: {rq.question_text}' for index, rq in enumerate(rqs)
        )
    else:
        rq_lines = 'No locked research questions found.'

    return (
        f'Review Objectives:\n{review.objectives or ""}\n\n'
        f'Locked Research Questions:\n{rq_lines}\n\n'
        f'Inclusion Criteria:\n{review.inclusion_criteria or ""}\n\n'
        f'Exclusion Criteria:\n{review.exclusion_criteria or ""}'
    )


def _screen_one_paper_deepseek(review, paper, model_name):
    paper_text = (paper.mineru_markdown or '').strip()
    if not paper_text:
        raise RuntimeError('No text available for full-text screening.')

    prompt = render_prompt_template(
        'phase_15_fulltext_screening.md',
        context={
            'context_block': _build_context_block(review),
            'paper_title': paper.title,
            'paper_text': paper_text,
        },
        fallback=FULLTEXT_SCREENING_PROMPT_FALLBACK,
    )

    raw_text = _call_deepseek(prompt=prompt, model_name=model_name)
    try:
        payload = _extract_json(raw_text)
    except JSONDecodeError:
        corrected = _call_deepseek(
            prompt=render_prompt_template(
                'phase_15_json_correction.md',
                context={'raw_response': raw_text},
                fallback=JSON_CORRECTION_PROMPT_FALLBACK,
            ),
            model_name=model_name,
        )
        payload = _extract_json(corrected)

    if not isinstance(payload, dict):
        raise RuntimeError('DeepSeek full-text response was not a JSON object.')

    return payload


def _save_full_text_result(paper, payload, provider, model_name):
    decision = str(payload.get('full_text_decision', '')).strip().lower()
    if decision not in {Paper.FullTextDecision.INCLUDED, Paper.FullTextDecision.EXCLUDED}:
        decision = Paper.FullTextDecision.MANUAL_FLAG

    exclusion_reason = payload.get('exclusion_reason')
    if exclusion_reason in (None, 'null'):
        exclusion_reason = ''

    rq_tags = payload.get('rq_tags')
    if not isinstance(rq_tags, list):
        rq_tags = []
    rq_tags = [str(item).strip() for item in rq_tags if str(item).strip()]

    rq_findings_map = payload.get('rq_findings_map')
    if not isinstance(rq_findings_map, dict):
        rq_findings_map = {}

    rq1 = payload.get('rq1_findings_summary')
    rq2 = payload.get('rq2_findings_summary')
    if rq1 in (None, 'null', '') or rq2 in (None, 'null', ''):
        derived_rq1, derived_rq2 = _derive_rq_summaries(rq_tags=rq_tags, rq_findings_map=rq_findings_map)
        if rq1 in (None, 'null', ''):
            rq1 = derived_rq1
        if rq2 in (None, 'null', ''):
            rq2 = derived_rq2

    notes = payload.get('notes')
    notes_text = '' if notes in (None, 'null') else str(notes).strip()
    if rq_findings_map:
        serialized_map = json.dumps(rq_findings_map, ensure_ascii=False)
        notes_text = f'{notes_text}\nRQ findings map: {serialized_map}'.strip()

    paper.full_text_decision = decision
    paper.full_text_exclusion_reason = str(exclusion_reason or '').strip()
    paper.full_text_rq_tags = rq_tags
    paper.full_text_rq_findings_map = rq_findings_map
    paper.full_text_rq1_findings_summary = '' if rq1 in (None, 'null') else str(rq1).strip()
    paper.full_text_rq2_findings_summary = '' if rq2 in (None, 'null') else str(rq2).strip()
    paper.full_text_notes = notes_text
    paper.full_text_screening_provider = provider
    paper.full_text_screening_model = model_name
    paper.full_text_screening_status = 'screened'
    paper.full_text_screening_error = ''
    paper.full_text_screened_at = timezone.now()

    if decision == Paper.FullTextDecision.INCLUDED:
        paper.ta_decision = Paper.TADecision.INCLUDED
    elif decision == Paper.FullTextDecision.EXCLUDED:
        paper.ta_decision = Paper.TADecision.EXCLUDED
    else:
        paper.ta_decision = Paper.TADecision.MANUAL_FLAG

    with transaction.atomic():
        paper.save(update_fields=[
            'full_text_decision',
            'full_text_exclusion_reason',
            'full_text_rq_tags',
            'full_text_rq_findings_map',
            'full_text_rq1_findings_summary',
            'full_text_rq2_findings_summary',
            'full_text_notes',
            'full_text_screening_provider',
            'full_text_screening_model',
            'full_text_screening_status',
            'full_text_screening_error',
            'full_text_screened_at',
            'ta_decision',
        ])


def _derive_rq_summaries(rq_tags, rq_findings_map):
    ordered_keys = []
    for key in rq_tags:
        if key in rq_findings_map and key not in ordered_keys:
            ordered_keys.append(key)
    for key in rq_findings_map.keys():
        if key not in ordered_keys:
            ordered_keys.append(key)

    first = ''
    second = ''
    if ordered_keys:
        first = str(rq_findings_map.get(ordered_keys[0]) or '').strip()
    if len(ordered_keys) > 1:
        second = str(rq_findings_map.get(ordered_keys[1]) or '').strip()
    return first, second


def _call_deepseek(prompt, model_name):
    api_key = getattr(settings, 'DEEPSEEK_API_KEY', '') or os.getenv('DEEPSEEK_API_KEY', '')
    if not api_key:
        raise RuntimeError('DEEPSEEK_API_KEY is not configured.')

    base_url = (getattr(settings, 'DEEPSEEK_BASE_URL', '') or os.getenv('DEEPSEEK_BASE_URL', '') or 'https://api.deepseek.com').rstrip('/')
    timeout_seconds = float(getattr(settings, 'DEEPSEEK_TIMEOUT_SECONDS', 90))

    url = f'{base_url}/chat/completions'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    payload = {
        'model': model_name,
        'messages': [
            {'role': 'system', 'content': 'Return only valid JSON.'},
            {'role': 'user', 'content': prompt},
        ],
        'temperature': 0.0,
    }

    response = requests.post(url, headers=headers, json=payload, timeout=timeout_seconds)
    if response.status_code >= 400:
        detail = response.text[:1000]
        raise RuntimeError(f'DeepSeek HTTP {response.status_code}: {detail}')

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
        raise RuntimeError('DeepSeek returned empty full-text screening content.')

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
        for index, char in enumerate(text):
            if char not in '[{':
                continue
            try:
                parsed, _ = decoder.raw_decode(text[index:])
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





