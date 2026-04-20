

## 2. Phase 1: Theory Landscape Discovery



### VERBATIM PROMPT: Theory Landscape Discovery
```markdown
You are analysing the theoretical foundations of a systematic
literature review corpus.

REVIEW OBJECTIVES:
{objectives}

RESEARCH QUESTIONS:
{rq_list}

---

THEORETICAL FRAMEWORKS EXTRACTED FROM ALL {total_papers} PAPERS:
{all_theoretical_frameworks_json}

This JSON contains for each paper: scopus_id, short_ref, year,
study_design, and theoretical_frameworks [{theory_name,
usage_type, how_used}].

---

YOUR TASK — complete all four steps:

STEP 1 — THEORY FREQUENCY MAP
Count how many papers use each named theory (primary + secondary).
Identify the top 5 most frequently used theories in this corpus.
Order by total_count descending.

STEP 2 — THEORY-THEME ALIGNMENT PREDICTION
Based on the theories present and the research objectives, predict
which theories are most likely to illuminate which aspects of the
research topic. This will be confirmed against actual themes after
the evidence matrix runs.

STEP 3 — THEORETICAL GAPS
Which important theories relevant to this phenomenon are ABSENT
from the corpus? Identify at least 2 and up to 5 absent theories.
Explain what their absence means for the field.

STEP 4 — PRIMARY LENS RECOMMENDATION
Identify the theory with the highest primary usage and best explanatory
fit for the research topic.
  a) Assess whether the most frequent theory is genuinely appropriate 
     for these research objectives.
  b) Recommend this theory as the primary lens.
  c) Provide the researcher with 2-3 alternative lenses from the corpus
     with a one-sentence rationale for each.

---

Return ONLY valid JSON. No preamble. No markdown fences.

{
  "theory_frequency": [
    {
      "theory_name": "exact theory name",
      "abbreviation": "abbreviation or null",
      "primary_count": integer,
      "secondary_count": integer,
      "total_count": integer,
      "pct_of_corpus": float,
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
      "primary_count": integer,
      "secondary_count": integer,
      "total_count": integer,
      "pct_of_corpus": float
    },
    "assessment": "2-3 sentences explaining why this lens is recommended.",
    "alternative_lenses": [
      {
        "theory_name": "alternative theory name",
        "pct_of_corpus": float,
        "rationale": "why this could be used as the primary lens"
      }
    ]
  },

  "theoretical_diversity_score": "low | medium | high",
  "theoretical_diversity_rationale": "one sentence",

  "theoretical_landscape_summary": "3-4 sentences describing the
    theoretical character of this literature.",

  "theory_usage_pattern": "applying | testing | extending |
                            challenging | building"
}
```

---

## 3. Phase 2: Conceptual Model Specification

### Purpose
[cite_start]To define the structural relationships between constructs. Following the structure of Verma et al. (2025), the model must link drivers to consequences through specific mechanisms[cite: 70, 74, 910].

### VERBATIM PROMPT: Conceptual Model Specification
```markdown
You are specifying a conceptual model for a systematic literature 
review. The model will be rendered as a diagram and published in 
the review article.

REVIEW TOPIC: {primary_topic}
PRIMARY THEORETICAL LENS: {recommended_lens_from_phase_1}

THEORETICAL PROPOSITIONS FROM THIS REVIEW:
{propositions_formatted}

THEME SYNTHESES (all reconciled texts):
{all_reconciled_texts_with_theme_names}

SUBGROUP DATA:
{subgroup_data_formatted}

---

YOUR TASK: Specify the conceptual model as a structured JSON object 
that can be rendered as a diagram.

The model must show:
1. ANTECEDENTS — factors that cause or precede the main outcome
2. MAIN OUTCOME — the primary dependent variable of this literature
3. MEDIATORS — variables that explain HOW antecedents affect outcomes
4. MODERATORS — variables that change WHEN or FOR WHOM relationships hold
5. DIRECTIONAL RELATIONSHIPS — which constructs influence which
6. EVIDENCE GRADES — how strong the evidence is for each relationship

Rules for specifying the model:
- Every node must appear in at least one relationship
- Direction: positive = same direction, negative = opposite direction,
  mixed = evidence is divided, unknown = direction unclear
- Moderators sit on arrows, not as standalone nodes
- Parsimony: The model should be readable as a figure — 8-15 nodes maximum

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
      "on_relationship": { "from": "node_id", "to": "node_id" },
      "direction": "strengthens | weakens | mixed",
      "evidence_grade": "Established|Emerging|Contested|Insufficient",
      "key_papers": ["Author et al. (Year)"]
    }
  ],
  "model_narrative": "3-4 sentences explaining how to read the model 
                      and what its key theoretical claim is."
}
```

---

## 4. Logical Integration & Human-in-the-Loop

### Theoretical Confirmation Gate
Since no lens is specified by the user, the agent *always* pauses after Phase 1. 

[cite_start]**UI Requirement:** Show the researcher the **Recommended Lens** (e.g., Social Exchange Theory  and **Alternatives** . The pipeline proceeds only after the user selects one.

### Visual Conventions
* **Antecedents:** Rectangles
* **Mediators:** Ovals
* **Consequences/Outcomes:** Double-bordered Rectangles


---

