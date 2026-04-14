import re

from reviews.models import LitPaperAssignment, LitReview
from reviews.services.lit_citation_service import generate_apa_citations_for_lit_review


def run_lit_stage5c_references_for_review(review_id, progress_callback=None, stop_check=None):
    review = LitReview.objects.get(pk=review_id)
    _emit(progress_callback, {'event': 'started'})

    if stop_check and stop_check():
        return {'stopped': True}

    _emit(progress_callback, {'event': 'collecting'})
    used_refs = _collect_used_references(review)

    if stop_check and stop_check():
        return {'stopped': True}

    _emit(
        progress_callback,
        {
            'event': 'ensuring_citations',
            'used_count': len(used_refs['used_paper_ids']),
            'missing_count': len(used_refs['missing_citation_paper_ids']),
        },
    )

    if used_refs['missing_citation_paper_ids']:
        # Reuse existing layered APA generator for missing entries.
        generate_apa_citations_for_lit_review(
            review_id=review.id,
            only_missing=True,
            progress_callback=None,
            stop_check=stop_check,
        )
        used_refs = _collect_used_references(review)

    if stop_check and stop_check():
        return {'stopped': True}

    refs = used_refs['references_apa']
    _emit(progress_callback, {'event': 'assembling', 'references_count': len(refs)})
    final_text = _append_references_block(review.final_prose or '', refs)

    review.final_prose = final_text
    stage_progress = review.stage_progress or {}
    stage_progress['stage5c_references'] = {
        'status': 'completed',
        'used_paper_ids': used_refs['used_paper_ids'],
        'missing_reference_paper_ids': used_refs['missing_citation_paper_ids'],
        'references_apa': refs,
    }
    review.stage_progress = stage_progress
    review.save(update_fields=['final_prose', 'stage_progress'])

    _emit(progress_callback, {'event': 'done', 'references_count': len(refs)})
    return {
        'stopped': False,
        'references_count': len(refs),
        'used_paper_ids': used_refs['used_paper_ids'],
        'missing_reference_paper_ids': used_refs['missing_citation_paper_ids'],
        'references_apa': refs,
    }


def _collect_used_references(review):
    stage5 = (review.stage_progress or {}).get('stage5a_writing', {})
    section_outputs = stage5.get('section_outputs') if isinstance(stage5, dict) else {}
    if not isinstance(section_outputs, dict):
        section_outputs = {}

    used_citation_strings = []
    for row in section_outputs.values():
        if not isinstance(row, dict):
            continue
        papers_used = row.get('papers_used')
        if not isinstance(papers_used, list):
            continue
        for item in papers_used:
            text = str(item or '').strip()
            if text:
                used_citation_strings.append(text)

    assignments = list(
        LitPaperAssignment.objects
        .filter(review=review)
        .select_related('paper', 'section')
        .order_by('paper_id')
    )

    used_paper_ids = []
    missing_citation_paper_ids = []
    references = []

    for assignment in assignments:
        paper = assignment.paper
        citation = str(paper.citation_apa or '').strip()
        include = False

        if used_citation_strings:
            if citation and citation in used_citation_strings:
                include = True
        else:
            # Fallback: if stage5a metadata is absent, include assigned papers for written sections.
            prose = str(assignment.section.prose or '').strip()
            include = bool(prose)

        if not include:
            continue

        if paper.id not in used_paper_ids:
            used_paper_ids.append(paper.id)

        if citation:
            references.append(citation)
        else:
            missing_citation_paper_ids.append(paper.id)

    # Include direct citations from stage5 payload even if no assignment match.
    for text in used_citation_strings:
        if text not in references:
            references.append(text)

    references = _dedupe_and_sort_references(references)
    return {
        'used_paper_ids': used_paper_ids,
        'missing_citation_paper_ids': missing_citation_paper_ids,
        'references_apa': references,
    }


def _dedupe_and_sort_references(refs):
    seen = set()
    out = []
    for item in refs:
        text = str(item or '').strip()
        if not text:
            continue
        key = re.sub(r'\s+', ' ', text).strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    out.sort(key=lambda x: re.sub(r'\s+', ' ', str(x)).strip().lower())
    return out


def _append_references_block(final_prose, references_apa):
    text = str(final_prose or '').strip()
    if not text:
        text = ''

    # Replace existing trailing References block if present.
    marker = '\n\nReferences\n'
    idx = text.find(marker)
    if idx >= 0:
        text = text[:idx].rstrip()

    if not references_apa:
        return text

    refs_block = 'References\n' + '\n'.join(references_apa)
    if text:
        return f'{text}\n\n{refs_block}'
    return refs_block


def _emit(callback, payload):
    if not callback:
        return
    try:
        callback(payload)
    except Exception:
        return
