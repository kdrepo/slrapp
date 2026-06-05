You are writing the theoretical contribution and synthesis for a high-impact systematic literature review.

PRIMARY THEORETICAL LENS:
{primary_theoretical_lens}

SUPPORTING FRAMEWORKS:
{supporting_lenses}

RESEARCH CONTEXT/DOMAIN:
{research_context}

REVIEW OBJECTIVES:
{objectives}

RESEARCH QUESTIONS:
{rq_list}

THEORETICAL LANDSCAPE:
{theoretical_landscape_summary}

RECONCILED SYNTHESES FOR ALL {theme_count} THEMES:
{all_reconciled_texts_with_theme_names}

---

TASK:
OUTPUT 1: THIRD-ORDER SYNTHESIS (350-450 words)
- Identify the overarching theoretical insight that emerges ONLY when reading all themes together through the Primary Theoretical Lens.
- Make a specific theoretical argument: How do these themes collectively challenge, extend, or refine our understanding of the phenomenon within the {research_context}?
- Do not just describe the themes; explain the "theoretical mechanics" behind the patterns.

OUTPUT 2: THEORETICAL PROPOSITIONS (3-5 propositions)
- Provide falsifiable, forward-looking theoretical propositions.
- GUIDANCE BY DOMAIN:
  - For Finance/Economics: Focus on relationships between market variables, institutional structures, risk factors, or firm-level performance.
  - For Social/Behavioral Sciences: Focus on psychological needs, social dynamics, or individual/group agency.
- CITATION MANDATE: Every proposition's 'rationale' MUST cite the specific papers (using the provided apa_citation_parenthetical) from the theme syntheses that support the logic.

OUTPUT 3: REVISED THEORETICAL FRAMEWORK NARRATIVE (200-250 words)
- Explain how the Primary Theoretical Lens should be refined or boundary-conditioned based on the review's evidence.
- Identify where the theory worked as expected and where the specific constraints of the {research_context} forced the theory to adapt.

=== CRITICAL RULES ===
- CITATION MANDATE: You MUST use APA citations (Author, Year) in the rationale for all propositions.
- TOPIC ADAPTATION: Use the provided "RESEARCH CONTEXT/DOMAIN" to ensure the synthesis is relevant to the specific subject matter.
- TONE: Maintain a high-level academic tone suitable for top-tier journal submissions.

=== OUTPUT FORMAT ===

Return ONLY valid JSON. No preamble. No markdown fences.

{
  "third_order_synthesis": "The high-level theoretical argument linking all themes via the primary lens.",
  "propositions": [
    {
      "number": 1,
      "statement": "P1: [Testable statement]",
      "rationale": "2-3 sentences explaining the logic. YOU MUST INCLUDE APA CITATIONS HERE.",
      "evidence_grade": "Established | Emerging | Contested | Insufficient",
      "themes_supporting": ["Name of Theme 1", "Name of Theme 2"]
    }
  ],
  "revised_framework_narrative": "Refinement of the primary theory based on review findings."
}