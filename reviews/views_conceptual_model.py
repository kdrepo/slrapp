import threading
import traceback

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from .models import Review
from .services.conceptual_model_service import (
    generate_conceptual_model_spec,
)


class ConceptualModelMonitorView(View):
    template_name = 'reviews/conceptual_model_monitor.html'

    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        stage = _get_stage(review)
        scaffold = review.scaffold_data if isinstance(review.scaffold_data, dict) else {}
        return render(
            request,
            self.template_name,
            {
                'review': review,
                'stage': stage,
                'conceptual_model_spec': scaffold.get('conceptual_model_spec', {}),
                'conceptual_model_narrative': scaffold.get('conceptual_model_narrative', ''),
            },
        )

    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        stage = _get_stage(review)
        action = (request.POST.get('action') or '').strip().lower()

        if action == 'stop':
            if stage.get('status') not in {'running', 'queued', 'stopping'}:
                messages.warning(request, 'No active conceptual-model run is in progress.')
                return redirect('reviews:conceptual-model-monitor', pk=review.pk)
            stage['status'] = 'stopping'
            stage['stop_requested'] = True
            stage['stop_requested_at'] = timezone.now().isoformat()
            _set_stage(review, stage)
            messages.success(request, 'Stop requested.')
            return redirect('reviews:conceptual-model-monitor', pk=review.pk)

        if stage.get('status') in {'running', 'queued', 'stopping'}:
            messages.warning(request, 'Conceptual-model process is already running.')
            return redirect('reviews:conceptual-model-monitor', pk=review.pk)

        if action not in {'run_spec'}:
            messages.error(request, 'Invalid action.')
            return redirect('reviews:conceptual-model-monitor', pk=review.pk)

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
        messages.success(request, 'Conceptual model process started.')
        return redirect('reviews:conceptual-model-monitor', pk=review.pk)


class ConceptualModelStatusView(View):
    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        stage = dict(_get_stage(review))
        scaffold = review.scaffold_data if isinstance(review.scaffold_data, dict) else {}
        stage['conceptual_model_spec'] = scaffold.get('conceptual_model_spec', {})
        stage['conceptual_model_narrative'] = scaffold.get('conceptual_model_narrative', '')
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

        if action == 'run_spec':
            spec_result = generate_conceptual_model_spec(review_id)
            review = Review.objects.get(pk=review_id)
            stage = _get_stage(review)
            logs = list(stage.get('logs') or [])
            logs.insert(
                0,
                {
                    'time': timezone.now().isoformat(),
                    'event': 'spec_done',
                    'message': (
                        f"Spec generated: {spec_result.get('node_count', 0)} nodes, "
                        f"{spec_result.get('relationship_count', 0)} relationships. "
                        f"JSON: {', '.join(spec_result.get('generated', []))}"
                    ),
                },
            )
            stage['logs'] = logs[:300]
            _set_stage(review, stage)

        review = Review.objects.get(pk=review_id)
        stage = _get_stage(review)
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
    return progress.get('phase_19_conceptual_model', {})


def _set_stage(review, stage):
    progress = review.stage_progress or {}
    progress['phase_19_conceptual_model'] = stage
    review.stage_progress = progress
    review.save(update_fields=['stage_progress'])
