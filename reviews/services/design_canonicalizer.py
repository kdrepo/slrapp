import re


def _norm(text):
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def canonicalize_study_design(raw_design):
    text = _norm(raw_design)
    if not text:
        return "unknown"

    if any(k in text for k in ["randomized", "randomised", "rct", "controlled trial", "experiment"]):
        return "randomized controlled trial"

    if "quasi" in text or "difference-in-differences" in text or "natural experiment" in text:
        return "quasi-experimental"

    if "mixed" in text and "method" in text:
        return "mixed-methods"

    if any(k in text for k in ["qualitative", "interview", "focus group", "ethnograph", "thematic analysis", "grounded theory", "phenomenolog"]):
        return "qualitative"

    if any(k in text for k in ["cross-sectional", "cross sectional", "survey", "questionnaire"]):
        return "cross-sectional survey"

    if any(k in text for k in ["longitudinal", "panel", "cohort", "time series"]):
        return "longitudinal observational"

    if "case study" in text:
        return "case study"

    if any(k in text for k in ["systematic review", "meta-analysis", "meta analysis", "scoping review"]):
        return "evidence synthesis"

    if any(k in text for k in ["secondary", "administrative data", "registry data", "dataset"]):
        return "secondary data analysis"

    return raw_design.strip() if isinstance(raw_design, str) and raw_design.strip() else "unknown"


def canonicalize_design_list(values):
    if not isinstance(values, list):
        values = [values] if values else []

    out = []
    seen = set()
    for value in values:
        c = canonicalize_study_design(value)
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out
