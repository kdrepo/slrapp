{scaffold_preamble}
TASK: You are writing the final synthesis paragraph for the theme: {theme_name}.
ADVOCATE VIEW (internal draft): {advocate_text}
CRITIC VIEW (internal draft): {critic_text}
DATA: {theme_extractions_json}

Write the definitive synthesis paragraph for this theme for inclusion in
the systematic review.
- Start with a declarative sentence on the state of evidence.
- Synthesize supporting evidence and explicitly acknowledge limitations/qualifications.
- Explain contradictions by context.
- Ensure claims are cited from the registry by short_ref.
- End with implications for the overall review and any gaps this theme reveals

PUBLICATION STYLE CONSTRAINTS (MANDATORY):
- Do NOT mention internal roles, process, or debate framing.
- Never use words like: Advocate, Critic, Reconciler, pass, loop, prompt, or "this argument".
- Do NOT write meta-commentary such as "the Critic notes/correctly qualifies" or "the Advocate argues".
- Write as neutral, publication-ready synthesis prose for an SLR Results section.
- Use evidence-first statements grounded in cited studies.

If your draft contains any internal-role language, rewrite it before returning final text.
DO NOT use bullet points or headers.
