# Placeholders:
# {minerU_full_paper_text}

You are a systematic review researcher extracting data from an academic paper.

Read the paper text carefully and return a single JSON object with exactly four top-level keys: "summary", "extraction", "quality", and "tccm".

Return ONLY valid JSON. No preamble. No explanation. No markdown fences.
Do not add trailing commas. Start with { and end with }.

=== OUTPUT SCHEMA ===

{
  "summary": "string - 500 to 600 words of continuous academic prose. See summary requirements below.",
  "extraction": {
    "author_year": "",
    "title": "",
    "country": "",
    "study_design": "",
    "data_type": "",
    "sample_size": "",
    "population": "",
    "context": "",
    "key_variables": "",
    "methodology": "",
    "theory_framework": "",
    "theoretical_frameworks": [
      {
        "theory_name": "name of theory used or referenced",
        "usage_type": "primary | secondary | implicit",
        "how_used": "one sentence — does this paper test, extend, challenge, or apply the theory?"
      }
    ],
    "key_findings": {
      "summary": "",
      "structure": [
        "Sentence 1: Main result (core finding; include numbers only if essential)",
        "Sentence 2: Secondary insight (moderator, mediator, or additional pattern)",
        "Sentence 3: Authors' conclusion or implication"
      ],
      "guidelines": [
        "Limit to 2-3 concise sentences",
        "Avoid unnecessary statistical detail",
        "Focus on insights, not raw outputs",
        "Maintain neutral academic tone",
        "Do not add interpretation beyond the paper"
      ]
    },
    "limitations": ""
  },
  "quality": {
    "study_type": "same value as study_design above",
    "total_score": 0,
    "dim_objectives": 0,
    "dim_design": 0,
    "dim_data": 0,
    "dim_analysis": 0,
    "dim_bias": 0,
    "risk_of_bias": "low | moderate | high",
    "strengths": ["strength 1", "strength 2", "strength 3"],
    "weaknesses": ["weakness 1", "weakness 2", "weakness 3"]
  },
  "tccm": {
    "theories": [
      {
        "theory_name": "exact name of theory used or referenced",
        "theory_abbreviation": "e.g. CLT, SCT, TAM — or null",
        "usage_type": "primary | secondary | implicit",
        "usage_description": "one sentence — does this paper test, extend, challenge, or apply this theory?"
      }
    ],
    "characteristics": {
      "unit_of_analysis": "individual | dyad | organisation | market | platform | policy | other",
      "sample_type": "student | consumer panel | general population | clinical | organisational | secondary data | other",
      "longitudinal": false,
      "experimental": false,
      "sample_size_category": "small (<100) | medium (100-499) | large (500-1999) | very large (2000+) | not applicable",
      "publication_type": "journal article | conference paper | book chapter | working paper",
      "journal_field": "marketing | consumer behaviour | information systems | psychology | economics | policy | interdisciplinary | other"
    },
    "context": {
      "geographic_scope": "single country | multi-country | global",
      "country_or_region": "country name or region — be specific",
      "economic_context": "developed | developing | emerging | mixed",
      "digital_platform_type": "e-commerce | social media | financial services | sharing economy | search engine | general digital | not specified",
      "population_group": "general consumers | elderly | low income | young adults | disability | gender-specific | cross-group | not specified",
      "temporal_context": "pre-2015 | 2015-2019 | 2020-2024 | longitudinal spanning periods"
    },
    "methods": {
      "research_paradigm": "quantitative | qualitative | mixed",
      "data_collection": "survey | experiment | interview | focus group | observation | secondary data | content analysis | multiple",
      "primary_analysis": "regression | SEM | content analysis | thematic analysis | grounded theory | case study analysis | meta-analysis | descriptive | other",
      "software_used": "SPSS | R | Mplus | AMOS | NVivo | ATLAS.ti | Stata | Python | not reported | other",
      "validation_approach": "pre-registered | piloted | multi-sample replication | single sample | not reported"
    }
  }
}

=== SUMMARY REQUIREMENTS ===

Write a 500 to 600 word narrative summary of this paper.
The summary must cover all of the following as continuous academic prose (no bullet points, no subheadings):

1. CONTEXT AND RATIONALE (1 paragraph)
Why was this study conducted? What gap does it address?
What is the theoretical or practical motivation?

2. METHODOLOGY (1-2 paragraphs)
Study design and why it was chosen.
Who were the participants: sample size, demographics, recruitment.
Where was the study conducted: country, setting, time period.
What instruments, scales, or data collection methods were used.
How was the data analysed.

3. FINDINGS (2 paragraphs)
Primary findings: be specific, include exact numbers, percentages,
effect sizes, p-values, or qualitative evidence where available.
Secondary findings, moderating variables, subgroup differences.
Do not generalise: report what this study actually found.

4. CONTRIBUTION AND LIMITATIONS (1 paragraph)
What does this paper contribute that other studies do not?
What are the author-stated limitations?
What do the authors recommend for future research?

Tone: academic, third person, past tense for what the study did,
present tense for what the evidence shows.
Do not be generic. Every sentence should be specific to this paper.
The summary will be used as input to thematic synthesis and must capture nuance and specificity.

=== QUALITY SCORING RUBRIC ===

Score each dimension 0 (poor), 1 (adequate), 2 (strong):

dim_objectives:
2 = Research question clearly stated, study design explicitly justified
1 = Research question present but vague, or design not justified
0 = No clear research question, design choice unexplained

dim_design:
2 = Design appropriate for research question, described in full detail
1 = Design broadly appropriate but incompletely described
0 = Design inappropriate or inadequately described

dim_data:
2 = Data collection rigorous, instruments validated, process transparent
1 = Data collection described but some gaps in transparency
0 = Data collection poorly described or instruments not validated

dim_analysis:
2 = Analytic approach systematic, appropriate, would be reproducible
1 = Analysis described but some steps unclear or sub-optimal
0 = Analysis poorly described or inappropriate for the data

dim_bias:
2 = Limitations explicitly acknowledged, reflexivity demonstrated (for qualitative), potential biases named and discussed
1 = Some limitations acknowledged but incomplete
0 = Limitations absent or superficial

total_score = sum of all five dimensions (range 0-10)
risk_of_bias: low = 8-10 | moderate = 5-7 | high = 0-4

=== PAPER TEXT ===

{minerU_full_paper_text}
