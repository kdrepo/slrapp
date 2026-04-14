import threading
import traceback

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from .models import Review
from .services.ghostwriter_service import SECTION_MAP, run_ghostwriter


class GhostwriterMonitorView(View):
    template_name = 'reviews/ghostwriter_monitor.html'

    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        stage = _get_stage(review)
        sections = _ordered_sections(stage)
        return render(request, self.template_name, {'review': review, 'stage': stage, 'sections': sections})

    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        stage = _get_stage(review)
        action = (request.POST.get('action') or 'write_next').strip().lower()
        section_key = (request.POST.get('section_key') or '').strip()

        if action == 'stop':
            if stage.get('status') not in {'running', 'queued', 'stopping'}:
                messages.warning(request, 'No active ghostwriter run is in progress.')
                return redirect('reviews:ghostwriter-monitor', pk=review.pk)
            stage['status'] = 'stopping'
            stage['stop_requested'] = True
            stage['stop_requested_at'] = timezone.now().isoformat()
            _set_stage(review, stage)
            messages.success(request, 'Stop requested for ghostwriter run.')
            return redirect('reviews:ghostwriter-monitor', pk=review.pk)

        if stage.get('status') in {'running', 'queued'}:
            messages.warning(request, 'Ghostwriter is already running.')
            return redirect('reviews:ghostwriter-monitor', pk=review.pk)

        mode = 'next'
        retry = False
        if action == 'write_all':
            mode = 'all'
        elif action == 'write_section':
            mode = 'section'
        elif action == 'retry_failed':
            mode = 'failed'
            retry = True

        stage['status'] = 'running'
        stage['stop_requested'] = False
        stage['started_at'] = timezone.now().isoformat()
        stage['error_code'] = ''
        stage['error_message'] = ''
        _set_stage(review, stage)

        worker = threading.Thread(
            target=_run_async,
            args=(review.pk, mode, section_key, retry),
            daemon=True,
        )
        worker.start()

        messages.success(request, 'Ghostwriter run started.')
        return redirect('reviews:ghostwriter-monitor', pk=review.pk)


class GhostwriterStatusView(View):
    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        stage = dict(_get_stage(review))
        stage['sections_ordered'] = _ordered_sections(stage)
        return JsonResponse(stage)


def _run_async(review_id, mode, section_key, retry):
    try:
        result = run_ghostwriter(review_id=review_id, mode=mode, section_key=section_key, retry=retry)
        review = Review.objects.get(pk=review_id)
        stage = _get_stage(review)
        logs = list(stage.get('logs') or [])
        stopped = bool(result.get('stopped'))
        logs.insert(
            0,
            {
                'time': timezone.now().isoformat(),
                'event': 'stopped' if stopped else 'completed',
                'message': f"Ghostwriter wrote {result.get('written', 0)} section(s).",
            },
        )
        stage['logs'] = logs[:300]
        stage['status'] = 'stopped' if stopped else stage.get('status', 'completed')
        if stage['status'] not in {'completed', 'error', 'stopped'}:
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


def _ordered_sections(stage):
    sections = stage.get('sections', {}) if isinstance(stage.get('sections', {}), dict) else {}
    out = []
    for item in SECTION_MAP:
        data = sections.get(item['key'], {}) if isinstance(sections.get(item['key'], {}), dict) else {}
        out.append(
            {
                'key': item['key'],
                'name': item['name'],
                'status': data.get('status', 'pending'),
                'word_count': data.get('word_count', 0),
                'updated_at': data.get('updated_at', ''),
                'error': data.get('error', ''),
                'text_preview': (data.get('text') or '')[:240],
            }
        )
    return out


def _get_stage(review):
    progress = review.stage_progress or {}
    stage = progress.get('phase_23_ghostwriter', {})
    if not isinstance(stage, dict):
        stage = {}
    stage.setdefault('status', 'idle')
    stage.setdefault('stop_requested', False)
    stage.setdefault('logs', [])
    stage.setdefault('sections', {})
    stage.setdefault('compiled_draft', '')
    return stage


def _set_stage(review, stage):
    progress = review.stage_progress or {}
    progress['phase_23_ghostwriter'] = stage
    review.stage_progress = progress
    review.save(update_fields=['stage_progress'])
