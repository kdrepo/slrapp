from collections import Counter, defaultdict
from statistics import mean

from django.core.management.base import BaseCommand

from reviews.models import Paper, Review, ThemeSynthesis
from reviews.services.design_canonicalizer import canonicalize_study_design, canonicalize_design_list


class Command(BaseCommand):
    help = 'Backfill canonical study design labels in full_text_extraction and normalize theme/scaffold design buckets.'

    def add_arguments(self, parser):
        parser.add_argument('--review-id', type=int, help='Optional review id. If omitted, all reviews are processed.')

    def handle(self, *args, **options):
        review_id = options.get('review_id')
        reviews = Review.objects.filter(pk=review_id) if review_id else Review.objects.all()

        total_papers = 0
        updated_papers = 0
        updated_themes = 0

        for review in reviews:
            papers = review.papers.exclude(full_text_extraction={}).order_by('id')
            paper_updates = 0
            for paper in papers:
                total_papers += 1
                extraction = paper.full_text_extraction if isinstance(paper.full_text_extraction, dict) else {}
                quality = paper.full_text_quality if isinstance(paper.full_text_quality, dict) else {}

                raw_design = str(extraction.get('study_design') or quality.get('study_type') or '').strip()
                canonical = canonicalize_study_design(raw_design)

                current = str(extraction.get('study_design_canonical') or '').strip()
                if current == canonical:
                    continue

                extraction['study_design_canonical'] = canonical
                paper.full_text_extraction = extraction
                paper.save(update_fields=['full_text_extraction'])
                paper_updates += 1
                updated_papers += 1

            theme_updates = 0
            for theme in review.theme_syntheses.all().order_by('id'):
                normalized = canonicalize_design_list(theme.designs_represented)
                if normalized != (theme.designs_represented or []):
                    theme.designs_represented = normalized
                    theme.save(update_fields=['designs_represented'])
                    theme_updates += 1
                    updated_themes += 1

            self._refresh_scaffold_design_sections(review)

            self.stdout.write(
                self.style.SUCCESS(
                    f'Review {review.id}: papers_updated={paper_updates}, themes_updated={theme_updates}, scaffold_design_sections_refreshed=1'
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'Backfill complete. total_papers_seen={total_papers}, papers_updated={updated_papers}, themes_updated={updated_themes}'
            )
        )

    def _refresh_scaffold_design_sections(self, review):
        included = review.papers.filter(full_text_decision=Paper.FullTextDecision.INCLUDED)

        design_scores = defaultdict(list)
        scores = []
        risk_counts = Counter()

        by_design = Counter()
        by_country = Counter()
        by_year = Counter()

        for paper in included:
            extraction = paper.full_text_extraction if isinstance(paper.full_text_extraction, dict) else {}
            quality = paper.full_text_quality if isinstance(paper.full_text_quality, dict) else {}

            design = canonicalize_study_design(
                str(extraction.get('study_design_canonical') or extraction.get('study_design') or quality.get('study_type') or 'unknown').strip()
            )
            country = str(extraction.get('country') or 'unknown').strip() or 'unknown'

            by_design[design] += 1
            by_country[country] += 1
            if paper.publication_year:
                by_year[int(paper.publication_year)] += 1

            total_score = quality.get('total_score')
            if isinstance(total_score, (int, float)):
                total_score = float(total_score)
                scores.append(total_score)
                design_scores[design].append(total_score)

            risk = str(quality.get('risk_of_bias') or '').strip().lower()
            if risk in ('low', 'moderate', 'high'):
                risk_counts[risk] += 1

        quality_by_design = {}
        for design, vals in design_scores.items():
            if vals:
                quality_by_design[design] = {'mean': round(mean(vals), 2), 'count': len(vals)}

        if scores:
            score_range = f'{int(min(scores))}-{int(max(scores))}'
            mean_score = round(mean(scores), 2)
        else:
            score_range = ''
            mean_score = 0

        sorted_years = dict(sorted(by_year.items(), key=lambda x: x[0]))
        year_keys = list(sorted_years.keys())
        year_span = (max(year_keys) - min(year_keys)) if len(year_keys) >= 2 else 0
        years_with_three_or_more = sum(1 for _, c in sorted_years.items() if c >= 3)

        scaffold = review.scaffold_data if isinstance(review.scaffold_data, dict) else {}
        scaffold['quality_summary'] = {
            'mean_score': mean_score,
            'score_range': score_range,
            'low_risk': int(risk_counts.get('low', 0)),
            'moderate_risk': int(risk_counts.get('moderate', 0)),
            'high_risk': int(risk_counts.get('high', 0)),
            'by_design': quality_by_design,
        }
        scaffold['subgroup_data'] = {
            'by_design': dict(by_design),
            'by_country': dict(by_country),
            'by_year': sorted_years,
            'year_span': year_span,
            'sankey_eligible': year_span >= 10,
            'year_subgroup_eligible': years_with_three_or_more >= 3,
        }

        review.scaffold_data = scaffold
        review.save(update_fields=['scaffold_data'])
