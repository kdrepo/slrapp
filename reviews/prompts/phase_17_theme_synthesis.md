# Placeholders:
# {objectives}
# {rq_list_numbered}
# {total_papers}
# {established_threshold}
# {emerging_min}
# {emerging_max}
# {insufficient_threshold}
# {all_extractions_json}

You are conducting a thematic synthesis for a systematic literature review.

Your task is to identify the major themes that emerge from the evidence
corpus below, then assign an evidence grade to each theme based on
objective criteria.

=== REVIEW CONTEXT ===

RESEARCH OBJECTIVES:
{objectives}

RESEARCH QUESTIONS:
{rq_list_numbered}

TOTAL CONFIRMED PAPERS: {total_papers}

=== EVIDENCE CORPUS ===

Below are the structured extractions from all {total_papers} included papers.
Each entry contains: paper_id, short citation reference, year, study design,
population, intervention/context, outcomes, country, and key findings.

{all_extractions_json}

=== YOUR TASK ===

Step 1 — Read all {total_papers} extractions carefully.

Step 2 — Identify 3 to 5 distinct themes that emerge from the evidence.

A theme must:
  - Appear across multiple papers (minimum 3 papers, except Insufficient grade)
  - Represent a substantive finding pattern, not just a topic label
  - Be directly relevant to the research questions above
  - Be distinct from other themes (papers can appear in more than one theme
    but the themes themselves should not substantially overlap)

Step 3 — For each theme, list which paper_id values address it.
A paper addresses a theme if its findings, population, or intervention/context
is directly related to that theme — not merely mentions it in passing.

Step 4 — Assign an evidence grade using these exact criteria:

  ESTABLISHED:
    - 60% or more of all included papers ({established_threshold} or more papers)
    - AND findings are broadly convergent across multiple study designs

  EMERGING:
    - 10% to 59% of included papers ({emerging_min} to {emerging_max} papers)
    - OR findings come predominantly from one study design

  CONTESTED:
    - Papers in the corpus directly contradict each other on this theme
    - Contradictions are substantive (opposite directions of effect)

  INSUFFICIENT:
    - Fewer than 10% of included papers (fewer than {insufficient_threshold} papers)

Step 5 — Order themes by paper_count descending (most-evidenced first).

=== CRITICAL RULES ===

- Every paper must appear in at least one theme.
- A paper may appear in multiple themes if findings genuinely span more than one theme.
- Theme names must be precise (3-6 words), substantive, and specific.
- Evidence grades are determined strictly by the criteria above.
- grade_rationale must cite paper count, percentage, and design diversity.

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
    "grade_rationale": "one sentence explaining exactly why this grade was assigned",
    "theme_description": "2-3 sentences describing what this theme covers and what the papers collectively show"
  }
]
