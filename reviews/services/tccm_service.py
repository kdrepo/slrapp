import json
import os
from json import JSONDecodeError

import requests
from django.conf import settings

from reviews.models import Paper, Review
from reviews.services.prompt_loader import render_prompt_template
from reviews.services.scaffold_service import get_scaffold_data, set_scaffold_data


def run_tccm_aggregation_for_review(review_id):
    review = Review.objects.get(pk=review_id)
    corpus = _build_tccm_corpus(review)
    if not corpus:
        raise RuntimeError('No included papers with extraction data found for TCCM aggregation.')

    rq_list = _rq_list(review)
    prompt = render_prompt_template(
        'phase_20_tccm_aggregation.md',
        context={
            'primary_topic': review.title or '',
            'objectives': review.objectives or '',
            'rq_list': rq_list,
            'total_papers': len(corpus),
            'date_range': _date_range_text(review),
            'all_tccm_json': json.dumps(corpus, ensure_ascii=False, indent=2),
        },
    )
    if not prompt.strip():
        raise RuntimeError('Prompt file phase_20_tccm_aggregation.md is missing or empty.')

    raw = _call_deepseek(prompt=prompt)
    payload = _parse_with_correction(raw_response=raw)
    if not isinstance(payload, dict):
        raise RuntimeError('TCCM aggregation output must be a JSON object.')

    scaffold_data = get_scaffold_data(review)
    scaffold_data['tccm_summary'] = payload
    consistency = _build_theory_consistency_check(scaffold_data=scaffold_data)
    checks = scaffold_data.get('consistency_checks', {}) if isinstance(scaffold_data.get('consistency_checks', {}), dict) else {}
    checks['theory_landscape_vs_tccm'] = consistency
    scaffold_data['consistency_checks'] = checks
    set_scaffold_data(review, scaffold_data)
    review.save(update_fields=['scaffold_data'])

    return {
        'total_papers': len(corpus),
        'stored_key': 'tccm_summary',
        'has_future_research': bool(isinstance(payload.get('future_research_from_tccm'), list)),
        'consistency': consistency,
    }


def _build_tccm_corpus(review):
    papers = (
        review.papers.filter(full_text_decision=Paper.FullTextDecision.INCLUDED)
        .exclude(full_text_extraction={})
        .order_by('id')
    )
    rows = []
    for paper in papers:
        extraction = paper.full_text_extraction if isinstance(paper.full_text_extraction, dict) else {}
        quality = paper.full_text_quality if isinstance(paper.full_text_quality, dict) else {}
        tccm = paper.full_text_tccm if isinstance(getattr(paper, 'full_text_tccm', {}), dict) else {}
        if not extraction:
            continue

        tccm_theories = tccm.get('theories') if isinstance(tccm.get('theories'), list) else []
        tccm_characteristics = tccm.get('characteristics') if isinstance(tccm.get('characteristics'), dict) else {}
        tccm_context = tccm.get('context') if isinstance(tccm.get('context'), dict) else {}
        tccm_methods = tccm.get('methods') if isinstance(tccm.get('methods'), dict) else {}

        rows.append(
            {
                'paper_id': paper.id,
                'scopus_id': paper.scopus_id or '',
                'short_ref': _short_ref(paper=paper, extraction=extraction),
                'year': paper.publication_year,
                'study_design': str(
                    extraction.get('study_design_canonical')
                    or extraction.get('study_design')
                    or ''
                ).strip(),
                'country': str(extraction.get('country') or '').strip(),
                'population': str(extraction.get('population') or '').strip(),
                'context': str(extraction.get('context') or '').strip(),
                'methodology': str(extraction.get('methodology') or '').strip(),
                'data_type': str(extraction.get('data_type') or '').strip(),
                'theoretical_frameworks': tccm_theories or _normalize_theories(extraction),
                'tccm_characteristics': tccm_characteristics,
                'tccm_context': tccm_context,
                'tccm_methods': tccm_methods,
                'tccm': {
                    'theories': tccm_theories or _normalize_theories(extraction),
                    'characteristics': tccm_characteristics,
                    'context': tccm_context,
                    'methods': tccm_methods,
                },
                'quality': {
                    'total_score': quality.get('total_score'),
                    'risk_of_bias': quality.get('risk_of_bias'),
                    'dim_objectives': quality.get('dim_objectives'),
                    'dim_design': quality.get('dim_design'),
                    'dim_data': quality.get('dim_data'),
                    'dim_analysis': quality.get('dim_analysis'),
                    'dim_bias': quality.get('dim_bias'),
                },
            }
        )
    return rows


def _date_range_text(review):
    years = list(
        review.papers.filter(full_text_decision=Paper.FullTextDecision.INCLUDED)
        .exclude(publication_year__isnull=True)
        .values_list('publication_year', flat=True)
    )
    if not years:
        return 'Not available'
    return f'{min(years)}-{max(years)}'


def _normalize_theories(extraction):
    items = extraction.get('theoretical_frameworks')
    normalized = []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get('theory_name') or '').strip()
            if not name:
                continue
            usage = str(item.get('usage_type') or 'secondary').strip().lower()
            if usage not in {'primary', 'secondary', 'implicit'}:
                usage = 'secondary'
            normalized.append(
                {
                    'theory_name': name,
                    'usage_type': usage,
                    'how_used': str(item.get('how_used') or '').strip(),
                }
            )
    if normalized:
        return normalized

    legacy = str(extraction.get('theory_framework') or '').strip()
    if legacy:
        return [{'theory_name': legacy, 'usage_type': 'secondary', 'how_used': ''}]
    return []


def _short_ref(paper, extraction):
    author_year = str(extraction.get('author_year') or '').strip()
    if author_year:
        return author_year
    authors = (paper.authors or '').strip()
    if authors:
        first = authors.split(';')[0].strip()
        surname = first.split(',')[0].strip() or first.split(' ')[-1].strip()
    else:
        surname = 'Unknown'
    year = paper.publication_year or 'n.d.'
    return f'{surname} ({year})'


def _rq_list(review):
    questions = [q.question_text.strip() for q in review.research_questions.order_by('id') if (q.question_text or '').strip()]
    if not questions:
        return 'No research questions available.'
    return '\n'.join(f'RQ{i + 1}: {text}' for i, text in enumerate(questions))


def _parse_with_correction(raw_response):
    try:
        return _extract_json(raw_response)
    except (JSONDecodeError, ValueError):
        correction_prompt = render_prompt_template(
            'phase_20_tccm_json_correction.md',
            context={'raw_response': raw_response},
            fallback=(
                'Your previous response was not valid JSON. Return ONLY the valid JSON object from your prior response. '
                'No markdown fences.\n\n'
                'Previous response:\n{raw_response}'
            ),
        )
        corrected = _call_deepseek(prompt=correction_prompt)
        return _extract_json(corrected)


def _call_deepseek(prompt):
    api_key = getattr(settings, 'DEEPSEEK_API_KEY', '') or os.getenv('DEEPSEEK_API_KEY', '')
    if not api_key:
        raise RuntimeError('DEEPSEEK_API_KEY is not configured.')

    base_url = (
        getattr(settings, 'DEEPSEEK_BASE_URL', '')
        or os.getenv('DEEPSEEK_BASE_URL', '')
        or 'https://api.deepseek.com'
    ).rstrip('/')
    model_name = (
        getattr(settings, 'DEEPSEEK_TCCM_MODEL', '')
        or os.getenv('DEEPSEEK_TCCM_MODEL', '')
        or 'deepseek-reasoner'
    )
    timeout_seconds = float(getattr(settings, 'DEEPSEEK_TIMEOUT_SECONDS', 120))

    response = requests.post(
        f'{base_url}/chat/completions',
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        },
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
        for index, char in enumerate(text):
            if char not in '[{':
                continue
            try:
                parsed, _ = decoder.raw_decode(text[index:])
                return parsed
            except JSONDecodeError:
                continue
        raise


def _build_theory_consistency_check(scaffold_data):
    theory_landscape = scaffold_data.get('theory_landscape', {}) if isinstance(scaffold_data.get('theory_landscape', {}), dict) else {}
    theory_frequency = (
        theory_landscape.get('theory_frequency')
        if isinstance(theory_landscape.get('theory_frequency'), list)
        else []
    )
    top_landscape = [
        str(row.get('theory_name') or '').strip()
        for row in theory_frequency
        if isinstance(row, dict) and str(row.get('theory_name') or '').strip()
    ][:5]

    assessment = (
        theory_landscape.get('primary_lens_assessment')
        if isinstance(theory_landscape.get('primary_lens_assessment'), dict)
        else {}
    )
    recommended_lens = str(assessment.get('recommended_lens') or '').strip()

    tccm_summary = scaffold_data.get('tccm_summary', {}) if isinstance(scaffold_data.get('tccm_summary', {}), dict) else {}
    theory_dimension = tccm_summary.get('theory_dimension', {}) if isinstance(tccm_summary.get('theory_dimension', {}), dict) else {}
    tccm_candidates = _extract_tccm_top_theories(theory_dimension)

    check = {
        'status': 'not_available',
        'recommended_lens_17a': recommended_lens,
        'top_theories_17a': top_landscape,
        'top_theories_tccm': tccm_candidates[:5],
        'overlap_top5': [],
        'message': 'Theory landscape (17A) not available yet.',
    }
    if not top_landscape:
        return check

    norm_tccm = {x.casefold(): x for x in tccm_candidates if x}
    norm_landscape = {x.casefold(): x for x in top_landscape if x}
    overlap = [norm_landscape[k] for k in norm_landscape if k in norm_tccm]
    check['overlap_top5'] = overlap

    if recommended_lens and recommended_lens.casefold() in norm_tccm:
        check['status'] = 'aligned'
        check['message'] = '17A recommended lens aligns with TCCM dominant/top theory signals.'
    else:
        check['status'] = 'warning_mismatch'
        check['message'] = (
            '17A recommended lens differs from TCCM top theory signals. '
            'Use 17A as authoritative for synthesis; keep TCCM descriptive.'
        )
    return check


def _extract_tccm_top_theories(theory_dimension):
    out = []
    dominant = str(theory_dimension.get('dominant_theory') or '').strip()
    if dominant:
        out.append(dominant)

    dominant_list = theory_dimension.get('dominant_theories')
    if isinstance(dominant_list, list):
        for item in dominant_list:
            if isinstance(item, dict):
                name = str(item.get('theory_name') or '').strip()
            else:
                name = str(item or '').strip()
            if name:
                out.append(name)

    for key in ['theories_used', 'theories_present']:
        bucket = theory_dimension.get(key)
        if isinstance(bucket, dict):
            ranked = sorted(
                (
                    (str(name).strip(), _safe_int(count))
                    for name, count in bucket.items()
                    if str(name).strip()
                ),
                key=lambda x: x[1],
                reverse=True,
            )
            out.extend([name for name, _ in ranked[:5]])

    uniq = []
    seen = set()
    for name in out:
        k = name.casefold()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(name)
    return uniq


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
