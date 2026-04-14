import json
import os
from json import JSONDecodeError

from django.conf import settings

from reviews.services.prompt_loader import render_prompt_template


SYSTEM_PROMPT_FALLBACK = """You are a research assistant helping plan the literature review section of an academic research paper.

When given the research context, research question set, and a total word count, output a structured plan for the literature review.
Do not write the review itself, only plan it.

Return only valid JSON with keys:
research_question, review_goal, total_words_allocated, sections, gap_statement, section_order_rationale.

Rules:
- Include 3 to 5 sections.
- Use section types only: foundation, debate, recent, gap.
- Exactly one gap section and it must be last.
- total_words_allocated must be 90% of target_word_count (rounded to nearest integer).
- Each section must include number, title, type, purpose, what_to_look_for, search_keywords, target_paper_count, leads_to, word_count_target.
- Each section must include notable_authors as a list of 3 to 6 well-known authors for that section topic.
- section.word_count_target values must sum exactly to total_words_allocated.
- Output only valid JSON. No markdown.
"""

USER_PROMPT_FALLBACK = """Main research context:
{research_context}

Research questions:
{research_questions_block}

Primary research question: {primary_research_question}
Total word count target: {target_word_count} words

Generate the literature review structure with word count distribution.
"""


def generate_lit_review_stage1_plan(*, research_context, research_questions, target_word_count):
    context_text = str(research_context or '').strip()
    if not context_text:
        raise RuntimeError('research_context is required.')

    if not isinstance(research_questions, list) or not research_questions:
        raise RuntimeError('research_questions must be a non-empty list.')

    normalized_questions = [str(item).strip() for item in research_questions if str(item).strip()]
    if not normalized_questions:
        raise RuntimeError('research_questions must contain at least one valid question.')

    primary_question = normalized_questions[0]
    questions_block = '\n'.join(f'- {question}' for question in normalized_questions)

    system_prompt = render_prompt_template(
        'lr_stage_1_structure_system.md',
        fallback=SYSTEM_PROMPT_FALLBACK,
    )
    user_prompt = render_prompt_template(
        'lr_stage_1_structure_user.md',
        context={
            'research_context': context_text,
            'research_question': primary_question,
            'research_questions_block': questions_block,
            'primary_research_question': primary_question,
            'target_word_count': target_word_count,
        },
        fallback=USER_PROMPT_FALLBACK.format(
            research_context=context_text,
            research_questions_block=questions_block,
            primary_research_question=primary_question,
            target_word_count=target_word_count,
        ),
    )
    raw = _call_gemini(system_prompt=system_prompt, user_prompt=user_prompt)
    plan = _extract_json(raw)
    _validate_stage1_plan(plan, research_question=primary_question, target_word_count=target_word_count)
    return plan


def _call_gemini(*, system_prompt, user_prompt):
    api_key = getattr(settings, 'GEMINI_API_KEY', '') or os.getenv('GEMINI_API_KEY', '')
    if not api_key:
        raise RuntimeError('GEMINI_API_KEY is not configured.')

    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError('google-genai SDK is not installed. Install with: pip install google-genai') from exc

    model_name = (
        getattr(settings, 'GEMINI_LR_STAGE1_MODEL', '')
        or os.getenv('GEMINI_LR_STAGE1_MODEL', '')
        or 'gemini-2.5-pro'
    )

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model_name,
        contents=f'{system_prompt}\n\n{user_prompt}',
    )
    text = (getattr(response, 'text', '') or '').strip()
    if not text:
        raise RuntimeError('Gemini returned empty response.')
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
    raise RuntimeError('Stage 1 plan response is not valid JSON.')


def _validate_stage1_plan(plan, *, research_question, target_word_count):
    if not isinstance(plan, dict):
        raise RuntimeError('Stage 1 plan must be a JSON object.')

    sections = plan.get('sections')
    if not isinstance(sections, list) or not sections:
        raise RuntimeError('Stage 1 plan sections are missing.')

    total_allocated = int(plan.get('total_words_allocated') or 0)
    expected_allocated = round(float(target_word_count) * 0.9)
    if total_allocated <= 0:
        raise RuntimeError('Stage 1 plan total_words_allocated is missing.')
    if abs(total_allocated - expected_allocated) > 10:
        raise RuntimeError(
            f'Stage 1 plan total_words_allocated ({total_allocated}) is not close to expected {expected_allocated}.'
        )

    allowed_types = {'foundation', 'debate', 'recent', 'gap'}
    section_sum = 0
    gap_count = 0
    last_section_type = None
    for idx, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            raise RuntimeError('Each section must be an object.')

        section_type = str(section.get('type') or '').strip().lower()
        if section_type not in allowed_types:
            raise RuntimeError(f'Section {idx} has invalid type "{section_type}".')
        if section_type == 'gap':
            gap_count += 1
        last_section_type = section_type

        word_count = int(section.get('word_count_target') or 0)
        if word_count <= 0:
            raise RuntimeError(f'Section {idx} has invalid word_count_target.')
        section_sum += word_count

        authors = section.get('notable_authors')
        if not isinstance(authors, list):
            raise RuntimeError(f'Section {idx} missing notable_authors list.')
        cleaned_authors = [str(item).strip() for item in authors if str(item).strip()]
        if len(cleaned_authors) < 3 or len(cleaned_authors) > 6:
            raise RuntimeError(f'Section {idx} notable_authors must contain 3 to 6 names.')
        section['notable_authors'] = cleaned_authors

    if section_sum != total_allocated:
        raise RuntimeError(
            f'Section word counts must sum to total_words_allocated ({total_allocated}), got {section_sum}.'
        )
    if gap_count != 1 or last_section_type != 'gap':
        raise RuntimeError('Plan must contain exactly one gap section and it must be last.')

    plan['research_question'] = str(plan.get('research_question') or research_question).strip()
