import json

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    LitPaper,
    LitPaperAssignment,
    LitReview,
    Paper,
    ResearchQuestion,
    Review,
    ReviewSection,
    SearchQuery,
    ThemeSynthesis,
)


class ResearchQuestionInline(admin.TabularInline):
    model = ResearchQuestion
    extra = 0


class SearchQueryInline(admin.TabularInline):
    model = SearchQuery
    extra = 0


class SearchQueryFocusFilter(admin.SimpleListFilter):
    title = 'focus'
    parameter_name = 'focus'

    def lookups(self, request, model_admin):
        return SearchQuery.Focus.choices

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            return queryset.filter(focus=value)
        return queryset


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('id','title', 'status', 'theme_synthesis_status', 'theme_synthesis_updated_at')
    list_filter = ('status', 'theme_synthesis_status')
    search_fields = ('title', 'objectives', 'theme_synthesis_error')
    readonly_fields = (
        'theme_synthesis_updated_at',
        'scaffold_data_pretty',
        'theory_landscape_json',
        'theoretical_synthesis_json',
        'propositions_json',
        'conceptual_model_spec_json',
        'tccm_summary_json',
    )
    inlines = [ResearchQuestionInline, SearchQueryInline]

    fieldsets = (
        (
            'Review Core',
            {
                'fields': (
                    
                    'title',
                    'status',
                    'objectives',
                )
            },
        ),
        (
            'PICO and Criteria',
            {
                'classes': ('collapse',),
                'fields': (
                    'pico_population',
                    'pico_intervention',
                    'pico_comparison',
                    'pico_outcomes',
                    'inclusion_criteria',
                    'exclusion_criteria',
                )
            },
        ),
        (
            'Theme Synthesis (Phase 17)',
            {
                'fields': (
                    'theme_synthesis_status',
                    'theme_synthesis_error',
                    'theme_synthesis_updated_at',
                    'theme_synthesis',
                )
            },
        ),
        (
            'Pipeline Data',
            {
                'classes': ('collapse',),
                'fields': (
                    'stage_progress',
                    'scaffold_data_pretty',
                    'scaffold_data',
                    'scaffold_preamble_template',
                )
            },
        ),
        (
            'Scaffold: Theory / TCCM / Conceptual',
            {
                'classes': ('collapse',),
                'fields': (
                    'theory_landscape_json',
                    'theoretical_synthesis_json',
                    'propositions_json',
                    'conceptual_model_spec_json',
                    'tccm_summary_json',
                ),
            },
        ),
    )

    @admin.display(description='Scaffold theory_landscape')
    def theory_landscape_json(self, obj):
        data = obj.scaffold_data if isinstance(obj.scaffold_data, dict) else {}
        value = data.get('theory_landscape', {})
        return json.dumps(value, ensure_ascii=False, indent=2)

    @admin.display(description='Scaffold data (pretty)')
    def scaffold_data_pretty(self, obj):
        value = obj.scaffold_data if isinstance(obj.scaffold_data, dict) else {}
        pretty = json.dumps(value, ensure_ascii=False, indent=2)
        return format_html('<pre style="white-space: pre-wrap; margin: 0;">{}</pre>', pretty)

    @admin.display(description='Scaffold theoretical_synthesis')
    def theoretical_synthesis_json(self, obj):
        data = obj.scaffold_data if isinstance(obj.scaffold_data, dict) else {}
        value = data.get('theoretical_synthesis', {})
        return json.dumps(value, ensure_ascii=False, indent=2)

    @admin.display(description='Scaffold propositions')
    def propositions_json(self, obj):
        data = obj.scaffold_data if isinstance(obj.scaffold_data, dict) else {}
        ts = data.get('theoretical_synthesis', {}) if isinstance(data.get('theoretical_synthesis', {}), dict) else {}
        value = ts.get('propositions', []) if isinstance(ts.get('propositions', []), list) else []
        return json.dumps(value, ensure_ascii=False, indent=2)

    @admin.display(description='Scaffold conceptual_model_spec')
    def conceptual_model_spec_json(self, obj):
        data = obj.scaffold_data if isinstance(obj.scaffold_data, dict) else {}
        value = data.get('conceptual_model_spec', {})
        return json.dumps(value, ensure_ascii=False, indent=2)

    @admin.display(description='Scaffold tccm_summary')
    def tccm_summary_json(self, obj):
        data = obj.scaffold_data if isinstance(obj.scaffold_data, dict) else {}
        value = data.get('tccm_summary', {})
        return json.dumps(value, ensure_ascii=False, indent=2)


@admin.register(ResearchQuestion)
class ResearchQuestionAdmin(admin.ModelAdmin):
    list_display = ('review', 'type', 'question_text')
    list_filter = ('type',)
    search_fields = ('question_text',)


@admin.register(SearchQuery)
class SearchQueryAdmin(admin.ModelAdmin):
    list_display = ('review', 'focus', 'is_executed', 'ris_uploaded', 'imported_records')
    list_filter = (SearchQueryFocusFilter, 'is_executed', 'ris_uploaded')
    search_fields = ('query_string', 'rationale', 'ris_file_name')


@admin.action(description='Set TA decision to empty (NULL)')
def reset_ta_decision_to_null(modeladmin, request, queryset):
    updated = queryset.update(ta_decision=None, ta_reason='')
    modeladmin.message_user(request, f'{updated} paper(s) reset to empty TA decision.')


@admin.action(description='Mark selected papers as Missing_Abs')
def mark_missing_abstract(modeladmin, request, queryset):
    updated = queryset.update(
        ta_decision=Paper.TADecision.MISSING_ABS,
        ta_reason='Marked manually from admin panel as missing abstract.',
    )
    modeladmin.message_user(request, f'{updated} paper(s) marked as Missing_Abs.')


@admin.action(description='Clear screening conflicts for selected papers')
def clear_screening_conflict(modeladmin, request, queryset):
    updated = queryset.update(screening_conflict=False)
    modeladmin.message_user(request, f'{updated} paper(s) conflict flag cleared.')


@admin.register(Paper)
class PaperAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'short_title',
        'title_screening_decision',
        'title_screening_confidence',
        'ta_decision',
        'ta_confidence',
        'full_text_decision',
        'fulltext_retrieved',
        'processed_pdf_mineru',
        'mineru_parsed',
        'full_text_screening_status',
        'full_text_summery_status',
        'citation_count',
    )
    list_display_links = ('id', 'short_title')
    list_editable = ('title_screening_decision', 'ta_decision', 'full_text_decision')
    list_filter = (
        'review',
        'title_screening_decision',
        'title_screening_status',
        'ta_decision',
        'full_text_decision',
        'fulltext_retrieved',
        'screening_conflict',
        'processed_pdf_mineru',
        'mineru_parsed',
        'ref_delete_done',
        'full_text_screening_status',
        'full_text_screening_provider',
        'full_text_summery_status',
        'publication_year',
    )
    search_fields = (
        'title',
        'authors',
        'doi',
        'scopus_id',
        'keywords',
        'ta_reason',
        'full_text_exclusion_reason',
    )
    ordering = ('-id',)
    list_per_page = 50
    list_select_related = ('review',)
    actions = [reset_ta_decision_to_null, mark_missing_abstract, clear_screening_conflict]

    readonly_fields = ('id',)

    fieldsets = (
        (
            'Paper Identity',
            {
                'fields': (
                    'id',
                    'review',
                    'title',
                    'authors',
                    'doi',
                    'scopus_id',
                    'url',
                    'publication_year',
                    'journal',
                    'citation_count',
                )
            },
        ),
        (
            'RIS Metadata',
            {
                'classes': ('collapse',),
                'fields': (
                    'keywords',
                    'volume',
                    'number',
                    'start_page',
                    'end_page',
                    'publisher',
                    'issn',
                    'language',
                    'type_of_work',
                    'access_date',
                    'notes',
                ),
            },
        ),
        (
            'Title Screening (Pre-Abstract)',
            {
                'fields': (
                    'title_screening_decision',
                    'title_screening_confidence',
                    'title_screening_reason',
                    'title_screening_status',
                    'title_screening_provider',
                    'title_screening_model',
                    'title_screening_error',
                    'title_screening_screened_at',
                )
            },
        ),
        (
            'Title/Abstract Screening (Phase 7)',
            {
                'fields': (
                    'ta_decision',
                    'ta_confidence',
                    'ta_reason',
                    'screening_conflict',
                )
            },
        ),
        (
            'Full-text Retrieval (Phase 12)',
            {
                'fields': (
                    'pdf_source',
                    'pdf_path',
                    'fulltext_retrieved',
                )
            },
        ),
        (
            'MinerU Processing',
            {
                'fields': (
                    'processed_pdf_mineru',
                    'mineru_parsed',
                    'mineru_batch_id',
                    'mineru_status',
                    'mineru_error',
                    'ref_delete_done',
                )
            },
        ),
        (
            'Full-text Screening',
            {
                'fields': (
                    'full_text_decision',
                    'full_text_exclusion_reason',
                    'full_text_rq_tags',
                    'full_text_rq_findings_map',
                    'full_text_rq1_findings_summary',
                    'full_text_rq2_findings_summary',
                    'full_text_notes',
                    'full_text_screening_provider',
                    'full_text_screening_model',
                    'full_text_screening_status',
                    'full_text_screening_error',
                    'full_text_screened_at',
                )
            },
        ),
        (
            'DeepSeek Summary / Extraction / Quality',
            {
                'fields': (
                    'full_text_summery_status',
                    'full_text_summery_error',
                    'full_text_summery_updated_at',
                    'full_text_summery',
                    'full_text_extraction',
                    'full_text_quality',
                    'full_text_tccm',
                )
            },
        ),
        (
            'Large Text Blobs',
            {
                'classes': ('collapse',),
                'fields': (
                    'abstract',
                    'mineru_markdown',
                ),
            },
        ),
    )

    @admin.display(description='Title')
    def short_title(self, obj):
        value = obj.title or ''
        if len(value) <= 90:
            return value
        return f'{value[:87]}...'


@admin.register(ThemeSynthesis)
class ThemeSynthesisAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'review',
        'theme_name_locked',
        'evidence_grade',
        'paper_count',
        'pct_of_corpus',
        'order_index',
    )
    list_filter = ('evidence_grade', 'review')
    search_fields = ('theme_name_locked', 'grade_rationale', 'theme_description', 'advocate_notes', 'critic_notes', 'reconciled_text')
    filter_horizontal = ('papers',)
    ordering = ('review', 'order_index', '-paper_count')
    readonly_fields = ('reconciled_text',)


@admin.register(LitReview)
class LitReviewAdmin(admin.ModelAdmin):
    list_display = ('id', 'short_question', 'target_word_count', 'total_words_allocated', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('research_question', 'review_goal', 'gap_statement')
    readonly_fields = ('created_at',)

    @admin.display(description='Research Question')
    def short_question(self, obj):
        text = obj.research_question or ''
        if len(text) <= 90:
            return text
        return f'{text[:87]}...'


@admin.register(ReviewSection)
class ReviewSectionAdmin(admin.ModelAdmin):
    list_display = ('id', 'review', 'number', 'title', 'type', 'word_count_target')
    list_editable = ('word_count_target',)
    list_display_links = ('id', 'title')
    list_filter = ('type', 'review')
    search_fields = ('title', 'purpose', 'what_to_look_for', 'leads_to')
    ordering = ('review', 'number', 'id')


@admin.register(LitPaper)
class LitPaperAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'review',
        'short_title',
        'origin',
        'year',
        'doi',
        'fulltext_retrieved',
        'pdf_source',
        'processed_pdf_mineru',
        'mineru_parsed',
        'citation_status',
        'excel_row_index',
    )
    list_filter = (
        'origin',
        'fulltext_retrieved',
        'pdf_source',
        'processed_pdf_mineru',
        'mineru_parsed',
        'mineru_status',
        'citation_status',
        'review',
    )
    search_fields = ('title', 'authors', 'doi', 'source', 'url', 'pdf_link', 'citation_apa')
    ordering = ('review', 'id')

    @admin.display(description='Title')
    def short_title(self, obj):
        value = obj.title or ''
        if len(value) <= 80:
            return value
        return f'{value[:77]}...'


@admin.register(LitPaperAssignment)
class LitPaperAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'review',
        'paper_id',
        'short_paper_title',
        'section_number',
        'section_title',
        'assignment_confidence',
        'flag',
        'assigned_at',
    )
    list_filter = (
        'review',
        'assignment_confidence',
        'flag',
        'section',
        'assigned_at',
    )
    search_fields = (
        'paper__title',
        'reason',
        'how_to_use',
        'section__title',
    )
    ordering = ('review', 'section__number', 'paper_id')
    list_select_related = ('review', 'paper', 'section')

    @admin.display(description='Paper Title')
    def short_paper_title(self, obj):
        value = obj.paper.title if obj.paper else ''
        if len(value) <= 80:
            return value
        return f'{value[:77]}...'

    @admin.display(description='Section #')
    def section_number(self, obj):
        return obj.section.number if obj.section else None

    @admin.display(description='Section Title')
    def section_title(self, obj):
        return obj.section.title if obj.section else ''
