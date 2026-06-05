scaffold = {

    # ── 1. PRISMA COUNTS ─────────────────────────────────────────────────────
    # Source: DB queries at scaffold assembly time
    # Used in: every writing call, PRISMA diagram, consistency checker
    "prisma_counts": {
        "scopus_retrieved":     847,   # Paper.objects.filter(review=review).count()
        "after_dedup":          634,   # excluding Duplicate exclusion_criterion
        "ta_screened":          619,   # ta_decision not 'pending' (excl empty-abstract flagged)
        "passed_ta":            150,   # title_abstract_decision = 'included' or 'flagged'
        "flagged_ta":           35,    # screening_conflict = True
        "pdfs_retrieved":       115,   # fulltext_retrieved = True
        "abstract_only":        35,    # fulltext_retrieved = False, final=included
        "user_uploaded":        18,    # user_uploaded = True
        "fulltext_screened":    103,   # fulltext_decision populated (excl auto-included)
        "auto_included":        47,    # ta_confidence >= 0.92
        "passed_fulltext":      110,   # final_decision = 'included' before user confirm
        "user_excluded":        8,     # user_excluded = True
        "final_included":       55,    # confirmed, not user_excluded
    },

    # ── 2. CANONICAL TERMINOLOGY ─────────────────────────────────────────────
    # Source: one Gemini Pro call analysing keyword frequencies
    # Used in: scaffold preamble, consistency checker
    "canonical_terms": {
        "primary":  "consumer vulnerability",
        "banned":   [
            "consumer vulnerabilities",
            "consumer fragility",
            "consumer susceptibility"
        ],
        "acceptable_related": [
            "vulnerable consumers",
            "consumer welfare",
            "consumer harm"
        ]
    },

    # ── 3. RESEARCH QUESTIONS ────────────────────────────────────────────────
    # Source: user confirmed in Phase 2 — locked before pipeline started
    # Used in: Discussion prompt (must address all), consistency checker,
    #          Introduction, Conclusion, Abstract
    "research_questions": [
        "To what extent do digital marketplace environments amplify consumer vulnerability compared to traditional retail contexts?",
        "What individual-level factors mediate the relationship between digital market exposure and consumer vulnerability outcomes?",
        "Which intervention strategies have demonstrated effectiveness in reducing consumer vulnerability in digital market settings?"
    ],

    # ── 4. THEME NAMES ───────────────────────────────────────────────────────
    # Source: evidence matrix call output → ThemeSynthesis DB records
    # Used in: all synthesis calls, writing calls, consistency checker,
    #          theme graphs, Synthesis section headings
    # NOTE: populated AFTER evidence matrix runs, BEFORE scaffold locked
    "theme_names": [
        "Platform Design and Exploitation Mechanisms",
        "Digital Literacy as Vulnerability Mediator",
        "Age and Cognitive Vulnerability Factors",
        "Consumer Protection Awareness and Redress",
        "Intervention Effectiveness and Design",
        "Regulatory Frameworks and Enforcement"
    ],

    # ── 5. EVIDENCE GRADES ───────────────────────────────────────────────────
    # Source: evidence matrix call output → ThemeSynthesis DB records
    # Used in: scaffold preamble evidence language rules,
    #          Advocate/Critic/Reconciler prompts, Synthesis writing
    "evidence_grades": {
        "Platform Design and Exploitation Mechanisms":  "Established",
        "Digital Literacy as Vulnerability Mediator":   "Emerging",
        "Age and Cognitive Vulnerability Factors":      "Emerging",
        "Consumer Protection Awareness and Redress":    "Emerging",
        "Intervention Effectiveness and Design":        "Emerging",
        "Regulatory Frameworks and Enforcement":        "Insufficient"
    },

    # ── 6. PAPER REGISTRY ────────────────────────────────────────────────────
    # Source: Paper DB records for all 55 confirmed papers
    # Used in: every writing call that needs citations (registry sections),
    #          consistency checker (only these may be cited),
    #          APA formatter receives full metadata separately
    # 55 entries total — one per confirmed paper
    "paper_registry": [
        {
            "scopus_id":  "SCOPUS:85201234",
            "short_ref":  "Baker et al. (2019)",   # for in-text citation
            "year":       2019,
            "title":      "Consumer vulnerability in digital markets...",
            "journal":    "Journal of Consumer Research",
            "doi":        "10.1093/jcr/ucz052"
        },
        {
            "scopus_id":  "SCOPUS:85209876",
            "short_ref":  "Smith & Jones (2021)",
            "year":       2021,
            "title":      "Digital exclusion and elderly consumers...",
            "journal":    "Journal of Marketing",
            "doi":        "10.1177/00222429211012345"
        },
        # ... 53 more entries
    ],

    # ── 7. QUALITY SUMMARY ───────────────────────────────────────────────────
    # Source: QualityAssessment DB records aggregated
    # Used in: Results: Quality Assessment writing call,
    #          quality table in DOCX
    "quality_summary": {
        "mean_score":       7.2,
        "score_range":      "4–9",
        "low_risk":         22,    # risk_of_bias = 'low'
        "moderate_risk":    28,    # risk_of_bias = 'moderate'
        "high_risk":        5,     # risk_of_bias = 'high'
        "by_design": {
            "cross-sectional":  {"mean": 7.4, "count": 22},
            "qualitative":      {"mean": 7.1, "count": 14},
            "RCT":              {"mean": 8.1, "count": 8},
            "mixed-methods":    {"mean": 6.9, "count": 7},
            "other":            {"mean": 6.2, "count": 4}
        }
    },

    # ── 8. SUBGROUP DATA ─────────────────────────────────────────────────────
    # Source: DataExtraction DB records, Paper DB records
    # Used in: Results: Subgroup Analysis writing call,
    #          subgroup graphs, document builder
    "subgroup_data": {
        "by_design": {
            "cross-sectional":    22,
            "qualitative":        14,
            "RCT":                8,
            "mixed-methods":      7,
            "quasi-experimental": 2,
            "case-study":         2
        },
        "by_country": {
            "United Kingdom":  12,
            "United States":   10,
            "Australia":       6,
            "Germany":         4,
            "China":           3,
            "Multi-country":   8,
            "Other":           12
        },
        "by_year": {
            2010: 1, 2011: 1, 2012: 2,
            2013: 1, 2014: 2, 2015: 3,
            2016: 3, 2017: 4, 2018: 5,
            2019: 7, 2020: 8, 2021: 9,
            2022: 6, 2023: 3
        },
        "year_span":            13,
        "sankey_eligible":      True,   # year_span >= 10
        "year_subgroup_eligible": True  # >= 3 years with >= 3 papers each
    },

    # ── 9. PICO FRAMEWORK ────────────────────────────────────────────────────
    # Source: user intake form (verbatim)
    # Used in: Methods: Criteria writing call, PICO table in DOCX
    "pico": {
        "population":    "Adult consumers engaging with digital marketplaces",
        "intervention":  "Digital market exposure, platform design features",
        "comparison":    "Traditional retail environments or no intervention",
        "outcomes":      "Consumer vulnerability scores, harm outcomes, protective behaviors"
    },

    # ── 10. RQ ANSWERS ───────────────────────────────────────────────────────
    # Source: populated AFTER synthesis — one answer summary per RQ
    # Used in: Discussion and Conclusion writing calls
    # NOTE: this is the only key populated after scaffold is locked —
    #       updated as a controlled write after synthesis completes
    "rq_answers": {
        "To what extent do digital marketplace environments...":
            "Digital marketplace environments consistently demonstrate significantly elevated consumer vulnerability compared to traditional retail contexts, with effect sizes in the moderate-to-large range across quantitative studies",
        "What individual-level factors mediate...":
            "Digital literacy is the most consistently evidenced mediating factor, though its independence from socioeconomic confounds remains contested; age-related cognitive factors operate as additional independent mediators",
        "Which intervention strategies...":
            "Evidence for intervention effectiveness is emerging but inconsistent; mandatory interface regulation shows the most promise while voluntary literacy training effects are short-lived"
    },

    # ── 11. REVIEW METADATA ──────────────────────────────────────────────────
    # Source: Review DB record
    # Used in: title page, Methods sections, Abstract
    "review_metadata": {
        "title":           "Consumer Vulnerability in Digital Markets: A Systematic Review",
        "date_completed":  "2024-03-15",
        "date_range":      "2010–2024",
        "language":        "English",
        "database":        "Scopus",
        "query_count":     5,
        "prospero_number": ""   # user fills this manually before submission
    }
}
```

---

## Lock Sequence — What Gets Written When

Not everything is available at the same time. Items are written to the scaffold in this order:
```
PHASE 1 — After extraction batch completes:
  prisma_counts          ← from DB queries
  canonical_terms        ← from canonical term identification call
  research_questions     ← already locked from Phase 2 (form submission)
  paper_registry         ← from Paper DB records
  quality_summary        ← from QualityAssessment records aggregated
  subgroup_data          ← from DataExtraction + Paper records
  pico                   ← from Review.pico (user input)
  review_metadata        ← from Review record
  theme_names: []        ← empty, not yet known
  evidence_grades: {}    ← empty, not yet known
  rq_answers: {}         ← empty, not yet known

  scaffold_locked = True ← written now

PHASE 2 — After evidence matrix call (controlled update):
  theme_names            ← from ThemeSynthesis records
  evidence_grades        ← from ThemeSynthesis records
  (scaffold_locked remains True — only these two keys updated)

PHASE 3 — After dialectical synthesis (controlled update):
  rq_answers             ← written after reconciled texts are complete
  (scaffold_locked remains True — only this key updated)