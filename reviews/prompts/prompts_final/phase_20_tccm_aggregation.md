You are performing a TCCM (Theory, Characteristics, Context, Methodology) meta-synthesis for a systematic literature review. 

RESEARCH CONTEXT/DOMAIN:
{research_context}

INPUT DATA:
{all_tccm_extractions_json}

The input contains the TCCM block for all {total_papers} papers, including detailed classifications for Theories, Characteristics, Context, and Methods.

---

YOUR TASK:
Aggregate the data into a high-level audit summary that identifies dominant trends and critical research gaps.

STEP 1: THEORY DIMENSION (T)
- Report the diversity of theories used.
- Identify "Thematic-Theory Clusters" (e.g., which theories are consistently used to study specific outcomes in {research_context}).

STEP 2: CHARACTERISTICS DIMENSION (C)
- Aggregate the Unit of Analysis and Sample Types.
- Identify if the field is top-heavy (e.g., focused only on large firms or only on specific worker types).

STEP 3: CONTEXT DIMENSION (C)
- Map the Geographic and Economic distribution.
- Identify underrepresented contexts (e.g., specific regions, platforms, or market types).

STEP 4: METHODOLOGY DIMENSION (M)
- Audit the Research Paradigms and Analysis types.
- Identify methodological "monocultures" (e.g., an over-reliance on cross-sectional surveys or simple regressions).

STEP 5: FUTURE RESEARCH DIRECTIONS
- Generate 4 concrete research directions based EXCLUSIVELY on the gaps identified in the steps above.

=== ADAPTIVE GUIDANCE RULES ===

- DOMAIN SENSITIVITY: Use terminology appropriate for the {research_context}.
  - (e.g., In Finance/Economics, gaps might involve a lack of 'Event Studies', 'High-frequency data', or 'Institutional Contexts').
  - (e.g., In Social Sciences, gaps might involve a lack of 'Ethnography', 'Longitudinal tracking', or 'Marginalized Populations').
- GAP FOCUS: Do not just list what is present. Explicitly name what is MISSING (the "Absent" categories).
- PARSIMONY: Ensure the summary is dense with data but logically structured for inclusion in Section 4.4.

=== OUTPUT FORMAT ===

Return ONLY valid JSON. No preamble. No markdown fences.

{
  "theory_dimension": {
    "theoretical_diversity_score": "low | medium | high",
    "dominant_theory": "Name",
    "absent_theories": [
      {
        "theory_name": "Name",
        "why_relevant": "Why it matters for {research_context}",
        "implication": "What is missing because of its absence"
      }
    ],
    "theory_narrative": "2-3 sentences on the theoretical maturity of the field."
  },
  "characteristics_dimension": {
    "unit_of_analysis_dominant": "Name",
    "sample_type_distribution": { "type": count },
    "absent_characteristics": ["e.g., firm-level data", "e.g., longitudinal samples"],
    "characteristics_narrative": "2-3 sentences on the typical subjects of study."
  },
  "context_dimension": {
    "geographic_concentration": "low | medium | high",
    "western_dominance_pct": 0.0,
    "underrepresented_regions": ["Region 1", "Region 2"],
    "underrepresented_populations": ["Group 1", "Group 2"],
    "context_narrative": "2-3 sentences on the settings of the research."
  },
  "methods_dimension": {
    "quantitative_pct": 0.0,
    "dominant_analysis": "Name",
    "absent_methods": [
      {
        "method": "Name",
        "why_relevant": "Benefit for {research_context}",
        "implication": "Current limitation without this method"
      }
    ],
    "methods_narrative": "2-3 sentences on the methodological rigour of the field."
  },
  "future_research_from_tccm": [
    {
      "gap_dimension": "Theory | Characteristics | Context | Methods",
      "gap_description": "Specific gap identified",
      "research_direction": "Proposed study or approach",
      "priority": "high | medium",
      "rationale": "Why this is the logical next step for the {research_context}"
    }
  ]
}