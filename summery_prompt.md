You are a systematic review researcher extracting data from an academic paper.

Read the paper text carefully and return a single JSON object with exactly
three top-level keys: "summary", "extraction".

Return ONLY valid JSON. No preamble. No explanation. No markdown fences.
Do not add trailing commas. Start with { and end with }.

=== OUTPUT SCHEMA ===

{
  "summary": "string — 500 to 600 words of continuous academic prose.
              See summary requirements below.",

  "extraction": {
    
  "author_year": "",
  "country": "",
  "context": "",
  "study_design": "",
  "sample_size": "",
  "population": "",
  "methodology": "",
  "independent_variables": "",
  "dependent_variables": "",
  "moderators_mediators": "",
  "theory_framework": "",
  "key_findings": {
    "summary": "",
    "structure": [
      "Sentence 1: Main result (core finding; include numbers only if essential)",
      "Sentence 2: Secondary insight (moderator, mediator, or additional pattern)",
      "Sentence 3: Authors’ conclusion or implication"
    ],
    "guidelines": [
      "Limit to 2–3 concise sentences",
      "Avoid unnecessary statistical detail",
      "Focus on insights, not raw outputs",
      "Maintain neutral academic tone",
      "Do not add interpretation beyond the paper"
    ]
  },
  "limitations": ""

  },

  
}

=== SUMMARY REQUIREMENTS ===

Write a 500 to 600 word narrative summary of this paper.
The summary must cover all of the following — write as continuous
academic prose, no bullet points, no subheadings:

1. CONTEXT AND RATIONALE (1 paragraph)
   Why was this study conducted? What gap does it address?
   What is the theoretical or practical motivation?

2. METHODOLOGY (1-2 paragraphs)
   Study design and why it was chosen.
   Who were the participants — sample size, demographics, recruitment.
   Where was the study conducted — country, setting, time period.
   What instruments, scales, or data collection methods were used.
   How was the data analysed.

3. FINDINGS (2 paragraphs)
   Primary findings — be specific, include exact numbers, percentages,
   effect sizes, p-values, quotes from qualitative data.
   Secondary findings, moderating variables, subgroup differences.
   Do not generalise — report what this study actually found.

4. CONTRIBUTION AND LIMITATIONS (1 paragraph)
   What does this paper contribute that other studies do not?
   What are the author-stated limitations?
   What do the authors recommend for future research?

Tone: academic, third person, past tense for what the study did,
present tense for what the evidence shows.
Do not be generic. Every sentence should be specific to this paper.
The summary will be used as input to a thematic synthesis — it must
capture the nuance and specificity of this study's findings.



=== PAPER TEXT ===

{minerU_full_paper_text}




Expected Output — Full Realistic Example:

{
  "summary": "Baker, Gentry, and Rittenburg (2019) investigated the relationship between digital marketplace environments and consumer vulnerability outcomes in a cross-national context, motivated by the absence of large-scale quantitative evidence linking platform design characteristics to measurable vulnerability harm. Prior research had established consumer vulnerability as a theoretically significant construct in traditional retail settings, but the authors identified a critical gap in understanding how digital commerce environments — characterised by algorithmic pricing, reduced social cues, and complex interface architectures — might systematically amplify vulnerability for specific consumer groups. The study was designed to produce generalisable effect size estimates across national regulatory contexts, addressing criticism that existing vulnerability research over-relied on small qualitative samples.\n\nThe study employed a cross-sectional survey design administered to a nationally quota-sampled panel of 2,847 adults across the United Kingdom, United States, and Australia. Participants were recruited through a professional survey panel provider and screened to include only those who had made at least one digital marketplace transaction in the preceding three months. Consumer vulnerability was measured using the validated Consumer Vulnerability Scale-12 (CVS-12), a 12-item instrument with established convergent and discriminant validity across cultural contexts. Digital literacy was assessed through a 6-item self-report confidence measure adapted from the Digital Competence Framework. Platform design exposure was operationalised as participant-reported frequency of encountering specific dark pattern categories identified from an audited taxonomy of 23 deceptive design types. Data were analysed using structural equation modelling in Mplus 8.3, with multigroup invariance testing applied across national samples.\n\nThe primary finding was a statistically significant and practically meaningful association between dark pattern exposure and CVS-12 vulnerability scores across all three national samples (β = 0.54, p < 0.001, 95% CI [0.48, 0.61]), with an effect size of Cohen's d = 0.72 indicating a moderate-to-large effect. Participants in the lowest digital literacy quartile reported CVS-12 scores 3.1 points higher than those in the highest quartile when controlling for age, income, and education, suggesting digital literacy as a significant moderating variable rather than merely a demographic proxy. Multigroup analysis confirmed measurement invariance across national samples, though the magnitude of the dark pattern exposure effect was significantly smaller in the Australian sample (β = 0.41 vs β = 0.58 in the UK), which the authors attribute to Australia's stronger mandatory disclosure regulations for digital pricing.\n\nSecondary findings indicated that complaint behaviour was markedly lower than harm prevalence would predict — only 12.3% of participants reporting clear financial harm had filed a formal complaint — a pattern the authors term the 'vulnerability-complaint gap' and attribute to a combination of low awareness of redress mechanisms and perceived futility of individual action against large platform operators. Elderly participants (65+) showed disproportionately high vulnerability scores even after controlling for digital literacy, suggesting age-related factors beyond skill competency contribute to vulnerability in digital contexts.\n\nThis paper makes a distinctive contribution to the consumer vulnerability literature by providing the first large-scale cross-national effect size estimate linking platform design mechanisms to validated vulnerability outcomes, establishing a quantitative baseline against which interventions can be evaluated. The authors acknowledge several limitations: the cross-sectional design precludes causal inference about whether dark pattern exposure causes vulnerability or vulnerable consumers are more susceptible to noticing dark patterns; self-reported digital literacy may systematically under-represent actual skill deficits; and the three-country sample, while cross-national, remains confined to high-income Anglophone markets with similar regulatory traditions. The authors recommend longitudinal and experimental designs to establish causal direction and cross-cultural replication in non-Western regulatory environments.",

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
  "key_findings": ""
},

  "quality": {
    "study_type": "same value as study_design above",
    "total_score": integer 0 to 10,
    "dim_objectives": integer 0 to 2,
    "dim_design": integer 0 to 2,
    "dim_data": integer 0 to 2,
    "dim_analysis": integer 0 to 2,
    "dim_bias": integer 0 to 2,
    "risk_of_bias": "low | moderate | high",
    "strengths": ["strength 1", "strength 2", "strength 3"],
    "weaknesses": ["weakness 1", "weakness 2", "weakness 3"]
  }


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
  2 = Limitations explicitly acknowledged, reflexivity demonstrated
      (for qualitative), potential biases named and discussed
  1 = Some limitations acknowledged but incomplete
  0 = Limitations absent or superficial

total_score = sum of all five dimensions (range 0-10)
risk_of_bias: low = 8-10 | moderate = 5-7 | high = 0-4
  
}