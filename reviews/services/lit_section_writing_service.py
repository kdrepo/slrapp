import json
import os
import time
from json import JSONDecodeError

import requests
from django.conf import settings

from reviews.models import LitPaperAssignment, LitReview
from reviews.services.prompt_loader import render_prompt_template


DEFAULT_STANDARD_PROMPT = """You are an academic writing assistant writing one section of a literature review.

Research question: {research_question}
Review goal: {review_goal}
Gap statement: {gap_statement}

Section to write:
  Number: {section_number}
  Title: {section_title}
  Type: {section_type}
  Purpose: {section_purpose}
  Leads to: {section_leads_to}
  Word count target: {section_word_count_target}

Papers assigned to this section:
{papers_json_array}

Return only valid JSON with:
{{
  "section_number": <integer>,
  "section_title": "<title>",
  "prose": "<section text>",
  "word_count": <integer>,
  "papers_used": [],
  "papers_unused": [],
  "notes_for_user": null
}}

Do not use em dashes in the prose.
"""

DEFAULT_GAP_PROMPT = """You are an academic writing assistant writing the final synthesis section of a literature review.

Research question: {research_question}
Gap statement: {gap_statement}

This synthesis section:
  Number: {section_number}
  Title: {section_title}
  Purpose: {section_purpose}
  Word count target: {section_word_count_target}

What the preceding sections established:
{preceding_sections_json}

Return only valid JSON with:
{{
  "section_number": <integer>,
  "section_title": "<title>",
  "prose": "<section text>",
  "word_count": <integer>,
  "notes_for_user": null
}}

Do not use em dashes in the prose.
"""

JSON_CORRECTION_FALLBACK = """Your previous response was not valid JSON.
Return ONLY one valid JSON object using the required schema.
Original response:
{raw_response}
"""


def run_lit_stage5_writing_for_review(review_id, progress_callback=None, stop_check=None, rewrite_all=False):
    review = LitReview.objects.get(pk=review_id)
    all_sections = list(review.sections.all().order_by('number', 'id'))
    if rewrite_all:
        sections = list(all_sections)
    else:
        sections = [s for s in all_sections if not str(s.prose or '').strip()]
    _emit(progress_callback, {'event': 'started', 'targeted': len(sections), 'section_ids': [s.id for s in sections]})

    done = 0
    failed = 0
    processed_ids = []

    for idx, section in enumerate(sections, start=1):
        if stop_check and stop_check():
            _emit(progress_callback, {'event': 'stopped', 'processed_ids': list(processed_ids)})
            break

        _emit(
            progress_callback,
            {
                'event': 'processing',
                'section_id': section.id,
                'section_number': section.number,
                'section_title': section.title,
                'index': idx,
                'targeted': len(sections),
            },
        )

        try:
            if (section.type or '').strip().lower() == 'gap':
                payload = _write_gap_section(review=review, section=section)
            else:
                payload = _write_standard_section(review=review, section=section)

            prose = str(payload.get('prose') or '').strip()
            if not prose:
                raise RuntimeError('Section prose is empty.')

            section.prose = prose
            section.save(update_fields=['prose'])

            done += 1
            processed_ids.append(section.id)
            _emit(
                progress_callback,
                {
                    'event': 'done',
                    'section_id': section.id,
                    'section_number': section.number,
                    'section_title': section.title,
                    'word_count': int(payload.get('word_count') or _word_count(prose)),
                    'notes_for_user': payload.get('notes_for_user') or '',
                    'papers_used': payload.get('papers_used') if isinstance(payload.get('papers_used'), list) else [],
                },
            )
        except Exception as exc:
            failed += 1
            processed_ids.append(section.id)
            _emit(
                progress_callback,
                {
                    'event': 'failed',
                    'section_id': section.id,
                    'section_number': section.number,
                    'section_title': section.title,
                    'error_code': exc.__class__.__name__,
                    'error_message': str(exc),
                },
            )

        delay_seconds = float(getattr(settings, 'DEEPSEEK_REQUEST_DELAY_SECONDS', 1.0))
        if delay_seconds > 0:
            time.sleep(delay_seconds)

    remaining = [s.id for s in sections if s.id not in set(processed_ids)]
    actual_total = sum(_word_count(str(s.prose or '')) for s in review.sections.all())
    target_total = int(review.total_words_allocated or 0)
    drift_pct = 0.0
    if target_total > 0:
        drift_pct = ((actual_total - target_total) / float(target_total)) * 100.0
    return {
        'targeted': len(sections),
        'processed': len(processed_ids),
        'done': done,
        'failed': failed,
        'processed_ids': processed_ids,
        'remaining_section_ids': remaining,
        'stopped': bool(stop_check and stop_check()),
        'actual_total_words': actual_total,
        'target_total_words': target_total,
        'drift_pct': round(drift_pct, 2),
        'drift_warning': bool(abs(drift_pct) > 10.0) if target_total > 0 else False,
    }


def _write_standard_section(*, review, section):
    assignments = (
        LitPaperAssignment.objects
        .filter(review=review, section=section)
        .select_related('paper')
        .order_by('paper_id')
    )
    papers_json_array = []
    for assignment in assignments:
        extraction = assignment.paper.per_paper_extraction if isinstance(assignment.paper.per_paper_extraction, dict) else {}
        papers_json_array.append(
            {
                'paper_id': assignment.paper_id,
                'title': assignment.paper.title,
                'core_claim': extraction.get('core_claim'),
                'key_findings': extraction.get('key_findings'),
                'limitations': extraction.get('limitations'),
                'stance': extraction.get('stance'),
                'how_to_use': assignment.how_to_use,
                'citation_apa': assignment.paper.citation_apa or extraction.get('citation'),
            }
        )

    papers_json_text = json.dumps(papers_json_array, ensure_ascii=False, indent=2)
    fallback_prompt = _fill_prompt_template(
        DEFAULT_STANDARD_PROMPT,
        {
            'research_question': str(review.research_question or ''),
            'review_goal': str(review.review_goal or ''),
            'gap_statement': str(review.gap_statement or ''),
            'section_number': section.number,
            'section_title': str(section.title or ''),
            'section_type': str(section.type or ''),
            'section_purpose': str(section.purpose or ''),
            'section_leads_to': str(section.leads_to or ''),
            'section_word_count_target': int(section.word_count_target or 0),
            'papers_json_array': papers_json_text,
        },
    )
    prompt = render_prompt_template(
        'lr_stage_5a_section_write.md',
        context={
            'research_question': str(review.research_question or ''),
            'review_goal': str(review.review_goal or ''),
            'gap_statement': str(review.gap_statement or ''),
            'section_number': section.number,
            'section_title': str(section.title or ''),
            'section_type': str(section.type or ''),
            'section_purpose': str(section.purpose or ''),
            'section_leads_to': str(section.leads_to or ''),
            'section_word_count_target': int(section.word_count_target or 0),
            'papers_json_array': papers_json_text,
        },
        fallback=fallback_prompt,
    )
    return _call_and_parse_json(prompt=prompt, gap_mode=False)


def _write_gap_section(*, review, section):
    previous_sections = []
    for row in review.sections.filter(number__lt=section.number).order_by('number', 'id'):
        prose = str(row.prose or '').strip()
        if not prose:
            continue
        previous_sections.append(
            {
                'section_number': row.number,
                'section_title': row.title,
                'prose': prose,
            }
        )
    if not previous_sections:
        raise RuntimeError('Gap section requires preceding section prose, but none is available.')

    preceding_sections_json = json.dumps(previous_sections, ensure_ascii=False, indent=2)
    fallback_prompt = _fill_prompt_template(
        DEFAULT_GAP_PROMPT,
        {
            'research_question': str(review.research_question or ''),
            'gap_statement': str(review.gap_statement or ''),
            'section_number': section.number,
            'section_title': str(section.title or ''),
            'section_purpose': str(section.purpose or ''),
            'section_word_count_target': int(section.word_count_target or 0),
            'preceding_sections_json': preceding_sections_json,
        },
    )
    prompt = render_prompt_template(
        'lr_stage_5a_gap_write.md',
        context={
            'research_question': str(review.research_question or ''),
            'gap_statement': str(review.gap_statement or ''),
            'section_number': section.number,
            'section_title': str(section.title or ''),
            'section_purpose': str(section.purpose or ''),
            'section_word_count_target': int(section.word_count_target or 0),
            'preceding_sections_json': preceding_sections_json,
        },
        fallback=fallback_prompt,
    )
    return _call_and_parse_json(prompt=prompt, gap_mode=True)


def _call_and_parse_json(*, prompt, gap_mode):
    raw = _call_deepseek(prompt)
    try:
        payload = _extract_json(raw)
    except JSONDecodeError:
        correction = render_prompt_template(
            'lr_stage_5a_json_correction.md',
            context={'raw_response': raw},
            fallback=JSON_CORRECTION_FALLBACK.format(raw_response=raw),
        )
        corrected = _call_deepseek(correction)
        payload = _extract_json(corrected)

    return _normalize_section_payload(payload=payload, gap_mode=gap_mode)


def _normalize_section_payload(*, payload, gap_mode):
    if not isinstance(payload, dict):
        raise RuntimeError('Stage 5a output is not a JSON object.')

    def _as_str(value):
        if value is None:
            return ''
        return str(value).strip()

    prose = _as_str(payload.get('prose'))
    if not prose:
        raise RuntimeError('Stage 5a output missing prose.')

    try:
        word_count = int(payload.get('word_count'))
    except (TypeError, ValueError):
        word_count = _word_count(prose)

    normalized = {
        'section_number': payload.get('section_number'),
        'section_title': _as_str(payload.get('section_title')),
        'prose': prose,
        'word_count': word_count,
        'notes_for_user': _as_str(payload.get('notes_for_user')) or '',
    }

    if not gap_mode:
        papers_used = payload.get('papers_used')
        papers_unused = payload.get('papers_unused')
        if not isinstance(papers_used, list):
            papers_used = []
        if not isinstance(papers_unused, list):
            papers_unused = []
        normalized['papers_used'] = [str(item).strip() for item in papers_used if str(item).strip()]
        normalized['papers_unused'] = [str(item).strip() for item in papers_unused if str(item).strip()]
    return normalized


def _word_count(text):
    return len([tok for tok in str(text or '').split() if tok.strip()])


def _call_deepseek(prompt):
    api_key = getattr(settings, 'DEEPSEEK_API_KEY', '') or os.getenv('DEEPSEEK_API_KEY', '')
    if not api_key:
        raise RuntimeError('DEEPSEEK_API_KEY is not configured.')

    base_url = (getattr(settings, 'DEEPSEEK_BASE_URL', '') or os.getenv('DEEPSEEK_BASE_URL', '') or 'https://api.deepseek.com').rstrip('/')
    model_name = (
        getattr(settings, 'DEEPSEEK_LR_STAGE5_MODEL', '')
        or os.getenv('DEEPSEEK_LR_STAGE5_MODEL', '')
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
        raise RuntimeError(f'DeepSeek HTTP {response.status_code}: {response.text[:1200]}')

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


