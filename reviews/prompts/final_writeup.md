Task: Implement Phase 23 — The Ghostwriter Sequential Assembly

Build a service GhostwriterService that manages the stateful generation of the 8,000-word manuscript.

Step 1: The Section Map
Define a constant SECTION_MAP that dictates the order and the specific data "payload" for each call:

1.0 Introduction (Payload: Objectives + RQs)

2.1 Search Strategy (Payload: Query strings + Dates)

2.2 Selection Criteria (Payload: PICO + Inclusion/Exclusion)

2.3 Quality Assessment Method (Payload: The Rubric used in Phase 16)

2.4 Data Synthesis Method (Payload: Narrative on the Dialectical Loop)

3.1 Study Selection (Payload: PRISMA Narrative counts)

3.2 Study Characteristics (Payload: subgroup_data by Design/Country)

3.3 Quality Assessment Results (Payload: quality_summary stats)

3.4 Bibliometric Findings (Payload: Cluster names from Phase 17)

3.5 Synthesis of Themes (Payload: ALL reconciled_text from Phase 21)

3.6 Subgroup Analysis (Payload: subgroup_data correlations)

4.0 Discussion (Payload: RQs + Synthesis findings)

5.0 Conclusion (Payload: Final summary + Policy implications)

Abstract (Payload: The full draft of all previous sections)

References (Payload: The paper_registry)

Step 2: The Context Carry-Forward
For every call after the first, the service must prepend the text of the immediately preceding section to the prompt. This ensures the AI creates smooth transitions (e.g., "Building on the search strategy described above, the following criteria were applied...").

Step 3: Placeholder Injection
Instruct the backend to insert [INSERT FIGURE X] or [INSERT TABLE X] tags into the text based on the section (e.g., Figure 1 in Section 3.1).

Part 2: The "Master" LLM Prompt (Deepseek)
This is the exact prompt your backend will send for each section. It is designed to be a "Shell" that changes based on the data provided.

[SCAFFOLD PREAMBLE]
(This includes your locked counts, registry, and theme names as we finalized earlier.)

TASK: ACADEMIC MANUSCRIPT GENERATION
SECTION TO WRITE: {section_name} (e.g., Section 3.5 Synthesis of Themes)

PREVIOUS SECTION CONTEXT:
{previous_section_text}

SPECIFIC DATA FOR THIS SECTION:
{section_specific_payload}

WRITING INSTRUCTIONS:see below for each indivisual instructions



Table of Contents 

1. Introduction                    (~900 words)
2. Methodology
   2.1 Search Strategy             (~400 words + query table)
   2.2 Selection Criteria          (~300 words + PICO table)
   2.3 Study Selection Process     (~350 words)
   2.4 Data Extraction             (~300 words)
3. Results
   3.1 Study Selection             (~350 words + PRISMA diagram PNG)
   3.2 Study Characteristics       (~600 words + characteristics table)
   3.3 Quality Assessment          (~450 words + quality table + 
                                    risk of bias chart PNG)
   3.4 Bibliometric Findings       (~600 words + 5 graph PNGs)
   3.5 Synthesis by Theme          (~2,500 words + theme freq PNG +
                                    evidence heatmap PNG)
   3.6 Subgroup Analysis           (~600 words + subgroup PNGs)
4. Discussion                      (~1,200 words)
5. Conclusion                      (~500 words)




## 12. Writing: Introduction

**Model:** Deepseek 
**Called:** Once — first writing call  
**Purpose:** Background, motivation, objectives, and RQ statement  

**Scaffold:** Reduced (no paper registry — introduction does not cite individual included papers)

### Prompt

```
{SCAFFOLD_PREAMBLE — REGISTRY OMITTED}

---

=== NOW WRITE: SECTION 1 — INTRODUCTION ===
=== Do NOT cite individual papers from the paper registry in this section. ===

Write the Introduction section for this systematic literature review.

Structure (do not use these as subheadings — write continuous prose):
1. Opening: establish the significance and timeliness of the research topic
2. Background: what is known about the topic and why a systematic review
   is needed now
3. Gap statement: what the existing literature lacks that this review addresses
4. Objectives: the purpose of this review stated clearly
5. Research questions: state all {rq_count} research questions explicitly
   using their exact locked text

Requirements:
- 700–900 words
- Academic third person throughout
- Past tense for what studies have done; present tense for what evidence shows
- Do not use bullet points or numbered lists
- The research questions must appear verbatim as locked in the scaffold preamble
- Do not cite specific papers — this is background, not evidence review
- End with a one-sentence overview of the review's structure

=== END OF INTRODUCTION WRITING INSTRUCTIONS ===
```





## 13. Writing: Methods Sections

**Model:** Deepseek 
**Called:** 4 times (2.1 Search, 2.2 Criteria, 2.3 Selection, 2.4 Extraction)  
**Purpose:** Methods narrative  
**Note:** Search queries and PICO table are auto-formatted from DB, not AI-written

### Prompt — 2.3 Study Selection (most complex methods section)

```
{SCAFFOLD_PREAMBLE — REGISTRY OMITTED}

[SECTION LABEL BLOCK — all prior sections]

=== NOW WRITE: SECTION 2.3 — STUDY SELECTION PROCESS ===
=== Do NOT repeat content from sections already written above. ===

Write Section 2.3 describing the study selection process for this review.

Include:
- The two-stage screening process (title/abstract then full-text)
- That title/abstract screening used an automated approach with a
  confidence threshold of {confidence_threshold} for automatic decisions
- That papers below this threshold were flagged for manual researcher review
- That PDFs were retrieved via multi-source waterfall
  (Unpaywall, PMC, Semantic Scholar, arXiv, Europe PMC) supplemented
  by researcher-uploaded files
- That full-text screening used the retrieved PDF text where available,
  with extended abstracts used where PDFs could not be obtained
- That {auto_included_count} papers were confirmed at the title/abstract
  stage with high confidence (>={auto_include_floor}) without requiring
  full-text assessment
- That following full-text screening, {paper_count} papers were presented
  to the researcher for final confirmation with AI-generated selection
  rationales; {user_excluded_count} papers were excluded at this stage
- Reference the PRISMA 2020 flow diagram for counts

Requirements:
- 300–380 words
- Past tense throughout
- Do not use bullet points
- Factual and methodologically precise

=== END OF 2.3 WRITING INSTRUCTIONS ===
```

### Expected Output

```json
(raw text, ~250 words)

"Study selection proceeded in two stages. In the first stage, titles
and abstracts of all deduplicated records were screened against the
predefined inclusion and exclusion criteria using an automated
confidence-threshold approach. Each record received a relevance score
between 0 and 1; records scoring at or above 0.72 received automatic
inclusion or exclusion decisions, while those below this threshold
were flagged for manual researcher review. Records scoring at or
above 0.92 were confirmed as eligible without requiring full-text
assessment, given the unambiguous relevance indicated at the abstract
stage (n=47).

Full texts were retrieved for all remaining eligible records via
a sequential open-access source waterfall comprising Unpaywall,
PubMed Central, Semantic Scholar, arXiv, and Europe PMC, supplemented
by direct researcher uploads for records that automated retrieval
could not locate. Where full texts remained unavailable after
retrieval attempts, extended abstracts were used and these records
are noted as such in the study characteristics table.

Full-text screening applied the inclusion and exclusion criteria
to the retrieved document content. Following full-text assessment,
110 records were eligible for inclusion. These were presented to
the lead researcher with AI-generated selection rationales explaining
the relevance of each paper to the specific research questions.
Following researcher review, 8 records were excluded at this stage
(reasons documented in Appendix C), yielding a final included corpus
of 55 studies. The complete selection process is illustrated in the
PRISMA 2020 flow diagram (Figure 1)."
```

---

## 14. Writing: Results — Study Selection

**Model:** Deepseek 
**Called:** Once  
**Purpose:** PRISMA narrative using locked counts  
**Key constraint:** Every number must come from `scaffold['prisma_counts']`

### Prompt

```
{SCAFFOLD_PREAMBLE — REGISTRY OMITTED}

[SECTION LABEL BLOCK]

=== NOW WRITE: SECTION 3.1 — STUDY SELECTION RESULTS ===
=== Do NOT repeat content from sections already written above. ===
=== Use ONLY the exact counts from the locked scaffold. Do not round or approximate. ===

Write Section 3.1 reporting study selection results.

PRISMA COUNTS TO USE (use these exact numbers, no others):
Scopus retrieved:       {scopus_retrieved}
After deduplication:    {after_dedup}
Passed T/A screening:   {passed_ta}
PDFs retrieved:         {pdfs_retrieved}
Abstract only:          {abstract_only}
Passed full-text:       {passed_fulltext}
Excluded by researcher: {user_excluded}
Final included:         {final_included}

Requirements:
- Report counts in narrative form following the PRISMA stages
- Reference Figure 1 (PRISMA flow diagram) for the visual representation
- Note that {abstract_only} studies were assessed using extended abstracts
  and are identified as such in Table 2
- Note the reasons for exclusion at full-text stage are detailed in Appendix C
- 180–230 words
- Do not use bullet points

=== END OF 3.1 WRITING INSTRUCTIONS ===
```

### Expected Output

```json
(raw text)

"Database searching of Scopus across five Boolean queries retrieved
847 records (Figure 1). Following deduplication, 634 unique records
remained for screening. Title and abstract screening excluded 484
records as not meeting the inclusion criteria, leaving 150 records
for full-text assessment. Of these, full texts were successfully
retrieved for 115 records; the remaining 35 were assessed using
extended abstracts and are identified accordingly in the study
characteristics table (Table 2). Full-text screening excluded 40
records, with reasons detailed in Appendix C. The 110 remaining
records were presented to the lead researcher for final confirmation,
accompanied by AI-generated selection rationales. Following
researcher review, 8 records were excluded at this stage (4 deemed
out of scope upon closer examination, 2 with methodology concerns,
and 2 identified as presenting findings already comprehensively
covered by higher-quality included studies). The final included
corpus comprised 55 studies."
```

---

## 15. Writing: Results — Synthesis by Theme

**Model:** Deepseek 
**Called:** Once — longest writing call  
**Purpose:** Assemble all reconciled theme texts with transitions  
**Key input:** All `ThemeSynthesis.reconciled_text` records

### Prompt

```
{SCAFFOLD_PREAMBLE — FULL WITH REGISTRY}

[SECTION LABEL BLOCK — all prior sections]

=== NOW WRITE: SECTION 3.5 — SYNTHESIS OF FINDINGS ===
=== Do NOT repeat content from sections already written above. ===

Write Section 3.5 presenting the thematic synthesis of findings.

You are provided with the pre-written synthesis for each identified theme.
Your task is to:
1. Write a brief orienting paragraph introducing the {theme_count} themes
2. Present each theme as a clearly labelled subsection
3. Use the provided reconciled synthesis text for each theme as the body
   of each subsection — you may lightly edit for transitions but do not
   substantially change the content or evidence claims
4. Add transitional sentences between themes where relevant
5. End with a brief integrating paragraph noting cross-theme patterns

THEME SYNTHESES (use these in order):
{all_reconciled_texts_with_theme_names}

Requirements:
- Subsection headings for each theme (formatted as: 3.5.1, 3.5.2, etc.)
- The reconciled text for each theme must be preserved accurately
- Evidence language must match the locked evidence grades in the preamble
- All citations must be from the paper registry only
- Do not introduce new findings not present in the provided syntheses
- Total length: 2200–3,000 words depending on number of themes

=== END OF 3.5 WRITING INSTRUCTIONS ===
```

---

## 16. Writing: Discussion

**Model:** Deepseek 
**Called:** Once — largest context window call  
**Purpose:** Interpret findings, address all RQs, situate in broader context  
**Key constraint:** Must explicitly address every locked RQ by name

### Prompt

```
{SCAFFOLD_PREAMBLE — FULL WITH REGISTRY}

[SECTION LABEL BLOCK — all 11 prior sections, clearly labelled]

=== NOW WRITE: SECTION 4 — DISCUSSION ===
=== Do NOT repeat content from any section already written above. ===
=== The Results sections above contain the evidence. Discussion interprets it. ===

Write the Discussion section.

You must explicitly address each research question by name:
RQ1: {rq1_text}
RQ2: {rq2_text}
RQ3: {rq3_text}

Structure (write as continuous prose, not with these as subheadings):
1. Open with principal finding — what does this review's evidence collectively
   demonstrate about {primary_term}?
2. Address RQ1 explicitly — use the phrase "Regarding RQ1..."
3. Address RQ2 explicitly — use the phrase "Turning to RQ2..."
4. Address RQ3 explicitly — use the phrase "With respect to RQ3..."
5. Discuss the main contradictions identified in the synthesis and their
   methodological explanations
6. Situate findings in the broader literature beyond the included corpus
   (use general academic framing, not specific citations to non-included papers)
7. Implications for practice and policy
8. Limitations of the evidence base (distinct from limitations of this review,
   which appear in the Conclusion)

Requirements:
- 1000–1,300 words
- Discussion interprets and synthesises; it does not re-report results
- Any citation must be from the paper registry
- Past tense for what studies did; present tense for what evidence shows
- Do not use bullet points

=== END OF DISCUSSION WRITING INSTRUCTIONS ===
```

---

## 17. Writing: Conclusion

**Model:** Deepseek 
**Called:** Once  
**Purpose:** Summary, direct RQ answers, review limitations, future research  
**Scaffold:** Reduced (no registry — conclusion does not cite individual papers)

### Prompt

```
{SCAFFOLD_PREAMBLE — REGISTRY OMITTED}

[SECTION LABEL BLOCK]

=== NOW WRITE: SECTION 5 — CONCLUSION ===
=== Do NOT repeat content from any section already written above. ===

Write the Conclusion section.

Structure (continuous prose):
1. One-paragraph summary of what this review found
2. Direct answers to each research question (2–3 sentences each):
   RQ1: {rq1_text}
   RQ2: {rq2_text}
   RQ3: {rq3_text}
3. Limitations of THIS REVIEW (not the evidence base — that is in Discussion):
   - Include: {abstract_only_count} papers assessed from abstracts only
   - Include: grey literature not searched (conference proceedings, theses, reports)
   - Include: single database search (Scopus only)
   - Include: language restriction to English
   - Include: AI-assisted screening and extraction introduces potential for
     systematic errors different from human reviewer error
4. Recommendations for future research (2–3 specific gaps identified in synthesis)

Requirements:
- 550–700 words
- Do not introduce new evidence
- Do not cite individual papers
- The RQ answers should be direct and declarative
- Future research recommendations should be specific, not generic

=== END OF CONCLUSION WRITING INSTRUCTIONS ===
```

---

## 18. Writing: Abstract

**Model:** Deepseek 
**Called:** Once — written last after complete draft exists  
**Purpose:** Structured abstract summarising the complete review  
**Key rule:** Written after all other sections — reflects what is actually in the document

### Prompt

```
{SCAFFOLD_PREAMBLE — FULL WITH REGISTRY}

[COMPLETE DRAFT — all 13 sections in labelled blocks]

=== NOW WRITE: STRUCTURED ABSTRACT ===
=== The abstract must accurately reflect the complete document above. ===
=== Do NOT introduce findings not present in the document above. ===

Write a structured abstract for this systematic literature review.

Use exactly these five section labels as bold headings:
Background | Objectives | Methods | Results | Conclusions

Requirements per section:
- Background: 2–3 sentences on why this topic matters and why a review is needed
- Objectives: state the {rq_count} research questions concisely
- Methods: Scopus database, date range {start_year}–{end_year}, final N={final_included}
  papers, note two-stage screening and thematic synthesis approach
- Results: {final_included} studies included, {theme_count} themes identified,
  name the themes and their evidence grades, note key finding
- Conclusions: 2–3 sentences on implications and research gaps

Total word count: 280–350 words
Do not use bullet points within sections.
Use the exact locked theme names from the scaffold preamble.
All counts must match the locked PRISMA counts exactly.

=== END OF ABSTRACT WRITING INSTRUCTIONS ===
```

### Expected Output

```markdown
**Background**
Digital marketplace environments have been associated with elevated
consumer vulnerability outcomes, yet the mechanisms through which
digital contexts amplify vulnerability remain poorly characterised
across the empirical literature. A systematic synthesis of this
growing body of evidence is needed to inform both consumer protection
policy and intervention design.

**Objectives**
This review aimed to examine: (1) to what extent digital marketplace
environments amplify consumer vulnerability compared to traditional
retail contexts; (2) what individual-level factors mediate the
relationship between digital market exposure and vulnerability outcomes;
and (3) which intervention strategies have demonstrated effectiveness
in reducing consumer vulnerability in digital market settings.

**Methods**
A systematic search of the Scopus database was conducted in [month year]
using five Boolean queries developed through AI-assisted synonym
expansion. Studies published between 2010 and 2024 were eligible.
Following two-stage screening of 847 records and researcher confirmation,
55 empirical studies were included. Data were extracted and synthesised
using a thematic approach incorporating dialectical synthesis procedures.

**Results**
Fifty-five studies from 18 countries were included, spanning
cross-sectional surveys (n=22), qualitative designs (n=15), RCTs (n=8),
and mixed-methods studies (n=10). Six themes were identified: Platform
Design and Exploitation Mechanisms (Established); Digital Literacy as
Vulnerability Mediator (Emerging); Regulatory Frameworks and Enforcement
(Insufficient); Consumer Protection Awareness (Emerging); Age and
Cognitive Vulnerability (Established); and Intervention Effectiveness
(Emerging). Platform design features were the most consistently
evidenced determinant of vulnerability across multiple study designs
and national contexts.

**Conclusions**
Digital marketplace environments demonstrably amplify consumer
vulnerability through multiple interacting mechanisms, with platform
design features constituting the most modifiable determinant. Future
research should prioritise cross-cultural replication of mediation
findings and experimental evaluation of regulatory intervention effects.
```

---
