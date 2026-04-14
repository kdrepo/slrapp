# Placeholders:
# {objectives}
# {research_questions}
# {start_year}
# {end_year}
# {start_filter}
# {end_filter}

Generate 4 distinct Scopus Boolean queries using TITLE-ABS-KEY.
Review Context:
Objectives:
{objectives}

Research Questions:
{research_questions}

Date Range: {start_year} to {end_year}

Mandatory Query Requirements:

Core:
- Focus on primary terms.
- Must include LIMIT-TO ( EXACTKEYWORD, ... ) for the 3-5 most central keywords.

Constructs:
- Target theoretical frameworks linked with the review domain and concepts.

Population:
- Target specific participant groups, worker/user groups, or demographic subgroups relevant to the review.

Outcomes:
- Target specific outcomes, effects, or result variables relevant to the review.

Global Filters (append to every query):
AND PUBYEAR > {start_filter} AND PUBYEAR < {end_filter} AND ( LIMIT-TO ( DOCTYPE , "ar" ) ) AND ( LIMIT-TO ( LANGUAGE , "English" ) )

Return JSON:
[{"query": "...", "focus": "core|constructs|population|outcomes", "rationale": "..."}]
