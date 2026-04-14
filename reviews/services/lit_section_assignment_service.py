import json
import os
import time
from json import JSONDecodeError

import requests
from django.conf import settings
from django.db import models
from django.utils import timezone

from reviews.models import LitPaperAssignment, LitReview
from reviews.services.prompt_loader import render_prompt_template


DEFAULT_PROMPT = """You are a research assistant organizing papers into a literature review structure.

Literature review structure:
{review_structure_json}

Paper summary:
{paper_extraction_json}

Return only valid JSON:
{
  "paper_title": "",
  "assigned_section": 0,
  "assignment_confidence": "high|medium|low",
  "reason": "",
  "how_to_use": "",
  "also_relevant_to": [],
  "flag": null
}
"""

JSON_CORRECTION_FALLBACK = """Your previous response was not valid JSON.
Return ONLY one valid JSON object using the required schema.
Original response:
{raw_response}
"""

ALLOWED_FLAGS = {'', 'contradicts_another_paper', 'very_high_impact', 'methodology_concern', 'too_tangential'}
ALLOWED_CONFIDENCE = {'high', 'medium', 'low'}


def run_lit_section_assignment_for_review(review_id, progress_callback=None, stop_check=None, reassign_all=False):
    review = LitReview.objects.get(pk=review_id)
    section_map = _section_map(review)
    if not section_map:
        raise RuntimeError('No review sections found. Complete Stage 1 first.')

    papers = _eligible_papers(review=review, reassign_all=reassign_all)
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
            paper.section_assignment_status = 'running'
            paper.section_assignment_error = ''
            paper.section_assignment_updated_at = timezone.now()
            paper.save(
                update_fields=[
                    'section_assignment_status',
                    'section_assignment_error',
                    'section_assignment_updated_at',
                ]
            )

            payload = _assign_single_paper(review=review, paper=paper, section_map=section_map)
            section = section_map[payload['assigned_section']]
            LitPaperAssignment.objects.update_or_create(
                review=review,
                paper=paper,
                defaults={
                    'section': section,
                    'assignment_confidence': payload['assignment_confidence'],
                    'reason': payload['reason'],
                    'how_to_use': payload['how_to_use'],
                    'also_relevant_to': payload['also_relevant_to'],
                    'flag': payload['flag'],
                    'raw_payload': payload,
                },
            )

            paper.section_assignment_status = 'done'
            paper.section_assignment_error = ''
            paper.section_assignment_updated_at = timezone.now()
            paper.save(
                update_fields=[
                    'section_assignment_status',
                    'section_assignment_error',
                    'section_assignment_updated_at',
                ]
            )

            done += 1
            processed_ids.append(paper.id)
            _emit(
                progress_callback,
                {
                    'event': 'done',
                    'paper_id': paper.id,
                    'title': paper.title,
                    'assigned_section': payload['assigned_section'],
                    'assignment_confidence': payload['assignment_confidence'],
                    'flag': payload['flag'],
                },
            )
        except Exception as exc:
            failed += 1
            processed_ids.append(paper.id)
            paper.section_assignment_status = 'failed'
            paper.section_assignment_error = f'{exc.__class__.__name__}: {exc}'
            paper.section_assignment_updated_at = timezone.now()
            paper.save(
                update_fields=[
                    'section_assignment_status',
                    'section_assignment_error',
                    'section_assignment_updated_at',
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
    coverage = _section_coverage(review=review)
    return {
        'targeted': len(papers),
        'processed': len(processed_ids),
        'done': done,
        'failed': failed,
        'processed_ids': processed_ids,
        'remaining_paper_ids': remaining,
        'stopped': bool(stop_check and stop_check()),
        'missing_section_numbers': coverage['missing_section_numbers'],
        'too_tangential_count': coverage['too_tangential_count'],
    }


def _eligible_papers(review, reassign_all=False):
    qs = review.papers.filter(
        per_paper_extraction_status='done',
    ).exclude(per_paper_extraction={}).order_by('id')

    if not reassign_all:
        assigned_ids = set(
            review.paper_assignments.values_list('paper_id', flat=True)
        )
        papers = [p for p in qs if p.id not in assigned_ids]
    else:
        papers = list(qs)

    return papers


def _section_map(review):
    sections = review.sections.all().order_by('number', 'id')
    return {int(s.number): s for s in sections}


def _review_structure_json(review):
    rows = []
    for section in review.sections.all().order_by('number', 'id'):
        rows.append(
            {
                'number': int(section.number),
                'title': section.title,
                'type': section.type,
                'purpose': section.purpose,
            }
        )
    return json.dumps(rows, ensure_ascii=False, indent=2)


def _assign_single_paper(*, review, paper, section_map):
    extraction = paper.per_paper_extraction if isinstance(paper.per_paper_extraction, dict) else {}
    if not extraction:
        raise RuntimeError('Paper extraction payload is missing.')

    review_structure_json = _review_structure_json(review)
    paper_extraction_json = json.dumps(extraction, ensure_ascii=False, indent=2)

    fallback_prompt = _fill_prompt_template(
        DEFAULT_PROMPT,
        {
            'review_structure_json': review_structure_json,
            'paper_extraction_json': paper_extraction_json,
        },
    )
    prompt = render_prompt_template(
        'lr_stage_4b_assignment.md',
        context={
            'review_structure_json': review_structure_json,
            'paper_extraction_json': paper_extraction_json,
        },
        fallback=fallback_prompt,
    )

    raw = _call_deepseek(prompt)
    try:
        payload = _extract_json(raw)
    except JSONDecodeError:
        correction = render_prompt_template(
            'lr_stage_4b_assignment_json_correction.md',
            context={'raw_response': raw},
            fallback=JSON_CORRECTION_FALLBACK.format(raw_response=raw),
        )
        corrected = _call_deepseek(correction)
        payload = _extract_json(corrected)

    return _normalize_assignment(payload=payload, section_map=section_map, default_title=paper.title)


def _normalize_assignment(*, payload, section_map, default_title):
    if not isinstance(payload, dict):
        raise RuntimeError('Assignment output is not a JSON object.')

    section_numbers = sorted(section_map.keys())
    if not section_numbers:
        raise RuntimeError('No sections available for assignment.')

    def _as_str(value):
        if value is None:
            return ''
        return str(value).strip()

    try:
        assigned_section = int(payload.get('assigned_section'))
    except (TypeError, ValueError):
        assigned_section = section_numbers[0]

    if assigned_section not in section_map:
        assigned_section = section_numbers[0]

    confidence = _as_str(payload.get('assignment_confidence')).lower()
    if confidence not in ALLOWED_CONFIDENCE:
        confidence = 'low'

    reason = _as_str(payload.get('reason'))
    how_to_use = _as_str(payload.get('how_to_use'))
    if not reason:
        reason = 'Assigned based on closest thematic fit to the section purpose.'
    if not how_to_use:
        how_to_use = 'Use as supporting evidence for this section topic.'

    also = payload.get('also_relevant_to')
    if not isinstance(also, list):
        also = []
    also_clean = []
    for item in also:
        try:
            n = int(item)
        except (TypeError, ValueError):
            continue
        if n in section_map and n != assigned_section and n not in also_clean:
            also_clean.append(n)

    flag = _as_str(payload.get('flag'))
    if flag.lower() == 'null':
        flag = ''
    if flag not in ALLOWED_FLAGS:
        flag = ''

    normalized = {
        'paper_title': _as_str(payload.get('paper_title')) or _as_str(default_title),
        'assigned_section': assigned_section,
        'assignment_confidence': confidence,
        'reason': reason,
        'how_to_use': how_to_use,
        'also_relevant_to': also_clean,
        'flag': flag,
    }
    return normalized


def _section_coverage(review):
    section_numbers = set(review.sections.values_list('number', flat=True))
    counts = {}
    for row in review.paper_assignments.values('section__number').annotate(n=models.Count('id')):
        counts[int(row['section__number'])] = int(row['n'])
    missing = sorted([int(num) for num in section_numbers if counts.get(int(num), 0) == 0])
    tangential = review.paper_assignments.filter(flag='too_tangential').count()
    return {'missing_section_numbers': missing, 'too_tangential_count': tangential}


def _call_deepseek(prompt):
    api_key = getattr(settings, 'DEEPSEEK_API_KEY', '') or os.getenv('DEEPSEEK_API_KEY', '')
    if not api_key:
        raise RuntimeError('DEEPSEEK_API_KEY is not configured.')

    base_url = (getattr(settings, 'DEEPSEEK_BASE_URL', '') or os.getenv('DEEPSEEK_BASE_URL', '') or 'https://api.deepseek.com').rstrip('/')
    model_name = (
        getattr(settings, 'DEEPSEEK_LR_ASSIGN_MODEL', '')
        or os.getenv('DEEPSEEK_LR_ASSIGN_MODEL', '')
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
