Yes, the prompt needs modification. There are two scenarios:

1. User specified a lens → validate and use it
2. User left it blank → identify dominant theory from corpus and recommend one

---

### Modified Prompt: Theory Landscape Analysis

```
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

PRIMARY THEORETICAL LENS SPECIFIED BY RESEARCHER:
{theoretical_lens_or_none}

Note: This field may be empty. See instructions below.

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
from the corpus? Their absence is itself a finding — it means the
field has not theoretically engaged with certain perspectives.
Identify at least 2 and up to 5 absent theories.

STEP 4 — PRIMARY LENS DETERMINATION
This step has two paths depending on whether the researcher
specified a lens.

PATH A — RESEARCHER SPECIFIED A LENS:
Use this path if PRIMARY THEORETICAL LENS above is not empty.
  a) How many papers in this corpus engage with this theory?
     Count both primary and secondary usage.
  b) Is this an appropriate lens given the evidence base?
     Appropriate means: used in at least 20% of the corpus,
     maps onto the core constructs being studied, and has
     explanatory power for the phenomenon.
  c) If appropriate: confirm it as the primary lens.
  d) If NOT appropriate: explain why, then identify the
     best-supported alternative from Step 1 and recommend it.
  e) Set lens_was_specified = true in your output.

PATH B — NO LENS SPECIFIED:
Use this path if PRIMARY THEORETICAL LENS above is empty or
says "Not specified" or "Not sure".
  a) From Step 1, identify the theory with the highest
     primary_count as the candidate dominant theory.
  b) Assess whether it is genuinely appropriate for this
     research topic and objectives — not just the most frequent.
  c) If appropriate: recommend it as the primary lens.
  d) If the most frequent theory is NOT the most appropriate:
     recommend a better-suited theory and explain why.
  e) In either case: provide the researcher with 2-3 alternatives
     they could also choose from, with a one-sentence rationale
     for each alternative.
  f) Set lens_was_specified = false in your output.
  g) Set requires_researcher_confirmation = true — the system
     will present the recommendation to the researcher for
     approval before synthesis begins.

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
    "lens_was_specified": true or false,
    "specified_lens": "lens name if specified by researcher, else null",
    "recommended_lens": "the lens recommended for use in synthesis",
    "recommended_lens_coverage": {
      "primary_count": integer,
      "secondary_count": integer,
      "total_count": integer,
      "pct_of_corpus": float
    },
    "is_appropriate": true or false,
    "assessment": "2-3 sentences explaining why this lens is
                   recommended — cite coverage percentage, fit
                   with research objectives, and explanatory power",
    "requires_researcher_confirmation": true or false,
    "alternative_lenses": [
      {
        "theory_name": "alternative theory name",
        "pct_of_corpus": float,
        "rationale": "one sentence — why this could be the primary lens"
      }
    ]
  },

  "theoretical_diversity_score": "low | medium | high",
  "theoretical_diversity_rationale": "one sentence",

  "theoretical_landscape_summary": "3-4 sentences describing the
    theoretical character of this literature — is it theoretically
    diverse or concentrated? Are papers extending theory or just
    applying it? Is there theoretical consensus or fragmentation?",

  "theory_usage_pattern": "applying | testing | extending |
                            challenging | building — what is the
                            dominant relationship between papers
                            and their theoretical frameworks?"
}
```

---

### What Changes in the System Around This Prompt

The response handling has one branch:

```python
# pipeline/dialectical_synthesizer.py

result = json.loads(call_gemini_pro(THEORY_LANDSCAPE_PROMPT.format(...)))
assessment = result['primary_lens_assessment']

if assessment['requires_researcher_confirmation']:
    # PATH B was taken — no lens was specified
    # Store recommendation and alternatives
    review.scaffold['theoretical_framework'] = {
        'primary_lens':   None,              # not yet confirmed
        'recommended':    assessment['recommended_lens'],
        'alternatives':   assessment['alternative_lenses'],
        'status':         'awaiting_confirmation'
    }
    review.status = 'theory_confirmation'
    review.save()
    # Pipeline pauses — user sees confirmation UI
    # (same pattern as paper confirmation window)

else:
    # PATH A was taken — lens was specified and validated
    # OR PATH B where recommended lens is auto-accepted
    review.scaffold['theoretical_framework'] = {
        'primary_lens':   assessment['recommended_lens'],
        'alternatives':   assessment['alternative_lenses'],
        'status':         'confirmed'
    }
    review.save()
    # Pipeline continues immediately to evidence matrix
```

---

### The Theory Confirmation UI (When No Lens Was Specified)

A brief pause page — simpler than paper confirmation, typically resolved in under a minute:

```
Theoretical Lens Recommendation

Based on analysis of your 55 included papers, we recommend:

PRIMARY LENS:  Cognitive Load Theory (CLT)
Coverage:      54.5% of your papers use this theory (30 of 55)
Why:           CLT maps directly onto platform design mechanisms
               that exploit working memory limits, and dominates
               the corpus both in frequency and explanatory fit
               for your research objectives.

Alternatives you could choose instead:
  • Social Cognitive Theory (SCT) — 36.4% coverage
    Strong fit if your focus is on self-efficacy and behavioural
    learning responses to vulnerability
  • Technology Acceptance Model (TAM) — 32.7% coverage
    Better fit if adoption and usage behaviour is central
    rather than vulnerability outcomes

[ Use Cognitive Load Theory ]  [ Choose an alternative ]
```

User clicks one option. `review.scaffold['theoretical_framework']['primary_lens']` is set. `review.status = 'running'`. Pipeline continues to the evidence matrix.

If the user does not respond within 24 hours, the recommended lens is auto-accepted and the pipeline continues.

---

### Expected Output — Path A (Lens Specified)

```json
{
  "theory_frequency": [
    {
      "theory_name": "Cognitive Load Theory",
      "abbreviation": "CLT",
      "primary_count": 18,
      "secondary_count": 12,
      "total_count": 30,
      "pct_of_corpus": 54.5,
      "dominance": "dominant"
    }
  ],
  "theoretical_gaps": [
    {
      "theory_name": "Prospect Theory",
      "why_relevant": "Dark patterns exploit loss aversion and framing effects directly",
      "implication": "Mechanism-level explanation for why dark patterns work is absent"
    }
  ],
  "primary_lens_assessment": {
    "lens_was_specified": true,
    "specified_lens": "Cognitive Load Theory",
    "recommended_lens": "Cognitive Load Theory",
    "recommended_lens_coverage": {
      "primary_count": 18,
      "secondary_count": 12,
      "total_count": 30,
      "pct_of_corpus": 54.5
    },
    "is_appropriate": true,
    "assessment": "Cognitive Load Theory is well-supported at 54.5% corpus coverage and maps directly onto the mechanisms through which platform design amplifies vulnerability via working memory overload. Its dominance across both quantitative and qualitative studies confirms it as the appropriate primary lens for this synthesis.",
    "requires_researcher_confirmation": false,
    "alternative_lenses": [
      {
        "theory_name": "Social Cognitive Theory",
        "pct_of_corpus": 36.4,
        "rationale": "Strong alternative if self-efficacy and adaptive behaviour responses to vulnerability are central to the synthesis"
      }
    ]
  },
  "theoretical_diversity_score": "medium",
  "theoretical_diversity_rationale": "Five theories identified but CLT dominates at 54.5% with others in supporting roles",
  "theoretical_landscape_summary": "The literature exhibits moderate theoretical concentration with CLT as the clear dominant framework. Papers predominantly apply existing theories rather than extending them, suggesting limited theoretical contribution from individual studies. Notable absences include behavioural economics frameworks despite their direct relevance to dark pattern mechanisms.",
  "theory_usage_pattern": "applying"
}
```

---

### Expected Output — Path B (No Lens Specified)

```json
{
  "theory_frequency": [
    {
      "theory_name": "Cognitive Load Theory",
      "abbreviation": "CLT",
      "primary_count": 18,
      "secondary_count": 12,
      "total_count": 30,
      "pct_of_corpus": 54.5,
      "dominance": "dominant"
    },
    {
      "theory_name": "Social Cognitive Theory",
      "abbreviation": "SCT",
      "primary_count": 12,
      "secondary_count": 8,
      "total_count": 20,
      "pct_of_corpus": 36.4,
      "dominance": "present"
    }
  ],
  "theoretical_gaps": [
    {
      "theory_name": "Prospect Theory",
      "why_relevant": "Dark patterns exploit loss aversion and framing effects directly",
      "implication": "Mechanism-level explanation for why dark patterns work is absent"
    },
    {
      "theory_name": "Intersectionality Theory",
      "why_relevant": "Vulnerability dimensions co-occur and compound multiplicatively",
      "implication": "Additive models underestimate vulnerability in multi-risk consumers"
    }
  ],
  "primary_lens_assessment": {
    "lens_was_specified": false,
    "specified_lens": null,
    "recommended_lens": "Cognitive Load Theory",
    "recommended_lens_coverage": {
      "primary_count": 18,
      "secondary_count": 12,
      "total_count": 30,
      "pct_of_corpus": 54.5
    },
    "is_appropriate": true,
    "assessment": "Cognitive Load Theory is the corpus-dominant framework at 54.5% coverage and has strong explanatory fit for the research objectives — platform design features operate through working memory overload mechanisms that CLT was developed to explain. No researcher-specified lens was provided, and CLT is recommended as the primary lens with Social Cognitive Theory as a supporting framework.",
    "requires_researcher_confirmation": true,
    "alternative_lenses": [
      {
        "theory_name": "Social Cognitive Theory",
        "pct_of_corpus": 36.4,
        "rationale": "Better fit if self-efficacy and behavioural learning responses to vulnerability are more central than cognitive overload mechanisms"
      },
      {
        "theory_name": "Protection Motivation Theory",
        "pct_of_corpus": 25.5,
        "rationale": "Strong fit if consumer protective responses and threat appraisal are the primary focus rather than vulnerability induction"
      }
    ]
  },
  "theoretical_diversity_score": "medium",
  "theoretical_diversity_rationale": "Five theories present but CLT dominates; the field is theoretically concentrated rather than pluralistic",
  "theoretical_landscape_summary": "No theoretical lens was specified by the researcher. Analysis of the corpus identifies Cognitive Load Theory as the dominant framework at 54.5% coverage, with strong fit for the research objectives. The literature applies rather than extends theory, and notable absences include Prospect Theory and Intersectionality Theory despite their direct relevance.",
  "theory_usage_pattern": "applying"
}
```

---

The only structural difference between Path A and Path B output is:
- `lens_was_specified`: true vs false
- `specified_lens`: populated vs null
- `requires_researcher_confirmation`: false vs true

Everything else — frequency map, gaps, diversity score, landscape summary — is identical regardless of path. The system handles the branching in code, not in the prompt.