Since you haven't started the coding for visualizations yet, here is the full breakdown of your **Visual Assets Roadmap**. Your SLR engine generates these in two distinct "waves": the **Mathematical Wave** (Phases 17–18) and the **Evidence Wave** (Phase 22).

---

### Phase 17 & 18: The Mathematical Wave
**When:** Immediately after Quality Assessment and before Synthesis.
**Role:** To visualize the "landscape" of the research field using Scopus metadata.

| Type | Name | What it shows | Source Data |
| :--- | :--- | :--- | :--- |
| **Figure** | **Keyword Co-occurrence Network** | Connections between research topics (e.g., 'Algorithmic Management' linked to 'Burnout'). | Scopus Keywords |
| **Figure** | **Thematic Map (2x2)** | Motor, Niche, Emerging, and Basic themes based on Centrality and Density. | Louvain Clusters |
| **Figure** | **Temporal Trend Chart** | Growth of the topic over time (Publication Year vs. Count). | `paper.year` |
| **Figure** | **Geographic Choropleth** | Where the research is being conducted globally. | `extraction.country` |
| **Table** | **Journal Impact Table** | Top 10 journals publishing on this topic by frequency. | `paper.journal` |

---

### Phase 19: The Data Foundation (Scaffold)
**When:** The transition between analysis and writing.
**Role:** This phase generates the **Source of Truth** (JSON) for all tables but not the visual artifacts themselves.
* **What:** Generates the `subgroup_data` counts (e.g., "18 cross-sectional studies").

---

### Phase 22: The Evidence Wave (The "Proof")
**When:** After themes are identified, but before the full manuscript is written.
**Role:** To ground the AI's "claims" in hard evidence for the reader/reviewer.

| Type | Name | What it shows | Source Data |
| :--- | :--- | :--- | :--- |
| **Figure** | **Evidence Strength Heatmap** | A grid of **Themes** vs. **Quality Scores**. Shows where evidence is "Ironclad" vs "Weak." | `ThemeSynthesis` + `Quality` |
| **Table** | **Thematic Cross-Tabulation** | The "Receipts": A grid showing which specific paper supports which theme. | `ThemeSynthesis.papers` |
| **Table** | **Table 1: Study Characteristics** | Standard SLR table: Author, Year, Population, Design, Key Finding, Quality Score. | `DataExtraction` |
| **Table** | **Table 2: Quality Assessment** | Detailed rubric scores (0–10) and Risk of Bias levels for every paper. | `QualityAssessment` |

---

### Administrative / PRISMA Visuals
These are generated throughout the pipeline to track progress:
* **Figure: PRISMA 2020 Flow Diagram (Phase 3–13):** The classic "Waterfall" showing how 1,300 papers became 42.
* **Figure: Cleaning Summary (Phase 5):** A "Before vs. After" bar chart showing how many duplicates or "junk" records were removed during deduplication.


---
