from pathlib import Path

from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.decorators.clickjacking import xframe_options_exempt
from django.utils.decorators import method_decorator

from .models import Review
from .services.visual_assets_service import VisualAssetsService, generate_visual_assets


class VisualAssetsMonitorView(View):
    template_name = 'reviews/visual_assets_monitor.html'

    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        svc = VisualAssetsService(review_id=review.id)
        stage = _get_stage(review)
        files = svc.list_assets()
        return render(
            request,
            self.template_name,
            {
                'review': review,
                'stage': stage,
                'files': files,
            },
        )

    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        action = (request.POST.get('action') or '').strip().lower()
        bundle = 'all'
        if action == 'generate_core':
            bundle = 'core'
        elif action == 'generate_evidence':
            bundle = 'evidence'
        elif action == 'generate_admin':
            bundle = 'admin'
        elif action == 'generate_all':
            bundle = 'all'
        else:
            messages.error(request, 'Invalid action for visual asset generation.')
            return redirect('reviews:visual-assets-monitor', pk=review.pk)

        result = generate_visual_assets(review_id=review.pk, bundle=bundle)
        messages.success(request, f"Generated {result.get('generated') and len(result.get('generated')) or 0} assets for bundle: {bundle}.")
        return redirect('reviews:visual-assets-monitor', pk=review.pk)


class VisualAssetsStatusView(View):
    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        svc = VisualAssetsService(review_id=review.id)
        stage = _get_stage(review)
        stage['files'] = svc.list_assets()
        return JsonResponse(stage)


class VisualAssetsGalleryView(View):
    template_name = 'reviews/visual_assets_gallery.html'

    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        svc = VisualAssetsService(review_id=review.id)
        files = svc.list_assets()

        html_files = [f for f in files if f.get('name', '').lower().endswith('.html')]

        table_files = []
        figure_files = []
        for f in sorted(html_files, key=lambda x: x.get('name', '')):
            item = {
                'name': f.get('name', ''),
                'url': f.get('url', ''),
                'embed_url': reverse('reviews:visual-assets-embed', kwargs={'pk': review.pk, 'filename': f.get('name', '')}),
            }
            if item['name'].startswith('table_'):
                table_files.append(item)
            elif item['name'].startswith('figure_'):
                figure_files.append(item)

        selected_type = request.GET.get('type', '').strip().lower()
        selected_asset = request.GET.get('asset', '').strip()

        if selected_type not in {'table', 'figure'}:
            if figure_files:
                selected_type = 'figure'
                selected_asset = figure_files[0]['embed_url']
            elif table_files:
                selected_type = 'table'
                selected_asset = table_files[0]['embed_url']
            else:
                selected_type = ''
                selected_asset = ''

        if not selected_asset:
            if selected_type == 'table' and table_files:
                selected_asset = table_files[0]['embed_url']
            elif selected_type == 'figure' and figure_files:
                selected_asset = figure_files[0]['embed_url']

        selected_name = ''
        source_list = table_files if selected_type == 'table' else figure_files
        for item in source_list:
            if item['embed_url'] == selected_asset:
                selected_name = item['name']
                break

        return render(
            request,
            self.template_name,
            {
                'review': review,
                'table_files': table_files,
                'figure_files': figure_files,
                'selected_type': selected_type,
                'selected_asset': selected_asset,
                'selected_name': selected_name,
            },
        )


@method_decorator(xframe_options_exempt, name='dispatch')
class VisualAssetEmbedView(View):
    def get(self, request, pk, filename):
        review = get_object_or_404(Review, pk=pk)
        if not filename.lower().endswith('.html'):
            raise Http404('Only html visual assets can be embedded.')

        svc = VisualAssetsService(review_id=review.id)
        safe_name = Path(filename).name
        target = svc.assets_dir / safe_name
        if not target.exists() or not target.is_file():
            raise Http404('Asset not found.')

        return HttpResponse(target.read_text(encoding='utf-8', errors='ignore'), content_type='text/html')


def _get_stage(review):
    stage_progress = review.stage_progress if isinstance(review.stage_progress, dict) else {}
    stage = stage_progress.get('phase_22_visual_assets', {}) if isinstance(stage_progress.get('phase_22_visual_assets', {}), dict) else {}
    stage.setdefault('status', 'idle')
    stage.setdefault('logs', [])
    return stage
