## Complete Chronological Walkthrough — Every Step From Start to Finish

---

## PHASE 0 — User Arrives at the App

User opens the web app in their browser. They see a clean dashboard showing their previous reviews (empty on first visit) and a **New Review** button.

They click it.

---

## PHASE 1 — User Fills the Intake Form

One form, four sections. This is the only time the user provides input before the pipeline starts (except for the confirmation windows later).

**Section 1 — Research Details**
```
Review Title:     "Consumer Vulnerability in Digital Markets"
Objectives:       "This review aims to understand how digital market 
                   environments create and amplify consumer vulnerability, 
                   what factors mediate vulnerability outcomes, and what 
                   interventions have been shown to reduce harm..."
```

**Section 2 — Criteria**
```
Inclusion:     "Peer-reviewed empirical studies, human subjects, 
                published 2010-2024, English language"
Exclusion:     "Theoretical papers without empirical component, 
                B2B contexts, non-consumer populations"
Target papers: 50
Date range:    2010 - 2024
```

**Section 3 — PICO Framework**
```
Population:    "Adult consumers engaging with digital marketplaces"
Intervention:  "Digital market exposure, platform design features"
Comparison:    "Traditional retail environments or no intervention"
Outcomes:      "Consumer vulnerability scores, harm outcomes, 
                protective behaviors"
```


**Section 4 — Submit**

User clicks Submit. Django creates a `Review` record in PostgreSQL with `status='queued'`. The form data is stored exactly as entered — this is the verbatim source for the Methods section later.

---

## PHASE 2 — AI Formalises Research Questions, PICO Framework, and Criteria


Immediately after form submission, before the pipeline starts, one Gemini Pro call reads the objectives and PICO framework, inclusion and exclusion criteria,and generates precise Research Questions. Also if the PICO framework is empty it will generate one based on the research objectives. it will generate a exlucsion and inclusion list based improving upon what user has provided. 

Here’s a refined and internally consistent version of your **Phase 2 specification**, with clearer structure, stronger logic, and aligned downstream behavior. I’ve also tightened wording, removed ambiguity, and made the outputs more implementation-ready.

---

## **PHASE 2 — AI Formalises Research Questions, PICO Framework, and Criteria**

Immediately after form submission—and **before the pipeline starts**—a single **Gemini Pro call** processes the user input to:

1. Generate precise **Research Questions (RQs)**
2. Validate or construct the **PICO framework**
3. Refine and expand **Inclusion and Exclusion Criteria**

This phase acts as a **standardisation and locking step** to ensure all downstream stages operate on consistent, well-defined research parameters.

---

## **What Gemini Receives**

```
Objectives: [user's text]
"
Population: for example "consumers in digital marketplaces" [user's text]
Intervention: for example "digital market exposure" [user's text]
Comparison: for example "traditional retail" [user's text]
Outcomes: for example "vulnerability scores, harm, protective behaviors" [user's text]

Inclusion Criteria: [optional user input]
Exclusion Criteria: [optional user input]
```

---

## **Gemini Responsibilities**

### 1. **Research Question Generation**

* Generate **2–4 high-quality research questions**
* Ensure:

  * Direct alignment with objectives
  * Clear categorisation:

    * `comparative`
    * `causal`
    * `descriptive` (or `exploratory`)
  * No redundancy
  * Measurable or investigable framing

---

### 2. **PICO Framework Handling**

* If **any PICO field is missing or weak**:

  * Infer and complete it using the objectives
* If provided:

  * Refine for clarity, specificity, and academic rigor
* Output must always include a **fully defined PICO**

---

### 3. **Inclusion & Exclusion Criteria Refinement**

* Improve user-provided criteria by:

  * Removing ambiguity
  * Adding standard SLR constraints (e.g., language, study type, timeframe if inferable)
* If absent:

  * Generate a **reasonable default set** based on the domain

---

## **What Gemini Returns**

```json
{
  "research_questions": [
    {
      "rq": "To what extent do digital marketplace environments amplify consumer vulnerability compared to traditional retail contexts?",
      "type": "comparative"
    },
    {
      "rq": "What individual-level factors mediate the relationship between digital market exposure and consumer vulnerability outcomes?",
      "type": "causal"
    },
    {
      "rq": "Which intervention strategies have demonstrated effectiveness in reducing consumer vulnerability in digital market settings?",
      "type": "descriptive"
    }
  ],
  "pico": {
    "population": "Adult consumers engaging in digital marketplaces",
    "intervention": "Exposure to digital marketplace environments (e.g., e-commerce platforms, online advertising)",
    "comparison": "Traditional retail environments",
    "outcomes": "Consumer vulnerability metrics, harm indicators, and protective behaviors"
  },
  "inclusion_criteria": [
    "Studies involving adult consumers (18+)",
    "Research focused on digital or online marketplace contexts",
    "Empirical studies reporting measurable outcomes related to consumer vulnerability",
    "Peer-reviewed articles or high-quality reports",
    "Published in English"
  ],
  "exclusion_criteria": [
    "Studies focusing exclusively on children or adolescents",
    "Non-digital retail contexts without comparison",
    "Opinion pieces, editorials, or non-empirical work",
    "Studies lacking clear outcome measures related to vulnerability"
  ]
}
```

---

## **User Interaction Layer**

After generation, the user is shown a **confirmation interface** containing:

* Editable **Research Questions**
* Editable **PICO framework**
* Editable **Inclusion/Exclusion Criteria**

### User Actions:

* Inline edit allowed for all fields
* Clear labeling of RQ types (non-editable or editable based on design choice)

---

## **Locking Mechanism**

Once the user clicks **Confirm**:

* The following fields are **persisted and locked**:

  * `review.research_questions`
  * `review.pico`
  * `review.inclusion_criteria`
  * `review.exclusion_criteria`

* System state updates:

  ```python
  review.status = "running"
  ```

* Pipeline trigger:

  ```python
  run_slr_pipeline.delay(review_id)
  ```

---

## PHASE 3 — AI Generates Scopus Queries

Celery picks up the task. First pipeline stage.

One Gemini Pro call takes the objectives, inclusion/exclusion criteria, pico framework, criteria etc. and date range and generates 5 distinct Boolean Scopus queries.

**What each query targets: example is given below**
```
Query 1 — Core terms:
TITLE-ABS-KEY("consumer vulnerability" AND 
("digital market*" OR "e-commerce" OR "online retail"))

Query 2 — Synonyms:
TITLE-ABS-KEY(("vulnerable consumer*" OR "consumer disadvantage" 
OR "consumer harm") AND ("digital platform*" OR "marketplace"))

Query 3 — Related constructs:
TITLE-ABS-KEY(("digital literacy" OR "online trust") AND 
"consumer vulnerability" AND ("protection" OR "intervention"))

Query 4 — Population-specific:
TITLE-ABS-KEY("consumer vulnerability" AND 
("elderly" OR "low income" OR "cognitive vulnerability"))

Query 5 — Outcome-specific:
TITLE-ABS-KEY(("deceptive design" OR "dark pattern*" OR 
"pricing manipulation") AND "consumer" AND "vulnerability")
```

Five `SearchQuery` records created in DB, each storing the exact query string. These appear verbatim in Appendix A of the final document.

---

## PHASE 4 — Manul Scopus Search by user

each query is shown to the user. User will then maually search this, download the results. For each query it will upload the downloaded RIS file against each query via the RIS results upload form. 


## PHASE 5 — Parse the RIS data and save it in the database

All of this is stored as a `Paper` record. 

lets say roughly **800 Paper records** exist in the database. Many will be duplicates across queries.


## PHASE 6 — Deduplication

The same paper appearing in multiple query results is common. Two rules applied in sequence across all 800 papers, processed in order of database ID:

**Rule 1 — Exact DOI match:**
Paper A has DOI `10.1016/j.jretai.2019.03.001`. Paper B has the same DOI. Paper B gets `final_decision='excluded'`, `exclusion_criterion='Duplicate — exact DOI match'`.

**Rule 2 — Fuzzy title similarity:**
Title similarity > 92% using rapidfuzz `token_sort_ratio` AND year within 1 year of each other → later paper excluded.

After deduplication:
```
800 retrieved → 600 unique papers
200 marked excluded (Duplicate)
exclude the papers which has no abstract

```

PRISMA count locked: `after_dedup = 600`.

---

## PHASE 7 — T/A Batch Screening Submitted

All 600 papers with usable abstracts (excluding the ~one's flagged for no abstract) are compiled into a batch job for Gemini Flash.

**How the batch works:**

The system builds a JSONL file where each line is one paper's screening request:
```json
{"custom_id": "paper_id_1234", "model": "gemini-2.5-flash", 
 "prompt": "Inclusion: peer-reviewed, empirical, human subjects...\nExclusion: theoretical, B2B...\nTitle: Consumer Vulnerability in...\nAbstract: This study examines..."}
```

This JSONL file is uploaded to Gemini's Files API in one HTTP call. Gemini processes all 585 papers asynchronously within 24 hours at 50% of standard pricing.

The `submitted_at` timestamp is stored in `review.stage_progress['screening']`. If the batch has not completed within 36 hours, a sequential fallback kicks in automatically.

Review status: still `running`. Current stage: `screening_batch_pending`.

---

## PHASE 8 — Celery Beat Polls for Screening Results

Every 5 minutes, the `poll_all` Celery beat task checks all reviews in `screening_batch_pending` status. It calls `poll_batch(file_name)` which asks Gemini's Files API for the batch status.

```
First few polls: state = PROCESSING → return None, wait
Eventually:      state = ACTIVE → parse response JSONL
```

When results arrive, `process_screening_results()` runs for every paper:

```python
for each result:
    data = json.loads(result['text'])
    # data = {"decision": "included", "confidence": 0.84, 
    #          "reason": "...", "criterion_failed": null}
    
    paper.ta_decision = data['decision']
    paper.ta_confidence = data['confidence']
    paper.ta_reason = data['reason']
    
    if confidence < 0.72:
        paper.title_abstract_decision = 'flagged'
        paper.screening_conflict = True
    else:
        paper.title_abstract_decision = data['decision']
```

**Routing outcomes:**
```
Confidence ≥ 0.92 + included  → ~50 papers  (auto-include later)
Confidence 0.72–0.91 + included → ~100 papers (needs fulltext screen)
Confidence 0.72–0.91 + excluded → ~400 papers (excluded, reason stored)
Confidence < 0.72              → ~35 papers  (flagged for user)
```

Progress page updates in real time via SSE stream. Users watching the progress page see the screening stage complete and stats update.

---

## PHASE 9 — User Resolves Flagged Papers

The ~35 flagged papers appear in the progress UI as a table. User sees each paper's title, the AI's decision, the confidence score, and the reason for uncertainty:

```
Smith & Jones (2021) — Digital exclusion and elderly consumers
AI Decision: Excluded (62% confidence)
Reason: "Abstract describes study population but does not 
         clearly state digital market context"
                                          [Include]  [Exclude]
```

User clicks Include or Exclude for each. Their decision is recorded.

---

## PHASE 10 — PDF Retrieval Waterfall

`retrieve_pdfs_all` task runs for all papers with `title_abstract_decision = 'included'`. Roughly 120-150 papers.

**For each paper, six sources are tried in order:**

```
1. Unpaywall API
   GET https://api.unpaywall.org/v2/{doi}?email=...
   → Returns best open-access PDF URL if available
   → Covers ~50% of academic papers
   
2. PubMed Central
   → Search NCBI with DOI → get PMC ID → construct full text URL
   → Covers biomedical and health policy papers

3. Semantic Scholar
   GET https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}
   → Returns openAccessPdf URL if available
   → Cross-domain coverage

4. arXiv
   → Check if title/keywords suggest preprint
   → Search arXiv API
   → Covers CS, economics, some social science preprints

5. Europe PMC
   GET https://www.ebi.ac.uk/europepmc/webservices/rest/search
   → European life/social sciences coverage

6. Abstract fallback
   → If all five fail: pdf_source = 'abstract_only'
   → paper.pdf_text = paper.abstract
   → fulltext_retrieved = False
   → Continues through pipeline with abstract text only
```

**On successful download:**
- PDF saved to `media/pdfs/{review_id}/{scopus_id}.pdf`
- Content-type checked — must be `application/pdf` before saving
- `paper.fulltext_retrieved = True`
- `paper.pdf_source = 'unpaywall'` (or whichever source)

After retrieval: roughly 110 PDFs downloaded, 40 abstract-only.

---



## PHASE 12 — Upload Window Opens

here we allow the user to upload the remaining pdf that was not autometiclly downloaded. 
Review status changes to `upload_window`. Pipeline pauses.

User navigates to the upload page and sees **only the papers that passed screening but have no PDF** — typically 20–50 papers. Not all 600. Not all 150 included. Just the ones that need attention.

```
Papers Needing Full Text (31 remaining)

─────────────────────────────────────────────────────────────
Baker et al. (2019)
Consumer Vulnerability in Digital Markets
Journal of Consumer Research  |  Cited 847 times
                                          [Upload PDF] [Skip]
─────────────────────────────────────────────────────────────
Smith & Jones (2021)  
Digital Exclusion and Elderly Consumers
Journal of Marketing  |  Cited 312 times
                                          [Upload PDF] [Skip]
─────────────────────────────────────────────────────────────
```

**On Upload PDF click:**
```
1. OS file picker opens
2. User selects PDF from their university library download
3. POST /reviews/papers/{paper_id}/upload/
4. File saved: media/pdfs/{review_id}/user_{scopus_id}.pdf



**On Skip click:**
```
paper.pdf_source = 'abstract_only'
paper.pdf_text = paper.abstract
→ Row shows amber "Abstract only" badge
```




## PHASE 11 — GROBID Parses All PDFs

`grobid_parse_all` Celery task runs for all papers with downloaded+ user's uploaded PDFs.

**For each paper:**
```
POST media/pdfs/{review_id}/{scopus_id}.pdf 
     → http://localhost:8070/api/processFulltextDocument

GROBID returns TEI XML containing identified sections
```

The `_parse_tei_xml()` function processes the XML using fuzzy section classification. Social science papers use varied headings — "Research Methodology", "Empirical Findings", "Study Design" — all mapped to canonical section types via the keyword dict:

```python
SECTION_KEYWORDS = {
    'methods': ['method', 'methodology', 'research design', 
                'study design', 'data collection', 'participants'],
    'results': ['result', 'finding', 'outcome', 'analysis', 
                'empirical', 'observation'],
    ...
}
```

**For each paper, stored:**
```python
paper.grobid_sections = {
    'abstract':     'clean text...',
    'methods':      'clean text...',
    'results':      'clean text...',
    'discussion':   'clean text...',
    'full_text':    'all body text...'
}

paper.pdf_text = abstract + methods + results + discussion
                 (up to 32,000 chars, stripped of references/headers)
paper.grobid_parsed = True
```

**Edge case — scanned PDF:**
If GROBID returns < 200 chars of text (image-based PDF with no text layer):
```python
paper.pdf_text = paper.abstract    # fallback
paper.pdf_source = 'ocr_required'  # flagged in characteristics table
paper.grobid_parsed = False
```

**GROBID unavailable:**
`is_healthy()` check returns False → give user notice to check and debug the grobid

**Abstract-only papers:**
```python
paper.pdf_text = paper.abstract
```
No GROBID call needed. These are flagged as "Abstract only" in the characteristics table.

---


## PHASE 13 — Full-Text Screening

`screen_fulltext_all` runs. Before dispatching parallel tasks, `prepare_fulltext_screening()` handles two things:

**Auto-included papers (ta_confidence ≥ 0.92):**
```python
for paper in auto_included_papers:  # ~50 papers
    paper.fulltext_decision = 'included'
    paper.final_decision = 'included'
    paper.selection_rationale = (
        f"Auto-confirmed at {paper.ta_confidence:.0%} confidence. "
        f"{paper.ta_reason}"
    )
    paper.save()
```
These never go through fulltext screening. They are done.

**Redis counter set:**
```python
cache.set(f'ft_remaining_{review_id}', 90)  # papers to screen
```

**Parallel screening tasks dispatched:**
One `screen_fulltext_task` per non-auto paper (~90 tasks), all queued on the screening Celery worker.

**For each paper, the fulltext screening call:**
```
Gemini Pro reads:
  - Review objectives
  - Inclusion + exclusion criteria
  - GROBID-extracted text (up to 10,000 chars of methods+results+discussion)
  - Note if abstract-only

Returns:
  {
    "decision": "included",
    "confidence": 0.88,
    "reason": "Qualitative study examining elderly consumer responses...",
    "study_type": "qualitative",
    "criterion_failed": null,
    "selection_rationale": "This paper addresses RQ2 by providing 
      qualitative evidence of how platform design features 
      systematically disadvantage elderly consumers. Its 
      phenomenological approach complements the quantitative 
      studies already included..."
  }
```

Note: `selection_rationale` is generated here, inside this call, at no extra cost. No separate task.

**After each task completes:**
```python
paper.fulltext_decision = data['decision']
paper.fulltext_confidence = data['confidence']
paper.final_decision = data['decision']
paper.selection_rationale = data['selection_rationale'] if included else ''
if data['confidence'] < 0.65:
    paper.screening_conflict = True  # flag for user

# Decrement counter
remaining = cache.decr(f'ft_remaining_{review_id}')
if remaining == 0:
    task_enter_paper_confirmation.delay(review_id)
```

When the last task decrements the counter to zero, `task_enter_paper_confirmation` fires exactly once.

**After all fulltext screening:**
```
~50 auto-included
~60 passed fulltext
~30 excluded at fulltext
~5 flagged (confidence < 0.65) → user resolves these in UI

Total included so far: ~110 papers
```

---

## PHASE 14 — Paper Confirmation Window

`task_enter_paper_confirmation` fires:
```python
review.status = 'paper_confirmation'
review.confirmation_deadline = timezone.now() + timedelta(hours=48)
```

Pipeline pauses again.

User navigates to the confirmation page. Sees all ~110 included papers sorted by citation count:

```
Review Your 110 Selected Papers Before Analysis Begins

─────────────────────────────────────────────────────────────────────
☑ Baker et al. (2019)
  Cross-sectional  ● Full text  ● GROBID parsed
  Consumer Vulnerability in Digital Markets
  Journal of Consumer Research  |  Citations: 847

  "This paper directly addresses RQ1 and RQ3 by providing 
   large-scale quantitative evidence of vulnerability 
   determinants in e-commerce contexts. Its cross-national 
   sample (N=2,847) strengthens generalisability."
                                               [Exclude ▼]

─────────────────────────────────────────────────────────────────────
☑ Smith (2020)
  Qualitative  ● Full text  ⚡ Auto-confirmed
  Digital Exclusion and Elderly Consumers
  Journal of Marketing  |  Citations: 312

  "Auto-confirmed at 94% confidence. Paper explicitly 
   examines digital literacy as a mediating factor in 
   consumer vulnerability outcomes among elderly populations."
                                               [Exclude ▼]
─────────────────────────────────────────────────────────────────────
```

⚡ badge on auto-confirmed papers — user knows the rationale came from abstract screening not full-text reading.

**Exclude dropdown options:**
```
Out of scope
Methodology concerns
Quality concerns
Access issue (abstract only, uncertain)
Duplicate findings (already covered by another paper)
Other
```

**Excluded papers** stay visible, grayed out, with Undo button. User can change their mind.

**Warning** if remaining < 10 papers or if > 20% excluded.

**Confirm & Start Analysis** button:
```
Check: confirmed_count >= 5?
   NO  → Error: "Need at least 5 papers for synthesis"
   YES → confirmed.update(user_confirmed=True)
         review.status = 'running'
         submit_extraction_batch.delay(review_id)
```

**48-hour timeout:** `poll_all` detects expired `confirmation_deadline` → auto-confirms all remaining included papers → triggers extraction.

Final corpus after user confirmation: **~55–60 papers**.

---

## PHASE 15 — Data Extraction + Quality Assessment Batch Submitted

`submit_extraction_batch` builds a Gemini Pro batch job for all confirmed papers.

**For each paper, one prompt:**
```
Read this paper and return JSON with two keys: extraction and quality.

extraction: {
  study_design, population, intervention, comparison,
  outcomes [{name, measure, result, direction, p_value, effect_size}],
  sample_size, study_country, setting, key_findings (3 sentences),
  limitations, funding, year
}

quality: {
  study_type, total_score (0-10),
  dim_objectives, dim_design, dim_data, dim_analysis, dim_bias (0-2 each),
  risk_of_bias (low|moderate|high),
  strengths [...], weaknesses [...]
}

PAPER TEXT:
{paper.pdf_text[:32000]}  ← GROBID-extracted, clean, section-targeted
```

32,000 characters covers the full methods + results + discussion of virtually any social science paper. This is 8× the old 4,000-char limit — the full paper content is now available to Gemini for extraction.

Batch uploaded to Gemini Files API. `submitted_at` stored. `review.current_stage = 'extraction_batch_pending'`.

---

## PHASE 16 — Celery Beat Polls for Extraction Results

Same mechanism as screening polling. Every 5 minutes `poll_all` checks.

When results arrive, `process_extraction_results()` runs:

```python
for each result:
    data = json.loads(result['text'])  # retry with correction if invalid JSON
    
    DataExtraction.objects.update_or_create(
        paper=paper,
        defaults={
            'study_design': data['extraction']['study_design'],
            'population':   data['extraction']['population'],
            'outcomes':     data['extraction']['outcomes'],
            'key_findings': data['extraction']['key_findings'],
            ...
            'raw_json':     data['extraction']
        }
    )
    
    QualityAssessment.objects.update_or_create(
        paper=paper,
        defaults={
            'total_score':    data['quality']['total_score'],
            'dim_objectives': data['quality']['dim_objectives'],
            'risk_of_bias':   data['quality']['risk_of_bias'],
            ...
        }
    )
```

After all 55 papers processed: 55 `DataExtraction` records, 55 `QualityAssessment` records in DB. `run_post_extraction.delay(review_id)` fires.

---

## PHASE 17 — Bibliometric Analysis (Pure Computation, No AI)

`bibliometric_analysis` task runs entirely on metadata. No API calls.

**Co-occurrence graph:**
```python
# Build graph from paper keywords
for paper in all_included_papers:
    for pair in combinations(paper.keywords, 2):
        keyword_pairs[sorted_pair] += 1

# Add edges above threshold
for (kw1, kw2), weight in keyword_pairs.items():
    if weight >= 2:
        G.add_edge(kw1, kw2, weight=weight)

# Louvain community detection
partition = community_louvain.best_partition(G)
# partition = {keyword: cluster_id, ...}
```

**Keyword sparsity check:**
```python
if G.nodes < 8:
    # Fall back to title noun phrase extraction
    G, partition = _build_title_ngram_graph(papers)
```

**Other computations:**
```python
by_year    = Counter(p.year for p in papers)
by_country = Counter(p.author_country for p in papers)
by_journal = Counter(p.journal for p in papers)

thematic_map_data = compute_thematic_map_data(G, partition)
# [{label, centrality, density, size, nodes}]

sankey_data = compute_sankey_data(papers, review)
# None if year_span < 10 or < 15 papers per period
```

---

## PHASE 18 — Phase 1 Graphs Generated (12 Graphs) [for now we will skip this phase] 

`generate_phase1_graphs` creates 12 graphs as 300 DPI PNGs. These are the graphs that do NOT need theme data.

```
1.  Publication trend by year     → matplotlib bar chart
2.  Publications by country       → plotly choropleth → kaleido PNG
3.  Publications by journal       → matplotlib horizontal bar (if ≥3 journals with ≥3 papers)
4.  Keyword co-occurrence network → pyvis HTML (interactive) + static PNG
5.  Thematic map 2×2              → matplotlib scatter (centrality vs density)
6.  Thematic evolution Sankey     → plotly alluvial (if year_span ≥ 10)
7.  PRISMA 2020 flow diagram      → matplotlib FancyBboxPatch, 8 boxes
8.  Study design donut            → matplotlib donut chart
9.  Risk of bias stacked bar      → matplotlib stacked bar (per CASP dimension)
10. Findings by study design      → matplotlib grouped bar (subgroup)
11. Findings by year              → matplotlib line (if ≥3 years with ≥3 papers each)
12. [theme frequency reserved]    → phase 2
13. [evidence heatmap reserved]   → phase 2
```

Each graph saved to `media/graphs/{review_id}/{name}.png`. Each creates a `GraphFile` record with `phase=1`.

PRISMA flow diagram includes all screening stages including the user_excluded box — this is populated from `review.stage_progress['user_excluded_count']`.


---

## PHASE 19 — Consistency Scaffold Assembled and Locked

`build_scaffold` assembles everything into one JSON object from pure DB queries.

```python
scaffold = {
    'prisma_counts': {
        'scopus_retrieved':  847,  # from DB count
        'after_dedup':       634,
        'passed_ta':         150,
        'pdfs_retrieved':    115,
        'abstract_only':     35,
        'passed_fulltext':   110,
        'user_excluded':     8,     # from confirmation window
        'final_included':    55,    # user-confirmed papers only
    },
    'canonical_terms': {            # one Gemini Pro call identifies primary term
        'primary': 'consumer vulnerability',
        'banned':  ['consumer vulnerabilities', 'consumer fragility']
    },
    'research_questions': [         # exact text user confirmed
        'To what extent do digital marketplace...',
        'What individual-level factors...',
        'Which intervention strategies...'
    ],
    'paper_registry': [             # 55 entries
        {
            'scopus_id': 'SCOPUS:12345678',
            'short_ref': 'Baker et al. (2019)',
            'year': 2019,
            'title': 'Consumer Vulnerability in Digital...',
            'journal': 'Journal of Consumer Research',
            'doi': '10.1016/j.jcr.2019...'
        },
        ...
    ],
    'quality_summary': {
        'mean': 7.2,
        'low_risk': 22,
        'moderate_risk': 28,
        'high_risk': 5
    },
    'subgroup_data': {
        'by_design':  {'cross-sectional': 18, 'qualitative': 14, ...},
        'by_country': {'United Kingdom': 12, 'United States': 10, ...},
        'by_year':    {2019: 4, 2020: 7, 2021: 9, ...}
    },
    'pico': {
        'population': 'Adult consumers in digital marketplaces',
        'intervention': 'Digital market exposure...',
        ...
    },
    'theme_names':     [],   # populated by synthesis
    'evidence_grades': {},   # populated by synthesis
    'rq_answers':      {},   # populated after writing
    # NOTE: NO graph_paths — document builder queries GraphFile directly
}

review.scaffold = scaffold
review.scaffold_locked = True
review.save()
```

**Scaffold locked.** Nothing can modify it except `theme_names` and `evidence_grades` which synthesis writes to it as a controlled update. Graph paths are never stored here — document builder queries `GraphFile` DB table directly.

---

## PHASE 20 — Evidence Matrix Identifies Themes

One Gemini Pro call receives all 55 papers' extraction data as a JSON array.

```
Input: all 55 DataExtraction records serialised as JSON
       + review objectives
       + research questions

Output: 6 themes identified
[
  {"theme_name": "Digital Literacy as Vulnerability Mediator",
   "paper_ids": [31 scopus IDs],
   "pct": 56,
   "designs": ["cross-sectional", "qualitative", "RCT"],
   "evidence_grade": "Emerging"},
   
  {"theme_name": "Platform Design and Exploitation Mechanisms",
   "paper_ids": [38 scopus IDs],
   "pct": 69,
   "designs": ["RCT", "survey", "qualitative"],
   "evidence_grade": "Established"},
   
  {"theme_name": "Regulatory Frameworks and Enforcement",
   "paper_ids": [8 scopus IDs],
   "pct": 15,
   "evidence_grade": "Insufficient"},
   ...
]
```

Six `ThemeSynthesis` records created. `ThemeSynthesis.papers` ManyToMany set for each theme. Theme names and evidence grades written to scaffold (controlled update).

---

## PHASE 21 — Dialectical Synthesis Per Theme

For each of the 6 themes, sequential Gemini Pro calls construct the synthesis.

**Themes graded Established, Emerging, or Contested → 3 passes:**

**Pass 1 — Advocate**
```
Input:  scaffold preamble + theme name + evidence grade
        + all extraction data from papers in this theme

Output: 200-300 words
"Growing evidence suggests digital literacy functions as a 
 significant mediating variable... Smith & Jones (2021) found..."
```

**Pass 2 — Critic**
```
Input:  scaffold preamble + advocate text + same extractions

Output: 150-250 words
"The advocate position overstates consistency. While Smith & Jones 
 (2021) and Chen et al. (2022) show convergent results, both 
 operationalise digital literacy differently..."
```

**Pass 3 — Reconciler**
```
Input:  scaffold preamble + advocate + critic + evidence grade

Output: 300-400 words of publication-ready prose
"Digital literacy emerges as a theoretically significant mediating 
 variable, though the evidence warrants qualification on 
 methodological grounds. Convergent findings from cross-sectional 
 studies (Smith & Jones, 2021; Chen et al., 2022; Baker, 2020) 
 suggest that low digital literacy is associated with elevated 
 vulnerability scores, consistent with the cognitive capacity 
 framework (Williams, 2019). However, the sole RCT in this corpus 
 (Williams et al., 2020) found the effect non-significant when 
 controlling for socioeconomic status..."
```

**Themes graded Insufficient (≤2 papers) → 1 pass:**
```
Output: 120-180 words honest acknowledgement
"Preliminary evidence suggests a connection between regulatory 
 frameworks and consumer vulnerability, though the current 
 literature is insufficient to draw substantive conclusions.
 Only two studies address this directly... This represents 
 a significant research gap..."
```

All `ThemeSynthesis.reconciled_text` fields populated and saved.

---

## PHASE 22 — Phase 2 Graphs Generated [skip this phase, just save a csv file for later generation]

At the end of `run_full_synthesis`, immediately after all ThemeSynthesis records exist:

`generate_phase2_graphs(review, themes)` runs:

**Theme frequency bar chart:**
```python
# Horizontal bar: one bar per theme
# Bar length = paper_count
# Sorted by paper count descending
# Colour-coded by evidence grade
```

**Evidence strength heatmap:**
```python
# Grid: rows = papers, columns = themes
# Cell filled if paper in theme.papers.all()
# Built from ThemeSynthesis.papers ManyToMany
# NOT from DataExtraction (which has no themes_addressed field)
```

Two `GraphFile` records created with `phase=2`.

---

## PHASE 23 — Document Written Section by Section

`write_all_sections` runs 15 sequential Gemini Pro calls. Each call receives the scaffold preamble plus all previously written sections with clear labels.

**The scaffold preamble attached to every call:**
```
=== CONSISTENCY RULES — MANDATORY ===

CANONICAL TERM: Always use 'consumer vulnerability'. 
Never use: consumer vulnerabilities, consumer fragility.

LOCKED COUNTS (use exactly these numbers):
  Total retrieved: 847
  Final included: 55
  User excluded: 8
  ...

LOCKED THEME NAMES (use exactly as written):
  1. Digital Literacy as Vulnerability Mediator
  2. Platform Design and Exploitation Mechanisms
  3. Regulatory Frameworks and Enforcement
  ...

EVIDENCE LANGUAGE:
  Established: 'demonstrates', 'establishes', 'consistently shows'
  Emerging:    'suggests', 'indicates', 'growing evidence shows'
  Contested:   'remains debated', 'evidence is mixed'
  Insufficient:'preliminary evidence suggests' — always flag as gap

CITATIONS: Only cite papers in this registry:
  Baker et al. (2019) — Consumer Vulnerability in Digital...
  Smith & Jones (2021) — Digital Exclusion and Elderly...
  [53 more entries]

RESEARCH QUESTIONS:
  RQ1: To what extent do digital marketplace environments...
  RQ2: What individual-level factors mediate...
  RQ3: Which intervention strategies...

=== END CONSISTENCY RULES ===
```

**Section 1 — Introduction:**
```
Receives: scaffold preamble (registry omitted — no citations needed)
Writes:   Background on consumer vulnerability research
          Why this SLR is needed now
          Statement of objectives
          The three locked RQs stated explicitly
Output:   ~700 words
```

**Sections 2.1–2.4 — Methods:**
```
Receives: preamble + Introduction (already written)
2.1 Search Strategy: describes 5 queries, Scopus, dates, language
    Auto-formatted query list from DB — not AI-written
2.2 Selection Criteria: PICO table + inclusion/exclusion criteria
    Verbatim from user input — not AI-written
2.3 Study Selection: describes dual-stage screening, confidence 
    threshold, upload window, paper confirmation process
    Notes: N papers excluded by reviewer after rationale review
2.4 Data Extraction: describes merged extraction framework,
    CASP-adapted quality assessment, 0-10 scale
Output: ~400 words total
```

**Section 3.1 — Results: Study Selection:**
```
Receives: preamble (no registry) + all prior sections
Writes:   PRISMA narrative using locked counts
          "847 records identified via Scopus search across 5 queries.
           After deduplication, 634 unique records remained.
           Following title and abstract screening, 150 records 
           were assessed for eligibility..."
Output:   ~250 words + reference to PRISMA diagram
```

**Section 3.2 — Results: Study Characteristics:**
```
Receives: preamble (WITH registry) + all prior
Writes:   Narrative introducing the characteristics table
          Study design distribution, geographic spread, year range
The characteristics TABLE is auto-built from DataExtraction DB records
          — AI writes the paragraph, not the table itself
Output:   ~500 words narrative + auto-table
```

**Section 3.3 — Results: Quality Assessment:**
```
Receives: preamble (WITH registry) + all prior
Writes:   Interpretation of quality findings
          "Mean quality score was 7.2/10 (range 4–9). 
           22 studies were rated low risk of bias, 
           28 moderate, and 5 high risk..."
Quality TABLE auto-built from QualityAssessment records
Output:   ~350 words narrative + auto-table
```

**Section 3.4 — Results: Bibliometric Findings:**
```
Receives: preamble (no registry) + all prior
Writes:   Description of each bibliometric graph
          What the co-occurrence network reveals
          What the thematic map shows
          What the Sankey diagram shows (if generated)
Document builder embeds actual PNG files
Output:   ~500 words
```

**Section 3.5 — Results: Synthesis by Theme:**
```
Receives: preamble (WITH registry) + all prior
          + all reconciled_text from ThemeSynthesis records

Writes:   One subsection per theme with heading
          Stitches together the reconciled texts
          Adds transitions and cross-theme connections
          Every claim uses evidence-grade-appropriate language
          Every citation from paper_registry only
Output:   ~2,500 words (longest section)
```

**Section 3.6 — Results: Subgroup Analysis:**
```
Receives: preamble (WITH registry) + all prior
          + subgroup_data from scaffold

Writes:   Differences across study designs
          Geographic patterns if country data sufficient
          Temporal trends if year_span condition met
Output:   ~500 words
```

**Section 4 — Discussion:**
```
Receives: full scaffold WITH registry + all 11 prior sections

Writes:   Must explicitly address each RQ by name
          "Regarding RQ1, the evidence consistently demonstrates..."
          "Turning to RQ2, findings suggest that..."
          Interprets synthesis in broader context
          Explains contradictions from Critic passes
          Limitations of the evidence base
Output:   ~1,000 words
```

**Section 5 — Conclusion:**
```
Receives: preamble (no registry) + all prior sections
Writes:   Direct answers to each RQ
          Limitations of this review specifically
          (abstract-only papers, no grey literature, etc.)
          Recommendations for future research
Output:   ~400 words
```

**Abstract — written last:**
```
Receives: full scaffold WITH registry + COMPLETE DRAFT

Writes:   Structured abstract:
          Background: why this topic matters
          Objectives: the three RQs
          Methods:    Scopus, 847 records, 55 included
          Results:    6 themes identified, key findings summary
          Conclusions: implications
Output:   ~300 words
```

---

## PHASE 24 — Consistency Check

One Gemini Pro call reads the complete assembled draft and checks for violations:

```
Issues detected and auto-fixed:
1. "consumer vulnerabilities" used 3 times → replaced with 
   "consumer vulnerability"
2. Discussion paragraph cited (Johnson, 2018) not in registry → 
   softened to "prior literature suggests"
3. Abstract stated "46 papers included" → corrected to "55"
4. RQ3 not explicitly addressed in Discussion → flagged for 
   manual review (not auto-fixable)
```

All auto-fixable issues applied to draft text. Non-auto-fixable flagged in log.

---

## PHASE 25 — APA Reference List Generated

One dedicated Gemini Pro call formats all 55 confirmed papers as APA 7th edition, using the full metadata including volume, issue, and page range from the Paper model:

```
Baker, S. M., Gentry, J. W., & Rittenburg, T. L. (2019). 
    Consumer vulnerability in digital markets: A cross-national 
    examination. Journal of Consumer Research, 47(3), 412–431. 
    https://doi.org/10.1093/jcr/ucz052
```

Sorted alphabetically by first author surname, then year, then title. ~85–90% ready for submission without manual correction.

---

## PHASE 26 — md file Assembled

note: where graphs are to be placed write [graphs to be pasted here: graph name]

```
Title page
  ├── Review title
  ├── Date, total papers, review ID

PICO Table (auto-formatted from user input)

Table of Contents (Word auto-generates from headings)

1. Introduction                    (~700 words)
2. Methodology
   2.1 Search Strategy             (~300 words + query table)
   2.2 Selection Criteria          (~200 words + PICO table)
   2.3 Study Selection Process     (~250 words)
   2.4 Data Extraction             (~200 words)
3. Results
   3.1 Study Selection             (~250 words + PRISMA diagram PNG)
   3.2 Study Characteristics       (~500 words + characteristics table)
   3.3 Quality Assessment          (~350 words + quality table + 
                                    risk of bias chart PNG)
   3.4 Bibliometric Findings       (~500 words + 5 graph PNGs)
   3.5 Synthesis by Theme          (~2,500 words + theme freq PNG +
                                    evidence heatmap PNG)
   3.6 Subgroup Analysis           (~500 words + subgroup PNGs)
4. Discussion                      (~1,000 words)
5. Conclusion                      (~400 words)
References                         (55 APA 7th entries)
Appendix A: Search Queries         (5 verbatim Scopus queries)
Appendix B: PRISMA Checklist       (pre-filled from pipeline data)
Appendix C: Excluded Studies       (table of all excluded papers 
                                    with exclusion reasons from DB)
```

`GeneratedDocument` record created with `docx_path`, `word_count`.

Review `status = 'done'`, `completed_at = timezone.now()`.

---

## PHASE 27 — User Downloads

Review status changes to `done`. Progress page shows a download button. User navigates to the download page.

```
Your SLR is ready.

[ Download md File]
[ Download Paper List Excel ]
[ Open Interactive HTML Report ]

Summary:
  847 records retrieved → 55 papers included
  8 papers excluded by reviewer
  6 themes identified
  ~8,400 words
  Runtime cost: $1.59

Notes before submission:
  ⚠ Verify APA references — especially author name formatting
  ⚠ Add your PROSPERO registration number to Section 2.3
  ⚠ 12 papers used abstract only — flagged in characteristics table
```

**md file** — complete academic SLR ready for editing and submission.

**Paper List Excel** — all 847 papers with every screening decision, confidence score, final decision, PDF source, GROBID status, selection rationale, user exclusion reason.

**Interactive HTML Report** — pyvis co-occurrence network and thematic map that the user can zoom, hover, and explore. For supplementary materials or research websites.

---

## OTHER IMPORTANT EXTRA STUFF [how we are doing something like ]

Good question to get completely clear on before building. Let me walk through the entire analysis and writing process from the moment we have 55 confirmed papers to the moment the md file is assembled.

---

## Part 1 — Thematic Clustering

Yes, we are doing thematic clustering. It happens in two places in the pipeline and they serve different purposes.

---

### Clustering 1 — Bibliometric Keyword Co-occurrence (Stage 15/16)

This runs on **Scopus metadata only** — no PDFs needed. It uses NetworkX and the Louvain community detection algorithm.

**How it works:**

Every included paper has a list of author keywords from Scopus. For example:
```
Paper 1 keywords: ["consumer vulnerability", "digital markets", "elderly consumers"]
Paper 2 keywords: ["consumer vulnerability", "online retail", "digital literacy"]
Paper 3 keywords: ["digital literacy", "consumer protection", "regulation"]
```

NetworkX builds a graph where every keyword is a node. Two keyword nodes get an edge between them if they appear together in the same paper. The edge weight increases each time that pair co-occurs.

```
consumer vulnerability ──── digital markets (weight 3)
consumer vulnerability ──── elderly consumers (weight 2)
consumer vulnerability ──── digital literacy (weight 4)
digital literacy ─────────── consumer protection (weight 2)
digital literacy ─────────── regulation (weight 1)
```

Then the **Louvain algorithm** runs on this graph. Louvain is a community detection algorithm — it finds groups of nodes that are more densely connected to each other than to the rest of the graph. Each community becomes a colour on the co-occurrence network graph.

```
Community 1 (blue): consumer vulnerability, elderly consumers, digital exclusion
Community 2 (green): digital literacy, consumer protection, regulation
Community 3 (red): online retail, platform design, deceptive practices
```

**What this produces:**
- The keyword co-occurrence network visual (pyvis HTML + static PNG)
- The thematic map 2×2 (centrality vs density per community)
- The Sankey evolution diagram (keyword migration across time periods)

**Important:** This clustering is purely bibliometric. It shows the intellectual structure of the field. It does NOT produce the themes used in the synthesis. Those come from the next step.

---

### Clustering 2 — AI Evidence-Based Theme Identification (later Stage)

This runs on the actual **extracted content from all 55 papers** — the DataExtraction records. This is where the synthesis themes come from.

After extraction, every paper has structured data:
```python
{
  study_design: "cross-sectional survey",
  population: "elderly consumers aged 65+ in UK",
  intervention: "exposure to deceptive pricing interfaces",
  outcomes: [
    {name: "vulnerability score", result: "significantly higher in digital contexts"},
    {name: "complaint behavior", result: "lower than expected given harm experienced"}
  ],
  key_findings: "Elderly consumers showed 3.2x higher vulnerability scores..."
}
```

One Gemini Pro call receives all 55 papers' extraction data as a JSON array and identifies 5–8 themes by looking for patterns across the corpus:

```python
EVIDENCE_MATRIX_PROMPT = '''
You are identifying themes for a systematic review synthesis.
Research objectives: {objectives}
Research questions: {rqs}

Here are extracted data from all 55 included papers:
{all_extractions_json}

Identify 5-8 distinct themes that emerge from this evidence.
For each theme:
- Name it precisely (3-6 words)
- List which paper IDs address it
- Count what percentage of the corpus it represents
- Note what study designs are present
- Assess direction of findings (convergent/divergent)
- Assign evidence grade

Return JSON: [{theme_name, paper_ids, pct, designs, evidence_grade, rationale}]
'''
```

**What Gemini looks for:**
- Which papers address the same construct or phenomenon
- Where findings converge or contradict
- What the dominant and peripheral topics are
- What proportion of the corpus each topic represents

**Example output:**
```json
[
  {
    "theme_name": "Digital Literacy as Vulnerability Mediator",
    "paper_ids": ["SCOPUS:12345", "SCOPUS:23456", ...],
    "pct": 56,
    "designs": ["cross-sectional", "qualitative", "RCT"],
    "evidence_grade": "Emerging",
    "rationale": "31 papers examine digital literacy..."
  },
  {
    "theme_name": "Platform Design and Exploitation Mechanisms", 
    "pct": 69,
    "evidence_grade": "Established",
    ...
  },
  {
    "theme_name": "Regulatory Frameworks and Enforcement",
    "pct": 15,
    "evidence_grade": "Insufficient",
    ...
  }
]
```

**Evidence grades are assigned objectively:**

| Grade | Criteria |
|---|---|
| Established | ≥60% of papers, multiple study designs agree |
| Emerging | 30–60%, mostly one study design |
| Contested | Papers directly contradict each other |
| Insufficient | <30% or ≤2 papers |

These grades are locked into the scaffold. They control the language Gemini uses when writing every synthesis paragraph.

---

## Part 2 — Dialectical Synthesis Per Theme

For each theme, three sequential Gemini Pro calls construct an argument. This is the core quality mechanism.

---

### Pass 1 — The Advocate

Gemini receives the scaffold preamble (with consistency rules) plus all extraction data from papers in this theme. It is instructed to build the strongest possible case FOR this theme being well-established.

```
Input:  Scaffold preamble + theme extractions + evidence grade: Emerging
Output: 200-300 words of academic prose

Example output:
"Growing evidence suggests that digital literacy functions as a 
significant mediating variable in consumer vulnerability outcomes. 
Smith & Jones (2021) found that consumers in the lowest digital 
literacy quartile reported vulnerability scores 2.8 times higher 
than the highest quartile (p<0.001), a finding replicated by Chen 
et al. (2022) in a cross-national sample of 4,200 participants..."
```

The advocate respects the evidence grade. It uses "suggests" not "demonstrates" because the grade is Emerging, not Established.

---

### Pass 2 — The Critic

Gemini receives the advocate text and reads it critically. It is instructed to find every weakness in the advocate's argument.

```
Input:  Advocate text + all theme extractions + evidence grade
Output: 150-250 words identifying weaknesses

Example output:
"The advocate position overstates the consistency of findings. 
While Smith & Jones (2021) and Chen et al. (2022) show convergent 
results, both studies operationalise digital literacy differently — 
Smith uses self-reported confidence scores while Chen uses task 
completion rates. Williams et al. (2020), the only RCT in this 
group, found no significant mediation effect when controlling for 
age and socioeconomic status, a confound the cross-sectional 
studies cannot rule out..."
```

---

### Pass 3 — The Reconciler

Gemini receives both the advocate and critic texts, plus the original evidence. It writes the final synthesis paragraph.

```
Input:  Advocate + Critic + extractions + evidence grade + scaffold
Output: 300-400 words of publication-ready academic prose

Example output:
"Digital literacy emerges as a theoretically significant mediating 
variable in consumer vulnerability, though the evidence base 
warrants qualification on methodological grounds. Convergent 
findings from cross-sectional studies conducted in Western contexts 
(Smith & Jones, 2021; Chen et al., 2022; Baker, 2020) suggest that 
low digital literacy is associated with substantially elevated 
vulnerability scores, consistent with the cognitive capacity 
framework proposed by Williams (2019). However, this consensus 
requires careful interpretation. The sole RCT in this corpus 
(Williams et al., 2020) found the mediation effect non-significant 
when controlling for age and socioeconomic status, raising the 
possibility that digital literacy functions as a proxy for broader 
socioeconomic disadvantage rather than as an independent 
determinant. This methodological heterogeneity — self-reported 
confidence versus task-based competency measures — limits direct 
comparison across studies. The weight of evidence therefore 
supports digital literacy as an associated factor in vulnerability, 
with its independence from socioeconomic confounds representing a 
critical gap requiring experimental investigation."
```

This is not a summary. It makes a claim, acknowledges its limits, explains why the contradiction exists, and arrives at a defensible position. This is what a senior researcher writes.

---

### Thin Theme Treatment

Themes graded Insufficient (≤2 papers or <30% of corpus) do not get the three-pass treatment. There is nothing to argue for or against with 2 papers. A single call writes an honest acknowledgement:

```
"Preliminary evidence suggests a connection between regulatory 
frameworks and consumer vulnerability outcomes, though the current 
literature is insufficient to draw substantive conclusions. Only 
two studies in this corpus address regulatory mechanisms directly 
(Jones & Smith, 2019; Baker et al., 2021), and their differing 
national contexts — EU and Australian regulatory environments 
respectively — preclude direct synthesis. This represents a 
significant research gap requiring systematic investigation across 
regulatory jurisdictions."
```

---


