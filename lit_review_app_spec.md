# AI-Assisted Literature Review — Django App Specification

> Every stage, every Django model, every AI prompt, and all data flows — in order of implementation.

---

## Overview

This app takes a researcher's question and a word count target, then produces a complete literature review. It works in five stages. Each stage produces structured data that feeds the next. Nothing is generated in one shot.

| # | Stage | Input | Output |
|---|-------|-------|--------|
| 1 | Structure planning | Research question + word count | Section outline JSON with word targets |
| 2 | Paper discovery | Section keywords | Candidate papers from Semantic Scholar |
| 3 | PDF upload + extraction | PDF files | Per-paper extracted text |
| 4a | Paper extraction | PDF text | Structured summary JSON per paper |
| 4b | Section assignment | Summary JSON + structure JSON | Each paper assigned to a section |
| 5a | Section writing | Assigned papers + section brief | Prose for each section |
| 5b | Stitching | All section prose | Complete literature review |

---

## Django Models

Create these five models. They map directly to the five stages.

### LitReview

Top-level object. One per user session.

```
id                          UUID (primary key)
user                        FK → User
research_question           TextField
target_word_count           IntegerField
review_goal                 TextField             filled by Stage 1
gap_statement               TextField             filled by Stage 1
section_order_rationale     TextField             filled by Stage 1
final_prose                 TextField             filled by Stage 5b
created_at                  DateTimeField
status                      CharField             choices: planning | searching | extracting | writing | done
```

### ReviewSection

One row per section inside a LitReview. Created by Stage 1.

```
id                  UUID
review              FK → LitReview
number              IntegerField
title               CharField
type                CharField             choices: foundation | debate | recent | gap
purpose             TextField
what_to_look_for    TextField
search_keywords     JSONField             list of strings
target_paper_count  CharField
leads_to            TextField
word_count_target   IntegerField          set by Stage 1 word distribution
prose               TextField             filled by Stage 5a
```

### Paper

One row per discovered or uploaded paper.

```
id          UUID
review      FK → LitReview
title       CharField
authors     JSONField         list of strings
year        IntegerField
source      CharField         journal or conference
doi         CharField         nullable
pdf_file    FileField         nullable — only for uploaded PDFs
pdf_text    TextField         extracted raw text
origin      CharField         choices: api_discovery | user_upload
included    BooleanField      default False — user confirms inclusion
```

### PaperExtraction

Structured AI extraction for each included paper. One-to-one with Paper.

```
id                          UUID
paper                       OneToOneField → Paper
core_claim                  TextField
background                  TextField
methodology_type            CharField
methodology_description     TextField
methodology_sample          CharField         nullable
key_findings                JSONField         list of strings
limitations                 JSONField         list of strings
key_concepts                JSONField         list of strings
stance                      CharField         choices: supports | challenges | nuances | reviews
quotable                    TextField
citation_apa                TextField
```

### PaperAssignment

Links a paper to the section it belongs in. Created by Stage 4b.

```
id                  UUID
paper               FK → Paper
section             FK → ReviewSection
confidence          CharField     choices: high | medium | low
reason              TextField
how_to_use          TextField
also_relevant_to    JSONField     list of section numbers
flag                CharField     nullable
                                  choices: contradicts_another_paper | very_high_impact
                                           | methodology_concern | too_tangential
```

---

## Stage 1 — Research Question → Structure + Word Distribution

### What happens

1. User submits their research question and a total word count target (e.g. 3000 words).
2. Django calls the Anthropic API with the system and user prompt below.
3. AI returns a JSON with sections, each including a `word_count_target` field.
4. Django creates one `LitReview` record and N `ReviewSection` rows from the JSON.
5. User sees the section plan and can rename sections or reorder before proceeding.

### Word count distribution logic

Include the total word count in the prompt and instruct the AI to distribute it across sections. The intro paragraph and closing paragraph (written in Stage 5b) together consume roughly 10% of the total, so the AI allocates 90% across the main sections.

Distribution by section type:

- `debate` sections: 30–35% of allocated words each
- `recent` sections: 20–25%
- `foundation` sections: 15–20%
- `gap` section: 10–15%

All `word_count_target` values must sum exactly to `total_words_allocated`.

### System prompt

```
You are a research assistant helping plan the literature review section of an academic research paper.

When given a research question and a total word count, output a structured plan for the literature review.
Do not write the review itself — only plan it.

The plan must be a JSON object with this exact structure:

{
  "research_question": "<the question as given>",
  "review_goal": "<one sentence: what this lit review must accomplish to justify the research>",
  "total_words_allocated": <integer — 90% of the user's target, reserving 10% for intro/closing>,
  "sections": [
    {
      "number": 1,
      "title": "<concise section title>",
      "type": "foundation" | "debate" | "recent" | "gap",
      "purpose": "<2-3 sentences: what this section establishes and why it comes here>",
      "what_to_look_for": "<one sentence: what kind of papers belong here>",
      "search_keywords": ["keyword 1", "keyword 2", "keyword 3", "keyword 4"],
      "target_paper_count": "<e.g. 6-8>",
      "leads_to": "<one sentence: how this section sets up the next>",
      "word_count_target": <integer — words allocated to this section>
    }
  ],
  "gap_statement": "<2-3 sentences: the literature gap the research addresses>",
  "section_order_rationale": "<one sentence: why sections are in this order>"
}

Rules:
- Output only valid JSON. No markdown, no preamble, no explanation.
- Include 3 to 5 sections. Most research questions need 4.
- Word count distribution: debate sections get 30-35% of total_words_allocated each.
  Foundation sections get 15-20%. Recent sections get 20-25%. Gap section gets 10-15%.
  All section word_count_target values must sum exactly to total_words_allocated.
- Section types: foundation = defines context, debate = contested evidence,
  recent = latest developments, gap = explicit gap identification (use once, last section only).
- Sections must flow — each one builds on the previous.
- gap_statement must read as a natural conclusion after reading all sections in order.
- Search keywords must be specific enough to return focused results.
```

### User prompt

```
Research question: {{research_question}}
Total word count target: {{target_word_count}} words

Generate the literature review structure with word count distribution.
```

### Django view

- Endpoint: `POST /api/reviews/`
- Accepts: `research_question` (string), `target_word_count` (integer)
- Calls Anthropic API with the above prompts
- Parses JSON response, validates that section word counts sum to `total_words_allocated`
- Creates `LitReview` record and one `ReviewSection` record per section
- Returns the full structure JSON to the frontend

---

## Stage 2 — Paper Discovery via Semantic Scholar API

### What happens

1. For each `ReviewSection`, Django queries the Semantic Scholar API using that section's `search_keywords`.
2. Each keyword becomes one API call. Results are merged and deduplicated by DOI.
3. Top 10–15 results per section are returned to the user as candidates.
4. User browses candidates, checks boxes to include, and can also upload their own PDFs.
5. Included papers are saved as `Paper` records with `included = True`.

### Semantic Scholar API

No API key required for basic use. Use the public search endpoint:

```
GET https://api.semanticscholar.org/graph/v1/paper/search

Query params:
  query   = <keyword string>
  fields  = title,authors,year,abstract,externalIds,venue,citationCount
  limit   = 10
```

> Rate limit: 100 requests per 5 minutes without a key. Apply for a free API key at semanticscholar.org for higher limits. OpenAlex (openalex.org/api) is a free alternative with no rate limits.

### Django view

- Endpoint: `POST /api/reviews/{review_id}/search/`
- Loops over all sections in the review
- For each section, fires one API call per keyword (max 4 calls per section)
- Deduplicates results across sections by DOI or title similarity
- Creates `Paper` records with `origin = api_discovery` and `included = False`
- Returns grouped candidate list to frontend (grouped by section)

---

## Stage 3 — PDF Upload and Text Extraction

### What happens

1. User uploads PDF files. Each is stored in Django's media folder.
2. Django extracts text from each PDF using pdfplumber or PyMuPDF.
3. Extracted text is stored in `Paper.pdf_text`.
4. User marks which papers (discovered + uploaded) to include. These proceed to Stage 4.

### PDF text extraction strategy

Not all PDFs extract cleanly. Use this order of fallback:

1. **First try:** pdfplumber — best for structured academic papers
2. **Second try:** PyMuPDF (fitz) — faster, handles more formats
3. **For scanned PDFs:** use pytesseract OCR (install separately)

After extraction, run a basic cleaning step: remove excessive whitespace, strip repeating page headers and footers, normalize unicode characters.

> For long papers: extract abstract + introduction + conclusion first (pages 1–3 and last 2 pages). This is sufficient for extraction in 95% of academic papers. Only pull the full text if the abstract alone is too sparse.

### Django view

- Endpoint: `POST /api/reviews/{review_id}/papers/upload/`
- Accepts multipart form data with one or more PDF files
- For each file: save to `media/`, extract text, create `Paper` record with `origin = user_upload`
- Endpoint: `PATCH /api/papers/{paper_id}/` to toggle `included = True/False`

---

## Stage 4a — Per-Paper Extraction

### What happens

1. For each included paper, Django calls the AI with the paper's extracted text.
2. AI returns a structured JSON summarising the paper.
3. Django saves this as a `PaperExtraction` record linked to the paper.
4. This call is made independently of the review structure — it purely reads the paper.

> Run extraction calls concurrently using Celery tasks. Do not run sequentially — with 20+ papers it will be too slow.

### System prompt

```
You are a research paper analyst. Extract structured information from academic papers accurately.

Return a JSON object with this exact structure:

{
  "title": "<paper title>",
  "authors": ["<Last, F.>"],
  "year": <integer>,
  "source": "<journal or conference>",
  "core_claim": "<one sentence: the single most important thing this paper argues or finds>",
  "background": "<2-3 sentences: what problem this paper responds to>",
  "methodology": {
    "type": "<meta-analysis | longitudinal | experiment | systematic review | theoretical | qualitative | other>",
    "description": "<one sentence: how the study was conducted>",
    "sample": "<sample size and population, or null>"
  },
  "key_findings": [
    "<finding 1 — specific, one sentence>",
    "<finding 2 — specific, one sentence>",
    "<finding 3 if exists>"
  ],
  "limitations": [
    "<limitation 1>",
    "<limitation 2 if exists>"
  ],
  "key_concepts": ["<concept 1>", "<concept 2>", "<concept 3>"],
  "stance": "supports" | "challenges" | "nuances" | "reviews",
  "quality_category": "A" | "B" | "C" | "D",
  "quotable": "<one direct quote from the paper, under 30 words>",
  "citation": "<APA format citation string>"
}

Rules:
- Output only valid JSON. No markdown, no preamble.
- Be specific in findings — not "results were significant" but what was significant and in what direction.
- stance values:
    supports   = adds evidence to an established view
    challenges = contradicts the prevailing view
    nuances    = refines or adds conditions to the prevailing view
    reviews    = synthesizes existing work
- quality_category values (ordinal):
    A = very strong methodological quality and reporting
    B = strong quality with minor limitations
    C = moderate quality with notable limitations
    D = weak quality and/or major limitations
- If a field cannot be determined from the text, use null.
- Do not infer or hallucinate anything not present in the paper.
```

### User prompt

```
Here is the text of the research paper:

{{paper.pdf_text}}

Extract the structured summary.
```

### Django view

- Endpoint: `POST /api/reviews/{review_id}/extract/`
- Loops over all `Paper` records where `included = True` and no `PaperExtraction` exists yet
- For each paper: calls Anthropic API, parses JSON, creates `PaperExtraction` record
- Run these calls concurrently using Celery tasks
- Returns extraction status per paper to the frontend

---

## Stage 4b — Paper-to-Section Assignment

### What happens

1. For each paper with a completed `PaperExtraction`, Django calls the AI again.
2. This time the AI knows the review structure and decides which section the paper belongs to.
3. AI returns an assignment JSON. Django creates a `PaperAssignment` record.
4. Papers flagged as `too_tangential` are surfaced to the user before writing begins.

### System prompt

```
You are a research assistant organizing papers into a literature review structure.

You will receive:
1. A literature review structure with numbered sections (title, type, purpose)
2. A single extracted paper summary

Decide which section this paper belongs to and how it should be used.

Return a JSON object with this structure:

{
  "paper_title": "<title from the summary>",
  "assigned_section": <section number as integer>,
  "assignment_confidence": "high" | "medium" | "low",
  "reason": "<one sentence: why this paper fits that section>",
  "how_to_use": "<one sentence: what specific point this paper should be cited to support>",
  "also_relevant_to": [<section number>, ...],
  "flag": null | "contradicts_another_paper" | "very_high_impact" | "methodology_concern" | "too_tangential"
}

Rules:
- Output only valid JSON.
- assigned_section must match one of the section numbers in the structure.
- also_relevant_to lists other sections this paper could additionally support.
- flag is null unless a condition clearly applies.
- If the paper does not fit any section well: assign to closest, set confidence to low.
```

### User prompt

```
Literature review structure:
{{review_structure_json}}

Paper summary:
{{paper_extraction_json}}

Assign this paper to the appropriate section.
```

### Django view

- Endpoint: `POST /api/reviews/{review_id}/assign/`
- Loops over all `PaperExtraction` records for this review
- For each: calls Anthropic API with structure + extraction, parses response, creates `PaperAssignment`
- After all assignments: check if any section has zero assigned papers — alert the user if so

---

## Stage 5a — Section Writing (one call per section)

### What happens

1. For each `ReviewSection`, Django collects all `PaperAssignment` records where `assigned_section` = this section.
2. Calls the AI once per section, passing only that section's papers.
3. AI writes the prose for that section to the exact `word_count_target`.
4. Django saves prose to `ReviewSection.prose`.

> Sections must be written in order (section.number ASC). Do not parallelise this stage.

### System prompt

```
You are an academic writing assistant writing one section of a literature review.

You will receive:
1. The research question and review goal
2. The gap statement the full review builds toward
3. The current section: title, type, purpose, leads_to, and word_count_target
4. The papers assigned to this section with their extractions and how_to_use instructions

Write this section as polished academic prose.

Writing rules:
- Organize by idea, not by paper. Never write one paragraph per paper.
- Each paragraph: open with a point, use papers as evidence, close with implication.
- Cite inline: (Author, Year) or Author (Year) found that...
- Handle stance correctly:
    supports   → cite as converging evidence
    challenges → use contrast language: however, in contrast, counter to this
    nuances    → use qualifying language: this effect is moderated by, depends on
    reviews    → cite as synthesizing: a review of X found...
- Weave in paper limitations briefly — do not list them as a separate paragraph.
- Final sentence must flow into what the next section covers (use leads_to as your guide).
- Do not invent any fact, statistic, or claim not present in the paper summaries.
- Write to the word_count_target. Stay within 5% of that number.
- Do not use em dashes (�); use commas, colons, or parentheses instead.

Output this JSON:

{
  "section_number": <integer>,
  "section_title": "<title>",
  "prose": "<full section text, paragraphs separated by \n\n>",
  "word_count": <integer — actual word count of the prose>,
  "papers_used": ["<APA citation>", ...],
  "papers_unused": ["<APA citation>", ...],
  "notes_for_user": "<one sentence flagging judgment calls or evidence gaps, or null>"
}
```

### User prompt

```
Research question: {{review.research_question}}
Review goal: {{review.review_goal}}
Gap statement: {{review.gap_statement}}

Section to write:
  Number: {{section.number}}
  Title: {{section.title}}
  Type: {{section.type}}
  Purpose: {{section.purpose}}
  Leads to: {{section.leads_to}}
  Word count target: {{section.word_count_target}} words

Papers assigned to this section:
{{papers_json_array}}

Write this section.
```

The `papers_json_array` should include for each paper: `core_claim`, `key_findings`, `limitations`, `stance`, `how_to_use`, `citation_apa`.

### Gap section handling (special case inside Stage 5a)

If `section.type == "gap"`, do not use the standard section-writing prompt above.
Use a dedicated synthesis+gap prompt that does not require newly assigned papers for that section.

In Django view logic:

```python
if section.type == "gap":
    use the gap-writing prompt
else:
    use the normal section-writing prompt
```

#### Gap section system prompt

```
You are an academic writing assistant writing the final synthesis section of a literature review.

This section does not cite new papers. It is written entirely from what the
preceding sections have already established.

You will receive:
1. The research question
2. The gap statement — the conclusion the whole review has been building toward
3. The title and purpose of this synthesis section
4. A summary of what each preceding section established (their prose)
5. The word count target for this section

Write this section as polished academic prose. It must do three things in order:

1. Synthesize — in 1-2 paragraphs, draw together the key threads from the
   preceding sections. What do they collectively show? Where do they converge?
   Where do they conflict? Do not summarize each section separately —
   find the pattern across them.

2. Name the gap — in 1 paragraph, state clearly and precisely what the
   existing literature does not address. Be specific: not "more research is needed"
   but what kind of research, on what population, using what lens, is missing.

3. Justify your study — in 1-2 sentences, connect the gap directly to the
   research question. This should feel like a natural arrival, not a sudden pivot.

Writing rules:
- Do not introduce any new citations.
- You may refer back to authors already cited in earlier sections
  (e.g. "as Smith (2019) noted") but do not add new references.
- Write to the word_count_target. Stay within 5% of that number.
- The final sentence must end the literature review — it should leave the reader
  ready to encounter your research question as the logical next step.
- Do not use em dashes; use commas, colons, or parentheses instead.

Output this JSON:

{
  "section_number": <integer>,
  "section_title": "<title>",
  "prose": "<full section text, paragraphs separated by \n\n>",
  "word_count": <integer>,
  "notes_for_user": "<one sentence if anything needs human review, else null>"
}
```

#### Gap section user prompt

```
Research question: {{review.research_question}}
Gap statement: {{review.gap_statement}}

This synthesis section:
  Number: {{section.number}}
  Title: {{section.title}}
  Purpose: {{section.purpose}}
  Word count target: {{section.word_count_target}} words

What the preceding sections established:
{{array of {section_number, section_title, prose} for all sections before this one}}

Write the synthesis and gap section.
```

### Django view

- Endpoint: `POST /api/reviews/{review_id}/write/`
- Loop over all `ReviewSection` records in section number order
- For each section: collect its `PaperAssignment` records and their linked `PaperExtraction` data
- Build `papers_json_array` from the combined data
- Call Anthropic API, parse prose from JSON response, save to `ReviewSection.prose`
- Surface `notes_for_user` in the UI with a warning icon — these need human review

---

## Stage 5b — Stitching (intro, transitions, closing)

### What happens

1. All section prose is now written. This final call adds the connective tissue only.
2. AI writes: an opening paragraph, transition sentences between sections, and a closing paragraph.
3. Django assembles the full review and saves to `LitReview.final_prose`.
4. Status is set to `done`.

### System prompt

```
You are an academic writing assistant finalizing a literature review.

You will receive all written sections in order, plus the gap statement.

Your job is to write the connective tissue only — do not rewrite the sections themselves.

Important guard:
- Do not restate, dilute, or replace the gap conclusion already established in the final section.
- The closing paragraph should synthesize and bridge, not create a second gap section.

Write:
1. An opening paragraph (5-7 sentences) framing the domain and signposting what the review covers
2. A transition sentence between each pair of adjacent sections (only where the join needs smoothing)
3. A closing paragraph (5-7 sentences) synthesizing what the sections established,
   ending with the gap statement lightly reworded to flow naturally

The opening + closing together should use approximately 10% of the total review word count.

Output this JSON:

{
  "intro_paragraph": "<opening paragraph>",
  "transitions": [
    {
      "after_section": <integer>,
      "before_section": <integer>,
      "transition_sentence": "<one bridging sentence, or null if not needed>"
    }
  ],
  "closing_paragraph": "<synthesis + gap paragraph>"
}
```

### User prompt

```
Research question: {{review.research_question}}
Gap statement: {{review.gap_statement}}
Total target word count: {{review.target_word_count}}

Sections in order:
{{array of {section_number, section_title, prose} objects}}

Generate the connective tissue.
```

### Django view

- Endpoint: `POST /api/reviews/{review_id}/stitch/`
- Collects all `ReviewSection.prose` in section number order
- Calls Anthropic API with the above prompts
- Assembles final text: intro → section 1 → transition → section 2 → ... → closing
- Saves assembled text to `LitReview.final_prose`
- Sets `LitReview.status = done`
- Returns the full review to the frontend for display and download

---

## Implementation Notes

### Model to use

Use `deepseek` for all calls.

### User editing checkpoints

Give the user a chance to intervene at three points before moving to the next stage:

- **After Stage 1:** let the user rename sections and reorder them
- **After Stage 4b:** let the user move papers between sections manually
- **After Stage 5a:** let the user edit the prose of any section before stitching

### Handling flagged papers

In Stage 4b, surface flagged papers to the user with context:

- `too_tangential` → show: "This paper may not fit well — include anyway?"
- `contradicts_another_paper` → show: "This paper contradicts another in the same section — both are included."

Let the user decide in both cases.

### Word count drift

After Stage 5a, calculate the actual total word count across all sections. If it is more than 10% away from the target, show a notice in the UI. Optionally add a rewrite endpoint that sends a single section back with an instruction to expand or condense to a revised word target.

---

## Full Pipeline Summary

```
Stage 1    research_question + target_word_count
              → structure JSON with section word targets

Stage 2    section.search_keywords
              → Semantic Scholar API → candidate Paper records

Stage 3    PDF files
              → extracted pdf_text stored on Paper records

Stage 4a   paper.pdf_text
              → PaperExtraction JSON             (one call per paper, run in parallel)

Stage 4b   PaperExtraction + review structure
              → PaperAssignment JSON             (one call per paper, run in parallel)

Stage 5a   section + its assigned papers
              → ReviewSection.prose              (one call per section, run in order)

Stage 5b   all ReviewSection.prose + gap_statement
              → intro + transitions + closing
              → LitReview.final_prose
```






