You are analysing the theoretical foundations of a systematic literature review corpus.

REVIEW OBJECTIVES:
{objectives}

RESEARCH QUESTIONS:
{rq_list}

---

THEORETICAL FRAMEWORKS EXTRACTED FROM ALL {total_papers} PAPERS:
{all_theoretical_frameworks_json}

This JSON contains for each paper: scopus_id, short_ref, year, study_design, and theoretical_frameworks
[{theory_name, usage_type, how_used}].

---

YOUR TASK - complete all four steps:

STEP 1 - THEORY FREQUENCY MAP
Count how many papers use each named theory (primary + secondary).
Identify the top 5 most frequently used theories in this corpus.
Order by total_count descending.

STEP 2 - THEORY-THEME ALIGNMENT PREDICTION
Based on the theories present and the research objectives, predict which theories are most likely to illuminate which aspects of the research topic.
This will be confirmed against actual themes after the evidence matrix runs.

STEP 3 - THEORETICAL GAPS
Which important theories relevant to this phenomenon are ABSENT from the corpus?
Identify at least 2 and up to 5 absent theories.
Explain what their absence means for the field.

STEP 4 - PRIMARY LENS RECOMMENDATION
Identify the theory with the highest primary usage and best explanatory fit for the research topic.
a) Assess whether the most frequent theory is genuinely appropriate for these research objectives.
b) Recommend this theory as the primary lens.
c) Provide 2-3 alternative lenses from the corpus with one-sentence rationale for each.

Return ONLY valid JSON. No preamble. No markdown fences.

{
  "theory_frequency": [
    {
      "theory_name": "exact theory name",
      "abbreviation": "abbreviation or null",
      "primary_count": 0,
      "secondary_count": 0,
      "total_count": 0,
      "pct_of_corpus": 0.0,
      "dominance": "dominant | present | marginal"
    }
  ],
  "theoretical_gaps": [
    {
      "theory_name": "absent theory name",
      "why_relevant": "why this theory should be present",
      "implication": "what its absence means for the field"
    }
  ],
  "primary_lens_assessment": {
    "recommended_lens": "the lens recommended for use in synthesis",
    "recommended_lens_coverage": {
      "primary_count": 0,
      "secondary_count": 0,
      "total_count": 0,
      "pct_of_corpus": 0.0
    },
    "assessment": "2-3 sentences explaining why this lens is recommended.",
    "alternative_lenses": [
      {
        "theory_name": "alternative theory name",
        "pct_of_corpus": 0.0,
        "rationale": "why this could be used as the primary lens"
      }
    ]
  },
  "theoretical_diversity_score": "low | medium | high",
  "theoretical_diversity_rationale": "one sentence",
  "theoretical_landscape_summary": "3-4 sentences describing the theoretical character of this literature.",
  "theory_usage_pattern": "applying | testing | extending | challenging | building"
}
