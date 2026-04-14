import json
import os
import tempfile
import time
import threading
import traceback

from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.conf import settings
from django.utils import timezone
from django.views import View

from reviews.lit_review_forms import LitExcelUploadForm, LitNumberedPDFUploadForm, LitRISUploadForm, LitReviewStage1Form
from reviews.models import LitPaper, LitPaperAssignment, LitReview, ReviewSection
from reviews.services.lit_intake_service import (
    attach_numbered_pdfs_for_lit_review,
    download_missing_pdfs_for_lit_review,
    finalize_verified_title_extract_rows_for_lit_review,
    ingest_excel_for_lit_review,
    ingest_ris_for_lit_review,
    resolve_and_download_missing_pdfs_for_lit_review,
    stage_and_extract_titles_from_uploaded_pdfs_for_lit_review,
)
from reviews.services.lit_citation_service import generate_apa_citations_for_lit_review
from reviews.services.lit_mineru_service import clean_existing_lit_mineru_references, parse_lit_review_pdfs_with_mineru
from reviews.services.lit_per_paper_extraction_service import run_lit_per_paper_extraction_for_review
from reviews.services.lit_review_stage1_service import generate_lit_review_stage1_plan
from reviews.services.lit_section_writing_service import run_lit_stage5_writing_for_review
from reviews.services.lit_section_assignment_service import run_lit_section_assignment_for_review
from reviews.services.lit_stitching_service import run_lit_stage5b_stitch_for_review
from reviews.services.lit_references_service import run_lit_stage5c_references_for_review

_LIT_MINERU_WORKERS = {}
_LIT_PER_PAPER_WORKERS = {}
_LIT_ASSIGN_WORKERS = {}
_LIT_STAGE5_WORKERS = {}
_LIT_STAGE5B_WORKERS = {}
_LIT_STAGE5C_WORKERS = {}


class LitReviewStage1CreateView(View):
    template_name = 'reviews/lit_review_stage1_form.html'

    def get(self, request):
        return render(request, self.template_name, {'form': LitReviewStage1Form()})

    def post(self, request):
        form = LitReviewStage1Form(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form}, status=400)

        research_context = form.cleaned_data['research_context']
        questions = form.cleaned_data['research_questions']
        primary_question = questions[0]
        lit_review = form.save(commit=False)
        if request.user.is_authenticated:
            lit_review.user = request.user
        lit_review.research_context = research_context
        lit_review.research_questions = questions
        lit_review.research_question = primary_question
        lit_review.status = LitReview.Status.PLANNING
        lit_review.save()

        try:
            plan = generate_lit_review_stage1_plan(
                research_context=research_context,
                research_questions=questions,
                target_word_count=lit_review.target_word_count,
            )
            _persist_stage1_plan(lit_review=lit_review, plan=plan)
            messages.success(request, 'Stage 1 completed: structure plan generated.')
            return redirect('lit_reviews:stage1-detail', pk=lit_review.pk)
        except Exception as exc:
            lit_review.delete()
            messages.error(request, f'Stage 1 failed: {exc}')
            return render(request, self.template_name, {'form': form}, status=500)


class LitReviewStage1DetailView(View):
    template_name = 'reviews/lit_review_stage1_detail.html'

    def get(self, request, pk):
        lit_review = get_object_or_404(LitReview, pk=pk)
        sections = lit_review.sections.all().order_by('number', 'id')
        return render(
            request,
            self.template_name,
            {
                'lit_review': lit_review,
                'sections': sections,
            },
        )


class LitReviewStage2IntakeView(View):
    template_name = 'reviews/lit_review_stage2_intake.html'

    def get(self, request, pk):
        lit_review = get_object_or_404(LitReview, pk=pk)
        excel_pdf_status = (request.GET.get('excel_pdf_status') or 'all').strip().lower()
        excel_title_search = (request.GET.get('excel_title_search') or '').strip()
        papers = self._excel_filtered_papers(
            lit_review=lit_review,
            pdf_status=excel_pdf_status,
            title_search=excel_title_search,
        )
        return render(
            request,
            self.template_name,
            {
                'lit_review': lit_review,
                'papers': papers,
                'excel_pdf_status': excel_pdf_status,
                'excel_title_search': excel_title_search,
                'resolver_stage': _get_lit_resolver_stage_snapshot(lit_review),
                'citation_stage': _get_lit_citation_stage_snapshot(lit_review),
                'title_extract_stage': _get_lit_title_extract_stage_snapshot(lit_review),
                'ris_form': LitRISUploadForm(),
                'excel_form': LitExcelUploadForm(),
                'numbered_pdf_form': LitNumberedPDFUploadForm(),
                'stats': self._stats(lit_review),
            },
        )

    def post(self, request, pk):
        lit_review = get_object_or_404(LitReview, pk=pk)
        action = (request.POST.get('action') or '').strip().lower()

        if action == 'upload_ris':
            form = LitRISUploadForm(request.POST, request.FILES)
            if not form.is_valid():
                messages.error(request, 'Please upload a valid RIS file.')
                return redirect('lit_reviews:stage2-intake', pk=lit_review.pk)

            uploaded = form.cleaned_data['ris_file']
            temp_path = self._save_temp_file(uploaded, suffix='.ris')
            try:
                report = ingest_ris_for_lit_review(review_id=lit_review.id, file_path=temp_path)
                messages.success(
                    request,
                    f"RIS import done. Created: {report['created']}, skipped: {report['skipped']}, rows: {report['total_rows']}.",
                )
            except Exception as exc:
                messages.error(request, f'RIS import failed: {exc}')
            finally:
                self._safe_remove_temp_path(temp_path)
            return redirect('lit_reviews:stage2-intake', pk=lit_review.pk)

        if action == 'upload_excel':
            form = LitExcelUploadForm(request.POST, request.FILES)
            if not form.is_valid():
                messages.error(request, 'Please upload a valid Excel file.')
                return redirect('lit_reviews:stage2-intake', pk=lit_review.pk)

            uploaded = form.cleaned_data['excel_file']
            suffix = os.path.splitext(uploaded.name or '')[1] or '.xlsx'
            temp_path = self._save_temp_file(uploaded, suffix=suffix)
            try:
                report = ingest_excel_for_lit_review(review_id=lit_review.id, file_path=temp_path)
                messages.success(
                    request,
                    f"Excel import done. Created: {report['created']}, skipped: {report['skipped']}, rows: {report['total_rows']}.",
                )
            except Exception as exc:
                messages.error(request, f'Excel import failed: {exc}')
            finally:
                self._safe_remove_temp_path(temp_path)
            return redirect('lit_reviews:stage2-intake', pk=lit_review.pk)

        if action == 'upload_numbered_pdfs':
            files = request.FILES.getlist('pdf_files')
            if not files:
                messages.error(request, 'Please upload one or more PDF files.')
                return redirect('lit_reviews:stage2-intake', pk=lit_review.pk)
            try:
                report = attach_numbered_pdfs_for_lit_review(review_id=lit_review.id, uploaded_files=files)
                messages.success(
                    request,
                    f"Numbered PDF mapping complete. Matched: {report['matched']}, unmatched: {report['unmatched']}, errors: {report['errors']}.",
                )
            except Exception as exc:
                messages.error(request, f'Numbered PDF upload failed: {exc}')
            return redirect('lit_reviews:stage2-intake', pk=lit_review.pk)

        if action == 'download_links':
            try:
                report = download_missing_pdfs_for_lit_review(review_id=lit_review.id)
                messages.success(
                    request,
                    f"Link download completed. Targeted: {report['targeted']}, downloaded: {report['downloaded']}, skipped: {report['skipped']}, failed: {report['failed']}.",
                )
            except Exception as exc:
                messages.error(request, f'PDF download from links failed: {exc}')
            return redirect('lit_reviews:stage2-intake', pk=lit_review.pk)

        if action == 'resolve_missing_pdfs':
            stage = _get_lit_resolver_stage_snapshot(lit_review)
            if stage.get('status') in {'running', 'queued', 'stopping'}:
                messages.warning(request, 'Resolver is already running.')
                return redirect('lit_reviews:stage2-intake', pk=lit_review.pk)

            initial = {
                'status': 'running',
                'started_at': timezone.now().isoformat(),
                'targeted': 0,
                'processed': 0,
                'resolved': 0,
                'downloaded': 0,
                'failed': 0,
                'processed_paper_ids': [],
                'remaining_paper_ids': [],
                'logs': [],
                'error_code': '',
                'error_message': '',
                'error_traceback': '',
                'stop_requested': False,
            }
            _set_lit_resolver_stage_snapshot(lit_review, initial)
            worker = threading.Thread(target=_run_lit_resolver_async, args=(lit_review.pk,), daemon=True)
            worker.start()
            messages.success(request, 'Resolver started. Live status is shown below.')
            return redirect('lit_reviews:stage2-intake', pk=lit_review.pk)

        if action == 'upload_extract_titles':
            files = request.FILES.getlist('title_extract_pdf_files')
            if not files:
                messages.error(request, 'Please upload one or more PDFs for title extraction.')
                return redirect('lit_reviews:stage2-intake', pk=lit_review.pk)
            try:
                stage_report = stage_and_extract_titles_from_uploaded_pdfs_for_lit_review(
                    review_id=lit_review.id,
                    uploaded_files=files,
                )
                _set_lit_title_extract_stage_snapshot(lit_review, stage_report)
                messages.success(
                    request,
                    f"Title extraction completed. Ready: {stage_report.get('ready_count', 0)}, errors: {stage_report.get('error_count', 0)}.",
                )
            except Exception as exc:
                messages.error(request, f'PDF title extraction failed: {exc}')
            return redirect('lit_reviews:stage2-intake', pk=lit_review.pk)

        if action == 'confirm_extracted_titles':
            stage = _get_lit_title_extract_stage_snapshot(lit_review)
            stage_rows = stage.get('rows') or []
            if not stage_rows:
                messages.warning(request, 'No extracted titles found to confirm.')
                return redirect('lit_reviews:stage2-intake', pk=lit_review.pk)

            confirmations = []
            for row in stage_rows:
                row_id = str(row.get('row_id') or '')
                confirmations.append(
                    {
                        'row_id': row_id,
                        'original_name': row.get('original_name') or '',
                        'staged_relative_path': row.get('staged_relative_path') or '',
                        'verified_title': (request.POST.get(f'verified_title_{row_id}') or row.get('extracted_title') or '').strip(),
                        'include': request.POST.get(f'include_{row_id}') == 'on',
                    }
                )

            try:
                result = finalize_verified_title_extract_rows_for_lit_review(
                    review_id=lit_review.id,
                    rows=confirmations,
                )
                _set_lit_title_extract_stage_snapshot(lit_review, {'rows': []})
                messages.success(
                    request,
                    f"Verified titles saved. Created: {result['created']}, skipped: {result['skipped']}, errors: {result['errors']}.",
                )
            except Exception as exc:
                messages.error(request, f'Confirming extracted titles failed: {exc}')
            return redirect('lit_reviews:stage2-intake', pk=lit_review.pk)

        if action == 'generate_apa_citations':
            only_missing = (request.POST.get('only_missing') or '1').strip() == '1'
            stage = _get_lit_citation_stage_snapshot(lit_review)
            if stage.get('status') in {'running', 'queued', 'stopping'}:
                messages.warning(request, 'APA citation generation is already running.')
                return redirect('lit_reviews:stage2-intake', pk=lit_review.pk)

            initial = {
                'status': 'running',
                'started_at': timezone.now().isoformat(),
                'targeted': 0,
                'processed': 0,
                'done': 0,
                'failed': 0,
                'processed_paper_ids': [],
                'remaining_paper_ids': [],
                'logs': [],
                'error_code': '',
                'error_message': '',
                'error_traceback': '',
                'stop_requested': False,
                'only_missing': only_missing,
            }
            _set_lit_citation_stage_snapshot(lit_review, initial)
            worker = threading.Thread(target=_run_lit_citation_async, args=(lit_review.pk, only_missing), daemon=True)
            worker.start()
            messages.success(request, 'APA citation generation started. Live status is shown below.')
            return redirect('lit_reviews:stage2-intake', pk=lit_review.pk)

        messages.error(request, 'Invalid action.')
        return redirect('lit_reviews:stage2-intake', pk=lit_review.pk)

    def _save_temp_file(self, uploaded_file, suffix):
        os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=settings.MEDIA_ROOT) as temp_file:
            for chunk in uploaded_file.chunks():
                temp_file.write(chunk)
            return temp_file.name

    def _safe_remove_temp_path(self, path):
        if not path or not os.path.exists(path):
            return
        for attempt in range(1, 6):
            try:
                os.remove(path)
                return
            except PermissionError:
                time.sleep(0.2 * attempt)
            except OSError:
                return

    def _stats(self, lit_review):
        qs = lit_review.papers.all()
        return {
            'total': qs.count(),
            'ris': qs.filter(origin=LitPaper.Origin.RIS_UPLOAD).count(),
            'excel': qs.filter(origin=LitPaper.Origin.EXCEL_UPLOAD).count(),
            'pdf_upload': qs.filter(origin=LitPaper.Origin.PDF_UPLOAD).count(),
            'retrieved': qs.filter(fulltext_retrieved=True).count(),
            'pending_pdf': qs.filter(fulltext_retrieved=False).count(),
        }

    def _excel_filtered_papers(self, *, lit_review, pdf_status, title_search):
        qs = lit_review.papers.filter(origin=LitPaper.Origin.EXCEL_UPLOAD).order_by('excel_row_index', 'id')
        if pdf_status == 'downloaded':
            qs = qs.filter(fulltext_retrieved=True)
        elif pdf_status == 'missing':
            qs = qs.filter(fulltext_retrieved=False)
        if title_search:
            qs = qs.filter(title__icontains=title_search)
        return qs


class LitReviewResolverStatusView(View):
    def get(self, request, pk):
        lit_review = get_object_or_404(LitReview, pk=pk)
        return JsonResponse(_get_lit_resolver_stage_snapshot(lit_review))


class LitReviewCitationStatusView(View):
    def get(self, request, pk):
        lit_review = get_object_or_404(LitReview, pk=pk)
        return JsonResponse(_get_lit_citation_stage_snapshot(lit_review))


class LitReviewMinerUMonitorView(View):
    template_name = 'reviews/lit_review_mineru_monitor.html'

    def get(self, request, pk):
        lit_review = get_object_or_404(LitReview, pk=pk)
        stage = _get_lit_mineru_stage_snapshot(lit_review)
        return render(request, self.template_name, {'lit_review': lit_review, 'stage': stage})

    def post(self, request, pk):
        lit_review = get_object_or_404(LitReview, pk=pk)
        stage = _get_lit_mineru_stage_snapshot(lit_review)
        action = (request.POST.get('action') or 'process_not_done').strip().lower()
        worker_alive = _is_lit_mineru_worker_alive(lit_review.pk)

        if action == 'stop':
            if stage.get('status') not in {'running', 'queued', 'stopping'}:
                messages.warning(request, 'No active MinerU run is in progress.')
                return redirect('lit_reviews:stage3-mineru-monitor', pk=lit_review.pk)
            stage['status'] = 'stopping'
            stage['stop_requested'] = True
            stage['stop_requested_at'] = timezone.now().isoformat()
            _set_lit_mineru_stage_snapshot(lit_review, stage)
            messages.success(request, 'Stop requested for MinerU processing.')
            return redirect('lit_reviews:stage3-mineru-monitor', pk=lit_review.pk)

        if stage.get('status') in {'running', 'queued', 'stopping'} and worker_alive:
            messages.warning(request, 'MinerU processing is already running.')
            return redirect('lit_reviews:stage3-mineru-monitor', pk=lit_review.pk)
        if stage.get('status') in {'running', 'queued', 'stopping'} and not worker_alive:
            # Recover stale status left behind by a dead worker.
            stage['status'] = 'stopped'
            stage['completed_at'] = timezone.now().isoformat()
            _set_lit_mineru_stage_snapshot(lit_review, stage)

        retry_failed_only = action == 'retry_failed'
        run_ref_delete = action == 'run_ref_delete'
        job_type = 'ref_delete' if run_ref_delete else 'parse'
        initial = {
            'status': 'running',
            'job_type': job_type,
            'started_at': timezone.now().isoformat(),
            'targeted': 0,
            'processed': 0,
            'done': 0,
            'failed': 0,
            'processed_paper_ids': [],
            'remaining_paper_ids': [],
            'stop_requested': False,
            'stop_requested_at': '',
            'error_code': '',
            'error_message': '',
            'error_traceback': '',
            'logs': [],
            'retry_failed_only': retry_failed_only,
        }
        _set_lit_mineru_stage_snapshot(lit_review, initial)
        worker = threading.Thread(
            target=_run_lit_mineru_async,
            args=(lit_review.pk, retry_failed_only, run_ref_delete),
            daemon=True,
        )
        _LIT_MINERU_WORKERS[lit_review.pk] = worker
        worker.start()
        if run_ref_delete:
            messages.success(request, 'MinerU reference cleanup started for markdown records not yet cleaned.')
        else:
            messages.success(request, 'MinerU markdown parsing started.')
        return redirect('lit_reviews:stage3-mineru-monitor', pk=lit_review.pk)


class LitReviewMinerUStatusView(View):
    def get(self, request, pk):
        lit_review = get_object_or_404(LitReview, pk=pk)
        stage = _get_lit_mineru_stage_snapshot(lit_review)
        if stage.get('status') in {'running', 'queued', 'stopping'} and not _is_lit_mineru_worker_alive(lit_review.pk):
            stage['status'] = 'stopped'
            stage['completed_at'] = timezone.now().isoformat()
            _set_lit_mineru_stage_snapshot(lit_review, stage)
        return JsonResponse(_get_lit_mineru_stage_snapshot(lit_review))


class LitReviewPerPaperExtractionMonitorView(View):
    template_name = 'reviews/lit_review_stage4_extraction_monitor.html'

    def get(self, request, pk):
        lit_review = get_object_or_404(LitReview, pk=pk)
        stage = _get_lit_per_paper_stage_snapshot(lit_review)
        completed = _lit_per_paper_completed_rows(lit_review)
        return render(request, self.template_name, {'lit_review': lit_review, 'stage': stage, 'completed': completed})

    def post(self, request, pk):
        lit_review = get_object_or_404(LitReview, pk=pk)
        stage = _get_lit_per_paper_stage_snapshot(lit_review)
        action = (request.POST.get('action') or 'process_not_done').strip().lower()
        worker_alive = _is_lit_per_paper_worker_alive(lit_review.pk)

        if action == 'stop':
            if stage.get('status') not in {'running', 'queued', 'stopping'}:
                messages.warning(request, 'No active per-paper extraction run is in progress.')
                return redirect('lit_reviews:stage4-extraction-monitor', pk=lit_review.pk)
            stage['status'] = 'stopping'
            stage['stop_requested'] = True
            stage['stop_requested_at'] = timezone.now().isoformat()
            _set_lit_per_paper_stage_snapshot(lit_review, stage)
            messages.success(request, 'Stop requested for per-paper extraction.')
            return redirect('lit_reviews:stage4-extraction-monitor', pk=lit_review.pk)

        if stage.get('status') in {'running', 'queued', 'stopping'} and worker_alive:
            messages.warning(request, 'Per-paper extraction is already running.')
            return redirect('lit_reviews:stage4-extraction-monitor', pk=lit_review.pk)
        if stage.get('status') in {'running', 'queued', 'stopping'} and not worker_alive:
            stage['status'] = 'stopped'
            stage['completed_at'] = timezone.now().isoformat()
            _set_lit_per_paper_stage_snapshot(lit_review, stage)

        retry_failed_only = action == 'retry_failed'
        initial = {
            'status': 'running',
            'started_at': timezone.now().isoformat(),
            'targeted': 0,
            'processed': 0,
            'done': 0,
            'failed': 0,
            'processed_paper_ids': [],
            'remaining_paper_ids': [],
            'stop_requested': False,
            'stop_requested_at': '',
            'error_code': '',
            'error_message': '',
            'error_traceback': '',
            'logs': [],
            'retry_failed_only': retry_failed_only,
        }
        _set_lit_per_paper_stage_snapshot(lit_review, initial)
        worker = threading.Thread(
            target=_run_lit_per_paper_async,
            args=(lit_review.pk, retry_failed_only),
            daemon=True,
        )
        _LIT_PER_PAPER_WORKERS[lit_review.pk] = worker
        worker.start()
        if retry_failed_only:
            messages.success(request, 'Per-paper extraction retry for failed papers started.')
        else:
            messages.success(request, 'Per-paper extraction started.')
        return redirect('lit_reviews:stage4-extraction-monitor', pk=lit_review.pk)


class LitReviewPerPaperExtractionStatusView(View):
    def get(self, request, pk):
        lit_review = get_object_or_404(LitReview, pk=pk)
        stage = _get_lit_per_paper_stage_snapshot(lit_review)
        if stage.get('status') in {'running', 'queued', 'stopping'} and not _is_lit_per_paper_worker_alive(lit_review.pk):
            stage['status'] = 'stopped'
            stage['completed_at'] = timezone.now().isoformat()
            _set_lit_per_paper_stage_snapshot(lit_review, stage)
        payload = _get_lit_per_paper_stage_snapshot(lit_review)
        payload['completed'] = _lit_per_paper_completed_rows(lit_review)
        return JsonResponse(payload)


class LitReviewSectionAssignmentMonitorView(View):
    template_name = 'reviews/lit_review_stage4b_assignment_monitor.html'

    def get(self, request, pk):
        lit_review = get_object_or_404(LitReview, pk=pk)
        stage = _get_lit_assignment_stage_snapshot(lit_review)
        assignments = _lit_assignment_rows(lit_review)
        return render(
            request,
            self.template_name,
            {'lit_review': lit_review, 'stage': stage, 'assignments': assignments},
        )

    def post(self, request, pk):
        lit_review = get_object_or_404(LitReview, pk=pk)
        stage = _get_lit_assignment_stage_snapshot(lit_review)
        action = (request.POST.get('action') or 'process_not_done').strip().lower()
        worker_alive = _is_lit_assignment_worker_alive(lit_review.pk)

        if action == 'stop':
            if stage.get('status') not in {'running', 'queued', 'stopping'}:
                messages.warning(request, 'No active section-assignment run is in progress.')
                return redirect('lit_reviews:stage4b-assignment-monitor', pk=lit_review.pk)
            stage['status'] = 'stopping'
            stage['stop_requested'] = True
            stage['stop_requested_at'] = timezone.now().isoformat()
            _set_lit_assignment_stage_snapshot(lit_review, stage)
            messages.success(request, 'Stop requested for section assignment.')
            return redirect('lit_reviews:stage4b-assignment-monitor', pk=lit_review.pk)

        if stage.get('status') in {'running', 'queued', 'stopping'} and worker_alive:
            messages.warning(request, 'Section assignment is already running.')
            return redirect('lit_reviews:stage4b-assignment-monitor', pk=lit_review.pk)
        if stage.get('status') in {'running', 'queued', 'stopping'} and not worker_alive:
            stage['status'] = 'stopped'
            stage['completed_at'] = timezone.now().isoformat()
            _set_lit_assignment_stage_snapshot(lit_review, stage)

        reassign_all = action == 'reassign_all'
        initial = {
            'status': 'running',
            'started_at': timezone.now().isoformat(),
            'targeted': 0,
            'processed': 0,
            'done': 0,
            'failed': 0,
            'processed_paper_ids': [],
            'remaining_paper_ids': [],
            'missing_section_numbers': [],
            'too_tangential_count': 0,
            'stop_requested': False,
            'stop_requested_at': '',
            'error_code': '',
            'error_message': '',
            'error_traceback': '',
            'logs': [],
            'reassign_all': reassign_all,
        }
        _set_lit_assignment_stage_snapshot(lit_review, initial)
        worker = threading.Thread(
            target=_run_lit_assignment_async,
            args=(lit_review.pk, reassign_all),
            daemon=True,
        )
        _LIT_ASSIGN_WORKERS[lit_review.pk] = worker
        worker.start()

        if reassign_all:
            messages.success(request, 'Section assignment started (reassign all).')
        else:
            messages.success(request, 'Section assignment started for unassigned papers.')
        return redirect('lit_reviews:stage4b-assignment-monitor', pk=lit_review.pk)


class LitReviewSectionAssignmentStatusView(View):
    def get(self, request, pk):
        lit_review = get_object_or_404(LitReview, pk=pk)
        stage = _get_lit_assignment_stage_snapshot(lit_review)
        if stage.get('status') in {'running', 'queued', 'stopping'} and not _is_lit_assignment_worker_alive(lit_review.pk):
            stage['status'] = 'stopped'
            stage['completed_at'] = timezone.now().isoformat()
            _set_lit_assignment_stage_snapshot(lit_review, stage)
        payload = _get_lit_assignment_stage_snapshot(lit_review)
        payload['assignments'] = _lit_assignment_rows(lit_review)
        return JsonResponse(payload)


class LitReviewStage5WritingMonitorView(View):
    template_name = 'reviews/lit_review_stage5_writing_monitor.html'

    def get(self, request, pk):
        lit_review = get_object_or_404(LitReview, pk=pk)
        stage = _get_lit_stage5_snapshot(lit_review)
        sections = _lit_stage5_section_rows(lit_review)
        return render(request, self.template_name, {'lit_review': lit_review, 'stage': stage, 'sections': sections})

    def post(self, request, pk):
        lit_review = get_object_or_404(LitReview, pk=pk)
        stage = _get_lit_stage5_snapshot(lit_review)
        action = (request.POST.get('action') or 'write_remaining').strip().lower()
        worker_alive = _is_lit_stage5_worker_alive(lit_review.pk)

        if action == 'stop':
            if stage.get('status') not in {'running', 'queued', 'stopping'}:
                messages.warning(request, 'No active Stage 5a run is in progress.')
                return redirect('lit_reviews:stage5-writing-monitor', pk=lit_review.pk)
            stage['status'] = 'stopping'
            stage['stop_requested'] = True
            stage['stop_requested_at'] = timezone.now().isoformat()
            _set_lit_stage5_snapshot(lit_review, stage)
            messages.success(request, 'Stop requested for Stage 5a section writing.')
            return redirect('lit_reviews:stage5-writing-monitor', pk=lit_review.pk)

        if stage.get('status') in {'running', 'queued', 'stopping'} and worker_alive:
            messages.warning(request, 'Stage 5a writing is already running.')
            return redirect('lit_reviews:stage5-writing-monitor', pk=lit_review.pk)
        if stage.get('status') in {'running', 'queued', 'stopping'} and not worker_alive:
            stage['status'] = 'stopped'
            stage['completed_at'] = timezone.now().isoformat()
            _set_lit_stage5_snapshot(lit_review, stage)

        rewrite_all = action == 'rewrite_all'

        initial = {
            'status': 'running',
            'started_at': timezone.now().isoformat(),
            'targeted': 0,
            'processed': 0,
            'done': 0,
            'failed': 0,
            'processed_section_ids': [],
            'remaining_section_ids': [],
            'actual_total_words': 0,
            'target_total_words': int(lit_review.total_words_allocated or 0),
            'drift_pct': 0.0,
            'drift_warning': False,
            'stop_requested': False,
            'stop_requested_at': '',
            'error_code': '',
            'error_message': '',
            'error_traceback': '',
            'logs': [],
            'rewrite_all': rewrite_all,
        }
        _set_lit_stage5_snapshot(lit_review, initial)
        worker = threading.Thread(
            target=_run_lit_stage5_async,
            args=(lit_review.pk, rewrite_all),
            daemon=True,
        )
        _LIT_STAGE5_WORKERS[lit_review.pk] = worker
        worker.start()
        if rewrite_all:
            messages.success(request, 'Stage 5a writing started (rewrite all sections).')
        else:
            messages.success(request, 'Stage 5a writing started (remaining sections only).')
        return redirect('lit_reviews:stage5-writing-monitor', pk=lit_review.pk)


class LitReviewStage5WritingStatusView(View):
    def get(self, request, pk):
        lit_review = get_object_or_404(LitReview, pk=pk)
        stage = _get_lit_stage5_snapshot(lit_review)
        if stage.get('status') in {'running', 'queued', 'stopping'} and not _is_lit_stage5_worker_alive(lit_review.pk):
            stage['status'] = 'stopped'
            stage['completed_at'] = timezone.now().isoformat()
            _set_lit_stage5_snapshot(lit_review, stage)
        payload = _get_lit_stage5_snapshot(lit_review)
        payload['sections'] = _lit_stage5_section_rows(lit_review)
        return JsonResponse(payload)


class LitReviewStage5BStitchMonitorView(View):
    template_name = 'reviews/lit_review_stage5b_stitch_monitor.html'

    def get(self, request, pk):
        lit_review = get_object_or_404(LitReview, pk=pk)
        stage = _get_lit_stage5b_snapshot(lit_review)
        return render(request, self.template_name, {'lit_review': lit_review, 'stage': stage})

    def post(self, request, pk):
        lit_review = get_object_or_404(LitReview, pk=pk)
        stage = _get_lit_stage5b_snapshot(lit_review)
        action = (request.POST.get('action') or 'stitch').strip().lower()
        worker_alive = _is_lit_stage5b_worker_alive(lit_review.pk)

        if action == 'stop':
            if stage.get('status') not in {'running', 'queued', 'stopping'}:
                messages.warning(request, 'No active Stage 5b stitching run is in progress.')
                return redirect('lit_reviews:stage5b-stitch-monitor', pk=lit_review.pk)
            stage['status'] = 'stopping'
            stage['stop_requested'] = True
            stage['stop_requested_at'] = timezone.now().isoformat()
            _set_lit_stage5b_snapshot(lit_review, stage)
            messages.success(request, 'Stop requested for Stage 5b stitching.')
            return redirect('lit_reviews:stage5b-stitch-monitor', pk=lit_review.pk)

        if stage.get('status') in {'running', 'queued', 'stopping'} and worker_alive:
            messages.warning(request, 'Stage 5b stitching is already running.')
            return redirect('lit_reviews:stage5b-stitch-monitor', pk=lit_review.pk)
        if stage.get('status') in {'running', 'queued', 'stopping'} and not worker_alive:
            stage['status'] = 'stopped'
            stage['completed_at'] = timezone.now().isoformat()
            _set_lit_stage5b_snapshot(lit_review, stage)

        initial = {
            'status': 'running',
            'started_at': timezone.now().isoformat(),
            'sections_count': 0,
            'final_words': 0,
            'intro_words': 0,
            'closing_words': 0,
            'stop_requested': False,
            'stop_requested_at': '',
            'error_code': '',
            'error_message': '',
            'error_traceback': '',
            'logs': [],
        }
        _set_lit_stage5b_snapshot(lit_review, initial)
        worker = threading.Thread(
            target=_run_lit_stage5b_async,
            args=(lit_review.pk,),
            daemon=True,
        )
        _LIT_STAGE5B_WORKERS[lit_review.pk] = worker
        worker.start()
        messages.success(request, 'Stage 5b stitching started.')
        return redirect('lit_reviews:stage5b-stitch-monitor', pk=lit_review.pk)


class LitReviewStage5BStitchStatusView(View):
    def get(self, request, pk):
        lit_review = get_object_or_404(LitReview, pk=pk)
        stage = _get_lit_stage5b_snapshot(lit_review)
        if stage.get('status') in {'running', 'queued', 'stopping'} and not _is_lit_stage5b_worker_alive(lit_review.pk):
            stage['status'] = 'stopped'
            stage['completed_at'] = timezone.now().isoformat()
            _set_lit_stage5b_snapshot(lit_review, stage)
        payload = _get_lit_stage5b_snapshot(lit_review)
        payload['final_prose_chars'] = len(str(lit_review.final_prose or ''))
        return JsonResponse(payload)


class LitReviewStage5CReferencesMonitorView(View):
    template_name = 'reviews/lit_review_stage5c_references_monitor.html'

    def get(self, request, pk):
        lit_review = get_object_or_404(LitReview, pk=pk)
        stage = _get_lit_stage5c_snapshot(lit_review)
        return render(request, self.template_name, {'lit_review': lit_review, 'stage': stage})

    def post(self, request, pk):
        lit_review = get_object_or_404(LitReview, pk=pk)
        stage = _get_lit_stage5c_snapshot(lit_review)
        action = (request.POST.get('action') or 'build').strip().lower()
        worker_alive = _is_lit_stage5c_worker_alive(lit_review.pk)

        if action == 'stop':
            if stage.get('status') not in {'running', 'queued', 'stopping'}:
                messages.warning(request, 'No active Stage 5c references run is in progress.')
                return redirect('lit_reviews:stage5c-references-monitor', pk=lit_review.pk)
            stage['status'] = 'stopping'
            stage['stop_requested'] = True
            stage['stop_requested_at'] = timezone.now().isoformat()
            _set_lit_stage5c_snapshot(lit_review, stage)
            messages.success(request, 'Stop requested for Stage 5c references.')
            return redirect('lit_reviews:stage5c-references-monitor', pk=lit_review.pk)

        if stage.get('status') in {'running', 'queued', 'stopping'} and worker_alive:
            messages.warning(request, 'Stage 5c references is already running.')
            return redirect('lit_reviews:stage5c-references-monitor', pk=lit_review.pk)
        if stage.get('status') in {'running', 'queued', 'stopping'} and not worker_alive:
            stage['status'] = 'stopped'
            stage['completed_at'] = timezone.now().isoformat()
            _set_lit_stage5c_snapshot(lit_review, stage)

        initial = {
            'status': 'running',
            'started_at': timezone.now().isoformat(),
            'references_count': 0,
            'used_paper_ids': [],
            'missing_reference_paper_ids': [],
            'references_apa': [],
            'stop_requested': False,
            'stop_requested_at': '',
            'error_code': '',
            'error_message': '',
            'error_traceback': '',
            'logs': [],
        }
        _set_lit_stage5c_snapshot(lit_review, initial)
        worker = threading.Thread(
            target=_run_lit_stage5c_async,
            args=(lit_review.pk,),
            daemon=True,
        )
        _LIT_STAGE5C_WORKERS[lit_review.pk] = worker
        worker.start()
        messages.success(request, 'Stage 5c references build started.')
        return redirect('lit_reviews:stage5c-references-monitor', pk=lit_review.pk)


class LitReviewStage5CReferencesStatusView(View):
    def get(self, request, pk):
        lit_review = get_object_or_404(LitReview, pk=pk)
        stage = _get_lit_stage5c_snapshot(lit_review)
        if stage.get('status') in {'running', 'queued', 'stopping'} and not _is_lit_stage5c_worker_alive(lit_review.pk):
            stage['status'] = 'stopped'
            stage['completed_at'] = timezone.now().isoformat()
            _set_lit_stage5c_snapshot(lit_review, stage)
        payload = _get_lit_stage5c_snapshot(lit_review)
        payload['final_prose_chars'] = len(str(lit_review.final_prose or ''))
        return JsonResponse(payload)


class LitReviewStage1ApiCreateView(View):
    def post(self, request):
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except Exception:
            return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

        questions = payload.get('research_questions')
        if isinstance(questions, list):
            research_questions = _normalize_questions(questions)
        else:
            single = str(payload.get('research_question') or '').strip()
            research_questions = _normalize_questions([single] if single else [])

        target_word_count = payload.get('target_word_count')
        research_context = str(payload.get('research_context') or '').strip()

        if not research_questions:
            return JsonResponse({'error': 'research_questions (or research_question) is required.'}, status=400)
        if len(research_questions) > 12:
            return JsonResponse({'error': 'Please limit to 12 research questions.'}, status=400)
        if not research_context:
            return JsonResponse({'error': 'research_context is required.'}, status=400)
        if len(research_context) < 20:
            return JsonResponse({'error': 'research_context is too short. Add more detail.'}, status=400)
        try:
            target_word_count = int(target_word_count)
        except (TypeError, ValueError):
            return JsonResponse({'error': 'target_word_count must be an integer.'}, status=400)

        if target_word_count < 800 or target_word_count > 20000:
            return JsonResponse({'error': 'target_word_count must be between 800 and 20000.'}, status=400)

        with transaction.atomic():
            lit_review = LitReview.objects.create(
                user=request.user if request.user.is_authenticated else None,
                research_context=research_context,
                research_questions=research_questions,
                research_question=research_questions[0],
                target_word_count=target_word_count,
                status=LitReview.Status.PLANNING,
            )

            try:
                plan = generate_lit_review_stage1_plan(
                    research_context=research_context,
                    research_questions=research_questions,
                    target_word_count=target_word_count,
                )
                _persist_stage1_plan(lit_review=lit_review, plan=plan)
            except Exception as exc:
                transaction.set_rollback(True)
                return JsonResponse({'error': f'Stage 1 failed: {exc}'}, status=500)

        sections = list(
            lit_review.sections.all().order_by('number', 'id').values(
                'number',
                'title',
                'type',
                'purpose',
                'what_to_look_for',
                'search_keywords',
                'notable_authors',
                'target_paper_count',
                'leads_to',
                'word_count_target',
            )
        )
        return JsonResponse(
            {
                'review_id': lit_review.id,
                'research_context': lit_review.research_context,
                'research_questions': lit_review.research_questions,
                'research_question': lit_review.research_question,
                'target_word_count': lit_review.target_word_count,
                'total_words_allocated': lit_review.total_words_allocated,
                'review_goal': lit_review.review_goal,
                'gap_statement': lit_review.gap_statement,
                'section_order_rationale': lit_review.section_order_rationale,
                'sections': sections,
                'status': lit_review.status,
            },
            status=201,
        )


def _persist_stage1_plan(*, lit_review, plan):
    sections = plan.get('sections') or []
    with transaction.atomic():
        lit_review.total_words_allocated = int(plan.get('total_words_allocated') or 0)
        lit_review.review_goal = str(plan.get('review_goal') or '').strip()
        lit_review.gap_statement = str(plan.get('gap_statement') or '').strip()
        lit_review.section_order_rationale = str(plan.get('section_order_rationale') or '').strip()
        lit_review.save(
            update_fields=[
                'total_words_allocated',
                'review_goal',
                'gap_statement',
                'section_order_rationale',
            ]
        )

        lit_review.sections.all().delete()
        rows = []
        for idx, section in enumerate(sections, start=1):
            rows.append(
                ReviewSection(
                    review=lit_review,
                    number=int(section.get('number') or idx),
                    title=str(section.get('title') or '').strip()[:255],
                    type=str(section.get('type') or '').strip().lower(),
                    purpose=str(section.get('purpose') or '').strip(),
                    what_to_look_for=str(section.get('what_to_look_for') or '').strip(),
                    search_keywords=section.get('search_keywords') if isinstance(section.get('search_keywords'), list) else [],
                    notable_authors=section.get('notable_authors') if isinstance(section.get('notable_authors'), list) else [],
                    target_paper_count=str(section.get('target_paper_count') or '').strip()[:64],
                    leads_to=str(section.get('leads_to') or '').strip(),
                    word_count_target=int(section.get('word_count_target') or 0),
                )
            )
        ReviewSection.objects.bulk_create(rows)


def _normalize_questions(raw_items):
    unique = []
    seen = set()
    for item in raw_items:
        text = str(item).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(text)
    return unique


def _run_lit_resolver_async(lit_review_id):
    def _should_stop():
        review = LitReview.objects.get(pk=lit_review_id)
        stage = _get_lit_resolver_stage_snapshot(review)
        return bool(stage.get('stop_requested'))

    def _progress(event):
        _apply_lit_resolver_progress(lit_review_id=lit_review_id, event=event)

    try:
        summary = resolve_and_download_missing_pdfs_for_lit_review(
            review_id=lit_review_id,
            progress_callback=_progress,
            stop_check=_should_stop,
        )
        _apply_lit_resolver_completion(lit_review_id=lit_review_id, summary=summary)
    except Exception as exc:
        _mark_lit_resolver_error(lit_review_id=lit_review_id, exc=exc)


def _apply_lit_resolver_progress(*, lit_review_id, event):
    lit_review = LitReview.objects.get(pk=lit_review_id)
    stage = _get_lit_resolver_stage_snapshot(lit_review)
    logs = list(stage.get('logs') or [])

    event_name = event.get('event', '')
    paper_id = event.get('paper_id')
    title = (event.get('title') or '')[:220]
    source = (event.get('source') or '')[:64]
    error_message = event.get('error_message') or ''

    if event_name == 'started':
        stage['targeted'] = int(event.get('targeted', 0) or 0)
        stage['remaining_paper_ids'] = list(event.get('paper_ids') or [])
    elif event_name in {'done', 'failed'}:
        stage['processed'] = int(stage.get('processed', 0) or 0) + 1
        processed_ids = list(stage.get('processed_paper_ids') or [])
        if paper_id and paper_id not in processed_ids:
            processed_ids.append(paper_id)
        stage['processed_paper_ids'] = processed_ids
        stage['remaining_paper_ids'] = [pid for pid in (stage.get('remaining_paper_ids') or []) if pid != paper_id]
        if event_name == 'done':
            stage['downloaded'] = int(stage.get('downloaded', 0) or 0) + 1
        else:
            stage['failed'] = int(stage.get('failed', 0) or 0) + 1

    if event_name in {'processing', 'done', 'failed', 'stopped'}:
        logs.insert(
            0,
            {
                'time': timezone.now().isoformat(),
                'event': event_name,
                'paper_id': paper_id,
                'title': title,
                'source': source,
                'error_message': error_message,
            },
        )
        stage['logs'] = logs[:500]

    _set_lit_resolver_stage_snapshot(lit_review, stage)


def _apply_lit_resolver_completion(*, lit_review_id, summary):
    lit_review = LitReview.objects.get(pk=lit_review_id)
    stage = _get_lit_resolver_stage_snapshot(lit_review)
    stage['status'] = 'stopped' if summary.get('stopped') else 'completed'
    stage['completed_at'] = timezone.now().isoformat()
    stage['targeted'] = int(summary.get('targeted', stage.get('targeted', 0)))
    stage['processed'] = int(len(summary.get('processed_ids') or stage.get('processed_paper_ids') or []))
    stage['resolved'] = int(summary.get('resolved', stage.get('resolved', 0)))
    stage['downloaded'] = int(summary.get('downloaded', stage.get('downloaded', 0)))
    stage['failed'] = int(summary.get('failed', stage.get('failed', 0)))
    stage['processed_paper_ids'] = list(summary.get('processed_ids', stage.get('processed_paper_ids') or []))
    stage['remaining_paper_ids'] = list(summary.get('remaining_paper_ids', stage.get('remaining_paper_ids') or []))
    _set_lit_resolver_stage_snapshot(lit_review, stage)


def _mark_lit_resolver_error(*, lit_review_id, exc):
    lit_review = LitReview.objects.get(pk=lit_review_id)
    stage = _get_lit_resolver_stage_snapshot(lit_review)
    stage['status'] = 'error'
    stage['error_code'] = exc.__class__.__name__
    stage['error_message'] = str(exc)
    stage['error_traceback'] = traceback.format_exc()
    stage['completed_at'] = timezone.now().isoformat()
    _set_lit_resolver_stage_snapshot(lit_review, stage)


def _get_lit_resolver_stage_snapshot(lit_review):
    stage_progress = lit_review.stage_progress or {}
    stage = stage_progress.get('stage2_pdf_resolver', {})
    if not isinstance(stage, dict):
        stage = {}
    stage.setdefault('status', 'idle')
    stage.setdefault('targeted', 0)
    stage.setdefault('processed', 0)
    stage.setdefault('resolved', 0)
    stage.setdefault('downloaded', 0)
    stage.setdefault('failed', 0)
    stage.setdefault('processed_paper_ids', [])
    stage.setdefault('remaining_paper_ids', [])
    stage.setdefault('logs', [])
    stage.setdefault('error_code', '')
    stage.setdefault('error_message', '')
    stage.setdefault('error_traceback', '')
    stage.setdefault('stop_requested', False)
    return stage


def _set_lit_resolver_stage_snapshot(lit_review, stage_payload):
    stage_progress = lit_review.stage_progress or {}
    stage_progress['stage2_pdf_resolver'] = stage_payload
    lit_review.stage_progress = stage_progress
    lit_review.save(update_fields=['stage_progress'])


def _run_lit_citation_async(lit_review_id, only_missing):
    def _should_stop():
        review = LitReview.objects.get(pk=lit_review_id)
        stage = _get_lit_citation_stage_snapshot(review)
        return bool(stage.get('stop_requested'))

    def _progress(event):
        _apply_lit_citation_progress(lit_review_id=lit_review_id, event=event)

    try:
        summary = generate_apa_citations_for_lit_review(
            review_id=lit_review_id,
            only_missing=only_missing,
            progress_callback=_progress,
            stop_check=_should_stop,
        )
        _apply_lit_citation_completion(lit_review_id=lit_review_id, summary=summary)
    except Exception as exc:
        _mark_lit_citation_error(lit_review_id=lit_review_id, exc=exc)


def _apply_lit_citation_progress(*, lit_review_id, event):
    lit_review = LitReview.objects.get(pk=lit_review_id)
    stage = _get_lit_citation_stage_snapshot(lit_review)
    logs = list(stage.get('logs') or [])

    event_name = event.get('event', '')
    paper_id = event.get('paper_id')
    title = (event.get('title') or '')[:220]
    citation_source = (event.get('citation_source') or '')[:64]
    error_code = event.get('error_code') or ''
    error_message = event.get('error_message') or ''

    if event_name == 'started':
        stage['targeted'] = int(event.get('targeted', 0) or 0)
        stage['remaining_paper_ids'] = list(event.get('paper_ids') or [])
    elif event_name in {'done', 'failed'}:
        stage['processed'] = int(stage.get('processed', 0) or 0) + 1
        processed_ids = list(stage.get('processed_paper_ids') or [])
        if paper_id and paper_id not in processed_ids:
            processed_ids.append(paper_id)
        stage['processed_paper_ids'] = processed_ids
        stage['remaining_paper_ids'] = [pid for pid in (stage.get('remaining_paper_ids') or []) if pid != paper_id]
        if event_name == 'done':
            stage['done'] = int(stage.get('done', 0) or 0) + 1
        else:
            stage['failed'] = int(stage.get('failed', 0) or 0) + 1

    if event_name in {'processing', 'done', 'failed', 'stopped'}:
        logs.insert(
            0,
            {
                'time': timezone.now().isoformat(),
                'event': event_name,
                'paper_id': paper_id,
                'title': title,
                'citation_source': citation_source,
                'error_code': error_code,
                'error_message': error_message,
            },
        )
        stage['logs'] = logs[:500]

    _set_lit_citation_stage_snapshot(lit_review, stage)


def _apply_lit_citation_completion(*, lit_review_id, summary):
    lit_review = LitReview.objects.get(pk=lit_review_id)
    stage = _get_lit_citation_stage_snapshot(lit_review)
    stage['status'] = 'stopped' if summary.get('stopped') else 'completed'
    stage['completed_at'] = timezone.now().isoformat()
    stage['targeted'] = int(summary.get('targeted', stage.get('targeted', 0)))
    stage['processed'] = int(len(summary.get('processed_ids') or stage.get('processed_paper_ids') or []))
    stage['done'] = int(summary.get('done', stage.get('done', 0)))
    stage['failed'] = int(summary.get('failed', stage.get('failed', 0)))
    stage['processed_paper_ids'] = list(summary.get('processed_ids', stage.get('processed_paper_ids') or []))
    stage['remaining_paper_ids'] = list(summary.get('remaining_paper_ids', stage.get('remaining_paper_ids') or []))
    _set_lit_citation_stage_snapshot(lit_review, stage)


def _mark_lit_citation_error(*, lit_review_id, exc):
    lit_review = LitReview.objects.get(pk=lit_review_id)
    stage = _get_lit_citation_stage_snapshot(lit_review)
    stage['status'] = 'error'
    stage['error_code'] = exc.__class__.__name__
    stage['error_message'] = str(exc)
    stage['error_traceback'] = traceback.format_exc()
    stage['completed_at'] = timezone.now().isoformat()
    _set_lit_citation_stage_snapshot(lit_review, stage)


def _get_lit_citation_stage_snapshot(lit_review):
    stage_progress = lit_review.stage_progress or {}
    stage = stage_progress.get('stage2_apa_citations', {})
    if not isinstance(stage, dict):
        stage = {}
    stage.setdefault('status', 'idle')
    stage.setdefault('targeted', 0)
    stage.setdefault('processed', 0)
    stage.setdefault('done', 0)
    stage.setdefault('failed', 0)
    stage.setdefault('processed_paper_ids', [])
    stage.setdefault('remaining_paper_ids', [])
    stage.setdefault('logs', [])
    stage.setdefault('error_code', '')
    stage.setdefault('error_message', '')
    stage.setdefault('error_traceback', '')
    stage.setdefault('stop_requested', False)
    stage.setdefault('only_missing', True)
    return stage


def _set_lit_citation_stage_snapshot(lit_review, stage_payload):
    stage_progress = lit_review.stage_progress or {}
    stage_progress['stage2_apa_citations'] = stage_payload
    lit_review.stage_progress = stage_progress
    lit_review.save(update_fields=['stage_progress'])


def _run_lit_mineru_async(lit_review_id, retry_failed_only, run_ref_delete=False):
    def _should_stop():
        review = LitReview.objects.get(pk=lit_review_id)
        stage = _get_lit_mineru_stage_snapshot(review)
        return bool(stage.get('stop_requested'))

    def _progress(event):
        _apply_lit_mineru_progress(lit_review_id=lit_review_id, event=event)

    try:
        if run_ref_delete:
            summary = clean_existing_lit_mineru_references(
                review_id=lit_review_id,
                progress_callback=_progress,
                stop_check=_should_stop,
            )
        else:
            summary = parse_lit_review_pdfs_with_mineru(
                review_id=lit_review_id,
                retry_failed_only=retry_failed_only,
                progress_callback=_progress,
                stop_check=_should_stop,
            )
        _apply_lit_mineru_completion(lit_review_id=lit_review_id, summary=summary)
    except Exception as exc:
        _mark_lit_mineru_error(lit_review_id=lit_review_id, exc=exc)
    finally:
        _LIT_MINERU_WORKERS.pop(lit_review_id, None)


def _apply_lit_mineru_progress(*, lit_review_id, event):
    lit_review = LitReview.objects.get(pk=lit_review_id)
    stage = _get_lit_mineru_stage_snapshot(lit_review)
    logs = list(stage.get('logs') or [])

    event_name = event.get('event', '')
    paper_id = event.get('paper_id')
    title = (event.get('title') or '')[:220]
    error_message = event.get('error_message') or ''
    batch_id = event.get('batch_id') or ''
    markdown_chars = event.get('markdown_chars')

    if event_name == 'started':
        stage['targeted'] = int(event.get('targeted', 0) or 0)
        stage['remaining_paper_ids'] = list(event.get('paper_ids') or [])
    elif event_name in {'done', 'failed'}:
        stage['processed'] = int(stage.get('processed', 0)) + 1
        processed_ids = list(stage.get('processed_paper_ids') or [])
        if paper_id and paper_id not in processed_ids:
            processed_ids.append(paper_id)
        stage['processed_paper_ids'] = processed_ids
        stage['remaining_paper_ids'] = [pid for pid in (stage.get('remaining_paper_ids') or []) if pid != paper_id]
        if event_name == 'done':
            stage['done'] = int(stage.get('done', 0)) + 1
        else:
            stage['failed'] = int(stage.get('failed', 0)) + 1

    if event_name in {'processing', 'done', 'failed', 'stopped'}:
        logs.insert(
            0,
            {
                'time': timezone.now().isoformat(),
                'event': event_name,
                'paper_id': paper_id,
                'title': title,
                'batch_id': batch_id,
                'markdown_chars': markdown_chars,
                'error_message': error_message,
            },
        )
        stage['logs'] = logs[:500]

    _set_lit_mineru_stage_snapshot(lit_review, stage)


def _apply_lit_mineru_completion(*, lit_review_id, summary):
    lit_review = LitReview.objects.get(pk=lit_review_id)
    stage = _get_lit_mineru_stage_snapshot(lit_review)
    stage['status'] = 'stopped' if summary.get('stopped') else 'completed'
    stage['completed_at'] = timezone.now().isoformat()
    stage['targeted'] = int(summary.get('targeted', stage.get('targeted', 0)))
    stage['processed'] = int(summary.get('processed', stage.get('processed', 0)))
    stage['done'] = int(summary.get('done', stage.get('done', 0)))
    stage['failed'] = int(summary.get('failed', stage.get('failed', 0)))
    stage['processed_paper_ids'] = list(summary.get('processed_ids', stage.get('processed_paper_ids') or []))
    stage['remaining_paper_ids'] = list(summary.get('remaining_paper_ids', stage.get('remaining_paper_ids') or []))
    _set_lit_mineru_stage_snapshot(lit_review, stage)


def _mark_lit_mineru_error(*, lit_review_id, exc):
    lit_review = LitReview.objects.get(pk=lit_review_id)
    stage = _get_lit_mineru_stage_snapshot(lit_review)
    stage['status'] = 'error'
    stage['error_code'] = exc.__class__.__name__
    stage['error_message'] = str(exc)
    stage['error_traceback'] = traceback.format_exc()
    stage['completed_at'] = timezone.now().isoformat()
    _set_lit_mineru_stage_snapshot(lit_review, stage)


def _get_lit_mineru_stage_snapshot(lit_review):
    stage_progress = lit_review.stage_progress or {}
    stage = stage_progress.get('stage3_mineru', {})
    if not isinstance(stage, dict):
        stage = {}
    stage.setdefault('status', 'idle')
    stage.setdefault('targeted', 0)
    stage.setdefault('processed', 0)
    stage.setdefault('done', 0)
    stage.setdefault('failed', 0)
    stage.setdefault('processed_paper_ids', [])
    stage.setdefault('remaining_paper_ids', [])
    stage.setdefault('stop_requested', False)
    stage.setdefault('logs', [])
    stage.setdefault('error_code', '')
    stage.setdefault('error_message', '')
    stage.setdefault('error_traceback', '')
    stage.setdefault('rewrite_all', False)
    return stage


def _set_lit_mineru_stage_snapshot(lit_review, stage_payload):
    stage_progress = lit_review.stage_progress or {}
    stage_progress['stage3_mineru'] = stage_payload
    lit_review.stage_progress = stage_progress
    lit_review.save(update_fields=['stage_progress'])


def _is_lit_mineru_worker_alive(review_id):
    worker = _LIT_MINERU_WORKERS.get(review_id)
    if not worker:
        return False
    return worker.is_alive()


def _run_lit_per_paper_async(lit_review_id, retry_failed_only):
    def _should_stop():
        review = LitReview.objects.get(pk=lit_review_id)
        stage = _get_lit_per_paper_stage_snapshot(review)
        return bool(stage.get('stop_requested'))

    def _progress(event):
        _apply_lit_per_paper_progress(lit_review_id=lit_review_id, event=event)

    try:
        summary = run_lit_per_paper_extraction_for_review(
            review_id=lit_review_id,
            progress_callback=_progress,
            stop_check=_should_stop,
            retry_failed_only=retry_failed_only,
        )
        _apply_lit_per_paper_completion(lit_review_id=lit_review_id, summary=summary)
    except Exception as exc:
        _mark_lit_per_paper_error(lit_review_id=lit_review_id, exc=exc)
    finally:
        _LIT_PER_PAPER_WORKERS.pop(lit_review_id, None)


def _apply_lit_per_paper_progress(*, lit_review_id, event):
    lit_review = LitReview.objects.get(pk=lit_review_id)
    stage = _get_lit_per_paper_stage_snapshot(lit_review)
    logs = list(stage.get('logs') or [])

    event_name = event.get('event', '')
    paper_id = event.get('paper_id')
    title = (event.get('title') or '')[:220]
    error_code = event.get('error_code') or ''
    error_message = event.get('error_message') or ''
    quality_category = (event.get('quality_category') or '')[:4]
    stance = (event.get('stance') or '')[:32]

    if event_name == 'started':
        stage['targeted'] = int(event.get('targeted', 0) or 0)
        stage['remaining_paper_ids'] = list(event.get('paper_ids') or [])
    elif event_name in {'done', 'failed'}:
        stage['processed'] = int(stage.get('processed', 0)) + 1
        processed_ids = list(stage.get('processed_paper_ids') or [])
        if paper_id and paper_id not in processed_ids:
            processed_ids.append(paper_id)
        stage['processed_paper_ids'] = processed_ids
        stage['remaining_paper_ids'] = [pid for pid in (stage.get('remaining_paper_ids') or []) if pid != paper_id]
        if event_name == 'done':
            stage['done'] = int(stage.get('done', 0)) + 1
        else:
            stage['failed'] = int(stage.get('failed', 0)) + 1

    if event_name in {'processing', 'done', 'failed', 'stopped'}:
        logs.insert(
            0,
            {
                'time': timezone.now().isoformat(),
                'event': event_name,
                'paper_id': paper_id,
                'title': title,
                'quality_category': quality_category,
                'stance': stance,
                'error_code': error_code,
                'error_message': error_message,
            },
        )
        stage['logs'] = logs[:500]

    _set_lit_per_paper_stage_snapshot(lit_review, stage)


def _apply_lit_per_paper_completion(*, lit_review_id, summary):
    lit_review = LitReview.objects.get(pk=lit_review_id)
    stage = _get_lit_per_paper_stage_snapshot(lit_review)
    stage['status'] = 'stopped' if summary.get('stopped') else 'completed'
    stage['completed_at'] = timezone.now().isoformat()
    stage['targeted'] = int(summary.get('targeted', stage.get('targeted', 0)))
    stage['processed'] = int(summary.get('processed', stage.get('processed', 0)))
    stage['done'] = int(summary.get('done', stage.get('done', 0)))
    stage['failed'] = int(summary.get('failed', stage.get('failed', 0)))
    stage['processed_paper_ids'] = list(summary.get('processed_ids', stage.get('processed_paper_ids') or []))
    stage['remaining_paper_ids'] = list(summary.get('remaining_paper_ids', stage.get('remaining_paper_ids') or []))
    _set_lit_per_paper_stage_snapshot(lit_review, stage)


def _mark_lit_per_paper_error(*, lit_review_id, exc):
    lit_review = LitReview.objects.get(pk=lit_review_id)
    stage = _get_lit_per_paper_stage_snapshot(lit_review)
    stage['status'] = 'error'
    stage['error_code'] = exc.__class__.__name__
    stage['error_message'] = str(exc)
    stage['error_traceback'] = traceback.format_exc()
    stage['completed_at'] = timezone.now().isoformat()
    _set_lit_per_paper_stage_snapshot(lit_review, stage)


def _get_lit_per_paper_stage_snapshot(lit_review):
    stage_progress = lit_review.stage_progress or {}
    stage = stage_progress.get('stage4_per_paper_extraction', {})
    if not isinstance(stage, dict):
        stage = {}
    stage.setdefault('status', 'idle')
    stage.setdefault('targeted', 0)
    stage.setdefault('processed', 0)
    stage.setdefault('done', 0)
    stage.setdefault('failed', 0)
    stage.setdefault('processed_paper_ids', [])
    stage.setdefault('remaining_paper_ids', [])
    stage.setdefault('stop_requested', False)
    stage.setdefault('logs', [])
    stage.setdefault('error_code', '')
    stage.setdefault('error_message', '')
    stage.setdefault('error_traceback', '')
    return stage


def _set_lit_per_paper_stage_snapshot(lit_review, stage_payload):
    stage_progress = lit_review.stage_progress or {}
    stage_progress['stage4_per_paper_extraction'] = stage_payload
    lit_review.stage_progress = stage_progress
    lit_review.save(update_fields=['stage_progress'])


def _is_lit_per_paper_worker_alive(review_id):
    worker = _LIT_PER_PAPER_WORKERS.get(review_id)
    if not worker:
        return False
    return worker.is_alive()


def _lit_per_paper_completed_rows(lit_review):
    rows = lit_review.papers.filter(fulltext_retrieved=True).exclude(
        per_paper_extraction_status=''
    ).order_by('id').values(
        'id',
        'title',
        'per_paper_extraction_status',
        'per_paper_extraction_error',
        'per_paper_extraction_updated_at',
        'per_paper_quality_category',
        'per_paper_extraction',
    )

    output = []
    for row in rows:
        extraction = row.get('per_paper_extraction')
        stance = ''
        citation = ''
        if isinstance(extraction, dict):
            stance = str(extraction.get('stance') or '')
            citation = str(extraction.get('citation') or '')
        output.append(
            {
                'id': row['id'],
                'title': row.get('title') or '',
                'status': row.get('per_paper_extraction_status') or '',
                'error': row.get('per_paper_extraction_error') or '',
                'updated_at': row.get('per_paper_extraction_updated_at'),
                'quality_category': row.get('per_paper_quality_category') or '',
                'stance': stance,
                'citation': citation,
            }
        )
    return output


def _run_lit_assignment_async(lit_review_id, reassign_all):
    def _should_stop():
        review = LitReview.objects.get(pk=lit_review_id)
        stage = _get_lit_assignment_stage_snapshot(review)
        return bool(stage.get('stop_requested'))

    def _progress(event):
        _apply_lit_assignment_progress(lit_review_id=lit_review_id, event=event)

    try:
        summary = run_lit_section_assignment_for_review(
            review_id=lit_review_id,
            progress_callback=_progress,
            stop_check=_should_stop,
            reassign_all=reassign_all,
        )
        _apply_lit_assignment_completion(lit_review_id=lit_review_id, summary=summary)
    except Exception as exc:
        _mark_lit_assignment_error(lit_review_id=lit_review_id, exc=exc)
    finally:
        _LIT_ASSIGN_WORKERS.pop(lit_review_id, None)


def _apply_lit_assignment_progress(*, lit_review_id, event):
    lit_review = LitReview.objects.get(pk=lit_review_id)
    stage = _get_lit_assignment_stage_snapshot(lit_review)
    logs = list(stage.get('logs') or [])

    event_name = event.get('event', '')
    paper_id = event.get('paper_id')
    title = (event.get('title') or '')[:220]
    assigned_section = event.get('assigned_section')
    confidence = (event.get('assignment_confidence') or '')[:16]
    flag = (event.get('flag') or '')[:64]
    error_code = event.get('error_code') or ''
    error_message = event.get('error_message') or ''

    if event_name == 'started':
        stage['targeted'] = int(event.get('targeted', 0) or 0)
        stage['remaining_paper_ids'] = list(event.get('paper_ids') or [])
    elif event_name in {'done', 'failed'}:
        stage['processed'] = int(stage.get('processed', 0)) + 1
        processed_ids = list(stage.get('processed_paper_ids') or [])
        if paper_id and paper_id not in processed_ids:
            processed_ids.append(paper_id)
        stage['processed_paper_ids'] = processed_ids
        stage['remaining_paper_ids'] = [pid for pid in (stage.get('remaining_paper_ids') or []) if pid != paper_id]
        if event_name == 'done':
            stage['done'] = int(stage.get('done', 0)) + 1
        else:
            stage['failed'] = int(stage.get('failed', 0)) + 1

    if event_name in {'processing', 'done', 'failed', 'stopped'}:
        logs.insert(
            0,
            {
                'time': timezone.now().isoformat(),
                'event': event_name,
                'paper_id': paper_id,
                'title': title,
                'assigned_section': assigned_section,
                'assignment_confidence': confidence,
                'flag': flag,
                'error_code': error_code,
                'error_message': error_message,
            },
        )
        stage['logs'] = logs[:500]

    _set_lit_assignment_stage_snapshot(lit_review, stage)


def _apply_lit_assignment_completion(*, lit_review_id, summary):
    lit_review = LitReview.objects.get(pk=lit_review_id)
    stage = _get_lit_assignment_stage_snapshot(lit_review)
    stage['status'] = 'stopped' if summary.get('stopped') else 'completed'
    stage['completed_at'] = timezone.now().isoformat()
    stage['targeted'] = int(summary.get('targeted', stage.get('targeted', 0)))
    stage['processed'] = int(summary.get('processed', stage.get('processed', 0)))
    stage['done'] = int(summary.get('done', stage.get('done', 0)))
    stage['failed'] = int(summary.get('failed', stage.get('failed', 0)))
    stage['processed_paper_ids'] = list(summary.get('processed_ids', stage.get('processed_paper_ids') or []))
    stage['remaining_paper_ids'] = list(summary.get('remaining_paper_ids', stage.get('remaining_paper_ids') or []))
    stage['missing_section_numbers'] = list(summary.get('missing_section_numbers') or [])
    stage['too_tangential_count'] = int(summary.get('too_tangential_count') or 0)
    _set_lit_assignment_stage_snapshot(lit_review, stage)


def _mark_lit_assignment_error(*, lit_review_id, exc):
    lit_review = LitReview.objects.get(pk=lit_review_id)
    stage = _get_lit_assignment_stage_snapshot(lit_review)
    stage['status'] = 'error'
    stage['error_code'] = exc.__class__.__name__
    stage['error_message'] = str(exc)
    stage['error_traceback'] = traceback.format_exc()
    stage['completed_at'] = timezone.now().isoformat()
    _set_lit_assignment_stage_snapshot(lit_review, stage)


def _get_lit_assignment_stage_snapshot(lit_review):
    stage_progress = lit_review.stage_progress or {}
    stage = stage_progress.get('stage4b_assignment', {})
    if not isinstance(stage, dict):
        stage = {}
    stage.setdefault('status', 'idle')
    stage.setdefault('targeted', 0)
    stage.setdefault('processed', 0)
    stage.setdefault('done', 0)
    stage.setdefault('failed', 0)
    stage.setdefault('processed_paper_ids', [])
    stage.setdefault('remaining_paper_ids', [])
    stage.setdefault('missing_section_numbers', [])
    stage.setdefault('too_tangential_count', 0)
    stage.setdefault('stop_requested', False)
    stage.setdefault('logs', [])
    stage.setdefault('error_code', '')
    stage.setdefault('error_message', '')
    stage.setdefault('error_traceback', '')
    return stage


def _set_lit_assignment_stage_snapshot(lit_review, stage_payload):
    stage_progress = lit_review.stage_progress or {}
    stage_progress['stage4b_assignment'] = stage_payload
    lit_review.stage_progress = stage_progress
    lit_review.save(update_fields=['stage_progress'])


def _is_lit_assignment_worker_alive(review_id):
    worker = _LIT_ASSIGN_WORKERS.get(review_id)
    if not worker:
        return False
    return worker.is_alive()


def _lit_assignment_rows(lit_review):
    rows = (
        LitPaperAssignment.objects
        .filter(review=lit_review)
        .select_related('paper', 'section')
        .order_by('paper_id')
    )
    out = []
    for row in rows:
        out.append(
            {
                'paper_id': row.paper_id,
                'paper_title': row.paper.title,
                'section_number': row.section.number,
                'section_title': row.section.title,
                'assignment_confidence': row.assignment_confidence,
                'flag': row.flag,
                'how_to_use': row.how_to_use,
                'reason': row.reason,
                'also_relevant_to': row.also_relevant_to if isinstance(row.also_relevant_to, list) else [],
            }
        )
    return out


def _run_lit_stage5_async(lit_review_id, rewrite_all):
    def _should_stop():
        review = LitReview.objects.get(pk=lit_review_id)
        stage = _get_lit_stage5_snapshot(review)
        return bool(stage.get('stop_requested'))

    def _progress(event):
        _apply_lit_stage5_progress(lit_review_id=lit_review_id, event=event)

    try:
        summary = run_lit_stage5_writing_for_review(
            review_id=lit_review_id,
            progress_callback=_progress,
            stop_check=_should_stop,
            rewrite_all=rewrite_all,
        )
        _apply_lit_stage5_completion(lit_review_id=lit_review_id, summary=summary)
    except Exception as exc:
        _mark_lit_stage5_error(lit_review_id=lit_review_id, exc=exc)
    finally:
        _LIT_STAGE5_WORKERS.pop(lit_review_id, None)


def _apply_lit_stage5_progress(*, lit_review_id, event):
    lit_review = LitReview.objects.get(pk=lit_review_id)
    stage = _get_lit_stage5_snapshot(lit_review)
    logs = list(stage.get('logs') or [])

    event_name = event.get('event', '')
    section_id = event.get('section_id')
    section_number = event.get('section_number')
    section_title = (event.get('section_title') or '')[:220]
    word_count = event.get('word_count')
    notes_for_user = event.get('notes_for_user') or ''
    papers_used = event.get('papers_used') if isinstance(event.get('papers_used'), list) else []
    error_code = event.get('error_code') or ''
    error_message = event.get('error_message') or ''

    if event_name == 'started':
        stage['targeted'] = int(event.get('targeted', 0) or 0)
        stage['remaining_section_ids'] = list(event.get('section_ids') or [])
    elif event_name in {'done', 'failed'}:
        stage['processed'] = int(stage.get('processed', 0)) + 1
        processed_ids = list(stage.get('processed_section_ids') or [])
        if section_id and section_id not in processed_ids:
            processed_ids.append(section_id)
        stage['processed_section_ids'] = processed_ids
        stage['remaining_section_ids'] = [sid for sid in (stage.get('remaining_section_ids') or []) if sid != section_id]
        if event_name == 'done':
            stage['done'] = int(stage.get('done', 0)) + 1
        else:
            stage['failed'] = int(stage.get('failed', 0)) + 1

    if event_name in {'processing', 'done', 'failed', 'stopped'}:
        logs.insert(
            0,
            {
                'time': timezone.now().isoformat(),
                'event': event_name,
                'section_id': section_id,
                'section_number': section_number,
                'section_title': section_title,
                'word_count': word_count,
                'notes_for_user': notes_for_user,
                'error_code': error_code,
                'error_message': error_message,
            },
        )
        stage['logs'] = logs[:500]

    if event_name == 'done' and section_id:
        section_outputs = stage.get('section_outputs')
        if not isinstance(section_outputs, dict):
            section_outputs = {}
        section_outputs[str(section_id)] = {
            'section_number': section_number,
            'section_title': section_title,
            'word_count': word_count,
            'notes_for_user': notes_for_user,
            'papers_used': [str(item).strip() for item in papers_used if str(item).strip()],
        }
        stage['section_outputs'] = section_outputs

    _set_lit_stage5_snapshot(lit_review, stage)


def _apply_lit_stage5_completion(*, lit_review_id, summary):
    lit_review = LitReview.objects.get(pk=lit_review_id)
    stage = _get_lit_stage5_snapshot(lit_review)
    stage['status'] = 'stopped' if summary.get('stopped') else 'completed'
    stage['completed_at'] = timezone.now().isoformat()
    stage['targeted'] = int(summary.get('targeted', stage.get('targeted', 0)))
    stage['processed'] = int(summary.get('processed', stage.get('processed', 0)))
    stage['done'] = int(summary.get('done', stage.get('done', 0)))
    stage['failed'] = int(summary.get('failed', stage.get('failed', 0)))
    stage['processed_section_ids'] = list(summary.get('processed_ids', stage.get('processed_section_ids') or []))
    stage['remaining_section_ids'] = list(summary.get('remaining_section_ids', stage.get('remaining_section_ids') or []))
    stage['actual_total_words'] = int(summary.get('actual_total_words', stage.get('actual_total_words', 0)))
    stage['target_total_words'] = int(summary.get('target_total_words', stage.get('target_total_words', 0)))
    stage['drift_pct'] = float(summary.get('drift_pct', stage.get('drift_pct', 0.0)))
    stage['drift_warning'] = bool(summary.get('drift_warning', stage.get('drift_warning', False)))
    _set_lit_stage5_snapshot(lit_review, stage)


def _mark_lit_stage5_error(*, lit_review_id, exc):
    lit_review = LitReview.objects.get(pk=lit_review_id)
    stage = _get_lit_stage5_snapshot(lit_review)
    stage['status'] = 'error'
    stage['error_code'] = exc.__class__.__name__
    stage['error_message'] = str(exc)
    stage['error_traceback'] = traceback.format_exc()
    stage['completed_at'] = timezone.now().isoformat()
    _set_lit_stage5_snapshot(lit_review, stage)


def _get_lit_stage5_snapshot(lit_review):
    stage_progress = lit_review.stage_progress or {}
    stage = stage_progress.get('stage5a_writing', {})
    if not isinstance(stage, dict):
        stage = {}
    stage.setdefault('status', 'idle')
    stage.setdefault('targeted', 0)
    stage.setdefault('processed', 0)
    stage.setdefault('done', 0)
    stage.setdefault('failed', 0)
    stage.setdefault('processed_section_ids', [])
    stage.setdefault('remaining_section_ids', [])
    stage.setdefault('actual_total_words', 0)
    stage.setdefault('target_total_words', int(lit_review.total_words_allocated or 0))
    stage.setdefault('drift_pct', 0.0)
    stage.setdefault('drift_warning', False)
    stage.setdefault('stop_requested', False)
    stage.setdefault('logs', [])
    stage.setdefault('error_code', '')
    stage.setdefault('error_message', '')
    stage.setdefault('error_traceback', '')
    stage.setdefault('section_outputs', {})
    return stage


def _set_lit_stage5_snapshot(lit_review, stage_payload):
    stage_progress = lit_review.stage_progress or {}
    stage_progress['stage5a_writing'] = stage_payload
    lit_review.stage_progress = stage_progress
    lit_review.save(update_fields=['stage_progress'])


def _is_lit_stage5_worker_alive(review_id):
    worker = _LIT_STAGE5_WORKERS.get(review_id)
    if not worker:
        return False
    return worker.is_alive()


def _lit_stage5_section_rows(lit_review):
    rows = lit_review.sections.all().order_by('number', 'id')
    out = []
    for row in rows:
        prose = str(row.prose or '')
        out.append(
            {
                'section_id': row.id,
                'section_number': row.number,
                'section_title': row.title,
                'section_type': row.type,
                'has_prose': bool(prose.strip()),
                'word_count': len([tok for tok in prose.split() if tok.strip()]),
            }
        )
    return out


def _run_lit_stage5b_async(lit_review_id):
    def _should_stop():
        review = LitReview.objects.get(pk=lit_review_id)
        stage = _get_lit_stage5b_snapshot(review)
        return bool(stage.get('stop_requested'))

    def _progress(event):
        _apply_lit_stage5b_progress(lit_review_id=lit_review_id, event=event)

    try:
        summary = run_lit_stage5b_stitch_for_review(
            review_id=lit_review_id,
            progress_callback=_progress,
            stop_check=_should_stop,
        )
        _apply_lit_stage5b_completion(lit_review_id=lit_review_id, summary=summary)
    except Exception as exc:
        _mark_lit_stage5b_error(lit_review_id=lit_review_id, exc=exc)
    finally:
        _LIT_STAGE5B_WORKERS.pop(lit_review_id, None)


def _apply_lit_stage5b_progress(*, lit_review_id, event):
    lit_review = LitReview.objects.get(pk=lit_review_id)
    stage = _get_lit_stage5b_snapshot(lit_review)
    logs = list(stage.get('logs') or [])

    event_name = event.get('event', '')
    sections_count = event.get('sections_count')
    final_words = event.get('final_words')
    intro_words = event.get('intro_words')
    closing_words = event.get('closing_words')
    error_code = event.get('error_code') or ''
    error_message = event.get('error_message') or ''

    if event_name == 'started':
        stage['sections_count'] = int(sections_count or 0)
    if event_name == 'done':
        stage['final_words'] = int(final_words or 0)
        stage['intro_words'] = int(intro_words or 0)
        stage['closing_words'] = int(closing_words or 0)

    if event_name in {'started', 'processing', 'done', 'failed', 'stopped'}:
        logs.insert(
            0,
            {
                'time': timezone.now().isoformat(),
                'event': event_name,
                'sections_count': sections_count,
                'final_words': final_words,
                'intro_words': intro_words,
                'closing_words': closing_words,
                'error_code': error_code,
                'error_message': error_message,
            },
        )
        stage['logs'] = logs[:200]

    _set_lit_stage5b_snapshot(lit_review, stage)


def _apply_lit_stage5b_completion(*, lit_review_id, summary):
    lit_review = LitReview.objects.get(pk=lit_review_id)
    stage = _get_lit_stage5b_snapshot(lit_review)
    stage['status'] = 'stopped' if summary.get('stopped') else 'completed'
    stage['completed_at'] = timezone.now().isoformat()
    stage['sections_count'] = int(summary.get('sections_count', stage.get('sections_count', 0)))
    stage['final_words'] = int(summary.get('final_words', stage.get('final_words', 0)))
    stage['intro_words'] = int(summary.get('intro_words', stage.get('intro_words', 0)))
    stage['closing_words'] = int(summary.get('closing_words', stage.get('closing_words', 0)))
    _set_lit_stage5b_snapshot(lit_review, stage)


def _mark_lit_stage5b_error(*, lit_review_id, exc):
    lit_review = LitReview.objects.get(pk=lit_review_id)
    stage = _get_lit_stage5b_snapshot(lit_review)
    stage['status'] = 'error'
    stage['error_code'] = exc.__class__.__name__
    stage['error_message'] = str(exc)
    stage['error_traceback'] = traceback.format_exc()
    stage['completed_at'] = timezone.now().isoformat()
    _set_lit_stage5b_snapshot(lit_review, stage)


def _get_lit_stage5b_snapshot(lit_review):
    stage_progress = lit_review.stage_progress or {}
    stage = stage_progress.get('stage5b_stitch', {})
    if not isinstance(stage, dict):
        stage = {}
    stage.setdefault('status', 'idle')
    stage.setdefault('sections_count', 0)
    stage.setdefault('final_words', 0)
    stage.setdefault('intro_words', 0)
    stage.setdefault('closing_words', 0)
    stage.setdefault('stop_requested', False)
    stage.setdefault('logs', [])
    stage.setdefault('error_code', '')
    stage.setdefault('error_message', '')
    stage.setdefault('error_traceback', '')
    return stage


def _set_lit_stage5b_snapshot(lit_review, stage_payload):
    stage_progress = lit_review.stage_progress or {}
    stage_progress['stage5b_stitch'] = stage_payload
    lit_review.stage_progress = stage_progress
    lit_review.save(update_fields=['stage_progress'])


def _is_lit_stage5b_worker_alive(review_id):
    worker = _LIT_STAGE5B_WORKERS.get(review_id)
    if not worker:
        return False
    return worker.is_alive()


def _run_lit_stage5c_async(lit_review_id):
    def _should_stop():
        review = LitReview.objects.get(pk=lit_review_id)
        stage = _get_lit_stage5c_snapshot(review)
        return bool(stage.get('stop_requested'))

    def _progress(event):
        _apply_lit_stage5c_progress(lit_review_id=lit_review_id, event=event)

    try:
        summary = run_lit_stage5c_references_for_review(
            review_id=lit_review_id,
            progress_callback=_progress,
            stop_check=_should_stop,
        )
        _apply_lit_stage5c_completion(lit_review_id=lit_review_id, summary=summary)
    except Exception as exc:
        _mark_lit_stage5c_error(lit_review_id=lit_review_id, exc=exc)
    finally:
        _LIT_STAGE5C_WORKERS.pop(lit_review_id, None)


def _apply_lit_stage5c_progress(*, lit_review_id, event):
    lit_review = LitReview.objects.get(pk=lit_review_id)
    stage = _get_lit_stage5c_snapshot(lit_review)
    logs = list(stage.get('logs') or [])

    event_name = event.get('event', '')
    used_count = event.get('used_count')
    missing_count = event.get('missing_count')
    references_count = event.get('references_count')
    error_code = event.get('error_code') or ''
    error_message = event.get('error_message') or ''

    if event_name == 'done':
        stage['references_count'] = int(references_count or 0)
    if event_name in {'started', 'collecting', 'ensuring_citations', 'assembling', 'done', 'failed', 'stopped'}:
        logs.insert(
            0,
            {
                'time': timezone.now().isoformat(),
                'event': event_name,
                'used_count': used_count,
                'missing_count': missing_count,
                'references_count': references_count,
                'error_code': error_code,
                'error_message': error_message,
            },
        )
        stage['logs'] = logs[:200]

    _set_lit_stage5c_snapshot(lit_review, stage)


def _apply_lit_stage5c_completion(*, lit_review_id, summary):
    lit_review = LitReview.objects.get(pk=lit_review_id)
    stage = _get_lit_stage5c_snapshot(lit_review)
    stage['status'] = 'stopped' if summary.get('stopped') else 'completed'
    stage['completed_at'] = timezone.now().isoformat()
    stage['references_count'] = int(summary.get('references_count', stage.get('references_count', 0)))
    stage['used_paper_ids'] = list(summary.get('used_paper_ids', stage.get('used_paper_ids') or []))
    stage['missing_reference_paper_ids'] = list(
        summary.get('missing_reference_paper_ids', stage.get('missing_reference_paper_ids') or [])
    )
    stage['references_apa'] = list(summary.get('references_apa', stage.get('references_apa') or []))
    _set_lit_stage5c_snapshot(lit_review, stage)


def _mark_lit_stage5c_error(*, lit_review_id, exc):
    lit_review = LitReview.objects.get(pk=lit_review_id)
    stage = _get_lit_stage5c_snapshot(lit_review)
    stage['status'] = 'error'
    stage['error_code'] = exc.__class__.__name__
    stage['error_message'] = str(exc)
    stage['error_traceback'] = traceback.format_exc()
    stage['completed_at'] = timezone.now().isoformat()
    _set_lit_stage5c_snapshot(lit_review, stage)


def _get_lit_stage5c_snapshot(lit_review):
    stage_progress = lit_review.stage_progress or {}
    stage = stage_progress.get('stage5c_references', {})
    if not isinstance(stage, dict):
        stage = {}
    stage.setdefault('status', 'idle')
    stage.setdefault('references_count', 0)
    stage.setdefault('used_paper_ids', [])
    stage.setdefault('missing_reference_paper_ids', [])
    stage.setdefault('references_apa', [])
    stage.setdefault('stop_requested', False)
    stage.setdefault('logs', [])
    stage.setdefault('error_code', '')
    stage.setdefault('error_message', '')
    stage.setdefault('error_traceback', '')
    return stage


def _set_lit_stage5c_snapshot(lit_review, stage_payload):
    stage_progress = lit_review.stage_progress or {}
    stage_progress['stage5c_references'] = stage_payload
    lit_review.stage_progress = stage_progress
    lit_review.save(update_fields=['stage_progress'])


def _is_lit_stage5c_worker_alive(review_id):
    worker = _LIT_STAGE5C_WORKERS.get(review_id)
    if not worker:
        return False
    return worker.is_alive()


def _get_lit_title_extract_stage_snapshot(lit_review):
    stage_progress = lit_review.stage_progress or {}
    stage = stage_progress.get('stage2_title_extract', {})
    if not isinstance(stage, dict):
        stage = {}
    rows = stage.get('rows')
    if not isinstance(rows, list):
        rows = []
    return {'rows': rows}


def _set_lit_title_extract_stage_snapshot(lit_review, stage_payload):
    stage_progress = lit_review.stage_progress or {}
    stage_progress['stage2_title_extract'] = stage_payload
    lit_review.stage_progress = stage_progress
    lit_review.save(update_fields=['stage_progress'])
