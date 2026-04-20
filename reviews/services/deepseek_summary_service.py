import json
import os
import time
from json import JSONDecodeError

import requests
from django.conf import settings
from django.utils import timezone

from reviews.models import Paper, Review
from reviews.services.prompt_loader import render_prompt_template
from reviews.services.design_canonicalizer import canonicalize_study_design


DEFAULT_SUMMERY_PROMPT = '''You are a systematic review researcher extracting data from an academic paper.

Read the paper text carefully and return a single JSON object with exactly four top-level keys: "summary", "extraction", "quality", and "tccm".

Return ONLY valid JSON. No preamble. No explanation. No markdown fences.
Do not add trailing commas. Start with { and end with }.

=== OUTPUT SCHEMA ===

{
  "summary": "string - 500 to 600 words of continuous academic prose. See summary requirements below.",
  "extraction": {
    "author_year": "",
    "title": "",
    "country": "",
    "study_design": "",
    "data_type": "",
    "sample_size": "",
    "population": "",
    "context": "",
    "key_variables": "",
    "methodology": "",
    "theory_framework": "",
    "theoretical_frameworks": [
      {
        "theory_name": "",
        "usage_type": "primary | secondary | implicit",
        "how_used": ""
      }
    ],
    "key_findings": {
      "summary": "",
      "structure": [
        "Sentence 1: Main result (core finding; include numbers only if essential)",
        "Sentence 2: Secondary insight (moderator, mediator, or additional pattern)",
        "Sentence 3: Authors' conclusion or implication"
      ],
      "guidelines": [
        "Limit to 2-3 concise sentences",
        "Avoid unnecessary statistical detail",
        "Focus on insights, not raw outputs",
        "Maintain neutral academic tone",
        "Do not add interpretation beyond the paper"
      ]
    },
    "limitations": ""
  },
  "quality": {
    "study_type": "same value as study_design above",
    "total_score": 0,
    "dim_objectives": 0,
    "dim_design": 0,
    "dim_data": 0,
    "dim_analysis": 0,
    "dim_bias": 0,
    "risk_of_bias": "low | moderate | high",
    "strengths": ["strength 1", "strength 2", "strength 3"],
    "weaknesses": ["weakness 1", "weakness 2", "weakness 3"]
  },
  "tccm": {
    "theories": [
      {
        "theory_name": "",
        "theory_abbreviation": null,
        "usage_type": "primary | secondary | implicit",
        "usage_description": ""
      }
    ],
    "characteristics": {
      "unit_of_analysis": "",
      "sample_type": "",
      "longitudinal": false,
      "experimental": false,
      "sample_size_category": "",
      "publication_type": "",
      "journal_field": ""
    },
    "context": {
      "geographic_scope": "",
      "country_or_region": "",
      "economic_context": "",
      "digital_platform_type": "",
      "population_group": "",
      "temporal_context": ""
    },
    "methods": {
      "research_paradigm": "",
      "data_collection": "",
      "primary_analysis": "",
      "software_used": "",
      "validation_approach": ""
    }
  }
}

=== SUMMARY REQUIREMENTS ===

Write a 500 to 600 word narrative summary of this paper.
The summary must cover all of the following as continuous academic prose (no bullet points, no subheadings):

1. CONTEXT AND RATIONALE (1 paragraph)
Why was this study conducted? What gap does it address?
What is the theoretical or practical motivation?

2. METHODOLOGY (1-2 paragraphs)
Study design and why it was chosen.
Who were the participants: sample size, demographics, recruitment.
Where was the study conducted: country, setting, time period.
What instruments, scales, or data collection methods were used.
How was the data analysed.

3. FINDINGS (2 paragraphs)
Primary findings: be specific, include exact numbers, percentages,
effect sizes, p-values, or qualitative evidence where available.
Secondary findings, moderating variables, subgroup differences.
Do not generalise: report what this study actually found.

4. CONTRIBUTION AND LIMITATIONS (1 paragraph)
What does this paper contribute that other studies do not?
What are the author-stated limitations?
What do the authors recommend for future research?

Tone: academic, third person, past tense for what the study did,
present tense for what the evidence shows.
Do not be generic. Every sentence should be specific to this paper.
The summary will be used as input to thematic synthesis and must capture nuance and specificity.

=== QUALITY SCORING RUBRIC ===

Score each dimension 0 (poor), 1 (adequate), 2 (strong):

dim_objectives:
2 = Research question clearly stated, study design explicitly justified
1 = Research question present but vague, or design not justified
0 = No clear research question, design choice unexplained

dim_design:
2 = Design appropriate for research question, described in full detail
1 = Design broadly appropriate but incompletely described
0 = Design inappropriate or inadequately described

dim_data:
2 = Data collection rigorous, instruments validated, process transparent
1 = Data collection described but some gaps in transparency
0 = Data collection poorly described or instruments not validated

dim_analysis:
2 = Analytic approach systematic, appropriate, would be reproducible
1 = Analysis described but some steps unclear or sub-optimal
0 = Analysis poorly described or inappropriate for the data

dim_bias:
2 = Limitations explicitly acknowledged, reflexivity demonstrated (for qualitative), potential biases named and discussed
1 = Some limitations acknowledged but incomplete
0 = Limitations absent or superficial

total_score = sum of all five dimensions (range 0-10)
risk_of_bias: low = 8-10 | moderate = 5-7 | high = 0-4

=== PAPER TEXT ===

{minerU_full_paper_text}
'''

JSON_CORRECTION_PROMPT = (
    'Your previous response was not valid JSON. Return ONLY valid JSON object from that response, '
    'with exactly four top-level keys: "summary", "extraction", "quality", and "tccm".\n'
    'Original response:\n{raw_response}'
)


def run_deepseek_summery_for_review(
    review_id,
    progress_callback=None,
    stop_check=None,
    retry_failed_only=False,
    rerun_done_only=False,
):
    review = Review.objects.get(pk=review_id)
    papers = _eligible_papers(
        review=review,
        retry_failed_only=retry_failed_only,
        rerun_done_only=rerun_done_only,
    )
    _emit(progress_callback, {'event': 'started', 'targeted': len(papers), 'paper_ids': [p.id for p in papers]})

    processed_ids = []
    done = 0
    failed = 0

    for idx, paper in enumerate(papers, start=1):
        if stop_check and stop_check():
            _emit(progress_callback, {'event': 'stopped', 'processed_ids': list(processed_ids)})
            break

        _emit(progress_callback, {'event': 'processing', 'paper_id': paper.id, 'title': paper.title, 'index': idx, 'targeted': len(papers)})

        try:
            paper.full_text_summery_status = 'running'
            paper.full_text_summery_error = ''
            paper.full_text_summery_updated_at = timezone.now()
            paper.save(update_fields=['full_text_summery_status', 'full_text_summery_error', 'full_text_summery_updated_at'])

            text = _source_text_for_paper(paper)
            payload = _extract_summary_with_deepseek(paper_text=text)
            _save_summary_payload(paper=paper, payload=payload)
            done += 1
            processed_ids.append(paper.id)
            _emit(progress_callback, {'event': 'done', 'paper_id': paper.id, 'title': paper.title})
        except Exception as exc:
            failed += 1
            processed_ids.append(paper.id)
            paper.full_text_summery_status = 'failed'
            paper.full_text_summery_error = f'{exc.__class__.__name__}: {exc}'
            paper.full_text_summery_updated_at = timezone.now()
            paper.save(update_fields=['full_text_summery_status', 'full_text_summery_error', 'full_text_summery_updated_at'])
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


def _eligible_papers(review, retry_failed_only=False, rerun_done_only=False):
    qs = review.papers.filter(
        full_text_decision=Paper.FullTextDecision.INCLUDED,
        fulltext_retrieved=True,
    ).order_by('id')

    if rerun_done_only:
        qs = qs.filter(full_text_summery_status='done')
    elif retry_failed_only:
        qs = qs.filter(full_text_summery_status='failed')
    else:
        qs = qs.exclude(full_text_summery_status='done')

    papers = []
    for paper in qs:
        if (paper.mineru_markdown or '').strip():
            papers.append(paper)
    return papers


def _source_text_for_paper(paper):
    text = (paper.mineru_markdown or '').strip()

    if not text:
        raise RuntimeError('No paper text available (mineru_markdown empty).')

    return text


def _extract_summary_with_deepseek(paper_text):
    prompt_template = _load_prompt_template()
    prompt = prompt_template.replace('{minerU_full_paper_text}', paper_text)

    raw = _call_deepseek(prompt)
    try:
        payload = _extract_json(raw)
    except JSONDecodeError:
        correction = render_prompt_template(
            'phase_16_json_correction.md',
            context={'raw_response': raw},
            fallback=JSON_CORRECTION_PROMPT,
        )
        corrected = _call_deepseek(correction)
        payload = _extract_json(corrected)

    if not isinstance(payload, dict):
        raise RuntimeError('DeepSeek output is not a JSON object.')

    summary = payload.get('summary')
    extraction = payload.get('extraction')
    quality = payload.get('quality')
    tccm = payload.get('tccm')

    if not isinstance(summary, str) or not summary.strip():
        raise RuntimeError('DeepSeek output missing valid "summary" text.')

    if not isinstance(extraction, dict):
        raise RuntimeError('DeepSeek output missing valid "extraction" object.')

    if not isinstance(quality, dict):
        raise RuntimeError('DeepSeek output missing valid "quality" object.')
    if not isinstance(tccm, dict):
        tccm = {}

    quality = _normalize_quality(quality)
    tccm = _normalize_tccm(tccm, extraction)

    return {
        'summary': summary.strip(),
        'extraction': extraction,
        'quality': quality,
        'tccm': tccm,
    }


def _normalize_quality(quality):
    def _int_0_2(value):
        try:
            i = int(value)
        except (TypeError, ValueError):
            return 0
        if i < 0:
            return 0
        if i > 2:
            return 2
        return i

    dim_objectives = _int_0_2(quality.get('dim_objectives'))
    dim_design = _int_0_2(quality.get('dim_design'))
    dim_data = _int_0_2(quality.get('dim_data'))
    dim_analysis = _int_0_2(quality.get('dim_analysis'))
    dim_bias = _int_0_2(quality.get('dim_bias'))

    computed_total = dim_objectives + dim_design + dim_data + dim_analysis + dim_bias

    try:
        provided_total = int(quality.get('total_score'))
    except (TypeError, ValueError):
        provided_total = computed_total

    total_score = max(0, min(10, provided_total if provided_total == computed_total else computed_total))

    if total_score >= 8:
        risk_of_bias = 'low'
    elif total_score >= 5:
        risk_of_bias = 'moderate'
    else:
        risk_of_bias = 'high'

    strengths = quality.get('strengths')
    weaknesses = quality.get('weaknesses')
    if not isinstance(strengths, list):
        strengths = []
    if not isinstance(weaknesses, list):
        weaknesses = []

    return {
        'study_type': str(quality.get('study_type') or '').strip(),
        'total_score': total_score,
        'dim_objectives': dim_objectives,
        'dim_design': dim_design,
        'dim_data': dim_data,
        'dim_analysis': dim_analysis,
        'dim_bias': dim_bias,
        'risk_of_bias': risk_of_bias,
        'strengths': [str(item).strip() for item in strengths if str(item).strip()],
        'weaknesses': [str(item).strip() for item in weaknesses if str(item).strip()],
    }


def _save_summary_payload(paper, payload):
    extraction = payload['extraction'] if isinstance(payload.get('extraction'), dict) else {}
    quality = payload['quality'] if isinstance(payload.get('quality'), dict) else {}
    tccm = payload['tccm'] if isinstance(payload.get('tccm'), dict) else {}

    raw_design = str(extraction.get('study_design') or quality.get('study_type') or '').strip()
    extraction['study_design_canonical'] = canonicalize_study_design(raw_design)
    extraction['theoretical_frameworks'] = _normalize_theoretical_frameworks(extraction)

    paper.full_text_summery = payload['summary']
    paper.full_text_extraction = extraction
    paper.full_text_quality = quality
    paper.full_text_tccm = tccm
    paper.full_text_summery_status = 'done'
    paper.full_text_summery_error = ''
    paper.full_text_summery_updated_at = timezone.now()
    paper.save(
        update_fields=[
            'full_text_summery',
            'full_text_extraction',
            'full_text_quality',
            'full_text_tccm',
            'full_text_summery_status',
            'full_text_summery_error',
            'full_text_summery_updated_at',
        ]
    )


def _normalize_tccm(tccm, extraction):
    if not isinstance(tccm, dict):
        tccm = {}

    theories = tccm.get('theories')
    normalized_theories = []
    if isinstance(theories, list):
        for row in theories:
            if not isinstance(row, dict):
                continue
            name = str(row.get('theory_name') or '').strip()
            if not name:
                continue
            usage = str(row.get('usage_type') or 'secondary').strip().lower()
            if usage not in {'primary', 'secondary', 'implicit'}:
                usage = 'secondary'
            normalized_theories.append(
                {
                    'theory_name': name,
                    'theory_abbreviation': (
                        str(row.get('theory_abbreviation')).strip()
                        if row.get('theory_abbreviation') not in (None, '', 'null')
                        else None
                    ),
                    'usage_type': usage,
                    'usage_description': str(row.get('usage_description') or '').strip(),
                }
            )

    if not normalized_theories:
        fallback_theories = _normalize_theoretical_frameworks(extraction)
        for th in fallback_theories:
            normalized_theories.append(
                {
                    'theory_name': str(th.get('theory_name') or '').strip(),
                    'theory_abbreviation': None,
                    'usage_type': str(th.get('usage_type') or 'secondary').strip(),
                    'usage_description': str(th.get('how_used') or '').strip(),
                }
            )

    characteristics = tccm.get('characteristics') if isinstance(tccm.get('characteristics'), dict) else {}
    context = tccm.get('context') if isinstance(tccm.get('context'), dict) else {}
    methods = tccm.get('methods') if isinstance(tccm.get('methods'), dict) else {}

    return {
        'theories': normalized_theories,
        'characteristics': {
            'unit_of_analysis': str(characteristics.get('unit_of_analysis') or '').strip(),
            'sample_type': str(characteristics.get('sample_type') or '').strip(),
            'longitudinal': bool(characteristics.get('longitudinal')),
            'experimental': bool(characteristics.get('experimental')),
            'sample_size_category': str(characteristics.get('sample_size_category') or '').strip(),
            'publication_type': str(characteristics.get('publication_type') or '').strip(),
            'journal_field': str(characteristics.get('journal_field') or '').strip(),
        },
        'context': {
            'geographic_scope': str(context.get('geographic_scope') or '').strip(),
            'country_or_region': str(context.get('country_or_region') or '').strip(),
            'economic_context': str(context.get('economic_context') or '').strip(),
            'digital_platform_type': str(context.get('digital_platform_type') or '').strip(),
            'population_group': str(context.get('population_group') or '').strip(),
            'temporal_context': str(context.get('temporal_context') or '').strip(),
        },
        'methods': {
            'research_paradigm': str(methods.get('research_paradigm') or '').strip(),
            'data_collection': str(methods.get('data_collection') or '').strip(),
            'primary_analysis': str(methods.get('primary_analysis') or '').strip(),
            'software_used': str(methods.get('software_used') or '').strip(),
            'validation_approach': str(methods.get('validation_approach') or '').strip(),
        },
    }


def _normalize_theoretical_frameworks(extraction):
    raw = extraction.get('theoretical_frameworks')
    normalized = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            theory_name = str(item.get('theory_name') or '').strip()
            if not theory_name:
                continue
            usage_type = str(item.get('usage_type') or 'secondary').strip().lower()
            if usage_type not in {'primary', 'secondary', 'implicit'}:
                usage_type = 'secondary'
            how_used = str(item.get('how_used') or '').strip()
            normalized.append(
                {
                    'theory_name': theory_name,
                    'usage_type': usage_type,
                    'how_used': how_used,
                }
            )

    if normalized:
        return normalized

    # Backward compatibility from older single-field extraction schema.
    legacy = str(extraction.get('theory_framework') or '').strip()
    if legacy:
        return [{'theory_name': legacy, 'usage_type': 'secondary', 'how_used': ''}]
    return []


def _call_deepseek(prompt):
    api_key = getattr(settings, 'DEEPSEEK_API_KEY', '') or os.getenv('DEEPSEEK_API_KEY', '')
    if not api_key:
        raise RuntimeError('DEEPSEEK_API_KEY is not configured.')

    base_url = (getattr(settings, 'DEEPSEEK_BASE_URL', '') or os.getenv('DEEPSEEK_BASE_URL', '') or 'https://api.deepseek.com').rstrip('/')
    model_name = getattr(settings, 'DEEPSEEK_SUMMERY_MODEL', '') or os.getenv('DEEPSEEK_SUMMERY_MODEL', '') or 'deepseek-reasoner'
    timeout_seconds = float(getattr(settings, 'DEEPSEEK_TIMEOUT_SECONDS', 90))

    url = f'{base_url}/chat/completions'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    payload = {
        'model': model_name,
        'messages': [
            {'role': 'system', 'content': 'Return only valid JSON with keys summary, extraction, quality, and tccm.'},
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


def _load_prompt_template():
    prompt = render_prompt_template('phase_16_deepseek_summary.md')
    if prompt:
        return prompt

    legacy_prompt_file = os.path.join(getattr(settings, 'BASE_DIR', ''), 'summery_prompt.md')
    if os.path.exists(legacy_prompt_file):
        with open(legacy_prompt_file, 'r', encoding='utf-8') as handle:
            raw = handle.read().strip()
        if raw:
            return raw

    return DEFAULT_SUMMERY_PROMPT


def _emit(callback, payload):
    if not callback:
        return
    try:
        callback(payload)
    except Exception:
        return





