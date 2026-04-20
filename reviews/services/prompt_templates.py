RQ_FORMALIZATION_PROMPT = """
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

Mandatory baseline criteria that must remain present after refinement:
- Inclusion baseline: Peer-reviewed empirical studies; Document Type: Article; Language: English.
- Exclusion baseline: Theoretical papers without empirical components; non-English publications; all document types other than 'Article' (e.g., conference papers, book chapters, reviews).

Do not delete these baseline constraints. You may expand or clarify criteria, but these baseline constraints must remain in the final refined criteria.

Your task:
1. Generate 2-4 precise, answerable Research Questions for this systematic review.
2. Refine the PICO framework fields for precision and completeness.
3. Refine inclusion and exclusion criteria for clarity and screening usability.

Requirements for each RQ:
- Must be directly answerable from empirical peer-reviewed literature
- Must be specific enough to guide inclusion/exclusion decisions
- Must align with the PICO framework provided
- Must be distinct from each other (no overlap)
- Use clear academic language

Classify each RQ as one of: descriptive | comparative | causal | exploratory

Return ONLY valid JSON. No preamble. No markdown fences.

{
  "research_questions": [
    {
      "rq": "exact research question text",
      "type": "descriptive|comparative|causal|exploratory",
      "pico_alignment": "one sentence explaining which PICO elements this RQ addresses"
    }
  ],
  "refined_pico": {
    "population": "...",
    "intervention": "...",
    "comparison": "...",
    "outcomes": "..."
  },
  "refined_criteria": {
    "inclusion_criteria": ["criterion 1", "criterion 2"],
    "exclusion_criteria": ["criterion 1", "criterion 2"]
  }
}
""".strip()

SCOPUS_QUERY_PROMPT = """
Generate 4 distinct Scopus Boolean queries using TITLE-ABS-KEY.
Review Context:
Objectives:
{objectives}

Research Questions:
{research_questions}

Date Range: {start_year} to {end_year}

Mandatory Query Requirements:

Core:
- Focus on primary terms.
- Must include LIMIT-TO ( EXACTKEYWORD, ... ) for the 3-5 most central keywords.

Constructs:
- Target theoretical frameworks linked with the review domain and concepts.

Population:
- Target specific participant groups, worker/user groups, or demographic subgroups relevant to the review.

Outcomes:
- Target specific outcomes, effects, or result variables relevant to the review.

Global Filters (append to every query):
AND PUBYEAR > {start_filter} AND PUBYEAR < {end_filter} AND ( LIMIT-TO ( DOCTYPE , "ar" ) ) AND ( LIMIT-TO ( LANGUAGE , "English" ) )

Return JSON:
[{"query": "...", "focus": "core|constructs|population|outcomes", "rationale": "..."}]
""".strip()

JSON_CORRECTION_PROMPT = """
Your previous response was not valid JSON and could not be parsed.

Your previous response:
---
{raw_response}
---

Return ONLY the valid JSON object or array from your response above.
No preamble. No explanation. No markdown fences. No trailing commas.
Start with { or [ and end with } or ].
""".strip()

SCOPUS_JSON_CORRECTION_PROMPT = """
Your previous response was not valid JSON. Return ONLY the valid JSON array from that response starting with [ and ending with ].

Previous response:
---
{raw_response}
---
""".strip()

SCAFFOLD_PREAMBLE_TEMPLATE = """
=== CONSISTENCY RULES - MANDATORY, NON-NEGOTIABLE ===


LOCKED PRISMA COUNTS - use these exact numbers, no approximation:
  Records retrieved from Scopus:     {scopus_retrieved}
  After deduplication:               {after_dedup}
  Passed title/abstract screening:   {passed_ta}
  Full texts retrieved:              {pdfs_retrieved}
  Assessed as abstract only:         {abstract_only}
  Passed full-text assessment:       {passed_fulltext}
  Excluded by researcher:            {user_excluded}
  Final included:                    {final_included}

LOCKED THEME NAMES - use exactly as written, never paraphrase:
{theme_names_numbered}

LOCKED EVIDENCE GRADES (by theme):
{evidence_grades}

THEORETICAL FRAMEWORK (locked):
  Primary lens: {theory_primary_lens}
  Supporting lenses: {theory_supporting_lenses}
  Dominant theory: {theory_dominant}
  Coverage: {theory_coverage}
  Gaps: {theory_gaps}
  Landscape summary: {theory_landscape_summary}

THEORETICAL SYNTHESIS (locked):
Third-order synthesis:
{third_order_synthesis}
Propositions:
{propositions_formatted}
Revised framework narrative:
{revised_framework_narrative}

QUALITY SUMMARY (locked):
{quality_summary}

SUBGROUP DATA (locked):
{subgroup_data}

REVIEW METADATA (locked):
{review_metadata}

EVIDENCE LANGUAGE RULES - apply based on each theme's grade:
  Established (>=60% corpus, multiple designs):
    Use: 'demonstrates', 'establishes', 'consistently shows', 'confirms'
    Do not use: 'suggests', 'indicates', 'appears to'
  Emerging (10-60%, mostly one design):
    Use: 'suggests', 'indicates', 'growing evidence shows'
    Do not use: 'demonstrates', 'establishes', 'confirms'
  Contested (contradictory findings):
    Use: 'remains debated', 'evidence is mixed', 'findings diverge'
    Do not use language implying consensus
  Insufficient (<10% corpus):
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
[{paper_count} papers in registry - citations not required for this section.
Do not cite any individual paper in this section.]

STUDY SCOPE (PICO):
Population: {pico_population}
Outcome: {pico_outcomes}

RESEARCH QUESTIONS - all must be explicitly addressed in Results and Discussion:
{rq_numbered_list}

STYLE RULES:
  Academic third person throughout.
  Past tense: for what studies did, found, reported.
  Present tense: for what evidence shows, demonstrates, suggests.
  TRANSITIONS: Avoid formulaic transitions (e.g., 'Moreover', 'In addition'). Use conceptual transitions that link findings based on shared variables or contexts.
  No bullet points. Continuous prose only.
  Average sentence length: 22-28 words.
  No first person (no 'we', 'our', 'I').

=== END CONSISTENCY RULES ===

[SECTION LABEL BLOCK - previous sections if applicable]
{previous_sections_labelled}
""".strip()

SCREENING_SYSTEM_PROMPT = """
You are an expert academic reviewer conducting abstract-level screening for a Systematic Literature Review (SLR).

You will receive:
- Review Objectives
- Locked Research Questions
- Inclusion Criteria
- Exclusion Criteria
- Paper Title and Abstract

Screening Rules (STRICT):
- INCLUDE if the abstract directly addresses at least one locked research question and satisfies inclusion criteria.
- EXCLUDE if exclusion criteria are triggered, population/context is out of scope, or RQ linkage is absent/incidental.
- Be conservative and evidence-grounded: prefer exclusion over weak inclusion.

Decision guidance:
- Base judgment on semantic meaning, not keyword matching.
- Use only evidence present in the title/abstract.
- If uncertain, lower confidence and explain the uncertainty clearly.

Confidence guidance:
- 0.90-0.95: direct, explicit relevance to RQ(s)
- 0.80-0.89: strong but slightly indirect relevance
- 0.60-0.79: ambiguous relevance
- <0.60: weak relevance

Return ONLY JSON (single object) in this exact schema:
{ "decision": "included" | "excluded", "confidence": 0.0-1.0, "reason": "One concise evidence-grounded justification", "criterion_failed": "Specific exclusion criterion triggered, or null" }

No preamble. No markdown. No extra keys.
""".strip()

SCREENING_JSON_CORRECTION_PROMPT = """
Your previous response was not valid JSON. Return ONLY valid JSON from that response.

Previous response:
---
{raw_response}
---
""".strip()

