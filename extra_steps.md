## Theoretical Framework Anchoring + Conceptual Model — How and Full Prompts

---

## Part 1 — Theoretical Framework Anchoring

### The Core Idea

Every empirical paper in your corpus is built on a theory — whether explicitly stated or implicitly assumed. Consumer vulnerability research draws on Cognitive Load Theory, Social Cognitive Theory, Resource-Based View of the consumer, Protection Motivation Theory, Technology Acceptance Model, Institutional Theory, and others.

Without anchoring your synthesis to theory, your SLR answers "what happened across these studies." With theoretical anchoring, it answers "what do these findings mean for our theoretical understanding of the phenomenon and how should theory be revised or extended." That is the difference between a review article and a theoretical contribution — which is what A* journals require.

---

### Where It Enters the Pipeline

Theory anchoring touches four places:

```
INTAKE FORM          → user specifies primary theoretical lens
      ↓
EXTRACTION CALL      → each paper: what theory does it use?
      ↓
EVIDENCE MATRIX      → which theories appear across themes?
      ↓
RECONCILER PASSES    → synthesis argues at theoretical level, not just empirical
      ↓
CROSS-THEME CALL     → what does the combined evidence mean for theory?
      ↓
WRITING: Discussion  → theoretical contributions section
```

---

### Step 1 — Intake Form Addition

Add one field to the intake form:

```
Theoretical Lens (optional but strongly recommended):
  Which theoretical framework should anchor this review?
  
  Examples:
    - Cognitive Load Theory
    - Social Cognitive Theory  
    - Technology Acceptance Model
    - Institutional Theory
    - Resource-Based View
    - Protection Motivation Theory
    - Not sure — identify from literature

  If "Not sure": system identifies dominant theories from 
  extraction data and presents them for user selection before 
  synthesis begins.
```

Store as `review.theoretical_lens` — a text field. If blank, the system identifies the dominant theory from extraction data automatically.

---

### Step 2 — Extraction Call Addition

The merged extraction prompt gains one field in the extraction object:

```
"theoretical_frameworks": [
  {
    "theory_name": "name of theory used or referenced",
    "usage_type": "primary | secondary | implicit",
    "how_used": "one sentence — does this paper test, extend, challenge, or apply the theory?"
  }
]
```

Usage types:
- **Primary** — the paper explicitly names this as its theoretical foundation
- **Secondary** — the theory is referenced to contextualise findings but is not the primary lens
- **Implicit** — the paper uses concepts from the theory without naming it (you identify this from the constructs and relationships studied)

This field is extracted from the same PDF text already being processed. No extra call, no extra tokens beyond what the extraction already reads.

---

### Step 3 — Theory Landscape Call

After all extractions complete, before the evidence matrix, one new call analyses the theoretical landscape across the corpus.

---

#### Prompt: Theory Landscape Analysis

```
You are analysing the theoretical foundations of a systematic 
literature review corpus.

REVIEW OBJECTIVES:
{objectives}

RESEARCH QUESTIONS:
{rq_list}

PRIMARY THEORETICAL LENS SPECIFIED BY RESEARCHER:
{theoretical_lens}

---

THEORETICAL FRAMEWORKS EXTRACTED FROM ALL {total_papers} PAPERS:
{all_theoretical_frameworks_json}

This JSON contains for each paper: scopus_id, short_ref, year,
study_design, and theoretical_frameworks [{theory_name, usage_type, 
how_used}].

---

YOUR TASK — complete all four steps:

STEP 1 — THEORY FREQUENCY MAP
Count how many papers use each named theory (primary + secondary).
Identify the top 5 most frequently used theories in this corpus.

STEP 2 — THEORY-THEME ALIGNMENT PREDICTION
Based on the theories present and the research objectives, predict
which theories are most likely to illuminate which aspects of
{primary_topic}. This will be confirmed against actual themes after
the evidence matrix runs.

STEP 3 — THEORETICAL GAPS
Which important theories relevant to this phenomenon are ABSENT from
the corpus? Their absence is itself a finding — it means the field
has not theoretically engaged with certain perspectives.

STEP 4 — PRIMARY LENS VALIDATION
The researcher has specified {theoretical_lens} as the primary 
theoretical lens. Assess:
  a) How many papers in this corpus engage with this theory?
  b) Is this an appropriate lens given the evidence base?
  c) If not well-represented, suggest a better-supported alternative.

Return ONLY valid JSON. No preamble. No markdown fences.

{
  "theory_frequency": [
    {
      "theory_name": "exact theory name",
      "primary_count": integer,
      "secondary_count": integer,
      "total_count": integer,
      "pct_of_corpus": float,
      "paper_ids": ["SCOPUS:id1", "SCOPUS:id2"]
    }
  ],
  "dominant_theory": "the single most used theory by primary count",
  "theoretical_gaps": [
    {
      "theory_name": "absent theory name",
      "relevance": "why this theory should be present",
      "implication": "what its absence means for the field"
    }
  ],
  "primary_lens_assessment": {
    "papers_using_it": integer,
    "pct_of_corpus": float,
    "is_appropriate": true or false,
    "assessment": "2-3 sentence explanation",
    "recommended_lens": "if not appropriate, what to use instead"
  },
  "theoretical_landscape_summary": "3-4 sentences describing the 
    theoretical character of this literature — is it theoretically 
    diverse or concentrated? Are papers extending theory or just 
    applying it? Is there theoretical consensus or fragmentation?"
}
```

**Expected Output:**

```json
{
  "theory_frequency": [
    {
      "theory_name": "Cognitive Load Theory",
      "primary_count": 18,
      "secondary_count": 12,
      "total_count": 30,
      "pct_of_corpus": 54.5,
      "paper_ids": ["SCOPUS:85201234", "SCOPUS:85209876"]
    },
    {
      "theory_name": "Social Cognitive Theory",
      "primary_count": 12,
      "secondary_count": 8,
      "total_count": 20,
      "pct_of_corpus": 36.4,
      "paper_ids": ["SCOPUS:85201111", "SCOPUS:85202222"]
    },
    {
      "theory_name": "Protection Motivation Theory",
      "primary_count": 9,
      "secondary_count": 5,
      "total_count": 14,
      "pct_of_corpus": 25.5,
      "paper_ids": ["SCOPUS:85203333"]
    },
    {
      "theory_name": "Technology Acceptance Model",
      "primary_count": 7,
      "secondary_count": 11,
      "total_count": 18,
      "pct_of_corpus": 32.7,
      "paper_ids": ["SCOPUS:85204444"]
    },
    {
      "theory_name": "Institutional Theory",
      "primary_count": 6,
      "secondary_count": 4,
      "total_count": 10,
      "pct_of_corpus": 18.2,
      "paper_ids": ["SCOPUS:85205555"]
    }
  ],
  "dominant_theory": "Cognitive Load Theory",
  "theoretical_gaps": [
    {
      "theory_name": "Behavioural Economics / Prospect Theory",
      "relevance": "Consumer vulnerability in digital markets involves systematic cognitive biases in decision-making under risk and uncertainty — the core domain of prospect theory",
      "implication": "The absence of prospect theory framing means the corpus has not engaged with the loss aversion and framing effects that platform dark patterns explicitly exploit"
    },
    {
      "theory_name": "Intersectionality Theory",
      "relevance": "Vulnerability is compounded across multiple social dimensions simultaneously — age, income, disability, ethnicity — yet no paper frames this through intersectionality",
      "implication": "Additive models of vulnerability factors dominate the corpus; intersectional amplification effects remain theoretically unaddressed"
    }
  ],
  "primary_lens_assessment": {
    "papers_using_it": 30,
    "pct_of_corpus": 54.5,
    "is_appropriate": true,
    "assessment": "Cognitive Load Theory is the dominant framework with 54.5% of papers drawing on it explicitly or implicitly. The theory maps directly onto the mechanisms through which platform design amplifies vulnerability — working memory overload, reduced decision quality, and exploitation of attentional limits. Its appropriateness is confirmed by the convergent findings across design types.",
    "recommended_lens": null
  },
  "theoretical_landscape_summary": "The consumer vulnerability in digital markets literature is theoretically concentrated, with Cognitive Load Theory serving as the dominant framework across the majority of included papers. The field shows a predominantly applied theoretical orientation — most papers use theory to generate hypotheses rather than to extend or challenge theoretical propositions, suggesting limited theoretical contribution from individual studies. Notable absences include behavioural economics frameworks and intersectionality theory, which would provide complementary explanatory power for the mechanisms documented empirically. This theoretical narrowness represents both a limitation of the current evidence base and an opportunity for review-level theoretical contribution."
}
```

---

### Step 4 — Theoretical Anchoring in Scaffold

Add two items to the scaffold after the theory landscape call:

```python
scaffold['theoretical_framework'] = {
    "primary_lens":      "Cognitive Load Theory",
    "supporting_lenses": ["Social Cognitive Theory", "Protection Motivation Theory"],
    "dominant_theory":   "Cognitive Load Theory",
    "theory_coverage":   "54.5% of corpus",
    "theoretical_gaps":  ["Behavioural Economics / Prospect Theory", "Intersectionality Theory"],
    "landscape_summary": "..."
}
```

---

### Step 5 — Theoretical Anchoring in Synthesis Passes

The Reconciler prompt gains one additional requirement. After the normal reconciliation:

```
THEORETICAL INTEGRATION REQUIREMENT:
After reconciling the empirical evidence, add one final paragraph 
addressing this question:

What does the evidence on this theme reveal about the explanatory 
power, limitations, or boundaries of {primary_lens}?

Specifically:
- Does the evidence in this theme support, extend, challenge, or 
  qualify {primary_lens}?
- Are there findings in this theme that {primary_lens} cannot explain?
- What theoretical refinement does the evidence call for?

This paragraph should make a theoretical claim, not just describe 
empirical findings. It should say something about what the theory 
gets right, what it misses, and what should change.
```

This adds approximately 80–120 words to each Reconciler output — one theoretical paragraph per theme. No extra call. The Reconciler already has the context to write this.

---

### Step 6 — Cross-Theme Theoretical Synthesis Call

After all reconciled texts are complete, one dedicated call synthesises the theoretical implications across all themes together.

---

#### Prompt: Cross-Theme Theoretical Synthesis

```
You are writing the theoretical contribution section of a 
systematic literature review.

PRIMARY THEORETICAL LENS: {primary_theoretical_lens}
SUPPORTING FRAMEWORKS: {supporting_lenses}

REVIEW OBJECTIVES: {objectives}
RESEARCH QUESTIONS: {rq_list}

THEORETICAL LANDSCAPE:
{theoretical_landscape_summary}
{theoretical_gaps_formatted}

---

RECONCILED SYNTHESES FOR ALL {theme_count} THEMES:

{all_reconciled_texts_with_theme_names}

Each synthesis above ends with a theoretical paragraph identifying
what the evidence in that theme reveals about {primary_lens}.

---

YOUR TASK — complete all three outputs:

OUTPUT 1: THIRD-ORDER SYNTHESIS (350-450 words)
Read across ALL theme syntheses and identify the overarching 
theoretical insight that TRANSCENDS what any single theme shows.

This is not a summary of what themes found.
This is a new theoretical claim that emerges only from reading 
across all themes together.

Ask yourself: what pattern across ALL themes, when considered 
simultaneously, reveals something about {primary_lens} that 
no individual theme captures? What tension between themes 
exposes a theoretical blind spot? What do the collective findings 
suggest about when, why, and for whom {primary_lens} applies?

Write this as continuous academic prose making a specific 
theoretical argument. Use hedging appropriate to evidence grades.

OUTPUT 2: THEORETICAL PROPOSITIONS (3-5 propositions)
Based on the synthesised evidence, generate 3-5 formal theoretical 
propositions suitable for inclusion in a top-tier review article.

Propositions are falsifiable theoretical claims derived from the 
evidence synthesis. They go beyond what individual papers found 
and represent the review's theoretical contribution.

Format each as:
P[n]: [Statement of theoretical relationship]
Rationale: [One sentence grounding in synthesised evidence]
Evidence Grade: [Established|Emerging|Contested|Insufficient]

OUTPUT 3: REVISED THEORETICAL FRAMEWORK NARRATIVE (200-250 words)
How should {primary_lens} be refined, extended, or boundary-
conditioned based on the evidence in this review?
What modifications to the theory does this synthesis call for?
What boundary conditions have been established by the evidence?

Return ONLY valid JSON. No preamble. No markdown fences.

{
  "third_order_synthesis": "350-450 word theoretical argument",
  "propositions": [
    {
      "number": 1,
      "statement": "P1: formal theoretical proposition",
      "rationale": "one sentence grounding in evidence",
      "evidence_grade": "Established|Emerging|Contested|Insufficient",
      "themes_supporting": ["theme name 1", "theme name 2"]
    }
  ],
  "revised_framework_narrative": "200-250 words on how primary theory should be refined"
}
```

**Expected Output:**

```json
{
  "third_order_synthesis": "Reading across all six synthesised themes simultaneously reveals a pattern that no individual theme makes explicit: consumer vulnerability in digital markets is not a static trait that individuals carry into transactions but a dynamically constructed state that platform environments actively produce and maintain through layered, mutually reinforcing mechanisms. Cognitive Load Theory, as the dominant explanatory framework in this corpus, captures the cognitive dimension of this process accurately — platform complexity overwhelms working memory, reduces decision quality, and increases susceptibility. What the cross-theme reading exposes, however, is that Cognitive Load Theory treats cognitive capacity as the primary variable when the synthesised evidence suggests that platform design is the primary variable, with cognitive load as the mediating mechanism rather than the explanatory construct.\n\nThe convergence across Platform Design (Established) and Digital Literacy (Emerging) themes is theoretically revealing: digital literacy interventions show modest and often transient effects precisely because they attempt to build cognitive capacity in an environment designed to exhaust it. This finding pattern implies a fundamental boundary condition on Cognitive Load Theory applications in adversarial environments — the theory assumes cognitive resources are being taxed by task complexity, not by intentional design choices aimed at exhaustion. The distinction matters for intervention design: capacity-building approaches (literacy training) will always be outpaced by capacity-exhaustion approaches (dark pattern intensification) unless the adversarial design environment is itself constrained.\n\nThe Regulatory Frameworks theme, though Insufficient in evidence, becomes theoretically significant at the cross-theme level: the Australian subgroup finding in Baker et al. (2019) — where mandatory disclosure reduced the platform design effect — suggests that regulatory constraint of the adversarial environment produces larger vulnerability reductions than any individual-level intervention documented in this corpus. This cross-theme pattern constitutes a theoretical claim that cannot be derived from any single theme: regulatory environment functions as a boundary condition on Cognitive Load Theory's applicability to vulnerability in digital markets.",

  "propositions": [
    {
      "number": 1,
      "statement": "P1: In adversarial digital environments, the relationship between cognitive load and consumer vulnerability is moderated by platform design intent, such that vulnerability outcomes are more strongly predicted by the degree of intentional complexity than by individual cognitive capacity.",
      "rationale": "Platform Design theme (Established) consistently shows larger effects than Digital Literacy theme (Emerging) and the cross-theme pattern suggests design intent is the primary driver",
      "evidence_grade": "Emerging",
      "themes_supporting": ["Platform Design and Exploitation Mechanisms", "Digital Literacy as Vulnerability Mediator"]
    },
    {
      "number": 2,
      "statement": "P2: Digital literacy interventions demonstrate diminishing returns on vulnerability reduction as platform design complexity increases, suggesting a capacity-exhaustion ceiling effect not accounted for in standard Cognitive Load Theory formulations.",
      "rationale": "Intervention Effectiveness theme shows short-lived literacy training effects alongside Established platform design effects",
      "evidence_grade": "Emerging",
      "themes_supporting": ["Digital Literacy as Vulnerability Mediator", "Intervention Effectiveness and Design"]
    },
    {
      "number": 3,
      "statement": "P3: Regulatory constraint of digital market design features produces larger and more durable reductions in consumer vulnerability than individual-level cognitive or literacy interventions, establishing regulatory environment as a first-order boundary condition on digital vulnerability mechanisms.",
      "rationale": "Cross-national comparison in Baker et al. (2019) and regulatory theme suggest this but direct comparative evidence is insufficient",
      "evidence_grade": "Insufficient",
      "themes_supporting": ["Regulatory Frameworks and Enforcement", "Platform Design and Exploitation Mechanisms"]
    }
  ],

  "revised_framework_narrative": "The evidence synthesised in this review suggests Cognitive Load Theory requires two substantive extensions to adequately explain consumer vulnerability in digital market contexts. First, the theory must incorporate a distinction between incidental cognitive load (arising from task complexity) and adversarial cognitive load (arising from design choices intended to impair decision quality) — the mechanisms and appropriate responses differ fundamentally. Incidental load is addressed through better design or skill building; adversarial load requires constraint of the designing party. Second, the theory's implicit assumption of a static cognitive environment must be replaced with a dynamic adversarial environment model in which platform operators continuously update exploitation mechanisms in response to consumer adaptation. The evidence shows that individual-level vulnerability outcomes are more responsive to regulatory environment changes than to individual skill development, suggesting that the unit of intervention implied by Cognitive Load Theory — the individual consumer — is misspecified in adversarial digital market contexts. The appropriate unit of intervention is the design environment itself."
}
```

---

---

## Part 2 — Conceptual Model / Research Framework Diagram

### The Core Idea

After synthesis you know what constructs exist in the literature, how they relate to each other, and how strong the evidence is for each relationship. A conceptual model diagram makes all of this visible in a single figure. In top-tier journals this is often the most reproduced figure from the paper.

It is not a flowchart of the SLR process. It is a theoretical model of the phenomenon being reviewed — showing antecedents, mediators, moderators, and outcomes with evidence-graded directional arrows.

---

### Where It Enters the Pipeline

```
Cross-theme synthesis complete (theoretical propositions exist)
              ↓
CONCEPTUAL MODEL SPECIFICATION CALL
  Reads: reconciled themes + theoretical propositions + 
         extraction data (what predicts what)
  Produces: nodes, edges, moderators, evidence grades
              ↓
DIAGRAM RENDERER (matplotlib / graphviz)
  Reads: model specification JSON
  Produces: structured diagram PNG
              ↓
Stored as GraphFile (phase=2)
Embedded in Discussion section of DOCX
```

---

### Step 1 — Conceptual Model Specification Call

---

#### Prompt: Conceptual Model Specification

```
You are specifying a conceptual model for a systematic literature 
review. The model will be rendered as a diagram and published in 
the review article.

REVIEW TOPIC: {primary_topic}
PRIMARY THEORETICAL LENS: {primary_theoretical_lens}

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
- Every relationship must be supported by evidence in the synthesis
- Evidence grade applies to each RELATIONSHIP, not just constructs
- Direction: positive = same direction, negative = opposite direction,
  mixed = evidence is divided, unknown = direction unclear
- Moderators sit on arrows, not as standalone nodes
- Keep the model parsimonious — include only constructs with Emerging 
  or Established evidence unless an Insufficient finding is 
  theoretically critical
- The model should be readable as a figure — 8-15 nodes maximum

Return ONLY valid JSON. No preamble. No markdown fences.

{
  "model_title": "short title for the conceptual model figure",
  "main_outcome": {
    "id": "node_id",
    "label": "construct name as it appears in the model",
    "definition": "one sentence defining this construct",
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
      "key_papers": ["Baker et al. (2019)", "Smith & Jones (2021)"],
      "label": "short label for the arrow, e.g. 'amplifies' or 'reduces'"
    }
  ],
  "moderating_relationships": [
    {
      "moderator_id": "node_id of moderator",
      "on_relationship": {
        "from": "source node_id",
        "to": "target node_id"
      },
      "direction": "strengthens | weakens | mixed",
      "evidence_grade": "Established|Emerging|Contested|Insufficient",
      "key_papers": ["Chen et al. (2022)"]
    }
  ],
  "model_narrative": "3-4 sentences explaining how to read the model 
                      and what its key theoretical claim is. This 
                      becomes the figure caption."
}
```

**Expected Output:**

```json
{
  "model_title": "Conceptual Model of Consumer Vulnerability in Digital Markets",
  "main_outcome": {
    "id": "consumer_vulnerability",
    "label": "Consumer Vulnerability",
    "definition": "The degree to which consumers are susceptible to harm from digital marketplace exploitation due to cognitive, structural, or individual factors",
    "evidence_grade": "Established"
  },
  "antecedents": [
    {
      "id": "platform_design",
      "label": "Platform Design Complexity",
      "definition": "The degree to which digital marketplace interfaces incorporate deceptive, complexity-maximising, or cognitively exploitative design elements",
      "category": "environmental",
      "evidence_grade": "Established"
    },
    {
      "id": "digital_literacy",
      "label": "Digital Literacy",
      "definition": "Individual competency in understanding, navigating, and critically evaluating digital marketplace environments",
      "category": "individual",
      "evidence_grade": "Emerging"
    },
    {
      "id": "age_cognitive",
      "label": "Age-Related Cognitive Capacity",
      "definition": "Age-associated differences in working memory capacity, processing speed, and susceptibility to cognitive overload in complex digital environments",
      "category": "individual",
      "evidence_grade": "Emerging"
    }
  ],
  "mediators": [
    {
      "id": "cognitive_load",
      "label": "Cognitive Load",
      "definition": "The degree of mental effort imposed on the consumer's working memory during digital marketplace interactions",
      "evidence_grade": "Emerging"
    },
    {
      "id": "protection_awareness",
      "label": "Consumer Protection Awareness",
      "definition": "Knowledge of consumer rights, redress mechanisms, and recognition of exploitative platform practices",
      "evidence_grade": "Emerging"
    }
  ],
  "moderators": [
    {
      "id": "regulatory_environment",
      "label": "Regulatory Environment",
      "definition": "The strength and enforcement of consumer protection regulation in the jurisdiction where the digital transaction occurs",
      "evidence_grade": "Insufficient"
    }
  ],
  "relationships": [
    {
      "from": "platform_design",
      "to": "cognitive_load",
      "relationship_type": "direct",
      "direction": "positive",
      "evidence_grade": "Established",
      "key_papers": ["Baker et al. (2019)", "Smith & Jones (2021)", "Chen et al. (2022)"],
      "label": "increases"
    },
    {
      "from": "cognitive_load",
      "to": "consumer_vulnerability",
      "relationship_type": "direct",
      "direction": "positive",
      "evidence_grade": "Emerging",
      "key_papers": ["Baker et al. (2019)", "Williams et al. (2020)"],
      "label": "amplifies"
    },
    {
      "from": "platform_design",
      "to": "consumer_vulnerability",
      "relationship_type": "direct",
      "direction": "positive",
      "evidence_grade": "Established",
      "key_papers": ["Baker et al. (2019)", "Smith & Jones (2021)"],
      "label": "directly increases"
    },
    {
      "from": "digital_literacy",
      "to": "cognitive_load",
      "relationship_type": "direct",
      "direction": "negative",
      "evidence_grade": "Emerging",
      "key_papers": ["Chen et al. (2022)", "Park & Kim (2021)"],
      "label": "reduces"
    },
    {
      "from": "digital_literacy",
      "to": "consumer_vulnerability",
      "relationship_type": "mediated",
      "direction": "negative",
      "evidence_grade": "Emerging",
      "key_papers": ["Baker et al. (2019)", "Williams et al. (2020)"],
      "label": "reduces"
    },
    {
      "from": "age_cognitive",
      "to": "cognitive_load",
      "relationship_type": "direct",
      "direction": "positive",
      "evidence_grade": "Emerging",
      "key_papers": ["Johnson et al. (2020)"],
      "label": "increases susceptibility"
    },
    {
      "from": "protection_awareness",
      "to": "consumer_vulnerability",
      "relationship_type": "direct",
      "direction": "negative",
      "evidence_grade": "Emerging",
      "key_papers": ["Smith & Jones (2021)"],
      "label": "reduces"
    }
  ],
  "moderating_relationships": [
    {
      "moderator_id": "regulatory_environment",
      "on_relationship": {
        "from": "platform_design",
        "to": "consumer_vulnerability"
      },
      "direction": "weakens",
      "evidence_grade": "Insufficient",
      "key_papers": ["Baker et al. (2019) — Australian subgroup"]
    }
  ],
  "model_narrative": "The conceptual model positions Platform Design Complexity as the primary environmental antecedent of Consumer Vulnerability, operating both directly and through the mediating mechanism of Cognitive Load — consistent with an adversarial application of Cognitive Load Theory. Individual-level factors (Digital Literacy, Age-Related Cognitive Capacity) function as antecedents that amplify or attenuate the cognitive load pathway, explaining why vulnerability is not uniformly distributed across the population. Regulatory Environment is positioned as a moderator of the platform design-vulnerability relationship, weakening the effect under conditions of mandatory disclosure enforcement, though evidence for this boundary condition remains insufficient and constitutes the primary gap for future research."
}
```

---

### Step 2 — Diagram Renderer

The JSON specification above is passed to a matplotlib/graphviz renderer that draws the actual figure.

**Visual conventions used consistently:**

```
NODE SHAPES:
  Rectangle     → antecedents
  Oval          → mediators
  Diamond       → moderators
  Rectangle     → main outcome (double border)

NODE COLOURS (by evidence grade):
  Deep blue     → Established
  Medium blue   → Emerging
  Orange        → Contested
  Light grey    → Insufficient

ARROW STYLES:
  Solid line    → Established relationship
  Dashed line   → Emerging relationship
  Dotted line   → Contested or Insufficient

ARROW COLOURS:
  Dark grey     → positive direction
  Red           → negative direction
  Purple        → mixed direction

MODERATOR DISPLAY:
  Arrow enters from moderator node
  Points to the midpoint of the relationship arrow it moderates
  Labelled with direction (strengthens / weakens)

EVIDENCE GRADE LEGEND:
  Bottom right corner of the figure
  Colour swatches with grade labels
```

The renderer produces a 300 DPI PNG stored as a GraphFile record with `phase=2`.

---

### Step 3 — What the Figure Looks Like in the Paper

The figure appears in two places:

**In Results: Section 3.5 (Synthesis)** — a preliminary version or reference to it
**In Discussion: Section 4 (as the opening figure)** — the full conceptual model

The figure caption uses `model_narrative` from the JSON output:

```
Figure 3. Conceptual Model of Consumer Vulnerability in Digital Markets.
The model positions Platform Design Complexity as the primary 
environmental antecedent operating through Cognitive Load (Cognitive 
Load Theory, Sweller 1988) and directly on Consumer Vulnerability. 
Individual factors (Digital Literacy, Age-Related Cognitive Capacity) 
moderate the cognitive pathway. Regulatory Environment moderates the 
platform-vulnerability relationship (preliminary evidence). Arrow style 
indicates evidence strength (solid=Established, dashed=Emerging, 
dotted=Insufficient). See Table 4 for supporting citations per relationship.
```

---

### Step 4 — Propositions Table in the Paper

The theoretical propositions from the cross-theme call are rendered as a formatted table in the Discussion section:

```
Table X. Theoretical Propositions Derived from Synthesis

P1: In adversarial digital environments, the relationship between 
    cognitive load and consumer vulnerability is moderated by platform 
    design intent...
    Evidence: Emerging | Themes: Platform Design, Digital Literacy

P2: Digital literacy interventions demonstrate diminishing returns...
    Evidence: Emerging | Themes: Digital Literacy, Interventions

P3: Regulatory constraint produces larger vulnerability reductions...
    Evidence: Insufficient | Themes: Regulatory, Platform Design
```

---

### How Both Features Connect

```
INTAKE FORM: user specifies theoretical lens (optional)
      ↓
EXTRACTION: each paper tagged with theories used
      ↓
THEORY LANDSCAPE CALL: frequency map, gaps, lens validation
      ↓
EVIDENCE MATRIX CALL: themes identified (unchanged)
      ↓
RECONCILER PASSES: each theme ends with theoretical paragraph
      ↓
CROSS-THEME THEORETICAL SYNTHESIS: 
  → third-order synthesis
  → 3-5 theoretical propositions
  → revised framework narrative
      ↓
CONCEPTUAL MODEL SPECIFICATION CALL:
  → nodes, edges, moderators, evidence grades
      ↓
DIAGRAM RENDERER:
  → conceptual model PNG (GraphFile phase=2)
      ↓
SCAFFOLD ADDITIONS:
  scaffold['theoretical_framework'] = {...}
  scaffold['propositions'] = [...]
      ↓
WRITING CALLS:
  Discussion receives: propositions + model narrative
  Discussion writes: theoretical contributions section
  Figure embedded: conceptual model PNG
```

---


## TCCM Framework — How and Full Prompts

---

### What TCCM Is

TCCM stands for **Theory, Characteristics, Context, Methods**. It was formalised by Paul et al. (2021) in the *International Business Review* as a structured way to organise what a systematic review finds about how a field has studied a topic — not just what it found, but how it went about finding it.

It answers four questions systematically:

```
THEORY:          What theoretical lenses has the field used?
CHARACTERISTICS: What are the characteristics of the studies themselves?
CONTEXT:         In what settings, populations, and geographies was this studied?
METHODS:         What research designs and analytical methods were used?
```

Top journals — JAMS, JIBS, IMR, JBR, and increasingly JM and JMR — now routinely require a TCCM table or structured TCCM analysis. Reviewers at these journals will explicitly look for it in any SLR submission.

The power of TCCM is that it makes the **gaps in the literature immediately visible**. Where the cells are empty or thin is exactly where future research should go.

---

### Where TCCM Enters the Pipeline

```
EXTRACTION CALL (already running)
  → add TCCM-specific fields to each paper's extraction
        ↓
TCCM AGGREGATION CALL (new — after all extractions complete)
  → aggregate TCCM data across all 55 papers
  → identify what is present, dominant, and absent in each dimension
        ↓
TCCM TABLE BUILDER (pure computation — no AI)
  → build the formatted TCCM table from aggregated data
        ↓
TCCM NARRATIVE CALL (new — one writing call)
  → write the TCCM analysis section in prose
        ↓
SCAFFOLD ADDITIONS
  → scaffold['tccm_summary'] for writing calls to reference
        ↓
DOCX ASSEMBLY
  → TCCM table embedded in Results: Study Characteristics
  → TCCM narrative in Results section
```

---

### Step 1 — Extraction Call Addition

The merged extraction prompt gains a fourth top-level key `tccm` alongside `summary`, `extraction`, and `quality`.

---

#### Addition to the Extraction Prompt

Add this to the existing extraction prompt after the quality schema:

```
  "tccm": {

    "theories": [
      {
        "theory_name": "exact name of theory used or referenced",
        "theory_abbreviation": "e.g. CLT, SCT, TAM — or null",
        "usage_type": "primary | secondary | implicit",
        "usage_description": "one sentence — does this paper test, 
                              extend, challenge, or apply this theory?"
      }
    ],

    "characteristics": {
      "unit_of_analysis": "individual | dyad | organisation | 
                            market | platform | policy | other",
      "sample_type": "student | consumer panel | general population | 
                       clinical | organisational | secondary data | other",
      "longitudinal": true or false,
      "experimental": true or false,
      "sample_size_category": "small (<100) | medium (100-499) | 
                                large (500-1999) | very large (2000+) | 
                                not applicable",
      "publication_type": "journal article | conference paper | 
                            book chapter | working paper",
      "journal_field": "marketing | consumer behaviour | information systems | 
                         psychology | economics | policy | interdisciplinary | other"
    },

    "context": {
      "geographic_scope": "single country | multi-country | global",
      "country_or_region": "country name or region — be specific",
      "economic_context": "developed | developing | emerging | mixed",
      "digital_platform_type": "e-commerce | social media | 
                                  financial services | sharing economy | 
                                  search engine | general digital | 
                                  not specified",
      "population_group": "general consumers | elderly | low income | 
                            young adults | disability | gender-specific | 
                            cross-group | not specified",
      "temporal_context": "pre-2015 | 2015-2019 | 2020-2024 | 
                            longitudinal spanning periods"
    },

    "methods": {
      "research_paradigm": "quantitative | qualitative | mixed",
      "data_collection": "survey | experiment | interview | 
                           focus group | observation | secondary data | 
                           content analysis | multiple",
      "primary_analysis": "regression | SEM | content analysis | 
                            thematic analysis | grounded theory | 
                            case study analysis | meta-analysis | 
                            descriptive | other",
      "software_used": "SPSS | R | Mplus | AMOS | NVivo | ATLAS.ti | 
                         Stata | Python | not reported | other",
      "validation_approach": "pre-registered | piloted | 
                               multi-sample replication | 
                               single sample | not reported"
    }
  }
```

---

### Step 2 — TCCM Aggregation Call

After all 55 extractions complete, one deepseek call aggregates across all TCCM fields to identify patterns, dominances, and gaps.

---

#### Prompt: TCCM Aggregation and Gap Analysis

```
You are conducting a TCCM (Theory, Characteristics, Context, Methods) 
analysis for a systematic literature review following the framework 
proposed by Paul et al. (2021).

REVIEW TOPIC: {primary_topic}
TOTAL PAPERS: {total_papers}
DATE RANGE: {date_range}

---

TCCM DATA FROM ALL {total_papers} INCLUDED PAPERS:
{all_tccm_json}

This JSON contains for each paper: scopus_id, short_ref, year,
and the full tccm object with theories, characteristics, context, 
and methods fields.

---

YOUR TASK — analyse each TCCM dimension systematically.

Produce a comprehensive TCCM analysis covering all four dimensions.
For each dimension identify:
  1. What is DOMINANT — the most common approach, theory, or context
  2. What is PRESENT but not dominant — minority approaches
  3. What is ABSENT — important theories, contexts, or methods not used
  4. What the pattern MEANS for the field — the interpretive insight

The "absent" analysis is as important as the "present" analysis.
Gaps in TCCM are where future research should go.

Return ONLY valid JSON. No preamble. No markdown fences.

{
  "theory_dimension": {
    "theories_used": [
      {
        "theory_name": "full theory name",
        "abbreviation": "e.g. CLT",
        "primary_count": integer,
        "secondary_count": integer,
        "total_count": integer,
        "pct_of_corpus": float,
        "dominance": "dominant | present | marginal"
      }
    ],
    "theoretical_diversity_score": "low | medium | high",
    "theoretical_diversity_rationale": "one sentence",
    "dominant_theory": "name of most-used primary theory",
    "absent_theories": [
      {
        "theory_name": "name of absent theory",
        "why_relevant": "why this theory should be present in this literature",
        "implication": "what its absence means"
      }
    ],
    "theory_usage_pattern": "one of: applying | testing | extending | 
                              challenging | building — what is the 
                              dominant relationship between papers 
                              and their theoretical frameworks?",
    "theory_narrative": "3-4 sentences interpreting the theoretical 
                          dimension — what does the pattern tell us 
                          about the field's theoretical maturity?"
  },

  "characteristics_dimension": {
    "unit_of_analysis": {
      "distribution": {"individual": integer, "organisation": integer},
      "dominant": "most common unit",
      "absent": ["units not studied"],
      "narrative": "2 sentences"
    },
    "sample_types": {
      "distribution": {"consumer panel": integer, "general population": integer},
      "dominant": "most common sample type",
      "concerns": "any methodological concern about sample dominance"
    },
    "longitudinal_count": integer,
    "longitudinal_pct": float,
    "experimental_count": integer,
    "experimental_pct": float,
    "sample_size_distribution": {
      "small": integer,
      "medium": integer,
      "large": integer,
      "very_large": integer
    },
    "journal_field_distribution": {
      "marketing": integer,
      "consumer_behaviour": integer,
      "information_systems": integer,
      "psychology": integer,
      "other": integer
    },
    "characteristics_narrative": "3-4 sentences interpreting study 
                                   characteristics — what kind of 
                                   studies dominate and what 
                                   methodological biases exist?"
  },

  "context_dimension": {
    "geographic_distribution": [
      {
        "country_or_region": "name",
        "count": integer,
        "pct": float
      }
    ],
    "geographic_concentration": "low | medium | high",
    "western_dominance_pct": float,
    "underrepresented_regions": ["regions with < 5% representation"],
    "economic_context_distribution": {
      "developed": integer,
      "developing": integer,
      "emerging": integer,
      "mixed": integer
    },
    "platform_type_distribution": {
      "e-commerce": integer,
      "financial_services": integer,
      "social_media": integer,
      "other": integer
    },
    "population_group_distribution": {
      "general_consumers": integer,
      "elderly": integer,
      "low_income": integer,
      "young_adults": integer,
      "other": integer
    },
    "underrepresented_populations": ["population groups not studied"],
    "temporal_distribution": {
      "pre_2015": integer,
      "2015_2019": integer,
      "2020_2024": integer
    },
    "context_narrative": "3-4 sentences interpreting the context 
                           dimension — where has this been studied, 
                           where has it not, and what does that mean?"
  },

  "methods_dimension": {
    "paradigm_distribution": {
      "quantitative": integer,
      "qualitative": integer,
      "mixed": integer
    },
    "quantitative_pct": float,
    "data_collection_distribution": {
      "survey": integer,
      "experiment": integer,
      "interview": integer,
      "secondary_data": integer,
      "other": integer
    },
    "analysis_distribution": {
      "regression": integer,
      "SEM": integer,
      "thematic_analysis": integer,
      "content_analysis": integer,
      "other": integer
    },
    "pre_registered_count": integer,
    "pre_registered_pct": float,
    "multi_sample_replication_count": integer,
    "absent_methods": [
      {
        "method": "method name",
        "why_relevant": "why this method should be used in this literature",
        "implication": "what its absence means for evidence quality"
      }
    ],
    "methods_narrative": "3-4 sentences interpreting the methods 
                           dimension — what does the methodological 
                           profile tell us about evidence quality 
                           and maturity?"
  },

  "tccm_gaps_synthesis": "4-5 sentences synthesising the most important 
                           gaps across ALL four TCCM dimensions — this 
                           becomes the basis for the future research agenda. 
                           Be specific about what is missing and why it matters.",

  "future_research_from_tccm": [
    {
      "gap_dimension": "Theory | Characteristics | Context | Methods",
      "gap_description": "specific gap identified",
      "research_direction": "specific research question or approach that would address this gap",
      "priority": "high | medium | low",
      "rationale": "one sentence explaining why this gap is consequential"
    }
  ]
}
```

---

#### Expected Output (abbreviated)

```json
{
  "theory_dimension": {
    "theories_used": [
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
      },
      {
        "theory_name": "Protection Motivation Theory",
        "abbreviation": "PMT",
        "primary_count": 9,
        "secondary_count": 5,
        "total_count": 14,
        "pct_of_corpus": 25.5,
        "dominance": "present"
      },
      {
        "theory_name": "Technology Acceptance Model",
        "abbreviation": "TAM",
        "primary_count": 7,
        "secondary_count": 11,
        "total_count": 18,
        "pct_of_corpus": 32.7,
        "dominance": "present"
      },
      {
        "theory_name": "Institutional Theory",
        "abbreviation": "IT",
        "primary_count": 6,
        "secondary_count": 4,
        "total_count": 10,
        "pct_of_corpus": 18.2,
        "dominance": "marginal"
      }
    ],
    "theoretical_diversity_score": "medium",
    "theoretical_diversity_rationale": "Five theories identified but CLT dominates at 54.5% with others playing secondary roles, indicating moderate concentration",
    "dominant_theory": "Cognitive Load Theory",
    "absent_theories": [
      {
        "theory_name": "Prospect Theory / Behavioural Economics",
        "why_relevant": "Platform dark patterns systematically exploit loss aversion, framing effects, and reference point manipulation — the core mechanisms of prospect theory — yet no included paper frames vulnerability through this lens",
        "implication": "The corpus has documented what dark patterns do to consumers without theorising why they work at the psychological level, leaving the mechanism explanation incomplete"
      },
      {
        "theory_name": "Intersectionality Theory",
        "why_relevant": "Multiple vulnerability dimensions (age, income, disability, gender) co-occur in consumers and compound vulnerability multiplicatively, yet all papers treat these as additive independent variables",
        "implication": "Current models systematically underestimate vulnerability in consumers with multiple co-occurring risk factors"
      },
      {
        "theory_name": "Agency Theory",
        "why_relevant": "Platform-consumer relationships involve fundamental information asymmetries and principal-agent problems that agency theory was developed to explain",
        "implication": "The structural power dynamics enabling consumer exploitation remain theoretically unaddressed"
      }
    ],
    "theory_usage_pattern": "applying",
    "theory_narrative": "The consumer vulnerability in digital markets literature exhibits a predominantly applied theoretical orientation — 87% of papers use existing theories to generate and test hypotheses rather than to extend or challenge theoretical propositions. Cognitive Load Theory dominates at 54.5% of the corpus, reflecting the field's cognitive-individual focus, while structural and institutional perspectives remain marginal. The notable absence of behavioural economics frameworks is theoretically significant given that platform dark patterns explicitly exploit the cognitive biases Kahneman and Tversky documented. The field's theoretical concentration on the individual cognitive level, rather than the structural level, may explain why intervention research consistently shows individual-level solutions to be less effective than environmental regulation."
  },

  "characteristics_dimension": {
    "unit_of_analysis": {
      "distribution": {
        "individual": 48,
        "dyad": 2,
        "organisation": 1,
        "market": 3,
        "platform": 1
      },
      "dominant": "individual",
      "absent": ["policy system", "regulatory body", "cross-platform comparison"],
      "narrative": "Individual consumers constitute the unit of analysis in 87% of included studies, reflecting the field's psychological orientation. Market-level and platform-level analyses are severely underrepresented, meaning the field understands vulnerability as an individual state while the structural conditions producing it remain largely unstudied at the appropriate level of analysis."
    },
    "sample_types": {
      "distribution": {
        "consumer_panel": 24,
        "general_population": 14,
        "student": 8,
        "secondary_data": 5,
        "other": 4
      },
      "dominant": "consumer panel",
      "concerns": "Consumer panel samples (44%) may over-represent digitally active, higher-literacy consumers and systematically underestimate vulnerability in the most at-risk populations who are less likely to participate in online panels"
    },
    "longitudinal_count": 4,
    "longitudinal_pct": 7.3,
    "experimental_count": 11,
    "experimental_pct": 20.0,
    "sample_size_distribution": {
      "small": 8,
      "medium": 14,
      "large": 21,
      "very_large": 12
    },
    "journal_field_distribution": {
      "marketing": 18,
      "consumer_behaviour": 14,
      "information_systems": 10,
      "psychology": 8,
      "other": 5
    },
    "characteristics_narrative": "The literature is dominated by cross-sectional survey studies of individual consumers using professional panel samples, with only 7.3% of studies employing longitudinal designs and 20% using experimental methods. This methodological profile severely limits causal inference — the field has documented associations extensively but established causal mechanisms in only a fraction of the corpus. The low rate of pre-registration (12.7%) and multi-sample replication (18.2%) raises concerns about publication bias and the robustness of reported effect sizes."
  },

  "context_dimension": {
    "geographic_distribution": [
      {"country_or_region": "United Kingdom", "count": 12, "pct": 21.8},
      {"country_or_region": "United States", "count": 10, "pct": 18.2},
      {"country_or_region": "Australia", "count": 6, "pct": 10.9},
      {"country_or_region": "Germany", "count": 4, "pct": 7.3},
      {"country_or_region": "China", "count": 3, "pct": 5.5},
      {"country_or_region": "Multi-country", "count": 8, "pct": 14.5},
      {"country_or_region": "Other", "count": 12, "pct": 21.8}
    ],
    "geographic_concentration": "high",
    "western_dominance_pct": 72.7,
    "underrepresented_regions": [
      "Sub-Saharan Africa",
      "South and Southeast Asia",
      "Latin America",
      "Middle East and North Africa"
    ],
    "economic_context_distribution": {
      "developed": 42,
      "developing": 4,
      "emerging": 6,
      "mixed": 3
    },
    "platform_type_distribution": {
      "e_commerce": 28,
      "financial_services": 12,
      "social_media": 8,
      "sharing_economy": 3,
      "not_specified": 4
    },
    "population_group_distribution": {
      "general_consumers": 28,
      "elderly": 12,
      "low_income": 7,
      "young_adults": 5,
      "disability": 1,
      "cross_group": 2
    },
    "underrepresented_populations": [
      "Consumers with cognitive disabilities",
      "Non-English speaking minority consumers",
      "Rural and digitally excluded consumers",
      "Consumers in developing market digital contexts"
    ],
    "temporal_distribution": {
      "pre_2015": 7,
      "2015_2019": 24,
      "2020_2024": 24
    },
    "context_narrative": "The literature is overwhelmingly concentrated in high-income Anglophone markets, with the UK, USA, and Australia together accounting for 50.9% of single-country studies. Developing and emerging market contexts represent only 18.2% of the corpus despite the rapid growth of digital commerce in these regions and the potentially greater vulnerability of consumers operating with fewer regulatory protections and lower baseline digital literacy. E-commerce platforms dominate the contextual focus (50.9%), leaving financial services (21.8%), social media (14.5%), and emerging platform types substantially underexplored. Elderly consumers are the most studied vulnerable subgroup (21.8%) while consumers with cognitive disabilities appear in only one study, representing a severe contextual gap given documented differential vulnerability."
  },

  "methods_dimension": {
    "paradigm_distribution": {
      "quantitative": 33,
      "qualitative": 14,
      "mixed": 8
    },
    "quantitative_pct": 60.0,
    "data_collection_distribution": {
      "survey": 28,
      "experiment": 11,
      "interview": 9,
      "focus_group": 4,
      "secondary_data": 3
    },
    "analysis_distribution": {
      "regression": 14,
      "SEM": 12,
      "thematic_analysis": 9,
      "content_analysis": 5,
      "grounded_theory": 3,
      "other": 12
    },
    "pre_registered_count": 7,
    "pre_registered_pct": 12.7,
    "multi_sample_replication_count": 10,
    "multi_sample_replication_pct": 18.2,
    "absent_methods": [
      {
        "method": "Digital trace data / behavioural data analysis",
        "why_relevant": "Platform vulnerability operates through actual behavioural sequences that are measurable via clickstream and transaction data — self-report surveys cannot capture the moment-by-moment cognitive experience",
        "implication": "The evidence base rests almost entirely on retrospective self-report, introducing substantial recall and social desirability biases that may systematically underestimate vulnerability frequency and overestimate coping effectiveness"
      },
      {
        "method": "Audit methodology / platform scraping",
        "why_relevant": "Systematically documenting dark pattern prevalence and intensity across platforms would provide objective environmental measures, yet all studies rely on consumer-reported platform exposure",
        "implication": "The field lacks objective measurement of the independent variable it studies — platform design complexity is never independently verified"
      },
      {
        "method": "Longitudinal panel with repeated measures",
        "why_relevant": "Vulnerability effects may accumulate over time or diminish as consumers adapt — only longitudinal designs can distinguish transient from chronic vulnerability",
        "implication": "The 7.3% longitudinal rate means the field cannot distinguish whether vulnerability is a persistent state or an episodic response"
      }
    ],
    "methods_narrative": "The methodological profile is predominantly quantitative (60%) and survey-based (50.9%), with experimental evidence present but limited to 20% of the corpus. The near-total absence of digital trace data and platform audit methodologies is the most consequential methodological gap — the field measures vulnerability through consumer self-report while the platform-side design features driving vulnerability are never independently documented. Pre-registration rates are low (12.7%) and multi-sample replication occurs in only 18.2% of studies, raising systematic concerns about the robustness of reported effect sizes and the potential for publication bias in the quantitative literature."
  },

  "tccm_gaps_synthesis": "Across all four TCCM dimensions, the consumer vulnerability in digital markets literature exhibits a consistent pattern of individual-level focus at the expense of structural and environmental analysis. Theoretically, the field applies cognitive frameworks without engaging behavioural economics or structural theories that would better explain why platforms design for vulnerability exploitation. Contextually, 72.7% of evidence comes from developed Western markets, leaving the largest and fastest-growing digital consumer populations — in Asia, Africa, and Latin America — almost entirely unstudied. Methodologically, the absence of digital trace data and platform audit methodologies means the field has never independently verified the platform-side independent variable it studies; all evidence rests on consumer self-report of experiences that are demonstrably subject to recall and social desirability biases. These gaps collectively point to a field that understands the individual cognitive experience of vulnerability well but understands the structural, environmental, and cross-cultural determinants poorly.",

  "future_research_from_tccm": [
    {
      "gap_dimension": "Theory",
      "gap_description": "Behavioural economics frameworks (Prospect Theory, dual-process theory) are entirely absent despite being theoretically central to explaining why dark patterns work",
      "research_direction": "Studies applying Prospect Theory to model consumer responses to specific dark pattern types would provide mechanism-level explanations that CLT-based studies cannot offer",
      "priority": "high",
      "rationale": "Understanding the psychological mechanism is prerequisite to designing effective counter-interventions"
    },
    {
      "gap_dimension": "Context",
      "gap_description": "Developing and emerging market digital commerce contexts are severely underrepresented at 18.2% of corpus despite rapid market growth and weaker regulatory protection",
      "research_direction": "Cross-national comparative studies explicitly designed to test whether vulnerability mechanisms documented in Anglophone markets generalise to different regulatory and cultural contexts",
      "priority": "high",
      "rationale": "Policy recommendations derived from Western samples cannot be responsibly applied to markets with fundamentally different regulatory environments and consumer baseline characteristics"
    },
    {
      "gap_dimension": "Methods",
      "gap_description": "Digital trace data and platform audit methodologies are entirely absent, meaning the platform-side independent variable is never independently measured",
      "research_direction": "Combining platform dark pattern audits (objective environmental measure) with consumer outcome data (behavioural and self-report) in matched designs",
      "priority": "high",
      "rationale": "Without independent measurement of platform design intensity, causal claims about platform design as the driver of vulnerability cannot be established"
    },
    {
      "gap_dimension": "Characteristics",
      "gap_description": "Only 7.3% of studies use longitudinal designs, making it impossible to distinguish transient from chronic vulnerability or to track adaptation and learning effects",
      "research_direction": "Longitudinal panel studies tracking the same consumers across platform interactions over 12-24 month periods, measuring both vulnerability states and coping adaptation",
      "priority": "medium",
      "rationale": "Intervention design requires knowing whether vulnerability is episodic or chronic — current cross-sectional evidence cannot answer this"
    },
    {
      "gap_dimension": "Context",
      "gap_description": "Consumers with cognitive disabilities appear in only one study despite being among the most vulnerable populations in digital markets",
      "research_direction": "Dedicated studies of digital marketplace vulnerability in consumers with autism spectrum conditions, acquired brain injury, dementia, and learning disabilities",
      "priority": "medium",
      "rationale": "Consumer protection policy increasingly requires disability-specific evidence for digital accessibility mandates; the research base does not currently support this"
    }
  ]
}
```

---

### Step 3 — TCCM Table Builder (Pure Computation)

After the aggregation call, the TCCM table is built directly from the JSON output — no AI call needed. python-docx renders it.

**The standard TCCM table format used in JAMS, JBR, IMR:**

```
┌─────────────────────┬──────────────────────────────────────────────────────┐
│ DIMENSION           │ FINDINGS AND GAPS                                     │
├─────────────────────┼──────────────────────────────────────────────────────┤
│ THEORY              │                                                       │
│ Dominant            │ Cognitive Load Theory (54.5%), Social Cognitive      │
│                     │ Theory (36.4%), TAM (32.7%)                          │
│ Present             │ Protection Motivation Theory (25.5%),                │
│                     │ Institutional Theory (18.2%)                         │
│ Absent              │ Prospect Theory / Behavioural Economics ✗            │
│                     │ Intersectionality Theory ✗                           │
│                     │ Agency Theory ✗                                      │
├─────────────────────┼──────────────────────────────────────────────────────┤
│ CHARACTERISTICS     │                                                       │
│ Unit of analysis    │ Individual consumer (87%), Market (5%), Other (8%)   │
│ Sample type         │ Consumer panel (44%), General population (25%),      │
│                     │ Student (15%), Secondary data (9%)                   │
│ Longitudinal        │ 4 studies (7.3%) — predominantly cross-sectional ✗  │
│ Experimental        │ 11 studies (20%)                                     │
│ Pre-registered      │ 7 studies (12.7%) ✗                                 │
│ Replicated          │ 10 studies (18.2%) ✗                                │
├─────────────────────┼──────────────────────────────────────────────────────┤
│ CONTEXT             │                                                       │
│ Geography           │ UK (21.8%), USA (18.2%), Australia (10.9%)           │
│                     │ Western markets: 72.7% of corpus                    │
│ Underrepresented    │ Sub-Saharan Africa ✗, South/SE Asia ✗               │
│                     │ Latin America ✗, MENA ✗                             │
│ Economic context    │ Developed (76.4%), Emerging (10.9%), Mixed (5.5%)   │
│ Platform type       │ E-commerce (50.9%), Financial services (21.8%)      │
│ Population          │ General (50.9%), Elderly (21.8%), Low income (12.7%)│
│ Underrepresented    │ Cognitive disability ✗, Rural consumers ✗           │
├─────────────────────┼──────────────────────────────────────────────────────┤
│ METHODS             │                                                       │
│ Paradigm            │ Quantitative (60%), Qualitative (25.5%), Mixed (14.5)│
│ Data collection     │ Survey (50.9%), Experiment (20%), Interview (16.4%) │
│ Analysis            │ Regression (25.5%), SEM (21.8%), Thematic (16.4%)  │
│ Absent methods      │ Digital trace data ✗                                │
│                     │ Platform audit methodology ✗                        │
│                     │ Longitudinal panel with repeated measures ✗         │
└─────────────────────┴──────────────────────────────────────────────────────┘
✗ = identified gap requiring future research
```

---

### Step 4 — TCCM Narrative Writing Call

After the aggregation JSON is stored, one Deepseek writing call produces the TCCM narrative section that appears in the paper.

---

#### Prompt: TCCM Section Writing

```
{SCAFFOLD_PREAMBLE}

[SECTION LABEL BLOCK — all prior sections]

=== NOW WRITE: SECTION 3.2b — TCCM ANALYSIS ===
=== Do NOT repeat content from sections already written above. ===

Write the TCCM (Theory, Characteristics, Context, Methods) analysis 
section for this systematic literature review.

TCCM AGGREGATED DATA:
{tccm_summary_json}

The TCCM table (Table X) has already been inserted before this text.
This section provides the narrative interpretation of the table.

Structure — write as four subsections with these exact headings:

3.2.1 Theoretical Landscape
3.2.2 Study Characteristics  
3.2.3 Contextual Coverage
3.2.4 Methodological Profile

For each subsection:
- Open with what DOMINATES and why this matters
- Describe what is PRESENT but not dominant
- Explicitly identify what is ABSENT
- State the interpretive implication — what does this pattern 
  reveal about the field's development and blind spots?

Use these exact narratives from the TCCM analysis as your 
starting point — expand and contextualise them in academic prose:
  Theory narrative:          {theory_narrative}
  Characteristics narrative: {characteristics_narrative}
  Context narrative:         {context_narrative}
  Methods narrative:         {methods_narrative}

Requirements:
- 600-800 words total across four subsections
- Academic third person
- ✗ gaps should be stated as explicit research gaps, not just 
  described as absent
- Every percentage cited must match the TCCM aggregation data exactly
- The section should end with 2-3 sentences synthesising the most 
  consequential gap across all four dimensions

=== END OF TCCM WRITING INSTRUCTIONS ===
```

---

### Step 5 — Scaffold Addition

```python
scaffold['tccm_summary'] = {
    "dominant_theory":           "Cognitive Load Theory",
    "theory_diversity":          "medium",
    "absent_theories":           ["Prospect Theory", "Intersectionality Theory", "Agency Theory"],
    "longitudinal_pct":          7.3,
    "experimental_pct":          20.0,
    "western_dominance_pct":     72.7,
    "underrepresented_regions":  ["Sub-Saharan Africa", "South/SE Asia", "Latin America"],
    "quantitative_pct":          60.0,
    "absent_methods":            ["Digital trace data", "Platform audit methodology"],
    "pre_registered_pct":        12.7,
    "key_gaps": [
        "Behavioural economics frameworks entirely absent",
        "72.7% of evidence from Western markets",
        "Digital trace data not used in any study",
        "7.3% longitudinal rate"
    ]
}
```

The Discussion and Future Research writing calls receive this summary so they can reference TCCM gaps when making recommendations.

---



### Where TCCM Appears in the Final Paper

```
3.2  Study Characteristics
     Table 2: Study Characteristics (auto-built from DataExtraction)
     [narrative paragraph]
     Table 3: TCCM Analysis (auto-built from TCCM aggregation JSON)
3.2.1  Theoretical Landscape
3.2.2  Study Characteristics
3.2.3  Contextual Coverage
3.2.4  Methodological Profile
```

The TCCM table and its narrative interpretation appear together in the Study Characteristics section. Future research gaps identified in TCCM flow directly into Section 6 (Future Research Agenda) — the `future_research_from_tccm` array feeds into that section's structured table.