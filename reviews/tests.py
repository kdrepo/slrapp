import json
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .constants import DEFAULT_EXCLUSION_CRITERIA, DEFAULT_INCLUSION_CRITERIA
from .forms import ReviewForm
from .models import Paper, ResearchQuestion, Review, SearchQuery
from .services.gemini_service import formalize_research_parameters, render_scaffold_preamble
from .services.ris_parser import dedupe_review_papers, ingest_ris_file
from .services.scopus_query_service import generate_scopus_queries
from .services.screening_service import _ingest_batch_responses, prepare_screening_batch


class ReviewModelTests(TestCase):
    def test_review_can_be_created(self):
        review = Review.objects.create(
            title='AI Screening for Literature Reviews',
            objectives='Evaluate AI-assisted title and abstract screening.',
            pico_population='Peer-reviewed publications on screening automation',
            pico_intervention='LLM-assisted screening',
            pico_comparison='Manual screening',
            pico_outcomes='Precision, recall, time saved',
            inclusion_criteria='Studies discussing screening workflows',
            exclusion_criteria='Editorials and non-English abstracts',
            stage_progress={'intake': 'complete'},
            scaffold={'source': 'scopus'},
        )

        self.assertEqual(review.status, Review.Status.QUEUED)
        self.assertEqual(review.stage_progress['intake'], 'complete')
        self.assertEqual(review.scaffold['source'], 'scopus')


class IntakeDefaultsTests(TestCase):
    def test_review_form_has_static_criteria_defaults(self):
        form = ReviewForm()

        self.assertEqual(form.fields['inclusion_criteria'].initial, DEFAULT_INCLUSION_CRITERIA)
        self.assertEqual(form.fields['exclusion_criteria'].initial, DEFAULT_EXCLUSION_CRITERIA)


class PaperModelTests(TestCase):
    def test_paper_can_be_created_with_keywords_and_citations(self):
        review = Review.objects.create(
            title='Scopus RIS Review',
            objectives='Assess RIS ingestion.',
        )

        paper = Paper.objects.create(
            review=review,
            title='Large Language Models for Evidence Synthesis',
            authors='Doe, Jane; Roe, Richard',
            abstract='An overview of LLM use in evidence synthesis.',
            publication_year=2025,
            journal='Journal of Evidence Engineering',
            volume='12',
            number='3',
            start_page='101',
            end_page='120',
            publisher='Example Press',
            issn='1234-5678',
            language='English',
            type_of_work='Article',
            access_date='2026-03-18',
            notes='Cited By: 42',
            doi='10.1000/example-doi',
            scopus_id='2-s2.0-1234567890',
            url='https://example.com/paper',
            keywords='systematic review;llm;screening automation',
            citation_count=42,
            ta_decision=Paper.TADecision.INCLUDED,
            ta_confidence=0.93,
            ta_reason='Strong relevance to the review objective.',
            fulltext_retrieved=True,
            pdf_text='Extracted full text content',
        )

        self.assertEqual(paper.review, review)
        self.assertIn('llm', paper.keywords)
        self.assertEqual(paper.citation_count, 42)
        self.assertEqual(paper.ta_decision, Paper.TADecision.INCLUDED)


class ReviewCreateViewTests(TestCase):
    @patch('reviews.views.formalize_research_parameters')
    def test_review_create_redirects_to_confirmation_and_starts_phase2(self, mock_formalize):
        response = self.client.post(
            reverse('reviews:review-create'),
            data={
                'title': 'Clinical Decision Support SLR',
                'objectives': 'Assess impact of AI-driven clinical decision support.',
                'pico_population': 'Hospital clinicians',
                'pico_intervention': 'AI decision support tools',
                'pico_comparison': 'Standard care',
                'pico_outcomes': 'Accuracy and efficiency',
                'inclusion_criteria': DEFAULT_INCLUSION_CRITERIA,
                'exclusion_criteria': DEFAULT_EXCLUSION_CRITERIA,
            },
        )

        review = Review.objects.get(title='Clinical Decision Support SLR')

        mock_formalize.assert_called_once_with(review_id=review.pk)
        self.assertRedirects(
            response,
            reverse('reviews:review-confirm', kwargs={'pk': review.pk}),
        )


class GeminiFormalizationServiceTests(TestCase):
    @patch('reviews.services.gemini_service._call_gemini_model')
    def test_formalize_research_parameters_keeps_mandatory_criteria(self, mock_call_model):
        review = Review.objects.create(
            title='Digital Vulnerability Review',
            objectives='Understand vulnerability in digital commerce.',
            pico_population='Consumers in online markets',
            inclusion_criteria=DEFAULT_INCLUSION_CRITERIA,
            exclusion_criteria=DEFAULT_EXCLUSION_CRITERIA,
        )

        malformed = 'NOT JSON'
        corrected = '''
        {
          "research_questions": [
            {"rq": "How does digital market exposure affect vulnerability?", "type": "causal"}
          ],
          "refined_pico": {
            "population": "Adult consumers in digital marketplaces",
            "intervention": "Exposure to digital platform design and marketing tactics",
            "comparison": "Traditional retail contexts",
            "outcomes": "Vulnerability metrics and harm indicators"
          },
          "refined_criteria": {
            "inclusion_criteria": ["Must focus on platform workers"],
            "exclusion_criteria": ["Exclude studies outside labor platforms"]
          }
        }
        '''

        mock_call_model.side_effect = [malformed, corrected]

        formalize_research_parameters(review.id)

        review.refresh_from_db()
        self.assertIn(DEFAULT_INCLUSION_CRITERIA, review.inclusion_criteria)
        self.assertIn(DEFAULT_EXCLUSION_CRITERIA, review.exclusion_criteria)

    def test_render_scaffold_preamble_is_ready_for_future_calls(self):
        review = Review.objects.create(
            title='Scaffold Test',
            objectives='Objective text',
            scaffold={
                'primary_term': 'consumer vulnerability',
                'banned_terms': ['consumer vulnerabilities'],
                'prisma_counts': {'scopus_retrieved': 10, 'final_included': 3},
                'theme_names': ['Theme A'],
                'paper_registry': ['(Doe et al., 2024)'],
                'phase_2': {
                    'research_questions': [
                        {'rq': 'RQ sample 1', 'type': 'descriptive'},
                    ]
                },
            },
        )

        preamble = render_scaffold_preamble(review=review, include_registry=True)

        self.assertIn('CONSISTENCY RULES', preamble)
        self.assertIn('consumer vulnerability', preamble)
        self.assertIn('RQ1: RQ sample 1', preamble)


class ScopusQueryServiceTests(TestCase):
    @patch('reviews.services.scopus_query_service._call_gemini_model')
    def test_generate_scopus_queries_builds_four_queries_with_filters(self, mock_call_model):
        review = Review.objects.create(
            title='Scopus Strategy Review',
            objectives='Assess digital consumer vulnerability factors.',
            inclusion_criteria=DEFAULT_INCLUSION_CRITERIA,
            exclusion_criteria=DEFAULT_EXCLUSION_CRITERIA,
            scaffold={'start_year': 2010, 'end_year': 2024},
        )
        ResearchQuestion.objects.create(
            review=review,
            question_text='How does platform design affect consumer vulnerability?',
            type=ResearchQuestion.QuestionType.CAUSAL,
        )

        malformed = 'Not valid JSON at all'
        corrected = json.dumps(
            [
                {'query': 'TITLE-ABS-KEY("gig economy" AND "platform work")', 'focus': 'core', 'rationale': 'Core terms.'},
                {'query': 'TITLE-ABS-KEY("precarious work" AND "platform")', 'focus': 'constructs', 'rationale': 'Constructs.'},
                {'query': 'TITLE-ABS-KEY("platform workers" OR "drivers")', 'focus': 'population', 'rationale': 'Population.'},
                {'query': 'TITLE-ABS-KEY("job satisfaction" OR "algorithmic management")', 'focus': 'outcomes', 'rationale': 'Outcomes.'},
            ]
        )
        mock_call_model.side_effect = [malformed, corrected]

        generated = generate_scopus_queries(review.id)

        review.refresh_from_db()
        db_queries = list(review.search_queries.order_by('focus'))

        self.assertEqual(len(generated), 4)
        self.assertEqual(len(db_queries), 4)
        self.assertEqual(review.stage_progress.get('phase_3'), 'queries_generated')
        self.assertEqual(generated[0]['focus'], SearchQuery.Focus.CORE)
        self.assertIn('LIMIT-TO ( DOCTYPE , "ar" )', generated[0]['query_string'])
        self.assertIn('LIMIT-TO ( LANGUAGE , "English" )', generated[0]['query_string'])
        self.assertIn('EXACTKEYWORD', generated[0]['query_string'])


class RISIngestorServiceTests(TestCase):
    @patch('reviews.services.ris_parser._load_ris_entries')
    def test_ingest_then_dedupe_maps_metadata_and_reports_quality(self, mock_load):
        review = Review.objects.create(title='RIS Ingest Review', objectives='obj')

        mock_load.return_value = [
            {
                'authors': ['Doe, Jane', 'Roe, Richard'],
                'title': 'Platform Work and Vulnerability',
                'year': '2024',
                'secondary_title': 'Journal of Platform Studies',
                'abstract': 'Study abstract',
                'doi': '10.1000/xyz',
                'urls': ['https://example.org/p1'],
                'keywords': ['gig economy', 'platform'],
                'volume': '10',
                'number': '2',
                'start_page': '15',
                'end_page': '34',
                'publisher': 'Academic Press',
                'issn': '0000-0000',
                'language': 'English',
                'type_of_reference': 'JOUR',
                'access_date': '2026-03-18',
                'notes': ['Cited By: 7'],
                'id': 'SCOPUS-1',
            },
            {
                'authors': ['Someone, A'],
                'title': 'Platform Work and Vulnerability',
                'year': '2023',
                'doi': '',
                'abstract': '',
                'notes': ['Cited By: 3'],
            },
        ]

        ingest_report = ingest_ris_file(review.id, 'dummy.ris')
        dedupe_report = dedupe_review_papers(review.id)
        papers = list(review.papers.all())

        self.assertEqual(ingest_report['total_papers_imported'], 2)
        self.assertEqual(len(papers), 1)
        self.assertEqual(dedupe_report['duplicates_removed'], 1)
        self.assertEqual(papers[0].citation_count, 7)
        self.assertEqual(papers[0].authors, 'Doe, Jane; Roe, Richard')
        self.assertEqual(papers[0].keywords, 'gig economy; platform')


class ReviewConfirmationViewTests(TestCase):
    def test_confirmation_view_locks_review_and_redirects_to_search_strategy(self):
        review = Review.objects.create(
            title='Confirmable Review',
            objectives='Test objective',
            pico_population='Old pop',
            pico_intervention='Old intervention',
            pico_comparison='Old comparison',
            pico_outcomes='Old outcomes',
            inclusion_criteria=DEFAULT_INCLUSION_CRITERIA,
            exclusion_criteria=DEFAULT_EXCLUSION_CRITERIA,
        )
        rq = ResearchQuestion.objects.create(
            review=review,
            question_text='Old question',
            type=ResearchQuestion.QuestionType.DESCRIPTIVE,
        )

        response = self.client.post(
            reverse('reviews:review-confirm', kwargs={'pk': review.pk}),
            data={
                'pico_population': 'New population',
                'pico_intervention': 'New intervention',
                'pico_comparison': 'New comparison',
                'pico_outcomes': 'New outcomes',
                'inclusion_criteria': DEFAULT_INCLUSION_CRITERIA,
                'exclusion_criteria': DEFAULT_EXCLUSION_CRITERIA,
                'rqs-TOTAL_FORMS': '1',
                'rqs-INITIAL_FORMS': '1',
                'rqs-MIN_NUM_FORMS': '1',
                'rqs-MAX_NUM_FORMS': '1000',
                'rqs-0-id': str(rq.id),
                'rqs-0-question_text': 'Refined question text',
                'rqs-0-type': 'comparative',
                'rqs-0-DELETE': '',
            },
        )

        review.refresh_from_db()

        self.assertRedirects(
            response,
            reverse('reviews:search-strategy', kwargs={'pk': review.pk}),
        )
        self.assertEqual(review.status, Review.Status.RUNNING)
        self.assertEqual(review.pico_population, 'New population')
        self.assertEqual(review.stage_progress.get('phase_2'), 'confirmed_locked')


class SearchStrategyViewTests(TestCase):
    @patch('reviews.views.generate_scopus_queries')
    def test_search_strategy_view_calls_generation_when_queries_missing(self, mock_generate):
        review = Review.objects.create(
            title='Search Strategy UI Review',
            objectives='Objective',
            status=Review.Status.RUNNING,
        )

        response = self.client.get(reverse('reviews:search-strategy', kwargs={'pk': review.pk}))

        self.assertEqual(response.status_code, 200)
        mock_generate.assert_called_once_with(review_id=review.pk)


class RISUploadViewTests(TestCase):
    @patch('reviews.views.ingest_ris_file')
    @patch('reviews.views.dedupe_review_papers')
    def test_ris_upload_shows_uploaded_status_and_saves_quality_when_all_done(self, mock_dedupe, mock_ingest):
        review = Review.objects.create(title='Upload Review', objectives='obj')
        q1 = SearchQuery.objects.create(review=review, focus=SearchQuery.Focus.CORE, query_string='q1')
        SearchQuery.objects.create(review=review, focus=SearchQuery.Focus.CONSTRUCTS, query_string='q2', ris_uploaded=True)
        SearchQuery.objects.create(review=review, focus=SearchQuery.Focus.POPULATION, query_string='q3', ris_uploaded=True)
        SearchQuery.objects.create(review=review, focus=SearchQuery.Focus.OUTCOMES, query_string='q4', ris_uploaded=True)

        mock_ingest.return_value = {
            'total_papers_imported': 11,
            'duplicates_removed': 0,
            'missing_abstracts_flagged': 2,
        }
        mock_dedupe.return_value = {
            'total_before_dedupe': 40,
            'duplicates_removed': 6,
            'total_after_dedupe': 34,
            'missing_abstracts_flagged': 5,
        }

        ris_content = b'TY  - JOUR\nTI  - Sample\nER  -\n'
        upload = SimpleUploadedFile('sample.ris', ris_content, content_type='application/x-research-info-systems')

        response = self.client.post(
            reverse('reviews:ris-upload', kwargs={'pk': review.pk}),
            data={'ris_file': upload, 'search_query_id': q1.id},
        )

        review.refresh_from_db()
        q1.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(q1.ris_uploaded)
        self.assertContains(response, 'Data Quality Report')
        self.assertContains(response, 'Total Papers Imported: 40')
        self.assertContains(response, 'Duplicates Removed: 6')
        self.assertContains(response, 'Papers missing Abstracts (Flagged): 5')
        self.assertEqual(review.scaffold['prisma_counts']['scopus_retrieved'], 40)
        self.assertEqual(review.scaffold['prisma_counts']['after_dedup'], 34)


class ScreeningBatchServiceTests(TestCase):
    def test_prepare_screening_batch_uses_locked_rq_context_and_unprocessed_filter(self):
        review = Review.objects.create(
            title='Batch Screen Review',
            objectives='Assess worker outcomes.',
            inclusion_criteria=DEFAULT_INCLUSION_CRITERIA,
            exclusion_criteria=DEFAULT_EXCLUSION_CRITERIA,
        )
        ResearchQuestion.objects.create(
            review=review,
            question_text='How do platform controls affect worker wellbeing?',
            type=ResearchQuestion.QuestionType.CAUSAL,
        )

        Paper.objects.create(review=review, title='Paper A', abstract='Useful abstract', ta_decision=Paper.TADecision.NOT_PROCESSED)
        Paper.objects.create(review=review, title='Paper B', abstract='', ta_decision=Paper.TADecision.NOT_PROCESSED)
        Paper.objects.create(review=review, title='Paper C', abstract='Already done', ta_decision=Paper.TADecision.EXCLUDED)

        payload = prepare_screening_batch(review.id)

        self.assertEqual(payload['request_count'], 1)
        self.assertEqual(len(payload['paper_ids']), 1)
        self.assertEqual(payload['jsonl_path'], '')
        self.assertEqual(payload['paper_ids'][0], Paper.objects.get(title='Paper A').id)

    def test_ingest_batch_sets_conflict_for_low_confidence(self):
        review = Review.objects.create(title='Ingest Batch', objectives='Obj')
        paper = Paper.objects.create(review=review, title='Paper X', abstract='A')

        responses = [
            {
                'paper_id': str(paper.id),
                'text': '{"decision": "included", "confidence": 0.61, "reason": "Edge match", "criterion_failed": null}',
            }
        ]

        summary = _ingest_batch_responses(review=review, responses=responses)
        paper.refresh_from_db()

        self.assertEqual(summary['updated'], 1)
        self.assertEqual(paper.ta_decision, Paper.TADecision.INCLUDED)
        self.assertTrue(paper.screening_conflict)


class ScreeningConflictViewTests(TestCase):
    def test_conflict_resolution_include_clears_flag(self):
        review = Review.objects.create(title='Conflict UI', objectives='obj')
        ResearchQuestion.objects.create(
            review=review,
            question_text='RQ1 text',
            type=ResearchQuestion.QuestionType.DESCRIPTIVE,
        )
        paper = Paper.objects.create(
            review=review,
            title='Conflict Paper',
            abstract='x',
            ta_decision=Paper.TADecision.EXCLUDED,
            ta_confidence=0.51,
            ta_reason='Low certainty',
            screening_conflict=True,
        )

        response = self.client.post(
            reverse('reviews:screening-conflicts', kwargs={'pk': review.pk}),
            data={'paper_id': paper.id, 'decision': 'included'},
        )

        paper.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(paper.ta_decision, Paper.TADecision.INCLUDED)
        self.assertFalse(paper.screening_conflict)

class ScreeningBatchDebugViewTests(TestCase):
    @patch('reviews.views_batch_debug.submit_screening_batch')
    def test_debug_start_submits_five_papers(self, mock_submit):
        review = Review.objects.create(title='Debug Review', objectives='obj')
        mock_submit.return_value = {'submitted': True, 'request_count': 5, 'paper_ids': [1, 2, 3, 4, 5]}

        response = self.client.post(reverse('reviews:screening-batch-debug-start', kwargs={'pk': review.pk}))

        self.assertEqual(response.status_code, 200)
        mock_submit.assert_called_once_with(review_id=review.pk, max_papers=5, stage_key='phase_7_debug')

    def test_debug_page_loads(self):
        review = Review.objects.create(title='Debug Page', objectives='obj')
        response = self.client.get(reverse('reviews:screening-batch-debug', kwargs={'pk': review.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Gemini Batch Debug (5 Papers)')



class ScreeningDecisionReviewViewTests(TestCase):
    def test_decision_review_page_lists_papers_and_updates_decision(self):
        review = Review.objects.create(title='Decision Review', objectives='obj')
        paper = Paper.objects.create(
            review=review,
            title='Paper For Override',
            abstract='abc',
            ta_decision=Paper.TADecision.EXCLUDED,
            ta_reason='Initial AI exclusion reason',
            screening_conflict=True,
        )

        get_response = self.client.get(reverse('reviews:screening-decisions', kwargs={'pk': review.pk}))
        self.assertEqual(get_response.status_code, 200)
        self.assertContains(get_response, 'All Screening Decisions')
        self.assertContains(get_response, 'Initial AI exclusion reason')

        post_response = self.client.post(
            reverse('reviews:screening-decisions', kwargs={'pk': review.pk}),
            data={'paper_id': paper.id, 'decision': 'manual_flag', 'note': 'Reviewed manually'},
        )

        paper.refresh_from_db()
        self.assertEqual(post_response.status_code, 302)
        self.assertEqual(paper.ta_decision, Paper.TADecision.MANUAL_FLAG)
        self.assertFalse(paper.screening_conflict)
        self.assertIn('Manually set to manual_flag', paper.ta_reason)





    def test_decision_review_filters_by_ta_decision_and_confidence_band(self):
        review = Review.objects.create(title='Decision Filters', objectives='obj')
        Paper.objects.create(
            review=review,
            title='Included 0.75',
            abstract='A',
            ta_decision=Paper.TADecision.INCLUDED,
            ta_confidence=0.75,
        )
        Paper.objects.create(
            review=review,
            title='Included 0.95',
            abstract='B',
            ta_decision=Paper.TADecision.INCLUDED,
            ta_confidence=0.95,
        )
        Paper.objects.create(
            review=review,
            title='Excluded 0.76',
            abstract='C',
            ta_decision=Paper.TADecision.EXCLUDED,
            ta_confidence=0.76,
        )

        response = self.client.get(
            reverse('reviews:screening-decisions', kwargs={'pk': review.pk}),
            data={'ta_decision': 'included', 'confidence_band': '70_79'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Included 0.75')
        self.assertNotContains(response, 'Included 0.95')
        self.assertNotContains(response, 'Excluded 0.76')

class ScreeningExportViewTests(TestCase):
    def test_export_json_for_selected_ta_decision_generates_batch_links(self):
        review = Review.objects.create(title='Export Review', objectives='obj')
        for i in range(75):
            Paper.objects.create(
                review=review,
                title=f'Included {i}',
                abstract=f'Abs {i}',
                ta_decision=Paper.TADecision.INCLUDED,
            )

        response = self.client.post(
            reverse('reviews:screening-export', kwargs={'pk': review.pk}),
            data={'decision': 'included'},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Download Batches')
        self.assertContains(response, 'batch_01_1-70')
        self.assertContains(response, 'batch_02_71-75')

    def test_export_batch_download_returns_named_file(self):
        review = Review.objects.create(title='Export Batch File Review', objectives='obj')
        for i in range(75):
            Paper.objects.create(
                review=review,
                title=f'Included {i}',
                abstract=f'Abs {i}',
                ta_decision=Paper.TADecision.INCLUDED,
            )

        response = self.client.get(
            reverse('reviews:screening-export', kwargs={'pk': review.pk}),
            data={
                'download_batch': '1',
                'decision': 'included',
                'batch': '2',
                'batch_size': '70',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertIn('attachment; filename=batch_02_71-75.json', response['Content-Disposition'])

        payload = json.loads(response.content.decode('utf-8'))
        self.assertEqual(payload['ta_decision'], 'included')
        self.assertEqual(payload['batch_label'], 'batch_02_71-75')
        self.assertEqual(payload['count'], 5)

    def test_upload_json_updates_matching_titles(self):
        review = Review.objects.create(title='Upload Decisions', objectives='obj')
        paper = Paper.objects.create(
            review=review,
            title='Predictability and transparency of working conditions for food delivery platform workers across selected EU countries',
            abstract='Abs text',
            ta_decision=Paper.TADecision.EXCLUDED,
            ta_confidence=0.2,
            ta_reason='Old reason',
        )

        payload = [
            {
                'Title': 'Predictability and transparency of working conditions for food delivery platform workers across selected EU countries',
                'decision': 'manual_flag',
                'rq_tag': 'RQ2',
                'confidence': 0.9,
                'reason': 'Does not directly address motivations or job satisfaction determinants',
                'criterion': 'Does not address RQ1 or RQ2 directly',
            }
        ]
        upload = SimpleUploadedFile(
            'updates.json',
            json.dumps(payload).encode('utf-8'),
            content_type='application/json',
        )

        response = self.client.post(
            reverse('reviews:screening-export', kwargs={'pk': review.pk}),
            data={'action': 'upload', 'json_file': upload},
        )

        paper.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(paper.ta_decision, Paper.TADecision.MANUAL_FLAG)
        self.assertEqual(paper.ta_confidence, 0.9)
        self.assertEqual(
            paper.ta_reason,
            'RQ Tag: RQ2 | Reason: Does not directly address motivations or job satisfaction determinants | Criterion: Does not address RQ1 or RQ2 directly',
        )

    def test_upload_json_fuzzy_matches_title_at_95_percent(self):
        review = Review.objects.create(title='Upload Decisions Fuzzy', objectives='obj')
        paper = Paper.objects.create(
            review=review,
            title='Algorithmic precarity and metric power: Managing the affective measures and customers in the gig economy',
            abstract='Abs text',
            ta_decision=Paper.TADecision.EXCLUDED,
            ta_confidence=0.2,
            ta_reason='Old reason',
        )

        payload = [
            {
                'Title': 'Algorithmic precarity and metric power Managing the affective measures and customers in the gig economy',
                'decision': 'flagged',
                'rq_tag': 'RQ2',
                'confidence': 0.67,
                'reason': 'Indirect linkage to satisfaction determinants.',
                'criterion': 'Primary focus is metric governance.',
            }
        ]
        upload = SimpleUploadedFile(
            'updates.json',
            json.dumps(payload).encode('utf-8'),
            content_type='application/json',
        )

        response = self.client.post(
            reverse('reviews:screening-export', kwargs={'pk': review.pk}),
            data={'action': 'upload', 'json_file': upload},
            follow=True,
        )

        paper.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(paper.ta_decision, Paper.TADecision.FLAGGED)
        self.assertEqual(paper.ta_confidence, 0.67)
        self.assertIn('Fuzzy matched (&gt;=95%): 1', response.content.decode('utf-8'))


class ScreeningDecisionBulkUpdateTests(TestCase):
    def test_bulk_update_applies_row_decisions(self):
        review = Review.objects.create(title='Bulk Decision Review', objectives='obj')
        p1 = Paper.objects.create(review=review, title='Paper 1', abstract='a', ta_decision=Paper.TADecision.FLAGGED, ta_reason='Old')
        p2 = Paper.objects.create(review=review, title='Paper 2', abstract='b', ta_decision=Paper.TADecision.FLAGGED, ta_reason='Old')

        response = self.client.post(
            reverse('reviews:screening-decisions', kwargs={'pk': review.pk}),
            data={
                'action': 'bulk',
                'current_ta_decision': 'all',
                'current_confidence_band': 'all',
                f'decision_{p1.id}': 'included',
                f'note_{p1.id}': 'bulk include',
                f'decision_{p2.id}': 'manual_flag',
                f'note_{p2.id}': 'needs manual check',
            },
        )

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(p1.ta_decision, Paper.TADecision.INCLUDED)
        self.assertEqual(p2.ta_decision, Paper.TADecision.MANUAL_FLAG)

    def test_single_update_reads_row_scoped_fields(self):
        review = Review.objects.create(title='Single Row Decision Review', objectives='obj')
        paper = Paper.objects.create(review=review, title='Paper Single', abstract='a', ta_decision=Paper.TADecision.EXCLUDED)

        response = self.client.post(
            reverse('reviews:screening-decisions', kwargs={'pk': review.pk}),
            data={
                'action': 'single',
                'paper_id': str(paper.id),
                'current_ta_decision': 'all',
                'current_confidence_band': 'all',
                f'decision_{paper.id}': 'included',
                f'note_{paper.id}': 'row scoped input',
            },
        )

        paper.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(paper.ta_decision, Paper.TADecision.INCLUDED)
        self.assertIn('row scoped input', paper.ta_reason)



class FullTextRetrievalServiceTests(TestCase):
    @patch('reviews.services.fulltext_retrieval_service._save_pdf_bytes')
    @patch('reviews.services.fulltext_retrieval_service._try_unpaywall_pdf')
    @patch('reviews.services.fulltext_retrieval_service._try_elsevier_pdf')
    def test_retrieve_pdfs_for_review_updates_source_and_flags(self, mock_elsevier, mock_unpaywall, mock_save):
        from reviews.services.fulltext_retrieval_service import retrieve_pdfs_for_review

        review = Review.objects.create(title='Full Text Retrieval', objectives='obj')
        paper = Paper.objects.create(
            review=review,
            title='Included Paper',
            abstract='A',
            doi='10.1000/example',
            ta_decision=Paper.TADecision.INCLUDED,
        )

        mock_elsevier.return_value = {'ok': True, 'status_code': 200, 'pdf_bytes': b'%PDF-1.4 sample'}
        mock_unpaywall.return_value = {'ok': False, 'status_code': 404, 'error_message': 'not used'}
        mock_save.return_value = f'pdfs/{review.id}/{paper.id}.pdf'

        summary = retrieve_pdfs_for_review(review.id)

        paper.refresh_from_db()
        self.assertEqual(summary['downloaded'], 1)
        self.assertTrue(paper.fulltext_retrieved)
        self.assertEqual(paper.pdf_source, 'elsevier')


class FullTextUploadWindowViewTests(TestCase):
    @patch('reviews.views.retrieve_pdfs_for_review')
    def test_upload_window_actions(self, mock_retrieve):
        review = Review.objects.create(title='Upload Window', objectives='obj')
        paper = Paper.objects.create(
            review=review,
            title='Included Pending',
            abstract='A',
            ta_decision=Paper.TADecision.INCLUDED,
            fulltext_retrieved=False,
        )

        get_response = self.client.get(reverse('reviews:fulltext-upload-window', kwargs={'pk': review.pk}))
        self.assertEqual(get_response.status_code, 200)
        self.assertContains(get_response, 'Included Pending')

        mock_retrieve.return_value = {'targeted': 1, 'downloaded': 0, 'abstract_only': 1}
        auto_response = self.client.post(
            reverse('reviews:fulltext-upload-window', kwargs={'pk': review.pk}),
            data={'action': 'run_auto_retrieval'},
        )
        self.assertEqual(auto_response.status_code, 302)

        pdf_upload = SimpleUploadedFile('paper.pdf', b'%PDF-1.4 test', content_type='application/pdf')
        upload_response = self.client.post(
            reverse('reviews:fulltext-upload-window', kwargs={'pk': review.pk}),
            data={'action': 'upload_pdf', 'paper_id': paper.id, 'pdf_file': pdf_upload},
        )
        self.assertEqual(upload_response.status_code, 302)

        paper.refresh_from_db()
        self.assertTrue(paper.fulltext_retrieved)
        self.assertEqual(paper.pdf_source, 'manual_upload')

        paper.fulltext_retrieved = False
        paper.save(update_fields=['fulltext_retrieved'])

        skip_response = self.client.post(
            reverse('reviews:fulltext-upload-window', kwargs={'pk': review.pk}),
            data={'action': 'skip_abstract_only', 'paper_id': paper.id},
        )
        self.assertEqual(skip_response.status_code, 302)
        paper.refresh_from_db()
        self.assertFalse(paper.fulltext_retrieved)
        self.assertEqual(paper.pdf_source, 'abstract_only')

    def test_download_pending_urls_json_only_includes_included_and_not_retrieved(self):
        review = Review.objects.create(title='Upload Window Export', objectives='obj')
        included_pending = Paper.objects.create(
            review=review,
            title='Included Pending URL',
            abstract='A',
            ta_decision=Paper.TADecision.INCLUDED,
            fulltext_retrieved=False,
            url='https://example.com/paper-1',
        )
        Paper.objects.create(
            review=review,
            title='Included Already Retrieved',
            abstract='B',
            ta_decision=Paper.TADecision.INCLUDED,
            fulltext_retrieved=True,
            url='https://example.com/paper-2',
        )
        Paper.objects.create(
            review=review,
            title='Excluded Pending',
            abstract='C',
            ta_decision=Paper.TADecision.EXCLUDED,
            fulltext_retrieved=False,
            url='https://example.com/paper-3',
        )

        response = self.client.post(
            reverse('reviews:fulltext-upload-window', kwargs={'pk': review.pk}),
            data={'action': 'download_pending_json'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertIn(
            f'attachment; filename=review_{review.id}_pending_fulltext_urls.json',
            response['Content-Disposition'],
        )

        payload = json.loads(response.content.decode('utf-8'))
        self.assertEqual(payload['count'], 1)
        self.assertEqual(payload['papers'][0]['paper_id'], included_pending.id)
        self.assertEqual(payload['papers'][0]['url'], 'https://example.com/paper-1')
class FullTextRetrievalMonitorViewTests(TestCase):
    @patch('reviews.views.threading.Thread')
    def test_start_monitor_sets_running_status(self, mock_thread):
        review = Review.objects.create(title='Retrieval Monitor', objectives='obj')
        response = self.client.post(reverse('reviews:fulltext-retrieval-monitor', kwargs={'pk': review.pk}))

        review.refresh_from_db()
        stage = (review.stage_progress or {}).get('phase_10_fulltext', {})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(stage.get('status'), 'running')
        self.assertTrue(mock_thread.called)

    def test_status_endpoint_returns_json_snapshot(self):
        review = Review.objects.create(
            title='Retrieval Status',
            objectives='obj',
            stage_progress={'phase_10_fulltext': {'status': 'running', 'processed': 3, 'downloaded': 2, 'failed': 1}},
        )

        response = self.client.get(reverse('reviews:fulltext-retrieval-status', kwargs={'pk': review.pk}))

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode('utf-8'))
        self.assertEqual(payload['status'], 'running')
        self.assertEqual(payload['processed'], 3)

    @patch('reviews.views.threading.Thread')
    def test_retry_uses_remaining_papers_from_previous_run(self, mock_thread):
        review = Review.objects.create(
            title='Retrieval Retry',
            objectives='obj',
            stage_progress={
                'phase_10_fulltext': {
                    'status': 'error',
                    'remaining_paper_ids': [11, 12, 13],
                }
            },
        )

        response = self.client.post(
            reverse('reviews:fulltext-retrieval-monitor', kwargs={'pk': review.pk}),
            data={'action': 'retry'},
        )

        review.refresh_from_db()
        stage = (review.stage_progress or {}).get('phase_10_fulltext', {})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(stage.get('status'), 'running')
        self.assertEqual(stage.get('run_type'), 'retry_remaining')
        self.assertEqual(stage.get('remaining_paper_ids'), [11, 12, 13])
        self.assertEqual(stage.get('targeted'), 3)
        self.assertTrue(mock_thread.called)
    def test_stop_monitor_sets_stop_requested_flag(self):
        review = Review.objects.create(
            title='Retrieval Stop',
            objectives='obj',
            stage_progress={'phase_10_fulltext': {'status': 'running', 'stop_requested': False}},
        )

        response = self.client.post(
            reverse('reviews:fulltext-retrieval-monitor', kwargs={'pk': review.pk}),
            data={'action': 'stop'},
        )

        review.refresh_from_db()
        stage = (review.stage_progress or {}).get('phase_10_fulltext', {})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(stage.get('status'), 'stopping')
        self.assertTrue(stage.get('stop_requested'))
class ElsevierPDFDebugViewTests(TestCase):
    @patch('reviews.views_batch_debug.threading.Thread')
    def test_elsevier_debug_start_sets_running_stage(self, mock_thread):
        review = Review.objects.create(title='Elsevier Debug Start', objectives='obj')

        response = self.client.post(reverse('reviews:elsevier-pdf-debug-start', kwargs={'pk': review.pk}))
        payload = json.loads(response.content.decode('utf-8'))

        review.refresh_from_db()
        stage = (review.stage_progress or {}).get('phase_12_elsevier_debug', {})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['ok'])
        self.assertEqual(stage.get('status'), 'running')
        self.assertTrue(mock_thread.called)

    def test_elsevier_debug_status_endpoint(self):
        review = Review.objects.create(
            title='Elsevier Debug Status',
            objectives='obj',
            stage_progress={
                'phase_12_elsevier_debug': {
                    'status': 'running',
                    'targeted': 5,
                    'processed': 2,
                    'downloaded': 1,
                    'failed': 1,
                }
            },
        )

        response = self.client.get(reverse('reviews:elsevier-pdf-debug-status', kwargs={'pk': review.pk}))
        payload = json.loads(response.content.decode('utf-8'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['ok'])
        self.assertEqual(payload['snapshot']['status'], 'running')
        self.assertEqual(payload['snapshot']['processed'], 2)

    def test_elsevier_debug_stop_sets_stop_requested(self):
        review = Review.objects.create(
            title='Elsevier Debug Stop',
            objectives='obj',
            stage_progress={'phase_12_elsevier_debug': {'status': 'running', 'stop_requested': False}},
        )

        response = self.client.post(reverse('reviews:elsevier-pdf-debug-stop', kwargs={'pk': review.pk}))
        payload = json.loads(response.content.decode('utf-8'))

        review.refresh_from_db()
        stage = (review.stage_progress or {}).get('phase_12_elsevier_debug', {})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['ok'])
        self.assertTrue(stage.get('stop_requested'))
        self.assertEqual(stage.get('status'), 'stopping')





