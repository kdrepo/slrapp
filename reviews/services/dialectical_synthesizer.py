import json
import os

import requests
from django.conf import settings
from django.utils import timezone

from reviews.models import Review
from reviews.services.prompt_loader import render_prompt_template
from reviews.services.scaffold_service import get_scaffold_preamble


ADVOCATE_PROMPT_FALLBACK = """{scaffold_preamble}
TASK: You are the ADVOCATE for the theme: {theme_name}.
EVIDENCE GRADE: {evidence_grade}
DATA: {theme_extractions_json}
Build the strongest possible case FOR this theme being established in the literature.
- Cite papers by short_ref.
- Apply evidence language rules from scaffold.
- Focus on convergent findings and strong evidence.
- Write 300-400 words of continuous academic prose.
DO NOT use bullet points or headers.
""".strip()

CRITIC_PROMPT_FALLBACK = """{scaffold_preamble}
TASK: You are the CRITIC reviewing this Advocate position:
ADVOCATE TEXT: {advocate_text}
DATA: {theme_extractions_json}
Identify legitimate weaknesses in the Advocate's argument:
- Methodological flaws or risk of bias.
- Conflicting findings or outliers.
- Geographic or temporal limitations.
Write 250-350 words. No bullet points.
""".strip()

RECONCILER_PROMPT_FALLBACK = """{scaffold_preamble}
TASK: You are the RECONCILER. Write the final synthesis for: {theme_name}.
ADVOCATE VIEW: {advocate_text}
CRITIC VIEW: {critic_text}
DATA: {theme_extractions_json}
Write the final synthesis paragraph (500-600 words).
- Start with declarative sentence on state of evidence.
- Synthesize advocate evidence and critic qualifications.
- Explain contradictions by context.
- Ensure claims are cited by short_ref.
- End with implications for overall review.
No bullet points or headers.
""".strip()

THIN_THEME_PROMPT_FALLBACK = """{scaffold_preamble}
TASK: Write a brief synthesis note for a theme with limited evidence: {theme_name}.
DATA: {theme_extractions_json}
Acknowledge limited evidence explicitly. Identify as research gap requiring further investigation.
Use the phrase 'preliminary evidence suggests'.
Write 120-180 words. No bullet points.
""".strip()

TEXT_CORRECTION_PROMPT_FALLBACK = """The previous output violated formatting requirements.
Rewrite it as continuous academic prose with NO bullet points, NO numbering, and NO headers.
Keep meaning intact and keep length near {target_words} words.
Return plain text only.

Previous output:
---
{raw_text}
---
""".strip()


class DialecticalStopRequested(Exception):
    pass


class DialecticalSynthesizer:
    def __init__(self, review_id):
        self.review = Review.objects.get(pk=review_id)
        self.model_name = (
            getattr(settings, 'DEEPSEEK_DIALECTICAL_MODEL', '')
            or os.getenv('DEEPSEEK_DIALECTICAL_MODEL', '')
            or 'deepseek-reasoner'
        )
        scaffold_data = self.review.scaffold_data if isinstance(self.review.scaffold_data, dict) else {}
        theoretical_framework = scaffold_data.get('theoretical_framework', {}) if isinstance(scaffold_data.get('theoretical_framework'), dict) else {}
        self.primary_lens = (
            str(
                theoretical_framework.get('primary_lens')
                or theoretical_framework.get('recommended')
                or 'the primary theoretical lens'
            )
        )

    def run(self):
        stage = self.review.stage_progress or {}
        stage['phase_18'] = 'running'
        self.review.stage_progress = stage
        self.review.save(update_fields=['stage_progress'])

        updated = 0
        failed = 0
        for theme in self.review.theme_syntheses.all().order_by('order_index', 'id'):
            self._check_stop_requested()
            try:
                self._process_theme(theme)
                updated += 1
            except DialecticalStopRequested:
                return {'updated': updated, 'failed': failed, 'stopped': True}
            except Exception as exc:
                failed += 1
                theme.reconciler_notes = f'Phase 18 error: {exc}'
                theme.save(update_fields=['reconciler_notes'])

        stage = self.review.stage_progress or {}
        stage['phase_18'] = 'done' if failed == 0 else 'done_with_errors'
        stage['phase_18_updated'] = updated
        stage['phase_18_failed'] = failed
        stage['phase_18_finished_at'] = timezone.now().isoformat()
        self.review.stage_progress = stage
        self.review.save(update_fields=['stage_progress'])
        return {'updated': updated, 'failed': failed, 'stopped': False}

    def _process_theme(self, theme):
        self._check_stop_requested()
        extractions = self._theme_extractions(theme)
        extraction_json = json.dumps(extractions, ensure_ascii=False, indent=2)
        scaffold_preamble = get_scaffold_preamble(self.review)

        is_insufficient = (theme.evidence_grade or '').strip().lower() == 'insufficient'
        thin_theme = is_insufficient and (theme.paper_count or theme.papers.count()) < 5

        if thin_theme:
            self._check_stop_requested()
            thin_text = self._run_single_pass(
                template='phase_18_thin_theme.md',
                fallback=THIN_THEME_PROMPT_FALLBACK,
                context={
                    'scaffold_preamble': scaffold_preamble,
                    'theme_name': theme.theme_name_locked,
                    'theme_extractions_json': extraction_json,
                },
                target_words=150,
            )
            theme.advocate_notes = ''
            theme.critic_notes = ''
            theme.reconciler_notes = thin_text
            theme.reconciled_text = thin_text
            theme.save(update_fields=['advocate_notes', 'critic_notes', 'reconciler_notes', 'reconciled_text'])
            return

        self._check_stop_requested()
        advocate_text = self._run_single_pass(
            template='phase_18_advocate.md',
            fallback=ADVOCATE_PROMPT_FALLBACK,
            context={
                'scaffold_preamble': scaffold_preamble,
                'theme_name': theme.theme_name_locked,
                'evidence_grade': theme.evidence_grade,
                'theme_extractions_json': extraction_json,
            },
            target_words=350,
        )

        self._check_stop_requested()
        critic_text = self._run_single_pass(
            template='phase_18_critic.md',
            fallback=CRITIC_PROMPT_FALLBACK,
            context={
                'scaffold_preamble': scaffold_preamble,
                'advocate_text': advocate_text,
                'theme_extractions_json': extraction_json,
            },
            target_words=300,
        )

        self._check_stop_requested()
        reconciled_text = self._run_single_pass(
            template='phase_18_reconciler.md',
            fallback=RECONCILER_PROMPT_FALLBACK,
            context={
                'scaffold_preamble': scaffold_preamble,
                'theme_name': theme.theme_name_locked,
                'advocate_text': advocate_text,
                'critic_text': critic_text,
                'theme_extractions_json': extraction_json,
                'primary_lens': self.primary_lens,
            },
            target_words=550,
        )

        theme.advocate_notes = advocate_text
        theme.critic_notes = critic_text
        theme.reconciler_notes = reconciled_text
        theme.reconciled_text = reconciled_text
        theme.save(update_fields=['advocate_notes', 'critic_notes', 'reconciler_notes', 'reconciled_text'])

    def _run_single_pass(self, template, fallback, context, target_words):
        self._check_stop_requested()
        prompt = render_prompt_template(template, context=context, fallback=fallback)
        text = self._call_deepseek(prompt)
        self._check_stop_requested()

        if self._invalid_text(text):
            correction_prompt = render_prompt_template(
                'phase_18_text_correction.md',
                context={
                    'raw_text': text,
                    'target_words': target_words,
                },
                fallback=TEXT_CORRECTION_PROMPT_FALLBACK,
            )
            text = self._call_deepseek(correction_prompt)

        if self._invalid_text(text):
            raise RuntimeError('Text output failed formatting (no-bullets rule) after correction pass.')
        return text

    def _theme_extractions(self, theme):
        items = []
        for paper in theme.papers.all().order_by('id'):
            ext = paper.full_text_extraction if isinstance(paper.full_text_extraction, dict) else {}
            qual = paper.full_text_quality if isinstance(paper.full_text_quality, dict) else {}
            items.append(
                {
                    'paper_id': paper.id,
                    'short_ref': self._short_ref(paper, ext),
                    'title': paper.title,
                    'year': paper.publication_year,
                    'study_design': ext.get('study_design') or '',
                    'country': ext.get('country') or '',
                    'key_findings': ext.get('key_findings') or '',
                    'limitations': ext.get('limitations') or '',
                    'quality': qual,
                }
            )
        return items

    def _short_ref(self, paper, ext):
        ay = str(ext.get('author_year') or '').strip()
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

    def _check_stop_requested(self):
        latest = Review.objects.only('stage_progress').get(pk=self.review.pk)
        stage = (latest.stage_progress or {}).get('phase_18_dialectical', {})
        if isinstance(stage, dict) and stage.get('stop_requested'):
            raise DialecticalStopRequested('Stop requested by user.')

    def _invalid_text(self, text):
        t = (text or '').strip()
        if not t:
            return True

        for raw_line in t.splitlines():
            line = raw_line.lstrip()
            if not line:
                continue
            if line.startswith('- ') or line.startswith('* '):
                return True

            idx = 0
            while idx < len(line) and line[idx].isdigit():
                idx += 1
            if idx > 0 and idx < len(line) and line[idx] in {'.', ')'}:
                if idx + 1 < len(line) and line[idx + 1].isspace():
                    return True

        return False

    def _call_deepseek(self, prompt):
        api_key = getattr(settings, 'DEEPSEEK_API_KEY', '') or os.getenv('DEEPSEEK_API_KEY', '')
        if not api_key:
            raise RuntimeError('DEEPSEEK_API_KEY is not configured.')

        base_url = (
            getattr(settings, 'DEEPSEEK_BASE_URL', '')
            or os.getenv('DEEPSEEK_BASE_URL', '')
            or 'https://api.deepseek.com'
        ).rstrip('/')
        timeout_seconds = float(getattr(settings, 'DEEPSEEK_TIMEOUT_SECONDS', 90))

        url = f'{base_url}/chat/completions'
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }
        payload = {
            'model': self.model_name,
            'messages': [
                {'role': 'system', 'content': 'Return only plain academic prose text.'},
                {'role': 'user', 'content': prompt},
            ],
            'temperature': 0.2,
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
            raise RuntimeError('DeepSeek returned empty dialectical synthesis content.')
        return text


def run_dialectical_synthesis(review_id):
    return DialecticalSynthesizer(review_id=review_id).run()
