import json
import os
from json import JSONDecodeError

import requests
from django.conf import settings
from django.utils import timezone

from reviews.models import LitReview
from reviews.services.prompt_loader import render_prompt_template


DEFAULT_STITCH_PROMPT = """You are an academic writing assistant finalizing a literature review.

You will receive all written sections in order, plus the gap statement.

Your job is to write the connective tissue only - do not rewrite the sections themselves.

Important guard:
- Do not restate, dilute, or replace the gap conclusion already established in the final section.
- The closing paragraph should synthesize and bridge, not create a second gap section.
- Do not use em dashes in the prose.

Write:
1. An opening paragraph (5-7 sentences) framing the domain and signposting what the review covers
2. A transition sentence between each pair of adjacent sections (only where the join needs smoothing)
3. A closing paragraph (5-7 sentences) synthesizing what the sections established,
   ending with the gap statement lightly reworded to flow naturally

The opening + closing together should use approximately 10% of the total review word count.

Output this JSON:
{
  "intro_paragraph": "",
  "transitions": [
    {
      "after_section": 0,
      "before_section": 0,
      "transition_sentence": null
    }
  ],
  "closing_paragraph": ""
}

Research question: {research_question}
Gap statement: {gap_statement}
Total target word count: {target_word_count}

Sections in order:
{sections_in_order_json}
"""

JSON_CORRECTION_FALLBACK = """Your previous response was not valid JSON.
Return ONLY one valid JSON object using the required schema.
Original response:
{raw_response}
"""


def run_lit_stage5b_stitch_for_review(review_id, progress_callback=None, stop_check=None):
    review = LitReview.objects.get(pk=review_id)
    sections = list(review.sections.all().order_by('number', 'id'))
    sections_payload = []
    for section in sections:
        prose = str(section.prose or '').strip()
        if not prose:
            continue
        sections_payload.append(
            {
                'section_number': section.number,
                'section_title': section.title,
                'prose': prose,
            }
        )
    if not sections_payload:
        raise RuntimeError('No written section prose found. Complete Stage 5a first.')

    if stop_check and stop_check():
        return {'stopped': True}

    _emit(
        progress_callback,
        {
            'event': 'started',
            'sections_count': len(sections_payload),
        },
    )

    _emit(progress_callback, {'event': 'processing'})
    payload = _generate_stitch_payload(review=review, sections_payload=sections_payload)

    if stop_check and stop_check():
        return {'stopped': True}

    final_text = _assemble_final_text(
        sections=sections,
        intro_paragraph=payload['intro_paragraph'],
        transitions=payload['transitions'],
        closing_paragraph=payload['closing_paragraph'],
    )
    review.final_prose = final_text
    review.status = LitReview.Status.DONE
    review.save(update_fields=['final_prose', 'status'])

    _emit(
        progress_callback,
        {
            'event': 'done',
            'final_words': _word_count(final_text),
            'intro_words': _word_count(payload['intro_paragraph']),
            'closing_words': _word_count(payload['closing_paragraph']),
        },
    )

    return {
        'stopped': False,
        'sections_count': len(sections_payload),
        'final_words': _word_count(final_text),
        'intro_words': _word_count(payload['intro_paragraph']),
        'closing_words': _word_count(payload['closing_paragraph']),
    }


def _generate_stitch_payload(*, review, sections_payload):
    sections_in_order_json = json.dumps(sections_payload, ensure_ascii=False, indent=2)
    fallback_prompt = _fill_prompt_template(
        DEFAULT_STITCH_PROMPT,
        {
            'research_question': str(review.research_question or ''),
            'gap_statement': str(review.gap_statement or ''),
            'target_word_count': int(review.target_word_count or 0),
            'sections_in_order_json': sections_in_order_json,
        },
    )

    prompt = render_prompt_template(
        'lr_stage_5b_stitch.md',
        context={
            'research_question': str(review.research_question or ''),
            'gap_statement': str(review.gap_statement or ''),
            'target_word_count': int(review.target_word_count or 0),
            'sections_in_order_json': sections_in_order_json,
        },
        fallback=fallback_prompt,
    )

    raw = _call_deepseek(prompt)
    try:
        parsed = _extract_json(raw)
    except JSONDecodeError:
        correction = render_prompt_template(
            'lr_stage_5b_json_correction.md',
            context={'raw_response': raw},
            fallback=JSON_CORRECTION_FALLBACK.format(raw_response=raw),
        )
        corrected = _call_deepseek(correction)
        parsed = _extract_json(corrected)

    return _normalize_stitch_payload(parsed)


def _normalize_stitch_payload(payload):
    if not isinstance(payload, dict):
        raise RuntimeError('Stage 5b output is not a JSON object.')

    def _as_str(value):
        if value is None:
            return ''
        return str(value).strip()

    intro = _as_str(payload.get('intro_paragraph'))
    closing = _as_str(payload.get('closing_paragraph'))
    transitions = payload.get('transitions')
    if not isinstance(transitions, list):
        transitions = []

    normalized_transitions = []
    for row in transitions:
        if not isinstance(row, dict):
            continue
        try:
            after_section = int(row.get('after_section'))
            before_section = int(row.get('before_section'))
        except (TypeError, ValueError):
            continue
        sentence = row.get('transition_sentence')
        sentence = _as_str(sentence)
        normalized_transitions.append(
            {
                'after_section': after_section,
                'before_section': before_section,
                'transition_sentence': sentence or '',
            }
        )

    if not intro:
        raise RuntimeError('Stage 5b output missing intro_paragraph.')
    if not closing:
        raise RuntimeError('Stage 5b output missing closing_paragraph.')

    return {
        'intro_paragraph': intro,
        'transitions': normalized_transitions,
        'closing_paragraph': closing,
    }


def _assemble_final_text(*, sections, intro_paragraph, transitions, closing_paragraph):
    transition_map = {}
    for row in transitions:
        key = (int(row['after_section']), int(row['before_section']))
        transition_map[key] = str(row.get('transition_sentence') or '').strip()

    chunks = [intro_paragraph.strip()]
    ordered_sections = list(sections)
    for idx, section in enumerate(ordered_sections):
        heading = f'{section.number}. {section.title}'.strip()
        prose = str(section.prose or '').strip()
        if heading:
            chunks.append(heading)
        if prose:
            chunks.append(prose)

        if idx < len(ordered_sections) - 1:
            nxt = ordered_sections[idx + 1]
            bridge = transition_map.get((int(section.number), int(nxt.number)), '').strip()
            if bridge:
                chunks.append(bridge)

    chunks.append(closing_paragraph.strip())
    return '\n\n'.join(part for part in chunks if str(part or '').strip())


def _word_count(text):
    return len([tok for tok in str(text or '').split() if tok.strip()])


def _call_deepseek(prompt):
    api_key = getattr(settings, 'DEEPSEEK_API_KEY', '') or os.getenv('DEEPSEEK_API_KEY', '')
    if not api_key:
        raise RuntimeError('DEEPSEEK_API_KEY is not configured.')

    base_url = (getattr(settings, 'DEEPSEEK_BASE_URL', '') or os.getenv('DEEPSEEK_BASE_URL', '') or 'https://api.deepseek.com').rstrip('/')
    model_name = (
        getattr(settings, 'DEEPSEEK_LR_STAGE5B_MODEL', '')
        or os.getenv('DEEPSEEK_LR_STAGE5B_MODEL', '')
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
