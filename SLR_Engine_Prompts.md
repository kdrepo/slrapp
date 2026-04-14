# SLR Engine — All LLM Prompts & Expected Outputs

**Stack:** Gemini 2.5 Pro (reasoning) · Gemini 2.5 Flash (screening)  
**Total LLM calls per run:** ~782 across 19 distinct prompt types  
**Runtime cost:** ~$1.59 per SLR run (50–60 included papers)

---

## Table of Contents

1. [RQ Formalization](#1-rq-formalization)
2. [Scopus Query Generation](#2-scopus-query-generation)
3. [T/A Batch Screening (Flash)](#3-ta-batch-screening-flash)
4. [Fulltext Screening + Rationale (Pro)](#4-fulltext-screening--rationale-pro)
5. [Merged Extraction + Quality (Pro Batch)](#5-merged-extraction--quality-pro-batch)
6. [Canonical Term Identification](#6-canonical-term-identification)
7. [Evidence Matrix + Theme Identification](#7-evidence-matrix--theme-identification)
8. [Advocate Pass](#8-advocate-pass)
9. [Critic Pass](#9-critic-pass)
10. [Reconciler Pass](#10-reconciler-pass)
11. [Thin Theme Synthesis](#11-thin-theme-synthesis)
12. [Writing: Introduction](#12-writing-introduction)
13. [Writing: Methods Sections](#13-writing-methods-sections)
14. [Writing: Results — Study Selection](#14-writing-results--study-selection)
15. [Writing: Results — Synthesis by Theme](#15-writing-results--synthesis-by-theme)
16. [Writing: Discussion](#16-writing-discussion)
17. [Writing: Conclusion](#17-writing-conclusion)
18. [Writing: Abstract](#18-writing-abstract)
19. [Consistency Checker](#19-consistency-checker)
20. [APA Reference Formatter](#20-apa-reference-formatter)
21. [JSON Correction Prompt (Universal)](#21-json-correction-prompt-universal)
22. [Scaffold Preamble (Universal Prefix)](#22-scaffold-preamble-universal-prefix)

---

## Prompt Conventions

Every prompt marked **[SCAFFOLD]** receives the full scaffold preamble prepended before the section-specific instructions. The preamble is defined in Section 22 and is not repeated in each section.

Variables in `{curly_braces}` are runtime values injected from the database.

`[SECTION LABEL BLOCK]` refers to the labelled context of all previously written sections, formatted as shown in Section 22.

---

---

## 1. RQ Formalization

**Model:** Gemini 2.5 Pro  
**Called:** Once, immediately after form submission, before pipeline starts  
**Purpose:** Convert user's free-text objectives into precise, answerable Research Questions  
**Tokens (approx):** 700 input / 300 output

### Prompt

```
You are a systematic review methodologist specialising in social science research.

A researcher has provided the following information for a systematic literature review:

RESEARCH OBJECTIVES:
{objectives}

PICO FRAMEWORK:
Population:    {pico_population}
Intervention:  {pico_intervention}
Comparison:    {pico_comparison}
Outcomes:      {pico_outcomes}

INCLUSION CRITERIA:
{inclusion_criteria}

EXCLUSION CRITERIA:
{exclusion_criteria}

---

Your task: Generate 2–4 precise, answerable Research Questions for this systematic review.

Requirements for each RQ:
- Must be directly answerable from empirical peer-reviewed literature
- Must be specific enough to guide inclusion/exclusion decisions
- Must align with the PICO framework provided
- Must be distinct from each other (no overlap)
- Use clear academic language

Classify each RQ as one of: descriptive | comparative | causal | exploratory

Return ONLY valid JSON. No preamble. No markdown fences.

[
  {
    "rq": "exact research question text",
    "type": "descriptive|comparative|causal|exploratory",
    "pico_alignment": "one sentence explaining which PICO elements this RQ addresses"
  }
]
```

### Expected Output

```json
[
  {
    "rq": "To what extent do digital marketplace environments amplify consumer vulnerability compared to traditional retail contexts?",
    "type": "comparative",
    "pico_alignment": "Addresses Population (adult consumers) and Comparison (traditional vs digital retail) with Outcome (vulnerability amplification)"
  },
  {
    "rq": "What individual-level factors mediate the relationship between digital market exposure and consumer vulnerability outcomes?",
    "type": "causal",
    "pico_alignment": "Addresses Population and Intervention (digital exposure) with Outcome (vulnerability mediators)"
  },
  {
    "rq": "Which intervention strategies have demonstrated effectiveness in reducing consumer vulnerability in digital market settings?",
    "type": "descriptive",
    "pico_alignment": "Addresses Intervention (strategies) and Outcome (reduction in vulnerability) within Population"
  }
]
```

---

## 2. Scopus Query Generation

**Model:** Gemini 2.5 Pro  
**Called:** Once, early pipeline  
**Purpose:** Generate 5 distinct Boolean Scopus queries covering different angles of the topic  
**Tokens (approx):** 800 input / 700 output

### Prompt

```
You are a systematic review librarian specialising in social science database searching.

A researcher needs 5 distinct Boolean search queries for the Scopus academic database.

RESEARCH OBJECTIVES:
{objectives}

INCLUSION CRITERIA:
{inclusion_criteria}

EXCLUSION CRITERIA:
{exclusion_criteria}

DATE RANGE: {start_year} to {end_year}

---

Generate exactly 5 Boolean search queries using Scopus TITLE-ABS-KEY field codes.

Requirements:
- Each query must target a different angle: (1) core terms, (2) synonyms,
  (3) related constructs, (4) population-specific, (5) outcome-specific
- Use TITLE-ABS-KEY() field code for all terms
- Use AND, OR, NOT operators correctly
- Use quotes for multi-word phrases
- Include truncation (*) where appropriate
- Queries should be complementary, not redundant
- Each query should retrieve a distinct subset of relevant literature

Return ONLY valid JSON. No preamble. No markdown fences.

[
  {
    "query": "exact Scopus Boolean query string",
    "focus": "core|synonyms|constructs|population|outcomes",
    "rationale": "one sentence explaining what this query adds"
  }
]
```

### Expected Output

```json
[
  {
    "query": "TITLE-ABS-KEY(\"consumer vulnerability\" AND (\"digital market*\" OR \"e-commerce\" OR \"online retail\"))",
    "focus": "core",
    "rationale": "Primary terms directly matching the research topic"
  },
  {
    "query": "TITLE-ABS-KEY((\"vulnerable consumer*\" OR \"consumer disadvantage\" OR \"consumer harm\") AND (\"digital platform*\" OR \"online marketplace\"))",
    "focus": "synonyms",
    "rationale": "Alternative terminology used across disciplines for the same construct"
  },
  {
    "query": "TITLE-ABS-KEY((\"digital literacy\" OR \"online trust\" OR \"cognitive vulnerability\") AND \"consumer vulnerability\" AND (\"protection\" OR \"intervention\"))",
    "focus": "constructs",
    "rationale": "Related theoretical constructs that mediate or moderate vulnerability"
  },
  {
    "query": "TITLE-ABS-KEY(\"consumer vulnerability\" AND (\"elder*\" OR \"low income\" OR \"financial exclusion\" OR \"disability\") AND \"digital\")",
    "focus": "population",
    "rationale": "Specific vulnerable population groups most studied in this literature"
  },
  {
    "query": "TITLE-ABS-KEY((\"dark pattern*\" OR \"deceptive design\" OR \"pricing manipulation\" OR \"algorithmic harm\") AND \"consumer\" AND \"vulnerability\")",
    "focus": "outcomes",
    "rationale": "Specific harmful outcome mechanisms in digital contexts"
  }
]
```

---

## 3. T/A Batch Screening (Flash)

**Model:** Gemini 2.5 Flash  
**Called:** ~585 times (one per paper), submitted as batch job  
**Purpose:** Screen each paper's title and abstract against inclusion/exclusion criteria  
**Tokens (approx):** 800 input / 120 output per paper  
**Total batch tokens:** ~480,000 input / ~70,000 output

### Prompt

```
You are screening papers for a systematic literature review.

INCLUSION CRITERIA:
{inclusion_criteria}

EXCLUSION CRITERIA:
{exclusion_criteria}

---

PAPER TO SCREEN:
Title: {title}
Abstract: {abstract}

---

Screen this paper against the criteria above.

Confidence calibration:
- 1.0 = paper explicitly and unambiguously meets or violates all criteria
- 0.9 = very clear match/non-match, minor wording ambiguity only
- 0.8 = clear but one criterion requires inference from limited information
- 0.7 = probable match/non-match but abstract lacks confirming detail
- below 0.7 = genuinely uncertain — abstract is ambiguous or insufficient

Return ONLY valid JSON. No preamble. No markdown fences.

{
  "decision": "included" or "excluded",
  "confidence": 0.0 to 1.0,
  "reason": "one sentence explaining the decision",
  "criterion_failed": "exact exclusion criterion violated if excluded, or null"
}
```

### Expected Output — Included (High Confidence)

```json
{
  "decision": "included",
  "confidence": 0.91,
  "reason": "Cross-sectional study examining consumer vulnerability determinants in e-commerce context with quantitative outcomes, meeting all stated criteria",
  "criterion_failed": null
}
```

### Expected Output — Excluded (Confident)

```json
{
  "decision": "excluded",
  "confidence": 0.88,
  "reason": "Study examines B2B procurement vulnerability, not consumer-facing digital markets",
  "criterion_failed": "B2B contexts excluded per exclusion criterion 3"
}
```

### Expected Output — Flagged (Low Confidence)

```json
{
  "decision": "excluded",
  "confidence": 0.61,
  "reason": "Abstract describes consumer behavior study but does not clearly specify digital market context or vulnerability as primary outcome",
  "criterion_failed": null
}
```

> Papers with confidence < 0.72 are flagged regardless of decision and surfaced for user manual review.

---

## 4. Fulltext Screening + Rationale (Pro)

**Model:** Gemini 2.5 Pro  
**Called:** ~90 times (papers with 0.72–0.91 T/A confidence)  
**Purpose:** Definitive inclusion decision based on actual PDF text + generate selection rationale  
**Tokens (approx):** 3,800 input / 250 output per paper  
**Key feature:** Rationale generated here — no separate call needed

### Prompt

```
You are conducting full-text screening for a systematic literature review.

REVIEW OBJECTIVES:
{objectives}

RESEARCH QUESTIONS:
{research_questions_formatted}

INCLUSION CRITERIA:
{inclusion_criteria}

EXCLUSION CRITERIA:
{exclusion_criteria}

{abstract_only_note}

---

PAPER TEXT (methods, results, discussion):
{pdf_text}

---

Make a definitive inclusion decision based on the full text above.

For selection_rationale: if including, write 2–3 sentences explaining why this
specific paper is relevant to the objectives and research questions above.
- Reference which specific RQ(s) it addresses
- Mention the study design and what it contributes
- Be specific to THIS review's objectives, not generic
- Write in plain language the researcher can read and act on
- Leave empty string if excluding

Return ONLY valid JSON. No preamble. No markdown fences.

{
  "decision": "included" or "excluded",
  "confidence": 0.0 to 1.0,
  "reason": "one sentence explaining the decision",
  "study_type": "RCT|qualitative|cross-sectional|cohort|mixed-methods|case-study|other",
  "criterion_failed": "exact criterion violated if excluded, or null",
  "selection_rationale": "2-3 sentence rationale if included, empty string if excluded"
}
```

> `{abstract_only_note}` is populated with `"NOTE: Only the abstract is available for this paper. Apply a lower confidence threshold and flag if uncertain."` when `paper.grobid_parsed = False`.

### Expected Output — Included with Rationale

```json
{
  "decision": "included",
  "confidence": 0.89,
  "reason": "Qualitative study examining elderly consumer responses to deceptive platform design with clear vulnerability outcomes measured",
  "study_type": "qualitative",
  "criterion_failed": null,
  "selection_rationale": "This paper directly addresses RQ2 by providing qualitative evidence of how platform design features systematically disadvantage elderly consumers through cognitive overload mechanisms. Its phenomenological approach (N=42 in-depth interviews) complements the quantitative studies in this corpus by offering depth on lived experience of vulnerability that survey instruments cannot capture. The study's UK context and 2021 data collection are particularly relevant given the post-pandemic acceleration of digital retail adoption."
}
```

### Expected Output — Excluded

```json
{
  "decision": "excluded",
  "confidence": 0.93,
  "reason": "Study examines consumer vulnerability in physical retail environments only; digital context absent throughout methods and results",
  "study_type": "cross-sectional",
  "criterion_failed": "Must involve digital marketplace or online platform context",
  "selection_rationale": ""
}
```

---

## 5. Merged Extraction + Quality (Pro Batch)

**Model:** Gemini 2.5 Pro  
**Called:** ~55 times (one per confirmed paper), submitted as batch  
**Purpose:** Extract structured data AND assess quality in single call — PDF read once, two outputs  
**Tokens (approx):** 4,200 input / 900 output per paper  
**Total batch tokens:** ~231,000 input / ~49,500 output

### Prompt

```
You are extracting data and assessing methodological quality for a systematic review.
Read this paper carefully and return a single JSON object with exactly two top-level
keys: "extraction" and "quality".

Return ONLY valid JSON. No preamble. No markdown fences. No trailing commas.

{
  "extraction": {
    "study_design": "RCT|quasi-experimental|cohort|cross-sectional|case-control|qualitative|mixed-methods|case-study",
    "population": "description of study participants/subjects",
    "intervention": "what was tested, manipulated, or studied",
    "comparison": "comparator or control condition, or null if absent",
    "outcomes": [
      {
        "name": "outcome name",
        "measure": "how it was measured",
        "result": "quantitative result or qualitative finding",
        "direction": "positive|negative|neutral|mixed",
        "p_value": "if reported, else null",
        "effect_size": "if reported, else null"
      }
    ],
    "sample_size": integer or null,
    "study_country": "country name or 'Multi-country'",
    "setting": "hospital|community|online|laboratory|school|workplace|other",
    "key_findings": "exactly 3 sentences summarising the main results",
    "limitations": "author-stated limitations",
    "funding": "funding source or null",
    "year": integer
  },
  "quality": {
    "study_type": "same value as study_design above",
    "total_score": integer 0-10,
    "dim_objectives": integer 0-2,
    "dim_design": integer 0-2,
    "dim_data": integer 0-2,
    "dim_analysis": integer 0-2,
    "dim_bias": integer 0-2,
    "risk_of_bias": "low|moderate|high",
    "strengths": ["strength 1", "strength 2"],
    "weaknesses": ["weakness 1", "weakness 2"]
  }
}

Quality scoring rubric — each dimension scored 0 (poor), 1 (adequate), 2 (strong):
- dim_objectives: Is the research question clearly stated? Is the study design justified?
- dim_design:     Is the design appropriate for the question? Is it described in sufficient detail?
- dim_data:       Is data collection rigorous? Are instruments justified? Is process transparent?
- dim_analysis:   Is the analytic approach systematic and appropriate? Would it be reproducible?
- dim_bias:       Are limitations acknowledged? Is reflexivity demonstrated (qualitative)?

Total score = sum of all five dimensions (max 10).
Risk of bias: low = 8-10, moderate = 5-7, high = 0-4.

---

PAPER TEXT:
{pdf_text}
```

### Expected Output

```json
{
  "extraction": {
    "study_design": "cross-sectional",
    "population": "UK adults aged 18-75 who had made at least one online purchase in the past 3 months (N=2,847)",
    "intervention": "Exposure to digital marketplace environments with varying levels of deceptive design features",
    "comparison": "Traditional retail shopping behavior as self-reported baseline",
    "outcomes": [
      {
        "name": "Consumer vulnerability score",
        "measure": "Validated 12-item Consumer Vulnerability Scale (CVS-12)",
        "result": "Mean CVS-12 score 3.8 (SD 1.2) in digital context vs 2.1 (SD 0.9) in traditional retail",
        "direction": "negative",
        "p_value": "p<0.001",
        "effect_size": "Cohen's d = 0.72"
      },
      {
        "name": "Complaint behavior",
        "measure": "Self-reported formal complaint filing in past 12 months",
        "result": "Only 12% of those reporting harm had filed a formal complaint",
        "direction": "negative",
        "p_value": null,
        "effect_size": null
      }
    ],
    "sample_size": 2847,
    "study_country": "United Kingdom",
    "setting": "online",
    "key_findings": "Digital marketplace environments were associated with significantly higher consumer vulnerability scores compared to traditional retail contexts (d=0.72, p<0.001). Digital literacy was the strongest individual-level moderator, accounting for 23% of variance in vulnerability scores after controlling for age and income. Complaint behavior was markedly lower than expected given reported harm levels, suggesting substantial under-reporting of consumer detriment.",
    "limitations": "Cross-sectional design precludes causal inference; self-reported digital literacy may not reflect actual competency; sample over-represented urban and educated respondents",
    "funding": "UK Consumer Affairs Research Council",
    "year": 2019
  },
  "quality": {
    "study_type": "cross-sectional",
    "total_score": 8,
    "dim_objectives": 2,
    "dim_design": 2,
    "dim_data": 2,
    "dim_analysis": 1,
    "dim_bias": 1,
    "risk_of_bias": "low",
    "strengths": [
      "Large nationally representative sample with quota sampling",
      "Validated measurement instrument (CVS-12) with strong psychometric properties",
      "Rigorous data collection with professional survey firm"
    ],
    "weaknesses": [
      "Cross-sectional design cannot establish causation",
      "Self-reported digital literacy measure does not capture actual skill level",
      "Convenience elements in sampling despite quota controls"
    ]
  }
}
```

---

## 6. Canonical Term Identification

**Model:** Gemini 2.5 Pro  
**Called:** Once, during scaffold assembly  
**Purpose:** Identify the single most used primary term across the corpus and ban its synonyms from writing  
**Tokens (approx):** 8,000 input / 400 output

### Prompt

```
You are analysing terminology consistency across a corpus of academic papers for a
systematic review. Your task is to identify the canonical primary term used in this
field and which synonymous terms should be avoided to maintain consistency.

REVIEW TOPIC: {objectives}

KEYWORD FREQUENCIES ACROSS CORPUS:
{keyword_frequency_json}

PAPER TITLES SAMPLE (first 20):
{paper_titles_sample}

---

Identify:
1. The single most precise and consistently used primary term for the core construct
2. Synonyms that mean the same thing and should not be used alongside the primary term
3. Related but distinct terms that are acceptable (different constructs, not synonyms)

Return ONLY valid JSON. No preamble. No markdown fences.

{
  "primary": "the canonical term to use throughout the document",
  "synonyms_to_ban": ["term1", "term2"],
  "acceptable_related": ["term3", "term4"],
  "rationale": "one sentence explaining the choice"
}
```

### Expected Output

```json
{
  "primary": "consumer vulnerability",
  "synonyms_to_ban": [
    "consumer vulnerabilities",
    "consumer fragility",
    "consumer susceptibility",
    "vulnerable consumerism"
  ],
  "acceptable_related": [
    "vulnerable consumers",
    "consumer welfare",
    "consumer harm",
    "digital vulnerability"
  ],
  "rationale": "Consumer vulnerability appears in 89% of included papers as a singular noun and is the established term in Journal of Consumer Research and Journal of Marketing since Baker et al. (2005)"
}
```

---

## 7. Evidence Matrix + Theme Identification

**Model:** Gemini 2.5 Pro  
**Called:** Once, start of synthesis  
**Purpose:** Identify 5–8 themes from all extraction data and assign evidence grades  
**Tokens (approx):** 12,000 input / 1,200 output

### Prompt

```
You are identifying synthesis themes for a systematic literature review.

REVIEW OBJECTIVES:
{objectives}

RESEARCH QUESTIONS:
{research_questions_formatted}

TOTAL INCLUDED PAPERS: {total_papers}

---

EXTRACTED DATA FROM ALL {total_papers} INCLUDED PAPERS:
{all_extractions_json}

---

Identify 5–8 distinct themes that emerge from this evidence corpus.

For each theme:
- Name it precisely using 3–6 words
- List which paper scopus_ids address it
- Calculate what percentage of the corpus it represents
- Note which study designs are represented
- Assess whether findings are convergent or divergent across papers
- Assign an evidence grade

Evidence grading rules:
- Established:   >= 60% of included papers AND multiple study designs agree
- Emerging:      30-60% of papers, mostly one study design
- Contested:     Papers in corpus directly contradict each other on this theme
- Insufficient:  < 30% of papers OR only 1-2 papers total

Themes must be:
- Grounded in actual findings across multiple papers (not a single study)
- Distinct from each other (minimal overlap in paper assignments)
- Directly relevant to the research questions
- Ordered by paper count descending

Return ONLY valid JSON. No preamble. No markdown fences.

[
  {
    "theme_name": "precise 3-6 word theme name",
    "paper_ids": ["SCOPUS:id1", "SCOPUS:id2"],
    "paper_count": integer,
    "pct": float (percentage of total corpus),
    "designs": ["design1", "design2"],
    "finding_direction": "convergent|divergent|mixed",
    "evidence_grade": "Established|Emerging|Contested|Insufficient",
    "rationale": "one sentence explaining why this evidence grade was assigned"
  }
]
```

### Expected Output

```json
[
  {
    "theme_name": "Platform Design and Exploitation Mechanisms",
    "paper_ids": ["SCOPUS:85201234", "SCOPUS:85209876", "SCOPUS:85213456"],
    "paper_count": 38,
    "pct": 69.1,
    "designs": ["RCT", "cross-sectional", "qualitative", "mixed-methods"],
    "finding_direction": "convergent",
    "evidence_grade": "Established",
    "rationale": "38 papers across 4 study designs consistently find platform design features amplify vulnerability, meeting both the 60% threshold and multi-design criteria"
  },
  {
    "theme_name": "Digital Literacy as Vulnerability Mediator",
    "paper_ids": ["SCOPUS:85201111", "SCOPUS:85202222"],
    "paper_count": 31,
    "pct": 56.4,
    "designs": ["cross-sectional", "qualitative"],
    "finding_direction": "mixed",
    "evidence_grade": "Emerging",
    "rationale": "56% of corpus but only two study designs, and one RCT found non-significant mediation when controlling for socioeconomic status"
  },
  {
    "theme_name": "Regulatory Frameworks and Enforcement",
    "paper_ids": ["SCOPUS:85205555", "SCOPUS:85206666"],
    "paper_count": 8,
    "pct": 14.5,
    "designs": ["qualitative"],
    "finding_direction": "convergent",
    "evidence_grade": "Insufficient",
    "rationale": "Only 8 papers (14.5%) address regulatory mechanisms, all qualitative, insufficient for substantive evidence claims"
  }
]
```

---

## 8. Advocate Pass

**Model:** Gemini 2.5 Pro  
**Called:** Once per substantive theme (Established/Emerging/Contested)  
**Purpose:** Build the strongest possible case for this theme  
**Tokens (approx):** 4,200 input / 450 output per theme

### Prompt

```
{SCAFFOLD_PREAMBLE}

---

TASK: You are the ADVOCATE for this synthesis theme.

THEME: {theme_name}
EVIDENCE GRADE: {evidence_grade}
PAPERS IN THIS THEME: {paper_count} of {total_papers} total ({pct}%)

EXTRACTION DATA FOR PAPERS IN THIS THEME:
{theme_extractions_json}

---

Build the strongest possible case FOR this theme being well-established
in the literature.

Requirements:
- Cite specific papers by their short_ref (e.g., Baker et al. (2019))
- Apply evidence language rules from the preamble based on the grade above
- Use only papers from the extraction data provided
- Focus on convergent findings and strong evidence
- Write continuous academic prose — no bullet points, no headers
- 200–300 words

Do not start with "This theme" or "The evidence". Begin with the substantive claim.
```

### Expected Output

```json
(raw text, not JSON)

"Growing evidence suggests that platform design features function as
systematic mechanisms of consumer exploitation rather than incidental
characteristics of digital commerce. Smith & Jones (2021) demonstrated
that consumers exposed to dark pattern interfaces reported vulnerability
scores 2.4 times higher than those using standard interfaces (p<0.001,
d=0.68), a finding replicated by Chen et al. (2022) across three
national contexts. Baker et al. (2019) further indicates that the
relationship between platform complexity and vulnerability outcomes is
partially mediated by cognitive load, with elderly consumers showing
disproportionate susceptibility when task demands exceed working memory
capacity. Williams et al. (2020) provides complementary qualitative
evidence, with participants describing a pervasive sense of being
'deliberately confused' by interface design choices that obscure pricing
and limit exit options. The convergence across quantitative and
qualitative methodologies strengthens confidence in this finding,
suggesting platform design mechanisms operate through multiple
psychological pathways simultaneously."
```

---

## 9. Critic Pass

**Model:** Gemini 2.5 Pro  
**Called:** Once per substantive theme, receives Advocate output  
**Purpose:** Challenge the advocate's argument, find weaknesses  
**Tokens (approx):** 4,600 input / 350 output per theme

### Prompt

```
{SCAFFOLD_PREAMBLE}

---

TASK: You are the CRITIC reviewing the following advocate position.

THEME: {theme_name}
EVIDENCE GRADE: {evidence_grade}

--- ADVOCATE TEXT ---
{advocate_text}
--- END ADVOCATE TEXT ---

FULL EXTRACTION DATA FOR THIS THEME:
{theme_extractions_json}

---

Critically examine the advocate position above. Your role is to identify
every legitimate weakness in the argument.

Specifically look for:
- Papers in the evidence set that contradict or qualify the advocate's claims
- Methodological limitations that undermine the strongest assertions
- Claims that are overstated given the actual evidence grade ({evidence_grade})
- Geographic, temporal, or study design confounds the advocate ignored
- Operationalisation differences across studies that make comparison problematic
- Sample characteristics that limit generalisability

Requirements:
- Be specific — name papers and cite exact findings that challenge the advocate
- Do not dismiss findings, explain why they qualify or contradict
- Write continuous academic prose — no bullet points
- 150–250 words
```

### Expected Output

```json
(raw text)

"The advocate position presents a more uniform picture than the evidence
supports. While Smith & Jones (2021) and Chen et al. (2022) show
convergent quantitative results, both studies operationalise platform
design vulnerability differently — Smith uses a composite dark pattern
count while Chen uses a single deceptive interface exposure. This
operationalisation heterogeneity makes the claimed replication
problematic. More substantially, Johnson et al. (2020), the only RCT
in this theme, found that vulnerability scores returned to baseline
levels within two weeks of dark pattern removal, suggesting the effect
may be more transient than the advocate implies. Additionally, all
four studies reporting the strongest effects were conducted in Western
high-income contexts (UK, USA, Australia), and Park & Kim (2021),
the only non-Western study, found substantially smaller effect sizes
in Korean digital markets, raising generalisability concerns the
advocate does not acknowledge. The qualitative evidence cited from
Williams et al. (2020) reflects participant perceptions rather than
measured outcomes, which should be clearly distinguished from the
quantitative effect size evidence."
```

---

## 10. Reconciler Pass

**Model:** Gemini 2.5 Pro  
**Called:** Once per substantive theme, receives both Advocate and Critic  
**Purpose:** Write final publication-ready synthesis resolving the argument  
**Tokens (approx):** 5,100 input / 600 output per theme

### Prompt

```
{SCAFFOLD_PREAMBLE}

---

TASK: You are the RECONCILER. Write the final synthesis for this theme.

THEME: {theme_name}
EVIDENCE GRADE: {evidence_grade}

--- ADVOCATE TEXT ---
{advocate_text}
--- END ADVOCATE ---

--- CRITIC TEXT ---
{critic_text}
--- END CRITIC ---

FULL EXTRACTION DATA:
{theme_extractions_json}

---

Write the definitive synthesis paragraph for this theme for inclusion in
the systematic review.

Requirements:
1. Open with ONE sentence that honestly states what is settled and what
   remains contested — calibrated to the evidence grade ({evidence_grade})
2. Present the strongest evidence, using evidence language appropriate to
   the grade (see preamble rules)
3. Acknowledge the contradictions the critic identified, but explain them
   by context (geography, time period, study design, operationalisation)
   rather than by dismissing papers
4. Every empirical claim must be supported by at least one paper from
   the registry in the preamble
5. End with a clear statement of what this means for the overall review
   and any gaps this theme reveals
6. Write continuous academic prose — no bullet points, no headers
7. 300–400 words
8. Do not start with "This theme" or "The findings"
```

### Expected Output

```json
(raw text)

"Platform design features emerge as a structurally significant
determinant of consumer vulnerability in digital commerce contexts,
though the magnitude and persistence of this effect require
qualification across methodological and geographic boundaries. Convergent
evidence from cross-sectional and experimental studies conducted in
Western contexts (Baker et al., 2019; Smith & Jones, 2021; Chen et al.,
2022) consistently demonstrates that exposure to deceptive interface
elements is associated with substantially elevated vulnerability scores,
with effect sizes in the moderate-to-large range (d=0.52–0.74). The
theoretical coherence of these findings is strengthened by Baker et al.
(2019), which identifies cognitive load as a partial mediating mechanism,
suggesting platform design operates through established psychological
pathways rather than as an artefact of measurement.

However, two important qualifications constrain the generalisability of
this evidence base. First, Johnson et al.'s (2020) RCT found that
measured vulnerability effects dissipated within two weeks of dark
pattern removal, which either suggests a more transient impact than
cross-sectional studies imply or indicates that cross-sectional
instruments capture cumulative exposure effects that experimental
designs miss. This distinction carries material implications for
intervention design. Second, Park & Kim (2021) observed substantially
smaller effects in Korean digital markets, which the authors attribute
to platform regulatory differences and cultural variation in scepticism
towards commercial interfaces — a finding that the predominantly Western
evidence base cannot currently address.

These qualifications do not undermine the core finding but do indicate
that the mechanisms linking platform design to vulnerability are
contextually moderated in ways the current literature has not fully
mapped. For this review, platform design represents the most
consistently evidenced vulnerability mechanism, but future research
should prioritise cross-cultural replication and longitudinal designs
to establish whether effects are transient responses or accumulating
exposures."
```

---

## 11. Thin Theme Synthesis

**Model:** Gemini 2.5 Pro  
**Called:** Once per Insufficient-grade theme (≤2 papers or <30% corpus)  
**Purpose:** Honest brief note on limited evidence — no dialectical passes needed  
**Tokens (approx):** 3,200 input / 300 output

### Prompt

```
{SCAFFOLD_PREAMBLE}

---

TASK: Write a brief synthesis note for a theme with limited evidence.

THEME: {theme_name}
EVIDENCE GRADE: Insufficient
PAPERS IN THIS THEME: {paper_count} ({pct}% of corpus)

EXTRACTION DATA:
{theme_extractions_json}

---

Write an honest, brief synthesis note for this theme.

Requirements:
- Acknowledge the limited evidence base explicitly at the start
- State what the {paper_count} paper(s) show, using language appropriate
  to an Insufficient evidence grade: "preliminary evidence suggests"
- Identify this as a research gap requiring further investigation
- Do not overstate — with {paper_count} papers there is no basis for
  strong claims
- Write continuous academic prose — no bullet points
- 120–180 words
```

### Expected Output

```json
(raw text)

"Regulatory frameworks as a determinant of consumer vulnerability
outcomes remain substantially underexplored in the current literature,
with only two studies addressing this mechanism directly. Preliminary
evidence suggests that regulatory environment moderates the relationship
between digital market exposure and vulnerability outcomes: Jones &
Smith (2019) found that consumers in jurisdictions with active digital
consumer protection enforcement reported significantly greater trust and
lower vulnerability scores than those in comparable markets with weaker
regulatory frameworks, while Baker et al. (2021) observed that
awareness of consumer rights predicted complaint behaviour in Australian
digital markets. However, these two studies represent different national
regulatory contexts — the EU General Data Protection Regulation
framework and Australian Consumer Law respectively — and their
contextual specificity precludes cross-jurisdictional synthesis. The
absence of comparative regulatory research represents a substantive gap
in this literature, particularly given the rapid divergence in digital
consumer protection approaches across jurisdictions following 2020."
```

---

## 12. Writing: Introduction

**Model:** Gemini 2.5 Pro  
**Called:** Once — first writing call  
**Purpose:** Background, motivation, objectives, and RQ statement  
**Tokens (approx):** 3,200 input / 900 output  
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
- 600–900 words
- Academic third person throughout
- Past tense for what studies have done; present tense for what evidence shows
- Do not use bullet points or numbered lists
- The research questions must appear verbatim as locked in the scaffold preamble
- Do not cite specific papers — this is background, not evidence review
- End with a one-sentence overview of the review's structure

=== END OF INTRODUCTION WRITING INSTRUCTIONS ===
```

### Expected Output

```json
(raw text, ~700 words academic prose)

"Digital commerce has fundamentally restructured the conditions under
which consumers make purchasing decisions, introducing asymmetries
of information, algorithmic complexity, and interface design practices
that have no direct precedent in traditional retail environments.
While consumer vulnerability has been studied across diverse contexts
for several decades, the intersection of digital market structures
and vulnerability outcomes has emerged as a distinct and rapidly
growing area of scholarly attention since approximately 2015, driven
by documented harms including manipulative pricing algorithms, dark
pattern interfaces, and the disproportionate targeting of cognitively
or economically disadvantaged population groups...

[continues for ~700 words, ending with RQs stated verbatim and
a sentence on review structure]"
```

---

## 13. Writing: Methods Sections

**Model:** Gemini 2.5 Pro  
**Called:** 4 times (2.1 Search, 2.2 Criteria, 2.3 Selection, 2.4 Extraction)  
**Purpose:** Methods narrative  
**Tokens (approx):** 2,800 input / 500 output each  
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
- That PDFs were retrieved via an automated multi-source waterfall
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
- 200–280 words
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

**Model:** Gemini 2.5 Pro  
**Called:** Once  
**Purpose:** PRISMA narrative using locked counts  
**Tokens (approx):** 3,400 input / 350 output  
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

**Model:** Gemini 2.5 Pro  
**Called:** Once — longest writing call  
**Purpose:** Assemble all reconciled theme texts with transitions  
**Tokens (approx):** 14,000 input / 2,800 output  
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
- Total length: 1,800–3,000 words depending on number of themes

=== END OF 3.5 WRITING INSTRUCTIONS ===
```

---

## 16. Writing: Discussion

**Model:** Gemini 2.5 Pro  
**Called:** Once — largest context window call  
**Purpose:** Interpret findings, address all RQs, situate in broader context  
**Tokens (approx):** 14,000 input / 1,400 output  
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
- 800–1,200 words
- Discussion interprets and synthesises; it does not re-report results
- Any citation must be from the paper registry
- Past tense for what studies did; present tense for what evidence shows
- Do not use bullet points

=== END OF DISCUSSION WRITING INSTRUCTIONS ===
```

---

## 17. Writing: Conclusion

**Model:** Gemini 2.5 Pro  
**Called:** Once  
**Purpose:** Summary, direct RQ answers, review limitations, future research  
**Tokens (approx):** 12,000 input / 550 output  
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
- 350–500 words
- Do not introduce new evidence
- Do not cite individual papers
- The RQ answers should be direct and declarative
- Future research recommendations should be specific, not generic

=== END OF CONCLUSION WRITING INSTRUCTIONS ===
```

---

## 18. Writing: Abstract

**Model:** Gemini 2.5 Pro  
**Called:** Once — written last after complete draft exists  
**Purpose:** Structured abstract summarising the complete review  
**Tokens (approx):** 16,000 input (full draft) / 450 output  
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

## 19. Consistency Checker

**Model:** Gemini 2.5 Pro  
**Called:** Once after all sections written  
**Purpose:** Find and fix violations of scaffold rules across the complete draft  
**Tokens (approx):** 16,000 input / 900 output

### Prompt

```
You are a copy-editor for a systematic literature review.
Check the complete draft below against the scaffold rules provided.

SCAFFOLD RULES:
Primary canonical term: "{primary_term}"
Banned synonyms: {banned_terms_list}

Locked PRISMA counts (no other numbers acceptable):
{prisma_counts_formatted}

Locked theme names (must appear exactly as written):
{theme_names_list}

Paper registry (only these papers may be cited):
{paper_registry_short}

Research questions (all must be explicitly answered):
{rq_list}

User-excluded papers (must not be cited):
{user_excluded_scopus_ids}

---

COMPLETE DRAFT:
{full_draft}

---

Find ALL violations. For each one return a fix.

Check for:
1. Any number that differs from the locked PRISMA counts
2. Any use of a banned synonym instead of the canonical term
3. Any theme name that differs from the exact locked names
4. Any citation of a paper not in the paper registry
5. Any research question not explicitly addressed in the Results or Discussion
6. Any citation of a user-excluded paper
7. Any claim in the Discussion that directly repeats Results text word-for-word

Return ONLY valid JSON. No preamble. No markdown fences.

[
  {
    "section": "section key name",
    "issue_type": "wrong_count|wrong_term|wrong_theme_name|unregistered_citation|unanswered_rq|excluded_paper_cited|verbatim_repetition",
    "original_text": "exact text containing the problem",
    "fix": "corrected text to replace it with",
    "explanation": "one sentence explaining the issue"
  }
]
```

### Expected Output

```json
[
  {
    "section": "abstract",
    "issue_type": "wrong_count",
    "original_text": "46 studies were included",
    "fix": "55 studies were included",
    "explanation": "Abstract states 46 but locked final_included count is 55"
  },
  {
    "section": "discussion",
    "issue_type": "wrong_term",
    "original_text": "consumer vulnerabilities in digital contexts",
    "fix": "consumer vulnerability in digital contexts",
    "explanation": "Plural form 'consumer vulnerabilities' is a banned synonym; canonical term is singular 'consumer vulnerability'"
  },
  {
    "section": "synthesis",
    "issue_type": "unregistered_citation",
    "original_text": "(Johnson & Williams, 2017)",
    "fix": "the literature suggests",
    "explanation": "Johnson & Williams (2017) does not appear in the paper registry of 55 confirmed papers"
  }
]
```

---

## 20. APA Reference Formatter

**Model:** Gemini 2.5 Pro  
**Called:** Once after consistency check  
**Purpose:** Format all 55 confirmed papers as APA 7th edition  
**Tokens (approx):** 7,000 input / 3,200 output

### Prompt

```
Format the following {paper_count} academic papers as an APA 7th edition
reference list.

Formatting rules:
- Sort alphabetically by first author surname, then by year ascending,
  then by title alphabetically where same author and year
- Same author, same year: append lowercase letters (2019a, 2019b)
- Up to 20 authors: list all. 21+: list first 19, then "...", then last author
- Use & before the final author (not "and")
- Article title: sentence case (only first word and proper nouns capitalised)
- Journal name: title case (all major words capitalised)
- Include volume(issue) if both available; volume only if issue missing
- Include page range with en-dash (–) if available
- Include DOI as https://doi.org/xxxxx if doi field is not null
- Omit DOI line entirely if doi is null
- Use hanging indent format in the final document (handled by python-docx)

Standard journal article format:
Surname, I. I., & Surname, I. I. (Year). Title of article in sentence case.
    Journal Name in Title Case, volume(issue), start–end page.
    https://doi.org/xxxxx

Return the formatted reference list only.
No numbering. No preamble. No markdown. One reference per line.
Separate each reference with a single blank line.

PAPER METADATA:
{paper_metadata_json}
```

### Expected Output

```
Baker, S. M., Gentry, J. W., & Rittenburg, T. L. (2019). Consumer
    vulnerability as a shared experience: Tornado recovery process in
    Wright, Wyoming. Journal of Public Policy & Marketing, 25(2), 128–139.
    https://doi.org/10.1509/jppm.25.2.128

Chen, X., Li, Y., & Wang, Z. (2022). Digital market complexity and
    consumer vulnerability: A cross-national examination. Journal of
    Consumer Research, 49(1), 44–67.
    https://doi.org/10.1093/jcr/ucab052

Johnson, M. K., & Williams, P. (2020). Dark patterns and consumer
    harm: An experimental investigation. Journal of Marketing, 84(3),
    78–96.
    https://doi.org/10.1177/0022242920912924
```

---

## 21. JSON Correction Prompt (Universal)

**Model:** Same model as the failing call (Pro or Flash)  
**Called:** When any JSON parse fails — maximum 2 retries  
**Purpose:** Extract valid JSON from a malformed response  
**Tokens (approx):** 1,200 input / varies

### Prompt

```
Your previous response was not valid JSON and could not be parsed.

Your previous response:
---
{raw_response}
---

Return ONLY the valid JSON object or array from your response above.
No preamble. No explanation. No markdown fences. No trailing commas.
Start with { or [ and end with } or ].
```

### Expected Output

```json
{ the corrected JSON from the original response }
```

---

## 22. Scaffold Preamble (Universal Prefix)

**Not a standalone call** — prepended to every writing and synthesis prompt.  
**Purpose:** Lock all consistency rules into every writing call.  
**Tokens:** ~2,600 tokens when registry included / ~950 without registry

### Full Preamble Template

```
=== CONSISTENCY RULES — MANDATORY, NON-NEGOTIABLE ===

CANONICAL TERM: Always use '{primary_term}'.
Never use these synonyms: {banned_terms_formatted}
This rule applies throughout every sentence you write.

LOCKED PRISMA COUNTS — use these exact numbers, no approximation:
  Records retrieved from Scopus:     {scopus_retrieved}
  After deduplication:               {after_dedup}
  Passed title/abstract screening:   {passed_ta}
  Full texts retrieved:              {pdfs_retrieved}
  Assessed as abstract only:         {abstract_only}
  Passed full-text assessment:       {passed_fulltext}
  Excluded by researcher:            {user_excluded}
  Final included:                    {final_included}

LOCKED THEME NAMES — use exactly as written, never paraphrase:
{theme_names_numbered}

EVIDENCE LANGUAGE RULES — apply based on each theme's grade:
  Established (>=60% corpus, multiple designs):
    Use: 'demonstrates', 'establishes', 'consistently shows', 'confirms'
    Do not use: 'suggests', 'indicates', 'appears to'
  Emerging (30-60%, mostly one design):
    Use: 'suggests', 'indicates', 'growing evidence shows'
    Do not use: 'demonstrates', 'establishes', 'confirms'
  Contested (contradictory findings):
    Use: 'remains debated', 'evidence is mixed', 'findings diverge'
    Do not use language implying consensus
  Insufficient (<=2 papers or <30% corpus):
    Use: 'preliminary evidence suggests', 'limited evidence indicates'
    Always follow with: flag as research gap
    Do not use any other strength language

CITATION RULES:
  Only cite papers explicitly listed in the registry below.
  Never cite a paper not in this registry.
  Never cite a paper by memory or inference.
  In-text format: (Surname et al., Year) or (Surname & Surname, Year)

PAPER REGISTRY ({paper_count} confirmed papers):
{paper_registry_formatted}
[OR if registry omitted for this section:]
[{paper_count} papers in registry — citations not required for this section.
Do not cite any individual paper in this section.]

RESEARCH QUESTIONS — all must be explicitly addressed in Results and Discussion:
{rq_numbered_list}

STYLE RULES:
  Academic third person throughout.
  Past tense: for what studies did, found, reported.
  Present tense: for what evidence shows, demonstrates, suggests.
  No bullet points. Continuous prose only.
  Average sentence length: 22–28 words.
  No first person (no 'we', 'our', 'I').

=== END CONSISTENCY RULES ===

[SECTION LABEL BLOCK — previous sections if applicable]
{previous_sections_labelled}
```

---

## Call Summary

| # | Prompt | Model | Calls | Input tokens | Output tokens |
|---|---|---|---|---|---|
| 1 | RQ Formalization | Pro | 1 | 700 | 300 |
| 2 | Query Generation | Pro | 1 | 800 | 700 |
| 3 | T/A Batch Screening | Flash | ~585 | ~480,000 | ~70,000 |
| 4 | Fulltext Screening + Rationale | Pro | ~90 | ~342,000 | ~22,500 |
| 5 | Extraction + Quality (merged) | Pro | ~55 | ~231,000 | ~49,500 |
| 6 | Canonical Term ID | Pro | 1 | 8,000 | 400 |
| 7 | Evidence Matrix | Pro | 1 | 12,000 | 1,200 |
| 8 | Advocate Pass | Pro | ~4 | ~16,800 | ~1,800 |
| 9 | Critic Pass | Pro | ~4 | ~18,400 | ~1,400 |
| 10 | Reconciler Pass | Pro | ~4 | ~20,400 | ~2,400 |
| 11 | Thin Theme | Pro | ~2 | ~6,400 | ~600 |
| 12 | Writing: Introduction | Pro | 1 | 3,200 | 900 |
| 13 | Writing: Methods (×4) | Pro | 4 | ~11,200 | ~2,000 |
| 14 | Writing: Results Sections (×4) | Pro | 4 | ~37,600 | ~3,200 |
| 15 | Writing: Synthesis | Pro | 1 | 14,000 | 2,800 |
| 16 | Writing: Discussion | Pro | 1 | 14,000 | 1,400 |
| 17 | Writing: Conclusion | Pro | 1 | 12,000 | 550 |
| 18 | Writing: Abstract | Pro | 1 | 16,000 | 450 |
| 19 | Consistency Checker | Pro | 1 | 16,000 | 900 |
| 20 | APA Formatter | Pro | 1 | 7,000 | 3,200 |
| 21 | JSON Correction | Pro/Flash | ~10 | ~12,000 | ~2,000 |
| **Total** | | | **~772** | **~1,280,000** | **~168,300** |

**Estimated runtime cost:** ~$1.59 (Gemini 2.5 Pro hybrid + Batch API discounts applied to items 3 and 5)
