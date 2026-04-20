import threading
import traceback

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from .models import Review
from .services.tccm_service import run_tccm_aggregation_for_review


class TCCMMonitorView(View):
    template_name = 'reviews/tccm_monitor.html'

    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        stage = _get_stage(review)
        scaffold_data = review.scaffold_data if isinstance(review.scaffold_data, dict) else {}
        return render(
            request,
            self.template_name,
            {
                'review': review,
                'stage': stage,
                'tccm_summary': scaffold_data.get('tccm_summary', {}),
            },
        )

    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        stage = _get_stage(review)
        action = (request.POST.get('action') or '').strip().lower()

        if action == 'stop':
            if stage.get('status') not in {'running', 'queued', 'stopping'}:
                messages.warning(request, 'No active TCCM run is in progress.')
                return redirect('reviews:tccm-monitor', pk=review.pk)
            stage['status'] = 'stopping'
            stage['stop_requested'] = True
            stage['stop_requested_at'] = timezone.now().isoformat()
            _set_stage(review, stage)
            messages.success(request, 'Stop requested for TCCM aggregation.')
            return redirect('reviews:tccm-monitor', pk=review.pk)

        if stage.get('status') in {'running', 'queued', 'stopping'}:
            messages.warning(request, 'TCCM aggregation is already running.')
            return redirect('reviews:tccm-monitor', pk=review.pk)

        if action not in {'start', 'retry'}:
            messages.error(request, 'Invalid action.')
            return redirect('reviews:tccm-monitor', pk=review.pk)

        _set_stage(
            review,
            {
                'status': 'running',
                'started_at': timezone.now().isoformat(),
                'stop_requested': False,
                'error_code': '',
                'error_message': '',
                'logs': [],
                'retry': action == 'retry',
            },
        )

        worker = threading.Thread(target=_run_async, args=(review.pk,), daemon=True)
        worker.start()
        messages.success(request, 'TCCM aggregation started.')
        return redirect('reviews:tccm-monitor', pk=review.pk)


class TCCMStatusView(View):
    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        stage = dict(_get_stage(review))
        scaffold_data = review.scaffold_data if isinstance(review.scaffold_data, dict) else {}
        stage['tccm_summary'] = scaffold_data.get('tccm_summary', {})
        checks = scaffold_data.get('consistency_checks', {}) if isinstance(scaffold_data.get('consistency_checks', {}), dict) else {}
        stage['theory_consistency_check'] = checks.get('theory_landscape_vs_tccm', {})
        return JsonResponse(stage)


def _run_async(review_id):
    try:
        review = Review.objects.get(pk=review_id)
        stage = _get_stage(review)
        if stage.get('stop_requested'):
            stage['status'] = 'stopped'
            stage['completed_at'] = timezone.now().isoformat()
            _set_stage(review, stage)
            return

        result = run_tccm_aggregation_for_review(review_id=review_id)

        review = Review.objects.get(pk=review_id)
        stage = _get_stage(review)
        logs = list(stage.get('logs') or [])
        logs.insert(
            0,
            {
                'time': timezone.now().isoformat(),
                'event': 'completed',
                'message': (
                    f"TCCM aggregation done for {result.get('total_papers', 0)} papers. "
                    f"Saved as {result.get('stored_key')}."
                ),
            },
        )
        consistency = result.get('consistency') if isinstance(result.get('consistency'), dict) else {}
        if consistency and consistency.get('status') == 'warning_mismatch':
            logs.insert(
                0,
                {
                    'time': timezone.now().isoformat(),
                    'event': 'consistency_warning',
                    'message': str(consistency.get('message') or 'Theory consistency warning.'),
                },
            )
        stage['logs'] = logs[:300]
        stage['status'] = 'completed'
        stage['completed_at'] = timezone.now().isoformat()
        _set_stage(review, stage)
    except Exception as exc:
        review = Review.objects.get(pk=review_id)
        stage = _get_stage(review)
        logs = list(stage.get('logs') or [])
        logs.insert(
            0,
            {
                'time': timezone.now().isoformat(),
                'event': 'failed',
                'error_code': exc.__class__.__name__,
                'error_message': str(exc),
            },
        )
        stage['logs'] = logs[:300]
        stage['status'] = 'error'
        stage['error_code'] = exc.__class__.__name__
        stage['error_message'] = str(exc)
        stage['error_traceback'] = traceback.format_exc()
        stage['completed_at'] = timezone.now().isoformat()
        _set_stage(review, stage)


def _get_stage(review):
    progress = review.stage_progress or {}
    return progress.get('phase_20_tccm', {})


def _set_stage(review, stage):
    progress = review.stage_progress or {}
    progress['phase_20_tccm'] = stage
    review.stage_progress = progress
    review.save(update_fields=['stage_progress'])
