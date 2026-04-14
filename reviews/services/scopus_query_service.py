import json
import os
import re
from json import JSONDecodeError

from django.conf import settings
from django.db import transaction

from reviews.models import Review, SearchQuery
from reviews.services.prompt_loader import render_prompt_template
from reviews.services.prompt_templates import SCOPUS_JSON_CORRECTION_PROMPT, SCOPUS_QUERY_PROMPT
from reviews.services.scaffold_service import get_scaffold_data

_FOCUS_ORDER = [
    SearchQuery.Focus.CORE,
    SearchQuery.Focus.CONSTRUCTS,
    SearchQuery.Focus.POPULATION,
    SearchQuery.Focus.OUTCOMES,
]
_FOCUS_SET = set(_FOCUS_ORDER)


def generate_scopus_queries(review_id):
    review = Review.objects.get(pk=review_id)
    model_name = getattr(settings, 'GEMINI_SCOPUS_MODEL', 'gemini-2.5-pro')
    start_year, end_year = _resolve_date_range(review)
    start_filter = start_year - 1
    end_filter = end_year + 1

    rqs = review.research_questions.order_by('id')
    rq_block = '\n'.join(f'- {rq.question_text} ({rq.type})' for rq in rqs) or '- None provided.'

    prompt = render_prompt_template(
        'phase_3_scopus_queries.md',
        context={
            'objectives': review.objectives or '',
            'research_questions': rq_block,
            'start_year': start_year,
            'end_year': end_year,
            'start_filter': start_filter,
            'end_filter': end_filter,
        },
        fallback=SCOPUS_QUERY_PROMPT,
    )

    raw = _call_gemini_model(prompt=prompt, model_name=model_name)
    parsed = _parse_json_array_with_retry(raw_response=raw, model_name=model_name)
    normalized = _normalize_queries(parsed, review=review, start_filter=start_filter, end_filter=end_filter)

    with transaction.atomic():
        review.search_queries.all().delete()
        SearchQuery.objects.bulk_create(
            [
                SearchQuery(
                    review=review,
                    query_string=item['query_string'],
                    focus=item['focus'],
                    rationale=item['rationale'],
                )
                for item in normalized
            ]
        )

        stage_progress = review.stage_progress or {}
        stage_progress['phase_3'] = 'queries_generated'
        review.stage_progress = stage_progress
        review.save(update_fields=['stage_progress'])

    return normalized


def _resolve_date_range(review):
    scaffold_data = get_scaffold_data(review)
    start_year = int(scaffold_data.get('start_year', 2010))
    end_year = int(scaffold_data.get('end_year', 2024))
    if start_year >= end_year:
        start_year, end_year = 2010, 2024
    return start_year, end_year


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
        raise RuntimeError('Gemini returned an empty response for Scopus query generation.')
    return text.strip()


def _parse_json_array_with_retry(raw_response, model_name, max_retries=2):
    current = raw_response
    for attempt in range(max_retries + 1):
        try:
            parsed = _extract_json(current)
            if isinstance(parsed, list):
                return parsed
            raise ValueError('Expected JSON array for query list.')
        except (JSONDecodeError, ValueError):
            if attempt == max_retries:
                break
            correction_prompt = render_prompt_template(
                'phase_3_json_correction.md',
                context={'raw_response': current},
                fallback=SCOPUS_JSON_CORRECTION_PROMPT,
            )
            current = _call_gemini_model(prompt=correction_prompt, model_name=model_name)

    raise ValueError('Unable to parse valid Scopus query JSON array after retries.')


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


def _normalize_queries(items, review, start_filter, end_filter):
    normalized_by_focus = {}

    for item in items:
        if not isinstance(item, dict):
            continue

        raw_focus = str(item.get('focus', '')).strip().lower()
        focus = _coerce_focus(raw_focus)
        if focus in normalized_by_focus:
            continue

        query_text = str(item.get('query', '')).strip()
        if not query_text:
            continue

        query_text = _append_global_filters(query_text, start_filter=start_filter, end_filter=end_filter)
        if focus == SearchQuery.Focus.CORE:
            query_text = _ensure_exactkeyword_limit(query_text, review=review)

        normalized_by_focus[focus] = {
            'focus': focus,
            'query_string': query_text,
            'rationale': str(item.get('rationale', '')).strip(),
        }

    for focus in _FOCUS_ORDER:
        if focus in normalized_by_focus:
            continue

        fallback_query = f'TITLE-ABS-KEY("{focus} construct" AND "target population")'
        fallback_query = _append_global_filters(fallback_query, start_filter=start_filter, end_filter=end_filter)
        if focus == SearchQuery.Focus.CORE:
            fallback_query = _ensure_exactkeyword_limit(fallback_query, review=review)

        normalized_by_focus[focus] = {
            'focus': focus,
            'query_string': fallback_query,
            'rationale': 'Fallback placeholder generated because model output did not include this focus.',
        }

    return [normalized_by_focus[focus] for focus in _FOCUS_ORDER]


def _append_global_filters(query_text, start_filter, end_filter):
    filter_fragment = (
        f' AND PUBYEAR > {start_filter} AND PUBYEAR < {end_filter}'
        ' AND ( LIMIT-TO ( DOCTYPE , "ar" ) )'
        ' AND ( LIMIT-TO ( LANGUAGE , "English" ) )'
    )

    lowered = query_text.lower()
    if 'pubyear >' in lowered and 'limit-to ( doctype' in lowered and 'limit-to ( language' in lowered:
        return query_text

    return f'{query_text}{filter_fragment}'


def _ensure_exactkeyword_limit(query_text, review):
    if 'EXACTKEYWORD' in query_text.upper():
        return query_text

    keywords = _derive_exact_keywords(review)
    return (
        f'{query_text} AND ( LIMIT-TO ( EXACTKEYWORD, "{keywords[0]}" ) '
        f'OR LIMIT-TO ( EXACTKEYWORD, "{keywords[1]}" ) '
        f'OR LIMIT-TO ( EXACTKEYWORD, "{keywords[2]}" ) )'
    )


def _derive_exact_keywords(review):
    corpus = f"{review.title or ''} {review.objectives or ''}"
    for rq in review.research_questions.all().order_by('id'):
        corpus += f" {rq.question_text}"

    stop_words = {
        'the', 'and', 'for', 'with', 'from', 'that', 'this', 'are', 'was', 'were',
        'into', 'between', 'among', 'about', 'study', 'review', 'research', 'question',
        'questions', 'objective', 'objectives', 'analysis', 'assess', 'assessing',
    }

    tokens = []
    for match in re.finditer(r'[A-Za-z][A-Za-z0-9_-]{2,}', corpus.lower()):
        word = match.group(0)
        if word in stop_words:
            continue
        if word not in tokens:
            tokens.append(word)
        if len(tokens) >= 3:
            break

    defaults = ['primary construct', 'target population', 'key outcome']
    while len(tokens) < 3:
        tokens.append(defaults[len(tokens)])
    return tokens[:3]


def _coerce_focus(raw_focus):
    if raw_focus in _FOCUS_SET:
        return raw_focus

    mapping = {
        'core terms': SearchQuery.Focus.CORE,
        'related constructs': SearchQuery.Focus.CONSTRUCTS,
        'construct': SearchQuery.Focus.CONSTRUCTS,
        'population-specific': SearchQuery.Focus.POPULATION,
        'outcome-specific': SearchQuery.Focus.OUTCOMES,
        'outcomes': SearchQuery.Focus.OUTCOMES,
    }
    return mapping.get(raw_focus, SearchQuery.Focus.CORE)


