# SLR Engine — Optional Feature Toggles

Complete specification for user-controlled inclusion/exclusion of
advanced analysis features. Covers: intake form changes, pipeline
routing, prompt modifications, scaffold changes, writing chain
adaptations, and cost implications per configuration.

---

## Overview

Users can toggle 5 optional feature groups on or off before the
pipeline starts. Defaults are chosen to produce a publishable SLR
without requiring advanced methodological knowledge.

```
FEATURE GROUP 1: Theoretical Framework Anchoring
FEATURE GROUP 2: TCCM Analysis
FEATURE GROUP 3: Conceptual Model + Propositions
FEATURE GROUP 4: Future Research Agenda (structured)
FEATURE GROUP 5: Sensitivity Analysis
```

Each feature is independent. They can be mixed in any combination.
However, some features depend on others — dependencies are shown
in the dependency matrix below.

---

## Dependency Matrix

```
Feature 1 (Theory)         → no dependencies
Feature 2 (TCCM)           → no dependencies
Feature 3 (Conceptual Model) → REQUIRES Feature 1 (Theory)
                              if Feature 1 off: Feature 3 is disabled
Feature 4 (Future Research) → no dependencies
                              but is RICHER if Feature 2 enabled
                              (TCCM gaps feed into the agenda)
Feature 5 (Sensitivity)    → no dependencies
```

If user enables Feature 3 but disables Feature 1:
→ System shows warning: "Conceptual Model requires Theoretical
  Framework Anchoring. Feature 1 has been automatically enabled."
→ Feature 1 is force-enabled.

---


## Part A — Intake Form Changes

### New Section: Analysis Options

Add a collapsible section at the bottom of the intake form titled
**"Advanced Analysis Options"** with a subtitle:
*"These options enhance publishability for top-tier journals.
Each adds a small cost (shown). All are optional."*

```
┌─────────────────────────────────────────────────────────────────┐
│ ADVANCED ANALYSIS OPTIONS                                       │
│ Toggle on the analyses you want included in your SLR.           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ ☑ Theoretical Framework Anchoring              +$0.13/run       │
│   Anchors synthesis in a named theoretical lens. Identifies     │
│   which theories the literature uses and what is absent.        │
│   Required for: Conceptual Model.                               │
│                                                                  │
│   Theoretical lens: [text field — leave blank to auto-identify] │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ ☑ TCCM Analysis                                 +$0.09/run      │
│   Theory-Characteristics-Context-Methods framework analysis.    │
│   Required by JAMS, JBR, IMR, JIBS and other top journals.     │
│   Adds a structured gap analysis table to your review.          │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ ☑ Conceptual Model + Propositions               +$0.17/run      │
│   Proposes a theoretical model diagram and formal propositions. │
│   Requires: Theoretical Framework Anchoring (auto-enabled).     │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ ☑ Structured Future Research Agenda             +$0.04/run      │
│   Generates specific research directions by TCCM dimension.     │
│   Richer when TCCM Analysis is also enabled.                   │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ ☑ Sensitivity Analysis                          +$0.01/run      │
│   Tests whether conclusions change when high-risk studies       │
│   are removed. Recommended for all reviews.                     │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ Estimated total run cost:  $1.85  (all features enabled)        │
│ Cost updates dynamically as you toggle features.                │
└─────────────────────────────────────────────────────────────────┘
```

Cost estimate updates live via AlpineJS as user toggles features.

---

## Part B — Review Model Changes

Add the following boolean fields to the `Review` model:

```python
# apps/reviews/models.py

class Review(models.Model):
    # ... existing fields ...

    # Feature toggles — set at intake, never changed after pipeline starts
    enable_theoretical_framework = BooleanField(default=True)
    enable_tccm                  = BooleanField(default=True)
    enable_conceptual_model      = BooleanField(default=True)
    enable_future_research       = BooleanField(default=True)
    enable_sensitivity_analysis  = BooleanField(default=True)

    # Theoretical lens — set at intake or during theory confirmation window
    theoretical_lens             = CharField(max_length=300, blank=True)
    # blank = auto-identify from corpus
```

---

## Part C — Pipeline Routing Changes

### In tasks.py — run_post_extraction chain

```python
@shared_task
def run_post_extraction(review_id: int):
    review = Review.objects.get(id=review_id)

    # Always run
    bibliometric_analysis(review_id)
    generate_phase1_graphs(review_id)

    # Conditional: TCCM aggregation
    if review.enable_tccm:
        run_tccm_aggregation(review_id)

    # Always run
    build_scaffold(review_id)

    # Conditional: Theory landscape
    if review.enable_theoretical_framework:
        run_theory_landscape(review_id)
        # May pause for theory confirmation if no lens specified
        # Pipeline resumes when user confirms or timeout fires

    # Always run
    run_evidence_matrix(review_id)
    run_dialectical_synthesis(review_id)

    # Conditional: Conceptual model (requires theory)
    if review.enable_conceptual_model and review.enable_theoretical_framework:
        run_conceptual_model_specification(review_id)

    # Always run phase 2 graphs
    generate_phase2_graphs(review_id)

    # Conditional: Sensitivity analysis computation
    if review.enable_sensitivity_analysis:
        run_sensitivity_analysis(review_id)

    # Write document
    write_all_sections(review_id)
    run_consistency_check(review_id)
    format_references(review_id)
    build_docx(review_id)
    finalize(review_id)
```

---

## Part D — Scaffold Changes

The scaffold stores which features are active. Every writing call
reads this to know what data is available.

```python
# pipeline/scaffold_builder.py

def build_scaffold(review_id: int) -> dict:
    review = Review.objects.get(id=review_id)

    scaffold = {
        # ... all existing scaffold keys ...

        # Feature flags — writing calls read these
        'features': {
            'theoretical_framework': review.enable_theoretical_framework,
            'tccm':                  review.enable_tccm,
            'conceptual_model':      review.enable_conceptual_model,
            'future_research':       review.enable_future_research,
            'sensitivity_analysis':  review.enable_sensitivity_analysis,
        },

        # These keys only populated if feature enabled
        'theoretical_framework': {} if not review.enable_theoretical_framework
                                  else None,  # populated by theory landscape call
        'tccm_summary':          {} if not review.enable_tccm
                                  else None,  # populated by TCCM aggregation
        'propositions':          [] if not review.enable_conceptual_model
                                  else None,  # populated by model spec call
        'sensitivity_results':   {} if not review.enable_sensitivity_analysis
                                  else None,  # populated by sensitivity call
    }
    return scaffold
```

---


## Part F — Writing Chain Routing

The section writing order adapts based on features.

### Full order (all features enabled):

```
1.  Introduction
2.  Methods 2.1 — Search Strategy
3.  Methods 2.2 — Selection Criteria
4.  Methods 2.3 — Study Selection Process
5.  Methods 2.4 — Data Extraction and Synthesis
6.  Results 3.1 — Study Selection (PRISMA)
7a. Results 3.2a — Study Characteristics
7b. Results 3.2b — TCCM Analysis           ← Feature 2 only
8.  Results 3.3 — Quality Assessment
9.  Results 3.4 — Bibliometric Findings
10. Results 3.5 — Thematic Synthesis
11. Results 3.6 — Subgroup Analysis
    Results 3.6.4 — Sensitivity subsection  ← Feature 5 only
12. Conceptual Framework (Section 4)        ← Feature 3 only
13. Discussion (Section 5)
14. Future Research Agenda (Section 6)      ← Feature 4 only
15. Conclusion
16. Abstract (last)
```

### Adaptive section numbering:

When features are disabled, section numbers shift. The document
builder handles this automatically by computing the actual section
number from the enabled features list rather than hardcoding numbers.

```python
# pipeline/document_builder.py

def get_section_order(review):
    sections = [
        ('introduction',            True),
        ('methods_search',          True),
        ('methods_criteria',        True),
        ('methods_selection',       True),
        ('methods_extraction',      True),
        ('results_prisma',          True),
        ('results_characteristics', True),
        ('results_tccm',            review.enable_tccm),
        ('results_quality',         True),
        ('results_biblio',          True),
        ('results_synthesis',       True),
        ('results_subgroup',        True),
        ('conceptual_framework',    review.enable_conceptual_model
                                    and review.enable_theoretical_framework),
        ('discussion',              True),
        ('future_research',         review.enable_future_research),
        ('conclusion',              True),
    ]
    # Return only enabled sections in order
    return [s for s, enabled in sections if enabled]
```

---

## Part G — Modified Writing Prompts

### How each prompt changes per feature state

Rather than maintaining 2^5 = 32 separate prompt versions, each
prompt has conditional blocks that insert or omit content based
on the features dict from the scaffold.

The pattern used throughout:

```python
def build_section_prompt(section_key, review, scaffold, written):
    features = scaffold['features']

    preamble = build_scaffold_preamble(scaffold, section_key)
    prev     = format_section_label_block(written)
    instr    = SECTION_INSTRUCTIONS[section_key](features, scaffold)

    return preamble + prev + instr
```

Each section instruction function accepts `features` dict and
conditionally includes or excludes content blocks.

---

### Section 1 — Introduction

**When Feature 1 (Theory) is ON:**
Paragraph 2-3 introduces the primary theoretical lens by name.
Paragraph 4 references absent theories from theory landscape call.

**When Feature 1 (Theory) is OFF:**
Paragraph 2-3 describes the literature without anchoring to a
specific theoretical framework.
Paragraph 4 identifies gaps without theoretical framing.

#### Prompt — Feature 1 ON

```
{SCAFFOLD_PREAMBLE — REGISTRY OMITTED}

{SECTION_LABEL_BLOCK}

=== NOW WRITE: SECTION 1 — INTRODUCTION ===
=== Do NOT cite individual papers from the paper registry. ===

Write the Introduction section.

SOURCE DATA:
Objectives:               {objectives}
Primary theoretical lens: {primary_theoretical_lens}
Lens corpus coverage:     {lens_pct_of_corpus}%
Absent theories:          {absent_theories_formatted}
Research questions:       {rq_count}

STRUCTURE:

Paragraph 1 — SIGNIFICANCE AND TIMELINESS (100-120 words)
Establish why this topic matters now with a specific opening claim.

Paragraph 2-3 — BACKGROUND AND THEORETICAL CONTEXT (200-250 words)
What is known. What theories have been applied.
Introduce {primary_theoretical_lens} as the primary theoretical
lens used in this field and in this review. Explain what it offers.
Do not cite individual included papers.

Paragraph 4 — GAPS AND MOTIVATION (120-150 words)
What the literature lacks. Why a review is needed now.
Reference the theoretical gaps identified in this corpus:
{absent_theories_formatted}
These absent frameworks motivate this review's analytical approach.

Paragraph 5 — OBJECTIVES AND RQs (80-100 words)
State purpose. Present all {rq_count} RQs using EXACT locked text:
{rq_numbered_list}

Paragraph 6 — STRUCTURE (40-50 words)
One sentence overview of the paper's organisation.

REQUIREMENTS:
- 700-900 words total
- Academic third person, no bullet points
- Theoretical lens introduced by name in paragraphs 2-3
- RQs verbatim as locked
- No bullet points or numbered lists in output

=== END INTRODUCTION INSTRUCTIONS ===
```

#### Prompt — Feature 1 OFF

```
{SCAFFOLD_PREAMBLE — REGISTRY OMITTED}

{SECTION_LABEL_BLOCK}

=== NOW WRITE: SECTION 1 — INTRODUCTION ===
=== Do NOT cite individual papers from the paper registry. ===

Write the Introduction section.

SOURCE DATA:
Objectives:               {objectives}
Research questions:       {rq_count}

STRUCTURE:

Paragraph 1 — SIGNIFICANCE AND TIMELINESS (100-120 words)
Establish why this topic matters now with a specific opening claim.

Paragraph 2-3 — BACKGROUND AND STATE OF KNOWLEDGE (200-250 words)
What is already known. What prior reviews have established.
What theoretical perspectives have been applied in general terms.
Do not anchor to a specific named theory.
Do not cite individual included papers.

Paragraph 4 — GAPS AND MOTIVATION (120-150 words)
What the literature lacks. Why a systematic review is needed now.
Identify 2-3 concrete gaps (contextual, methodological, empirical).

Paragraph 5 — OBJECTIVES AND RQs (80-100 words)
State purpose. Present all {rq_count} RQs using EXACT locked text:
{rq_numbered_list}

Paragraph 6 — STRUCTURE (40-50 words)
One sentence overview of the paper's organisation.

REQUIREMENTS:
- 700-900 words total
- Academic third person, no bullet points
- RQs verbatim as locked

=== END INTRODUCTION INSTRUCTIONS ===
```

---

### Section Methods 2.4 — Data Extraction and Synthesis

**When Feature 1 (Theory) is ON:** names theoretical lens,
describes theory extraction, describes theory-anchored synthesis.

**When Feature 2 (TCCM) is ON:** names TCCM framework, cites
Paul et al. (2021), describes TCCM coding.

**When both are OFF:** describes extraction and synthesis without
theoretical or TCCM framing.

#### Prompt — Both Features ON

```
{SCAFFOLD_PREAMBLE — REGISTRY OMITTED}

{SECTION_LABEL_BLOCK}

=== NOW WRITE: SECTION 2.4 — DATA EXTRACTION AND SYNTHESIS ===
=== Do NOT repeat content from any section already written above. ===

Write Section 2.4.

SOURCE DATA:
Primary theoretical lens: {primary_theoretical_lens}
Total confirmed papers:   {final_included}
Synthesis method:         Thematic synthesis with dialectical argumentation
TCCM framework:           Paul et al. (2021)
Quality framework:        CASP-adapted, 5 dimensions, 0-10 scale
Evidence grades:          Established/Emerging/Contested/Insufficient
Themes identified:        {theme_count}

WRITE:

Paragraph 1 — DATA EXTRACTION (120-150 words):
Four categories of output per study:
(1) Detailed narrative summary (500-600 words) capturing study
    context, methodology, specific findings, and contribution
(2) Structured data fields for characteristics table: study design,
    population, intervention, outcomes, sample size, country, setting
(3) Methodological quality scores using adapted CASP framework
(4) TCCM coding classifying each study's theoretical foundations,
    sample characteristics, contextual scope, and methodological
    approach following Paul et al. (2021)

Paragraph 2 — QUALITY ASSESSMENT (80-100 words):
Adapted CASP: five dimensions scored 0-2. Total 0-10.
Risk of bias: low (8-10), moderate (5-7), high (0-4).
Six rubric variants by study design type.

Paragraph 3 — SYNTHESIS METHOD (150-200 words):
Thematic synthesis as primary approach.
{primary_theoretical_lens} as theoretical lens, present in
{lens_pct_of_corpus}% of included studies.
Themes identified inductively from extraction data.
Dialectical procedure per theme: Advocate, Critic, Reconciler.
Evidence grades: Established (>=60%, multiple designs),
Emerging (30-59%), Contested (contradictory), Insufficient (<30%).

REQUIREMENTS:
- 350-500 words
- Cite Paul et al. (2021) for TCCM
- Name {primary_theoretical_lens} explicitly
- No bullet points

=== END OF 2.4 INSTRUCTIONS ===
```

#### Prompt — Feature 1 ON, Feature 2 OFF

```
{SCAFFOLD_PREAMBLE — REGISTRY OMITTED}

{SECTION_LABEL_BLOCK}

=== NOW WRITE: SECTION 2.4 — DATA EXTRACTION AND SYNTHESIS ===
=== Do NOT repeat content from any section already written above. ===

Write Section 2.4.

SOURCE DATA:
Primary theoretical lens: {primary_theoretical_lens}
Total confirmed papers:   {final_included}
Synthesis method:         Thematic synthesis with dialectical argumentation
Quality framework:        CASP-adapted, 5 dimensions, 0-10 scale
Evidence grades:          Established/Emerging/Contested/Insufficient
Themes identified:        {theme_count}

WRITE:

Paragraph 1 — DATA EXTRACTION (100-120 words):
Three categories of output per study:
(1) Detailed narrative summary (500-600 words)
(2) Structured data fields for characteristics table
(3) Methodological quality scores using adapted CASP framework
Also: theoretical framework coding classifying which theories
each study draws on and how (primary/secondary/implicit usage).

Paragraph 2 — QUALITY ASSESSMENT (80-100 words):
Same as above.

Paragraph 3 — SYNTHESIS METHOD (150-200 words):
Thematic synthesis anchored in {primary_theoretical_lens}.
Dialectical procedure: Advocate, Critic, Reconciler per theme.
Each theme's Reconciler synthesis includes a theoretical paragraph
on what the evidence reveals about {primary_theoretical_lens}.
Evidence grades as above.

REQUIREMENTS:
- 320-460 words
- Name {primary_theoretical_lens} explicitly
- No TCCM citation (feature disabled)
- No bullet points

=== END OF 2.4 INSTRUCTIONS ===
```

#### Prompt — Both Features OFF

```
{SCAFFOLD_PREAMBLE — REGISTRY OMITTED}

{SECTION_LABEL_BLOCK}

=== NOW WRITE: SECTION 2.4 — DATA EXTRACTION AND SYNTHESIS ===
=== Do NOT repeat content from any section already written above. ===

Write Section 2.4.

SOURCE DATA:
Total confirmed papers:   {final_included}
Synthesis method:         Thematic synthesis with dialectical argumentation
Quality framework:        CASP-adapted, 5 dimensions, 0-10 scale
Evidence grades:          Established/Emerging/Contested/Insufficient
Themes identified:        {theme_count}

WRITE:

Paragraph 1 — DATA EXTRACTION (100-120 words):
Three categories of output per study:
(1) Detailed narrative summary (500-600 words)
(2) Structured data fields for characteristics table including
    study design, population, intervention, outcomes, sample size,
    country, and setting
(3) Methodological quality scores using adapted CASP framework

Paragraph 2 — QUALITY ASSESSMENT (80-100 words):
Adapted CASP: five dimensions scored 0-2. Total 0-10.
Risk of bias: low (8-10), moderate (5-7), high (0-4).

Paragraph 3 — SYNTHESIS METHOD (120-150 words):
Thematic synthesis as primary approach.
Themes identified inductively from extraction data.
Dialectical procedure: Advocate builds strongest case, Critic
identifies weaknesses, Reconciler writes final synthesis.
Evidence grades: Established, Emerging, Contested, Insufficient.

REQUIREMENTS:
- 300-400 words
- No theoretical lens named (feature disabled)
- No TCCM citation (feature disabled)
- No bullet points

=== END OF 2.4 INSTRUCTIONS ===
```

---

### Section Results 3.2 — Study Characteristics

**When Feature 2 (TCCM) is ON:**
Section is 3.2a (characteristics) + 3.2b (TCCM analysis).

**When Feature 2 (TCCM) is OFF:**
Section is 3.2 only (characteristics table + narrative).
No TCCM subsections. Shorter.

#### Prompt — Feature 2 OFF (characteristics only)

```
{SCAFFOLD_PREAMBLE — FULL WITH REGISTRY}

{SECTION_LABEL_BLOCK}

=== NOW WRITE: SECTION 3.2 — STUDY CHARACTERISTICS ===
=== Do NOT repeat content from any section already written above. ===

Write Section 3.2 presenting study characteristics.
Table 2 (study characteristics) has been inserted before this text.

SOURCE DATA:
Total studies:           {final_included}
Design distribution:     {by_design_formatted}
Year range:              {year_min} to {year_max}
Geographic distribution: {by_country_top5_formatted}
Sample size range:       {sample_size_min} to {sample_size_max}
Abstract-only:           {abstract_only}

WRITE:
Four paragraphs covering: temporal and design distribution,
geographic distribution (noting abstract-only studies), sample
size variation and population focus, setting and context variation.
Cite specific papers from registry as exemplars.

REQUIREMENTS:
- 350-450 words
- No TCCM analysis (feature disabled)
- Cite papers using short_ref format
- No bullet points

=== END OF 3.2 INSTRUCTIONS ===
```

When Feature 2 is ON, use the full 3.2a + 3.2b prompts from the
ghostwriter prompts document.

---

### Section Results 3.5 — Thematic Synthesis

**When Feature 1 (Theory) is ON:**
Each theme subsection ends with the theoretical paragraph from the
Reconciler output. A cross-theme theoretical synthesis subsection
is added at the end.

**When Feature 1 (Theory) is OFF:**
Reconciler texts are used but the theoretical paragraphs at the
end of each are omitted. No cross-theme theoretical synthesis
subsection. The synthesis is empirical only.

#### Prompt — Feature 1 ON

(Full prompt as in ghostwriter prompts document — unchanged)

#### Prompt — Feature 1 OFF

```
{SCAFFOLD_PREAMBLE — FULL WITH REGISTRY}

{SECTION_LABEL_BLOCK}

=== NOW WRITE: SECTION 3.5 — THEMATIC SYNTHESIS ===
=== Do NOT repeat content from any section already written above. ===
=== Do NOT alter evidence claims in the reconciled texts. ===

Write Section 3.5 presenting the thematic synthesis.

SOURCE DATA:
Total themes:          {theme_count}
Theme evidence grades: {theme_grades_formatted}

RECONCILED SYNTHESIS TEXTS:
{all_reconciled_texts_formatted}

Note: Each reconciled text may end with a theoretical paragraph
connecting findings to a theoretical framework. Because
theoretical framework analysis is not included in this review,
OMIT the final theoretical paragraph from each reconciled text.
Present only the empirical synthesis content.

STRUCTURE:

Opening paragraph (80-100 words):
Introduce the {theme_count} themes with their evidence grades.
State they are presented in order of evidence strength.

Theme subsections (one per theme):
Subheading: 3.5.[n] [Theme Name] ([Evidence Grade])
Body: reconciled text for this theme — omit the final
theoretical paragraph if present.

Cross-theme integration (150-200 words):
After all theme subsections write 3.5.{theme_count + 1}
Cross-Theme Patterns.
Identify the overarching empirical pattern across all themes.
This is NOT a theoretical argument — it is an empirical
observation about what the collective findings show.
Do not make theoretical claims. Describe what is collectively
found.

REQUIREMENTS:
- Subsection headings 3.5.1, 3.5.2, etc.
- Evidence language matching locked grades
- All citations from paper registry only
- No theoretical paragraphs (feature disabled)
- No bullet points

=== END OF 3.5 INSTRUCTIONS ===
```

---

### Section Results 3.6 — Subgroup Analysis

**When Feature 5 (Sensitivity) is ON:**
Section includes subsection 3.6.4 — Sensitivity Analysis.

**When Feature 5 (Sensitivity) is OFF:**
Section has only 3.6.1, 3.6.2, 3.6.3. No sensitivity subsection.

#### Prompt — Feature 5 OFF

```
{SCAFFOLD_PREAMBLE — FULL WITH REGISTRY}

{SECTION_LABEL_BLOCK}

=== NOW WRITE: SECTION 3.6 — SUBGROUP ANALYSIS ===
=== Do NOT repeat content from any section already written above. ===

Write Section 3.6 presenting subgroup analyses.

SOURCE DATA:
By study design:    {by_design_formatted}
By country:         {by_country_formatted}
By year groups:     {by_year_groups_formatted}
Year subgroup:      {year_subgroup_eligible}
Country subgroup:   {country_subgroup_note}

WRITE:
Subsection 3.6.1 — By Study Design (120-150 words)
Subsection 3.6.2 — By Country and Region (100-130 words)
Subsection 3.6.3 — By Publication Period (100-130 words)

Note: Sensitivity analysis is not included in this review.

REQUIREMENTS:
- 380-480 words total
- Subsections 3.6.1, 3.6.2, 3.6.3 only
- No sensitivity subsection
- No bullet points

=== END OF 3.6 INSTRUCTIONS ===
```

---

### Section Conceptual Framework

Only generated when Feature 3 (Conceptual Model) is ON AND
Feature 1 (Theory) is ON.

If both are OFF: section does not exist in the document.
If Feature 1 is OFF and Feature 3 is ON: Feature 1 is
force-enabled (dependency rule).

No prompt needed for OFF state — section is skipped entirely.

---

### Section Discussion

**When Feature 1 (Theory) is ON:**
Discussion includes: theoretical contributions paragraph
referencing propositions (P1, P2, P3) and third-order synthesis.

**When Feature 1 (Theory) is OFF:**
Discussion omits: theoretical contributions paragraph.
Follows: principal finding → RQ answers → practical implications
→ limitations of evidence base.

**When Feature 3 (Model) is ON:**
Discussion references the conceptual framework by section number.
Does NOT re-describe it.

**When Feature 3 (Model) is OFF:**
No reference to conceptual framework section.

#### Prompt — Feature 1 ON, Feature 3 ON
(Full prompt as in ghostwriter prompts document — unchanged)

#### Prompt — Feature 1 OFF, Feature 3 OFF

```
{SCAFFOLD_PREAMBLE — FULL WITH REGISTRY}

{SECTION_LABEL_BLOCK}

=== NOW WRITE: SECTION [N] — DISCUSSION ===
=== Section 3.5 contains the evidence. Discussion INTERPRETS. ===
=== Do NOT re-report results. Do NOT repeat content above. ===

Write the Discussion section.

SOURCE DATA:
RQ answers:           {rq_answers_formatted}

STRUCTURE:

Paragraph 1 — PRINCIPAL FINDING (120-150 words):
The single most important finding of this review.
Strong specific claim about {primary_topic}.

Paragraph 2 — RQ1 ANSWER (150-200 words):
Open with: "Regarding RQ1..."
State RQ1 verbatim: {rq1_text}
Answer directly using {rq1_answer}.
Cite supporting papers from registry.

Paragraph 3 — RQ2 ANSWER (150-200 words):
Open with: "Turning to RQ2..."
Same structure.

{rq3_paragraph_if_applicable}

Paragraph — PRACTICAL IMPLICATIONS (100-130 words):
Implications for practitioners, platforms, regulators.
Ground each in a specific finding.

Paragraph — LIMITATIONS OF EVIDENCE BASE (100-130 words):
Limitations of what the field has produced — not this review.
Western dominance, cross-sectional dominance, pre-registration rates.

REQUIREMENTS:
- 800-1,000 words (shorter than full version — no theory paragraph)
- Every RQ addressed using "Regarding RQ[n]" phrasing
- All citations from paper registry only
- No theoretical contributions paragraph (feature disabled)
- No reference to conceptual framework (feature disabled)
- No bullet points

=== END DISCUSSION INSTRUCTIONS ===
```

#### Prompt — Feature 1 ON, Feature 3 OFF

```
{SCAFFOLD_PREAMBLE — FULL WITH REGISTRY}

{SECTION_LABEL_BLOCK}

=== NOW WRITE: SECTION [N] — DISCUSSION ===
=== Do NOT repeat content from any section already written above. ===

Write the Discussion section.

SOURCE DATA:
RQ answers:              {rq_answers_formatted}
Propositions:            {propositions_formatted}
Primary lens:            {primary_theoretical_lens}
Third-order synthesis:   {third_order_synthesis_text}
TCCM key gaps:           {tccm_key_gaps_or_omit}

STRUCTURE:

Paragraph 1 — PRINCIPAL FINDING (120-150 words)

Paragraph 2 — RQ1 ANSWER (150-200 words): "Regarding RQ1..."
Paragraph 3 — RQ2 ANSWER (150-200 words): "Turning to RQ2..."
{rq3_paragraph_if_applicable}

Paragraph — THEORETICAL CONTRIBUTIONS (150-200 words):
What this review contributes theoretically.
Reference propositions by number (P1, P2, P3).
Use third-order synthesis as signature theoretical claim.
Reference absent theories as next frontier.
Note: No conceptual model diagram to reference (feature disabled).
State propositions as key theoretical contribution.

Paragraph — PRACTICAL IMPLICATIONS (100-130 words)
Paragraph — LIMITATIONS OF EVIDENCE BASE (100-130 words)

REQUIREMENTS:
- 900-1,100 words
- Propositions referenced by number
- No reference to conceptual framework diagram
- No bullet points

=== END DISCUSSION INSTRUCTIONS ===
```

---

### Section Future Research Agenda

**When Feature 4 (Future Research) is ON AND Feature 2 (TCCM) is ON:**
Full structured agenda with TCCM dimensions.
Uses `tccm_future_research` from TCCM aggregation JSON.

**When Feature 4 is ON AND Feature 2 is OFF:**
Structured agenda without TCCM framing.
Uses synthesis gaps, Critic texts, and proposition testing needs.
Organised by theme rather than TCCM dimension.

**When Feature 4 is OFF:**
No dedicated future research section.
Future research integrated into Conclusion (2 paragraphs).

#### Prompt — Feature 4 ON, Feature 2 OFF

```
{SCAFFOLD_PREAMBLE — REGISTRY OMITTED}

{SECTION_LABEL_BLOCK}

=== NOW WRITE: SECTION [N] — FUTURE RESEARCH AGENDA ===
=== Do NOT repeat content from any section already written above. ===
=== Each direction must be specific — no generic statements. ===

Write the Future Research Agenda section.
Note: TCCM analysis is not included in this review so the agenda
is organised by evidence theme rather than TCCM dimension.

SOURCE DATA:
Synthesis gaps (from Critic passes and Insufficient themes):
{synthesis_gaps_formatted}

Theoretical gaps (from theory landscape):
{theoretical_gaps_or_omit}

Propositions needing empirical testing:
{propositions_or_omit}

STRUCTURE:

Opening paragraph (60-80 words):
State that this agenda derives from two sources: themes rated
Insufficient or Contested in the synthesis, and gaps identified
in the Critic analyses of each theme.

For each Insufficient or Contested theme — one subsection:
[N].1 Gaps in {theme_name} (100-120 words per theme)
  - What specific question needs answering
  - What methodology would answer it
  - What it would contribute

{propositions_testing_subsection_or_omit}
If Feature 1 enabled: add subsection on testing P1, P2, P3.
If Feature 1 disabled: omit this subsection.

Closing paragraph (60-80 words):
State the highest-priority single direction.

REQUIREMENTS:
- 400-550 words total
- Subsections by theme not TCCM dimension
- No TCCM table reference (feature disabled)
- Every direction specific and grounded
- No bullet points within subsections

=== END FUTURE RESEARCH INSTRUCTIONS ===
```

#### Prompt — Feature 4 OFF (integrated into Conclusion)

When Feature 4 is OFF, the Conclusion prompt gains two extra
paragraphs:

```
[Added to Conclusion prompt when Feature 4 is OFF:]

After the limitations paragraph, write two additional paragraphs:

Paragraph — FUTURE RESEARCH DIRECTIONS (120-150 words):
State 3-4 specific research directions that emerge from this
review. Derive from Insufficient/Contested themes and synthesis
gaps. Be specific — name what is needed and why.
{propositions_testing_note_if_feature1_on}

Paragraph — CLOSING STATEMENT (60-80 words):
Strong closing claim about what this review establishes and
what the field now needs.
```

---

### Section Conclusion

**When Feature 4 (Future Research) is ON:**
Conclusion is shorter — future research is in its own section.
Conclusion = summary + RQ answers + review limitations + closing.

**When Feature 4 (Future Research) is OFF:**
Conclusion is longer — incorporates 2 future research paragraphs.
See modification above.

**When Feature 1 (Theory) is ON:**
Conclusion references theoretical propositions as contribution.

**When Feature 1 (Theory) is OFF:**
Conclusion states empirical contribution only.

#### Prompt — Feature 1 ON, Feature 4 ON

(Full prompt as in ghostwriter prompts document)

#### Prompt — Feature 1 OFF, Feature 4 ON

```
{SCAFFOLD_PREAMBLE — REGISTRY OMITTED}

{SECTION_LABEL_BLOCK}

=== NOW WRITE: SECTION [N] — CONCLUSION ===
=== Do NOT repeat Discussion or Future Research content above. ===

Write the Conclusion.

SOURCE DATA:
RQ answers:         {rq_answers_formatted}
Final included:     {final_included}
Theme count:        {theme_count}
Review limitations: [as specified]

WRITE:
Paragraph 1 — SUMMARY (100-120 words): what review found overall.
Paragraph 2 — RQ ANSWERS (120-150 words): direct declarative answers.
Paragraph 3 — CONTRIBUTION (80-100 words):
  Empirical contribution — what the synthesis establishes.
  No theoretical propositions (feature disabled).
Paragraph 4 — REVIEW LIMITATIONS (100-120 words)
Paragraph 5 — CLOSING (60-80 words)

REQUIREMENTS:
- 380-500 words
- No proposition references (feature disabled)
- No bullet points

=== END CONCLUSION INSTRUCTIONS ===
```

#### Prompt — Feature 1 OFF, Feature 4 OFF

```
{SCAFFOLD_PREAMBLE — REGISTRY OMITTED}

{SECTION_LABEL_BLOCK}

=== NOW WRITE: SECTION [N] — CONCLUSION ===
=== Includes future research directions (no separate section). ===
=== Do NOT repeat Discussion content above. ===

Write the Conclusion.

SOURCE DATA:
RQ answers:         {rq_answers_formatted}
Synthesis gaps:     {synthesis_gaps_formatted}
Final included:     {final_included}
Theme count:        {theme_count}
Review limitations: [as specified]

WRITE:
Paragraph 1 — SUMMARY (100-120 words)
Paragraph 2 — RQ ANSWERS (120-150 words)
Paragraph 3 — CONTRIBUTION (80-100 words): empirical contribution.
Paragraph 4 — REVIEW LIMITATIONS (100-120 words)
Paragraph 5 — FUTURE RESEARCH (120-150 words):
  3-4 specific directions from synthesis gaps and Insufficient themes.
  Be specific — not generic.
Paragraph 6 — CLOSING (60-80 words)

REQUIREMENTS:
- 500-650 words (longer — incorporates future research)
- No theoretical propositions
- Future research integrated not in separate section
- No bullet points

=== END CONCLUSION INSTRUCTIONS ===
```

---

### Abstract

**When Feature 2 (TCCM) is ON:**
Methods sentence mentions TCCM framework (Paul et al., 2021).

**When Feature 3 (Model) is ON:**
Results sentence mentions conceptual model and propositions count.

**When both are OFF:**
Abstract methods and results are shorter and simpler.

#### Prompt — All Features ON

(Full prompt as in ghostwriter prompts document)

#### Prompt — Features 1, 2, 3 OFF, 4 ON, 5 varies

```
{SCAFFOLD_PREAMBLE — FULL WITH REGISTRY}

{SECTION_LABEL_BLOCK — ALL prior sections}

=== NOW WRITE: STRUCTURED ABSTRACT ===
=== Must accurately reflect the document above. ===
=== All counts must match locked PRISMA counts exactly. ===
=== All theme names must match locked names exactly. ===

Write structured abstract using these five bold headings:

**Background**
**Objectives**
**Methods**
**Results**
**Conclusions**

Background (50-60 words): significance and why review is needed.
No theoretical lens framing (feature disabled).

Objectives (40-50 words): the {rq_count} research questions.

Methods (55-65 words):
Scopus, {start_year}-{end_year}, {final_included} studies included.
Thematic synthesis with dialectical argumentation.
No TCCM citation (feature disabled).

Results (80-100 words):
{final_included} studies, {theme_count} themes identified.
Name all themes with evidence grades.
No conceptual model mention (feature disabled).
Principal finding in one sentence.

Conclusions (50-60 words):
What review establishes. Most consequential gap. Forward statement.
No proposition reference (feature disabled).

REQUIREMENTS:
- 280-340 words (slightly shorter — fewer features)
- Bold headings exactly as shown
- All counts locked exactly
- All theme names locked exactly
- No bullet points

=== END ABSTRACT INSTRUCTIONS ===
```

---

## Part H — Consistency Checker Changes

The consistency checker adapts its checklist based on features.

```
ALWAYS CHECKED (regardless of features):
1. PRISMA counts match locked values
2. Canonical term used, no banned synonyms
3. Theme names match locked names exactly
4. Evidence grades match locked grades
5. All citations from paper registry only
6. All RQs addressed using "Regarding RQ[n]"
7. No user-excluded papers cited
8. Discussion does not verbatim repeat Results

CHECKED ONLY IF Feature 1 (Theory) IS ON:
9.  Primary theoretical lens named consistently
10. Propositions stated accurately (P1, P2, P3)
11. Theoretical paragraphs present at end of each theme in 3.5
12. Third-order synthesis present in 3.5

CHECKED ONLY IF Feature 2 (TCCM) IS ON:
13. TCCM percentages consistent with aggregation data
14. Paul et al. (2021) cited in Methods 2.4
15. TCCM subsections present in 3.2b

CHECKED ONLY IF Feature 3 (Model) IS ON:
16. Conceptual framework section present (Section 4)
17. Propositions referenced by number in Discussion

CHECKED ONLY IF Feature 4 (Future Research) IS ON:
18. Future Research section present and structured by correct
    dimension (TCCM if F2 enabled, theme-based if F2 disabled)

CHECKED ONLY IF Feature 5 (Sensitivity) IS ON:
19. Sensitivity subsection 3.6.4 present
20. Sensitivity results match computed sensitivity data
```

#### Modified Consistency Checker Prompt

```
You are a systematic copy-editor for a systematic literature review.

ACTIVE FEATURES IN THIS REVIEW:
{features_active_list}

=== UNIVERSAL SCAFFOLD RULES (always apply) ===

Canonical term: "{primary_term}"
Banned synonyms: {banned_terms}
Locked PRISMA counts: {prisma_counts_formatted}
Locked theme names: {theme_names_list}
Locked evidence grades: {evidence_grades_formatted}
Paper registry: {paper_registry_formatted}
Research questions: {rq_list}
User-excluded papers: {user_excluded_ids}

{theoretical_rules_block_or_empty}
{tccm_rules_block_or_empty}
{model_rules_block_or_empty}
{future_research_rules_block_or_empty}
{sensitivity_rules_block_or_empty}

=== COMPLETE DRAFT ===
{full_draft}

=== CHECK FOR ALL VIOLATIONS ===

Check categories that apply based on ACTIVE FEATURES above.
Return ONLY valid JSON. No preamble. No markdown fences.

[
  {
    "section": "section key",
    "issue_type": "wrong_count | wrong_term | wrong_theme_name |
                   wrong_evidence_grade | unregistered_citation |
                   unanswered_rq | excluded_paper_cited |
                   verbatim_repetition | wrong_proposition |
                   wrong_tccm_pct | inconsistent_lens_name |
                   missing_section | missing_subsection",
    "original_text": "exact text with problem",
    "fix": "corrected text",
    "explanation": "one sentence"
  }
]
```

Where the conditional rule blocks are:

```python
def build_checker_prompt(review, scaffold, full_draft):
    features = scaffold['features']

    theory_block = '''
=== FEATURE 1 RULES (Theoretical Framework) ===
Primary lens: "{primary_theoretical_lens}" — must appear
with this exact name throughout.
Propositions: {propositions_formatted}
Check: lens consistent, propositions accurate, theoretical
paragraphs present at end of each theme in 3.5,
third-order synthesis present.
''' if features['theoretical_framework'] else ''

    tccm_block = '''
=== FEATURE 2 RULES (TCCM) ===
TCCM percentages: {tccm_key_percentages}
Check: percentages consistent in 3.2b, Paul et al. (2021)
cited in 2.4, TCCM subsections 3.2.1-3.2.4 present.
''' if features['tccm'] else ''

    model_block = '''
=== FEATURE 3 RULES (Conceptual Model) ===
Check: Section 4 (Conceptual Framework) present,
propositions referenced by number (P1, P2) in Discussion.
''' if features['conceptual_model'] else ''

    future_block = '''
=== FEATURE 4 RULES (Future Research) ===
Check: Dedicated future research section present and
organised by {"TCCM dimension" if tccm_enabled else "theme"}.
''' if features['future_research'] else ''

    sensitivity_block = '''
=== FEATURE 5 RULES (Sensitivity Analysis) ===
Sensitivity results: {sensitivity_results_formatted}
Check: Subsection 3.6.4 present, sensitivity results match
computed data.
''' if features['sensitivity_analysis'] else ''

    return CHECKER_TEMPLATE.format(
        features_active_list=get_active_features_list(features),
        theory_block=theory_block,
        tccm_block=tccm_block,
        model_block=model_block,
        future_block=future_block,
        sensitivity_block=sensitivity_block,
        full_draft=full_draft,
        **scaffold
    )
```

---
