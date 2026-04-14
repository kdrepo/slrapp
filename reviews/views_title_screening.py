import threading
import traceback
from io import BytesIO
from urllib.parse import urlencode

from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.db.models import Q
from django.views import View

from .models import Paper, Review
from .services.title_screening_service import run_title_screening_for_review
from .services.scopus_metadata_service import enrich_missing_abstracts_from_scopus, probe_scopus_metadata_for_paper


class TitleScreeningView(View):
    template_name = 'reviews/title_screening.html'

    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        selected_decision = (request.GET.get('title_decision') or 'all').strip().lower()

        papers = review.papers.order_by('id')
        papers = self._apply_decision_filter(papers, selected_decision)

        decision_options = [('all', 'All decisions')] + list(Paper.TitleScreeningDecision.choices)

        return render(
            request,
            self.template_name,
            {
                'review': review,
                'stage': _get_stage(review),
                'papers': papers,
                'decision_options': decision_options,
                'title_decision_choices': Paper.TitleScreeningDecision.choices,
                'selected_decision': selected_decision,
                'default_override_decision': self._default_override_decision(selected_decision),
            },
        )

    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        selected_decision = (request.POST.get('current_title_decision') or 'all').strip().lower()
        action = (request.POST.get('action') or 'single').strip().lower()
        stage = _get_stage(review)

        if action == 'export_excel':
            return self._export_excel(request, review, selected_decision)

        if action == 'stop':
            if stage.get('status') not in {'running', 'queued', 'stopping'}:
                messages.warning(request, 'No active title-screening run is in progress.')
                return self._redirect_with_filters(review.pk, selected_decision)
            stage['status'] = 'stopping'
            stage['stop_requested'] = True
            stage['stop_requested_at'] = timezone.now().isoformat()
            _set_stage(review, stage)
            messages.success(request, 'Stop requested for title screening.')
            return self._redirect_with_filters(review.pk, selected_decision)

        if action in {'run', 'retry_failed'}:
            if stage.get('status') in {'running', 'queued', 'stopping'}:
                messages.warning(request, 'Title screening is already running.')
                return self._redirect_with_filters(review.pk, selected_decision)

            retry_failed_only = action == 'retry_failed'
            initial = {
                'status': 'running',
                'started_at': timezone.now().isoformat(),
                'targeted': 0,
                'processed': 0,
                'done': 0,
                'failed': 0,
                'pending': 0,
                'chunk_size': 25,
                'stop_requested': False,
                'error_code': '',
                'error_message': '',
                'logs': [],
                'retry_failed_only': retry_failed_only,
            }
            _set_stage(review, initial)

            worker = threading.Thread(target=_run_async, args=(review.pk, retry_failed_only), daemon=True)
            worker.start()

            if retry_failed_only:
                messages.success(request, 'Title screening retry for failed papers started.')
            else:
                messages.success(request, 'Title screening started.')
            return self._redirect_with_filters(review.pk, selected_decision)

        if action == 'bulk':
            return self._handle_bulk_update(request, review, selected_decision)

        paper = get_object_or_404(Paper, pk=request.POST.get('paper_id'), review=review)
        decision = (request.POST.get('decision') or request.POST.get(f'decision_{paper.id}') or '').strip().lower()
        note = (request.POST.get('note') or request.POST.get(f'note_{paper.id}') or '').strip()

        allowed = {choice[0] for choice in Paper.TitleScreeningDecision.choices} | {'', 'empty'}
        if decision not in allowed:
            messages.error(request, 'Invalid title-screening decision value.')
            return self._redirect_with_filters(review.pk, selected_decision)

        if decision in {'', 'empty'}:
            paper.title_screening_decision = Paper.TitleScreeningDecision.NOT_PROCESSED
        else:
            paper.title_screening_decision = decision
        if note:
            paper.title_screening_reason = note
        paper.title_screening_status = 'manual'
        paper.title_screening_error = ''
        paper.save(update_fields=['title_screening_decision', 'title_screening_reason', 'title_screening_status', 'title_screening_error'])
        messages.success(request, f'Updated paper {paper.id} title decision to {paper.title_screening_decision}.')
        return self._redirect_with_filters(review.pk, selected_decision)

    def _handle_bulk_update(self, request, review, selected_decision):
        papers = review.papers.order_by('id')
        papers = self._apply_decision_filter(papers, selected_decision)
        papers = list(papers.only('id', 'title_screening_reason'))

        allowed = {choice[0] for choice in Paper.TitleScreeningDecision.choices} | {'', 'empty'}
        updated = 0
        skipped = 0

        for paper in papers:
            decision = (request.POST.get(f'decision_{paper.id}') or '').strip().lower()
            note = (request.POST.get(f'note_{paper.id}') or '').strip()

            if decision == '':
                skipped += 1
                continue

            if decision not in allowed:
                messages.error(request, f'Invalid title decision "{decision}" for paper {paper.id}.')
                return self._redirect_with_filters(review.pk, selected_decision)

            if decision == 'empty':
                paper.title_screening_decision = Paper.TitleScreeningDecision.NOT_PROCESSED
            else:
                paper.title_screening_decision = decision

            if note:
                paper.title_screening_reason = note
            paper.title_screening_status = 'manual'
            paper.title_screening_error = ''
            paper.save(update_fields=['title_screening_decision', 'title_screening_reason', 'title_screening_status', 'title_screening_error'])
            updated += 1

        messages.success(request, f'Bulk title decision update complete. Updated: {updated}, skipped (blank): {skipped}.')
        return self._redirect_with_filters(review.pk, selected_decision)

    def _export_excel(self, request, review, selected_decision):
        papers = review.papers.order_by('id')
        papers = self._apply_decision_filter(papers, selected_decision)
        try:
            from openpyxl import Workbook
        except Exception:
            messages.error(request, 'Excel export requires openpyxl. Please install it in the active environment.')
            return self._redirect_with_filters(review.pk, selected_decision)

        wb = Workbook()
        ws = wb.active
        ws.title = 'Title Screening Export'
        ws.append(['Title', 'Authors', 'Citation Count', 'Journal'])

        for paper in papers:
            ws.append([
                paper.title or '',
                paper.authors or '',
                paper.citation_count if paper.citation_count is not None else '',
                paper.journal or '',
            ])

        output = BytesIO()
        wb.save(output)
        output.seek(0)

        response = HttpResponse(
            output.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = (
            f'attachment; filename=review_{review.pk}_title_screening_{selected_decision or "all"}.xlsx'
        )
        return response

    def _apply_decision_filter(self, papers, selected_decision):
        valid = {choice[0] for choice in Paper.TitleScreeningDecision.choices}
        if selected_decision == 'all':
            return papers
        if selected_decision in valid:
            return papers.filter(title_screening_decision=selected_decision)
        return papers

    def _default_override_decision(self, selected_decision):
        valid = {choice[0] for choice in Paper.TitleScreeningDecision.choices}
        if selected_decision in valid:
            return selected_decision
        return ''

    def _redirect_with_filters(self, review_id, selected_decision):
        query = urlencode({'title_decision': selected_decision or 'all'})
        return redirect(f"{reverse('reviews:title-screening', kwargs={'pk': review_id})}?{query}")


class TitleMissingAbstractsView(View):
    template_name = 'reviews/title_missing_abstracts.html'

    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        selected_decisions = self._selected_from_request(request)
        papers = self._missing_abstract_papers(review, selected_decisions)
        stage = _get_missing_abstracts_stage(review)
        probe_row = None
        if papers:
            probe = probe_scopus_metadata_for_paper(papers[0])
            probe_row = {
                'paper_id': papers[0].id,
                'title': papers[0].title,
                'ok': probe.get('ok', False),
                'source': probe.get('source') or '',
                'status_code': probe.get('status_code'),
                'error': probe.get('error') or '',
            }

        return render(
            request,
            self.template_name,
            {
                'review': review,
                'decision_rows': self._decision_rows(selected_decisions),
                'papers': papers,
                'selected_decisions': selected_decisions,
                'stage': stage,
                'last_summary': (review.stage_progress or {}).get('phase_6_missing_abstracts_last_run') or {},
                'probe_row': probe_row,
            },
        )

    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        selected_decisions = self._selected_from_request(request)
        action = (request.POST.get('action') or 'start').strip().lower()
        query = urlencode([('title_screening_decisions', d) for d in selected_decisions])
        stage = _get_missing_abstracts_stage(review)

        if action == 'stop':
            if stage.get('status') not in {'running', 'queued', 'stopping'}:
                messages.warning(request, 'No active missing-abstract run is in progress.')
                return redirect(f"{reverse('reviews:title-missing-abstracts', kwargs={'pk': review.pk})}?{query}")
            stage['status'] = 'stopping'
            stage['stop_requested'] = True
            stage['stop_requested_at'] = timezone.now().isoformat()
            _set_missing_abstracts_stage(review, stage)
            messages.success(request, 'Stop requested for missing-abstract recovery.')
            return redirect(f"{reverse('reviews:title-missing-abstracts', kwargs={'pk': review.pk})}?{query}")

        if stage.get('status') in {'running', 'queued', 'stopping'}:
            messages.warning(request, 'Missing-abstract recovery is already running.')
            return redirect(f"{reverse('reviews:title-missing-abstracts', kwargs={'pk': review.pk})}?{query}")

        initial = {
            'status': 'running',
            'started_at': timezone.now().isoformat(),
            'selected_decisions': selected_decisions,
            'targeted': 0,
            'processed': 0,
            'done': 0,
            'failed': 0,
            'pending': 0,
            'updated': 0,
            'abstract_filled': 0,
            'stop_requested': False,
            'error_code': '',
            'error_message': '',
            'logs': [],
        }
        _set_missing_abstracts_stage(review, initial)

        worker = threading.Thread(target=_run_missing_abstracts_async, args=(review.pk, selected_decisions), daemon=True)
        worker.start()
        messages.success(request, 'Missing-abstract recovery started. Live status is shown below.')

        return redirect(f"{reverse('reviews:title-missing-abstracts', kwargs={'pk': review.pk})}?{query}")

    def _selected_from_request(self, request):
        allowed = {choice[0] for choice in Paper.TitleScreeningDecision.choices}
        selected = []
        for value in request.GET.getlist('title_screening_decisions') + request.POST.getlist('title_screening_decisions'):
            item = str(value or '').strip().lower()
            if item in allowed and item not in selected:
                selected.append(item)
        if not selected:
            selected = [
                Paper.TitleScreeningDecision.INCLUDED,
                Paper.TitleScreeningDecision.EXCLUDED,
                Paper.TitleScreeningDecision.UNCERTAIN,
                Paper.TitleScreeningDecision.MANUAL_TITLES,
                Paper.TitleScreeningDecision.NOT_PROCESSED,
            ]
        return selected

    def _missing_abstract_papers(self, review, selected_decisions):
        return list(
            review.papers.filter(title_screening_decision__in=selected_decisions)
            .filter(Q(abstract__isnull=True) | Q(abstract=''))
            .order_by('id')
        )

    def _decision_rows(self, selected_decisions):
        rows = []
        for value, label in Paper.TitleScreeningDecision.choices:
            rows.append(
                {
                    'value': value,
                    'label': label,
                    'selected': value in selected_decisions,
                }
            )
        return rows


class TitleMissingAbstractsStatusView(View):
    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        return JsonResponse(_get_missing_abstracts_stage(review))


class TitleScreeningStatusView(View):
    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        payload = dict(_get_stage(review))
        payload['results'] = list(
            review.papers.order_by('id').values(
                'id',
                'title',
                'title_screening_decision',
                'title_screening_confidence',
                'title_screening_reason',
                'title_screening_status',
                'title_screening_error',
            )
        )
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
            stage['chunk_size'] = int(event.get('chunk_size', stage.get('chunk_size', 25)) or 25)
            stage['pending'] = int(event.get('targeted', 0) or 0)
        elif event_name in {'done', 'failed'}:
            stage['processed'] = int(stage.get('processed', 0)) + 1
            if event_name == 'done':
                stage['done'] = int(stage.get('done', 0)) + 1
            else:
                stage['failed'] = int(stage.get('failed', 0)) + 1
            stage['pending'] = max(int(stage.get('targeted', 0)) - int(stage.get('processed', 0)), 0)

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
        summary = run_title_screening_for_review(
            review_id=review_id,
            retry_failed_only=retry_failed_only,
            progress_callback=_progress,
            stop_check=_should_stop,
        )

        review = Review.objects.get(pk=review_id)
        stage = _get_stage(review)
        stage['status'] = 'stopped' if summary.get('stopped') else 'completed'
        stage['completed_at'] = timezone.now().isoformat()
        stage['targeted'] = int(summary.get('targeted', stage.get('targeted', 0)))
        stage['processed'] = int(summary.get('processed', stage.get('processed', 0)))
        stage['done'] = int(summary.get('done', stage.get('done', 0)))
        stage['failed'] = int(summary.get('failed', stage.get('failed', 0)))
        stage['pending'] = max(stage['targeted'] - stage['processed'], 0)
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



def _run_missing_abstracts_async(review_id, selected_decisions):
    def _should_stop():
        review = Review.objects.get(pk=review_id)
        stage = _get_missing_abstracts_stage(review)
        return bool(stage.get('stop_requested'))

    def _progress(event):
        review = Review.objects.get(pk=review_id)
        stage = _get_missing_abstracts_stage(review)
        event_name = event.get('event')

        if event_name == 'started':
            stage['targeted'] = int(event.get('targeted', 0) or 0)
            stage['pending'] = int(event.get('targeted', 0) or 0)
            stage['selected_decisions'] = list(event.get('selected_decisions') or stage.get('selected_decisions') or [])
        elif event_name in {'updated', 'no_change', 'failed'}:
            stage['processed'] = int(stage.get('processed', 0)) + 1
            if event_name == 'failed':
                stage['failed'] = int(stage.get('failed', 0)) + 1
            else:
                stage['done'] = int(stage.get('done', 0)) + 1
                if event_name == 'updated':
                    stage['updated'] = int(stage.get('updated', 0)) + 1
            stage['pending'] = max(int(stage.get('targeted', 0)) - int(stage.get('processed', 0)), 0)

        if event_name in {'processing', 'updated', 'no_change', 'failed', 'stopped'}:
            logs = list(stage.get('logs') or [])
            logs.insert(0, {
                'time': timezone.now().isoformat(),
                'event': event_name,
                'paper_id': event.get('paper_id'),
                'title': (event.get('title') or '')[:220],
                'status_code': event.get('status_code'),
                'source': event.get('source') or '',
                'message': event.get('message') or '',
            })
            stage['logs'] = logs[:500]

        _set_missing_abstracts_stage(review, stage)

    try:
        summary = enrich_missing_abstracts_from_scopus(
            review_id=review_id,
            title_screening_decisions=selected_decisions,
            progress_callback=_progress,
            stop_check=_should_stop,
        )

        review = Review.objects.get(pk=review_id)
        stage = _get_missing_abstracts_stage(review)
        stage['status'] = 'stopped' if summary.get('stopped') else 'completed'
        stage['completed_at'] = timezone.now().isoformat()
        stage['targeted'] = int(summary.get('targeted', stage.get('targeted', 0)))
        stage['processed'] = int(stage.get('processed', 0))
        stage['done'] = int(stage.get('done', 0))
        stage['failed'] = int(summary.get('failed', stage.get('failed', 0)))
        stage['updated'] = int(summary.get('updated', stage.get('updated', 0)))
        stage['abstract_filled'] = int(summary.get('abstract_filled', stage.get('abstract_filled', 0)))
        stage['pending'] = max(stage['targeted'] - stage['processed'], 0)
        _set_missing_abstracts_stage(review, stage)

        progress = review.stage_progress or {}
        progress['phase_6_missing_abstracts_last_run'] = summary
        review.stage_progress = progress
        review.save(update_fields=['stage_progress'])
    except Exception as exc:
        review = Review.objects.get(pk=review_id)
        stage = _get_missing_abstracts_stage(review)
        stage['status'] = 'error'
        stage['error_code'] = exc.__class__.__name__
        stage['error_message'] = str(exc)
        stage['error_traceback'] = traceback.format_exc()
        stage['completed_at'] = timezone.now().isoformat()
        _set_missing_abstracts_stage(review, stage)


def _get_missing_abstracts_stage(review):
    progress = review.stage_progress or {}
    return progress.get('phase_6_missing_abstracts', {})


def _set_missing_abstracts_stage(review, stage):
    progress = review.stage_progress or {}
    progress['phase_6_missing_abstracts'] = stage
    review.stage_progress = progress
    review.save(update_fields=['stage_progress'])

def _get_stage(review):
    progress = review.stage_progress or {}
    return progress.get('phase_6_title_screening', {})


def _set_stage(review, stage):
    progress = review.stage_progress or {}
    progress['phase_6_title_screening'] = stage
    review.stage_progress = progress
    review.save(update_fields=['stage_progress'])




