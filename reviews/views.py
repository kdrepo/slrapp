import json
import os
import re
import tempfile
import time
import threading
import traceback
from io import BytesIO
from difflib import SequenceMatcher
from urllib.parse import urlencode
from django.db.models import Q

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView

from .forms import (
    PDFManualUploadForm,
    RISUploadForm,
    ResearchQuestionFormSet,
    ReviewForm,
    ReviewFormalizationConfirmForm,
    TitlesExcelUploadForm,
)
from .models import Paper, Review, SearchQuery
from .services.gemini_service import formalize_research_parameters
from .services.fulltext_retrieval_service import retrieve_pdfs_for_review
from .services.ris_parser import dedupe_review_papers, ingest_ris_file
from .services.scopus_query_service import generate_scopus_queries
from .services.screening_service import poll_screening_batch, submit_screening_batch
from .services.title_excel_import_service import import_titles_file_for_review


_ACTIVE_FOCUS_ORDER = ['core', 'constructs', 'population', 'outcomes']


def _normalize_title_for_match(value):
    if not value:
        return ''
    return ' '.join(str(value).strip().lower().split())



class ReviewCreateView(CreateView):
    model = Review
    form_class = ReviewForm
    template_name = 'reviews/review_form.html'

    def form_valid(self, form):
        response = super().form_valid(form)

        try:
            formalize_research_parameters(review_id=self.object.pk)
        except Exception as exc:
            stage_progress = self.object.stage_progress or {}
            stage_progress['phase_2'] = 'formalization_failed'
            stage_progress['phase_2_error'] = str(exc)
            self.object.stage_progress = stage_progress
            self.object.save(update_fields=['stage_progress'])
            messages.warning(
                self.request,
                'AI formalization did not complete automatically. You can still edit and confirm manually.',
            )

        return response

    def get_success_url(self):
        return reverse('reviews:review-confirm', kwargs={'pk': self.object.pk})


class ReviewDetailView(DetailView):
    model = Review
    template_name = 'reviews/review_detail.html'


class ReviewFormalizationConfirmView(View):
    template_name = 'reviews/review_confirm.html'

    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        review_form = ReviewFormalizationConfirmForm(instance=review)
        rq_formset = ResearchQuestionFormSet(instance=review, prefix='rqs')

        return render(
            request,
            self.template_name,
            {
                'review': review,
                'review_form': review_form,
                'rq_formset': rq_formset,
            },
        )

    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        review_form = ReviewFormalizationConfirmForm(request.POST, instance=review)
        rq_formset = ResearchQuestionFormSet(request.POST, instance=review, prefix='rqs')

        if not review_form.is_valid() or not rq_formset.is_valid():
            return render(
                request,
                self.template_name,
                {
                    'review': review,
                    'review_form': review_form,
                    'rq_formset': rq_formset,
                },
                status=400,
            )

        review_form.save()
        rq_formset.save()

        review.status = Review.Status.RUNNING
        stage_progress = review.stage_progress or {}
        stage_progress['phase_2'] = 'confirmed_locked'
        review.stage_progress = stage_progress
        review.save(update_fields=['status', 'stage_progress'])

        messages.success(request, 'Research parameters confirmed and locked. The review is now running.')
        return redirect('reviews:search-strategy', pk=review.pk)


class SearchStrategyView(View):
    template_name = 'reviews/search_strategy.html'

    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)

        if review.search_queries.filter(focus__in=_ACTIVE_FOCUS_ORDER).count() == 0:
            try:
                generate_scopus_queries(review_id=review.pk)
                messages.success(request, 'Phase 3 completed: 4 Scopus search queries generated.')
            except Exception as exc:
                stage_progress = review.stage_progress or {}
                stage_progress['phase_3'] = 'query_generation_failed'
                stage_progress['phase_3_error'] = str(exc)
                review.stage_progress = stage_progress
                review.save(update_fields=['stage_progress'])
                messages.error(
                    request,
                    'Query generation failed. Please verify Gemini configuration and try again.',
                )

        search_queries = review.search_queries.filter(focus__in=_ACTIVE_FOCUS_ORDER)
        ordered = sorted(
            search_queries,
            key=lambda item: _ACTIVE_FOCUS_ORDER.index(item.focus) if item.focus in _ACTIVE_FOCUS_ORDER else 99,
        )

        return render(
            request,
            self.template_name,
            {
                'review': review,
                'search_queries': ordered,
            },
        )


class RISUploadView(View):
    template_name = 'reviews/ris_upload.html'

    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        report = _get_saved_ingest_report(review)

        return render(
            request,
            self.template_name,
            {
                'review': review,
                'form': RISUploadForm(),
                'titles_form': TitlesExcelUploadForm(),
                'search_queries': _ordered_queries(review),
                'report': report,
            },
        )

    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        action = (request.POST.get('action') or 'upload').strip().lower()

        if action == 'start_dedupe':
            uploaded_count = review.search_queries.filter(focus__in=_ACTIVE_FOCUS_ORDER, ris_uploaded=True).count()
            if uploaded_count == 0:
                messages.warning(request, 'No RIS uploads found yet. Upload at least one RIS file before running dedupe.')
                return render(
                    request,
                    self.template_name,
                    {
                        'review': review,
                        'form': RISUploadForm(),
                        'titles_form': TitlesExcelUploadForm(),
                        'search_queries': _ordered_queries(review),
                        'report': _get_saved_ingest_report(review),
                    },
                )

            try:
                dedupe_report = dedupe_review_papers(review_id=review.pk)
                report = {
                    'total_papers_imported': dedupe_report['total_before_dedupe'],
                    'duplicates_removed': dedupe_report['duplicates_removed'],
                    'missing_abstracts_flagged': dedupe_report['missing_abstracts_flagged'],
                }
                _save_ingest_report(review, report, dedupe_report)
                messages.success(
                    request,
                    f"Deduplication completed. Uploaded queries used: {uploaded_count}. "
                    f"Duplicates removed: {dedupe_report['duplicates_removed']}.",
                )
            except Exception as exc:
                messages.error(request, f'Deduplication failed: {exc}')

            return render(
                request,
                self.template_name,
                {
                    'review': review,
                    'form': RISUploadForm(),
                    'titles_form': TitlesExcelUploadForm(),
                    'search_queries': _ordered_queries(review),
                    'report': _get_saved_ingest_report(review),
                },
            )

        if action == 'upload_titles_excel':
            titles_form = TitlesExcelUploadForm(request.POST, request.FILES)
            if not titles_form.is_valid():
                messages.error(request, 'Please select a valid .csv or .xlsx file with titles in the first column.')
                return render(
                    request,
                    self.template_name,
                    {
                        'review': review,
                        'form': RISUploadForm(),
                        'titles_form': titles_form,
                        'search_queries': _ordered_queries(review),
                        'report': _get_saved_ingest_report(review),
                    },
                )

            try:
                result = import_titles_file_for_review(
                    review_id=review.pk,
                    uploaded_file=titles_form.cleaned_data['titles_file'],
                )
                stage_progress = review.stage_progress or {}
                stage_progress['phase_5_titles_import'] = result
                review.stage_progress = stage_progress
                review.save(update_fields=['stage_progress'])
                messages.success(
                    request,
                    (
                        f"Titles import complete. Rows: {result.get('total_rows', 0)}, "
                        f"created: {result.get('created', 0)}, duplicates skipped: {result.get('duplicates_skipped', 0)}, "
                        f"empty rows: {result.get('empty_rows', 0)}."
                    ),
                )
            except Exception as exc:
                messages.error(request, f'Titles import failed: {exc}')

            return render(
                request,
                self.template_name,
                {
                    'review': review,
                    'form': RISUploadForm(),
                    'titles_form': TitlesExcelUploadForm(),
                    'search_queries': _ordered_queries(review),
                    'report': _get_saved_ingest_report(review),
                },
            )

        form = RISUploadForm(request.POST, request.FILES)
        report = None

        search_query_id = request.POST.get('search_query_id')
        search_query = get_object_or_404(SearchQuery, pk=search_query_id, review=review)

        if form.is_valid():
            uploaded = form.cleaned_data['ris_file']
            suffix = os.path.splitext(uploaded.name)[1] or '.ris'

            os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=settings.MEDIA_ROOT) as temp_file:
                for chunk in uploaded.chunks():
                    temp_file.write(chunk)
                temp_path = temp_file.name

            try:
                ingest_report = ingest_ris_file(review_id=review.pk, file_path=temp_path)

                search_query.ris_uploaded = True
                search_query.ris_uploaded_at = timezone.now()
                search_query.ris_file_name = uploaded.name
                search_query.imported_records = ingest_report['total_papers_imported']
                search_query.missing_abstracts = ingest_report['missing_abstracts_flagged']
                search_query.is_executed = True
                search_query.save(
                    update_fields=[
                        'ris_uploaded',
                        'ris_uploaded_at',
                        'ris_file_name',
                        'imported_records',
                        'missing_abstracts',
                        'is_executed',
                    ]
                )

                report = _aggregate_upload_report(review)
                messages.success(
                    request,
                    f'Uploaded RIS for {search_query.get_focus_display()}. '
                    'When ready, click "Start Deduplication".',
                )

            except Exception as exc:
                messages.error(request, f'RIS ingest failed: {exc}')
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        return render(
            request,
            self.template_name,
            {
                'review': review,
                'form': form,
                'titles_form': TitlesExcelUploadForm(),
                'search_queries': _ordered_queries(review),
                'report': report or _get_saved_ingest_report(review),
            },
        )

class FullTextUploadWindowView(View):
    template_name = 'reviews/fulltext_upload_window.html'

    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        papers = self._pending_papers(review)
        selected_table_decision = (request.GET.get('table_ta_decision') or 'all').strip().lower()
        selected_fulltext_filter = (request.GET.get('table_fulltext') or 'all').strip().lower()
        show_table = (request.GET.get('show_table') or '0').strip() == '1'
        table_papers = []
        if show_table:
            table_papers = self._table_papers(review, selected_table_decision, selected_fulltext_filter)
        decision_options = [('all', 'All decisions')] + list(Paper.TADecision.choices)
        fulltext_options = [
            ('all', 'All fulltext states'),
            ('retrieved', 'Retrieved (True)'),
            ('not_retrieved', 'Not Retrieved (False)'),
        ]

        pending_title_search = (request.GET.get('pending_title_search') or '').strip()
        pending_search_results = []
        if pending_title_search:
            pending_search_results = self._search_pending_titles(review, pending_title_search)

        bulk_report = self._get_bulk_upload_report(review)
        bulk_source_folder_path = (bulk_report.get('source_folder_path') or '').strip()
        selected_bulk_status = (request.GET.get('bulk_status') or 'all').strip().lower()
        bulk_status_options = [
            ('all', 'All statuses'),
            ('matched', 'Matched'),
            ('unmatched', 'Unmatched'),
            ('error', 'Error'),
        ]
        bulk_report_rows = list(bulk_report.get('rows') or [])
        if selected_bulk_status in {'matched', 'unmatched', 'error'}:
            bulk_report_rows = [row for row in bulk_report_rows if (row.get('status') or '').strip().lower() == selected_bulk_status]

        return render(
            request,
            self.template_name,
            {
                'review': review,
                'papers': papers,
                'decision_options': decision_options,
                'fulltext_options': fulltext_options,
                'selected_table_decision': selected_table_decision,
                'selected_fulltext_filter': selected_fulltext_filter,
                'show_table': show_table,
                'table_papers': table_papers,
                'bulk_report': bulk_report,
                'bulk_source_folder_path': bulk_source_folder_path,
                'bulk_report_rows': bulk_report_rows,
                'selected_bulk_status': selected_bulk_status,
                'bulk_status_options': bulk_status_options,
                'pending_title_search': pending_title_search,
                'pending_search_results': pending_search_results,
            },
        )

    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        action = (request.POST.get('action') or '').strip().lower()

        if action == 'download_pending_json':
            papers = self._pending_papers(review).values('id', 'url')
            payload = {
                'review_id': review.id,
                'review_title': review.title,
                'count': papers.count(),
                'papers': [
                    {
                        'paper_id': row['id'],
                        'url': row['url'] or '',
                    }
                    for row in papers
                ],
            }
            response = HttpResponse(
                json.dumps(payload, indent=2, ensure_ascii=False),
                content_type='application/json',
            )
            response['Content-Disposition'] = f'attachment; filename=review_{review.id}_pending_fulltext_urls.json'
            return response

        if action == 'upload_bulk_pdfs':
            return self._handle_bulk_pdf_upload(request, review)

        if action == 'run_auto_retrieval':
            summary = retrieve_pdfs_for_review(review_id=review.pk)
            messages.success(
                request,
                f"Auto retrieval done. Targeted: {summary.get('targeted', 0)}, downloaded: {summary.get('downloaded', 0)}, abstract_only: {summary.get('abstract_only', 0)}.",
            )
            return redirect('reviews:fulltext-upload-window', pk=review.pk)

        if action == 'upload_pdf':
            form = PDFManualUploadForm(request.POST, request.FILES)
            if not form.is_valid():
                messages.error(request, 'Please choose a PDF file before uploading.')
                return redirect('reviews:fulltext-upload-window', pk=review.pk)

            paper = get_object_or_404(Paper, pk=form.cleaned_data['paper_id'], review=review)
            uploaded_pdf = form.cleaned_data['pdf_file']
            relative_path = self._save_uploaded_pdf(review_id=review.pk, paper_id=paper.id, uploaded_file=uploaded_pdf)

            paper.pdf_path.name = relative_path
            paper.fulltext_retrieved = True
            paper.pdf_source = 'manual_upload'
            paper.save(update_fields=['pdf_path', 'fulltext_retrieved', 'pdf_source'])
            messages.success(request, f'Uploaded PDF for paper {paper.id}.')
            return redirect('reviews:fulltext-upload-window', pk=review.pk)

        if action == 'skip_abstract_only':
            paper = get_object_or_404(Paper, pk=request.POST.get('paper_id'), review=review)
            paper.fulltext_retrieved = False
            paper.pdf_source = 'abstract_only'
            paper.save(update_fields=['fulltext_retrieved', 'pdf_source'])
            messages.success(request, f'Paper {paper.id} marked as abstract_only.')
            return redirect('reviews:fulltext-upload-window', pk=review.pk)

        messages.error(request, 'Invalid action.')
        return redirect('reviews:fulltext-upload-window', pk=review.pk)

    def _handle_bulk_pdf_upload(self, request, review):
        uploaded_files = request.FILES.getlist('pdf_files')
        source_folder_path = (request.POST.get('source_folder_path') or '').strip()

        if not uploaded_files:
            messages.error(request, 'Please select one or more PDF files for bulk upload.')
            return redirect('reviews:fulltext-upload-window', pk=review.pk)

        candidate_papers = list(
            review.papers.filter(
                ta_decision=Paper.TADecision.INCLUDED,
                fulltext_retrieved=False,
            ).only('id', 'title')
        )

        candidates = []
        for paper in candidate_papers:
            normalized = _normalize_title_for_match(paper.title)
            if normalized:
                candidates.append({'paper': paper, 'normalized': normalized})

        stage_dir = self._bulk_stage_dir(review.id)
        os.makedirs(stage_dir, exist_ok=True)

        used_paper_ids = set()
        rows = []
        matched_count = 0
        unmatched_count = 0
        error_count = 0
        source_deleted_count = 0
        source_delete_failed_count = 0

        for uploaded in uploaded_files:
            file_name = uploaded.name
            staged_path = self._save_bulk_staging_file(stage_dir, uploaded)

            if not file_name.lower().endswith('.pdf'):
                error_count += 1
                rows.append(
                    {
                        'file_name': file_name,
                        'extracted_title': '',
                        'mapped_title': '',
                        'mapped_paper_id': '',
                        'score': 0.0,
                        'status': 'error',
                        'error': 'File is not a PDF.',
                        'source_delete_status': 'not_attempted',
                        'source_delete_message': '',
                    }
                )
                continue

            try:
                extracted_title = self._extract_pdf_title_from_path(staged_path, file_name)
            except Exception as exc:
                error_count += 1
                rows.append(
                    {
                        'file_name': file_name,
                        'extracted_title': '',
                        'mapped_title': '',
                        'mapped_paper_id': '',
                        'score': 0.0,
                        'status': 'error',
                        'error': f'Title extraction failed: {exc.__class__.__name__}: {exc}',
                        'source_delete_status': 'not_attempted',
                        'source_delete_message': '',
                    }
                )
                continue

            normalized_extracted = _normalize_title_for_match(extracted_title)
            if not normalized_extracted:
                unmatched_count += 1
                rows.append(
                    {
                        'file_name': file_name,
                        'extracted_title': '',
                        'mapped_title': '',
                        'mapped_paper_id': '',
                        'score': 0.0,
                        'status': 'unmatched',
                        'error': 'Could not extract title from PDF metadata or filename.',
                        'source_delete_status': 'not_attempted',
                        'source_delete_message': '',
                    }
                )
                continue

            best_candidate = None
            best_score = 0.0
            for candidate in candidates:
                paper_id = candidate['paper'].id
                if paper_id in used_paper_ids:
                    continue
                score = SequenceMatcher(None, normalized_extracted, candidate['normalized']).ratio() * 100.0
                if score > best_score:
                    best_score = score
                    best_candidate = candidate

            if best_candidate and best_score > 82.0:
                paper = best_candidate['paper']
                relative_path = self._save_pdf_from_path(review_id=review.pk, paper_id=paper.id, source_path=staged_path)
                paper.pdf_path.name = relative_path
                paper.fulltext_retrieved = True
                paper.pdf_source = 'bulk_upload'
                paper.save(update_fields=['pdf_path', 'fulltext_retrieved', 'pdf_source'])
                used_paper_ids.add(paper.id)
                matched_count += 1

                try:
                    os.remove(staged_path)
                except OSError:
                    pass

                source_delete_status, source_delete_message = self._delete_from_source_folder(source_folder_path, file_name)
                if source_delete_status == 'deleted':
                    source_deleted_count += 1
                elif source_delete_status == 'failed':
                    source_delete_failed_count += 1

                rows.append(
                    {
                        'file_name': file_name,
                        'extracted_title': extracted_title,
                        'mapped_title': paper.title,
                        'mapped_paper_id': paper.id,
                        'score': round(best_score, 2),
                        'status': 'matched',
                        'error': '',
                        'source_delete_status': source_delete_status,
                        'source_delete_message': source_delete_message,
                    }
                )
            else:
                unmatched_count += 1
                rows.append(
                    {
                        'file_name': file_name,
                        'extracted_title': extracted_title,
                        'mapped_title': '',
                        'mapped_paper_id': '',
                        'score': round(best_score, 2),
                        'status': 'unmatched',
                        'error': 'No paper title matched above 82%.',
                        'source_delete_status': 'not_attempted',
                        'source_delete_message': '',
                    }
                )

        report = {
            'timestamp': timezone.now().isoformat(),
            'source_folder_path': source_folder_path,
            'total_files': len(uploaded_files),
            'matched_count': matched_count,
            'unmatched_count': unmatched_count,
            'error_count': error_count,
            'source_deleted_count': source_deleted_count,
            'source_delete_failed_count': source_delete_failed_count,
            'rows': rows,
        }
        self._set_bulk_upload_report(review, report)

        messages.success(
            request,
            f"Bulk upload complete. Files: {len(uploaded_files)}, matched: {matched_count}, unmatched: {unmatched_count}, errors: {error_count}, source-deleted: {source_deleted_count}, source-delete-failed: {source_delete_failed_count}.",
        )
        return redirect('reviews:fulltext-upload-window', pk=review.pk)
    def _extract_pdf_title_from_path(self, staged_path, original_name):
        with open(staged_path, 'rb') as handle:
            raw = handle.read()

        if not raw:
            return ''

        text = raw.decode('latin-1', errors='ignore')

        metadata_match = re.search(r'/Title\s*\((.{5,500}?)\)', text, flags=re.IGNORECASE | re.DOTALL)
        if metadata_match:
            return self._clean_extracted_title(metadata_match.group(1))

        xmp_match = re.search(r'<dc:title>.*?<rdf:li[^>]*>(.{5,500}?)</rdf:li>.*?</dc:title>', text, flags=re.IGNORECASE | re.DOTALL)
        if xmp_match:
            return self._clean_extracted_title(xmp_match.group(1))

        file_stem = os.path.splitext(original_name or '')[0]
        file_stem = file_stem.replace('_', ' ').replace('-', ' ').strip()
        return self._clean_extracted_title(file_stem)

    def _clean_extracted_title(self, value):
        cleaned = (value or '').replace('\\(', '(').replace('\\)', ')')
        cleaned = cleaned.replace('\\n', ' ').replace('\n', ' ')
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned[:500]

    def _bulk_stage_dir(self, review_id):
        return os.path.join(settings.MEDIA_ROOT, 'pdfs', str(review_id), 'bulk_staging')

    def _save_bulk_staging_file(self, stage_dir, uploaded_file):
        safe_name = re.sub(r'[^A-Za-z0-9._-]+', '_', uploaded_file.name or 'upload.pdf').strip('._') or 'upload.pdf'
        base, ext = os.path.splitext(safe_name)
        ext = ext or '.pdf'
        candidate = os.path.join(stage_dir, f'{base}{ext}')
        counter = 1
        while os.path.exists(candidate):
            candidate = os.path.join(stage_dir, f'{base}_{counter}{ext}')
            counter += 1

        with open(candidate, 'wb') as handle:
            for chunk in uploaded_file.chunks():
                handle.write(chunk)

        return candidate

    def _delete_from_source_folder(self, source_folder_path, uploaded_file_name):
        if not source_folder_path:
            return 'not_attempted', 'Source folder path not provided.'

        if not os.path.isdir(source_folder_path):
            return 'failed', f'Source folder not found: {source_folder_path}'

        safe_name = os.path.basename(uploaded_file_name or '').strip()
        if not safe_name:
            return 'failed', 'Uploaded filename is empty.'

        source_file = os.path.join(source_folder_path, safe_name)
        if not os.path.exists(source_file):
            return 'failed', f'File not found in source folder: {safe_name}'

        # Windows can temporarily lock files (Explorer preview, AV scan, cloud sync).
        # Retry a few times before returning failure.
        last_exc = None
        for attempt in range(1, 6):
            try:
                os.remove(source_file)
                return 'deleted', f'Deleted from source folder: {safe_name} (attempt {attempt})'
            except PermissionError as exc:
                last_exc = exc
                time.sleep(0.6 * attempt)
            except Exception as exc:
                return 'failed', f'Could not delete source file {safe_name}: {exc.__class__.__name__}: {exc}'

        return (
            'failed',
            f'Could not delete source file {safe_name} after retries (likely locked by another process). '
            f'Last error: {last_exc.__class__.__name__}: {last_exc}'
        )
    def _search_pending_titles(self, review, query_text):
        normalized_query = _normalize_title_for_match(query_text)
        if not normalized_query:
            return []

        results = []
        for paper in self._pending_papers(review).only('id', 'title', 'doi', 'pdf_source'):
            normalized_title = _normalize_title_for_match(paper.title)
            if not normalized_title:
                continue
            score = SequenceMatcher(None, normalized_query, normalized_title).ratio() * 100.0
            if score > 80.0:
                results.append(
                    {
                        'paper': paper,
                        'score': round(score, 2),
                    }
                )

        results.sort(key=lambda item: item['score'], reverse=True)
        return results

    def _pending_papers(self, review):
        return review.papers.filter(
            ta_decision=Paper.TADecision.INCLUDED,
            fulltext_retrieved=False,
        ).order_by('id')

    def _table_papers(self, review, selected_decision, selected_fulltext_filter):
        queryset = review.papers.order_by('id')
        if selected_decision != 'all':
            valid = {choice[0] for choice in Paper.TADecision.choices}
            if selected_decision in valid:
                queryset = queryset.filter(ta_decision=selected_decision)

        if selected_fulltext_filter == 'retrieved':
            queryset = queryset.filter(fulltext_retrieved=True)
        elif selected_fulltext_filter == 'not_retrieved':
            queryset = queryset.filter(fulltext_retrieved=False)

        return queryset.only('id', 'title', 'url')

    def _save_pdf_from_path(self, review_id, paper_id, source_path):
        target_dir = os.path.join(settings.MEDIA_ROOT, 'pdfs', str(review_id))
        os.makedirs(target_dir, exist_ok=True)
        absolute_path = os.path.join(target_dir, f'{paper_id}.pdf')

        with open(source_path, 'rb') as source, open(absolute_path, 'wb') as target:
            target.write(source.read())

        return f'pdfs/{review_id}/{paper_id}.pdf'

    def _save_uploaded_pdf(self, review_id, paper_id, uploaded_file):
        target_dir = os.path.join(settings.MEDIA_ROOT, 'pdfs', str(review_id))
        os.makedirs(target_dir, exist_ok=True)
        absolute_path = os.path.join(target_dir, f'{paper_id}.pdf')

        with open(absolute_path, 'wb') as handle:
            for chunk in uploaded_file.chunks():
                handle.write(chunk)

        return f'pdfs/{review_id}/{paper_id}.pdf'

    def _get_bulk_upload_report(self, review):
        stage_progress = review.stage_progress or {}
        return stage_progress.get('phase_12_bulk_upload_report') or {}

    def _set_bulk_upload_report(self, review, report):
        stage_progress = review.stage_progress or {}
        stage_progress['phase_12_bulk_upload_report'] = report
        review.stage_progress = stage_progress
        review.save(update_fields=['stage_progress'])

class FullTextRetrievalMonitorView(View):
    template_name = 'reviews/fulltext_retrieval_monitor.html'

    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        snapshot = _get_fulltext_stage_snapshot(review)
        return render(
            request,
            self.template_name,
            {
                'review': review,
                'stage': snapshot,
            },
        )

    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        snapshot = _get_fulltext_stage_snapshot(review)
        action = (request.POST.get('action') or 'start').strip().lower()

        if action == 'stop':
            if snapshot.get('status') not in {'running', 'stopping'}:
                messages.warning(request, 'No active full-text retrieval is running.')
                return redirect('reviews:fulltext-retrieval-monitor', pk=review.pk)

            stage = dict(snapshot)
            stage['status'] = 'stopping'
            stage['stop_requested'] = True
            stage['stop_requested_at'] = timezone.now().isoformat()
            _set_fulltext_stage_snapshot(review, stage)
            messages.success(request, 'Stop requested. The current paper will finish, then retrieval will halt.')
            return redirect('reviews:fulltext-retrieval-monitor', pk=review.pk)

        if snapshot.get('status') in {'running', 'stopping'}:
            messages.warning(request, 'Full-text retrieval is already running.')
            return redirect('reviews:fulltext-retrieval-monitor', pk=review.pk)

        if action == 'retry':
            candidate_ids = list(snapshot.get('remaining_paper_ids') or [])
            if not candidate_ids:
                messages.warning(request, 'No remaining papers found from previous run. Starting normal retrieval.')
                action = 'start'
        else:
            candidate_ids = list(
                review.papers.filter(
                    ta_decision=Paper.TADecision.INCLUDED,
                    fulltext_retrieved=False,
                ).order_by('id').values_list('id', flat=True)
            )

        if action == 'retry' and candidate_ids:
            run_ids = [int(pid) for pid in candidate_ids]
            run_label = 'retry_remaining'
        else:
            run_ids = candidate_ids
            run_label = 'start_full'

        _set_fulltext_stage_snapshot(
            review,
            {
                'status': 'running',
                'run_type': run_label,
                'started_at': timezone.now().isoformat(),
                'targeted': len(run_ids),
                'processed': 0,
                'downloaded': 0,
                'failed': 0,
                'skipped_existing': 0,
                'processed_paper_ids': [],
                'remaining_paper_ids': run_ids,
                'logs': [],
                'error_code': '',
                'error_message': '',
                'error_traceback': '',
            },
        )

        worker = threading.Thread(target=_run_fulltext_retrieval_async, args=(review.pk, run_ids), daemon=True)
        worker.start()

        if run_label == 'retry_remaining':
            messages.success(request, f'Retry started for remaining papers: {len(run_ids)}.')
        else:
            messages.success(request, 'Full-text retrieval started. Open status below for live updates.')
        return redirect('reviews:fulltext-retrieval-monitor', pk=review.pk)


class FullTextRetrievalStatusView(View):
    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        return JsonResponse(_get_fulltext_stage_snapshot(review))


def _run_fulltext_retrieval_async(review_id, paper_ids):
    def _should_stop():
        review = Review.objects.get(pk=review_id)
        stage = _get_fulltext_stage_snapshot(review)
        return bool(stage.get('stop_requested'))

    def _progress(event):
        review = Review.objects.get(pk=review_id)
        stage = _get_fulltext_stage_snapshot(review)
        logs = list(stage.get('logs') or [])

        event_name = event.get('event', '')
        title = (event.get('title') or '')[:180]
        paper_id = event.get('paper_id')
        source = event.get('source') or ''
        status_code = event.get('status_code')
        error_message = event.get('error_message') or ''

        if event_name == 'started':
            stage['targeted'] = int(event.get('targeted', 0) or 0)
            stage['remaining_paper_ids'] = list(event.get('paper_ids') or stage.get('remaining_paper_ids') or [])
        elif event_name == 'stopped':
            stage['status'] = 'stopping'
            stage['remaining_paper_ids'] = list(event.get('remaining_paper_ids') or stage.get('remaining_paper_ids') or [])
        elif event_name in {'downloaded', 'failed', 'skipped_existing'}:
            stage['processed'] = int(stage.get('processed', 0)) + 1
            processed_ids = list(stage.get('processed_paper_ids') or [])
            if paper_id and paper_id not in processed_ids:
                processed_ids.append(paper_id)
            stage['processed_paper_ids'] = processed_ids
            stage['remaining_paper_ids'] = [pid for pid in (stage.get('remaining_paper_ids') or []) if pid != paper_id]

            if event_name == 'downloaded':
                stage['downloaded'] = int(stage.get('downloaded', 0)) + 1
            if event_name == 'failed':
                stage['failed'] = int(stage.get('failed', 0)) + 1
            if event_name == 'skipped_existing':
                stage['skipped_existing'] = int(stage.get('skipped_existing', 0)) + 1

        if event_name in {'processing', 'downloaded', 'failed', 'skipped_existing', 'stopped'}:
            logs.insert(
                0,
                {
                    'time': timezone.now().isoformat(),
                    'event': event_name,
                    'paper_id': paper_id,
                    'title': title,
                    'source': source,
                    'status_code': status_code,
                    'error_message': error_message,
                },
            )
            stage['logs'] = logs[:400]

        _set_fulltext_stage_snapshot(review, stage)

    try:
        summary = retrieve_pdfs_for_review(
            review_id=review_id,
            progress_callback=_progress,
            paper_ids=paper_ids,
            stop_check=_should_stop,
        )
        review = Review.objects.get(pk=review_id)
        stage = _get_fulltext_stage_snapshot(review)
        stage['status'] = 'stopped' if summary.get('stopped') else 'completed'
        stage['completed_at'] = timezone.now().isoformat()
        stage['targeted'] = int(summary.get('targeted', stage.get('targeted', 0)))
        stage['downloaded'] = int(summary.get('downloaded', stage.get('downloaded', 0)))
        stage['failed'] = int(summary.get('abstract_only', stage.get('failed', 0)))
        stage['skipped_existing'] = int(summary.get('skipped_existing', stage.get('skipped_existing', 0)))
        stage['processed_paper_ids'] = list(summary.get('processed_ids', stage.get('processed_paper_ids') or []))
        stage['remaining_paper_ids'] = list(summary.get('remaining_paper_ids', stage.get('remaining_paper_ids') or []))
        stage['processed'] = stage['downloaded'] + stage['failed'] + stage['skipped_existing']
        _set_fulltext_stage_snapshot(review, stage)
    except Exception as exc:
        review = Review.objects.get(pk=review_id)
        stage = _get_fulltext_stage_snapshot(review)
        stage['status'] = 'error'
        stage['error_code'] = exc.__class__.__name__
        stage['error_message'] = str(exc)
        stage['error_traceback'] = traceback.format_exc()
        stage['completed_at'] = timezone.now().isoformat()
        _set_fulltext_stage_snapshot(review, stage)

def _get_fulltext_stage_snapshot(review):
    stage_progress = review.stage_progress or {}
    return stage_progress.get('phase_10_fulltext', {})


def _set_fulltext_stage_snapshot(review, stage_payload):
    stage_progress = review.stage_progress or {}
    stage_progress['phase_10_fulltext'] = stage_payload
    review.stage_progress = stage_progress
    review.save(update_fields=['stage_progress'])
class ScreeningDashboardView(View):
    template_name = 'reviews/screening_dashboard.html'

    TITLE_SCREENING_OPTIONS = [
        Paper.TitleScreeningDecision.INCLUDED,
        Paper.TitleScreeningDecision.EXCLUDED,
        Paper.TitleScreeningDecision.UNCERTAIN,
        Paper.TitleScreeningDecision.MANUAL_TITLES,
        Paper.TitleScreeningDecision.NOT_PROCESSED,
    ]

    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        unprocessed_count = review.papers.filter(Q(ta_decision=Paper.TADecision.NOT_PROCESSED) | Q(ta_decision__isnull=True)).exclude(abstract__isnull=True).exclude(abstract='').count()
        conflicts_count = review.papers.filter(screening_conflict=True).count()
        fulltext_pending_count = review.papers.filter(ta_decision=Paper.TADecision.INCLUDED, fulltext_retrieved=False).count()

        stage_7 = (review.stage_progress or {}).get('phase_7', {})
        selected_title_decisions = stage_7.get('title_screening_decisions') or list(self.TITLE_SCREENING_OPTIONS)
        selected_title_decisions = [
            item for item in selected_title_decisions
            if item in self.TITLE_SCREENING_OPTIONS
        ] or list(self.TITLE_SCREENING_OPTIONS)

        title_screening_option_rows = []
        for value, label in Paper.TitleScreeningDecision.choices:
            if value not in self.TITLE_SCREENING_OPTIONS:
                continue
            title_screening_option_rows.append(
                {
                    'value': value,
                    'label': label,
                    'count': review.papers.filter(title_screening_decision=value).count(),
                    'selected': value in selected_title_decisions,
                }
            )

        return render(
            request,
            self.template_name,
            {
                'review': review,
                'unprocessed_count': unprocessed_count,
                'conflicts_count': conflicts_count,
                'fulltext_pending_count': fulltext_pending_count,
                'phase_7': stage_7,
                'phase_8': (review.stage_progress or {}).get('phase_8', {}),
                'title_screening_option_rows': title_screening_option_rows,
                'selected_title_decisions': selected_title_decisions,
            },
        )


class StartScreeningBatchView(View):
    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        action = (request.POST.get('action') or 'start').strip().lower()
        allowed = {choice[0] for choice in Paper.TitleScreeningDecision.choices}
        selected_title_decisions = [
            value for value in request.POST.getlist('title_screening_decisions')
            if value in allowed
        ]
        if not selected_title_decisions:
            selected_title_decisions = [choice[0] for choice in Paper.TitleScreeningDecision.choices]

        try:
            stage_progress = review.stage_progress or {}
            stage_phase = stage_progress.get('phase_7', {})
            stage_phase['title_screening_decisions'] = selected_title_decisions
            stage_progress['phase_7'] = stage_phase
            review.stage_progress = stage_progress
            review.save(update_fields=['stage_progress'])

            result = submit_screening_batch(
                review_id=review.pk,
                title_decisions=selected_title_decisions,
            )
            if result.get('submitted'):
                if action == 'retry_not_done':
                    messages.success(request, f"Retry for not-done papers started ({result.get('request_count', 0)} papers).")
                else:
                    messages.success(request, f"Screening queue started for {result.get('request_count', 0)} papers.")
            else:
                messages.warning(request, 'No eligible papers found for the selected title-screening categories (needs NOT_PROCESSED/NULL TA decision and non-empty abstract).')
        except Exception as exc:
            messages.error(request, f'Screening start failed: {exc}')
        return redirect('reviews:screening-dashboard', pk=review.pk)


class PollScreeningBatchView(View):
    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        try:
            result = poll_screening_batch(review_id=review.pk)
            messages.success(
                request,
                f"Poll result: {result.get('state')}. Updated {result.get('updated', 0)} papers, conflicts {result.get('conflicts', 0)}, remaining {result.get('remaining', 0)}.",
            )
        except Exception as exc:
            messages.error(request, f'Screening poll failed: {exc}')
        return redirect('reviews:screening-dashboard', pk=review.pk)


class ScreeningStatusView(View):
    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        stage_progress = review.stage_progress or {}
        phase_7 = stage_progress.get('phase_7', {})
        phase_8 = stage_progress.get('phase_8', {})
        remaining = len(phase_7.get('remaining_paper_ids') or [])
        return JsonResponse(
            {
                'phase_7': phase_7,
                'phase_8': phase_8,
                'remaining': remaining,
                'is_terminal': bool(phase_8.get('status') in {'completed', 'error', 'stopped', 'no_eligible_papers'}),
            }
        )


class PollScreeningBatchApiView(View):
    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        try:
            result = poll_screening_batch(review_id=review.pk)
            return JsonResponse({'ok': True, 'result': result})
        except Exception as exc:
            return JsonResponse({'ok': False, 'error': str(exc)}, status=500)


class ScreeningDecisionReviewView(View):
    template_name = 'reviews/screening_decisions.html'

    _CONFIDENCE_BANDS = [
        ('all', 'All confidence values'),
        ('lt_70', 'Less than 0.70'),
        ('70_79', '0.70 to 0.79'),
        ('80_89', '0.80 to 0.89'),
        ('90_100', '0.90 to 1.00'),
    ]

    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        selected_decision = (request.GET.get('ta_decision') or 'all').strip().lower()
        selected_confidence = (request.GET.get('confidence_band') or 'all').strip().lower()

        papers = review.papers.order_by('id')
        papers = self._apply_decision_filter(papers, selected_decision)
        papers = self._apply_confidence_filter(papers, selected_confidence)

        decision_options = [('all', 'All decisions'), ('empty', 'empty (NULL)')] + list(Paper.TADecision.choices)

        return render(
            request,
            self.template_name,
            {
                'review': review,
                'papers': papers,
                'decision_options': decision_options,
                'confidence_bands': self._CONFIDENCE_BANDS,
                'selected_decision': selected_decision,
                'selected_confidence': selected_confidence,
                'default_override_decision': self._default_override_decision(selected_decision),
            },
        )

    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        selected_decision = (request.POST.get('current_ta_decision') or 'all').strip().lower()
        selected_confidence = (request.POST.get('current_confidence_band') or 'all').strip().lower()
        action = (request.POST.get('action') or 'single').strip().lower()

        if action == 'export_excel':
            return self._export_excel(request, review, selected_decision, selected_confidence)

        if action == 'bulk':
            return self._handle_bulk_update(request, review, selected_decision, selected_confidence)

        paper = get_object_or_404(Paper, pk=request.POST.get('paper_id'), review=review)
        decision = (request.POST.get('decision') or request.POST.get(f'decision_{paper.id}') or '').strip().lower()
        note = (request.POST.get('note') or request.POST.get(f'note_{paper.id}') or '').strip()

        allowed = {
            Paper.TADecision.INCLUDED,
            Paper.TADecision.EXCLUDED,
            Paper.TADecision.FLAGGED,
            Paper.TADecision.TEMP_FLAG,
            Paper.TADecision.MANUAL_FLAG,
            Paper.TADecision.MISSING_ABS,
            Paper.TADecision.NOT_PROCESSED,
            'empty',
        }
        if decision not in allowed:
            messages.error(request, 'Invalid decision value.')
            return self._redirect_with_filters(review.pk, selected_decision, selected_confidence)

        if decision == 'empty':
            paper.ta_decision = None
            paper.screening_conflict = False
            paper.ta_reason = note
        else:
            paper.ta_decision = decision
            paper.screening_conflict = False
            manual_reason = f'Manually set to {decision}.'
            if note:
                manual_reason = f'{manual_reason} {note}'

            if paper.ta_reason:
                paper.ta_reason = f'{paper.ta_reason} | {manual_reason}'
            else:
                paper.ta_reason = manual_reason

        paper.save(update_fields=['ta_decision', 'screening_conflict', 'ta_reason'])
        messages.success(request, f'Updated paper {paper.id} decision to {paper.ta_decision or "empty"}.')
        return self._redirect_with_filters(review.pk, selected_decision, selected_confidence)

    def _handle_bulk_update(self, request, review, selected_decision, selected_confidence):
        papers = review.papers.order_by('id')
        papers = self._apply_decision_filter(papers, selected_decision)
        papers = self._apply_confidence_filter(papers, selected_confidence)
        papers = list(papers.only('id', 'ta_reason'))

        allowed = {
            Paper.TADecision.INCLUDED,
            Paper.TADecision.EXCLUDED,
            Paper.TADecision.FLAGGED,
            Paper.TADecision.TEMP_FLAG,
            Paper.TADecision.MANUAL_FLAG,
            Paper.TADecision.MISSING_ABS,
            Paper.TADecision.NOT_PROCESSED,
            'empty',
            '',
        }
        updated = 0
        skipped = 0

        for paper in papers:
            decision = (request.POST.get(f'decision_{paper.id}') or '').strip().lower()
            note = (request.POST.get(f'note_{paper.id}') or '').strip()

            if decision == '':
                skipped += 1
                continue

            if decision not in allowed:
                messages.error(request, f'Invalid decision "{decision}" for paper {paper.id}.')
                return self._redirect_with_filters(review.pk, selected_decision, selected_confidence)

            if decision == 'empty':
                paper.ta_decision = None
                paper.screening_conflict = False
                paper.ta_reason = note
            else:
                paper.ta_decision = decision
                paper.screening_conflict = False
                manual_reason = f'Manually set to {decision}.'
                if note:
                    manual_reason = f'{manual_reason} {note}'

                if paper.ta_reason:
                    paper.ta_reason = f'{paper.ta_reason} | {manual_reason}'
                else:
                    paper.ta_reason = manual_reason

            paper.save(update_fields=['ta_decision', 'screening_conflict', 'ta_reason'])
            updated += 1

        messages.success(request, f'Bulk update complete. Updated: {updated}, skipped (blank): {skipped}.')
        return self._redirect_with_filters(review.pk, selected_decision, selected_confidence)

    def _apply_decision_filter(self, papers, selected_decision):
        valid = {choice[0] for choice in Paper.TADecision.choices}
        if selected_decision == 'all':
            return papers
        if selected_decision == 'empty':
            return papers.filter(ta_decision__isnull=True)
        if selected_decision in valid:
            return papers.filter(ta_decision=selected_decision)
        return papers

    def _apply_confidence_filter(self, papers, selected_confidence):
        if selected_confidence == 'lt_70':
            return papers.filter(ta_confidence__lt=0.7)
        if selected_confidence == '70_79':
            return papers.filter(ta_confidence__gte=0.7, ta_confidence__lt=0.8)
        if selected_confidence == '80_89':
            return papers.filter(ta_confidence__gte=0.8, ta_confidence__lt=0.9)
        if selected_confidence == '90_100':
            return papers.filter(ta_confidence__gte=0.9, ta_confidence__lte=1.0)
        return papers

    def _default_override_decision(self, selected_decision):
        valid = {choice[0] for choice in Paper.TADecision.choices}
        if selected_decision in valid:
            return selected_decision
        return ''

    def _redirect_with_filters(self, review_id, selected_decision, selected_confidence):
        query = urlencode(
            {
                'ta_decision': selected_decision or 'all',
                'confidence_band': selected_confidence or 'all',
            }
        )
        return redirect(f"{reverse('reviews:screening-decisions', kwargs={'pk': review_id})}?{query}")

    def _export_excel(self, request, review, selected_decision, selected_confidence):
        papers = review.papers.order_by('id')
        papers = self._apply_decision_filter(papers, selected_decision)
        papers = self._apply_confidence_filter(papers, selected_confidence)
        try:
            from openpyxl import Workbook
        except Exception:
            messages.error(request, 'Excel export requires openpyxl. Please install it in the active environment.')
            return self._redirect_with_filters(review.pk, selected_decision, selected_confidence)

        wb = Workbook()
        ws = wb.active
        ws.title = 'Abstract Screening Export'
        ws.append(['Title', 'Authors', 'Citation Count', 'Journal'])

        for paper in papers:
            ws.append([
                paper.title or '',
                paper.authors or '',
                paper.citation_count if paper.citation_count is not None else '',
                paper.journal or '',
            ])

        output = BytesIO()
        wb.save(output)
        output.seek(0)

        response = HttpResponse(
            output.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = (
            f'attachment; filename=review_{review.pk}_abstract_screening_{selected_decision or "all"}_{selected_confidence or "all"}.xlsx'
        )
        return response

class ScreeningExportView(View):
    template_name = 'reviews/screening_export.html'
    DEFAULT_EXPORT_BATCH_SIZE = 70

    def get(self, request, pk):
        if (request.GET.get('download_batch') or '').strip() == '1':
            return self._handle_download_batch(request, pk)

        review = get_object_or_404(Review, pk=pk)
        decision = (request.GET.get('decision') or '').strip().lower()
        batch_size = self.DEFAULT_EXPORT_BATCH_SIZE
        batch_links = []

        if decision:
            batch_links = self._build_batch_links(review=review, decision=decision, batch_size=batch_size)

        return render(
            request,
            self.template_name,
            {
                'review': review,
                'decision_choices': Paper.TADecision.choices,
                'batch_links': batch_links,
                'selected_export_decision': decision,
                'export_batch_size': batch_size,
            },
        )

    def post(self, request, pk):
        action = (request.POST.get('action') or 'download').strip().lower()
        if action == 'upload':
            return self._handle_upload(request, pk)
        return self._handle_download(request, pk)

    def _handle_download(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        decision = (request.POST.get('decision') or '').strip().lower()
        valid_decisions = {choice[0] for choice in Paper.TADecision.choices}
        if decision not in valid_decisions:
            messages.error(request, 'Invalid TA decision selected for export.')
            return redirect('reviews:screening-export', pk=review.pk)

        batch_links = self._build_batch_links(review=review, decision=decision, batch_size=self.DEFAULT_EXPORT_BATCH_SIZE)
        if not batch_links:
            messages.warning(request, 'No papers found for the selected TA decision.')

        query = urlencode({'decision': decision})
        return redirect(f"{reverse('reviews:screening-export', kwargs={'pk': review.pk})}?{query}")

    def _handle_download_batch(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        decision = (request.GET.get('decision') or '').strip().lower()
        batch_number_raw = (request.GET.get('batch') or '').strip()
        batch_size_raw = (request.GET.get('batch_size') or str(self.DEFAULT_EXPORT_BATCH_SIZE)).strip()

        valid_decisions = {choice[0] for choice in Paper.TADecision.choices}
        if decision not in valid_decisions:
            messages.error(request, 'Invalid TA decision selected for export.')
            return redirect('reviews:screening-export', pk=review.pk)

        try:
            batch_number = int(batch_number_raw)
            batch_size = int(batch_size_raw)
        except (TypeError, ValueError):
            messages.error(request, 'Invalid batch request parameters.')
            return redirect('reviews:screening-export', pk=review.pk)

        if batch_number < 1 or batch_size < 1:
            messages.error(request, 'Invalid batch request parameters.')
            return redirect('reviews:screening-export', pk=review.pk)

        all_papers = review.papers.filter(ta_decision=decision).order_by('id').values('title', 'abstract')
        total = all_papers.count()
        if total == 0:
            messages.warning(request, 'No papers found for the selected TA decision.')
            return redirect('reviews:screening-export', pk=review.pk)

        start_index = (batch_number - 1) * batch_size
        end_index = min(start_index + batch_size, total)

        if start_index >= total:
            messages.error(request, 'Batch number is out of range.')
            return redirect('reviews:screening-export', pk=review.pk)

        papers = all_papers[start_index:end_index]
        payload = [
            {
                'title': paper['title'],
                'abstract': paper['abstract'] or '',
            }
            for paper in papers
        ]

        start_display = start_index + 1
        end_display = end_index
        batch_label = f'batch_{batch_number:02d}_{start_display}-{end_display}'

        response_data = {
            'review_id': review.pk,
            'review_title': review.title,
            'ta_decision': decision,
            'batch': batch_number,
            'batch_label': batch_label,
            'range': f'{start_display}-{end_display}',
            'count': len(payload),
            'papers': payload,
        }

        response = HttpResponse(
            json.dumps(response_data, indent=2, ensure_ascii=False),
            content_type='application/json',
        )
        response['Content-Disposition'] = f'attachment; filename={batch_label}.json'
        return response

    def _build_batch_links(self, review, decision, batch_size):
        valid_decisions = {choice[0] for choice in Paper.TADecision.choices}
        if decision not in valid_decisions:
            return []

        total = review.papers.filter(ta_decision=decision).count()
        if total == 0:
            return []

        links = []
        batch_number = 1
        for start in range(1, total + 1, batch_size):
            end = min(start + batch_size - 1, total)
            batch_label = f'batch_{batch_number:02d}_{start}-{end}'
            query = urlencode(
                {
                    'download_batch': 1,
                    'decision': decision,
                    'batch': batch_number,
                    'batch_size': batch_size,
                }
            )
            url = f"{reverse('reviews:screening-export', kwargs={'pk': review.pk})}?{query}"
            links.append(
                {
                    'batch_number': batch_number,
                    'label': batch_label,
                    'start': start,
                    'end': end,
                    'count': end - start + 1,
                    'url': url,
                }
            )
            batch_number += 1

        return links

    def _handle_upload(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        uploaded = request.FILES.get('json_file')
        if not uploaded:
            messages.error(request, 'Please choose a JSON file to upload.')
            return redirect('reviews:screening-export', pk=review.pk)

        try:
            entries = json.loads(uploaded.read().decode('utf-8'))
        except Exception:
            messages.error(request, 'Uploaded file is not valid JSON.')
            return redirect('reviews:screening-export', pk=review.pk)

        if not isinstance(entries, list):
            messages.error(request, 'JSON root must be an array of objects.')
            return redirect('reviews:screening-export', pk=review.pk)

        valid_decisions = {choice[0] for choice in Paper.TADecision.choices}
        papers = list(review.papers.only('id', 'title'))
        by_title = {
            _normalize_title_for_match(paper.title): paper
            for paper in papers
            if _normalize_title_for_match(paper.title)
        }

        updated = 0
        missing = 0
        invalid = 0
        exact_matched = 0
        fuzzy_matched = 0
        unmatched_titles = []
        invalid_rows = []

        for index, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict):
                invalid += 1
                invalid_rows.append(f'Row {index}: entry is not an object')
                continue

            incoming_title = (entry.get('Title') or entry.get('title') or '').strip()
            norm_title = _normalize_title_for_match(incoming_title)

            paper = by_title.get(norm_title)
            match_mode = 'exact' if paper else None

            if not paper and norm_title:
                best_paper = None
                best_score = 0.0
                for candidate_norm, candidate_paper in by_title.items():
                    score = SequenceMatcher(None, norm_title, candidate_norm).ratio() * 100
                    if score > best_score:
                        best_score = score
                        best_paper = candidate_paper
                if best_paper and best_score >= 95.0:
                    paper = best_paper
                    match_mode = f'fuzzy:{best_score:.2f}'

            if not paper:
                missing += 1
                unmatched_titles.append(incoming_title or f'(row {index} no title)')
                continue

            decision = str(entry.get('decision', '')).strip().lower()
            if decision not in valid_decisions:
                invalid += 1
                invalid_rows.append(f'Row {index}: invalid decision "{decision}" for title "{incoming_title}"')
                continue

            confidence = entry.get('confidence')
            rq_tag = str(entry.get('rq_tag', '')).strip()
            reason = str(entry.get('reason', '')).strip()
            criterion = str(entry.get('criterion', '')).strip() or str(entry.get('criterion_failed', '')).strip()

            try:
                confidence_value = float(confidence) if confidence is not None else 0.0
            except (TypeError, ValueError):
                confidence_value = 0.0

            reason_parts = []
            if rq_tag:
                reason_parts.append(f'RQ Tag: {rq_tag}')
            if reason:
                reason_parts.append(f'Reason: {reason}')
            if criterion:
                reason_parts.append(f'Criterion: {criterion}')
            merged_reason = ' | '.join(reason_parts)

            paper.ta_decision = decision
            paper.ta_confidence = confidence_value
            paper.ta_reason = merged_reason
            paper.screening_conflict = False
            paper.save(update_fields=['ta_decision', 'ta_confidence', 'ta_reason', 'screening_conflict'])
            updated += 1
            if match_mode == 'exact':
                exact_matched += 1
            else:
                fuzzy_matched += 1

        total_entries = len(entries)
        messages.success(
            request,
            f'JSON upload processed. Total rows: {total_entries}, Updated: {updated}, Exact matched: {exact_matched}, Fuzzy matched (>=95%): {fuzzy_matched}, Title not matched: {missing}, Invalid rows: {invalid}.',
        )

        if unmatched_titles:
            preview = '; '.join(unmatched_titles[:20])
            extra = '' if len(unmatched_titles) <= 20 else f' ... (+{len(unmatched_titles) - 20} more)'
            messages.warning(request, f'Unmatched titles: {preview}{extra}')

        if invalid_rows:
            preview = '; '.join(invalid_rows[:10])
            extra = '' if len(invalid_rows) <= 10 else f' ... (+{len(invalid_rows) - 10} more)'
            messages.warning(request, f'Invalid row details: {preview}{extra}')

        return redirect('reviews:screening-export', pk=review.pk)

class ScreeningConflictView(View):
    template_name = 'reviews/screening_conflicts.html'

    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        conflicts = review.papers.filter(screening_conflict=True).order_by('id')
        return render(
            request,
            self.template_name,
            {
                'review': review,
                'research_questions': review.research_questions.order_by('id'),
                'conflicts': conflicts,
            },
        )

    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        paper = get_object_or_404(Paper, pk=request.POST.get('paper_id'), review=review)
        action = request.POST.get('decision', '').lower().strip()

        if action not in {Paper.TADecision.INCLUDED, Paper.TADecision.EXCLUDED}:
            messages.error(request, 'Invalid action.')
            return redirect('reviews:screening-conflicts', pk=review.pk)

        paper.ta_decision = action
        paper.screening_conflict = False
        if paper.ta_reason:
            paper.ta_reason = f'{paper.ta_reason} | Manually confirmed as {action}.'
        else:
            paper.ta_reason = f'Manually confirmed as {action}.'
        paper.save(update_fields=['ta_decision', 'screening_conflict', 'ta_reason'])

        messages.success(request, f'Paper "{paper.title[:60]}" set to {action} and conflict cleared.')
        return redirect('reviews:screening-conflicts', pk=review.pk)


def _ordered_queries(review):
    queries = list(review.search_queries.filter(focus__in=_ACTIVE_FOCUS_ORDER))
    return sorted(queries, key=lambda item: _ACTIVE_FOCUS_ORDER.index(item.focus) if item.focus in _ACTIVE_FOCUS_ORDER else 99)


def _aggregate_upload_report(review):
    queries = review.search_queries.filter(focus__in=_ACTIVE_FOCUS_ORDER)
    total = sum(item.imported_records for item in queries)
    missing = sum(item.missing_abstracts for item in queries)
    return {
        'total_papers_imported': total,
        'duplicates_removed': 0,
        'missing_abstracts_flagged': missing,
    }


def _save_ingest_report(review, final_report, dedupe_report):
    stage_progress = review.stage_progress or {}
    stage_progress['phase_5'] = 'ingested_and_deduped'
    stage_progress['phase_5_report'] = {
        'ingest_quality': final_report,
        'prisma_counts': {
            'scopus_retrieved': dedupe_report['total_before_dedupe'],
            'after_dedup': dedupe_report['total_after_dedupe'],
            'missing_abstracts': dedupe_report['missing_abstracts_flagged'],
        },
    }
    review.stage_progress = stage_progress
    review.save(update_fields=['stage_progress'])


def _get_saved_ingest_report(review):
    stage_progress = review.stage_progress or {}
    phase_5_report = stage_progress.get('phase_5_report', {})
    if isinstance(phase_5_report, dict):
        ingest_quality = phase_5_report.get('ingest_quality')
        if isinstance(ingest_quality, dict):
            return ingest_quality
    return None



















































