## TCCM Framework — How and Full Prompts

---

### What TCCM Is

TCCM stands for **Theory, Characteristics, Context, Methods**. It was formalised by Paul et al. (2021) in the *International Business Review* as a structured way to organise what a systematic review finds about how a field has studied a topic — not just what it found, but how it went about finding it.

It answers four questions systematically:

```
THEORY:          What theoretical lenses has the field used?
CHARACTERISTICS: What are the characteristics of the studies themselves?
CONTEXT:         In what settings, populations, and geographies was this studied?
METHODS:         What research designs and analytical methods were used?
```

Top journals — JAMS, JIBS, IMR, JBR, and increasingly JM and JMR — now routinely require a TCCM table or structured TCCM analysis. Reviewers at these journals will explicitly look for it in any SLR submission.

The power of TCCM is that it makes the **gaps in the literature immediately visible**. Where the cells are empty or thin is exactly where future research should go.

---

### Where TCCM Enters the Pipeline

```
EXTRACTION CALL (already running)
  → add TCCM-specific fields to each paper's extraction
        ↓
TCCM AGGREGATION CALL (new — after all extractions complete)
  → aggregate TCCM data across all 55 papers
  → identify what is present, dominant, and absent in each dimension
        ↓
TCCM TABLE BUILDER (pure computation — no AI)
  → build the formatted TCCM table from aggregated data
        ↓
TCCM NARRATIVE CALL (new — one writing call)
  → write the TCCM analysis section in prose
        ↓
SCAFFOLD ADDITIONS
  → scaffold['tccm_summary'] for writing calls to reference
        ↓
DOCX ASSEMBLY
  → TCCM table embedded in Results: Study Characteristics
  → TCCM narrative in Results section
```

---

### Step 1 — Extraction Call Addition

The merged extraction prompt gains a fourth top-level key `tccm` alongside `summary`, `extraction`, and `quality`.

---

#### Addition to the Extraction Prompt

Add this to the existing extraction prompt after the quality schema:

```
  "tccm": {

    "theories": [
      {
        "theory_name": "exact name of theory used or referenced",
        "theory_abbreviation": "e.g. CLT, SCT, TAM — or null",
        "usage_type": "primary | secondary | implicit",
        "usage_description": "one sentence — does this paper test, 
                              extend, challenge, or apply this theory?"
      }
    ],

    "characteristics": {
      "unit_of_analysis": "individual | dyad | organisation | 
                            market | platform | policy | other",
      "sample_type": "student | consumer panel | general population | 
                       clinical | organisational | secondary data | other",
      "longitudinal": true or false,
      "experimental": true or false,
      "sample_size_category": "small (<100) | medium (100-499) | 
                                large (500-1999) | very large (2000+) | 
                                not applicable",
      "publication_type": "journal article | conference paper | 
                            book chapter | working paper",
      "journal_field": "marketing | consumer behaviour | information systems | 
                         psychology | economics | policy | interdisciplinary | other"
    },

    "context": {
      "geographic_scope": "single country | multi-country | global",
      "country_or_region": "country name or region — be specific",
      "economic_context": "developed | developing | emerging | mixed",
      "digital_platform_type": "e-commerce | social media | 
                                  financial services | sharing economy | 
                                  search engine | general digital | 
                                  not specified",
      "population_group": "general consumers | elderly | low income | 
                            young adults | disability | gender-specific | 
                            cross-group | not specified",
      "temporal_context": "pre-2015 | 2015-2019 | 2020-2024 | 
                            longitudinal spanning periods"
    },

    "methods": {
      "research_paradigm": "quantitative | qualitative | mixed",
      "data_collection": "survey | experiment | interview | 
                           focus group | observation | secondary data | 
                           content analysis | multiple",
      "primary_analysis": "regression | SEM | content analysis | 
                            thematic analysis | grounded theory | 
                            case study analysis | meta-analysis | 
                            descriptive | other",
      "software_used": "SPSS | R | Mplus | AMOS | NVivo | ATLAS.ti | 
                         Stata | Python | not reported | other",
      "validation_approach": "pre-registered | piloted | 
                               multi-sample replication | 
                               single sample | not reported"
    }
  }
```

---

### Step 2 — TCCM Aggregation Call

After all 55 extractions complete, one Gemini Pro call aggregates across all TCCM fields to identify patterns, dominances, and gaps.

---

#### Prompt: TCCM Aggregation and Gap Analysis

```
You are conducting a TCCM (Theory, Characteristics, Context, Methods) 
analysis for a systematic literature review following the framework 
proposed by Paul et al. (2021).

REVIEW TOPIC: {primary_topic}
TOTAL PAPERS: {total_papers}
DATE RANGE: {date_range}

---

TCCM DATA FROM ALL {total_papers} INCLUDED PAPERS:
{all_tccm_json}

This JSON contains for each paper: scopus_id, short_ref, year,
and the full tccm object with theories, characteristics, context, 
and methods fields.

---

YOUR TASK — analyse each TCCM dimension systematically.

Produce a comprehensive TCCM analysis covering all four dimensions.
For each dimension identify:
  1. What is DOMINANT — the most common approach, theory, or context
  2. What is PRESENT but not dominant — minority approaches
  3. What is ABSENT — important theories, contexts, or methods not used
  4. What the pattern MEANS for the field — the interpretive insight

The "absent" analysis is as important as the "present" analysis.
Gaps in TCCM are where future research should go.

Return ONLY valid JSON. No preamble. No markdown fences.

{
  "theory_dimension": {
    "theories_used": [
      {
        "theory_name": "full theory name",
        "abbreviation": "e.g. CLT",
        "primary_count": integer,
        "secondary_count": integer,
        "total_count": integer,
        "pct_of_corpus": float,
        "dominance": "dominant | present | marginal"
      }
    ],
    "theoretical_diversity_score": "low | medium | high",
    "theoretical_diversity_rationale": "one sentence",
    "dominant_theory": "name of most-used primary theory",
    "absent_theories": [
      {
        "theory_name": "name of absent theory",
        "why_relevant": "why this theory should be present in this literature",
        "implication": "what its absence means"
      }
    ],
    "theory_usage_pattern": "one of: applying | testing | extending | 
                              challenging | building — what is the 
                              dominant relationship between papers 
                              and their theoretical frameworks?",
    "theory_narrative": "3-4 sentences interpreting the theoretical 
                          dimension — what does the pattern tell us 
                          about the field's theoretical maturity?"
  },

  "characteristics_dimension": {
    "unit_of_analysis": {
      "distribution": {"individual": integer, "organisation": integer},
      "dominant": "most common unit",
      "absent": ["units not studied"],
      "narrative": "2 sentences"
    },
    "sample_types": {
      "distribution": {"consumer panel": integer, "general population": integer},
      "dominant": "most common sample type",
      "concerns": "any methodological concern about sample dominance"
    },
    "longitudinal_count": integer,
    "longitudinal_pct": float,
    "experimental_count": integer,
    "experimental_pct": float,
    "sample_size_distribution": {
      "small": integer,
      "medium": integer,
      "large": integer,
      "very_large": integer
    },
    "journal_field_distribution": {
      "marketing": integer,
      "consumer_behaviour": integer,
      "information_systems": integer,
      "psychology": integer,
      "other": integer
    },
    "characteristics_narrative": "3-4 sentences interpreting study 
                                   characteristics — what kind of 
                                   studies dominate and what 
                                   methodological biases exist?"
  },

  "context_dimension": {
    "geographic_distribution": [
      {
        "country_or_region": "name",
        "count": integer,
        "pct": float
      }
    ],
    "geographic_concentration": "low | medium | high",
    "western_dominance_pct": float,
    "underrepresented_regions": ["regions with < 5% representation"],
    "economic_context_distribution": {
      "developed": integer,
      "developing": integer,
      "emerging": integer,
      "mixed": integer
    },
    "platform_type_distribution": {
      "e-commerce": integer,
      "financial_services": integer,
      "social_media": integer,
      "other": integer
    },
    "population_group_distribution": {
      "general_consumers": integer,
      "elderly": integer,
      "low_income": integer,
      "young_adults": integer,
      "other": integer
    },
    "underrepresented_populations": ["population groups not studied"],
    "temporal_distribution": {
      "pre_2015": integer,
      "2015_2019": integer,
      "2020_2024": integer
    },
    "context_narrative": "3-4 sentences interpreting the context 
                           dimension — where has this been studied, 
                           where has it not, and what does that mean?"
  },

  "methods_dimension": {
    "paradigm_distribution": {
      "quantitative": integer,
      "qualitative": integer,
      "mixed": integer
    },
    "quantitative_pct": float,
    "data_collection_distribution": {
      "survey": integer,
      "experiment": integer,
      "interview": integer,
      "secondary_data": integer,
      "other": integer
    },
    "analysis_distribution": {
      "regression": integer,
      "SEM": integer,
      "thematic_analysis": integer,
      "content_analysis": integer,
      "other": integer
    },
    "pre_registered_count": integer,
    "pre_registered_pct": float,
    "multi_sample_replication_count": integer,
    "absent_methods": [
      {
        "method": "method name",
        "why_relevant": "why this method should be used in this literature",
        "implication": "what its absence means for evidence quality"
      }
    ],
    "methods_narrative": "3-4 sentences interpreting the methods 
                           dimension — what does the methodological 
                           profile tell us about evidence quality 
                           and maturity?"
  },

  "tccm_gaps_synthesis": "4-5 sentences synthesising the most important 
                           gaps across ALL four TCCM dimensions — this 
                           becomes the basis for the future research agenda. 
                           Be specific about what is missing and why it matters.",

  "future_research_from_tccm": [
    {
      "gap_dimension": "Theory | Characteristics | Context | Methods",
      "gap_description": "specific gap identified",
      "research_direction": "specific research question or approach that would address this gap",
      "priority": "high | medium | low",
      "rationale": "one sentence explaining why this gap is consequential"
    }
  ]
}
```

---

#### Expected Output (abbreviated)

```json
{
  "theory_dimension": {
    "theories_used": [
      {
        "theory_name": "Cognitive Load Theory",
        "abbreviation": "CLT",
        "primary_count": 18,
        "secondary_count": 12,
        "total_count": 30,
        "pct_of_corpus": 54.5,
        "dominance": "dominant"
      },
      {
        "theory_name": "Social Cognitive Theory",
        "abbreviation": "SCT",
        "primary_count": 12,
        "secondary_count": 8,
        "total_count": 20,
        "pct_of_corpus": 36.4,
        "dominance": "present"
      },
      {
        "theory_name": "Protection Motivation Theory",
        "abbreviation": "PMT",
        "primary_count": 9,
        "secondary_count": 5,
        "total_count": 14,
        "pct_of_corpus": 25.5,
        "dominance": "present"
      },
      {
        "theory_name": "Technology Acceptance Model",
        "abbreviation": "TAM",
        "primary_count": 7,
        "secondary_count": 11,
        "total_count": 18,
        "pct_of_corpus": 32.7,
        "dominance": "present"
      },
      {
        "theory_name": "Institutional Theory",
        "abbreviation": "IT",
        "primary_count": 6,
        "secondary_count": 4,
        "total_count": 10,
        "pct_of_corpus": 18.2,
        "dominance": "marginal"
      }
    ],
    "theoretical_diversity_score": "medium",
    "theoretical_diversity_rationale": "Five theories identified but CLT dominates at 54.5% with others playing secondary roles, indicating moderate concentration",
    "dominant_theory": "Cognitive Load Theory",
    "absent_theories": [
      {
        "theory_name": "Prospect Theory / Behavioural Economics",
        "why_relevant": "Platform dark patterns systematically exploit loss aversion, framing effects, and reference point manipulation — the core mechanisms of prospect theory — yet no included paper frames vulnerability through this lens",
        "implication": "The corpus has documented what dark patterns do to consumers without theorising why they work at the psychological level, leaving the mechanism explanation incomplete"
      },
      {
        "theory_name": "Intersectionality Theory",
        "why_relevant": "Multiple vulnerability dimensions (age, income, disability, gender) co-occur in consumers and compound vulnerability multiplicatively, yet all papers treat these as additive independent variables",
        "implication": "Current models systematically underestimate vulnerability in consumers with multiple co-occurring risk factors"
      },
      {
        "theory_name": "Agency Theory",
        "why_relevant": "Platform-consumer relationships involve fundamental information asymmetries and principal-agent problems that agency theory was developed to explain",
        "implication": "The structural power dynamics enabling consumer exploitation remain theoretically unaddressed"
      }
    ],
    "theory_usage_pattern": "applying",
    "theory_narrative": "The consumer vulnerability in digital markets literature exhibits a predominantly applied theoretical orientation — 87% of papers use existing theories to generate and test hypotheses rather than to extend or challenge theoretical propositions. Cognitive Load Theory dominates at 54.5% of the corpus, reflecting the field's cognitive-individual focus, while structural and institutional perspectives remain marginal. The notable absence of behavioural economics frameworks is theoretically significant given that platform dark patterns explicitly exploit the cognitive biases Kahneman and Tversky documented. The field's theoretical concentration on the individual cognitive level, rather than the structural level, may explain why intervention research consistently shows individual-level solutions to be less effective than environmental regulation."
  },

  "characteristics_dimension": {
    "unit_of_analysis": {
      "distribution": {
        "individual": 48,
        "dyad": 2,
        "organisation": 1,
        "market": 3,
        "platform": 1
      },
      "dominant": "individual",
      "absent": ["policy system", "regulatory body", "cross-platform comparison"],
      "narrative": "Individual consumers constitute the unit of analysis in 87% of included studies, reflecting the field's psychological orientation. Market-level and platform-level analyses are severely underrepresented, meaning the field understands vulnerability as an individual state while the structural conditions producing it remain largely unstudied at the appropriate level of analysis."
    },
    "sample_types": {
      "distribution": {
        "consumer_panel": 24,
        "general_population": 14,
        "student": 8,
        "secondary_data": 5,
        "other": 4
      },
      "dominant": "consumer panel",
      "concerns": "Consumer panel samples (44%) may over-represent digitally active, higher-literacy consumers and systematically underestimate vulnerability in the most at-risk populations who are less likely to participate in online panels"
    },
    "longitudinal_count": 4,
    "longitudinal_pct": 7.3,
    "experimental_count": 11,
    "experimental_pct": 20.0,
    "sample_size_distribution": {
      "small": 8,
      "medium": 14,
      "large": 21,
      "very_large": 12
    },
    "journal_field_distribution": {
      "marketing": 18,
      "consumer_behaviour": 14,
      "information_systems": 10,
      "psychology": 8,
      "other": 5
    },
    "characteristics_narrative": "The literature is dominated by cross-sectional survey studies of individual consumers using professional panel samples, with only 7.3% of studies employing longitudinal designs and 20% using experimental methods. This methodological profile severely limits causal inference — the field has documented associations extensively but established causal mechanisms in only a fraction of the corpus. The low rate of pre-registration (12.7%) and multi-sample replication (18.2%) raises concerns about publication bias and the robustness of reported effect sizes."
  },

  "context_dimension": {
    "geographic_distribution": [
      {"country_or_region": "United Kingdom", "count": 12, "pct": 21.8},
      {"country_or_region": "United States", "count": 10, "pct": 18.2},
      {"country_or_region": "Australia", "count": 6, "pct": 10.9},
      {"country_or_region": "Germany", "count": 4, "pct": 7.3},
      {"country_or_region": "China", "count": 3, "pct": 5.5},
      {"country_or_region": "Multi-country", "count": 8, "pct": 14.5},
      {"country_or_region": "Other", "count": 12, "pct": 21.8}
    ],
    "geographic_concentration": "high",
    "western_dominance_pct": 72.7,
    "underrepresented_regions": [
      "Sub-Saharan Africa",
      "South and Southeast Asia",
      "Latin America",
      "Middle East and North Africa"
    ],
    "economic_context_distribution": {
      "developed": 42,
      "developing": 4,
      "emerging": 6,
      "mixed": 3
    },
    "platform_type_distribution": {
      "e_commerce": 28,
      "financial_services": 12,
      "social_media": 8,
      "sharing_economy": 3,
      "not_specified": 4
    },
    "population_group_distribution": {
      "general_consumers": 28,
      "elderly": 12,
      "low_income": 7,
      "young_adults": 5,
      "disability": 1,
      "cross_group": 2
    },
    "underrepresented_populations": [
      "Consumers with cognitive disabilities",
      "Non-English speaking minority consumers",
      "Rural and digitally excluded consumers",
      "Consumers in developing market digital contexts"
    ],
    "temporal_distribution": {
      "pre_2015": 7,
      "2015_2019": 24,
      "2020_2024": 24
    },
    "context_narrative": "The literature is overwhelmingly concentrated in high-income Anglophone markets, with the UK, USA, and Australia together accounting for 50.9% of single-country studies. Developing and emerging market contexts represent only 18.2% of the corpus despite the rapid growth of digital commerce in these regions and the potentially greater vulnerability of consumers operating with fewer regulatory protections and lower baseline digital literacy. E-commerce platforms dominate the contextual focus (50.9%), leaving financial services (21.8%), social media (14.5%), and emerging platform types substantially underexplored. Elderly consumers are the most studied vulnerable subgroup (21.8%) while consumers with cognitive disabilities appear in only one study, representing a severe contextual gap given documented differential vulnerability."
  },

  "methods_dimension": {
    "paradigm_distribution": {
      "quantitative": 33,
      "qualitative": 14,
      "mixed": 8
    },
    "quantitative_pct": 60.0,
    "data_collection_distribution": {
      "survey": 28,
      "experiment": 11,
      "interview": 9,
      "focus_group": 4,
      "secondary_data": 3
    },
    "analysis_distribution": {
      "regression": 14,
      "SEM": 12,
      "thematic_analysis": 9,
      "content_analysis": 5,
      "grounded_theory": 3,
      "other": 12
    },
    "pre_registered_count": 7,
    "pre_registered_pct": 12.7,
    "multi_sample_replication_count": 10,
    "multi_sample_replication_pct": 18.2,
    "absent_methods": [
      {
        "method": "Digital trace data / behavioural data analysis",
        "why_relevant": "Platform vulnerability operates through actual behavioural sequences that are measurable via clickstream and transaction data — self-report surveys cannot capture the moment-by-moment cognitive experience",
        "implication": "The evidence base rests almost entirely on retrospective self-report, introducing substantial recall and social desirability biases that may systematically underestimate vulnerability frequency and overestimate coping effectiveness"
      },
      {
        "method": "Audit methodology / platform scraping",
        "why_relevant": "Systematically documenting dark pattern prevalence and intensity across platforms would provide objective environmental measures, yet all studies rely on consumer-reported platform exposure",
        "implication": "The field lacks objective measurement of the independent variable it studies — platform design complexity is never independently verified"
      },
      {
        "method": "Longitudinal panel with repeated measures",
        "why_relevant": "Vulnerability effects may accumulate over time or diminish as consumers adapt — only longitudinal designs can distinguish transient from chronic vulnerability",
        "implication": "The 7.3% longitudinal rate means the field cannot distinguish whether vulnerability is a persistent state or an episodic response"
      }
    ],
    "methods_narrative": "The methodological profile is predominantly quantitative (60%) and survey-based (50.9%), with experimental evidence present but limited to 20% of the corpus. The near-total absence of digital trace data and platform audit methodologies is the most consequential methodological gap — the field measures vulnerability through consumer self-report while the platform-side design features driving vulnerability are never independently documented. Pre-registration rates are low (12.7%) and multi-sample replication occurs in only 18.2% of studies, raising systematic concerns about the robustness of reported effect sizes and the potential for publication bias in the quantitative literature."
  },

  "tccm_gaps_synthesis": "Across all four TCCM dimensions, the consumer vulnerability in digital markets literature exhibits a consistent pattern of individual-level focus at the expense of structural and environmental analysis. Theoretically, the field applies cognitive frameworks without engaging behavioural economics or structural theories that would better explain why platforms design for vulnerability exploitation. Contextually, 72.7% of evidence comes from developed Western markets, leaving the largest and fastest-growing digital consumer populations — in Asia, Africa, and Latin America — almost entirely unstudied. Methodologically, the absence of digital trace data and platform audit methodologies means the field has never independently verified the platform-side independent variable it studies; all evidence rests on consumer self-report of experiences that are demonstrably subject to recall and social desirability biases. These gaps collectively point to a field that understands the individual cognitive experience of vulnerability well but understands the structural, environmental, and cross-cultural determinants poorly.",

  "future_research_from_tccm": [
    {
      "gap_dimension": "Theory",
      "gap_description": "Behavioural economics frameworks (Prospect Theory, dual-process theory) are entirely absent despite being theoretically central to explaining why dark patterns work",
      "research_direction": "Studies applying Prospect Theory to model consumer responses to specific dark pattern types would provide mechanism-level explanations that CLT-based studies cannot offer",
      "priority": "high",
      "rationale": "Understanding the psychological mechanism is prerequisite to designing effective counter-interventions"
    },
    {
      "gap_dimension": "Context",
      "gap_description": "Developing and emerging market digital commerce contexts are severely underrepresented at 18.2% of corpus despite rapid market growth and weaker regulatory protection",
      "research_direction": "Cross-national comparative studies explicitly designed to test whether vulnerability mechanisms documented in Anglophone markets generalise to different regulatory and cultural contexts",
      "priority": "high",
      "rationale": "Policy recommendations derived from Western samples cannot be responsibly applied to markets with fundamentally different regulatory environments and consumer baseline characteristics"
    },
    {
      "gap_dimension": "Methods",
      "gap_description": "Digital trace data and platform audit methodologies are entirely absent, meaning the platform-side independent variable is never independently measured",
      "research_direction": "Combining platform dark pattern audits (objective environmental measure) with consumer outcome data (behavioural and self-report) in matched designs",
      "priority": "high",
      "rationale": "Without independent measurement of platform design intensity, causal claims about platform design as the driver of vulnerability cannot be established"
    },
    {
      "gap_dimension": "Characteristics",
      "gap_description": "Only 7.3% of studies use longitudinal designs, making it impossible to distinguish transient from chronic vulnerability or to track adaptation and learning effects",
      "research_direction": "Longitudinal panel studies tracking the same consumers across platform interactions over 12-24 month periods, measuring both vulnerability states and coping adaptation",
      "priority": "medium",
      "rationale": "Intervention design requires knowing whether vulnerability is episodic or chronic — current cross-sectional evidence cannot answer this"
    },
    {
      "gap_dimension": "Context",
      "gap_description": "Consumers with cognitive disabilities appear in only one study despite being among the most vulnerable populations in digital markets",
      "research_direction": "Dedicated studies of digital marketplace vulnerability in consumers with autism spectrum conditions, acquired brain injury, dementia, and learning disabilities",
      "priority": "medium",
      "rationale": "Consumer protection policy increasingly requires disability-specific evidence for digital accessibility mandates; the research base does not currently support this"
    }
  ]
}
```

---

### Step 3 — TCCM Table Builder (Pure Computation)

After the aggregation call, the TCCM table is built directly from the JSON output — no AI call needed. python-docx renders it.

**The standard TCCM table format used in JAMS, JBR, IMR:**

```
┌─────────────────────┬──────────────────────────────────────────────────────┐
│ DIMENSION           │ FINDINGS AND GAPS                                     │
├─────────────────────┼──────────────────────────────────────────────────────┤
│ THEORY              │                                                       │
│ Dominant            │ Cognitive Load Theory (54.5%), Social Cognitive      │
│                     │ Theory (36.4%), TAM (32.7%)                          │
│ Present             │ Protection Motivation Theory (25.5%),                │
│                     │ Institutional Theory (18.2%)                         │
│ Absent              │ Prospect Theory / Behavioural Economics ✗            │
│                     │ Intersectionality Theory ✗                           │
│                     │ Agency Theory ✗                                      │
├─────────────────────┼──────────────────────────────────────────────────────┤
│ CHARACTERISTICS     │                                                       │
│ Unit of analysis    │ Individual consumer (87%), Market (5%), Other (8%)   │
│ Sample type         │ Consumer panel (44%), General population (25%),      │
│                     │ Student (15%), Secondary data (9%)                   │
│ Longitudinal        │ 4 studies (7.3%) — predominantly cross-sectional ✗  │
│ Experimental        │ 11 studies (20%)                                     │
│ Pre-registered      │ 7 studies (12.7%) ✗                                 │
│ Replicated          │ 10 studies (18.2%) ✗                                │
├─────────────────────┼──────────────────────────────────────────────────────┤
│ CONTEXT             │                                                       │
│ Geography           │ UK (21.8%), USA (18.2%), Australia (10.9%)           │
│                     │ Western markets: 72.7% of corpus                    │
│ Underrepresented    │ Sub-Saharan Africa ✗, South/SE Asia ✗               │
│                     │ Latin America ✗, MENA ✗                             │
│ Economic context    │ Developed (76.4%), Emerging (10.9%), Mixed (5.5%)   │
│ Platform type       │ E-commerce (50.9%), Financial services (21.8%)      │
│ Population          │ General (50.9%), Elderly (21.8%), Low income (12.7%)│
│ Underrepresented    │ Cognitive disability ✗, Rural consumers ✗           │
├─────────────────────┼──────────────────────────────────────────────────────┤
│ METHODS             │                                                       │
│ Paradigm            │ Quantitative (60%), Qualitative (25.5%), Mixed (14.5)│
│ Data collection     │ Survey (50.9%), Experiment (20%), Interview (16.4%) │
│ Analysis            │ Regression (25.5%), SEM (21.8%), Thematic (16.4%)  │
│ Absent methods      │ Digital trace data ✗                                │
│                     │ Platform audit methodology ✗                        │
│                     │ Longitudinal panel with repeated measures ✗         │
└─────────────────────┴──────────────────────────────────────────────────────┘
✗ = identified gap requiring future research
```

---

### Step 4 — TCCM Narrative Writing Call

After the aggregation JSON is stored, one Gemini Pro writing call produces the TCCM narrative section that appears in the paper.

---

#### Prompt: TCCM Section Writing

```
{SCAFFOLD_PREAMBLE}

[SECTION LABEL BLOCK — all prior sections]

=== NOW WRITE: SECTION 3.2b — TCCM ANALYSIS ===
=== Do NOT repeat content from sections already written above. ===

Write the TCCM (Theory, Characteristics, Context, Methods) analysis 
section for this systematic literature review.

TCCM AGGREGATED DATA:
{tccm_summary_json}

The TCCM table (Table X) has already been inserted before this text.
This section provides the narrative interpretation of the table.

Structure — write as four subsections with these exact headings:

3.2.1 Theoretical Landscape
3.2.2 Study Characteristics  
3.2.3 Contextual Coverage
3.2.4 Methodological Profile

For each subsection:
- Open with what DOMINATES and why this matters
- Describe what is PRESENT but not dominant
- Explicitly identify what is ABSENT
- State the interpretive implication — what does this pattern 
  reveal about the field's development and blind spots?

Use these exact narratives from the TCCM analysis as your 
starting point — expand and contextualise them in academic prose:
  Theory narrative:          {theory_narrative}
  Characteristics narrative: {characteristics_narrative}
  Context narrative:         {context_narrative}
  Methods narrative:         {methods_narrative}

Requirements:
- 600-800 words total across four subsections
- Academic third person
- ✗ gaps should be stated as explicit research gaps, not just 
  described as absent
- Every percentage cited must match the TCCM aggregation data exactly
- The section should end with 2-3 sentences synthesising the most 
  consequential gap across all four dimensions

=== END OF TCCM WRITING INSTRUCTIONS ===
```

---

### Step 5 — Scaffold Addition

```python
scaffold['tccm_summary'] = {
    "dominant_theory":           "Cognitive Load Theory",
    "theory_diversity":          "medium",
    "absent_theories":           ["Prospect Theory", "Intersectionality Theory", "Agency Theory"],
    "longitudinal_pct":          7.3,
    "experimental_pct":          20.0,
    "western_dominance_pct":     72.7,
    "underrepresented_regions":  ["Sub-Saharan Africa", "South/SE Asia", "Latin America"],
    "quantitative_pct":          60.0,
    "absent_methods":            ["Digital trace data", "Platform audit methodology"],
    "pre_registered_pct":        12.7,
    "key_gaps": [
        "Behavioural economics frameworks entirely absent",
        "72.7% of evidence from Western markets",
        "Digital trace data not used in any study",
        "7.3% longitudinal rate"
    ]
}
```

The Discussion and Future Research writing calls receive this summary so they can reference TCCM gaps when making recommendations.

---


### Where TCCM Appears in the Final Paper

```
3.2  Study Characteristics
     Table 2: Study Characteristics (auto-built from DataExtraction)
     [narrative paragraph]
     Table 3: TCCM Analysis (auto-built from TCCM aggregation JSON)
3.2.1  Theoretical Landscape
3.2.2  Study Characteristics
3.2.3  Contextual Coverage
3.2.4  Methodological Profile
```

The TCCM table and its narrative interpretation appear together in the Study Characteristics section. Future research gaps identified in TCCM flow directly into Section 6 (Future Research Agenda) — the `future_research_from_tccm` array feeds into that section's structured table.