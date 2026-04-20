from collections import Counter

from reviews.models import Paper, Review
from reviews.services.scaffold_service import get_scaffold_data, set_scaffold_data


def compute_sensitivity_results_for_review(review_id):
    review = Review.objects.get(pk=review_id)
    included_qs = review.papers.filter(full_text_decision=Paper.FullTextDecision.INCLUDED).order_by('id')
    included_ids = list(included_qs.values_list('id', flat=True))

    if not included_ids:
        result = {
            'total_included': 0,
            'high_risk_removed': 0,
            'retained_after_removal': 0,
            'pct_removed': 0.0,
            'theme_counts_all': {},
            'theme_counts_after_removal': {},
            'themes_shifted': [],
            'summary': 'No included papers available for sensitivity analysis.',
        }
        _store_result(review, result)
        return result

    high_risk_ids = []
    for paper in included_qs:
        quality = paper.full_text_quality if isinstance(paper.full_text_quality, dict) else {}
        if str(quality.get('risk_of_bias') or '').strip().lower() == 'high':
            high_risk_ids.append(paper.id)

    retained_ids = set(included_ids) - set(high_risk_ids)
    theme_counts_all = Counter()
    theme_counts_after = Counter()

    for theme in review.theme_syntheses.all():
        theme_paper_ids = set(theme.papers.values_list('id', flat=True))
        if not theme_paper_ids:
            continue
        theme_counts_all[theme.theme_name_locked] = len(theme_paper_ids)
        theme_counts_after[theme.theme_name_locked] = len(theme_paper_ids & retained_ids)

    shifts = []
    for theme_name in sorted(set(theme_counts_all.keys()) | set(theme_counts_after.keys())):
        before = int(theme_counts_all.get(theme_name, 0))
        after = int(theme_counts_after.get(theme_name, 0))
        if before != after:
            shifts.append({'theme': theme_name, 'before': before, 'after': after})

    total_included = len(included_ids)
    removed = len(high_risk_ids)
    retained = len(retained_ids)
    pct_removed = round((removed / total_included) * 100.0, 2) if total_included else 0.0

    if not shifts:
        summary = (
            f'After removing {removed} high-risk studies '
            f'({pct_removed}% of included), theme coverage remained stable.'
        )
    else:
        summary = (
            f'After removing {removed} high-risk studies ({pct_removed}% of included), '
            f'{len(shifts)} theme(s) changed in supporting paper count.'
        )

    result = {
        'total_included': total_included,
        'high_risk_removed': removed,
        'retained_after_removal': retained,
        'pct_removed': pct_removed,
        'theme_counts_all': dict(theme_counts_all),
        'theme_counts_after_removal': dict(theme_counts_after),
        'themes_shifted': shifts,
        'summary': summary,
    }
    _store_result(review, result)
    return result


def get_or_compute_sensitivity_results(review):
    scaffold = get_scaffold_data(review)
    existing = scaffold.get('sensitivity_results', {})
    if isinstance(existing, dict) and existing:
        return existing
    return compute_sensitivity_results_for_review(review.id)


def _store_result(review, result):
    scaffold = get_scaffold_data(review)
    scaffold['sensitivity_results'] = result
    set_scaffold_data(review, scaffold)
    review.save(update_fields=['scaffold_data'])

