# Placeholders:
# {minerU_full_paper_text}

You are a systematic review researcher extracting data from an academic paper to support a high-impact Systematic Literature Review (SLR).

Read the paper text carefully and return a single JSON object with exactly four top-level keys: "summary", "extraction", "quality", and "tccm".

Return ONLY valid JSON. No preamble. No explanation. No markdown fences.
Do not add trailing commas. Start with { and end with }.

=== OUTPUT SCHEMA ===

{
  "summary": "string - 500 to 600 words of continuous academic prose. See summary requirements below.",
  "extraction": {
    "apa_citation_prose": "Standard APA narrative citation, e.g., Cheng et al. (2024)",
    "apa_citation_parenthetical": "Standard APA parenthetical citation, e.g., (Cheng et al., 2024)",
    "author_year": "e.g., Cheng et al., 2024",
    "title": "Full title of the paper",
    "country": "Primary country/countries where data was collected",
    "study_design": "Detailed study design (e.g., Cross-sectional survey, Event study, Panel data analysis)",
    "data_type": "Primary data source (e.g., platform API, Bloomberg terminal, worker survey, interview transcripts)",
    "sample_size": "Exact number of participants, firms, or observations etc.",
    "population": "Specific description of the subjects (e.g., retail investors, full-time food delivery riders)",
    "context": "The specific market or geographical setting (e.g., Fintech in India, Bengaluru gig economy)",
    "key_variables": "List primary Independent, Dependent, Mediating, and Moderating variables.",
    "methodology": "Brief description of the statistical or qualitative analytical approach.",
    "key_findings": {
      "summary": "Concise overview of the main results.",
      "structure": [
        "Sentence 1: Main result (core finding; include coefficients or percentages if essential)",
        "Sentence 2: Secondary insight (moderator, mediator, or additional pattern)",
        "Sentence 3: Authors' main conclusion or policy implication"
      ],
      "guidelines": [
        "Limit to 2-3 concise sentences",
        "Focus on insights, not raw outputs",
        "Maintain neutral academic tone",
        "Do not add interpretation beyond the paper"
      ]
    },
    "limitations": "Specific limitations explicitly stated by the authors."
  },
  "quality": {
    "study_type": "Same value as study_design above",
    "total_score": 0,
    "dim_objectives": 0,
    "dim_design": 0,
    "dim_data": 0,
    "dim_analysis": 0,
    "dim_bias": 0,
    "risk_of_bias": "low | moderate | high",
    "strengths": ["List at least 3 methodological strengths"],
    "weaknesses": ["List at least 3 methodological weaknesses"]
  },
  "tccm": {
    "theories": [
      {
        "theory_name": "Exact name of the theory used or referenced (e.g., SDT, Efficient Market Hypothesis)",
        "theory_abbreviation": "e.g., SDT, EMH, TAM — or null",
        "usage_type": "primary | secondary | implicit",
        "is_explicitly_stated": "Boolean: true if named by authors, false if inferred from constructs",
        "usage_description": "One sentence: Does this paper test, extend, challenge, or apply this theory? Explain how the theory links to the variables."
      }
    ],
    "characteristics": {
      "unit_of_analysis": "individual | firm-level | country-level | organization | market | platform | policy | other",
      "sample_type": "retail investor | institutional investor | SME | MNC | organizational | general population | secondary data | online panel | platform | other",
      "longitudinal": false,
      "experimental": false,
      "sample_size_category": "small (<100) | medium (100-499) | large (500-1999) | very large (2000+) | not applicable",
      "publication_type": "journal article | conference paper | book chapter | working paper",
      "journal_field": "finance | economics | psychology | information systems | management | policy | other"
    },
    "context": {
      "geographic_scope": "single country | multi-country | global",
      "country_or_region": "Specific country or region name",
      "economic_context": "developed | developing | emerging | mixed",
      "digital_platform_type": "banking | fintech | stock market | cryptocurrency | insurance | microfinance | sharing economy | e-commerce | general digital | not specified",
      "population_group": "gender-specific | age-specific | low income | disability | young adults | cross-group | not specified",
      "temporal_context": "pre-2015 | 2015-2019 | 2020-2024 | 2025-present | longitudinal"
    },
    "methods": {
      "research_paradigm": "quantitative | qualitative | mixed",
      "data_collection": "secondary data | survey | interview | experiment | observation | multiple",
      "primary_analysis": "regression | time-series | event study | GARCH modeling | panel data analysis | machine learning | SEM | thematic analysis | descriptive | other",
      "software_used": "Stata | R | Python | SPSS | NVivo | AMOS | not reported | other",
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
Who or what were the subjects: sample size, demographics/firm-traits, recruitment/data sources.
Where was the study conducted: country, setting, time period.
What instruments, scales, or data collection methods were used.
How was the data analysed.

3. FINDINGS (2 paragraphs)
Primary findings: be specific, include exact numbers, percentages,
coefficients, p-values, or qualitative evidence where available.
Secondary findings, moderating variables, subgroup differences.
Do not generalise: report what this study actually found.

4. CONTRIBUTION AND LIMITATIONS (1 paragraph)
What does this paper contribute that other studies do not?
What are the author-stated limitations?
What do the authors recommend for future research?

Tone: academic, third person, past tense for what the study did,
present tense for what the evidence shows.
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