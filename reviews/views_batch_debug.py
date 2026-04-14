import logging
import threading

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views import View

from .models import Review
from .services.elsevier_pdf_debug import run_elsevier_pdf_debug
from .services.screening_service import get_screening_snapshot, poll_screening_batch, submit_screening_batch

_DEBUG_STAGE_KEY = 'phase_7_debug'
_ELSEVIER_DEBUG_STAGE_KEY = 'phase_12_elsevier_debug'
logger = logging.getLogger(__name__)


def _trace(message):
    line = f'[BatchDebugView] {message}'
    print(line)
    logger.info(line)


class ScreeningBatchDebugPageView(View):
    template_name = 'reviews/screening_batch_debug.html'

    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        _trace(f'GET debug page review_id={review.pk}')
        return render(request, self.template_name, {'review': review})


class ScreeningBatchDebugStartView(View):
    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        _trace(f'START requested review_id={review.pk}')
        try:
            result = submit_screening_batch(
                review_id=review.pk,
                max_papers=5,
                stage_key=_DEBUG_STAGE_KEY,
            )
            _trace(f'START result review_id={review.pk} result={result}')
            payload = {
                'ok': True,
                'step': 'submitted' if result.get('submitted') else 'no_eligible_papers',
                'message': 'Process started and batch submitted.' if result.get('submitted') else 'No eligible papers found for debug batch.',
                'result': result,
            }
        except Exception as exc:
            _trace(f'START failed review_id={review.pk} error={exc}')
            payload = {'ok': False, 'step': 'submit_failed', 'message': 'Batch submit failed.', 'error': str(exc)}
        return JsonResponse(payload)


class ScreeningBatchDebugStatusView(View):
    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        _trace(f'STATUS requested review_id={review.pk}')
        snapshot = get_screening_snapshot(review_id=review.pk, stage_key=_DEBUG_STAGE_KEY)
        _trace(f'STATUS snapshot review_id={review.pk} total={snapshot.get("total", 0)} decided={snapshot.get("decided", 0)}')
        return JsonResponse({'ok': True, 'snapshot': snapshot})


class ScreeningBatchDebugForcePollView(View):
    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        _trace(f'FORCE_POLL requested review_id={review.pk}')
        try:
            result = poll_screening_batch(review_id=review.pk, stage_key=_DEBUG_STAGE_KEY)
            _trace(f'FORCE_POLL result review_id={review.pk} result={result}')
            payload = {'ok': True, 'step': 'polled', 'message': 'Manual poll complete.', 'result': result}
        except Exception as exc:
            _trace(f'FORCE_POLL failed review_id={review.pk} error={exc}')
            payload = {'ok': False, 'step': 'poll_failed', 'message': 'Manual poll failed.', 'error': str(exc)}
        return JsonResponse(payload)


class ElsevierPDFDebugPageView(View):
    template_name = 'reviews/elsevier_pdf_debug.html'

    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        snapshot = _get_elsevier_snapshot(review)
        return render(request, self.template_name, {'review': review, 'stage': snapshot})


class ElsevierPDFDebugStartView(View):
    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        snapshot = _get_elsevier_snapshot(review)

        if snapshot.get('status') == 'running':
            return JsonResponse({'ok': False, 'error': 'Elsevier debug already running.'})

        _set_elsevier_snapshot(
            review,
            {
                'status': 'running',
                'started_at': timezone.now().isoformat(),
                'targeted': 0,
                'processed': 0,
                'downloaded': 0,
                'failed': 0,
                'logs': [],
                'stop_requested': False,
            },
        )

        thread = threading.Thread(target=_run_elsevier_debug_async, args=(review.pk,), daemon=True)
        thread.start()

        return JsonResponse({'ok': True, 'message': 'Elsevier PDF debug started.'})


class ElsevierPDFDebugStopView(View):
    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        snapshot = _get_elsevier_snapshot(review)

        if snapshot.get('status') != 'running':
            return JsonResponse({'ok': False, 'error': 'No running Elsevier debug job to stop.'})

        snapshot['stop_requested'] = True
        snapshot['status'] = 'stopping'
        _set_elsevier_snapshot(review, snapshot)
        print(f'[ElsevierPDFDebug] stop_requested | review_id={review.pk}')
        return JsonResponse({'ok': True, 'message': 'Stop requested. Finishing current request and halting.'})


class ElsevierPDFDebugStatusView(View):
    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        return JsonResponse({'ok': True, 'snapshot': _get_elsevier_snapshot(review)})


def _run_elsevier_debug_async(review_id):
    def should_stop():
        review = Review.objects.get(pk=review_id)
        stage = _get_elsevier_snapshot(review)
        return bool(stage.get('stop_requested', False))

    def progress(event):
        review = Review.objects.get(pk=review_id)
        stage = _get_elsevier_snapshot(review)
        logs = list(stage.get('logs') or [])

        event_name = event.get('event', '')
        if event_name == 'started':
            stage['targeted'] = int(event.get('targeted', 0) or 0)

        if event_name in {'downloaded', 'failed'}:
            stage['processed'] = int(stage.get('processed', 0)) + 1
            if event_name == 'downloaded':
                stage['downloaded'] = int(stage.get('downloaded', 0)) + 1
            else:
                stage['failed'] = int(stage.get('failed', 0)) + 1

        if event_name in {'processing', 'downloaded', 'failed', 'stopped', 'completed'}:
            logs.insert(
                0,
                {
                    'time': timezone.now().isoformat(),
                    'event': event_name,
                    'paper_id': event.get('paper_id'),
                    'status_code': event.get('status_code'),
                    'error_type': event.get('error_type'),
                    'title': (event.get('title') or '')[:160],
                    'message': event.get('message', ''),
                },
            )
            stage['logs'] = logs[:400]

        _set_elsevier_snapshot(review, stage)

    try:
        summary = run_elsevier_pdf_debug(
            review_id=review_id,
            progress_callback=progress,
            stop_check=should_stop,
        )
        review = Review.objects.get(pk=review_id)
        stage = _get_elsevier_snapshot(review)
        stage['status'] = 'stopped' if summary.get('stopped') else 'completed'
        stage['completed_at'] = timezone.now().isoformat()
        stage['targeted'] = int(summary.get('targeted', stage.get('targeted', 0)))
        stage['downloaded'] = int(summary.get('downloaded', stage.get('downloaded', 0)))
        stage['failed'] = int(summary.get('failed', stage.get('failed', 0)))
        stage['processed'] = stage['downloaded'] + stage['failed']
        _set_elsevier_snapshot(review, stage)
    except Exception as exc:
        review = Review.objects.get(pk=review_id)
        stage = _get_elsevier_snapshot(review)
        stage['status'] = 'error'
        stage['error'] = str(exc)
        stage['completed_at'] = timezone.now().isoformat()
        _set_elsevier_snapshot(review, stage)
        print(f'[ElsevierPDFDebug] fatal_error | {exc}')


def _get_elsevier_snapshot(review):
    stage_progress = review.stage_progress or {}
    return stage_progress.get(_ELSEVIER_DEBUG_STAGE_KEY, {})


def _set_elsevier_snapshot(review, payload):
    stage_progress = review.stage_progress or {}
    stage_progress[_ELSEVIER_DEBUG_STAGE_KEY] = payload
    review.stage_progress = stage_progress
    review.save(update_fields=['stage_progress'])
