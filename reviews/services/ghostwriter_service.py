import json
import os
import re
from collections import OrderedDict

import requests
from django.conf import settings
from django.utils import timezone

from reviews.models import Review
from reviews.services.prompt_loader import render_prompt_template
from reviews.services.scaffold_service import get_scaffold_data, get_scaffold_preamble, get_theoretical_synthesis
from reviews.services.sensitivity_service import get_or_compute_sensitivity_results


GHOSTWRITER_SHELL_FALLBACK = """{scaffold_preamble}

TASK: ACADEMIC MANUSCRIPT GENERATION
SECTION TO WRITE: {section_name}

PREVIOUS SECTION CONTEXT:
{previous_section_text}

SPECIFIC DATA FOR THIS SECTION:
{section_specific_payload}

WRITING INSTRUCTIONS:
{section_instructions}

Return only the section prose text. No JSON.
""".strip()

SECTION_INSTRUCTION_FALLBACK = """Write this section in academic prose.
Use only provided scaffold and payload data.
No bullet points unless section requires explicit subsection labels.
""".strip()


SECTION_MAP = [
    {'key': '1_0_introduction', 'name': '1.0 Introduction', 'prompt': 'phase_23_1_0_introduction.md', 'include_registry': False, 'payload': 'intro_payload', 'placeholder_tags': []},
    {'key': '2_1_search_strategy', 'name': '2.1 Search Strategy', 'prompt': 'phase_23_2_1_search_strategy.md', 'include_registry': False, 'payload': 'search_payload', 'placeholder_tags': ['[INSERT TABLE 1: SCOPUS QUERY STRINGS]']},
    {'key': '2_2_selection_criteria', 'name': '2.2 Selection Criteria', 'prompt': 'phase_23_2_2_selection_criteria.md', 'include_registry': False, 'payload': 'criteria_payload', 'placeholder_tags': ['[INSERT TABLE 2: PICO AND CRITERIA]']},
    {'key': '2_3_study_selection_process', 'name': '2.3 Study Selection Process', 'prompt': 'phase_23_2_3_study_selection_process.md', 'include_registry': False, 'payload': 'study_selection_process_payload', 'placeholder_tags': []},
    {'key': '2_4_data_extraction', 'name': '2.4 Data Extraction', 'prompt': 'phase_23_2_4_data_extraction.md', 'include_registry': False, 'payload': 'data_extraction_payload', 'placeholder_tags': []},
    {'key': '3_1_study_selection', 'name': '3.1 Study Selection', 'prompt': 'phase_23_3_1_study_selection.md', 'include_registry': False, 'payload': 'study_selection_payload', 'placeholder_tags': ['[INSERT FIGURE 1: PRISMA FLOW DIAGRAM]']},
    {'key': '3_2_study_characteristics', 'name': '3.2 Study Characteristics', 'prompt': 'phase_23_3_2_study_characteristics.md', 'include_registry': True, 'payload': 'study_characteristics_payload', 'placeholder_tags': ['[INSERT TABLE 3: STUDY CHARACTERISTICS]']},
    {'key': '3_2b_tccm_analysis', 'name': '3.2b TCCM Analysis', 'prompt': 'phase_23_3_2b_tccm_analysis.md', 'include_registry': True, 'payload': 'tccm_payload', 'placeholder_tags': ['[INSERT TABLE 3B: TCCM ANALYSIS]']},
    {'key': '3_3_quality_assessment_results', 'name': '3.3 Quality Assessment', 'prompt': 'phase_23_3_3_quality_results.md', 'include_registry': True, 'payload': 'quality_results_payload', 'placeholder_tags': ['[INSERT TABLE 4: QUALITY ASSESSMENT SUMMARY]', '[INSERT FIGURE 2: RISK OF BIAS CHART]']},
    {'key': '3_4_bibliometric_findings', 'name': '3.4 Bibliometric Findings', 'prompt': 'phase_23_3_4_bibliometric_findings.md', 'include_registry': True, 'payload': 'bibliometric_payload', 'placeholder_tags': ['[INSERT FIGURE 3: BIBLIOMETRIC OVERVIEW]']},
    {'key': '3_5_synthesis_of_themes', 'name': '3.5 Synthesis of Findings', 'prompt': 'phase_23_3_5_synthesis_of_themes.md', 'include_registry': True, 'payload': 'themes_payload', 'placeholder_tags': ['[INSERT FIGURE 4: THEME FREQUENCY]', '[INSERT FIGURE 5: EVIDENCE HEATMAP]']},
    {'key': '3_6_subgroup_analysis', 'name': '3.6 Subgroup Analysis', 'prompt': 'phase_23_3_6_subgroup_analysis.md', 'include_registry': True, 'payload': 'subgroup_payload', 'placeholder_tags': ['[INSERT FIGURE 6: SUBGROUP ANALYSIS PANELS]']},
    {'key': '3_7_theory_landscape', 'name': '3.7 Theory Landscape of the Corpus', 'prompt': 'phase_23_3_7_theory_landscape.md', 'include_registry': True, 'payload': 'theory_landscape_payload', 'placeholder_tags': []},
    {'key': '3_8_theoretical_synthesis', 'name': '3.8 Cross-Theme Theoretical Synthesis and Propositions', 'prompt': 'phase_23_3_8_theoretical_synthesis.md', 'include_registry': True, 'payload': 'theoretical_synthesis_payload', 'placeholder_tags': []},
    {'key': '4_0_discussion', 'name': '4.0 Discussion', 'prompt': 'phase_23_4_0_discussion.md', 'include_registry': True, 'payload': 'discussion_payload', 'placeholder_tags': ['[INSERT FIGURE 7: CONCEPTUAL MODEL]']},
    {'key': '6_0_future_research', 'name': '6.0 Future Research Agenda', 'prompt': 'phase_23_6_0_future_research_tccm_on.md', 'include_registry': False, 'payload': 'future_research_payload', 'placeholder_tags': []},
    {'key': '5_0_conclusion', 'name': '5.0 Conclusion', 'prompt': 'phase_23_5_0_conclusion.md', 'include_registry': False, 'payload': 'conclusion_payload', 'placeholder_tags': []},
    {'key': 'abstract', 'name': 'Abstract', 'prompt': 'phase_23_abstract.md', 'include_registry': True, 'payload': 'abstract_payload', 'placeholder_tags': []},
    {'key': 'references', 'name': 'References', 'prompt': 'phase_23_references.md', 'include_registry': True, 'payload': 'references_payload', 'placeholder_tags': [], 'non_llm': True},
]


class GhostwriterService:
    stage_key = 'phase_23_ghostwriter'

    def __init__(self, review_id):
        self.review = Review.objects.get(pk=review_id)
        self.model_name = (
            getattr(settings, 'DEEPSEEK_GHOSTWRITER_MODEL', '')
            or os.getenv('DEEPSEEK_GHOSTWRITER_MODEL', '')
            or 'deepseek-reasoner'
        )

    def run(self, mode='next', section_key=None, retry=False):
        stage = self._ensure_stage()
        options = self._options(stage)
        self._preflight_validate(stage=stage, options=options)
        if options.get('include_theoretical_framework', True):
            scaffold = get_scaffold_data(self.review)
            tf = scaffold.get('theoretical_framework', {}) if isinstance(scaffold.get('theoretical_framework', {}), dict) else {}
            if str(tf.get('status') or '').strip().lower() == 'awaiting_confirmation':
                raise RuntimeError('Theoretical lens is awaiting confirmation. Confirm lens before running Ghostwriter with theory enabled.')
        stage['status'] = 'running'
        stage['started_at'] = timezone.now().isoformat()
        stage['error_code'] = ''
        stage['error_message'] = ''
        if not retry:
            stage['stop_requested'] = False
        self._save_stage(stage)

        targets = self._resolve_targets(stage=stage, mode=mode, section_key=section_key)
        if not targets:
            stage['status'] = 'completed'
            stage['completed_at'] = timezone.now().isoformat()
            self._save_stage(stage)
            return {'written': 0, 'stopped': False}

        written = 0
        for key in targets:
            if self._stop_requested():
                stage = self._ensure_stage()
                stage['status'] = 'stopped'
                stage['completed_at'] = timezone.now().isoformat()
                self._log(stage, 'stopped', f'Stopped before section {key}.')
                self._save_stage(stage)
                return {'written': written, 'stopped': True}

            stage = self._ensure_stage()
            stage['current_section_key'] = key
            sec = stage['sections'][key]
            sec['status'] = 'running'
            sec['error'] = ''
            self._save_stage(stage)

            try:
                text = self._write_section(stage=stage, section_key=key)
                stage = self._ensure_stage()
                sec = stage['sections'][key]
                sec['text'] = text
                sec['status'] = 'done'
                sec['updated_at'] = timezone.now().isoformat()
                sec['word_count'] = self._word_count(text)
                self._log(stage, 'section_done', f'{key} written ({sec["word_count"]} words).')
                self._save_stage(stage)
                written += 1
            except Exception as exc:
                stage = self._ensure_stage()
                sec = stage['sections'][key]
                sec['status'] = 'failed'
                sec['error'] = f'{exc.__class__.__name__}: {exc}'
                sec['updated_at'] = timezone.now().isoformat()
                self._log(stage, 'section_failed', f'{key} failed: {exc.__class__.__name__}: {exc}')
                stage['status'] = 'error'
                stage['error_code'] = exc.__class__.__name__
                stage['error_message'] = str(exc)
                stage['completed_at'] = timezone.now().isoformat()
                self._save_stage(stage)
                return {'written': written, 'stopped': False}

        stage = self._ensure_stage()
        stage['current_section_key'] = ''
        stage['status'] = 'completed' if self._all_done(stage) else 'idle'
        stage['completed_at'] = timezone.now().isoformat()
        stage['compiled_draft'] = self._compile_draft(stage)
        self._save_stage(stage)
        return {'written': written, 'stopped': False}

    def _resolve_targets(self, stage, mode, section_key):
        order = self._active_order(stage=stage)
        if mode == 'section' and section_key in order:
            return [section_key]
        if mode == 'all':
            return [k for k in order if stage['sections'][k].get('status') != 'done']
        if mode == 'failed':
            return [k for k in order if stage['sections'][k].get('status') == 'failed']
        for k in order:
            if stage['sections'][k].get('status') != 'done':
                return [k]
        return []

    def _write_section(self, stage, section_key):
        config = next(x for x in SECTION_MAP if x['key'] == section_key)
        payload = self._build_payload(config['payload'], stage)
        options = self._options(stage)

        if config.get('non_llm'):
            return self._inject_placeholders(self._render_references(payload), config)

        previous_text = self._previous_section_text(stage, section_key)
        scaffold_preamble = get_scaffold_preamble(
            self.review,
            previous_sections_labelled='',
            include_registry=bool(config.get('include_registry', True)),
            include_theoretical_framework=options.get('include_theoretical_framework', True),
            include_conceptual_model=options.get('include_conceptual_model', True),
            include_tccm=options.get('include_tccm', True),
        )
        prompt_file = self._resolve_prompt_file(section_key=section_key, options=options, default_prompt=config['prompt'])

        section_context = self._build_section_prompt_context(
            stage=stage,
            section_key=section_key,
            payload=payload,
        )
        section_instructions = render_prompt_template(
            prompt_file,
            context=section_context,
            fallback=SECTION_INSTRUCTION_FALLBACK,
        )
        self._assert_no_unresolved_placeholders(section_instructions, section_key=section_key)

        prompt = render_prompt_template(
            'phase_23_shell.md',
            context={
                'scaffold_preamble': scaffold_preamble,
                'section_name': config['name'],
                'previous_section_text': previous_text,
                'section_specific_payload': json.dumps(payload, ensure_ascii=False, indent=2),
                'section_instructions': section_instructions,
            },
            fallback=GHOSTWRITER_SHELL_FALLBACK,
        )
        return self._inject_placeholders(self._call_deepseek(prompt), config, stage=stage)

    def _build_section_prompt_context(self, stage, section_key, payload):
        scaffold = get_scaffold_data(self.review)
        theory = scaffold.get('theoretical_framework', {}) if isinstance(scaffold.get('theoretical_framework', {}), dict) else {}
        subgroup = payload.get('subgroup_data', {}) if isinstance(payload.get('subgroup_data', {}), dict) else {}
        research_questions = payload.get('research_questions', []) if isinstance(payload.get('research_questions', []), list) else []

        ctx = {}
        for key, value in payload.items():
            if isinstance(value, (dict, list)):
                ctx[key] = json.dumps(value, ensure_ascii=False, indent=2)
            else:
                ctx[key] = value

        primary_lens = str(payload.get('primary_lens') or theory.get('primary_lens') or theory.get('recommended') or '').strip()
        absent_theories = theory.get('theoretical_gaps', []) if isinstance(theory.get('theoretical_gaps', []), list) else []
        propositions = payload.get('propositions', []) if isinstance(payload.get('propositions', []), list) else []

        ctx['SECTION_LABEL_BLOCK'] = self._section_label_block(stage=stage, section_key=section_key)
        ctx['primary_theoretical_lens'] = primary_lens
        ctx['absent_theories_formatted'] = self._format_list(absent_theories) or 'None identified'
        ctx['lens_pct_of_corpus'] = self._lens_pct_of_corpus(primary_lens)
        ctx['rq_numbered_list'] = self._rq_numbered_list(research_questions)
        ctx['primary_topic'] = str(self.review.title or 'the review topic')
        ctx['propositions_formatted'] = json.dumps(propositions, ensure_ascii=False, indent=2) if propositions else '[]'
        ctx['third_order_synthesis_text'] = str(payload.get('third_order_synthesis') or '')
        ctx['theme_grades_formatted'] = self._theme_grades_formatted(payload)
        ctx['all_reconciled_texts_formatted'] = self._all_reconciled_texts_formatted(payload)

        rq_answers = self._rq_answers_formatted(payload)
        ctx['rq_answers_formatted'] = rq_answers
        ctx['rq1_answer'] = self._rq_single_answer(payload, 1)
        ctx['rq3_paragraph_if_applicable'] = self._rq3_placeholder_block(payload)

        by_design = payload.get('by_design') or subgroup.get('by_design') or {}
        by_country = payload.get('by_country') or subgroup.get('by_country') or {}
        by_year = payload.get('by_year') or subgroup.get('by_year') or {}
        ctx['by_design_formatted'] = json.dumps(by_design, ensure_ascii=False, indent=2)
        ctx['by_country_formatted'] = json.dumps(by_country, ensure_ascii=False, indent=2)
        ctx['by_year_groups_formatted'] = json.dumps(by_year, ensure_ascii=False, indent=2)
        ctx['year_subgroup_eligible'] = str(subgroup.get('year_subgroup_eligible', 'unknown'))
        ctx['country_subgroup_note'] = self._country_subgroup_note(by_country)

        tccm_future = payload.get('tccm_future_research') if isinstance(payload.get('tccm_future_research'), list) else []
        ctx['tccm_key_gaps_or_omit'] = json.dumps(tccm_future[:5], ensure_ascii=False, indent=2) if tccm_future else 'TCCM gaps not available or omitted.'

        if propositions:
            ctx['propositions_testing_subsection_or_omit'] = (
                'Add a short subsection on testing P1, P2, and P3 with concrete designs and contexts.'
            )
        else:
            ctx['propositions_testing_subsection_or_omit'] = 'No propositions-testing subsection required.'

        # Template helper placeholder appearing as prose token in one prompt.
        ctx['theme_name'] = 'Theme Name'

        return ctx

    def _build_payload(self, stage_payload_key, stage):
        scaffold = get_scaffold_data(self.review)
        prisma = scaffold.get('prisma_counts', {}) if isinstance(scaffold.get('prisma_counts', {}), dict) else {}
        review_meta = scaffold.get('review_metadata', {}) if isinstance(scaffold.get('review_metadata', {}), dict) else {}
        subgroups = scaffold.get('subgroup_data', {}) if isinstance(scaffold.get('subgroup_data', {}), dict) else {}
        quality_summary = scaffold.get('quality_summary', {}) if isinstance(scaffold.get('quality_summary', {}), dict) else {}
        paper_registry = scaffold.get('paper_registry', []) if isinstance(scaffold.get('paper_registry', []), list) else []
        options = self._options(stage)
        sensitivity_results = {}
        if options.get('include_sensitivity', True):
            sensitivity_results = get_or_compute_sensitivity_results(self.review)

        rqs = [q.question_text for q in self.review.research_questions.order_by('id') if (q.question_text or '').strip()]
        rq_map = {f'rq{idx + 1}_text': text for idx, text in enumerate(rqs)}
        rq_map.setdefault('rq1_text', 'Not applicable')
        rq_map.setdefault('rq2_text', 'Not applicable')
        rq_map.setdefault('rq3_text', 'Not applicable')
        themes = list(self.review.theme_syntheses.order_by('order_index', 'id'))

        confidence_threshold = float(getattr(settings, 'SCREENING_CONFLICT_THRESHOLD', 0.72))
        auto_include_floor = 0.92
        auto_included_count = int(prisma.get('auto_included') or self.review.papers.filter(ta_confidence__gte=auto_include_floor).count())
        user_excluded_count = int(prisma.get('user_excluded') or prisma.get('fulltext_excluded') or 0)
        presented_after_fulltext_count = int(prisma.get('passed_fulltext') or prisma.get('final_included') or len(paper_registry) or 0)
        start_year, end_year = self._derive_year_range(review_meta)

        common = {
            'rq_count': len(rqs),
            'research_questions': rqs,
            'confidence_threshold': confidence_threshold,
            'auto_include_floor': auto_include_floor,
            'auto_included_count': auto_included_count,
            'user_excluded_count': user_excluded_count,
            'paper_count': presented_after_fulltext_count,
            'start_year': start_year,
            'end_year': end_year,
            'final_included': int(prisma.get('final_included') or 0),
            'theme_count': len(themes),
            'features': options,
            'sensitivity_results': sensitivity_results,
            **rq_map,
        }

        if stage_payload_key == 'intro_payload':
            return {**common, 'objectives': self.review.objectives}

        if stage_payload_key == 'search_payload':
            queries = list(self.review.search_queries.order_by('id').values('focus', 'query_string'))
            return {**common, 'queries': queries, 'query_count': len(queries), 'review_metadata': review_meta}

        if stage_payload_key == 'criteria_payload':
            return {**common, 'pico': scaffold.get('pico', {}), 'inclusion_criteria': self.review.inclusion_criteria, 'exclusion_criteria': self.review.exclusion_criteria}

        if stage_payload_key == 'study_selection_process_payload':
            return {**common, 'prisma_counts': prisma, 'retrieval_sources': ['Unpaywall', 'PMC', 'Semantic Scholar', 'arXiv', 'Europe PMC']}

        if stage_payload_key == 'data_extraction_payload':
            return {
                **common,
                'quality_rubric': {
                    'dimensions': ['dim_objectives', 'dim_design', 'dim_data', 'dim_analysis', 'dim_bias'],
                    'score_range': '0-10',
                    'risk_bins': {'low': '8-10', 'moderate': '5-7', 'high': '0-4'},
                },
                'extraction_fields': ['author_year', 'title', 'country', 'study_design', 'sample_size', 'population', 'context', 'methodology', 'key_findings', 'limitations'],
            }

        if stage_payload_key == 'study_selection_payload':
            return {
                **common,
                'prisma_counts': prisma,
                'scopus_retrieved': prisma.get('scopus_retrieved'),
                'after_dedup': prisma.get('after_dedup'),
                'passed_ta': prisma.get('passed_ta'),
                'pdfs_retrieved': prisma.get('pdfs_retrieved'),
                'abstract_only': prisma.get('abstract_only'),
                'passed_fulltext': prisma.get('passed_fulltext'),
                'user_excluded': prisma.get('user_excluded'),
                'final_included': prisma.get('final_included'),
            }

        if stage_payload_key == 'study_characteristics_payload':
            return {**common, 'by_design': subgroups.get('by_design', {}), 'by_country': subgroups.get('by_country', {}), 'by_year': subgroups.get('by_year', {})}

        if stage_payload_key == 'tccm_payload':
            tccm_summary = scaffold.get('tccm_summary', {}) if isinstance(scaffold.get('tccm_summary', {}), dict) else {}
            theory_dimension = tccm_summary.get('theory_dimension', {}) if isinstance(tccm_summary.get('theory_dimension', {}), dict) else {}
            characteristics_dimension = tccm_summary.get('characteristics_dimension', {}) if isinstance(tccm_summary.get('characteristics_dimension', {}), dict) else {}
            context_dimension = tccm_summary.get('context_dimension', {}) if isinstance(tccm_summary.get('context_dimension', {}), dict) else {}
            methods_dimension = tccm_summary.get('methods_dimension', {}) if isinstance(tccm_summary.get('methods_dimension', {}), dict) else {}
            return {
                **common,
                'tccm_summary_json': json.dumps(tccm_summary, ensure_ascii=False, indent=2),
                'theory_narrative': str(theory_dimension.get('theory_narrative') or ''),
                'characteristics_narrative': str(characteristics_dimension.get('characteristics_narrative') or ''),
                'context_narrative': str(context_dimension.get('context_narrative') or ''),
                'methods_narrative': str(methods_dimension.get('methods_narrative') or ''),
            }

        if stage_payload_key == 'quality_results_payload':
            return {**common, 'quality_summary': quality_summary}

        if stage_payload_key == 'bibliometric_payload':
            return {**common, 'cluster_names': [t.theme_name_locked for t in themes], 'theme_count': len(themes), 'themes': [{'theme_name': t.theme_name_locked, 'evidence_grade': t.evidence_grade} for t in themes]}

        if stage_payload_key == 'themes_payload':
            all_reconciled = [{'theme_name': t.theme_name_locked, 'evidence_grade': t.evidence_grade, 'paper_count': t.paper_count, 'reconciled_text': t.reconciled_text or t.reconciler_notes} for t in themes]
            return {**common, 'theme_count': len(themes), 'all_reconciled_texts_with_theme_names': all_reconciled}

        if stage_payload_key == 'subgroup_payload':
            return {**common, 'subgroup_data': subgroups, 'sensitivity_results': sensitivity_results}

        if stage_payload_key == 'theory_landscape_payload':
            theory_landscape = scaffold.get('theory_landscape', {}) if isinstance(scaffold.get('theory_landscape', {}), dict) else {}
            theoretical_framework = scaffold.get('theoretical_framework', {}) if isinstance(scaffold.get('theoretical_framework', {}), dict) else {}
            consistency_checks = scaffold.get('consistency_checks', {}) if isinstance(scaffold.get('consistency_checks', {}), dict) else {}
            theory_consistency = consistency_checks.get('theory_landscape_vs_tccm', {}) if isinstance(consistency_checks.get('theory_landscape_vs_tccm', {}), dict) else {}
            return {
                **common,
                'primary_lens': str(theoretical_framework.get('primary_lens') or theoretical_framework.get('recommended') or ''),
                'dominant_theory': str(theoretical_framework.get('dominant_theory') or ''),
                'theory_coverage': str(theoretical_framework.get('theory_coverage') or ''),
                'theoretical_gaps': theoretical_framework.get('theoretical_gaps', []) if isinstance(theoretical_framework.get('theoretical_gaps', []), list) else [],
                'theory_frequency': theory_landscape.get('theory_frequency', []) if isinstance(theory_landscape.get('theory_frequency', []), list) else [],
                'theoretical_landscape_summary': str(theory_landscape.get('theoretical_landscape_summary') or ''),
                'theoretical_diversity_score': str(theory_landscape.get('theoretical_diversity_score') or ''),
                'theory_usage_pattern': str(theory_landscape.get('theory_usage_pattern') or ''),
                'theory_consistency_check': theory_consistency,
            }

        if stage_payload_key == 'theoretical_synthesis_payload':
            theoretical_synthesis = get_theoretical_synthesis(scaffold)
            propositions = theoretical_synthesis.get('propositions', [])
            return {
                **common,
                'third_order_synthesis': str(theoretical_synthesis.get('third_order_synthesis') or ''),
                'revised_framework_narrative': str(theoretical_synthesis.get('revised_framework_narrative') or ''),
                'propositions': propositions,
                'theoretical_synthesis': theoretical_synthesis,
            }

        if stage_payload_key == 'discussion_payload':
            theoretical_synthesis = get_theoretical_synthesis(scaffold)
            options = self._options(stage)
            include_conceptual = options.get('include_conceptual_model', True)
            conceptual_model_spec = scaffold.get('conceptual_model_spec', {}) if isinstance(scaffold.get('conceptual_model_spec', {}), dict) else {}
            if not include_conceptual:
                conceptual_model_spec = {}
            conceptual_nodes = {
                'main_outcome': conceptual_model_spec.get('main_outcome', {}),
                'antecedents': conceptual_model_spec.get('antecedents', []),
                'mediators': conceptual_model_spec.get('mediators', []),
                'moderators': conceptual_model_spec.get('moderators', []),
            }
            return {
                **common,
                'primary_term': (scaffold.get('canonical_terms', {}) or {}).get('primary') or 'the core construct',
                'theme_summaries': [{'theme_name': t.theme_name_locked, 'evidence_grade': t.evidence_grade, 'summary': (t.reconciled_text or t.reconciler_notes)[:1800]} for t in themes],
                'primary_lens': str((scaffold.get('theoretical_framework', {}) or {}).get('primary_lens') or ''),
                'third_order_synthesis': str(theoretical_synthesis.get('third_order_synthesis') or ''),
                'propositions': theoretical_synthesis.get('propositions', []),
                'conceptual_model_title': str(conceptual_model_spec.get('model_title') or ''),
                'conceptual_model_narrative': str(scaffold.get('conceptual_model_narrative') or ''),
                'conceptual_model_core_nodes': conceptual_nodes,
                'conceptual_model_relationships': conceptual_model_spec.get('relationships', []),
                'conceptual_model_moderating_relationships': conceptual_model_spec.get('moderating_relationships', []),
            }

        if stage_payload_key == 'conclusion_payload':
            return {
                **common,
                'abstract_only_count': int(prisma.get('abstract_only') or 0),
                'review_limitations': {
                    'grey_literature_not_searched': True,
                    'single_database': 'Scopus only',
                    'language_restriction': 'English',
                    'ai_assisted_risk': True,
                },
                'synthesis_gaps_formatted': self._build_synthesis_gaps(themes),
                'policy_implications_seed': 'Derive from synthesis findings and evidence grades.',
            }

        if stage_payload_key == 'future_research_payload':
            tccm_summary = scaffold.get('tccm_summary', {}) if isinstance(scaffold.get('tccm_summary', {}), dict) else {}
            theory = scaffold.get('theoretical_framework', {}) if isinstance(scaffold.get('theoretical_framework', {}), dict) else {}
            theoretical_synthesis = get_theoretical_synthesis(scaffold)
            synthesis_gaps = self._build_synthesis_gaps(themes)
            return {
                **common,
                'synthesis_gaps_formatted': synthesis_gaps,
                'theoretical_gaps_or_omit': theory.get('theoretical_gaps', []) if isinstance(theory.get('theoretical_gaps', []), list) else [],
                'propositions_or_omit': theoretical_synthesis.get('propositions', []),
                'tccm_future_research': tccm_summary.get('future_research_from_tccm', []) if isinstance(tccm_summary.get('future_research_from_tccm', []), list) else [],
            }

        if stage_payload_key == 'abstract_payload':
            return {**common, 'full_draft': self._compile_draft(stage), 'themes': [{'theme_name': t.theme_name_locked, 'evidence_grade': t.evidence_grade} for t in themes]}

        if stage_payload_key == 'references_payload':
            return {**common, 'paper_registry': paper_registry}

        return common

    def _derive_year_range(self, review_meta):
        start_year = 2010
        end_year = timezone.now().year
        date_range = str(review_meta.get('date_range') or '').strip()
        if '-' in date_range:
            parts = date_range.replace('?', '-').split('-')
            if len(parts) >= 2:
                try:
                    start_year = int(parts[0].strip())
                    end_year = int(parts[1].strip())
                except Exception:
                    pass

        scaffold = get_scaffold_data(self.review)
        try:
            start_year = int(scaffold.get('start_year', start_year))
        except Exception:
            pass
        try:
            end_year = int(scaffold.get('end_year', end_year))
        except Exception:
            pass
        return start_year, end_year

    def _render_references(self, payload):
        rows = payload.get('paper_registry') or []
        lines = []
        for idx, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                continue
            short_ref = str(row.get('short_ref') or '').strip()
            title = str(row.get('title') or '').strip()
            journal = str(row.get('journal') or '').strip()
            year = str(row.get('year') or '').strip()
            doi = str(row.get('doi') or '').strip()
            entry = f'{idx}. {short_ref}. {title}. {journal}. {year}.'
            if doi:
                entry += f' doi:{doi}'
            lines.append(entry.strip())
        return '\n'.join(lines)

    def _assert_no_unresolved_placeholders(self, text, section_key):
        unresolved = sorted(set(re.findall(r'\{([a-zA-Z0-9_+.-]+)\}', text or '')))
        if unresolved:
            raise RuntimeError(
                f'Unresolved placeholders in prompt for {section_key}: {", ".join(unresolved)}'
            )

    def _section_label_block(self, stage, section_key):
        keys = self._active_order(stage=stage)
        if section_key not in keys:
            return 'No prior section labels.'
        idx = keys.index(section_key)
        if idx <= 0:
            return 'No prior section labels.'
        parts = []
        for key in keys[:idx]:
            sec = stage.get('sections', {}).get(key, {}) if isinstance(stage.get('sections', {}), dict) else {}
            name = sec.get('name') or key
            status = sec.get('status') or 'pending'
            parts.append(f'- {name}: {status}')
        return '\n'.join(parts) if parts else 'No prior section labels.'

    def _format_list(self, items):
        if not isinstance(items, list) or not items:
            return ''
        return '\n'.join(f'- {str(x)}' for x in items if str(x).strip())

    def _rq_numbered_list(self, questions):
        if not questions:
            return 'No locked research questions available.'
        out = []
        for idx, q in enumerate(questions, start=1):
            out.append(f'RQ{idx}: {q}')
        return '\n'.join(out)

    def _theme_grades_formatted(self, payload):
        rows = payload.get('all_reconciled_texts_with_theme_names') if isinstance(payload.get('all_reconciled_texts_with_theme_names'), list) else []
        if not rows:
            rows = payload.get('theme_summaries') if isinstance(payload.get('theme_summaries'), list) else []
        if not rows:
            return 'No theme grades available.'
        out = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get('theme_name') or '').strip()
            grade = str(row.get('evidence_grade') or '').strip()
            if name:
                out.append(f'{name}: {grade or "Unknown"}')
        return '\n'.join(out) if out else 'No theme grades available.'

    def _all_reconciled_texts_formatted(self, payload):
        rows = payload.get('all_reconciled_texts_with_theme_names') if isinstance(payload.get('all_reconciled_texts_with_theme_names'), list) else []
        if not rows:
            return 'No reconciled synthesis texts available.'
        out = []
        for idx, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                continue
            name = str(row.get('theme_name') or f'Theme {idx}')
            grade = str(row.get('evidence_grade') or 'Unknown')
            text = str(row.get('reconciled_text') or '').strip()
            out.append(f'[{idx}] {name} ({grade})\n{text}')
        return '\n\n'.join(out)

    def _rq_answers_formatted(self, payload):
        questions = payload.get('research_questions') if isinstance(payload.get('research_questions'), list) else []
        if not questions:
            return 'No RQ answers available.'
        summaries = payload.get('theme_summaries') if isinstance(payload.get('theme_summaries'), list) else []
        evidence = ' '.join(str(x.get('summary') or '') for x in summaries if isinstance(x, dict)).strip()
        answers = []
        for idx, rq in enumerate(questions, start=1):
            answers.append(
                f'RQ{idx}: {rq}\nAnswer summary: '
                f'{(evidence[:260] + "...") if evidence else "Synthesized across included themes."}'
            )
        return '\n\n'.join(answers)

    def _rq_single_answer(self, payload, rq_number):
        questions = payload.get('research_questions') if isinstance(payload.get('research_questions'), list) else []
        if rq_number < 1 or rq_number > len(questions):
            return 'No answer available.'
        summaries = payload.get('theme_summaries') if isinstance(payload.get('theme_summaries'), list) else []
        evidence = ' '.join(str(x.get('summary') or '') for x in summaries if isinstance(x, dict)).strip()
        if evidence:
            return (evidence[:280] + '...') if len(evidence) > 280 else evidence
        return 'Synthesized across included themes.'

    def _rq3_placeholder_block(self, payload):
        rq_count = int(payload.get('rq_count') or 0)
        if rq_count < 3:
            return ''
        rq3 = str(payload.get('rq3_text') or '')
        return (
            f'Paragraph 4 - RQ3 ANSWER (150-200 words): "Regarding RQ3..."\n'
            f'State RQ3 verbatim: {rq3}\n'
            'Provide a direct, evidence-grounded answer from the synthesized findings.'
        )

    def _country_subgroup_note(self, by_country):
        if not isinstance(by_country, dict) or not by_country:
            return 'Country subgroup analysis is constrained by sparse country reporting.'
        if len(by_country.keys()) < 3:
            return 'Country subgroup analysis should be interpreted cautiously due to limited country diversity.'
        return 'Country subgroup analysis is feasible with moderate geographic spread.'

    def _lens_pct_of_corpus(self, primary_lens):
        if not primary_lens:
            return 'N/A'
        included = self.review.papers.filter(full_text_decision='included')
        total = included.count()
        if total == 0:
            return '0'
        matched = 0
        target = primary_lens.casefold()
        for paper in included:
            extraction = paper.full_text_extraction if isinstance(paper.full_text_extraction, dict) else {}
            theories = extraction.get('theoretical_frameworks')
            names = []
            if isinstance(theories, list):
                for row in theories:
                    if isinstance(row, dict):
                        n = str(row.get('theory_name') or '').strip()
                        if n:
                            names.append(n.casefold())
            legacy = str(extraction.get('theory_framework') or '').strip()
            if legacy:
                names.append(legacy.casefold())
            if target in names:
                matched += 1
        pct = round((matched / total) * 100.0, 1) if total else 0.0
        return str(pct)

    def _build_synthesis_gaps(self, themes):
        gaps = []
        for theme in themes:
            grade = str(theme.evidence_grade or '').strip()
            if grade not in {'Insufficient', 'Contested'}:
                continue
            critic = str(theme.critic_notes or '').strip()
            reason = critic[:320] if critic else str(theme.grade_rationale or '').strip()
            gaps.append(
                {
                    'theme_name': theme.theme_name_locked,
                    'grade': grade,
                    'paper_count': int(theme.paper_count or 0),
                    'gap_note': reason,
                }
            )
        return gaps

    def _resolve_prompt_file(self, section_key, options, default_prompt):
        theory_on = bool(options.get('include_theoretical_framework', True))
        tccm_on = bool(options.get('include_tccm', True))
        model_on = bool(options.get('include_conceptual_model', True))
        future_on = bool(options.get('include_future_research', True))
        sensitivity_on = bool(options.get('include_sensitivity', True))

        if section_key == '1_0_introduction':
            return 'phase_23_1_0_introduction_theory_on.md' if theory_on else 'phase_23_1_0_introduction_theory_off.md'

        if section_key == '2_4_data_extraction':
            if theory_on and tccm_on:
                return 'phase_23_2_4_data_extraction_theory_on_tccm_on.md'
            if theory_on and not tccm_on:
                return 'phase_23_2_4_data_extraction_theory_on_tccm_off.md'
            if not theory_on and tccm_on:
                return 'phase_23_2_4_data_extraction_theory_off_tccm_on.md'
            return 'phase_23_2_4_data_extraction_theory_off_tccm_off.md'

        if section_key == '3_5_synthesis_of_themes':
            return 'phase_23_3_5_synthesis_of_themes_theory_on.md' if theory_on else 'phase_23_3_5_synthesis_of_themes_theory_off.md'

        if section_key == '3_6_subgroup_analysis':
            return 'phase_23_3_6_subgroup_analysis_sensitivity_on.md' if sensitivity_on else 'phase_23_3_6_subgroup_analysis_sensitivity_off.md'

        if section_key == '4_0_discussion':
            if theory_on and model_on:
                return 'phase_23_4_0_discussion.md'
            if theory_on and not model_on:
                return 'phase_23_4_0_discussion_theory_on_no_conceptual.md'
            return 'phase_23_4_0_discussion_theory_off_no_conceptual.md'

        if section_key == '6_0_future_research':
            return 'phase_23_6_0_future_research_tccm_on.md' if tccm_on else 'phase_23_6_0_future_research_tccm_off.md'

        if section_key == '5_0_conclusion':
            if theory_on and future_on:
                return 'phase_23_5_0_conclusion_theory_on_future_on.md'
            if not theory_on and future_on:
                return 'phase_23_5_0_conclusion_theory_off_future_on.md'
            if not theory_on and not future_on:
                return 'phase_23_5_0_conclusion_theory_off_future_off.md'
            return 'phase_23_5_0_conclusion_theory_on_future_off.md'

        if section_key == 'abstract':
            if theory_on and tccm_on and model_on:
                return 'phase_23_abstract_all_features_core_on.md'
            return 'phase_23_abstract_light.md'

        return default_prompt

    def _inject_placeholders(self, text, config, stage=None):
        tags = self._effective_placeholder_tags(config=config, stage=stage)
        if not tags:
            return text
        blocks = '\n'.join(tags)
        if blocks in text:
            return text
        return f'{text.strip()}\n\n{blocks}\n'.strip()

    def _previous_section_text(self, stage, section_key):
        keys = self._active_order(stage=stage)
        if section_key not in keys:
            return 'No previous section.'
        idx = keys.index(section_key)
        if idx <= 0:
            return 'No previous section.'
        prev = stage['sections'][keys[idx - 1]].get('text') or ''
        return prev or 'Previous section not available.'

    def _compile_draft(self, stage):
        active_keys = set(self._active_order(stage=stage))
        out = []
        toc_lines = ['## Table of Contents', '']
        for item in SECTION_MAP:
            if item['key'] in active_keys:
                toc_lines.append(f'- {item["name"]}')
        out.append('\n'.join(toc_lines))
        for item in SECTION_MAP:
            if item['key'] not in active_keys:
                continue
            sec = stage['sections'].get(item['key'], {})
            text = (sec.get('text') or '').strip()
            if text:
                out.append(f'## {item["name"]}\n\n{text}')
        return '\n\n'.join(out)

    def _ensure_stage(self):
        self.review.refresh_from_db(fields=['stage_progress'])
        progress = self.review.stage_progress or {}
        stage = progress.get(self.stage_key, {})
        if not isinstance(stage, dict):
            stage = {}

        sections = stage.get('sections', {}) if isinstance(stage.get('sections', {}), dict) else {}
        changed = False
        ordered = OrderedDict()
        for item in SECTION_MAP:
            key = item['key']
            sec = sections.get(key, {}) if isinstance(sections.get(key, {}), dict) else {}
            if not sec:
                changed = True
                sec = {'name': item['name'], 'status': 'pending', 'text': '', 'error': '', 'updated_at': '', 'word_count': 0}
            else:
                sec.setdefault('name', item['name'])
                sec.setdefault('status', 'pending')
                sec.setdefault('text', '')
                sec.setdefault('error', '')
                sec.setdefault('updated_at', '')
                sec.setdefault('word_count', 0)
            ordered[key] = sec

        stage.setdefault('status', 'idle')
        stage.setdefault('stop_requested', False)
        stage.setdefault('current_section_key', '')
        stage.setdefault('logs', [])
        stage.setdefault('error_code', '')
        stage.setdefault('error_message', '')
        stage.setdefault('compiled_draft', '')
        stage.setdefault('options', self._default_options())
        stage['sections'] = ordered
        self._apply_options_to_sections(stage)

        progress[self.stage_key] = stage
        if changed:
            self.review.stage_progress = progress
            self.review.save(update_fields=['stage_progress'])
        return stage

    def _save_stage(self, stage):
        self.review.refresh_from_db(fields=['stage_progress'])
        progress = self.review.stage_progress or {}
        progress[self.stage_key] = stage
        self.review.stage_progress = progress
        self.review.save(update_fields=['stage_progress'])

    def _all_done(self, stage):
        return all((stage['sections'][key].get('status') == 'done') for key in self._active_order(stage=stage))

    def _stop_requested(self):
        self.review.refresh_from_db(fields=['stage_progress'])
        stage = (self.review.stage_progress or {}).get(self.stage_key, {})
        return bool(isinstance(stage, dict) and stage.get('stop_requested'))

    def _log(self, stage, event, message):
        logs = list(stage.get('logs') or [])
        logs.insert(0, {'time': timezone.now().isoformat(), 'event': event, 'message': message})
        stage['logs'] = logs[:300]

    def _word_count(self, text):
        return len([x for x in (text or '').split() if x.strip()])

    def _call_deepseek(self, prompt):
        api_key = getattr(settings, 'DEEPSEEK_API_KEY', '') or os.getenv('DEEPSEEK_API_KEY', '')
        if not api_key:
            raise RuntimeError('DEEPSEEK_API_KEY is not configured.')

        base_url = (getattr(settings, 'DEEPSEEK_BASE_URL', '') or os.getenv('DEEPSEEK_BASE_URL', '') or 'https://api.deepseek.com').rstrip('/')
        timeout_seconds = float(getattr(settings, 'DEEPSEEK_TIMEOUT_SECONDS', 120))

        url = f'{base_url}/chat/completions'
        headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
        payload = {
            'model': self.model_name,
            'messages': [
                {'role': 'system', 'content': 'Return only section text in academic prose. No JSON.'},
                {'role': 'user', 'content': prompt},
            ],
            'temperature': 0.2,
        }

        response = requests.post(url, headers=headers, json=payload, timeout=timeout_seconds)
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
            raise RuntimeError('DeepSeek returned empty ghostwriter content.')
        return text

    def _default_options(self):
        return {
            'include_theoretical_framework': True,
            'include_conceptual_model': True,
            'include_tccm': True,
            'include_future_research': True,
            'include_sensitivity': True,
        }

    def _options(self, stage):
        defaults = self._default_options()
        raw = stage.get('options', {}) if isinstance(stage.get('options', {}), dict) else {}
        merged = dict(defaults)
        for key in defaults:
            if key in raw:
                merged[key] = bool(raw.get(key))
        if merged.get('include_conceptual_model', True) and not merged.get('include_theoretical_framework', True):
            merged['include_theoretical_framework'] = True
        return merged

    def _active_order(self, stage):
        options = self._options(stage)
        order = [s['key'] for s in SECTION_MAP]
        if not options.get('include_theoretical_framework', True):
            order = [k for k in order if k not in {'3_7_theory_landscape', '3_8_theoretical_synthesis'}]
        if not options.get('include_tccm', True):
            order = [k for k in order if k != '3_2b_tccm_analysis']
        if not options.get('include_future_research', True):
            order = [k for k in order if k != '6_0_future_research']
        return order

    def _apply_options_to_sections(self, stage):
        options = self._options(stage)
        sections = stage.get('sections', {}) if isinstance(stage.get('sections', {}), dict) else {}
        theory_keys = {'3_7_theory_landscape', '3_8_theoretical_synthesis'}
        tccm_key = '3_2b_tccm_analysis'
        for key in theory_keys:
            if key in sections:
                sec = sections[key]
                if not options.get('include_theoretical_framework', True):
                    if sec.get('status') in {'pending', 'skipped'}:
                        sec['status'] = 'skipped'
                else:
                    if sec.get('status') == 'skipped':
                        sec['status'] = 'pending'
        if tccm_key in sections:
            sec = sections[tccm_key]
            if not options.get('include_tccm', True):
                if sec.get('status') in {'pending', 'skipped'}:
                    sec['status'] = 'skipped'
            else:
                if sec.get('status') == 'skipped':
                    sec['status'] = 'pending'

        future_key = '6_0_future_research'
        if future_key in sections:
            sec = sections[future_key]
            if not options.get('include_future_research', True):
                if sec.get('status') in {'pending', 'skipped'}:
                    sec['status'] = 'skipped'
            else:
                if sec.get('status') == 'skipped':
                    sec['status'] = 'pending'

    def _effective_placeholder_tags(self, config, stage):
        tags = list(config.get('placeholder_tags') or [])
        if not tags:
            return tags
        options = self._options(stage or {})
        if config.get('key') == '4_0_discussion' and not options.get('include_conceptual_model', True):
            tags = [tag for tag in tags if 'CONCEPTUAL MODEL' not in tag.upper()]
        if config.get('key') == '3_2b_tccm_analysis' and not options.get('include_tccm', True):
            return []
        if config.get('key') == '3_6_subgroup_analysis' and not options.get('include_sensitivity', True):
            tags = [tag for tag in tags if 'SENSITIVITY' not in tag.upper()]
        return tags

    def _preflight_validate(self, stage, options):
        scaffold = get_scaffold_data(self.review)
        errors = []
        if options.get('include_conceptual_model', True) and not options.get('include_theoretical_framework', True):
            errors.append('Conceptual Model requires Theoretical Framework Anchoring. Enable theory option first.')

        rq_count = self.review.research_questions.exclude(question_text='').count()
        if rq_count == 0:
            errors.append('No research questions found. Confirm Phase 2 before running Ghostwriter.')

        theme_count = self.review.theme_syntheses.count()
        if theme_count == 0:
            errors.append('No theme syntheses found. Run theme synthesis and dialectical phases first.')

        if options.get('include_theoretical_framework', True):
            tf = scaffold.get('theoretical_framework', {}) if isinstance(scaffold.get('theoretical_framework', {}), dict) else {}
            if not tf:
                errors.append('Missing scaffold_data.theoretical_framework (run Part 1 Theory Landscape).')
            else:
                tf_status = str(tf.get('status') or '').strip().lower()
                primary_lens = str(tf.get('primary_lens') or '').strip()
                if tf_status != 'confirmed' or not primary_lens:
                    errors.append('Theoretical framework is not confirmed (confirm selected primary lens in Part 1).')

            if not (isinstance(scaffold.get('theory_landscape', {}), dict) and scaffold.get('theory_landscape')):
                errors.append('Missing scaffold_data.theory_landscape (run Part 1 Theory Landscape).')

            ts = get_theoretical_synthesis(scaffold)
            propositions = ts.get('propositions', [])
            third_order = str(ts.get('third_order_synthesis') or '').strip()
            if not ts and not propositions and not third_order:
                errors.append('Missing theoretical synthesis inputs (run Part 1 Cross-Theme Theoretical Synthesis).')

        if options.get('include_conceptual_model', True):
            cms = scaffold.get('conceptual_model_spec', {}) if isinstance(scaffold.get('conceptual_model_spec', {}), dict) else {}
            if not cms:
                errors.append('Missing scaffold_data.conceptual_model_spec (run Part 2 Conceptual Model Spec).')

        if options.get('include_tccm', True):
            tccm = scaffold.get('tccm_summary', {}) if isinstance(scaffold.get('tccm_summary', {}), dict) else {}
            if not tccm:
                errors.append('Missing scaffold_data.tccm_summary (run Part 3 TCCM Aggregation).')

        if options.get('include_sensitivity', True):
            sensitivity = scaffold.get('sensitivity_results', {}) if isinstance(scaffold.get('sensitivity_results', {}), dict) else {}
            if not sensitivity:
                try:
                    get_or_compute_sensitivity_results(self.review)
                except Exception as exc:
                    errors.append(f'Sensitivity computation failed: {exc}')

        if errors:
            raise RuntimeError('Ghostwriter preflight failed:\n- ' + '\n- '.join(errors))


def run_ghostwriter(review_id, mode='next', section_key=None, retry=False):
    return GhostwriterService(review_id=review_id).run(mode=mode, section_key=section_key, retry=retry)
