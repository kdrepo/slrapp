import threading
import traceback

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from .models import Review
from .services.mineru_service import clean_existing_mineru_references, parse_review_pdfs_with_mineru


class MinerUMonitorView(View):
    template_name = 'reviews/mineru_monitor.html'

    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        stage = _get_mineru_stage_snapshot(review)
        return render(request, self.template_name, {'review': review, 'stage': stage})

    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        stage = _get_mineru_stage_snapshot(review)
        action = (request.POST.get('action') or 'process_not_done').strip().lower()

        if action == 'stop':
            if stage.get('status') not in {'running', 'queued', 'stopping'}:
                messages.warning(request, 'No active MinerU run is in progress.')
                return redirect('reviews:mineru-monitor', pk=review.pk)
            updated = dict(stage)
            updated['status'] = 'stopping'
            updated['stop_requested'] = True
            updated['stop_requested_at'] = timezone.now().isoformat()
            _set_mineru_stage_snapshot(review, updated)
            messages.success(request, 'Stop requested for MinerU processing.')
            return redirect('reviews:mineru-monitor', pk=review.pk)

        if stage.get('status') in {'running', 'queued', 'stopping'}:
            messages.warning(request, 'MinerU processing is already running.')
            return redirect('reviews:mineru-monitor', pk=review.pk)

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
        _set_mineru_stage_snapshot(review, initial)

        if run_ref_delete:
            worker = threading.Thread(target=_run_mineru_ref_delete_async, args=(review.pk,), daemon=True)
            worker.start()
            messages.success(request, 'MinerU reference cleanup started for markdown records not yet cleaned.')
        else:
            worker = threading.Thread(target=_run_mineru_parse_async, args=(review.pk, retry_failed_only), daemon=True)
            worker.start()
            messages.success(request, 'MinerU markdown parsing started.')

        return redirect('reviews:mineru-monitor', pk=review.pk)


class MinerUStatusView(View):
    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        return JsonResponse(_get_mineru_stage_snapshot(review))


def _run_mineru_parse_async(review_id, retry_failed_only):
    def _should_stop():
        review = Review.objects.get(pk=review_id)
        stage = _get_mineru_stage_snapshot(review)
        return bool(stage.get('stop_requested'))

    def _progress(event):
        _apply_progress(review_id, event)

    try:
        summary = parse_review_pdfs_with_mineru(
            review_id=review_id,
            retry_failed_only=retry_failed_only,
            progress_callback=_progress,
            stop_check=_should_stop,
        )
        _apply_completion(review_id, summary)
    except Exception as exc:
        _mark_error(review_id, exc)


def _run_mineru_ref_delete_async(review_id):
    def _should_stop():
        review = Review.objects.get(pk=review_id)
        stage = _get_mineru_stage_snapshot(review)
        return bool(stage.get('stop_requested'))

    def _progress(event):
        _apply_progress(review_id, event)

    try:
        summary = clean_existing_mineru_references(
            review_id=review_id,
            progress_callback=_progress,
            stop_check=_should_stop,
        )
        _apply_completion(review_id, summary)
    except Exception as exc:
        _mark_error(review_id, exc)


def _apply_progress(review_id, event):
    review = Review.objects.get(pk=review_id)
    stage = _get_mineru_stage_snapshot(review)
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
        elif event_name == 'failed':
            stage['failed'] = int(stage.get('failed', 0)) + 1

    if event_name in {'processing', 'done', 'failed', 'stopped'}:
        logs.insert(0, {
            'time': timezone.now().isoformat(),
            'event': event_name,
            'paper_id': paper_id,
            'title': title,
            'batch_id': batch_id,
            'markdown_chars': markdown_chars,
            'error_message': error_message,
        })
        stage['logs'] = logs[:500]

    _set_mineru_stage_snapshot(review, stage)


def _apply_completion(review_id, summary):
    review = Review.objects.get(pk=review_id)
    stage = _get_mineru_stage_snapshot(review)
    stage['status'] = 'stopped' if summary.get('stopped') else 'completed'
    stage['completed_at'] = timezone.now().isoformat()
    stage['targeted'] = int(summary.get('targeted', stage.get('targeted', 0)))
    stage['processed'] = int(summary.get('processed', stage.get('processed', 0)))
    stage['done'] = int(summary.get('done', stage.get('done', 0)))
    stage['failed'] = int(summary.get('failed', stage.get('failed', 0)))
    stage['processed_paper_ids'] = list(summary.get('processed_ids', stage.get('processed_paper_ids') or []))
    stage['remaining_paper_ids'] = list(summary.get('remaining_paper_ids', stage.get('remaining_paper_ids') or []))
    _set_mineru_stage_snapshot(review, stage)


def _mark_error(review_id, exc):
    review = Review.objects.get(pk=review_id)
    stage = _get_mineru_stage_snapshot(review)
    stage['status'] = 'error'
    stage['error_code'] = exc.__class__.__name__
    stage['error_message'] = str(exc)
    stage['error_traceback'] = traceback.format_exc()
    stage['completed_at'] = timezone.now().isoformat()
    _set_mineru_stage_snapshot(review, stage)


def _get_mineru_stage_snapshot(review):
    stage_progress = review.stage_progress or {}
    return stage_progress.get('phase_11_mineru', {})


def _set_mineru_stage_snapshot(review, stage_payload):
    stage_progress = review.stage_progress or {}
    stage_progress['phase_11_mineru'] = stage_payload
    review.stage_progress = stage_progress
    review.save(update_fields=['stage_progress'])
