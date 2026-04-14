import json
import os
from collections import OrderedDict

import requests
from django.conf import settings
from django.utils import timezone

from reviews.models import Review
from reviews.services.prompt_loader import render_prompt_template
from reviews.services.scaffold_service import get_scaffold_data, get_scaffold_preamble


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
    {'key': '3_3_quality_assessment_results', 'name': '3.3 Quality Assessment', 'prompt': 'phase_23_3_3_quality_results.md', 'include_registry': True, 'payload': 'quality_results_payload', 'placeholder_tags': ['[INSERT TABLE 4: QUALITY ASSESSMENT SUMMARY]', '[INSERT FIGURE 2: RISK OF BIAS CHART]']},
    {'key': '3_4_bibliometric_findings', 'name': '3.4 Bibliometric Findings', 'prompt': 'phase_23_3_4_bibliometric_findings.md', 'include_registry': True, 'payload': 'bibliometric_payload', 'placeholder_tags': ['[INSERT FIGURE 3: BIBLIOMETRIC OVERVIEW]']},
    {'key': '3_5_synthesis_of_themes', 'name': '3.5 Synthesis of Findings', 'prompt': 'phase_23_3_5_synthesis_of_themes.md', 'include_registry': True, 'payload': 'themes_payload', 'placeholder_tags': ['[INSERT FIGURE 4: THEME FREQUENCY]', '[INSERT FIGURE 5: EVIDENCE HEATMAP]']},
    {'key': '3_6_subgroup_analysis', 'name': '3.6 Subgroup Analysis', 'prompt': 'phase_23_3_6_subgroup_analysis.md', 'include_registry': True, 'payload': 'subgroup_payload', 'placeholder_tags': ['[INSERT FIGURE 6: SUBGROUP ANALYSIS PANELS]']},
    {'key': '4_0_discussion', 'name': '4.0 Discussion', 'prompt': 'phase_23_4_0_discussion.md', 'include_registry': True, 'payload': 'discussion_payload', 'placeholder_tags': []},
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
        order = [s['key'] for s in SECTION_MAP]
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

        if config.get('non_llm'):
            return self._inject_placeholders(self._render_references(payload), config)

        previous_text = self._previous_section_text(stage, section_key)
        scaffold_preamble = get_scaffold_preamble(
            self.review,
            previous_sections_labelled='',
            include_registry=bool(config.get('include_registry', True)),
        )
        section_instructions = render_prompt_template(config['prompt'], fallback=SECTION_INSTRUCTION_FALLBACK)

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
        return self._inject_placeholders(self._call_deepseek(prompt), config)

    def _build_payload(self, stage_payload_key, stage):
        scaffold = get_scaffold_data(self.review)
        prisma = scaffold.get('prisma_counts', {}) if isinstance(scaffold.get('prisma_counts', {}), dict) else {}
        review_meta = scaffold.get('review_metadata', {}) if isinstance(scaffold.get('review_metadata', {}), dict) else {}
        subgroups = scaffold.get('subgroup_data', {}) if isinstance(scaffold.get('subgroup_data', {}), dict) else {}
        quality_summary = scaffold.get('quality_summary', {}) if isinstance(scaffold.get('quality_summary', {}), dict) else {}
        paper_registry = scaffold.get('paper_registry', []) if isinstance(scaffold.get('paper_registry', []), list) else []

        rqs = [q.question_text for q in self.review.research_questions.order_by('id') if (q.question_text or '').strip()]
        rq_map = {f'rq{idx + 1}_text': text for idx, text in enumerate(rqs)}
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

        if stage_payload_key == 'quality_results_payload':
            return {**common, 'quality_summary': quality_summary}

        if stage_payload_key == 'bibliometric_payload':
            return {**common, 'cluster_names': [t.theme_name_locked for t in themes], 'theme_count': len(themes), 'themes': [{'theme_name': t.theme_name_locked, 'evidence_grade': t.evidence_grade} for t in themes]}

        if stage_payload_key == 'themes_payload':
            all_reconciled = [{'theme_name': t.theme_name_locked, 'evidence_grade': t.evidence_grade, 'paper_count': t.paper_count, 'reconciled_text': t.reconciled_text or t.reconciler_notes} for t in themes]
            return {**common, 'theme_count': len(themes), 'all_reconciled_texts_with_theme_names': all_reconciled}

        if stage_payload_key == 'subgroup_payload':
            return {**common, 'subgroup_data': subgroups}

        if stage_payload_key == 'discussion_payload':
            return {
                **common,
                'primary_term': (scaffold.get('canonical_terms', {}) or {}).get('primary') or 'the core construct',
                'theme_summaries': [{'theme_name': t.theme_name_locked, 'evidence_grade': t.evidence_grade, 'summary': (t.reconciled_text or t.reconciler_notes)[:1800]} for t in themes],
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
                'policy_implications_seed': 'Derive from synthesis findings and evidence grades.',
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

    def _inject_placeholders(self, text, config):
        tags = config.get('placeholder_tags') or []
        if not tags:
            return text
        blocks = '\n'.join(tags)
        if blocks in text:
            return text
        return f'{text.strip()}\n\n{blocks}\n'.strip()

    def _previous_section_text(self, stage, section_key):
        keys = [s['key'] for s in SECTION_MAP]
        idx = keys.index(section_key)
        if idx <= 0:
            return 'No previous section.'
        prev = stage['sections'][keys[idx - 1]].get('text') or ''
        return prev or 'Previous section not available.'

    def _compile_draft(self, stage):
        out = []
        for item in SECTION_MAP:
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
        stage['sections'] = ordered

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
        return all((stage['sections'][s['key']].get('status') == 'done') for s in SECTION_MAP)

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


def run_ghostwriter(review_id, mode='next', section_key=None, retry=False):
    return GhostwriterService(review_id=review_id).run(mode=mode, section_key=section_key, retry=retry)
