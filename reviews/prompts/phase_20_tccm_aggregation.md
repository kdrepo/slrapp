You are conducting a TCCM (Theory, Characteristics, Context, Methods)
analysis for a systematic literature review following the framework by
Paul et al. (2021).

REVIEW TOPIC:
{primary_topic}

REVIEW OBJECTIVES:
{objectives}

RESEARCH QUESTIONS:
{rq_list}

TOTAL PAPERS:
{total_papers}

DATE RANGE:
{date_range}

TCCM DATA FROM ALL INCLUDED PAPERS:
{all_tccm_json}

YOUR TASK:
Analyse each TCCM dimension and identify:
1. What is DOMINANT
2. What is PRESENT but not dominant
3. What is ABSENT
4. What this pattern MEANS for the field

Return ONLY valid JSON. No markdown fences. No preamble.

{
  "theory_dimension": {
    "theories_used": [
      {
        "theory_name": "",
        "abbreviation": null,
        "primary_count": 0,
        "secondary_count": 0,
        "total_count": 0,
        "pct_of_corpus": 0.0,
        "dominance": "dominant | present | marginal"
      }
    ],
    "theoretical_diversity_score": "low | medium | high",
    "theoretical_diversity_rationale": "",
    "dominant_theory": "",
    "absent_theories": [
      {
        "theory_name": "",
        "why_relevant": "",
        "implication": ""
      }
    ],
    "theory_usage_pattern": "applying | testing | extending | challenging | building",
    "theory_narrative": ""
  },
  "characteristics_dimension": {
    "unit_of_analysis": {
      "distribution": {},
      "dominant": "",
      "absent": [],
      "narrative": ""
    },
    "sample_types": {
      "distribution": {},
      "dominant": "",
      "concerns": ""
    },
    "longitudinal_count": 0,
    "longitudinal_pct": 0.0,
    "experimental_count": 0,
    "experimental_pct": 0.0,
    "sample_size_distribution": {},
    "journal_field_distribution": {},
    "characteristics_narrative": ""
  },
  "context_dimension": {
    "geographic_distribution": [
      {
        "country_or_region": "",
        "count": 0,
        "pct": 0.0
      }
    ],
    "geographic_concentration": "low | medium | high",
    "western_dominance_pct": 0.0,
    "underrepresented_regions": [],
    "economic_context_distribution": {},
    "platform_type_distribution": {},
    "population_group_distribution": {},
    "underrepresented_populations": [],
    "temporal_distribution": {},
    "context_narrative": ""
  },
  "methods_dimension": {
    "paradigm_distribution": {},
    "quantitative_pct": 0.0,
    "data_collection_distribution": {},
    "analysis_distribution": {},
    "pre_registered_count": 0,
    "pre_registered_pct": 0.0,
    "multi_sample_replication_count": 0,
    "multi_sample_replication_pct": 0.0,
    "absent_methods": [
      {
        "method": "",
        "why_relevant": "",
        "implication": ""
      }
    ],
    "methods_narrative": ""
  },
  "tccm_gaps_synthesis": "",
  "future_research_from_tccm": [
    {
      "gap_dimension": "Theory | Characteristics | Context | Methods",
      "gap_description": "",
      "research_direction": "",
      "priority": "high | medium | low",
      "rationale": ""
    }
  ]
}
