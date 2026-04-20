import json
import os
from json import JSONDecodeError

import requests
from django.conf import settings
from django.utils import timezone

from reviews.models import Paper, Review
from reviews.services.prompt_loader import render_prompt_template
from reviews.services.scaffold_service import get_scaffold_data, set_scaffold_data


def run_theory_landscape_for_review(review_id):
    review = Review.objects.get(pk=review_id)
    corpus = _build_theory_corpus(review)
    if not corpus:
        raise RuntimeError('No included papers with theoretical framework extraction found.')

    rq_list = _rq_list(review)
    prompt = render_prompt_template(
        'phase_17a_theory_landscape.md',
        context={
            'objectives': review.objectives or '',
            'rq_list': rq_list,
            'total_papers': len(corpus),
            'all_theoretical_frameworks_json': json.dumps(corpus, ensure_ascii=False, indent=2),
        },
    )
    if not prompt.strip():
        raise RuntimeError('Prompt file phase_17a_theory_landscape.md is missing or empty.')

    raw = _call_deepseek(prompt=prompt, model_setting='DEEPSEEK_THEORY_MODEL')
    payload = _parse_with_correction(raw, correction_template='phase_17a_json_correction.md')
    if not isinstance(payload, dict):
        raise RuntimeError('Theory landscape output must be a JSON object.')

    scaffold_data = get_scaffold_data(review)
    theoretical_framework = _build_theoretical_framework_block(
        payload=payload,
        corpus_count=len(corpus),
    )
    scaffold_data['theoretical_framework'] = theoretical_framework
    scaffold_data['theory_landscape'] = payload
    consistency = _build_theory_consistency_check(theory_landscape_payload=payload, scaffold_data=scaffold_data)
    checks = scaffold_data.get('consistency_checks', {}) if isinstance(scaffold_data.get('consistency_checks', {}), dict) else {}
    checks['theory_landscape_vs_tccm'] = consistency
    scaffold_data['consistency_checks'] = checks
    set_scaffold_data(review, scaffold_data)

    review.status = Review.Status.PAPER_CONFIRMATION
    review.save(update_fields=['scaffold_data', 'status'])

    dominant_theory = ''
    theory_frequency = payload.get('theory_frequency') if isinstance(payload.get('theory_frequency'), list) else []
    if theory_frequency:
        first = theory_frequency[0] if isinstance(theory_frequency[0], dict) else {}
        dominant_theory = str(first.get('theory_name') or '').strip()

    return {
        'total_papers': len(corpus),
        'dominant_theory': dominant_theory,
        'requires_researcher_confirmation': True,
        'stored_keys': ['theoretical_framework', 'theory_landscape'],
        'consistency': consistency,
    }


def run_cross_theme_theoretical_synthesis_for_review(review_id):
    review = Review.objects.get(pk=review_id)
    themes = list(review.theme_syntheses.all().order_by('order_index', 'id'))
    if not themes:
        raise RuntimeError('No theme syntheses found. Run Phase 17 and Phase 18 first.')

    scaffold_data = get_scaffold_data(review)
    theory_landscape = scaffold_data.get('theory_landscape', {}) if isinstance(scaffold_data.get('theory_landscape'), dict) else {}
    theoretical_framework = scaffold_data.get('theoretical_framework', {}) if isinstance(scaffold_data.get('theoretical_framework'), dict) else {}

    primary_lens = str(
        theoretical_framework.get('primary_lens')
        or theoretical_framework.get('recommended')
        or 'Not specified'
    ).strip()
    if not primary_lens or primary_lens.lower() == 'not specified':
        raise RuntimeError('Primary theoretical lens is not confirmed yet. Confirm lens in Part 1 before cross-theme synthesis.')
    supporting_lenses = theoretical_framework.get('supporting_lenses', [])
    if not isinstance(supporting_lenses, list):
        supporting_lenses = []

    rq_list = _rq_list(review)
    theoretical_gaps = theory_landscape.get('theoretical_gaps', [])
    if not isinstance(theoretical_gaps, list):
        theoretical_gaps = []

    all_reconciled = []
    for t in themes:
        all_reconciled.append(
            {
                'theme_name': t.theme_name_locked,
                'evidence_grade': t.evidence_grade,
                'paper_count': t.paper_count,
                'reconciled_text': (t.reconciled_text or t.reconciler_notes or '').strip(),
            }
        )

    prompt = render_prompt_template(
        'phase_17b_cross_theme_theoretical_synthesis.md',
        context={
            'primary_theoretical_lens': primary_lens,
            'supporting_lenses': ', '.join(str(x) for x in supporting_lenses) if supporting_lenses else 'None',
            'objectives': review.objectives or '',
            'rq_list': rq_list,
            'theoretical_landscape_summary': theory_landscape.get('theoretical_landscape_summary', ''),
            'theoretical_gaps_formatted': json.dumps(theoretical_gaps, ensure_ascii=False, indent=2),
            'theme_count': len(all_reconciled),
            'all_reconciled_texts_with_theme_names': json.dumps(all_reconciled, ensure_ascii=False, indent=2),
        },
    )
    if not prompt.strip():
        raise RuntimeError('Prompt file phase_17b_cross_theme_theoretical_synthesis.md is missing or empty.')

    raw = _call_deepseek(prompt=prompt, model_setting='DEEPSEEK_THEORY_MODEL')
    payload = _parse_with_correction(raw, correction_template='phase_17b_json_correction.md')
    if not isinstance(payload, dict):
        raise RuntimeError('Cross-theme theoretical synthesis output must be a JSON object.')

    scaffold_data['theoretical_synthesis'] = payload
    set_scaffold_data(review, scaffold_data)
    review.save(update_fields=['scaffold_data'])

    propositions = payload.get('propositions') if isinstance(payload.get('propositions'), list) else []

    return {
        'theme_count': len(all_reconciled),
        'proposition_count': len(propositions),
        'stored_keys': ['theoretical_synthesis'],
    }


def _build_theory_corpus(review):
    papers = (
        review.papers.filter(full_text_decision=Paper.FullTextDecision.INCLUDED)
        .exclude(full_text_extraction={})
        .order_by('id')
    )
    rows = []
    for paper in papers:
        extraction = paper.full_text_extraction if isinstance(paper.full_text_extraction, dict) else {}
        frameworks = extraction.get('theoretical_frameworks')
        normalized_frameworks = _normalize_frameworks(frameworks, extraction)
        if not normalized_frameworks:
            continue

        rows.append(
            {
                'paper_id': paper.id,
                'scopus_id': paper.scopus_id or '',
                'short_ref': _short_ref(paper, extraction),
                'year': paper.publication_year,
                'study_design': extraction.get('study_design_canonical') or extraction.get('study_design') or '',
                'theoretical_frameworks': normalized_frameworks,
            }
        )
    return rows


def _normalize_frameworks(frameworks, extraction):
    out = []
    if isinstance(frameworks, list):
        for item in frameworks:
            if not isinstance(item, dict):
                continue
            theory_name = str(item.get('theory_name') or '').strip()
            if not theory_name:
                continue
            usage_type = str(item.get('usage_type') or 'secondary').strip().lower()
            if usage_type not in {'primary', 'secondary', 'implicit'}:
                usage_type = 'secondary'
            out.append(
                {
                    'theory_name': theory_name,
                    'usage_type': usage_type,
                    'how_used': str(item.get('how_used') or '').strip(),
                }
            )

    if out:
        return out

    legacy = str(extraction.get('theory_framework') or '').strip()
    if legacy:
        return [{'theory_name': legacy, 'usage_type': 'secondary', 'how_used': ''}]
    return []


def _short_ref(paper, extraction):
    ay = str(extraction.get('author_year') or '').strip()
    if ay:
        return ay
    authors = (paper.authors or '').strip()
    if authors:
        first = authors.split(';')[0].strip()
        surname = first.split(',')[0].strip() or first.split(' ')[-1].strip()
    else:
        surname = 'Unknown'
    year = paper.publication_year or 'n.d.'
    return f'{surname} ({year})'


def _rq_list(review):
    items = [x.question_text.strip() for x in review.research_questions.order_by('id') if (x.question_text or '').strip()]
    if not items:
        return 'No research questions available.'
    return '\n'.join(f'RQ{i + 1}: {text}' for i, text in enumerate(items))


def _build_theoretical_framework_block(payload, corpus_count):
    theory_frequency = payload.get('theory_frequency') if isinstance(payload.get('theory_frequency'), list) else []
    assessment = payload.get('primary_lens_assessment') if isinstance(payload.get('primary_lens_assessment'), dict) else {}
    gaps = payload.get('theoretical_gaps') if isinstance(payload.get('theoretical_gaps'), list) else []
    alternatives = assessment.get('alternative_lenses') if isinstance(assessment.get('alternative_lenses'), list) else []
    dominant = ''
    if theory_frequency:
        first = theory_frequency[0] if isinstance(theory_frequency[0], dict) else {}
        dominant = str(first.get('theory_name') or '').strip()

    top_supporting = []
    for row in theory_frequency:
        if not isinstance(row, dict):
            continue
        name = str(row.get('theory_name') or '').strip()
        if not name or name == dominant:
            continue
        top_supporting.append((name, int(row.get('total_count') or 0)))
    top_supporting = [name for name, _ in sorted(top_supporting, key=lambda x: x[1], reverse=True)[:2]]

    recommended_lens = str(assessment.get('recommended_lens') or dominant or '').strip()
    coverage_pct = 0.0
    if recommended_lens:
        for row in theory_frequency:
            if not isinstance(row, dict):
                continue
            if str(row.get('theory_name') or '').strip().lower() == recommended_lens.lower():
                try:
                    coverage_pct = float(row.get('pct_of_corpus') or 0.0)
                except (TypeError, ValueError):
                    coverage_pct = 0.0
                break
    if not coverage_pct:
        try:
            coverage_pct = float(
                (
                    assessment.get('recommended_lens_coverage', {})
                    if isinstance(assessment.get('recommended_lens_coverage', {}), dict)
                    else {}
                ).get('pct_of_corpus')
                or 0.0
            )
        except (TypeError, ValueError):
            coverage_pct = 0.0

    return {
        'primary_lens': None,
        'recommended': recommended_lens or dominant or '',
        'status': 'awaiting_confirmation',
        'alternatives': alternatives,
        'supporting_lenses': top_supporting,
        'dominant_theory': dominant or 'Not identified',
        'theory_coverage': f'{round(coverage_pct, 1)}% of corpus' if corpus_count else '0% of corpus',
        'theoretical_gaps': [str(x.get('theory_name') or '').strip() for x in gaps if isinstance(x, dict) and str(x.get('theory_name') or '').strip()],
        'landscape_summary': str(payload.get('theoretical_landscape_summary') or '').strip(),
    }


def _build_theory_consistency_check(theory_landscape_payload, scaffold_data):
    theory_frequency = (
        theory_landscape_payload.get('theory_frequency')
        if isinstance(theory_landscape_payload.get('theory_frequency'), list)
        else []
    )
    top_landscape = [
        str(row.get('theory_name') or '').strip()
        for row in theory_frequency
        if isinstance(row, dict) and str(row.get('theory_name') or '').strip()
    ][:5]

    assessment = (
        theory_landscape_payload.get('primary_lens_assessment')
        if isinstance(theory_landscape_payload.get('primary_lens_assessment'), dict)
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
        'message': 'TCCM theory summary not available yet.',
        'checked_at': timezone.now().isoformat(),
    }

    if not tccm_candidates:
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


def _parse_with_correction(raw_response, correction_template):
    try:
        return _extract_json(raw_response)
    except (JSONDecodeError, ValueError):
        correction_prompt = render_prompt_template(
            correction_template,
            context={'raw_response': raw_response},
        )
        if not correction_prompt.strip():
            raise RuntimeError(f'Prompt file {correction_template} is missing or empty.')
        corrected = _call_deepseek(prompt=correction_prompt, model_setting='DEEPSEEK_THEORY_MODEL')
        return _extract_json(corrected)


def _call_deepseek(prompt, model_setting='DEEPSEEK_THEORY_MODEL'):
    api_key = getattr(settings, 'DEEPSEEK_API_KEY', '') or os.getenv('DEEPSEEK_API_KEY', '')
    if not api_key:
        raise RuntimeError('DEEPSEEK_API_KEY is not configured.')

    base_url = (
        getattr(settings, 'DEEPSEEK_BASE_URL', '')
        or os.getenv('DEEPSEEK_BASE_URL', '')
        or 'https://api.deepseek.com'
    ).rstrip('/')
    model_name = getattr(settings, model_setting, '') or os.getenv(model_setting, '') or 'deepseek-reasoner'
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
        for index, char in enumerate(text):
            if char not in '[{':
                continue
            try:
                parsed, _ = decoder.raw_decode(text[index:])
                return parsed
            except JSONDecodeError:
                continue
        raise
