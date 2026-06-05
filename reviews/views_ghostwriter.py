import threading
import traceback

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from .models import Review
from .services.ghostwriter_service import SECTION_MAP, run_ghostwriter

THEORY_OPTION_KEYS = {'3_5_theory'}
TCCM_OPTION_KEYS = {'3_2_char'}
FUTURE_RESEARCH_KEY = '4_4_future'


class GhostwriterMonitorView(View):
    template_name = 'reviews/ghostwriter_monitor.html'

    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        stage = _get_stage(review)
        sections = _ordered_sections(stage)
        return render(
            request,
            self.template_name,
            {
                'review': review,
                'stage': stage,
                'sections': sections,
                'options': _get_options(stage),
                'active_toc': _active_toc(stage),
            },
        )

    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        stage = _get_stage(review)
        action = (request.POST.get('action') or 'write_next').strip().lower()
        section_key = (request.POST.get('section_key') or '').strip()

        if action == 'update_options':
            if stage.get('status') in {'running', 'queued', 'stopping'}:
                messages.warning(request, 'Cannot update writing options while ghostwriter is running.')
                return redirect('reviews:ghostwriter-monitor', pk=review.pk)
            requested_theory = bool(request.POST.get('include_theoretical_framework'))
            requested_model = bool(request.POST.get('include_conceptual_model'))
            stage['options'] = _parse_options_from_post(request.POST)
            _apply_options_to_sections(stage)
            _set_stage(review, stage)
            if requested_model and not requested_theory:
                messages.warning(
                    request,
                    'Conceptual Model requires Theoretical Framework Anchoring. '
                    'Theoretical Framework was automatically enabled.',
                )
            messages.success(request, 'Ghostwriter writing options updated.')
            return redirect('reviews:ghostwriter-monitor', pk=review.pk)

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
        custom_prompt = None
        if action == 'write_all':
            mode = 'all'
        elif action == 'write_section':
            mode = 'section'
            custom_prompt = request.POST.get('custom_prompt') or None
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
            args=(review.pk, mode, section_key, retry, custom_prompt),
            daemon=True,
        )
        worker.start()

        messages.success(request, 'Ghostwriter run started.')
        return redirect('reviews:ghostwriter-monitor', pk=review.pk)

class GhostwriterPromptPreviewView(View):
    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        section_key = request.GET.get('section_key')
        if not section_key:
            return JsonResponse({'error': 'section_key is required'}, status=400)
        
        try:
            service = __import__('reviews.services.ghostwriter_service', fromlist=['GhostwriterService']).GhostwriterService(review_id=review.pk)
            prompt = service.get_section_prompt(section_key=section_key)
            return JsonResponse({'prompt': prompt})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

class GhostwriterStatusView(View):
    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        stage = dict(_get_stage(review))
        stage['sections_ordered'] = _ordered_sections(stage)
        stage['options'] = _get_options(stage)
        stage['active_toc'] = _active_toc(stage)
        return JsonResponse(stage)


def _run_async(review_id, mode, section_key, retry, custom_prompt=None):
    try:
        service = __import__('reviews.services.ghostwriter_service', fromlist=['GhostwriterService']).GhostwriterService(review_id=review_id)
        if custom_prompt and mode == 'section' and section_key:
            # We override the run method slightly if a custom prompt is provided for a specific section
            stage = service._ensure_stage()
            stage['status'] = 'running'
            stage['started_at'] = timezone.now().isoformat()
            stage['error_code'] = ''
            stage['error_message'] = ''
            stage['stop_requested'] = False
            stage['current_section_key'] = section_key
            sec = stage['sections'][section_key]
            sec['status'] = 'running'
            sec['error'] = ''
            service._save_stage(stage)

            try:
                text = service._write_section(stage=stage, section_key=section_key, custom_prompt=custom_prompt)
                stage = service._ensure_stage()
                sec = stage['sections'][section_key]
                sec['text'] = text
                sec['status'] = 'done'
                sec['updated_at'] = timezone.now().isoformat()
                sec['word_count'] = service._word_count(text)
                service._log(stage, 'section_done', f'{section_key} written with custom prompt ({sec["word_count"]} words).')
                service._save_stage(stage)
                written = 1
            except Exception as exc:
                stage = service._ensure_stage()
                sec = stage['sections'][section_key]
                sec['status'] = 'failed'
                sec['error'] = f'{exc.__class__.__name__}: {exc}'
                sec['updated_at'] = timezone.now().isoformat()
                service._log(stage, 'section_failed', f'{section_key} failed: {exc.__class__.__name__}: {exc}')
                stage['status'] = 'error'
                stage['error_code'] = exc.__class__.__name__
                stage['error_message'] = str(exc)
                stage['completed_at'] = timezone.now().isoformat()
                service._save_stage(stage)
                written = 0

            stage = service._ensure_stage()
            stage['current_section_key'] = ''
            stage['status'] = 'completed' if service._all_done(stage) else 'idle'
            stage['completed_at'] = timezone.now().isoformat()
            stage['compiled_draft'] = service._compile_draft(stage)
            service._save_stage(stage)
            result = {'written': written, 'stopped': False}
        else:
            result = service.run(mode=mode, section_key=section_key, retry=retry)
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
    active_keys = set(_active_section_keys(stage))
    sections = stage.get('sections', {}) if isinstance(stage.get('sections', {}), dict) else {}
    out = []
    for item in SECTION_MAP:
        data = sections.get(item['key'], {}) if isinstance(sections.get(item['key'], {}), dict) else {}
        out.append(
            {
                'key': item['key'],
                'name': item['name'],
                'included': item['key'] in active_keys,
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
    stage.setdefault('options', _default_options())
    return stage


def _set_stage(review, stage):
    progress = review.stage_progress or {}
    progress['phase_23_ghostwriter'] = stage
    review.stage_progress = progress
    review.save(update_fields=['stage_progress'])


def _default_options():
    return {
        'include_theoretical_framework': True,
        'include_conceptual_model': True,
        'include_tccm': True,
        'include_future_research': True,
        'include_sensitivity': True,
    }


def _get_options(stage):
    defaults = _default_options()
    raw = stage.get('options', {}) if isinstance(stage.get('options', {}), dict) else {}
    out = dict(defaults)
    for key in defaults:
        if key in raw:
            out[key] = bool(raw.get(key))
    return out


def _parse_options_from_post(post_data):
    parsed = {
        'include_theoretical_framework': bool(post_data.get('include_theoretical_framework')),
        'include_conceptual_model': bool(post_data.get('include_conceptual_model')),
        'include_tccm': bool(post_data.get('include_tccm')),
        'include_future_research': bool(post_data.get('include_future_research')),
        'include_sensitivity': bool(post_data.get('include_sensitivity')),
    }
    # Dependency rule: conceptual model requires theoretical framework.
    if parsed['include_conceptual_model'] and not parsed['include_theoretical_framework']:
        parsed['include_theoretical_framework'] = True
    return parsed


def _active_section_keys(stage):
    options = _get_options(stage)
    keys = [x['key'] for x in SECTION_MAP]
    if not options.get('include_theoretical_framework', True):
        keys = [k for k in keys if k not in THEORY_OPTION_KEYS]
    if not options.get('include_tccm', True):
        keys = [k for k in keys if k not in TCCM_OPTION_KEYS]
    if not options.get('include_future_research', True):
        keys = [k for k in keys if k != FUTURE_RESEARCH_KEY]
    return keys


def _apply_options_to_sections(stage):
    sections = stage.get('sections', {}) if isinstance(stage.get('sections', {}), dict) else {}
    options = _get_options(stage)
    if options.get('include_conceptual_model', True) and not options.get('include_theoretical_framework', True):
        options['include_theoretical_framework'] = True
        stage['options'] = options
    for key in THEORY_OPTION_KEYS:
        if key in sections:
            sec = sections[key]
            if not options.get('include_theoretical_framework', True):
                if sec.get('status') in {'pending', 'skipped'}:
                    sec['status'] = 'skipped'
            else:
                if sec.get('status') == 'skipped':
                    sec['status'] = 'pending'
    for tccm_key in TCCM_OPTION_KEYS:
        if tccm_key not in sections:
            continue
        sec = sections[tccm_key]
        if not options.get('include_tccm', True):
            if sec.get('status') in {'pending', 'skipped'}:
                sec['status'] = 'skipped'
        else:
            if sec.get('status') == 'skipped':
                sec['status'] = 'pending'
    future_key = FUTURE_RESEARCH_KEY
    if future_key in sections:
        sec = sections[future_key]
        if not options.get('include_future_research', True):
            if sec.get('status') in {'pending', 'skipped'}:
                sec['status'] = 'skipped'
        else:
            if sec.get('status') == 'skipped':
                sec['status'] = 'pending'


def _active_toc(stage):
    keys = set(_active_section_keys(stage))
    return [item['name'] for item in SECTION_MAP if item['key'] in keys]
