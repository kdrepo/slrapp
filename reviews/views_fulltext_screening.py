import threading
import traceback
from urllib.parse import urlencode

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from .models import Paper, Review
from .services.fulltext_screening_service import run_full_text_screening_for_review


class FullTextScreeningMonitorView(View):
    template_name = 'reviews/fulltext_screening_monitor.html'

    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        stage = _get_stage(review)
        completed_results = _get_completed_results(review)
        return render(request, self.template_name, {'review': review, 'stage': stage, 'completed_results': completed_results})

    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        stage = _get_stage(review)
        action = (request.POST.get('action') or '').strip().lower()

        if action == 'stop':
            if stage.get('status') not in {'running', 'queued', 'stopping'}:
                messages.warning(request, 'No active full-text screening run is in progress.')
                return redirect('reviews:fulltext-screening-monitor', pk=review.pk)
            stage['status'] = 'stopping'
            stage['stop_requested'] = True
            stage['stop_requested_at'] = timezone.now().isoformat()
            _set_stage(review, stage)
            messages.success(request, 'Stop requested.')
            return redirect('reviews:fulltext-screening-monitor', pk=review.pk)

        current_status = stage.get('status')
        if current_status in {'running', 'queued'}:
            messages.warning(request, 'A full-text screening job is already running.')
            return redirect('reviews:fulltext-screening-monitor', pk=review.pk)

        if current_status == 'stopping':
            stage['status'] = 'stopped'
            stage['completed_at'] = stage.get('completed_at') or timezone.now().isoformat()
            _set_stage(review, stage)

        allowed = {'start_screening', 'retry_screening', 'run_screening', 'retry_failed'}
        if action not in allowed:
            messages.error(request, 'Invalid action.')
            return redirect('reviews:fulltext-screening-monitor', pk=review.pk)

        retry_failed_only = action in {'retry_screening', 'retry_failed'}

        initial = {
            'status': 'running',
            'run_mode': 'deepseek',
            'started_at': timezone.now().isoformat(),
            'targeted': 0,
            'processed': 0,
            'done': 0,
            'failed': 0,
            'chunk_size': 5,
            'provider': 'deepseek',
            'stop_requested': False,
            'error_code': '',
            'error_message': '',
            'logs': [],
            'retry_failed_only': retry_failed_only,
        }
        _set_stage(review, initial)

        worker = threading.Thread(target=_run_async, args=(review.pk, retry_failed_only), daemon=True)
        worker.start()

        if action in {'retry_screening', 'retry_failed'}:
            messages.success(request, 'Retry screening failed started in chunks of 5 (DeepSeek).')
        else:
            messages.success(request, 'Full-text screening started in chunks of 5 (DeepSeek).')
        return redirect('reviews:fulltext-screening-monitor', pk=review.pk)


class FullTextScreeningStatusView(View):
    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        payload = dict(_get_stage(review))
        payload['completed_results'] = _get_completed_results(review)
        return JsonResponse(payload)


class FullTextFinalDecisionView(View):
    template_name = 'reviews/fulltext_final_decisions.html'

    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        selected = (request.GET.get('full_text_decision') or 'all').strip().lower()

        papers = review.papers.order_by('id')
        papers = self._apply_filter(papers, selected)

        decision_options = [('all', 'All decisions')] + list(Paper.FullTextDecision.choices)

        return render(
            request,
            self.template_name,
            {
                'review': review,
                'papers': papers,
                'decision_options': decision_options,
                'selected_decision': selected,
            },
        )

    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        selected = (request.POST.get('current_full_text_decision') or 'all').strip().lower()
        action = (request.POST.get('action') or 'single').strip().lower()

        if action == 'bulk':
            papers = self._apply_filter(review.papers.order_by('id'), selected)
            updated = 0
            for paper in papers:
                choice = (request.POST.get(f'decision_{paper.id}') or '').strip().lower()
                if not choice:
                    continue
                if choice not in {c[0] for c in Paper.FullTextDecision.choices}:
                    continue
                self._apply_final_decision(paper, choice)
                updated += 1
            messages.success(request, f'Bulk update complete. Updated: {updated} papers.')
            return redirect(self._redirect_url(review.pk, selected))

        paper = get_object_or_404(Paper, pk=request.POST.get('paper_id'), review=review)
        choice = (request.POST.get('decision') or request.POST.get(f'decision_{paper.id}') or '').strip().lower()
        if choice not in {c[0] for c in Paper.FullTextDecision.choices}:
            messages.error(request, 'Invalid final decision value.')
            return redirect(self._redirect_url(review.pk, selected))

        self._apply_final_decision(paper, choice)
        messages.success(request, f'Updated paper {paper.id} to {choice}.')
        return redirect(self._redirect_url(review.pk, selected))

    def _apply_filter(self, papers, selected):
        valid = {c[0] for c in Paper.FullTextDecision.choices}
        if selected in valid:
            return papers.filter(full_text_decision=selected)
        return papers

    def _apply_final_decision(self, paper, decision):
        paper.full_text_decision = decision
        paper.full_text_screening_status = 'manual_override'
        paper.full_text_screening_provider = 'manual'
        paper.full_text_screened_at = timezone.now()

        if decision == Paper.FullTextDecision.INCLUDED:
            paper.ta_decision = Paper.TADecision.INCLUDED
        elif decision == Paper.FullTextDecision.EXCLUDED:
            paper.ta_decision = Paper.TADecision.EXCLUDED
        elif decision == Paper.FullTextDecision.MANUAL_FLAG:
            paper.ta_decision = Paper.TADecision.MANUAL_FLAG

        paper.save(update_fields=['full_text_decision', 'full_text_screening_status', 'full_text_screening_provider', 'full_text_screened_at', 'ta_decision'])

    def _redirect_url(self, review_id, selected):
        query = urlencode({'full_text_decision': selected or 'all'})
        return f"{reverse('reviews:fulltext-final-decisions', kwargs={'pk': review_id})}?{query}"


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
            stage['chunk_size'] = int(event.get('chunk_size', stage.get('chunk_size', 5)) or 5)
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
                'decision': event.get('decision') or '',
                'error_code': event.get('error_code') or '',
                'error_message': event.get('error_message') or '',
            })
            stage['logs'] = logs[:500]

        _set_stage(review, stage)

    try:
        summary = run_full_text_screening_for_review(
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
        if summary.get('chunk_size'):
            stage['chunk_size'] = int(summary.get('chunk_size'))
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
    return progress.get('phase_15_fulltext_screening', {})


def _set_stage(review, stage):
    progress = review.stage_progress or {}
    progress['phase_15_fulltext_screening'] = stage
    review.stage_progress = progress
    review.save(update_fields=['stage_progress'])


def _get_completed_results(review):
    rows = review.papers.exclude(full_text_decision=Paper.FullTextDecision.NOT_SCREENED).order_by('id').values(
        'id',
        'title',
        'full_text_decision',
        'full_text_screening_provider',
        'full_text_screening_model',
        'full_text_screening_status',
        'full_text_exclusion_reason',
        'full_text_rq_tags',
        'full_text_rq1_findings_summary',
        'full_text_rq2_findings_summary',
        'full_text_notes',
        'full_text_screened_at',
    )
    return list(rows)
