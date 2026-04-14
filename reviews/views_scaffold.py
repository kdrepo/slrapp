import json
from collections import Counter, defaultdict
from statistics import mean

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from .models import Paper, Review
from .services.prompt_templates import SCAFFOLD_PREAMBLE_TEMPLATE
from .services.design_canonicalizer import canonicalize_study_design
from .services.scaffold_service import (
    get_scaffold_data,
    set_scaffold_data,
)


class ScaffoldEditorView(View):
    template_name = 'reviews/scaffold_editor.html'

    ACTION_POPULATORS = {
        'populate_research_questions': 'research_questions',
        'populate_pico': 'pico',
        'populate_paper_registry': 'paper_registry',
        'populate_quality_summary': 'quality_summary',
        'populate_subgroup_data': 'subgroup_data',
        'populate_review_metadata': 'review_metadata',
    }

    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        scaffold_data = get_scaffold_data(review)
        entries = self._entries_from_scaffold(scaffold_data)
        return render(
            request,
            self.template_name,
            {
                'review': review,
                'entries': entries,
                'preamble_text': review.scaffold_preamble_template or '',
                'errors': [],
            },
        )

    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        action = (request.POST.get('action') or 'save').strip().lower()

        if action == 'recalculate_prisma':
            self._recalculate_prisma_counts(review)
            messages.success(request, 'Final PRISMA counts recalculated and saved to scaffold_data.')
            return redirect(reverse('reviews:scaffold-editor', kwargs={'pk': review.pk}))

        if action == 'populate_all_now':
            self._populate_all_now(review)
            messages.success(request, 'Added all scaffold_data components available from existing data.')
            return redirect(reverse('reviews:scaffold-editor', kwargs={'pk': review.pk}))

        if action == 'generate_preamble':
            review.scaffold_preamble_template = SCAFFOLD_PREAMBLE_TEMPLATE
            review.save(update_fields=['scaffold_preamble_template'])
            messages.success(request, 'scaffold_preamble_template reset to template placeholders.')
            return redirect(reverse('reviews:scaffold-editor', kwargs={'pk': review.pk}))

        if action in self.ACTION_POPULATORS:
            key = self.ACTION_POPULATORS[action]
            self._populate_single(review, key)
            messages.success(request, f'Added/updated scaffold_data.{key} from existing data.')
            return redirect(reverse('reviews:scaffold-editor', kwargs={'pk': review.pk}))

        errors = []
        entry_count = self._safe_int(request.POST.get('entry_count'), 0)
        scaffold_data = {}
        entries = []

        for index in range(entry_count):
            key = (request.POST.get(f'key_{index}') or '').strip()
            value_raw = (request.POST.get(f'value_{index}') or '').strip()
            if not key:
                continue

            entries.append({'key': key, 'value_raw': value_raw})
            try:
                scaffold_data[key] = json.loads(value_raw)
            except json.JSONDecodeError as exc:
                errors.append(f'Invalid JSON for "{key}" ({exc.msg}).')

        new_key = (request.POST.get('new_key') or '').strip()
        new_value_raw = (request.POST.get('new_value') or '').strip()
        if new_key:
            entries.append({'key': new_key, 'value_raw': new_value_raw})
            if new_key in scaffold_data:
                errors.append(f'Duplicate key "{new_key}" was submitted.')
            else:
                try:
                    scaffold_data[new_key] = json.loads(new_value_raw)
                except json.JSONDecodeError as exc:
                    errors.append(f'Invalid JSON for new key "{new_key}" ({exc.msg}).')

        preamble_text = (request.POST.get('scaffold_preamble_template') or '').strip()

        if errors:
            messages.error(request, 'Scaffold update failed. Please fix JSON errors and retry.')
            return render(
                request,
                self.template_name,
                {
                    'review': review,
                    'entries': entries,
                    'preamble_text': preamble_text,
                    'errors': errors,
                },
                status=400,
            )

        set_scaffold_data(review, scaffold_data)
        review.scaffold_preamble_template = preamble_text
        review.save(update_fields=['scaffold_data', 'scaffold_preamble_template'])
        messages.success(request, 'Scaffold data and preamble template updated successfully.')
        return redirect(reverse('reviews:scaffold-editor', kwargs={'pk': review.pk}))

    def _entries_from_scaffold(self, scaffold):
        entries = []
        for key, value in scaffold.items():
            entries.append(
                {
                    'key': key,
                    'value_raw': json.dumps(value, indent=2, ensure_ascii=False),
                }
            )
        return entries

    def _safe_int(self, value, fallback):
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    def _populate_single(self, review, key):
        scaffold_data = get_scaffold_data(review)

        if key == 'research_questions':
            scaffold_data[key] = self._build_research_questions(review)
        elif key == 'pico':
            scaffold_data[key] = self._build_pico(review)
        elif key == 'paper_registry':
            scaffold_data[key] = self._build_paper_registry(review)
        elif key == 'quality_summary':
            scaffold_data[key] = self._build_quality_summary(review)
        elif key == 'subgroup_data':
            scaffold_data[key] = self._build_subgroup_data(review)
        elif key == 'review_metadata':
            scaffold_data[key] = self._build_review_metadata(review, scaffold_data)

        set_scaffold_data(review, scaffold_data)
        review.save(update_fields=['scaffold_data'])

    def _populate_all_now(self, review):
        scaffold_data = get_scaffold_data(review)

        scaffold_data['research_questions'] = self._build_research_questions(review)
        scaffold_data['pico'] = self._build_pico(review)
        scaffold_data['paper_registry'] = self._build_paper_registry(review)
        scaffold_data['quality_summary'] = self._build_quality_summary(review)
        scaffold_data['subgroup_data'] = self._build_subgroup_data(review)
        scaffold_data['review_metadata'] = self._build_review_metadata(review, scaffold_data)

        set_scaffold_data(review, scaffold_data)
        review.save(update_fields=['scaffold_data'])

    def _build_research_questions(self, review):
        questions = [q.question_text.strip() for q in review.research_questions.order_by('id') if q.question_text.strip()]
        if questions:
            return questions

        phase_2 = get_scaffold_data(review).get('phase_2', {})
        legacy = phase_2.get('research_questions', []) if isinstance(phase_2, dict) else []
        out = []
        for item in legacy:
            if isinstance(item, dict):
                text = str(item.get('rq') or '').strip()
                if text:
                    out.append(text)
            elif isinstance(item, str) and item.strip():
                out.append(item.strip())
        return out

    def _build_pico(self, review):
        return {
            'population': review.pico_population or '',
            'intervention': review.pico_intervention or '',
            'comparison': review.pico_comparison or '',
            'outcomes': review.pico_outcomes or '',
        }

    def _build_paper_registry(self, review):
        papers = review.papers.filter(full_text_decision=Paper.FullTextDecision.INCLUDED).order_by('id')
        registry = []
        for paper in papers:
            short_ref = self._paper_short_ref(paper)
            registry.append(
                {
                    'paper_id': paper.id,
                    'scopus_id': paper.scopus_id or '',
                    'short_ref': short_ref,
                    'year': paper.publication_year,
                    'title': paper.title or '',
                    'journal': paper.journal or '',
                    'doi': paper.doi or '',
                }
            )
        return registry

    def _paper_short_ref(self, paper):
        ext = paper.full_text_extraction or {}
        if isinstance(ext, dict):
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

    def _build_quality_summary(self, review):
        papers = review.papers.filter(full_text_decision=Paper.FullTextDecision.INCLUDED)
        scores = []
        risk_counts = Counter()
        design_scores = defaultdict(list)

        for paper in papers:
            quality = paper.full_text_quality if isinstance(paper.full_text_quality, dict) else {}
            extraction = paper.full_text_extraction if isinstance(paper.full_text_extraction, dict) else {}

            total_score = quality.get('total_score')
            if isinstance(total_score, (int, float)):
                scores.append(float(total_score))

            risk = str(quality.get('risk_of_bias') or '').strip().lower()
            if risk in ('low', 'moderate', 'high'):
                risk_counts[risk] += 1

            design = canonicalize_study_design(str(extraction.get('study_design_canonical') or extraction.get('study_design') or quality.get('study_type') or 'unknown').strip() or 'unknown')
            if isinstance(total_score, (int, float)):
                design_scores[design].append(float(total_score))

        by_design = {}
        for design, vals in design_scores.items():
            if vals:
                by_design[design] = {'mean': round(mean(vals), 2), 'count': len(vals)}

        if scores:
            score_range = f'{int(min(scores))}-{int(max(scores))}'
            mean_score = round(mean(scores), 2)
        else:
            score_range = ''
            mean_score = 0

        return {
            'mean_score': mean_score,
            'score_range': score_range,
            'low_risk': int(risk_counts.get('low', 0)),
            'moderate_risk': int(risk_counts.get('moderate', 0)),
            'high_risk': int(risk_counts.get('high', 0)),
            'by_design': by_design,
        }

    def _build_subgroup_data(self, review):
        papers = review.papers.filter(full_text_decision=Paper.FullTextDecision.INCLUDED)

        by_design = Counter()
        by_country = Counter()
        by_year = Counter()

        for paper in papers:
            extraction = paper.full_text_extraction if isinstance(paper.full_text_extraction, dict) else {}
            design = canonicalize_study_design(str(extraction.get('study_design_canonical') or extraction.get('study_design') or 'unknown').strip() or 'unknown')
            country = str(extraction.get('country') or 'unknown').strip() or 'unknown'
            by_design[design] += 1
            by_country[country] += 1
            if paper.publication_year:
                by_year[int(paper.publication_year)] += 1

        sorted_years = dict(sorted(by_year.items(), key=lambda x: x[0]))
        year_keys = list(sorted_years.keys())
        year_span = (max(year_keys) - min(year_keys)) if len(year_keys) >= 2 else 0
        years_with_three_or_more = sum(1 for _, c in sorted_years.items() if c >= 3)

        return {
            'by_design': dict(by_design),
            'by_country': dict(by_country),
            'by_year': sorted_years,
            'year_span': year_span,
            'sankey_eligible': year_span >= 10,
            'year_subgroup_eligible': years_with_three_or_more >= 3,
        }

    def _build_review_metadata(self, review, scaffold_data):
        papers = review.papers.filter(full_text_decision=Paper.FullTextDecision.INCLUDED)
        years = [p.publication_year for p in papers if p.publication_year]
        date_range = ''
        if years:
            date_range = f'{min(years)}-{max(years)}'

        existing = scaffold_data.get('review_metadata', {}) if isinstance(scaffold_data, dict) else {}
        prospero_number = ''
        if isinstance(existing, dict):
            prospero_number = str(existing.get('prospero_number') or '').strip()

        return {
            'title': review.title,
            'date_completed': timezone.now().date().isoformat(),
            'date_range': date_range,
            'language': 'English',
            'database': 'Scopus',
            'query_count': review.search_queries.count(),
            'prospero_number': prospero_number,
        }

    def _recalculate_prisma_counts(self, review):
        papers = review.papers.all()
        total_papers = papers.count()

        ta_included = papers.filter(ta_decision=Paper.TADecision.INCLUDED).count()
        fulltext_assessed = papers.filter(fulltext_retrieved=True).count()
        fulltext_included = papers.filter(full_text_decision=Paper.FullTextDecision.INCLUDED).count()

        screening_excluded = max(total_papers - ta_included, 0)
        fulltext_excluded = max(fulltext_assessed - fulltext_included, 0)

        scaffold_data = get_scaffold_data(review)
        prisma_counts = scaffold_data.get('prisma_counts', {})

        existing_identification = prisma_counts.get('identification', {})
        existing_records_identified = existing_identification.get(
            'records_identified',
            prisma_counts.get('scopus_retrieved', 0),
        )
        existing_records_after_duplicates = existing_identification.get(
            'records_after_duplicates',
            prisma_counts.get('after_dedup', 0),
        )

        grouped = {
            'identification': {
                'records_identified': int(existing_records_identified or 0),
                'records_after_duplicates': int(existing_records_after_duplicates or 0),
            },
            'screening': {
                'records_screened': total_papers,
                'records_excluded': screening_excluded,
            },
            'eligibility': {
                'full_text_assessed': fulltext_assessed,
                'full_text_excluded': fulltext_excluded,
            },
            'included': {
                'studies_included': fulltext_included,
            },
        }

        prisma_counts.update(
            {
                'scopus_retrieved': grouped['identification']['records_identified'],
                'after_dedup': grouped['identification']['records_after_duplicates'],
                'passed_ta': ta_included,
                'pdfs_retrieved': grouped['eligibility']['full_text_assessed'],
                'passed_fulltext': grouped['included']['studies_included'],
                'final_included': grouped['included']['studies_included'],
                'screening_total': grouped['screening']['records_screened'],
                'screening_excluded': grouped['screening']['records_excluded'],
                'fulltext_excluded': grouped['eligibility']['full_text_excluded'],
                'identification': grouped['identification'],
                'screening': grouped['screening'],
                'eligibility': grouped['eligibility'],
                'included': grouped['included'],
            }
        )

        scaffold_data['prisma_counts'] = prisma_counts
        set_scaffold_data(review, scaffold_data)
        review.save(update_fields=['scaffold_data'])


