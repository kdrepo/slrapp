# Placeholders:
# {objectives}
# {rq_list_numbered}
# {total_papers}
# {established_threshold}
# {emerging_min}
# {emerging_max}
# {insufficient_threshold}
# {all_extractions_json}

You are conducting a thematic synthesis for a high-impact systematic literature review.

Your task is to identify the major themes (empirical regularities or narrative patterns) that emerge from the evidence corpus below, then assign an evidence grade to each theme based on objective criteria.

=== REVIEW CONTEXT ===

RESEARCH OBJECTIVES:
{objectives}

RESEARCH QUESTIONS:
{rq_list_numbered}

TOTAL CONFIRMED PAPERS: {total_papers}

=== EVIDENCE CORPUS ===

Below are the structured extractions from all {total_papers} included papers. 
Each entry contains: paper_id, apa_citation_parenthetical, year, study_design, population/subjects, context/market, outcomes/variables, and key_findings.

{all_extractions_json}

=== YOUR TASK ===

Step 1 — Read all {total_papers} extractions carefully.

Step 2 — Identify 3 to 5 distinct themes that emerge from the evidence.

A theme must:
  - Appear across multiple papers (minimum 3 papers, except Insufficient grade).
  - Represent a substantive finding pattern (e.g., a consistent relationship between variables in Finance, or a recurring narrative experience in Social Science).
  - For Quantitative/Finance topics: A theme often represents the sign, significance, and consistency of a relationship (e.g., "Positive impact of ESG on firm value").
  - For Qualitative/Social Science topics: A theme represents a shared phenomenon or challenge.
  - Be directly relevant to the Research Questions.

Step 3 — Map paper_id values to each theme. A paper addresses a theme if its primary findings or data directly support that pattern.

Step 4 — Assign an evidence grade using these exact criteria:

  ESTABLISHED:
    - 60% or more of all included papers ({established_threshold} or more papers).
    - AND findings are broadly convergent across multiple study designs or diverse market contexts/datasets.

  EMERGING:
    - 10% to 59% of included papers ({emerging_min} to {emerging_max} papers).
    - OR findings come predominantly from one specific study design or a single geographic/market context.

  CONTESTED:
    - Papers in the corpus directly contradict each other (e.g., one study finds a positive relationship, another finds a negative one).
    - Contradictions must be substantive (opposite directions of effect).

  INSUFFICIENT:
    - Fewer than 10% of included papers (fewer than {insufficient_threshold} papers).

Step 5 — Order themes by paper_count descending.

=== CRITICAL RULES ===

- CITATION MANDATE: The `theme_description` MUST use the provided `apa_citation_parenthetical` for every specific finding mentioned.
- Every paper must appear in at least one theme.
- Theme names must be precise (3-6 words), substantive, and specific.
- grade_rationale must cite paper count, percentage, and design/context diversity.

=== OUTPUT FORMAT ===

Return ONLY valid JSON. No preamble. No explanation. No markdown fences.
Start with [ and end with ].

[
  {
    "theme_name": "precise 3-6 word theme name",
    "paper_ids": [1, 2, 3],
    "paper_count": 3,
    "pct_of_corpus": 56.4,
    "designs_represented": ["design1", "design2"],
    "finding_direction": "convergent | divergent | mixed",
    "evidence_grade": "Established | Emerging | Contested | Insufficient",
    "grade_rationale": "one sentence explaining exactly why this grade was assigned based on count and diversity.",
    "theme_description": "4-5 sentences describing what this theme covers. You MUST use parenthetical citations from the extraction JSON to ground every claim (e.g., 'Findings show X (Author, Year)')."
  }
]