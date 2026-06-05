import json

payload_map = {
    "sections": [
        {
            "id": "1_0_introduction",
            "name": "Introduction",
            "construction_logic": {
                "source_data": ["Initial Project Config", "Phase 1-2"],
                "payload_fields": {
                    "research_context": "Global domain definition from Project Config",
                    "rq_list": "Array of strings from Research Questions",
                    "objectives": "List of review objectives",
                    "pico": "Population, Intervention, Comparison, Outcome definitions"
                }
            }
        },
        {
            "id": "2_1_search_2_2_criteria",
            "name": "2.1 Search Strategy and 2.2 Selection Criteria",
            "construction_logic": {
                "source_data": ["Initial Project Config", "Phase 2 Search Output"],
                "payload_fields": {
                    "search_queries": "Full tier-based search architecture",
                    "review_metadata": "Date range, databases used, and search limits",
                    "pico": "Inclusion and exclusion criteria strings"
                }
            }
        },
        {
            "id": "2_3_process_extraction",
            "name": "Study Selection and Data Extraction",
            "construction_logic": {
                "source_data": ["Phase 5 Screening", "Phase 16 Registry"],
                "payload_fields": {
                    "prisma_counts": "Full numerical funnel (Initial hits, screening, full-text, final)",
                    "paper_registry": "List of citations for the final included papers"
                }
            }
        },
        {
            "id": "3_1_results_quality",
            "name": "Search Results and Quality Assessment",
            "construction_logic": {
                "source_data": ["Phase 5 Screening", "Phase 16 Extraction"],
                "payload_fields": {
                    "prisma_counts": "Final inclusion count (n=X)",
                    "quality_summary": "Aggregate stats (Mean, Med, Risk Categories) from all phase 16 quality scores",
                    "paper_registry": "Lookup for papers mentioned as high-quality examples"
                }
            }
        },
        {
            "id": "3_2_characteristics_subgroup",
            "name": "Study Characteristics and Subgroup Analysis",
            "construction_logic": {
                "source_data": ["Phase 20 TCCM Aggregation", "Phase 16 Extraction"],
                "payload_fields": {
                    "tccm_summary": "Characteristics and Context dimensions from Phase 20 JSON",
                    "subgroup_data": "Derived clusters (e.g., Developed vs Emerging count) from context_dimension",
                    "paper_registry": "Citations to anchor specific characteristic trends"
                }
            }
        },
        {
            "id": "3_3_bibliometric",
            "name": "Bibliometric Findings",
            "construction_logic": {
                "source_data": ["Phase 2 Metadata", "Phase 16 Year/Journal extraction"],
                "payload_fields": {
                    "review_metadata": "List of journals and publication date ranges",
                    "quality_summary": "Used to correlate recency with quality scores",
                    "paper_registry": "Used to cite earliest vs latest papers in the range"
                }
            }
        },
        {
            "id": "3_4_synthesis",
            "name": "Thematic Synthesis of Empirical Findings",
            "construction_logic": {
                "source_data": ["Phase 18 Master Reconciler"],
                "payload_fields": {
                    "reconciled_master_themes": "The 'master_description' and 'evidence_grade' from Phase 18 output",
                    "paper_registry": "Mandatory citation lookup for every finding"
                }
            }
        },
        {
            "id": "3_5_theory_propositions",
            "name": "Integrated Theoretical Framework and Propositions",
            "construction_logic": {
                "source_data": ["Phase 17a", "Phase 17b", "Phase 18", "Phase 19"],
                "payload_fields": {
                    "theory_landscape": "Frequency counts and primary lens from Phase 17a",
                    "theoretical_synthesis": "Overarching argument and Propositions (P1-P5) from Phase 17b",
                    "conceptual_model_spec": "Model JSON (Antecedents, Mediators, Moderators) from Phase 19",
                    "reconciled_master_themes": "The 'theoretical_integration' paragraphs from Phase 18 output",
                    "paper_registry": "Citations to anchor theoretical claims"
                }
            }
        },
        {
            "id": "4_1_rq_discussion",
            "name": "Addressing the Core Research Questions",
            "construction_logic": {
                "source_data": ["Phase 18 Master Reconciler", "Phase 17b Propositions"],
                "payload_fields": {
                    "rq_list": "Original research questions",
                    "reconciled_master_themes": "Master themes to provide debate-tested evidence",
                    "theoretical_synthesis": "Propositions to explain the 'why' behind the answers"
                }
            }
        },
        {
            "id": "4_2_implications",
            "name": "Practice and Policy Implications",
            "construction_logic": {
                "source_data": ["Phase 17b Propositions", "Phase 18 Reconciler"],
                "payload_fields": {
                    "theoretical_synthesis": "Propositions mapped to real-world actions",
                    "reconciled_master_themes": "Boundary conditions from the 'Critic' view to warn stakeholders",
                    "research_context": "Target domain for stakeholder-specific advice"
                }
            }
        },
        {
            "id": "4_3_limitations",
            "name": "Limitations of the Review",
            "construction_logic": {
                "source_data": ["Phase 16 Extraction (Bias Notes)", "Phase 2 Search Constraints"],
                "payload_fields": {
                    "quality_summary": "Aggregate weaknesses (e.g., bias in 'Design' or 'Analysis')",
                    "review_metadata": "Search limits (Scopus only, English only)",
                    "prisma_counts": "Total records excluded vs included"
                }
            }
        },
        {
            "id": "4_4_future_research",
            "name": "Future Research Agenda",
            "construction_logic": {
                "source_data": ["Phase 20 TCCM Gaps", "Phase 17a Theoretical Gaps"],
                "payload_fields": {
                    "tccm_summary": "Future research directions from Phase 20 'Methods' and 'Context' audits",
                    "theoretical_gaps": "Missing theories and their implications from Phase 17a",
                    "paper_registry": "Citations to contrast current vs future directions"
                }
            }
        },
        {
            "id": "5_0_conclusion",
            "name": "Conclusion",
            "construction_logic": {
                "source_data": ["Phase 17b Synthesis"],
                "payload_fields": {
                    "rq_list": "Final loop-back to original questions",
                    "theoretical_synthesis": "The final theoretical contribution summary"
                }
            }
        }
    ],
    "global_injection_requirements": {
        "every_section": ["research_context", "paper_registry"],
        "discussion_chapters": ["global_intro_text", "previous_section_text"]
    }
}

# Output the file
file_path = "ghostwriter_payload_map.json"
with open(file_path, "w") as f:
    json.dump(payload_map, f, indent=4)
