from reviews.models import Paper

ids = list(
    Paper.objects.exclude(full_text_screening_status='')
    .values_list('id', flat=True)
)

print(f"Papers with full-text screening status: {len(ids)}")
for pid in ids[:50]:
    print(f"- paper_id={pid}")
