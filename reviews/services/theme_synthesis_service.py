import json
import os
from json import JSONDecodeError

import requests
from django.conf import settings
from django.utils import timezone

from reviews.models import Paper, Review, ThemeSynthesis
from reviews.services.prompt_loader import render_prompt_template
from reviews.services.design_canonicalizer import canonicalize_study_design, canonicalize_design_list


THEME_SYNTHESIS_PROMPT_FALLBACK = '''You are conducting a thematic synthesis for a systematic literature review.

=== REVIEW CONTEXT ===
RESEARCH OBJECTIVES:
{objectives}

RESEARCH QUESTIONS:
{rq_list_numbered}

TOTAL CONFIRMED PAPERS: {total_papers}

=== EVIDENCE CORPUS ===
{all_extractions_json}

Use these thresholds:
Established >= {established_threshold} papers
Emerging {emerging_min} to {emerging_max} papers
Insufficient < {insufficient_threshold} papers

Return ONLY a valid JSON array with objects containing:
theme_name, paper_ids, paper_count, pct_of_corpus, designs_represented,
finding_direction, evidence_grade, grade_rationale, theme_description.
'''

THEME_SYNTHESIS_JSON_CORRECTION_FALLBACK = (
    'Your previous response was not valid JSON. Return ONLY a valid JSON array from that response.\n'
    'Previous response:\n---\n{raw_response}\n---'
)


def build_extractions_for_matrix(review_id):
    review = Review.objects.get(pk=review_id)
    papers = list(
        review.papers.filter(full_text_decision=Paper.FullTextDecision.INCLUDED)
        .exclude(full_text_extraction={})
        .order_by('id')
    )

    result = []
    for paper in papers:
        ext = paper.full_text_extraction or {}
        if isinstance(ext, str):
            try:
                ext = json.loads(ext)
            except Exception:
                ext = {}

        if not isinstance(ext, dict) or not ext:
            continue

        short_ref = _build_short_ref(ext.get('author_year'), paper)

        item = {
            'paper_id': paper.id,
            'short_ref': short_ref,
            'year': paper.publication_year,
            'study_design': canonicalize_study_design(_safe_text(ext.get('study_design_canonical') or ext.get('study_design'))),
            'population': _safe_text(ext.get('population')),
            'intervention': _safe_text(ext.get('intervention') or ext.get('context')),
            'outcomes': _normalize_outcomes(ext),
            'study_country': _safe_text(ext.get('country')),
            'key_findings': _normalize_key_findings(ext.get('key_findings')),
        }
        result.append(item)

    return result


def synthesize_themes_for_review(review_id):
    review = Review.objects.get(pk=review_id)
    extractions = build_extractions_for_matrix(review_id)
    total_papers = len(extractions)
    if total_papers == 0:
        raise RuntimeError('No included papers with full_text_extraction found.')

    established_threshold = round(total_papers * 0.60)
    emerging_min = round(total_papers * 0.30)
    emerging_max = established_threshold - 1
    insufficient_threshold = emerging_min

    rq_items = list(review.research_questions.order_by('id'))
    rq_list_numbered = '\n'.join(
        f'RQ{index + 1}: {rq.question_text}' for index, rq in enumerate(rq_items)
    ) or 'No locked research questions found.'

    all_extractions_json = json.dumps(extractions, ensure_ascii=False, indent=2)

    prompt = render_prompt_template(
        'phase_17_theme_synthesis.md',
        context={
            'objectives': review.objectives or '',
            'rq_list_numbered': rq_list_numbered,
            'total_papers': total_papers,
            'established_threshold': established_threshold,
            'emerging_min': emerging_min,
            'emerging_max': emerging_max,
            'insufficient_threshold': insufficient_threshold,
            'all_extractions_json': all_extractions_json,
        },
        fallback=THEME_SYNTHESIS_PROMPT_FALLBACK,
    )

    raw = _call_deepseek(prompt=prompt)
    themes = _parse_theme_json_with_retry(raw)
    themes = _normalize_themes(
        themes,
        valid_paper_ids={item['paper_id'] for item in extractions},
        total_papers=total_papers,
    )

    _persist_theme_synthesis_gatekeeper(review=review, themes=themes)

    review.theme_synthesis = themes
    review.theme_synthesis_status = 'done'
    review.theme_synthesis_error = ''
    review.theme_synthesis_updated_at = timezone.now()
    review.save(
        update_fields=[
            'theme_synthesis',
            'theme_synthesis_status',
            'theme_synthesis_error',
            'theme_synthesis_updated_at',
        ]
    )

    return {
        'total_papers': total_papers,
        'theme_count': len(themes),
        'themes': themes,
    }


def _parse_theme_json_with_retry(raw_response, max_retries=2):
    current = raw_response
    for attempt in range(max_retries + 1):
        try:
            parsed = _extract_json(current)
            if isinstance(parsed, list):
                return parsed
            raise ValueError('Expected JSON array output for theme synthesis.')
        except (JSONDecodeError, ValueError):
            if attempt == max_retries:
                break
            correction_prompt = render_prompt_template(
                'phase_17_json_correction.md',
                context={'raw_response': current},
                fallback=THEME_SYNTHESIS_JSON_CORRECTION_FALLBACK,
            )
            current = _call_deepseek(prompt=correction_prompt)

    raise ValueError('Theme synthesis response could not be parsed as JSON array.')


def _persist_theme_synthesis_gatekeeper(review, themes):
    ThemeSynthesis.objects.filter(review=review).delete()

    created = []
    for index, item in enumerate(themes):
        theme = ThemeSynthesis.objects.create(
            review=review,
            theme_name_locked=_safe_text(item.get('theme_name')) or f'Theme {index + 1}',
            evidence_grade=_normalize_evidence_grade(item.get('evidence_grade')),
            paper_count=int(item.get('paper_count') or 0),
            pct_of_corpus=float(item.get('pct_of_corpus') or 0.0),
            finding_direction=_safe_text(item.get('finding_direction')),
            designs_represented=_normalize_str_list(item.get('designs_represented')),
            grade_rationale=_safe_text(item.get('grade_rationale')),
            theme_description=_safe_text(item.get('theme_description')),
            order_index=index,
        )
        created.append((theme, item))

    if not created:
        return

    all_pids = set()
    for _, item in created:
        for raw_pid in item.get('paper_ids') or []:
            try:
                all_pids.add(int(raw_pid))
            except (TypeError, ValueError):
                continue

    paper_map = {
        p.id: p
        for p in Paper.objects.filter(review=review, id__in=all_pids).only('id')
    }

    for theme, item in created:
        paper_ids = []
        for raw_pid in item.get('paper_ids') or []:
            try:
                pid = int(raw_pid)
            except (TypeError, ValueError):
                continue
            if pid in paper_map and pid not in paper_ids:
                paper_ids.append(pid)
        if paper_ids:
            theme.papers.set([paper_map[pid] for pid in paper_ids])


def _normalize_themes(themes, valid_paper_ids, total_papers):
    normalized = []
    for idx, item in enumerate(themes):
        if not isinstance(item, dict):
            continue

        raw_ids = item.get('paper_ids') or []
        paper_ids = []
        for val in raw_ids:
            try:
                pid = int(val)
            except (TypeError, ValueError):
                continue
            if pid in valid_paper_ids and pid not in paper_ids:
                paper_ids.append(pid)

        paper_count = len(paper_ids)
        pct = round((paper_count / total_papers) * 100, 1) if total_papers else 0.0

        normalized.append(
            {
                'theme_name': _safe_text(item.get('theme_name')) or f'Theme {idx + 1}',
                'paper_ids': paper_ids,
                'paper_count': int(item.get('paper_count') or paper_count),
                'pct_of_corpus': float(item.get('pct_of_corpus') or pct),
                'designs_represented': canonicalize_design_list(_normalize_str_list(item.get('designs_represented'))),
                'finding_direction': _safe_text(item.get('finding_direction')) or 'mixed',
                'evidence_grade': _safe_text(item.get('evidence_grade')) or 'Emerging',
                'grade_rationale': _safe_text(item.get('grade_rationale')),
                'theme_description': _safe_text(item.get('theme_description')),
            }
        )

    normalized.sort(key=lambda x: x.get('paper_count', 0), reverse=True)
    return normalized


def _normalize_outcomes(ext):
    outcomes = ext.get('outcomes')
    if isinstance(outcomes, list):
        return outcomes
    if isinstance(outcomes, dict):
        return [outcomes]

    findings = ext.get('key_findings')
    summary = ''
    if isinstance(findings, dict):
        summary = _safe_text(findings.get('summary'))
    elif isinstance(findings, str):
        summary = _safe_text(findings)

    if not summary:
        summary = _safe_text(ext.get('limitations'))

    if not summary:
        return []

    return [{'name': 'reported_outcome', 'result': summary, 'direction': 'mixed'}]


def _normalize_key_findings(value):
    if isinstance(value, dict):
        summary = _safe_text(value.get('summary'))
        structure = value.get('structure')
        if isinstance(structure, list) and structure:
            structured = ' '.join(_safe_text(x) for x in structure if _safe_text(x))
            return structured or summary
        return summary
    if isinstance(value, list):
        return ' '.join(_safe_text(x) for x in value if _safe_text(x))
    return _safe_text(value)


def _build_short_ref(author_year, paper):
    text = _safe_text(author_year)
    if text:
        return text

    author_block = _safe_text(paper.authors)
    if author_block:
        first = author_block.split(';')[0].strip()
        surname = first.split(',')[0].strip() or first.split(' ')[-1].strip()
    else:
        surname = 'Unknown'

    year = paper.publication_year or 'n.d.'
    return f'{surname} ({year})'


def _normalize_str_list(value):
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _normalize_evidence_grade(value):
    text = _safe_text(value).lower()
    if text == 'established':
        return ThemeSynthesis.EvidenceGrade.ESTABLISHED
    if text == 'contested':
        return ThemeSynthesis.EvidenceGrade.CONTESTED
    if text == 'insufficient':
        return ThemeSynthesis.EvidenceGrade.INSUFFICIENT
    return ThemeSynthesis.EvidenceGrade.EMERGING


def _safe_text(value):
    if value is None:
        return ''
    return str(value).strip()


def _call_deepseek(prompt):
    api_key = getattr(settings, 'DEEPSEEK_API_KEY', '') or os.getenv('DEEPSEEK_API_KEY', '')
    if not api_key:
        raise RuntimeError('DEEPSEEK_API_KEY is not configured.')

    base_url = (getattr(settings, 'DEEPSEEK_BASE_URL', '') or os.getenv('DEEPSEEK_BASE_URL', '') or 'https://api.deepseek.com').rstrip('/')
    model_name = getattr(settings, 'DEEPSEEK_THEME_MODEL', '') or os.getenv('DEEPSEEK_THEME_MODEL', '') or 'deepseek-reasoner'
    timeout_seconds = float(getattr(settings, 'DEEPSEEK_TIMEOUT_SECONDS', 90))

    url = f'{base_url}/chat/completions'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    payload = {
        'model': model_name,
        'messages': [
            {'role': 'system', 'content': 'Return only valid JSON array.'},
            {'role': 'user', 'content': prompt},
        ],
        'temperature': 0.0,
    }

    response = requests.post(url, headers=headers, json=payload, timeout=timeout_seconds)
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
        raise RuntimeError('DeepSeek returned empty theme synthesis content.')
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



