import json
import re
from reviews.services.prompt_templates import SCAFFOLD_PREAMBLE_TEMPLATE


def get_scaffold_data(review):
    data = review.scaffold_data if isinstance(review.scaffold_data, dict) else {}
    return dict(data)


def set_scaffold_data(review, data):
    review.scaffold_data = data if isinstance(data, dict) else {}


def get_theoretical_synthesis(scaffold_data):
    """
    Canonical source for theoretical synthesis fields is:
    scaffold_data["theoretical_synthesis"].

    Legacy fallback keys at top-level are read only when nested keys are absent.
    """
    scaffold = scaffold_data if isinstance(scaffold_data, dict) else {}
    nested = scaffold.get('theoretical_synthesis', {}) if isinstance(scaffold.get('theoretical_synthesis', {}), dict) else {}

    out = dict(nested)
    if 'third_order_synthesis' not in out:
        out['third_order_synthesis'] = str(scaffold.get('third_order_synthesis') or '')
    if 'revised_framework_narrative' not in out:
        out['revised_framework_narrative'] = str(scaffold.get('revised_framework_narrative') or '')
    if 'propositions' not in out:
        top_props = scaffold.get('propositions', [])
        out['propositions'] = top_props if isinstance(top_props, list) else []
    elif not isinstance(out.get('propositions'), list):
        out['propositions'] = []
    return out


def get_scaffold_preamble(
    review,
    previous_sections_labelled='',
    include_registry=True,
    include_theoretical_framework=True,
    include_conceptual_model=True,
    include_tccm=True,
):
    """
    Source of template is Review.scaffold_preamble_template.
    At call time we fill placeholders using Review.scaffold_data.
    """
    template_text = (review.scaffold_preamble_template or '').strip() or SCAFFOLD_PREAMBLE_TEMPLATE
    return _render_scaffold_template(
        template_text=template_text,
        review=review,
        include_registry=include_registry,
        previous_sections_labelled=previous_sections_labelled,
        include_theoretical_framework=include_theoretical_framework,
        include_conceptual_model=include_conceptual_model,
        include_tccm=include_tccm,
    )


def render_scaffold_preamble_from_data(
    review,
    include_registry=True,
    previous_sections_labelled='',
    include_theoretical_framework=True,
    include_conceptual_model=True,
    include_tccm=True,
):
    """
    Utility: render fallback/default template using scaffold_data.
    """
    return _render_scaffold_template(
        template_text=SCAFFOLD_PREAMBLE_TEMPLATE,
        review=review,
        include_registry=include_registry,
        previous_sections_labelled=previous_sections_labelled,
        include_theoretical_framework=include_theoretical_framework,
        include_conceptual_model=include_conceptual_model,
        include_tccm=include_tccm,
    )


def _render_scaffold_template(
    template_text,
    review,
    include_registry=True,
    previous_sections_labelled='',
    include_theoretical_framework=True,
    include_conceptual_model=True,
    include_tccm=True,
):
    scaffold = get_scaffold_data(review)
    phase_two = scaffold.get('phase_2', {}) if isinstance(scaffold.get('phase_2', {}), dict) else {}

    canonical_terms = scaffold.get('canonical_terms', {}) if isinstance(scaffold.get('canonical_terms', {}), dict) else {}
    primary_term = canonical_terms.get('primary') or scaffold.get('primary_term') or 'the core construct'
    banned_terms = canonical_terms.get('banned') if isinstance(canonical_terms.get('banned'), list) else scaffold.get('banned_terms', [])

    theme_names = scaffold.get('theme_names', []) if isinstance(scaffold.get('theme_names', []), list) else []
    prisma_counts = scaffold.get('prisma_counts', {}) if isinstance(scaffold.get('prisma_counts', {}), dict) else {}
    paper_registry = scaffold.get('paper_registry', []) if isinstance(scaffold.get('paper_registry', []), list) else []
    quality_summary_obj = scaffold.get('quality_summary', {}) if isinstance(scaffold.get('quality_summary', {}), dict) else {}
    subgroup_data_obj = scaffold.get('subgroup_data', {}) if isinstance(scaffold.get('subgroup_data', {}), dict) else {}
    review_metadata_obj = scaffold.get('review_metadata', {}) if isinstance(scaffold.get('review_metadata', {}), dict) else {}
    evidence_grades_obj = scaffold.get('evidence_grades', {}) if isinstance(scaffold.get('evidence_grades', {}), dict) else {}
    theoretical_framework_obj = scaffold.get('theoretical_framework', {}) if isinstance(scaffold.get('theoretical_framework', {}), dict) else {}
    theoretical_synthesis_obj = get_theoretical_synthesis(scaffold)
    propositions_obj = theoretical_synthesis_obj.get('propositions', [])
    pico = scaffold.get('pico', {}) if isinstance(scaffold.get('pico', {}), dict) else {}
    pico_population = str(pico.get('population') or review.pico_population or '').strip() or 'TBD'
    pico_outcomes = str(pico.get('outcomes') or review.pico_outcomes or '').strip() or 'TBD'

    if theme_names:
        theme_names_numbered = '\n'.join(f'{index + 1}. {name}' for index, name in enumerate(theme_names))
    else:
        theme_names_numbered = 'No locked theme names yet.'

    if include_registry and paper_registry:
        paper_registry_formatted = '\n'.join(str(item) for item in paper_registry)
    elif include_registry:
        paper_registry_formatted = 'No confirmed paper registry yet.'
    else:
        paper_registry_formatted = '[Registry omitted for this section.]'

    rq_items = phase_two.get('research_questions') or [
        {'rq': rq.question_text} for rq in review.research_questions.all().order_by('id')
    ]
    rq_numbered_list = '\n'.join(
        f'RQ{index + 1}: {item.get("rq", "")}' for index, item in enumerate(rq_items) if isinstance(item, dict)
    ) or 'No locked research questions yet.'

    quality_summary = json.dumps(quality_summary_obj, ensure_ascii=False, indent=2) if quality_summary_obj else '{}'
    subgroup_data = json.dumps(subgroup_data_obj, ensure_ascii=False, indent=2) if subgroup_data_obj else '{}'
    review_metadata = json.dumps(review_metadata_obj, ensure_ascii=False, indent=2) if review_metadata_obj else '{}'
    evidence_grades = json.dumps(evidence_grades_obj, ensure_ascii=False, indent=2) if evidence_grades_obj else '{}'
    propositions_formatted = json.dumps(propositions_obj, ensure_ascii=False, indent=2) if propositions_obj else '[]'

    theory_primary_lens = str(theoretical_framework_obj.get('primary_lens') or theoretical_framework_obj.get('recommended') or 'Not specified')
    supporting_lenses = theoretical_framework_obj.get('supporting_lenses', [])
    if not isinstance(supporting_lenses, list):
        supporting_lenses = []
    theory_supporting_lenses = ', '.join(str(x) for x in supporting_lenses) if supporting_lenses else 'None'
    theory_gaps_list = theoretical_framework_obj.get('theoretical_gaps', [])
    if not isinstance(theory_gaps_list, list):
        theory_gaps_list = []
    theory_gaps = ', '.join(str(x) for x in theory_gaps_list) if theory_gaps_list else 'None identified'

    if not include_theoretical_framework:
        theory_primary_lens = ''
        theory_supporting_lenses = ''
        theory_gaps = ''
        theoretical_framework_obj = {}

    if not include_conceptual_model:
        review_metadata_obj = dict(review_metadata_obj)
        review_metadata_obj['conceptual_model_included'] = False
        review_metadata = json.dumps(review_metadata_obj, ensure_ascii=False, indent=2)

    if not include_tccm:
        subgroup_data_obj = dict(subgroup_data_obj)
        subgroup_data_obj['tccm_included'] = False
        subgroup_data = json.dumps(subgroup_data_obj, ensure_ascii=False, indent=2)

    rendered = template_text.format(
        primary_term=primary_term,
        banned_terms_formatted=', '.join(str(x) for x in banned_terms) if banned_terms else 'None specified',
        scopus_retrieved=prisma_counts.get('scopus_retrieved', 'TBD'),
        after_dedup=prisma_counts.get('after_dedup', 'TBD'),
        passed_ta=prisma_counts.get('passed_ta', 'TBD'),
        pdfs_retrieved=prisma_counts.get('pdfs_retrieved', 'TBD'),
        abstract_only=prisma_counts.get('abstract_only', 'TBD'),
        passed_fulltext=prisma_counts.get('passed_fulltext', 'TBD'),
        user_excluded=prisma_counts.get('user_excluded', 'TBD'),
        final_included=prisma_counts.get('final_included', 'TBD'),
        theme_names_numbered=theme_names_numbered,
        evidence_grades=evidence_grades,
        theory_primary_lens=theory_primary_lens,
        theory_supporting_lenses=theory_supporting_lenses,
        theory_dominant=str(theoretical_framework_obj.get('dominant_theory') or ('Not identified' if include_theoretical_framework else '')),
        theory_coverage=str(theoretical_framework_obj.get('theory_coverage') or ('Not available' if include_theoretical_framework else '')),
        theory_gaps=theory_gaps,
        theory_landscape_summary=str(theoretical_framework_obj.get('landscape_summary') or ''),
        third_order_synthesis=str(theoretical_synthesis_obj.get('third_order_synthesis') or ''),
        propositions_formatted=(propositions_formatted if include_theoretical_framework else '[]'),
        revised_framework_narrative=str(theoretical_synthesis_obj.get('revised_framework_narrative') or ''),
        quality_summary=quality_summary,
        subgroup_data=subgroup_data,
        review_metadata=review_metadata,
        paper_count=len(paper_registry),
        paper_registry_formatted=paper_registry_formatted,
        rq_numbered_list=rq_numbered_list,
        pico_population=pico_population,
        pico_outcomes=pico_outcomes,
        previous_sections_labelled=previous_sections_labelled,
        prisma_counts=prisma_counts,
    )

    if not include_theoretical_framework:
        rendered = _remove_block(rendered, 'THEORETICAL FRAMEWORK (locked):', 'THEORETICAL SYNTHESIS (locked):')
        rendered = _remove_block(rendered, 'THEORETICAL SYNTHESIS (locked):', 'QUALITY SUMMARY (locked):')

    return rendered


def _remove_block(text, start_marker, end_marker):
    start = re.escape(start_marker)
    end = re.escape(end_marker)
    pattern = rf'{start}[\s\S]*?(?={end})'
    return re.sub(pattern, '', text, flags=re.MULTILINE).strip()
