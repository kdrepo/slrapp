You are specifying a conceptual model for a high-impact systematic literature review.
The model will serve as the logical blueprint for the review's visual framework and the "Section 3.5" discussion.

RESEARCH CONTEXT/DOMAIN:
{research_context}

PRIMARY THEORETICAL LENS:
{primary_theoretical_lens}

THEORETICAL PROPOSITIONS FROM THIS REVIEW:
{propositions_formatted}

THEME SYNTHESES (all reconciled texts):
{all_reconciled_texts_with_theme_names}

---

YOUR TASK:
Specify the conceptual model as a structured JSON object.

The model must show the logical flow of the {research_context} phenomenon:
1. Antecedents (External or internal drivers)
2. Main outcome (The primary phenomenon being studied)
3. Mediators (The "how" - the mechanisms connecting drivers to outcomes)
4. Moderators (The "when" - the boundary conditions or context-specific factors)
5. Directional relationships with evidence grades

=== ADAPTIVE GUIDANCE RULES ===

- CONSTRUCT DISCOVERY: Identify constructs that are empirically supported by the provided {all_reconciled_texts_with_theme_names}. Do not limit the model to pre-conceived categories; let the data drive the discovery of nodes.
- DOMAIN ALIGNMENT: Ensure constructs are labeled using terminology appropriate for the {research_context}.
  - (e.g., In Finance/Economics, look for structural moderators like 'Market Volatility', 'Regulatory Quality', or 'Information Asymmetry', but prioritize what is actually in the text).
  - (e.g., In Social/Behavioral Sciences, look for mechanisms like 'Psychological Need Satisfaction', 'Social Support', or 'Trust', but prioritize what is actually in the text).
- THEORETICAL ALIGNMENT: Use the constructs associated with the {primary_theoretical_lens} as the primary nodes where possible, specifically where they help explain the {propositions_formatted}.
- PARSIMONY: Keep the model readable and logically tight (8-15 nodes total). Every node must appear in at least one relationship.
- CITATION MANDATE: For every relationship, you MUST populate the 'key_papers' array with the relevant 'apa_citation_parenthetical' strings from the theme syntheses.

=== OUTPUT FORMAT ===

Return ONLY valid JSON. No preamble. No markdown fences.

{
  "model_title": "Short title for the conceptual model figure",
  "main_outcome": {
    "id": "node_id",
    "label": "Construct Name",
    "definition": "One sentence definition based on the findings",
    "evidence_grade": "Established | Emerging"
  },
  "antecedents": [
    {
      "id": "node_id",
      "label": "Construct Name",
      "definition": "One sentence definition",
      "category": "environmental | individual | contextual",
      "evidence_grade": "Established | Emerging | Contested | Insufficient"
    }
  ],
  "mediators": [
    {
      "id": "node_id",
      "label": "Construct Name",
      "definition": "Explanation of the mechanism",
      "evidence_grade": "Established | Emerging | Contested | Insufficient"
    }
  ],
  "moderators": [
    {
      "id": "node_id",
      "label": "Construct Name",
      "definition": "Boundary condition definition",
      "evidence_grade": "Established | Emerging | Contested | Insufficient"
    }
  ],
  "relationships": [
    {
      "from": "node_id of source",
      "to": "node_id of target",
      "relationship_type": "direct | mediated | moderated",
      "direction": "positive | negative | mixed | unknown",
      "evidence_grade": "Established | Emerging | Contested | Insufficient",
      "key_papers": ["Author (Year)", "Author (Year)"],
      "label": "Short label for the arrow"
    }
  ],
  "moderating_relationships": [
    {
      "moderator_id": "node_id of moderator",
      "on_relationship": {
        "from": "node_id",
        "to": "node_id"
      },
      "direction": "strengthens | weakens | mixed",
      "evidence_grade": "Established | Emerging | Contested | Insufficient",
      "key_papers": ["Author (Year)"]
    }
  ],
  "model_narrative": "3-4 sentences explaining how the model explains the {research_context} phenomenon through the lens of {primary_theoretical_lens}."
}