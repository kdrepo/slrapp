import threading
import traceback

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from .models import Paper, Review
from .services.deepseek_summary_service import run_deepseek_summery_for_review


class DeepSeekSummeryMonitorView(View):
    template_name = 'reviews/deepseek_summery_monitor.html'

    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        stage = _get_stage(review)
        completed = _completed_rows(review)
        return render(request, self.template_name, {'review': review, 'stage': stage, 'completed': completed})

    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        stage = _get_stage(review)
        action = (request.POST.get('action') or 'start').strip().lower()

        if action == 'stop':
            if stage.get('status') not in {'running', 'queued', 'stopping'}:
                messages.warning(request, 'No active DeepSeek summery run is in progress.')
                return redirect('reviews:deepseek-summery-monitor', pk=review.pk)
            stage['status'] = 'stopped'
            stage['stop_requested'] = True
            stage['stop_requested_at'] = timezone.now().isoformat()
            _set_stage(review, stage)
            messages.success(request, 'Stop requested for DeepSeek summery processing.')
            return redirect('reviews:deepseek-summery-monitor', pk=review.pk)

        if stage.get('status') in {'running', 'queued', 'stopping'}:
            messages.warning(request, 'DeepSeek summery processing is already running.')
            return redirect('reviews:deepseek-summery-monitor', pk=review.pk)

        retry_failed_only = action == 'retry_failed'
        initial = {
            'status': 'running',
            'started_at': timezone.now().isoformat(),
            'targeted': 0,
            'processed': 0,
            'done': 0,
            'failed': 0,
            'stop_requested': False,
            'error_code': '',
            'error_message': '',
            'error_traceback': '',
            'logs': [],
            'retry_failed_only': retry_failed_only,
        }
        _set_stage(review, initial)

        worker = threading.Thread(target=_run_async, args=(review.pk, retry_failed_only), daemon=True)
        worker.start()

        if retry_failed_only:
            messages.success(request, 'DeepSeek summery retry for failed papers started.')
        else:
            messages.success(request, 'DeepSeek summery extraction started.')
        return redirect('reviews:deepseek-summery-monitor', pk=review.pk)


class DeepSeekSummeryStatusView(View):
    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        payload = dict(_get_stage(review))
        payload['completed'] = _completed_rows(review)
        return JsonResponse(payload)


def _run_async(review_id, retry_failed_only):
    def _should_stop():
        review = Review.objects.get(pk=review_id)
        stage = _get_stage(review)
        return bool(stage.get('stop_requested'))

    def _progress(event):
        review = Review.objects.get(pk=review_id)
        stage = _get_stage(review)
        event_name = event.get('event')

        if event_name == 'started':
            stage['targeted'] = int(event.get('targeted', 0) or 0)
        elif event_name in {'done', 'failed'}:
            stage['processed'] = int(stage.get('processed', 0)) + 1
            if event_name == 'done':
                stage['done'] = int(stage.get('done', 0)) + 1
            else:
                stage['failed'] = int(stage.get('failed', 0)) + 1

        if event_name in {'processing', 'done', 'failed', 'stopped'}:
            logs = list(stage.get('logs') or [])
            logs.insert(0, {
                'time': timezone.now().isoformat(),
                'event': event_name,
                'paper_id': event.get('paper_id'),
                'title': (event.get('title') or '')[:220],
                'error_code': event.get('error_code') or '',
                'error_message': event.get('error_message') or '',
            })
            stage['logs'] = logs[:500]

        _set_stage(review, stage)

    try:
        summary = run_deepseek_summery_for_review(
            review_id=review_id,
            progress_callback=_progress,
            stop_check=_should_stop,
            retry_failed_only=retry_failed_only,
        )

        review = Review.objects.get(pk=review_id)
        stage = _get_stage(review)
        stage['status'] = 'stopped' if summary.get('stopped') else 'completed'
        stage['completed_at'] = timezone.now().isoformat()
        stage['targeted'] = int(summary.get('targeted', stage.get('targeted', 0)))
        stage['processed'] = int(summary.get('processed', stage.get('processed', 0)))
        stage['done'] = int(summary.get('done', stage.get('done', 0)))
        stage['failed'] = int(summary.get('failed', stage.get('failed', 0)))
        _set_stage(review, stage)
    except Exception as exc:
        review = Review.objects.get(pk=review_id)
        stage = _get_stage(review)
        stage['status'] = 'error'
        stage['error_code'] = exc.__class__.__name__
        stage['error_message'] = str(exc)
        stage['error_traceback'] = traceback.format_exc()
        stage['completed_at'] = timezone.now().isoformat()
        _set_stage(review, stage)


def _get_stage(review):
    progress = review.stage_progress or {}
    return progress.get('phase_16_deepseek_summery', {})


def _set_stage(review, stage):
    progress = review.stage_progress or {}
    progress['phase_16_deepseek_summery'] = stage
    review.stage_progress = progress
    review.save(update_fields=['stage_progress'])


def _completed_rows(review):
    rows = review.papers.filter(
        full_text_decision=Paper.FullTextDecision.INCLUDED,
        fulltext_retrieved=True,
    ).exclude(full_text_summery_status='').exclude(full_text_summery_status='not_started').order_by('id').values(
        'id',
        'title',
        'full_text_summery_status',
        'full_text_summery_error',
        'full_text_summery_updated_at',
        'full_text_summery',
        'full_text_extraction',
        'full_text_quality',
    )

    output = []
    for row in rows:
        summary_data = row.get('full_text_summery')
        extraction_data = row.get('full_text_extraction')
        quality_data = row.get('full_text_quality')

        summary_text = ''
        if isinstance(summary_data, str):
            summary_text = summary_data
        elif isinstance(summary_data, dict):
            summary_text = str(summary_data.get('summary') or '')

        total_score = ''
        risk_of_bias = ''
        if isinstance(quality_data, dict):
            total_score = quality_data.get('total_score', '')
            risk_of_bias = quality_data.get('risk_of_bias', '')

        output.append(
            {
                'id': row['id'],
                'title': row['title'],
                'full_text_summery_status': row.get('full_text_summery_status') or '',
                'full_text_summery_error': row.get('full_text_summery_error') or '',
                'full_text_summery_updated_at': row.get('full_text_summery_updated_at'),
                'summary_chars': len(summary_text),
                'has_extraction': isinstance(extraction_data, dict) and bool(extraction_data),
                'has_quality': isinstance(quality_data, dict) and bool(quality_data),
                'quality_total_score': total_score,
                'quality_risk_of_bias': risk_of_bias,
            }
        )

    return output
