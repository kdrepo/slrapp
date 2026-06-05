You are analyzing the theoretical foundations of a systematic literature review corpus for a high-impact academic journal.

RESEARCH CONTEXT/DOMAIN:
{research_context}

REVIEW OBJECTIVES:
{objectives}

RESEARCH QUESTIONS:
{rq_list}

---

THEORETICAL FRAMEWORKS EXTRACTED FROM ALL {total_papers} PAPERS:
{all_theoretical_frameworks_json}

The input JSON contains for each paper: paper_id, apa_citation_parenthetical, year, and a list of theories found in the 'tccm' block, including:
- theory_name
- usage_type (primary | secondary | implicit)
- is_explicitly_stated (Boolean: true if named by authors, false if inferred from constructs)
- usage_description

---

YOUR TASK - complete all four steps:

STEP 1 - THEORY FREQUENCY MAP
Count how many papers use each named theory. 
- Calculate separate counts for 'Explicitly Stated' vs. 'Implicitly Used' (using the 'is_explicitly_stated' flag).
- Identify the top 5 most frequently used theories in this corpus.
- Order by total_count descending.

STEP 2 - THEORY-THEME ALIGNMENT PREDICTION
Based on the theories present and the research objectives, predict which theories are most likely to illuminate which aspects of the {research_context} (e.g., how a specific theory might explain a particular dependent variable or outcome).

STEP 3 - THEORETICAL GAPS (ADAPTIVE GUIDANCE)
Identify 2 to 5 important theories relevant to the {research_context} that are ABSENT from the corpus.
- ADAPTIVE LOGIC: Do not use a fixed list. Identify gaps based on the intellectual requirements of the {research_context}.
  - (e.g., In Finance/Economics, you might look for missing frameworks like Agency Theory, Information Asymmetry, or Market Efficiency).
  - (e.g., In Social Sciences, you might look for missing frameworks like Institutional Theory, Social Cognitive Theory, or Bourdieu’s Capital Theory).
- Explain what the absence of these theories means for the current depth and maturity of the field.

STEP 4 - PRIMARY LENS RECOMMENDATION
Identify the theory with the highest primary usage and best explanatory fit for this specific review.
a) Assess whether the most frequent theory is genuinely appropriate for the {objectives}.
b) Recommend this theory as the primary lens for the subsequent synthesis.
c) Provide 2-3 alternative lenses from the corpus with a one-sentence rationale for each.

=== CRITICAL RULES ===
- CITATION MANDATE: The `theoretical_landscape_summary` MUST include parenthetical APA citations (e.g., Author, Year) for every claim regarding which papers use which theories.
- DATA INTEGRITY: Use the provided `apa_citation_parenthetical` from the input JSON to ensure citation accuracy.
- TONE: Maintain a high-level academic tone suitable for top-tier journal submissions.

=== OUTPUT FORMAT ===

Return ONLY valid JSON. No preamble. No markdown fences.

{
  "theory_frequency": [
    {
      "theory_name": "exact theory name",
      "abbreviation": "abbreviation or null",
      "primary_count": 0,
      "secondary_count": 0,
      "explicit_count": 0,
      "implicit_count": 0,
      "total_count": 0,
      "pct_of_corpus": 0.0,
      "dominance": "dominant | present | marginal"
    }
  ],
  "theoretical_gaps": [
    {
      "theory_name": "absent theory name",
      "why_relevant": "Why this theory should be present given the {research_context}",
      "implication": "What its absence means for the field's development"
    }
  ],
  "primary_lens_assessment": {
    "recommended_lens": "The lens recommended for use in the final synthesis",
    "recommended_lens_coverage": {
      "primary_count": 0,
      "total_count": 0,
      "explicit_pct": 0.0
    },
    "assessment": "2-3 sentences explaining why this lens is recommended based on its prevalence and explanatory power.",
    "alternative_lenses": [
      {
        "theory_name": "alternative theory name",
        "pct_of_corpus": 0.0,
        "rationale": "Why this could be used as an alternative primary lens"
      }
    ]
  },
  "theoretical_diversity_score": "low | medium | high",
  "theoretical_diversity_rationale": "One sentence summary of theoretical variety.",
  "theoretical_landscape_summary": "4-5 sentences describing the theoretical character of this literature. YOU MUST INCLUDE APA CITATIONS HERE for all theory-paper associations.",
  "theory_usage_pattern": "applying | testing | extending | challenging | building"
}