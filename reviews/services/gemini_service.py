import json
import os
from json import JSONDecodeError

from django.conf import settings
from django.db import transaction

from reviews.constants import DEFAULT_EXCLUSION_CRITERIA, DEFAULT_INCLUSION_CRITERIA
from reviews.models import ResearchQuestion, Review
from reviews.services.prompt_loader import render_prompt_template
from reviews.services.prompt_templates import JSON_CORRECTION_PROMPT, RQ_FORMALIZATION_PROMPT
from reviews.services.scaffold_service import get_scaffold_preamble

_ALLOWED_RQ_TYPES = {
    ResearchQuestion.QuestionType.DESCRIPTIVE,
    ResearchQuestion.QuestionType.COMPARATIVE,
    ResearchQuestion.QuestionType.CAUSAL,
    ResearchQuestion.QuestionType.EXPLORATORY,
}


def formalize_research_parameters(review_id):
    review = Review.objects.get(pk=review_id)
    model_name = getattr(settings, 'GEMINI_RQ_MODEL', 'gemini-2.5-pro')

    prompt = render_prompt_template(
        'phase_2_rq_formalization.md',
        context={
            'objectives': review.objectives or '',
            'pico_population': review.pico_population or '',
            'pico_intervention': review.pico_intervention or '',
            'pico_comparison': review.pico_comparison or '',
            'pico_outcomes': review.pico_outcomes or '',
            'inclusion_criteria': review.inclusion_criteria or DEFAULT_INCLUSION_CRITERIA,
            'exclusion_criteria': review.exclusion_criteria or DEFAULT_EXCLUSION_CRITERIA,
        },
        fallback=RQ_FORMALIZATION_PROMPT,
    )

    raw_response = _call_gemini_model(prompt=prompt, model_name=model_name)
    parsed = _parse_json_with_correction(raw_response=raw_response, model_name=model_name)
    normalized = _normalize_formalization_payload(parsed=parsed, review=review)

    with transaction.atomic():
        review.pico_population = normalized['refined_pico']['population']
        review.pico_intervention = normalized['refined_pico']['intervention']
        review.pico_comparison = normalized['refined_pico']['comparison']
        review.pico_outcomes = normalized['refined_pico']['outcomes']
        review.inclusion_criteria = normalized['refined_criteria']['inclusion_criteria']
        review.exclusion_criteria = normalized['refined_criteria']['exclusion_criteria']

        stage_progress = review.stage_progress or {}
        stage_progress['phase_2'] = 'formalized'
        review.stage_progress = stage_progress
        review.save()

        review.research_questions.all().delete()
        ResearchQuestion.objects.bulk_create(
            [
                ResearchQuestion(
                    review=review,
                    question_text=item['rq'],
                    type=item['type'],
                )
                for item in normalized['research_questions']
            ]
        )

    return normalized


def render_scaffold_preamble(review, include_registry=True, previous_sections_labelled=''):
    return get_scaffold_preamble(
        review=review,
        previous_sections_labelled=previous_sections_labelled,
    )


def _call_gemini_model(prompt, model_name):
    api_key = getattr(settings, 'GEMINI_API_KEY', '') or os.getenv('GEMINI_API_KEY', '')
    if not api_key:
        raise RuntimeError('GEMINI_API_KEY is not configured.')

    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError('google-genai SDK is not installed. Install with: pip install google-genai') from exc

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
    )

    text = getattr(response, 'text', '') or ''
    if not text:
        raise RuntimeError('Gemini returned an empty response.')
    return text.strip()


def _parse_json_with_correction(raw_response, model_name, max_retries=2):
    current_response = raw_response
    for attempt in range(max_retries + 1):
        try:
            return _extract_json(current_response)
        except JSONDecodeError:
            if attempt == max_retries:
                break
            correction_prompt = render_prompt_template(
                'phase_2_json_correction.md',
                context={'raw_response': current_response},
                fallback=JSON_CORRECTION_PROMPT,
            )
            current_response = _call_gemini_model(
                prompt=correction_prompt,
                model_name=model_name,
            )

    raise ValueError('Gemini response could not be parsed as JSON after correction retries.')


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


def _normalize_formalization_payload(parsed, review):
    if isinstance(parsed, list):
        rq_items = parsed
        refined_pico = {}
        refined_criteria = {}
    else:
        rq_items = parsed.get('research_questions') or parsed.get('rqs') or []
        refined_pico = parsed.get('refined_pico') or parsed.get('pico') or {}
        refined_criteria = parsed.get('refined_criteria') or {
            'inclusion_criteria': parsed.get('inclusion_criteria', []),
            'exclusion_criteria': parsed.get('exclusion_criteria', []),
        }

    normalized_rqs = []
    for item in rq_items:
        if not isinstance(item, dict):
            continue

        rq_text = (item.get('rq') or item.get('question_text') or '').strip()
        if not rq_text:
            continue

        rq_type = (item.get('type') or ResearchQuestion.QuestionType.DESCRIPTIVE).strip().lower()
        if rq_type not in _ALLOWED_RQ_TYPES:
            rq_type = ResearchQuestion.QuestionType.DESCRIPTIVE

        normalized_rqs.append({'rq': rq_text, 'type': rq_type})

    if not normalized_rqs:
        normalized_rqs = [
            {
                'rq': review.objectives.strip(),
                'type': ResearchQuestion.QuestionType.EXPLORATORY,
            }
        ]

    inclusion = _normalize_criteria(
        refined_criteria.get('inclusion_criteria'),
        review.inclusion_criteria or DEFAULT_INCLUSION_CRITERIA,
    )
    exclusion = _normalize_criteria(
        refined_criteria.get('exclusion_criteria'),
        review.exclusion_criteria or DEFAULT_EXCLUSION_CRITERIA,
    )

    inclusion = _ensure_contains(inclusion, DEFAULT_INCLUSION_CRITERIA)
    exclusion = _ensure_contains(exclusion, DEFAULT_EXCLUSION_CRITERIA)

    return {
        'research_questions': normalized_rqs,
        'refined_pico': {
            'population': (refined_pico.get('population') or review.pico_population or '').strip(),
            'intervention': (refined_pico.get('intervention') or review.pico_intervention or '').strip(),
            'comparison': (refined_pico.get('comparison') or review.pico_comparison or '').strip(),
            'outcomes': (refined_pico.get('outcomes') or review.pico_outcomes or '').strip(),
        },
        'refined_criteria': {
            'inclusion_criteria': inclusion,
            'exclusion_criteria': exclusion,
        },
    }


def _normalize_criteria(value, fallback):
    if isinstance(value, list):
        lines = [str(item).strip() for item in value if str(item).strip()]
        return '\n'.join(lines)

    if isinstance(value, str) and value.strip():
        return value.strip()

    return (fallback or '').strip()


def _ensure_contains(full_text, required_text):
    if required_text.lower() in full_text.lower():
        return full_text
    if not full_text:
        return required_text
    return f'{required_text}\n{full_text}'
