from django.urls import path

from reviews.views_lit_review import (
    LitReviewCitationStatusView,
    LitReviewPerPaperExtractionMonitorView,
    LitReviewPerPaperExtractionStatusView,
    LitReviewSectionAssignmentMonitorView,
    LitReviewSectionAssignmentStatusView,
    LitReviewStage5WritingMonitorView,
    LitReviewStage5WritingStatusView,
    LitReviewStage5BStitchMonitorView,
    LitReviewStage5BStitchStatusView,
    LitReviewStage5CReferencesMonitorView,
    LitReviewStage5CReferencesStatusView,
    LitReviewMinerUMonitorView,
    LitReviewMinerUStatusView,
    LitReviewResolverStatusView,
    LitReviewStage2IntakeView,
    LitReviewStage1ApiCreateView,
    LitReviewStage1CreateView,
    LitReviewStage1DetailView,
)

app_name = 'lit_reviews'

urlpatterns = [
    path('', LitReviewStage1CreateView.as_view(), name='stage1-create'),
    path('reviews/<int:pk>/', LitReviewStage1DetailView.as_view(), name='stage1-detail'),
    path('reviews/<int:pk>/stage-2-intake/', LitReviewStage2IntakeView.as_view(), name='stage2-intake'),
    path('reviews/<int:pk>/stage-3-mineru/monitor/', LitReviewMinerUMonitorView.as_view(), name='stage3-mineru-monitor'),
    path('reviews/<int:pk>/stage-3-mineru/status/', LitReviewMinerUStatusView.as_view(), name='stage3-mineru-status'),
    path('reviews/<int:pk>/stage-4-extraction/monitor/', LitReviewPerPaperExtractionMonitorView.as_view(), name='stage4-extraction-monitor'),
    path('reviews/<int:pk>/stage-4-extraction/status/', LitReviewPerPaperExtractionStatusView.as_view(), name='stage4-extraction-status'),
    path('reviews/<int:pk>/stage-4b-assignment/monitor/', LitReviewSectionAssignmentMonitorView.as_view(), name='stage4b-assignment-monitor'),
    path('reviews/<int:pk>/stage-4b-assignment/status/', LitReviewSectionAssignmentStatusView.as_view(), name='stage4b-assignment-status'),
    path('reviews/<int:pk>/stage-5-writing/monitor/', LitReviewStage5WritingMonitorView.as_view(), name='stage5-writing-monitor'),
    path('reviews/<int:pk>/stage-5-writing/status/', LitReviewStage5WritingStatusView.as_view(), name='stage5-writing-status'),
    path('reviews/<int:pk>/stage-5b-stitch/monitor/', LitReviewStage5BStitchMonitorView.as_view(), name='stage5b-stitch-monitor'),
    path('reviews/<int:pk>/stage-5b-stitch/status/', LitReviewStage5BStitchStatusView.as_view(), name='stage5b-stitch-status'),
    path('reviews/<int:pk>/stage-5c-references/monitor/', LitReviewStage5CReferencesMonitorView.as_view(), name='stage5c-references-monitor'),
    path('reviews/<int:pk>/stage-5c-references/status/', LitReviewStage5CReferencesStatusView.as_view(), name='stage5c-references-status'),
    path('reviews/<int:pk>/stage-2-intake/resolver-status/', LitReviewResolverStatusView.as_view(), name='stage2-resolver-status'),
    path('reviews/<int:pk>/stage-2-intake/citation-status/', LitReviewCitationStatusView.as_view(), name='stage2-citation-status'),
    path('api/reviews/', LitReviewStage1ApiCreateView.as_view(), name='stage1-api-create'),
]
