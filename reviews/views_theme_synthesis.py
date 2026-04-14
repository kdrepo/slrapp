import threading
import traceback

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from .models import Review
from .services.theme_synthesis_service import synthesize_themes_for_review


class ThemeSynthesisMonitorView(View):
    template_name = 'reviews/theme_synthesis_monitor.html'

    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        stage = _get_stage(review)
        themes = review.theme_synthesis or []
        return render(request, self.template_name, {'review': review, 'stage': stage, 'themes': themes})

    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        stage = _get_stage(review)
        action = (request.POST.get('action') or 'start').strip().lower()

        if action == 'stop':
            if stage.get('status') not in {'running', 'queued', 'stopping'}:
                messages.warning(request, 'No active thematic synthesis run is in progress.')
                return redirect('reviews:theme-synthesis-monitor', pk=review.pk)
            stage['status'] = 'stopping'
            stage['stop_requested'] = True
            stage['stop_requested_at'] = timezone.now().isoformat()
            _set_stage(review, stage)
            messages.success(request, 'Stop requested for thematic synthesis.')
            return redirect('reviews:theme-synthesis-monitor', pk=review.pk)

        if stage.get('status') in {'running', 'queued'}:
            messages.warning(request, 'Thematic synthesis is already running.')
            return redirect('reviews:theme-synthesis-monitor', pk=review.pk)

        retry = action == 'retry'
        initial = {
            'status': 'running',
            'started_at': timezone.now().isoformat(),
            'stop_requested': False,
            'error_code': '',
            'error_message': '',
            'logs': [],
            'retry': retry,
        }
        _set_stage(review, initial)

        worker = threading.Thread(target=_run_async, args=(review.pk,), daemon=True)
        worker.start()

        if retry:
            messages.success(request, 'Thematic synthesis retry started.')
        else:
            messages.success(request, 'Thematic synthesis started.')
        return redirect('reviews:theme-synthesis-monitor', pk=review.pk)


class ThemeSynthesisStatusView(View):
    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        payload = dict(_get_stage(review))
        payload['themes'] = review.theme_synthesis or []
        payload['theme_synthesis_status'] = review.theme_synthesis_status or ''
        payload['theme_synthesis_error'] = review.theme_synthesis_error or ''
        payload['theme_synthesis_updated_at'] = review.theme_synthesis_updated_at.isoformat() if review.theme_synthesis_updated_at else None
        return JsonResponse(payload)


def _run_async(review_id):
    try:
        review = Review.objects.get(pk=review_id)
        stage = _get_stage(review)
        if stage.get('stop_requested'):
            stage['status'] = 'stopped'
            stage['completed_at'] = timezone.now().isoformat()
            _set_stage(review, stage)
            return

        result = synthesize_themes_for_review(review_id)

        review = Review.objects.get(pk=review_id)
        review.theme_synthesis_status = 'done'
        review.theme_synthesis_error = ''
        review.theme_synthesis_updated_at = timezone.now()
        review.save(update_fields=['theme_synthesis_status', 'theme_synthesis_error', 'theme_synthesis_updated_at'])

        stage = _get_stage(review)
        logs = list(stage.get('logs') or [])
        logs.insert(0, {
            'time': timezone.now().isoformat(),
            'event': 'completed',
            'theme_count': result.get('theme_count', 0),
            'total_papers': result.get('total_papers', 0),
            'message': f"Generated {result.get('theme_count', 0)} themes from {result.get('total_papers', 0)} papers.",
        })
        stage['logs'] = logs[:300]
        stage['status'] = 'completed'
        stage['completed_at'] = timezone.now().isoformat()
        _set_stage(review, stage)
    except Exception as exc:
        review = Review.objects.get(pk=review_id)
        review.theme_synthesis_status = 'failed'
        review.theme_synthesis_error = f'{exc.__class__.__name__}: {exc}'
        review.theme_synthesis_updated_at = timezone.now()
        review.save(update_fields=['theme_synthesis_status', 'theme_synthesis_error', 'theme_synthesis_updated_at'])

        stage = _get_stage(review)
        logs = list(stage.get('logs') or [])
        logs.insert(0, {
            'time': timezone.now().isoformat(),
            'event': 'failed',
            'error_code': exc.__class__.__name__,
            'error_message': str(exc),
        })
        stage['logs'] = logs[:300]
        stage['status'] = 'error'
        stage['error_code'] = exc.__class__.__name__
        stage['error_message'] = str(exc)
        stage['error_traceback'] = traceback.format_exc()
        stage['completed_at'] = timezone.now().isoformat()
        _set_stage(review, stage)


def _get_stage(review):
    progress = review.stage_progress or {}
    return progress.get('phase_17_theme_synthesis', {})


def _set_stage(review, stage):
    progress = review.stage_progress or {}
    progress['phase_17_theme_synthesis'] = stage
    review.stage_progress = progress
    review.save(update_fields=['stage_progress'])
