from django.conf import settings
from django.db import models


class Review(models.Model):
    class Status(models.TextChoices):
        QUEUED = 'queued', 'Queued'
        RUNNING = 'running', 'Running'
        UPLOAD_WINDOW = 'upload_window', 'Upload Window'
        PAPER_CONFIRMATION = 'paper_confirmation', 'Paper Confirmation'
        DONE = 'done', 'Done'

    title = models.CharField(max_length=255)
    objectives = models.TextField()
    pico_population = models.TextField(blank=True)
    pico_intervention = models.TextField(blank=True)
    pico_comparison = models.TextField(blank=True)
    pico_outcomes = models.TextField(blank=True)
    inclusion_criteria = models.TextField(blank=True)
    exclusion_criteria = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.QUEUED,
    )
    stage_progress = models.JSONField(default=dict, blank=True)
    scaffold_data = models.JSONField(default=dict, blank=True)
    scaffold_preamble_template = models.TextField(blank=True)
    theme_synthesis = models.JSONField(default=list, blank=True)
    theme_synthesis_status = models.CharField(max_length=32, blank=True)
    theme_synthesis_error = models.TextField(blank=True)
    theme_synthesis_updated_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.title


class ResearchQuestion(models.Model):
    class QuestionType(models.TextChoices):
        DESCRIPTIVE = 'descriptive', 'Descriptive'
        COMPARATIVE = 'comparative', 'Comparative'
        CAUSAL = 'causal', 'Causal'
        EXPLORATORY = 'exploratory', 'Exploratory'

    review = models.ForeignKey(
        Review,
        on_delete=models.CASCADE,
        related_name='research_questions',
    )
    question_text = models.TextField()
    type = models.CharField(
        max_length=12,
        choices=QuestionType.choices,
        default=QuestionType.DESCRIPTIVE,
    )

    def __str__(self):
        return f'{self.type}: {self.question_text[:80]}'


class SearchQuery(models.Model):
    class Focus(models.TextChoices):
        CORE = 'core', 'Core'
        CONSTRUCTS = 'constructs', 'Constructs'
        POPULATION = 'population', 'Population'
        OUTCOMES = 'outcomes', 'Outcomes'

    review = models.ForeignKey(
        Review,
        on_delete=models.CASCADE,
        related_name='search_queries',
    )
    query_string = models.TextField()
    focus = models.CharField(max_length=20, choices=Focus.choices)
    rationale = models.TextField(blank=True)
    is_executed = models.BooleanField(default=False)
    ris_uploaded = models.BooleanField(default=False)
    ris_uploaded_at = models.DateTimeField(null=True, blank=True)
    ris_file_name = models.CharField(max_length=255, blank=True)
    imported_records = models.IntegerField(default=0)
    missing_abstracts = models.IntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['review', 'focus'], name='unique_review_focus_query')
        ]

    def __str__(self):
        return f'{self.review_id}:{self.focus}'


class Paper(models.Model):
    class FullTextDecision(models.TextChoices):
        NOT_SCREENED = 'not_screened', 'Not_Screened'
        INCLUDED = 'included', 'Included'
        EXCLUDED = 'excluded', 'Excluded'
        MANUAL_FLAG = 'manual_flag', 'Manual_Flag'

    class TADecision(models.TextChoices):
        INCLUDED = 'included', 'Included'
        EXCLUDED = 'excluded', 'Excluded'
        FLAGGED = 'flagged', 'Flagged'
        TEMP_FLAG = 'temp_flag', 'Temp_Flag'
        MANUAL_FLAG = 'manual_flag', 'Manual_Flag'
        MISSING_ABS = 'missing_abs', 'Missing_Abs'
        NOT_PROCESSED = 'not_processed', 'Not_Processed'

    class TitleScreeningDecision(models.TextChoices):
        INCLUDED = 'title_screening_included', 'Title_Screening_Included'
        EXCLUDED = 'title_screening_excluded', 'Title_Screening_Excluded'
        UNCERTAIN = 'title_screening_uncertain', 'Title_Screening_Uncertain'
        MANUAL_TITLES = 'manual_titles', 'Manual_Titles'
        NOT_PROCESSED = 'title_screening_not_processed', 'Title_Screening_Not_Processed'

    review = models.ForeignKey(
        Review,
        on_delete=models.CASCADE,
        related_name='papers',
    )
    title = models.CharField(max_length=500)
    authors = models.TextField(blank=True)
    abstract = models.TextField(blank=True)
    publication_year = models.IntegerField(null=True, blank=True)
    journal = models.CharField(max_length=255, blank=True)
    volume = models.CharField(max_length=64, blank=True)
    number = models.CharField(max_length=64, blank=True)
    start_page = models.CharField(max_length=64, blank=True)
    end_page = models.CharField(max_length=64, blank=True)
    publisher = models.CharField(max_length=255, blank=True)
    issn = models.CharField(max_length=64, blank=True)
    language = models.CharField(max_length=64, blank=True)
    type_of_work = models.CharField(max_length=128, blank=True)
    access_date = models.CharField(max_length=64, blank=True)
    notes = models.TextField(blank=True)
    doi = models.CharField(max_length=255, blank=True, db_index=True)
    scopus_id = models.CharField(max_length=255, blank=True, db_index=True)
    url = models.URLField(blank=True)
    keywords = models.TextField(blank=True)
    citation_count = models.IntegerField(default=0)
    ta_decision = models.CharField(
        max_length=20,
        choices=TADecision.choices,
        blank=True,
        null=True,
        default=TADecision.NOT_PROCESSED,
    )
    title_screening_decision = models.CharField(
        max_length=40,
        choices=TitleScreeningDecision.choices,
        default=TitleScreeningDecision.NOT_PROCESSED,
        db_index=True,
    )
    title_screening_confidence = models.FloatField(default=0.0)
    title_screening_reason = models.TextField(blank=True)
    title_screening_status = models.CharField(max_length=32, blank=True)
    title_screening_provider = models.CharField(max_length=32, blank=True)
    title_screening_model = models.CharField(max_length=64, blank=True)
    title_screening_error = models.TextField(blank=True)
    title_screening_screened_at = models.DateTimeField(null=True, blank=True)
    ta_confidence = models.FloatField(default=0.0)
    ta_reason = models.TextField(blank=True)
    screening_conflict = models.BooleanField(default=False)
    pdf_source = models.CharField(max_length=64, blank=True)
    pdf_path = models.FileField(upload_to='papers/pdfs/', blank=True)
    fulltext_retrieved = models.BooleanField(default=False)
    mineru_markdown = models.TextField(blank=True)
    mineru_parsed = models.BooleanField(default=False)
    processed_pdf_mineru = models.BooleanField(default=False)
    mineru_batch_id = models.CharField(max_length=128, blank=True)
    mineru_status = models.CharField(max_length=32, blank=True)
    mineru_error = models.TextField(blank=True)
    ref_delete_done = models.BooleanField(default=False)
    full_text_decision = models.CharField(
        max_length=20,
        choices=FullTextDecision.choices,
        default=FullTextDecision.NOT_SCREENED,
    )
    full_text_exclusion_reason = models.TextField(blank=True)
    full_text_rq_tags = models.JSONField(default=list, blank=True)
    full_text_rq_findings_map = models.JSONField(default=dict, blank=True)
    full_text_rq1_findings_summary = models.TextField(blank=True)
    full_text_rq2_findings_summary = models.TextField(blank=True)
    full_text_notes = models.TextField(blank=True)
    full_text_screening_status = models.CharField(max_length=32, blank=True)
    full_text_screening_provider = models.CharField(max_length=32, blank=True)
    full_text_screening_model = models.CharField(max_length=64, blank=True)
    full_text_screening_error = models.TextField(blank=True)
    full_text_screened_at = models.DateTimeField(null=True, blank=True)
    full_text_summery = models.JSONField(default=dict, blank=True)
    full_text_extraction = models.JSONField(default=dict, blank=True)
    full_text_quality = models.JSONField(default=dict, blank=True)
    full_text_tccm = models.JSONField(default=dict, blank=True)
    full_text_summery_status = models.CharField(max_length=32, blank=True)
    full_text_summery_error = models.TextField(blank=True)
    full_text_summery_updated_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.title


class ThemeSynthesis(models.Model):
    class EvidenceGrade(models.TextChoices):
        ESTABLISHED = 'Established', 'Established'
        EMERGING = 'Emerging', 'Emerging'
        CONTESTED = 'Contested', 'Contested'
        INSUFFICIENT = 'Insufficient', 'Insufficient'

    review = models.ForeignKey(
        Review,
        on_delete=models.CASCADE,
        related_name='theme_syntheses',
    )
    theme_name_locked = models.CharField(max_length=255)
    evidence_grade = models.CharField(max_length=32, choices=EvidenceGrade.choices)
    paper_count = models.IntegerField(default=0)
    pct_of_corpus = models.FloatField(default=0.0)
    finding_direction = models.CharField(max_length=32, blank=True)
    designs_represented = models.JSONField(default=list, blank=True)
    grade_rationale = models.TextField(blank=True)
    theme_description = models.TextField(blank=True)
    order_index = models.IntegerField(default=0)
    advocate_notes = models.TextField(blank=True)
    critic_notes = models.TextField(blank=True)
    reconciler_notes = models.TextField(blank=True)
    reconciled_text = models.TextField(blank=True)
    papers = models.ManyToManyField(Paper, related_name='themes', blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['review', 'theme_name_locked'], name='unique_review_locked_theme_name')
        ]
        ordering = ['order_index', '-paper_count', 'id']

    def __str__(self):
        return f'{self.review_id}: {self.theme_name_locked}'


class LitReview(models.Model):
    class Status(models.TextChoices):
        PLANNING = 'planning', 'Planning'
        SEARCHING = 'searching', 'Searching'
        EXTRACTING = 'extracting', 'Extracting'
        WRITING = 'writing', 'Writing'
        DONE = 'done', 'Done'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='lit_reviews',
        null=True,
        blank=True,
    )
    research_context = models.TextField(blank=True)
    research_questions = models.JSONField(default=list, blank=True)
    research_question = models.TextField()
    target_word_count = models.IntegerField()
    total_words_allocated = models.IntegerField(default=0)
    review_goal = models.TextField(blank=True)
    gap_statement = models.TextField(blank=True)
    section_order_rationale = models.TextField(blank=True)
    final_prose = models.TextField(blank=True)
    stage_progress = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PLANNING,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'LR#{self.pk}: {self.research_question[:80]}'


class ReviewSection(models.Model):
    class SectionType(models.TextChoices):
        FOUNDATION = 'foundation', 'Foundation'
        DEBATE = 'debate', 'Debate'
        RECENT = 'recent', 'Recent'
        GAP = 'gap', 'Gap'

    review = models.ForeignKey(
        LitReview,
        on_delete=models.CASCADE,
        related_name='sections',
    )
    number = models.IntegerField()
    title = models.CharField(max_length=255)
    type = models.CharField(max_length=16, choices=SectionType.choices)
    purpose = models.TextField(blank=True)
    what_to_look_for = models.TextField(blank=True)
    search_keywords = models.JSONField(default=list, blank=True)
    notable_authors = models.JSONField(default=list, blank=True)
    target_paper_count = models.CharField(max_length=64, blank=True)
    leads_to = models.TextField(blank=True)
    word_count_target = models.IntegerField(default=0)
    prose = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['review', 'number'], name='unique_lit_review_section_number'),
        ]
        ordering = ['number', 'id']

    def __str__(self):
        return f'LR#{self.review_id} S{self.number}: {self.title}'


class LitPaper(models.Model):
    class Origin(models.TextChoices):
        RIS_UPLOAD = 'ris_upload', 'RIS Upload'
        EXCEL_UPLOAD = 'excel_upload', 'Excel Upload'
        PDF_UPLOAD = 'pdf_upload', 'PDF Upload'

    review = models.ForeignKey(
        LitReview,
        on_delete=models.CASCADE,
        related_name='papers',
    )
    title = models.CharField(max_length=500)
    authors = models.TextField(blank=True)
    year = models.IntegerField(null=True, blank=True)
    source = models.CharField(max_length=255, blank=True)
    doi = models.CharField(max_length=255, blank=True, db_index=True)
    url = models.URLField(blank=True)
    pdf_link = models.URLField(blank=True)
    origin = models.CharField(max_length=20, choices=Origin.choices)
    excel_row_index = models.IntegerField(null=True, blank=True)
    pdf_path = models.FileField(upload_to='lit_papers/pdfs/', blank=True)
    fulltext_retrieved = models.BooleanField(default=False)
    pdf_source = models.CharField(max_length=64, blank=True)
    mineru_markdown = models.TextField(blank=True)
    mineru_parsed = models.BooleanField(default=False)
    processed_pdf_mineru = models.BooleanField(default=False)
    mineru_batch_id = models.CharField(max_length=128, blank=True)
    mineru_status = models.CharField(max_length=32, blank=True)
    mineru_error = models.TextField(blank=True)
    ref_delete_done = models.BooleanField(default=False)
    citation_apa = models.TextField(blank=True)
    citation_status = models.CharField(max_length=32, blank=True)
    citation_error = models.TextField(blank=True)
    citation_source = models.CharField(max_length=32, blank=True)
    per_paper_extraction = models.JSONField(default=dict, blank=True)
    per_paper_quality_category = models.CharField(max_length=1, blank=True)
    per_paper_extraction_status = models.CharField(max_length=32, blank=True)
    per_paper_extraction_error = models.TextField(blank=True)
    per_paper_extraction_updated_at = models.DateTimeField(null=True, blank=True)
    section_assignment_status = models.CharField(max_length=32, blank=True)
    section_assignment_error = models.TextField(blank=True)
    section_assignment_updated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'LR#{self.review_id} Paper#{self.id}: {self.title[:80]}'


class LitPaperAssignment(models.Model):
    review = models.ForeignKey(
        LitReview,
        on_delete=models.CASCADE,
        related_name='paper_assignments',
    )
    paper = models.ForeignKey(
        LitPaper,
        on_delete=models.CASCADE,
        related_name='section_assignments',
    )
    section = models.ForeignKey(
        ReviewSection,
        on_delete=models.CASCADE,
        related_name='paper_assignments',
    )
    assignment_confidence = models.CharField(max_length=16, blank=True)
    reason = models.TextField(blank=True)
    how_to_use = models.TextField(blank=True)
    also_relevant_to = models.JSONField(default=list, blank=True)
    flag = models.CharField(max_length=64, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    assigned_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['review', 'paper'], name='unique_lit_review_paper_assignment'),
        ]
        ordering = ['id']

    def __str__(self):
        return f'LR#{self.review_id} Assignment Paper#{self.paper_id} -> Section#{self.section_id}'






