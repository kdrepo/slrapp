import threading
import traceback

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from .models import Review
from .services.dialectical_synthesizer import run_dialectical_synthesis


class DialecticalMonitorView(View):
    template_name = 'reviews/dialectical_monitor.html'

    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        stage = _get_stage(review)
        themes = review.theme_syntheses.all().order_by('order_index', 'id')
        return render(request, self.template_name, {'review': review, 'stage': stage, 'themes': themes})

    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        stage = _get_stage(review)
        action = (request.POST.get('action') or 'start').strip().lower()

        if action == 'stop':
            if stage.get('status') not in {'running', 'queued', 'stopping'}:
                messages.warning(request, 'No active dialectical synthesis run is in progress.')
                return redirect('reviews:dialectical-monitor', pk=review.pk)
            stage['status'] = 'stopping'
            stage['stop_requested'] = True
            stage['stop_requested_at'] = timezone.now().isoformat()
            _set_stage(review, stage)
            messages.success(request, 'Stop requested for dialectical synthesis.')
            return redirect('reviews:dialectical-monitor', pk=review.pk)

        if stage.get('status') in {'running', 'queued'}:
            messages.warning(request, 'Dialectical synthesis is already running.')
            return redirect('reviews:dialectical-monitor', pk=review.pk)

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

        messages.success(request, 'Dialectical synthesis started.' if not retry else 'Dialectical synthesis retry started.')
        return redirect('reviews:dialectical-monitor', pk=review.pk)


class DialecticalStatusView(View):
    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        stage = dict(_get_stage(review))
        rows = []
        for t in review.theme_syntheses.all().order_by('order_index', 'id'):
            rows.append(
                {
                    'id': t.id,
                    'theme_name': t.theme_name_locked,
                    'grade': t.evidence_grade,
                    'paper_count': t.paper_count,
                    'has_advocate': bool((t.advocate_notes or '').strip()),
                    'has_critic': bool((t.critic_notes or '').strip()),
                    'has_reconciled': bool((t.reconciled_text or t.reconciler_notes or '').strip()),
                    'reconciled_preview': (t.reconciled_text or t.reconciler_notes or '')[:200],
                }
            )
        stage['themes'] = rows
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

        result = run_dialectical_synthesis(review_id)

        review = Review.objects.get(pk=review_id)
        stage = _get_stage(review)
        logs = list(stage.get('logs') or [])
        stopped = bool(result.get('stopped'))
        logs.insert(
            0,
            {
                'time': timezone.now().isoformat(),
                'event': 'stopped' if stopped else 'completed',
                'message': (
                    f"Dialectical synthesis stopped after updating {result.get('updated', 0)} themes; failed {result.get('failed', 0)}."
                    if stopped
                    else f"Dialectical synthesis updated {result.get('updated', 0)} themes; failed {result.get('failed', 0)}."
                ),
            },
        )
        stage['logs'] = logs[:300]
        stage['status'] = 'stopped' if stopped else 'completed'
        stage['completed_at'] = timezone.now().isoformat()
        _set_stage(review, stage)
    except Exception as exc:
        review = Review.objects.get(pk=review_id)
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
    return progress.get('phase_18_dialectical', {})


def _set_stage(review, stage):
    progress = review.stage_progress or {}
    progress['phase_18_dialectical'] = stage
    review.stage_progress = progress
    review.save(update_fields=['stage_progress'])
