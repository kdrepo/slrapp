import json
import logging
import math
import os

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from reviews.models import Paper, Review
from reviews.services.prompt_loader import render_prompt_template
from reviews.services.prompt_templates import SCREENING_JSON_CORRECTION_PROMPT, SCREENING_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def _trace(message):
    line = f'[ScreeningService] {message}'
    print(line)
    logger.info(line)


def _normalize_title_decisions(title_decisions):
    allowed = {
        Paper.TitleScreeningDecision.INCLUDED,
        Paper.TitleScreeningDecision.EXCLUDED,
        Paper.TitleScreeningDecision.UNCERTAIN,
        Paper.TitleScreeningDecision.MANUAL_TITLES,
        Paper.TitleScreeningDecision.NOT_PROCESSED,
    }
    if not title_decisions:
        return sorted(list(allowed))

    normalized = []
    for item in title_decisions:
        value = str(item or '').strip().lower()
        if value in allowed and value not in normalized:
            normalized.append(value)

    return normalized or sorted(list(allowed))


def prepare_screening_batch(review_id, max_papers=None, title_decisions=None):
    _trace(
        f'prepare_screening_batch start review_id={review_id} max_papers={max_papers} '
        f'title_decisions={title_decisions}'
    )
    review = Review.objects.get(pk=review_id)
    selected_title_decisions = _normalize_title_decisions(title_decisions)

    papers_qs = (
        review.papers.filter(Q(ta_decision=Paper.TADecision.NOT_PROCESSED) | Q(ta_decision__isnull=True))
        .filter(title_screening_decision__in=selected_title_decisions)
        .exclude(abstract__isnull=True)
        .exclude(abstract='')
        .order_by('id')
        .only('id')
    )
    if max_papers:
        papers_qs = papers_qs[:max_papers]

    paper_ids = list(papers_qs.values_list('id', flat=True))
    if not paper_ids:
        _trace(f'prepare_screening_batch no eligible papers review_id={review_id}')
        return {
            'jsonl_path': '',
            'request_count': 0,
            'paper_ids': [],
            'title_screening_decisions': selected_title_decisions,
        }

    result = {
        'jsonl_path': '',
        'request_count': len(paper_ids),
        'paper_ids': paper_ids,
        'title_screening_decisions': selected_title_decisions,
    }
    _trace(f'prepare_screening_batch done review_id={review_id} count={result["request_count"]}')
    return result


def submit_screening_batch(review_id, max_papers=None, stage_key='phase_7', title_decisions=None):
    _trace(
        f'submit_screening_batch start review_id={review_id} stage_key={stage_key} max_papers={max_papers} '
        f'title_decisions={title_decisions}'
    )
    prepared = prepare_screening_batch(
        review_id,
        max_papers=max_papers,
        title_decisions=title_decisions,
    )
    review = Review.objects.get(pk=review_id)

    if prepared['request_count'] == 0:
        _set_phase_status(review, phase_status='no_eligible_papers', stage_key=stage_key)
        _trace(f'submit_screening_batch no eligible papers review_id={review_id} stage_key={stage_key}')
        return {'submitted': False, 'reason': 'no_eligible_papers'}

    model_name = (
        getattr(settings, 'DEEPSEEK_ABSTRACT_SCREENING_MODEL', '')
        or os.getenv('DEEPSEEK_ABSTRACT_SCREENING_MODEL', '')
        or 'deepseek-chat'
    )

    stage_progress = review.stage_progress or {}
    batch_size = max(1, int(getattr(settings, 'SCREENING_POLL_CHUNK_SIZE', 25)))
    total_batches = math.ceil(prepared['request_count'] / batch_size)

    stage_progress[stage_key] = {
        'status': 'queued_standard_api',
        'mode': 'standard_api',
        'submitted_at': timezone.now().isoformat(),
        'request_count': prepared['request_count'],
        'paper_ids': prepared['paper_ids'],
        'remaining_paper_ids': prepared['paper_ids'],
        'processed_paper_ids': [],
        'batch_size': batch_size,
        'total_batches': total_batches,
        'current_batch_number': 1,
        'model': model_name,
        'provider': 'deepseek',
        'title_screening_decisions': prepared['title_screening_decisions'],
    }

    phase_8_key = _phase_8_key_for(stage_key)
    stage_progress[phase_8_key] = {
        'status': 'polling_pending',
        'last_polled_at': None,
        'next_poll_hint': 'Run poll every 1 minute.',
        'updated_papers': 0,
        'conflicts': 0,
        'errors': 0,
    }
    review.stage_progress = stage_progress
    review.save(update_fields=['stage_progress'])

    result = {
        'submitted': True,
        'batch_job_id': None,
        'request_count': prepared['request_count'],
        'paper_ids': prepared['paper_ids'],
        'mode': 'standard_api',
        'provider': 'deepseek',
        'title_screening_decisions': prepared['title_screening_decisions'],
    }
    _trace(f'submit_screening_batch done review_id={review_id} stage_key={stage_key} count={prepared["request_count"]}')
    return result


def poll_screening_batch(review_id, stage_key='phase_7'):
    _trace(f'poll_screening_batch start review_id={review_id} stage_key={stage_key}')
    review = Review.objects.get(pk=review_id)
    stage_progress = review.stage_progress or {}
    phase_7 = stage_progress.get(stage_key, {})

    remaining_ids = list(phase_7.get('remaining_paper_ids') or [])
    model_name = phase_7.get('model') or (
        getattr(settings, 'DEEPSEEK_ABSTRACT_SCREENING_MODEL', '')
        or os.getenv('DEEPSEEK_ABSTRACT_SCREENING_MODEL', '')
        or 'deepseek-chat'
    )

    if not remaining_ids:
        _trace(f'poll_screening_batch nothing remaining review_id={review_id} stage_key={stage_key}')
        phase_8_key = _phase_8_key_for(stage_key)
        phase_8 = stage_progress.get(phase_8_key, {})
        phase_8['status'] = 'completed'
        phase_8['last_polled_at'] = timezone.now().isoformat()
        phase_8['completed_at'] = phase_8.get('completed_at') or timezone.now().isoformat()
        stage_progress[phase_8_key] = phase_8
        review.stage_progress = stage_progress
        review.save(update_fields=['stage_progress'])
        return {'state': 'succeeded', 'updated': 0, 'conflicts': 0, 'remaining': 0}

    chunk_size = max(1, int(getattr(settings, 'SCREENING_POLL_CHUNK_SIZE', 25)))
    processed_before = len(phase_7.get('processed_paper_ids') or [])
    current_batch_number = (processed_before // chunk_size) + 1
    total_batches = int(phase_7.get('total_batches') or math.ceil((len(remaining_ids) + processed_before) / chunk_size))

    target_ids = remaining_ids[:chunk_size]

    papers = list(
        review.papers.filter(id__in=target_ids)
        .only('id', 'title', 'abstract')
    )
    paper_by_id = {paper.id: paper for paper in papers}

    context_block = _build_context_block(review)
    responses = []
    for paper_id in target_ids:
        paper = paper_by_id.get(paper_id)
        if not paper:
            responses.append({'paper_id': str(paper_id), 'text': '{"decision":"excluded","confidence":0.0,"reason":"Paper not found during screening poll","criterion_failed":"system_error"}'})
            continue

        user_prompt = (
            f'{context_block}\n\n'
            f'Paper Title: {paper.title}\n'
            f'Paper Abstract: {paper.abstract}'
        )
        raw_text = _call_screening_model(user_prompt=user_prompt, model_name=model_name)
        responses.append({'paper_id': str(paper.id), 'text': raw_text})

    ingest_summary = _ingest_batch_responses(review=review, responses=responses)

    processed_ids = list(phase_7.get('processed_paper_ids') or []) + target_ids
    remaining_ids = remaining_ids[len(target_ids):]

    phase_7['processed_paper_ids'] = processed_ids
    phase_7['remaining_paper_ids'] = remaining_ids
    phase_7['last_polled_at'] = timezone.now().isoformat()
    phase_7['status'] = 'running_standard_api' if remaining_ids else 'completed_standard_api'
    phase_7['batch_size'] = chunk_size
    phase_7['total_batches'] = total_batches
    phase_7['current_batch_number'] = current_batch_number + (1 if remaining_ids else 0)
    phase_7['last_completed_batch_number'] = current_batch_number
    phase_7['provider'] = phase_7.get('provider') or 'deepseek'
    stage_progress[stage_key] = phase_7

    phase_8_key = _phase_8_key_for(stage_key)
    phase_8 = stage_progress.get(phase_8_key, {})
    phase_8['status'] = 'running' if remaining_ids else 'completed'
    phase_8['last_polled_at'] = timezone.now().isoformat()
    phase_8['updated_papers'] = int(phase_8.get('updated_papers', 0)) + int(ingest_summary.get('updated', 0))
    phase_8['conflicts'] = int(phase_8.get('conflicts', 0)) + int(ingest_summary.get('conflicts', 0))
    phase_8['errors'] = int(phase_8.get('errors', 0)) + int(ingest_summary.get('errors', 0))
    if not remaining_ids:
        phase_8['completed_at'] = timezone.now().isoformat()
    stage_progress[phase_8_key] = phase_8

    review.stage_progress = stage_progress
    review.save(update_fields=['stage_progress'])

    state = 'running' if remaining_ids else 'succeeded'
    _trace(
        f'poll_screening_batch {state} review_id={review_id} stage_key={stage_key} '
        f'batch={current_batch_number}/{total_batches} sent={len(target_ids)} '
        f'updated={ingest_summary.get("updated", 0)} remaining={len(remaining_ids)}'
    )
    return {'state': state, **ingest_summary, 'remaining': len(remaining_ids)}


def poll_active_screening_batches():
    _trace('poll_active_screening_batches start')
    summaries = []
    stage_keys = ['phase_7', 'phase_7_debug']

    for review in Review.objects.all().only('id', 'stage_progress'):
        progress = review.stage_progress or {}

        for stage_key in stage_keys:
            phase = progress.get(stage_key, {})
            if not phase:
                continue

            remaining_ids = phase.get('remaining_paper_ids', [])
            phase_8_key = _phase_8_key_for(stage_key)
            phase_8 = progress.get(phase_8_key, {})
            if phase_8.get('status') == 'completed' and not remaining_ids:
                continue

            try:
                result = poll_screening_batch(review.id, stage_key=stage_key)
                summaries.append({'review_id': review.id, 'stage_key': stage_key, **result})
            except Exception as exc:
                summaries.append({'review_id': review.id, 'stage_key': stage_key, 'state': 'error', 'error': str(exc)})

    _trace(f'poll_active_screening_batches done count={len(summaries)}')
    return summaries


def get_screening_snapshot(review_id, stage_key='phase_7'):
    _trace(f'get_screening_snapshot review_id={review_id} stage_key={stage_key}')
    review = Review.objects.get(pk=review_id)
    stage_progress = review.stage_progress or {}
    phase_data = stage_progress.get(stage_key, {})
    phase_8_key = _phase_8_key_for(stage_key)
    phase8_data = stage_progress.get(phase_8_key, {})
    target_ids = phase_data.get('paper_ids') or []

    papers = list(
        review.papers.filter(id__in=target_ids)
        .order_by('id')
        .values('id', 'title', 'ta_decision', 'ta_confidence', 'ta_reason', 'screening_conflict')
    )

    decided_count = sum(1 for item in papers if item['ta_decision'])
    return {
        'stage': phase_data,
        'polling': phase8_data,
        'papers': papers,
        'total': len(papers),
        'decided': decided_count,
        'pending': max(len(papers) - decided_count, 0),
    }


def _ingest_batch_responses(review, responses):
    _trace(f'_ingest_batch_responses start review_id={review.id} response_count={len(responses)}')
    confidence_threshold = float(getattr(settings, 'SCREENING_CONFLICT_THRESHOLD', 0.72))
    updated = 0
    conflicts = 0
    errors = 0

    with transaction.atomic():
        for item in responses:
            paper_id = _safe_int(item.get('paper_id'))
            if not paper_id:
                errors += 1
                continue

            paper = Paper.objects.filter(review=review, id=paper_id).first()
            if not paper:
                errors += 1
                continue

            raw_text = item.get('text', '')
            try:
                payload = _parse_json_with_correction(raw_text)
            except Exception:
                paper.ta_decision = Paper.TADecision.FLAGGED
                paper.ta_reason = 'Malformed screening response from model.'
                paper.screening_conflict = True
                paper.ta_confidence = 0.0
                paper.save(update_fields=['ta_decision', 'ta_reason', 'screening_conflict', 'ta_confidence'])
                updated += 1
                conflicts += 1
                continue

            decision = str(payload.get('decision', '')).strip().lower()
            if decision not in {Paper.TADecision.INCLUDED, Paper.TADecision.EXCLUDED}:
                decision = Paper.TADecision.EXCLUDED

            confidence = _safe_float(payload.get('confidence'), default=0.0)
            reason = str(payload.get('reason', '')).strip()
            criterion_failed = payload.get('criterion_failed')

            if criterion_failed not in (None, '', 'null'):
                reason = f'{reason} | Criterion failed: {criterion_failed}' if reason else f'Criterion failed: {criterion_failed}'

            conflict = confidence < confidence_threshold

            paper.ta_decision = decision
            paper.ta_confidence = confidence
            paper.ta_reason = reason
            paper.screening_conflict = conflict
            paper.save(
                update_fields=['ta_decision', 'ta_confidence', 'ta_reason', 'screening_conflict']
            )
            updated += 1
            if conflict:
                conflicts += 1

    _trace(f'_ingest_batch_responses done review_id={review.id} updated={updated} conflicts={conflicts} errors={errors}')
    return {'updated': updated, 'conflicts': conflicts, 'errors': errors}


def _parse_json_with_correction(raw_text):
    try:
        return _extract_json(raw_text)
    except json.JSONDecodeError:
        model_name = (
            getattr(settings, 'DEEPSEEK_ABSTRACT_SCREENING_MODEL', '')
            or os.getenv('DEEPSEEK_ABSTRACT_SCREENING_MODEL', '')
            or 'deepseek-chat'
        )
        corrected = _call_single(
            prompt=_screening_json_correction_prompt(raw_text),
            model_name=model_name,
        )
        return _extract_json(corrected)


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


def _build_context_block(review):
    rq_lines = '\n'.join(
        f'- {rq.question_text}' for rq in review.research_questions.order_by('id')
    ) or '- No locked research questions found.'

    return (
        f'Review Objectives:\n{review.objectives or ""}\n\n'
        f'Locked Research Questions:\n{rq_lines}\n\n'
        f'Inclusion Criteria:\n{review.inclusion_criteria or ""}\n\n'
        f'Exclusion Criteria:\n{review.exclusion_criteria or ""}'
    )


def _set_phase_status(review, phase_status, stage_key='phase_7'):
    stage_progress = review.stage_progress or {}
    stage_progress[stage_key] = {'status': phase_status}
    review.stage_progress = stage_progress
    review.save(update_fields=['stage_progress'])


def _phase_8_key_for(stage_key):
    if stage_key == 'phase_7':
        return 'phase_8'
    return f'{stage_key}_phase_8'


def _call_screening_model(user_prompt, model_name):
    return _call_deepseek(
        system_prompt=_screening_system_prompt(),
        user_prompt=user_prompt,
        model_name=model_name,
    )


def _call_single(prompt, model_name):
    return _call_deepseek(
        system_prompt='Return only valid JSON.',
        user_prompt=prompt,
        model_name=model_name,
    )


def _call_deepseek(system_prompt, user_prompt, model_name):
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
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
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
        raise RuntimeError('DeepSeek returned empty abstract-screening content.')

    return text


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None



def _screening_system_prompt():
    return render_prompt_template(
        'phase_7_ta_screening.md',
        fallback=SCREENING_SYSTEM_PROMPT,
    )


def _screening_json_correction_prompt(raw_response):
    return render_prompt_template(
        'phase_7_json_correction.md',
        context={'raw_response': raw_response},
        fallback=SCREENING_JSON_CORRECTION_PROMPT,
    )
