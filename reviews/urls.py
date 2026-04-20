from django.urls import path

from .views import (
    FullTextRetrievalMonitorView,
    FullTextRetrievalStatusView,
    FullTextUploadWindowView,
    PollScreeningBatchView,
    RISUploadView,
    ReviewCreateView,
    ReviewDetailView,
    ReviewFormalizationConfirmView,
    ScreeningConflictView,
    ScreeningDashboardView,
    ScreeningDecisionReviewView,
    ScreeningExportView,
    ScreeningStatusView,
    SearchStrategyView,
    StartScreeningBatchView,
    PollScreeningBatchApiView,
)
from .views_mineru import (
    MinerUMonitorView,
    MinerUStatusView,
)
from .views_fulltext_screening import (
    FullTextFinalDecisionView,
    FullTextScreeningMonitorView,
    FullTextScreeningStatusView,
)
from .views_deepseek_summary import (
    DeepSeekSummeryMonitorView,
    DeepSeekSummeryStatusView,
)
from .views_scaffold import (
    ScaffoldEditorView,
)
from .views_theme_synthesis import (
    ThemeSynthesisMonitorView,
    ThemeSynthesisStatusView,
)
from .views_theory_anchoring import (
    TheoryAnchoringMonitorView,
    TheoryAnchoringStatusView,
)
from .views_dialectical import (
    DialecticalMonitorView,
    DialecticalStatusView,
)
from .views_conceptual_model import (
    ConceptualModelMonitorView,
    ConceptualModelStatusView,
)
from .views_tccm import (
    TCCMMonitorView,
    TCCMStatusView,
)
from .views_ghostwriter import (
    GhostwriterMonitorView,
    GhostwriterStatusView,
)
from .views_title_screening import (
    TitleMissingAbstractsStatusView,
    TitleMissingAbstractsView,
    TitleScreeningStatusView,
    TitleScreeningView,
)
from .views_visual_assets import (
    VisualAssetEmbedView,
    VisualAssetsGalleryView,
    VisualAssetsMonitorView,
    VisualAssetsStatusView,
)
from .views_batch_debug import (
    ElsevierPDFDebugPageView,
    ElsevierPDFDebugStartView,
    ElsevierPDFDebugStatusView,
    ElsevierPDFDebugStopView,
    ScreeningBatchDebugForcePollView,
    ScreeningBatchDebugPageView,
    ScreeningBatchDebugStartView,
    ScreeningBatchDebugStatusView,
)

app_name = 'reviews'

urlpatterns = [
    path('', ReviewCreateView.as_view(), name='review-create'),
    path('reviews/<int:pk>/confirm/', ReviewFormalizationConfirmView.as_view(), name='review-confirm'),
    path('reviews/<int:pk>/search-strategy/', SearchStrategyView.as_view(), name='search-strategy'),
    path('reviews/<int:pk>/title-screening/', TitleScreeningView.as_view(), name='title-screening'),
    path('reviews/<int:pk>/title-screening/status/', TitleScreeningStatusView.as_view(), name='title-screening-status'),
    path('reviews/<int:pk>/title-screening/missing-abstracts/', TitleMissingAbstractsView.as_view(), name='title-missing-abstracts'),
    path('reviews/<int:pk>/title-screening/missing-abstracts/status/', TitleMissingAbstractsStatusView.as_view(), name='title-missing-abstracts-status'),
    path('reviews/<int:pk>/ris-upload/', RISUploadView.as_view(), name='ris-upload'),
    path('reviews/<int:pk>/screening/', ScreeningDashboardView.as_view(), name='screening-dashboard'),
    path('reviews/<int:pk>/screening/start/', StartScreeningBatchView.as_view(), name='screening-start'),
    path('reviews/<int:pk>/screening/poll/', PollScreeningBatchView.as_view(), name='screening-poll'),
    path('reviews/<int:pk>/screening/poll-api/', PollScreeningBatchApiView.as_view(), name='screening-poll-api'),
    path('reviews/<int:pk>/screening/status/', ScreeningStatusView.as_view(), name='screening-status'),
    path('reviews/<int:pk>/screening/conflicts/', ScreeningConflictView.as_view(), name='screening-conflicts'),
    path('reviews/<int:pk>/screening/decisions/', ScreeningDecisionReviewView.as_view(), name='screening-decisions'),
    path('reviews/<int:pk>/screening/export/', ScreeningExportView.as_view(), name='screening-export'),
    path('reviews/<int:pk>/fulltext/upload-window/', FullTextUploadWindowView.as_view(), name='fulltext-upload-window'),
    path('reviews/<int:pk>/fulltext/retrieval-monitor/', FullTextRetrievalMonitorView.as_view(), name='fulltext-retrieval-monitor'),
    path('reviews/<int:pk>/fulltext/retrieval-status/', FullTextRetrievalStatusView.as_view(), name='fulltext-retrieval-status'),
    path('reviews/<int:pk>/mineru/monitor/', MinerUMonitorView.as_view(), name='mineru-monitor'),
    path('reviews/<int:pk>/mineru/status/', MinerUStatusView.as_view(), name='mineru-status'),
    path('reviews/<int:pk>/fulltext/screening-monitor/', FullTextScreeningMonitorView.as_view(), name='fulltext-screening-monitor'),
    path('reviews/<int:pk>/fulltext/screening-status/', FullTextScreeningStatusView.as_view(), name='fulltext-screening-status'),
    path('reviews/<int:pk>/fulltext/final-decisions/', FullTextFinalDecisionView.as_view(), name='fulltext-final-decisions'),
    path('reviews/<int:pk>/deepseek-summery/monitor/', DeepSeekSummeryMonitorView.as_view(), name='deepseek-summery-monitor'),
    path('reviews/<int:pk>/deepseek-summery/status/', DeepSeekSummeryStatusView.as_view(), name='deepseek-summery-status'),
    path('reviews/<int:pk>/theme-synthesis/monitor/', ThemeSynthesisMonitorView.as_view(), name='theme-synthesis-monitor'),
    path('reviews/<int:pk>/theme-synthesis/status/', ThemeSynthesisStatusView.as_view(), name='theme-synthesis-status'),
    path('reviews/<int:pk>/theory-anchoring/monitor/', TheoryAnchoringMonitorView.as_view(), name='theory-anchoring-monitor'),
    path('reviews/<int:pk>/theory-anchoring/status/', TheoryAnchoringStatusView.as_view(), name='theory-anchoring-status'),
    path('reviews/<int:pk>/dialectical/monitor/', DialecticalMonitorView.as_view(), name='dialectical-monitor'),
    path('reviews/<int:pk>/dialectical/status/', DialecticalStatusView.as_view(), name='dialectical-status'),
    path('reviews/<int:pk>/conceptual-model/monitor/', ConceptualModelMonitorView.as_view(), name='conceptual-model-monitor'),
    path('reviews/<int:pk>/conceptual-model/status/', ConceptualModelStatusView.as_view(), name='conceptual-model-status'),
    path('reviews/<int:pk>/tccm/monitor/', TCCMMonitorView.as_view(), name='tccm-monitor'),
    path('reviews/<int:pk>/tccm/status/', TCCMStatusView.as_view(), name='tccm-status'),
    path('reviews/<int:pk>/ghostwriter/monitor/', GhostwriterMonitorView.as_view(), name='ghostwriter-monitor'),
    path('reviews/<int:pk>/ghostwriter/status/', GhostwriterStatusView.as_view(), name='ghostwriter-status'),
    path('reviews/<int:pk>/visual-assets/monitor/', VisualAssetsMonitorView.as_view(), name='visual-assets-monitor'),
    path('reviews/<int:pk>/visual-assets/status/', VisualAssetsStatusView.as_view(), name='visual-assets-status'),
    path('reviews/<int:pk>/visual-assets/gallery/', VisualAssetsGalleryView.as_view(), name='visual-assets-gallery'),
    path('reviews/<int:pk>/visual-assets/embed/<str:filename>/', VisualAssetEmbedView.as_view(), name='visual-assets-embed'),
    path('reviews/<int:pk>/fulltext/debug-elsevier/', ElsevierPDFDebugPageView.as_view(), name='elsevier-pdf-debug'),
    path('reviews/<int:pk>/fulltext/debug-elsevier/start/', ElsevierPDFDebugStartView.as_view(), name='elsevier-pdf-debug-start'),
    path('reviews/<int:pk>/fulltext/debug-elsevier/stop/', ElsevierPDFDebugStopView.as_view(), name='elsevier-pdf-debug-stop'),
    path('reviews/<int:pk>/fulltext/debug-elsevier/status/', ElsevierPDFDebugStatusView.as_view(), name='elsevier-pdf-debug-status'),
    path('reviews/<int:pk>/screening/debug-batch/', ScreeningBatchDebugPageView.as_view(), name='screening-batch-debug'),
    path('reviews/<int:pk>/screening/debug-batch/start/', ScreeningBatchDebugStartView.as_view(), name='screening-batch-debug-start'),
    path('reviews/<int:pk>/screening/debug-batch/status/', ScreeningBatchDebugStatusView.as_view(), name='screening-batch-debug-status'),
    path('reviews/<int:pk>/screening/debug-batch/force-poll/', ScreeningBatchDebugForcePollView.as_view(), name='screening-batch-debug-force-poll'),
    path('reviews/<int:pk>/scaffold/', ScaffoldEditorView.as_view(), name='scaffold-editor'),
    path('reviews/<int:pk>/', ReviewDetailView.as_view(), name='review-detail'),
]
