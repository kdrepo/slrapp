import json
import os
import re
from json import JSONDecodeError

import requests
from django.conf import settings
from django.utils import timezone

from reviews.models import Paper, Review
from reviews.services.prompt_loader import render_prompt_template


TITLE_SCREENING_PROMPT_FALLBACK = '''You are an expert research assistant helping with a Systematic Literature Review (SLR).

Your task is to screen research paper titles based on the provided Research Questions (RQs), Objectives, and PICO.

Research Questions:
{research_questions}

Objectives:
{objectives}

PICO:
Population: {pico_population}
Intervention: {pico_intervention}
Comparison: {pico_comparison}
Outcomes: {pico_outcomes}

Inclusion Criteria:
- The title is relevant to at least one research question or objective
- The study appears to address the main topic/domain of the SLR
- The paper likely contains empirical, theoretical, or review-based contributions

Exclusion Criteria:
- Clearly unrelated to the topic
- Focuses on a different domain or problem

For each title, classify it into one of:
- Include
- Exclude
- Uncertain

Output Format (STRICT):
Title: <title text>
paperid: <paper_id>
Decision: Include / Exclude / Uncertain
Reason: <short reason>

Titles to Screen:
{titles_block}
'''

JSON_CORRECTION_PROMPT_FALLBACK = (
    'Your previous response was malformed. Return ONLY valid JSON array from that response. '
    'Each item must contain: paperid, title, decision, reason.\n'
    'Original response:\n{raw_response}'
)


_DECISION_MAP = {
    'include': Paper.TitleScreeningDecision.INCLUDED,
    'included': Paper.TitleScreeningDecision.INCLUDED,
    'exclude': Paper.TitleScreeningDecision.EXCLUDED,
    'excluded': Paper.TitleScreeningDecision.EXCLUDED,
    'uncertain': Paper.TitleScreeningDecision.UNCERTAIN,
}


def run_title_screening_for_review(review_id, retry_failed_only=False, progress_callback=None, stop_check=None):
    review = Review.objects.get(pk=review_id)
    model_name = getattr(settings, 'DEEPSEEK_TITLE_SCREENING_MODEL', '') or os.getenv('DEEPSEEK_TITLE_SCREENING_MODEL', '') or 'deepseek-chat'
    chunk_size = max(1, int(getattr(settings, 'TITLE_SCREENING_CHUNK_SIZE', 25)))

    papers = _eligible_papers(review=review, retry_failed_only=retry_failed_only)
    _emit(progress_callback, {'event': 'started', 'targeted': len(papers), 'chunk_size': chunk_size, 'paper_ids': [p.id for p in papers]})

    if not papers:
        return {
            'targeted': 0,
            'processed': 0,
            'done': 0,
            'failed': 0,
            'stopped': False,
            'remaining_paper_ids': [],
        }

    done = 0
    failed = 0
    processed = 0
    processed_ids = []

    for i in range(0, len(papers), chunk_size):
        if stop_check and stop_check():
            _emit(progress_callback, {'event': 'stopped'})
            break

        chunk = papers[i:i + chunk_size]

        for paper in chunk:
            if stop_check and stop_check():
                _emit(progress_callback, {'event': 'stopped'})
                break
            _emit(progress_callback, {'event': 'processing', 'paper_id': paper.id, 'title': paper.title})
            paper.title_screening_status = 'running'
            paper.title_screening_error = ''
            paper.save(update_fields=['title_screening_status', 'title_screening_error'])

        if stop_check and stop_check():
            break

        try:
            payload = _screen_chunk(review=review, papers=chunk, model_name=model_name)
            _apply_chunk_payload(chunk=chunk, payload=payload, model_name=model_name)
            done += len(chunk)
            processed += len(chunk)
            for paper in chunk:
                processed_ids.append(paper.id)
                _emit(progress_callback, {'event': 'done', 'paper_id': paper.id, 'title': paper.title, 'decision': paper.title_screening_decision})
        except Exception as exc:
            failed += len(chunk)
            processed += len(chunk)
            for paper in chunk:
                processed_ids.append(paper.id)
                paper.title_screening_status = 'failed'
                paper.title_screening_error = f'{exc.__class__.__name__}: {exc}'
                paper.title_screening_provider = 'deepseek'
                paper.title_screening_model = model_name
                paper.save(update_fields=[
                    'title_screening_status',
                    'title_screening_error',
                    'title_screening_provider',
                    'title_screening_model',
                ])
                _emit(progress_callback, {'event': 'failed', 'paper_id': paper.id, 'title': paper.title, 'error_code': exc.__class__.__name__, 'error_message': str(exc)})

    remaining = [p.id for p in papers if p.id not in set(processed_ids)]
    return {
        'targeted': len(papers),
        'processed': processed,
        'done': done,
        'failed': failed,
        'stopped': bool(stop_check and stop_check()),
        'remaining_paper_ids': remaining,
    }


def _eligible_papers(review, retry_failed_only=False):
    qs = review.papers.exclude(title='').order_by('id')
    if retry_failed_only:
        qs = qs.filter(title_screening_status='failed')
    else:
        qs = qs.filter(title_screening_decision=Paper.TitleScreeningDecision.NOT_PROCESSED)
    return list(qs)


def _screen_chunk(review, papers, model_name):
    rq_lines = '\n'.join(
        f'RQ{i + 1}: {rq.question_text}'
        for i, rq in enumerate(review.research_questions.order_by('id'))
    ) or 'No RQs available.'

    titles_block = '\n'.join(
        f'- paperid: {paper.id} | title: {paper.title}'
        for paper in papers
    )

    prompt = render_prompt_template(
        'phase_6_title_screening.md',
        context={
            'research_questions': rq_lines,
            'objectives': review.objectives or '',
            'pico_population': review.pico_population or '',
            'pico_intervention': review.pico_intervention or '',
            'pico_comparison': review.pico_comparison or '',
            'pico_outcomes': review.pico_outcomes or '',
            'titles_block': titles_block,
        },
        fallback=TITLE_SCREENING_PROMPT_FALLBACK,
    )

    raw_text = _call_deepseek(prompt=prompt, model_name=model_name)
    try:
        return _parse_payload(raw_text)
    except JSONDecodeError:
        correction = render_prompt_template(
            'phase_6_title_screening_json_correction.md',
            context={'raw_response': raw_text},
            fallback=JSON_CORRECTION_PROMPT_FALLBACK,
        )
        corrected = _call_deepseek(prompt=correction, model_name=model_name)
        return _parse_payload(corrected)


def _apply_chunk_payload(chunk, payload, model_name):
    by_id = {paper.id: paper for paper in chunk}

    for item in payload:
        paper_id = _safe_int(item.get('paperid'))
        if not paper_id or paper_id not in by_id:
            continue

        paper = by_id[paper_id]
        raw_decision = str(item.get('decision') or '').strip().lower()
        decision = _DECISION_MAP.get(raw_decision, Paper.TitleScreeningDecision.UNCERTAIN)
        reason = str(item.get('reason') or '').strip()

        confidence = 0.6
        if decision in {Paper.TitleScreeningDecision.INCLUDED, Paper.TitleScreeningDecision.EXCLUDED}:
            confidence = 0.9

        paper.title_screening_decision = decision
        paper.title_screening_reason = reason
        paper.title_screening_confidence = confidence
        paper.title_screening_status = 'screened'
        paper.title_screening_provider = 'deepseek'
        paper.title_screening_model = model_name
        paper.title_screening_error = ''
        paper.title_screening_screened_at = timezone.now()
        paper.save(update_fields=[
            'title_screening_decision',
            'title_screening_reason',
            'title_screening_confidence',
            'title_screening_status',
            'title_screening_provider',
            'title_screening_model',
            'title_screening_error',
            'title_screening_screened_at',
        ])

    processed_ids = {(_safe_int(item.get('paperid')) or 0) for item in payload}
    for paper in chunk:
        if paper.id in processed_ids:
            continue
        paper.title_screening_decision = Paper.TitleScreeningDecision.UNCERTAIN
        paper.title_screening_reason = 'No explicit decision returned by model; defaulted to uncertain.'
        paper.title_screening_confidence = 0.5
        paper.title_screening_status = 'screened'
        paper.title_screening_provider = 'deepseek'
        paper.title_screening_model = model_name
        paper.title_screening_error = ''
        paper.title_screening_screened_at = timezone.now()
        paper.save(update_fields=[
            'title_screening_decision',
            'title_screening_reason',
            'title_screening_confidence',
            'title_screening_status',
            'title_screening_provider',
            'title_screening_model',
            'title_screening_error',
            'title_screening_screened_at',
        ])


def _parse_payload(raw_text):
    text = (raw_text or '').strip()

    try:
        parsed = _extract_json(text)
        if isinstance(parsed, dict):
            parsed = [parsed]
        if isinstance(parsed, list):
            normalized = []
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                normalized.append({
                    'title': item.get('title') or item.get('Title') or '',
                    'paperid': item.get('paperid') or item.get('paper_id') or item.get('PaperID') or item.get('id'),
                    'decision': item.get('decision') or item.get('Decision') or '',
                    'reason': item.get('reason') or item.get('Reason') or '',
                })
            return normalized
    except Exception:
        pass

    pattern = re.compile(
        r"Title:\s*(?P<title>.*?)\n\s*paperid:\s*(?P<paperid>\d+)\s*\n\s*Decision:\s*(?P<decision>Include|Exclude|Uncertain)(?:\s*\n\s*Reason:\s*(?P<reason>.*?))?(?=\n\s*Title:|\Z)",
        flags=re.IGNORECASE | re.DOTALL,
    )
    results = []
    for m in pattern.finditer(text):
        results.append(
            {
                'title': (m.group('title') or '').strip(),
                'paperid': (m.group('paperid') or '').strip(),
                'decision': (m.group('decision') or '').strip(),
                'reason': (m.group('reason') or '').strip(),
            }
        )

    if not results:
        raise JSONDecodeError('Unable to parse title screening response', text, 0)

    return results


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
            {'role': 'system', 'content': 'Follow the required output format exactly.'},
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
        raise RuntimeError('DeepSeek returned empty title-screening content.')

    return text


def _extract_json(raw_text):
    text = (raw_text or '').strip()
    if text.startswith('```'):
        text = text.strip('`')
        text = text.replace('json\n', '', 1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, char in enumerate(text):
            if char not in '[{':
                continue
            try:
                parsed, _ = decoder.raw_decode(text[index:])
                return parsed
            except json.JSONDecodeError:
                continue
        raise


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _emit(callback, payload):
    if not callback:
        return
    try:
        callback(payload)
    except Exception:
        return
