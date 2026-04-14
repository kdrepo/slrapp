import re
from difflib import SequenceMatcher

from django.db import transaction
from django.db.models import Q

from reviews.models import Paper, Review

_CITED_BY_PATTERN = re.compile(r'Cited By:\s*(\d+)', re.IGNORECASE)


def ingest_ris_file(review_id, file_path):
    review = Review.objects.get(pk=review_id)
    entries = _load_ris_entries(file_path)

    pending = []
    missing_abstracts = 0

    for entry in entries:
        normalized = _normalize_entry(entry)
        if not normalized['abstract'].strip():
            missing_abstracts += 1
        pending.append(Paper(review=review, **normalized))

    with transaction.atomic():
        Paper.objects.bulk_create(pending)

    return {
        'total_papers_imported': len(pending),
        'duplicates_removed': 0,
        'missing_abstracts_flagged': missing_abstracts,
    }


def dedupe_review_papers(review_id):
    review = Review.objects.get(pk=review_id)
    papers = list(review.papers.order_by('id').only('id', 'doi', 'title', 'abstract'))

    total_before = len(papers)
    seen_dois = set()
    kept_titles = []
    kept_ids = []
    duplicate_ids = []

    for paper in papers:
        doi = _safe_text(paper.doi).lower()
        title = _safe_text(paper.title).lower()

        if doi and doi in seen_dois:
            duplicate_ids.append(paper.id)
            continue

        if title and any(_title_match(title, existing_title) for existing_title in kept_titles):
            duplicate_ids.append(paper.id)
            continue

        if doi:
            seen_dois.add(doi)
        if title:
            kept_titles.append(title)
        kept_ids.append(paper.id)

    if duplicate_ids:
        Paper.objects.filter(id__in=duplicate_ids).delete()

    Paper.objects.filter(review=review).update(ta_decision=Paper.TADecision.NOT_PROCESSED, ta_reason='', title_screening_decision=Paper.TitleScreeningDecision.NOT_PROCESSED, title_screening_reason='', title_screening_confidence=0.0, title_screening_status='', title_screening_provider='', title_screening_model='', title_screening_error='', title_screening_screened_at=None)

    missing_qs = Paper.objects.filter(review=review).filter(Q(abstract__isnull=True) | Q(abstract=''))
    missing_qs.update(
        ta_decision=Paper.TADecision.MISSING_ABS,
        ta_reason='Missing abstract in RIS metadata.',
    )

    total_after = total_before - len(duplicate_ids)
    missing_after_dedup = Paper.objects.filter(review=review, ta_decision=Paper.TADecision.MISSING_ABS).count()

    return {
        'total_before_dedupe': total_before,
        'duplicates_removed': len(duplicate_ids),
        'total_after_dedupe': total_after,
        'missing_abstracts_flagged': missing_after_dedup,
    }


def _load_ris_entries(file_path):
    try:
        import rispy
    except ImportError as exc:
        raise RuntimeError('rispy is not installed. Install with: pip install rispy') from exc

    with open(file_path, 'r', encoding='utf-8', errors='ignore') as handle:
        data = rispy.load(handle)

    return data or []


def _normalize_entry(entry):
    notes_raw = entry.get('notes', '')
    notes = _join_values(notes_raw, separator=' | ')

    return {
        'title': _safe_text(entry.get('title'))[:500],
        'authors': _join_values(entry.get('authors', []), separator='; '),
        'abstract': _safe_text(entry.get('abstract')),
        'publication_year': _parse_int(entry.get('year')),
        'journal': _safe_text(entry.get('secondary_title'))[:255],
        'volume': _safe_text(entry.get('volume'))[:64],
        'number': _safe_text(entry.get('number'))[:64],
        'start_page': _safe_text(entry.get('start_page'))[:64],
        'end_page': _safe_text(entry.get('end_page'))[:64],
        'publisher': _safe_text(entry.get('publisher'))[:255],
        'issn': _safe_text(entry.get('issn'))[:64],
        'language': _safe_text(entry.get('language'))[:64],
        'type_of_work': _safe_text(entry.get('type_of_reference'))[:128],
        'access_date': _safe_text(entry.get('access_date'))[:64],
        'notes': notes,
        'doi': _safe_text(entry.get('doi'))[:255],
        'scopus_id': _safe_text(entry.get('id'))[:255],
        'url': _first_url(entry.get('urls')),
        'keywords': _join_values(entry.get('keywords', []), separator='; '),
        'citation_count': _extract_citation_count(notes),
        'ta_decision': Paper.TADecision.NOT_PROCESSED,
        'title_screening_decision': Paper.TitleScreeningDecision.NOT_PROCESSED,
    }


def _title_match(left, right):
    if not left or not right:
        return False

    if left == right:
        return True

    ratio = SequenceMatcher(None, left, right).ratio() * 100
    return ratio >= 95


def _extract_citation_count(notes_text):
    if not notes_text:
        return 0

    match = _CITED_BY_PATTERN.search(notes_text)
    if not match:
        return 0

    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return 0


def _first_url(urls):
    if isinstance(urls, list):
        return _safe_text(urls[0]) if urls else ''
    return _safe_text(urls)


def _parse_int(value):
    if value is None:
        return None

    text = _safe_text(value)
    if not text:
        return None

    match = re.search(r'\d{4}', text)
    if not match:
        return None

    try:
        return int(match.group(0))
    except ValueError:
        return None


def _join_values(value, separator='; '):
    if isinstance(value, list):
        return separator.join(_safe_text(item) for item in value if _safe_text(item))
    return _safe_text(value)


def _safe_text(value):
    if value is None:
        return ''
    return str(value).strip()


