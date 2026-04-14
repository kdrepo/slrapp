from reviews.models import Review
from reviews.services.theme_synthesis_service import synthesize_themes_for_review

reviews = Review.objects.filter(theme_synthesis_status='done').order_by('id')
print(f'[ThemeResync] reviews_to_rerun={reviews.count()}')

ok = 0
failed = 0
for review in reviews:
    try:
        result = synthesize_themes_for_review(review.id)
        ok += 1
        print(f"[ThemeResync] review_id={review.id} status=done themes={result.get('theme_count', 0)} papers={result.get('total_papers', 0)}")
    except Exception as exc:
        failed += 1
        review.theme_synthesis_status = 'failed'
        review.theme_synthesis_error = f'{exc.__class__.__name__}: {exc}'
        review.save(update_fields=['theme_synthesis_status', 'theme_synthesis_error'])
        print(f"[ThemeResync] review_id={review.id} status=failed error={exc.__class__.__name__}: {exc}")

print(f'[ThemeResync] completed ok={ok} failed={failed}')
