You are specifying a conceptual model for a systematic literature review.
The model will later be rendered as a diagram and published in the review article.

REVIEW TOPIC:
{primary_topic}

PRIMARY THEORETICAL LENS:
{primary_theoretical_lens}

THEORETICAL PROPOSITIONS FROM THIS REVIEW:
{propositions_formatted}

THEME SYNTHESES (all reconciled texts):
{all_reconciled_texts_with_theme_names}

SUBGROUP DATA:
{subgroup_data_formatted}

---

YOUR TASK:
Specify the conceptual model as a structured JSON object.

The model must show:
1. Antecedents
2. Main outcome
3. Mediators
4. Moderators
5. Directional relationships
6. Evidence grades for each relationship

Rules:
- Every node must appear in at least one relationship.
- Direction must be one of: positive | negative | mixed | unknown.
- Moderators sit on arrows, not as standalone outcome paths.
- Keep model parsimonious and readable: 8-15 nodes.

Return ONLY valid JSON. No preamble. No markdown fences.

{
  "model_title": "short title for the conceptual model figure",
  "main_outcome": {
    "id": "node_id",
    "label": "construct name",
    "definition": "one sentence definition",
    "evidence_grade": "Established|Emerging"
  },
  "antecedents": [
    {
      "id": "node_id",
      "label": "construct name",
      "definition": "one sentence definition",
      "category": "environmental | individual | contextual",
      "evidence_grade": "Established|Emerging|Contested|Insufficient"
    }
  ],
  "mediators": [
    {
      "id": "node_id",
      "label": "construct name",
      "definition": "one sentence definition",
      "evidence_grade": "Established|Emerging|Contested|Insufficient"
    }
  ],
  "moderators": [
    {
      "id": "node_id",
      "label": "construct name",
      "definition": "one sentence definition",
      "evidence_grade": "Established|Emerging|Contested|Insufficient"
    }
  ],
  "relationships": [
    {
      "from": "node_id of source construct",
      "to": "node_id of target construct",
      "relationship_type": "direct | mediated | moderated",
      "direction": "positive | negative | mixed | unknown",
      "evidence_grade": "Established|Emerging|Contested|Insufficient",
      "key_papers": ["Author et al. (Year)"],
      "label": "short label for the arrow"
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
      "evidence_grade": "Established|Emerging|Contested|Insufficient",
      "key_papers": ["Author et al. (Year)"]
    }
  ],
  "model_narrative": "3-4 sentences explaining how to read the model and what its key theoretical claim is."
}
