import threading
import traceback

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from .models import Review
from .services.theoretical_anchoring_service import (
    run_cross_theme_theoretical_synthesis_for_review,
    run_theory_landscape_for_review,
)
from .services.scaffold_service import get_scaffold_data, set_scaffold_data


class TheoryAnchoringMonitorView(View):
    template_name = 'reviews/theory_anchoring_monitor.html'

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
                'theoretical_framework': scaffold_data.get('theoretical_framework', {}),
                'theory_landscape': scaffold_data.get('theory_landscape', {}),
                'theoretical_synthesis': scaffold_data.get('theoretical_synthesis', {}),
            },
        )

    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        stage = _get_stage(review)
        action = (request.POST.get('action') or '').strip().lower()

        if action in {'confirm_recommended_lens', 'confirm_alternative_lens'}:
            scaffold_data = get_scaffold_data(review)
            tf = scaffold_data.get('theoretical_framework', {}) if isinstance(scaffold_data.get('theoretical_framework'), dict) else {}
            recommended = str(tf.get('recommended') or '').strip()
            selected = recommended if action == 'confirm_recommended_lens' else str(request.POST.get('selected_lens') or '').strip()
            if not selected:
                messages.error(request, 'No lens selected for confirmation.')
                return redirect('reviews:theory-anchoring-monitor', pk=review.pk)

            tf['primary_lens'] = selected
            tf['status'] = 'confirmed'
            scaffold_data['theoretical_framework'] = tf
            set_scaffold_data(review, scaffold_data)
            review.status = Review.Status.RUNNING

            stage = _get_stage(review)
            logs = list(stage.get('logs') or [])
            logs.insert(
                0,
                {
                    'time': timezone.now().isoformat(),
                    'event': 'lens_confirmed',
                    'message': f'Theoretical lens confirmed: {selected}',
                },
            )
            stage['logs'] = logs[:300]
            _set_stage(review, stage)
            review.save(update_fields=['scaffold_data', 'status'])
            messages.success(request, f'Theoretical lens confirmed: {selected}')
            return redirect('reviews:theory-anchoring-monitor', pk=review.pk)

        if action == 'stop':
            if stage.get('status') not in {'running', 'queued', 'stopping'}:
                messages.warning(request, 'No active theoretical anchoring run is in progress.')
                return redirect('reviews:theory-anchoring-monitor', pk=review.pk)
            stage['status'] = 'stopping'
            stage['stop_requested'] = True
            stage['stop_requested_at'] = timezone.now().isoformat()
            _set_stage(review, stage)
            messages.success(request, 'Stop requested.')
            return redirect('reviews:theory-anchoring-monitor', pk=review.pk)

        if stage.get('status') in {'running', 'queued', 'stopping'}:
            messages.warning(request, 'Theoretical anchoring process is already running.')
            return redirect('reviews:theory-anchoring-monitor', pk=review.pk)

        if action not in {'run_landscape', 'run_cross_theme'}:
            messages.error(request, 'Invalid action.')
            return redirect('reviews:theory-anchoring-monitor', pk=review.pk)

        initial = {
            'status': 'running',
            'started_at': timezone.now().isoformat(),
            'stop_requested': False,
            'error_code': '',
            'error_message': '',
            'logs': [],
            'current_action': action,
        }
        _set_stage(review, initial)

        worker = threading.Thread(target=_run_async, args=(review.pk, action), daemon=True)
        worker.start()
        messages.success(
            request,
            'Theory landscape started.' if action == 'run_landscape' else 'Cross-theme theoretical synthesis started.',
        )
        return redirect('reviews:theory-anchoring-monitor', pk=review.pk)


class TheoryAnchoringStatusView(View):
    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        stage = dict(_get_stage(review))
        scaffold_data = review.scaffold_data if isinstance(review.scaffold_data, dict) else {}
        stage['theoretical_framework'] = scaffold_data.get('theoretical_framework', {})
        stage['theory_landscape'] = scaffold_data.get('theory_landscape', {})
        stage['theoretical_synthesis'] = scaffold_data.get('theoretical_synthesis', {})
        checks = scaffold_data.get('consistency_checks', {}) if isinstance(scaffold_data.get('consistency_checks', {}), dict) else {}
        stage['theory_consistency_check'] = checks.get('theory_landscape_vs_tccm', {})
        return JsonResponse(stage)


def _run_async(review_id, action):
    try:
        review = Review.objects.get(pk=review_id)
        stage = _get_stage(review)
        if stage.get('stop_requested'):
            stage['status'] = 'stopped'
            stage['completed_at'] = timezone.now().isoformat()
            _set_stage(review, stage)
            return

        if action == 'run_landscape':
            result = run_theory_landscape_for_review(review_id=review_id)
            msg = f"Theory landscape done for {result.get('total_papers', 0)} papers. Dominant: {result.get('dominant_theory', 'N/A')}."
        else:
            result = run_cross_theme_theoretical_synthesis_for_review(review_id=review_id)
            msg = f"Cross-theme synthesis done. Themes: {result.get('theme_count', 0)}, propositions: {result.get('proposition_count', 0)}."

        review = Review.objects.get(pk=review_id)
        stage = _get_stage(review)
        logs = list(stage.get('logs') or [])
        logs.insert(0, {'time': timezone.now().isoformat(), 'event': 'completed', 'message': msg})
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
    return progress.get('phase_17a_theory_anchoring', {})


def _set_stage(review, stage):
    progress = review.stage_progress or {}
    progress['phase_17a_theory_anchoring'] = stage
    review.stage_progress = progress
    review.save(update_fields=['stage_progress'])
