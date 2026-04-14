from .gemini_service import formalize_research_parameters, render_scaffold_preamble
from .ris_parser import dedupe_review_papers, ingest_ris_file
from .scopus_query_service import generate_scopus_queries
from .dialectical_synthesizer import run_dialectical_synthesis

__all__ = [
    'formalize_research_parameters',
    'render_scaffold_preamble',
    'generate_scopus_queries',
    'ingest_ris_file',
    'dedupe_review_papers',
    'run_dialectical_synthesis',
]

