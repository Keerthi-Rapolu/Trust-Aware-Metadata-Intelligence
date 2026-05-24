"""
frontend/streamlit_app.py

Lightweight Streamlit frontend for the metadata SQL assistant.
"""

import json
from pathlib import Path

try:
    import streamlit as st
except ImportError:  # pragma: no cover
    st = None

from generation.refusal_engine import RefusalEngine
from generation.sql_generator import SqlGenerator
from ingestion.graph_store import MetadataGraph
from ingestion.lineage_parser import LineageParser
from ingestion.manifest_ingestor import ManifestIngestor
from reasoning.query_planner import QueryPlanner


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"


def load_demo_components(user_role: str = "analyst") -> tuple:
    with open(DATA_DIR / "sample_manifest.json", "r", encoding="utf-8") as f:
        manifest = json.load(f)
    with open(DATA_DIR / "glossary.json", "r", encoding="utf-8") as f:
        glossary = json.load(f)

    ingestor = ManifestIngestor()
    parser = LineageParser()
    graph = MetadataGraph()
    graph.add_model_nodes(ingestor.extract_all(manifest))

    for edge in parser.extract_edges(manifest):
        graph.graph.add_edge(
            edge["upstream"],
            edge["downstream"],
            edge_type=edge["edge_type"],
            left_column=edge.get("left_column"),
            right_column=edge.get("right_column"),
        )

    planner = QueryPlanner(graph=graph, glossary=glossary, user_role=user_role)
    generator = SqlGenerator()
    refusal_engine = RefusalEngine()
    return planner, generator, refusal_engine


def build_response_bundle(
    query: str,
    planner: QueryPlanner,
    generator: SqlGenerator,
    refusal_engine: RefusalEngine,
) -> dict:
    plan_result = planner.plan(query)
    classification = refusal_engine.classify(query, plan_result)

    effective_result = plan_result
    if not classification.get("should_generate_sql", False):
        effective_result = {
            **plan_result,
            "should_proceed": False,
            "failure_type": classification.get("failure_type"),
            "failure_reason": classification.get("reason"),
            "recommendation": classification.get("recommendation"),
            "explanation_text": (
                f"Planning stopped with {classification.get('failure_type')}: "
                f"{classification.get('reason')}"
            ),
        }

    sql_result = generator.generate(effective_result)
    ui_state = build_ui_state(plan_result, classification, sql_result)
    return {
        "plan_result": plan_result,
        "classification": classification,
        "sql_result": sql_result,
        "ui_state": ui_state,
    }


def build_ui_state(plan_result: dict, classification: dict, sql_result: dict) -> dict:
    explanations = plan_result.get("explanations", {})
    confidence = explanations.get("confidence_explanation", {})
    refusal = explanations.get("refusal_explanation", {})
    steps = plan_result.get("step_results", {}) or {}

    refusal_type = classification.get("failure_type") or refusal.get("failure_type")
    refusal_reason = classification.get("reason") or refusal.get("reason")
    confidence_score = confidence.get(
        "overall_confidence",
        plan_result.get("final_confidence", 0.0),
    )
    limiting_factor = confidence.get("confidence_limiting_factor", "not_evaluated")
    retrieval_scores = explanations.get("retrieval_scores", {})
    governance = steps.get("step6_governance", {})
    retrieval = steps.get("step7_retrieval", {})
    extraction = steps.get("step2_extraction", {})
    confidence_step = steps.get("step8_confidence", {})

    if sql_result.get("sql"):
        decision = "SQL_GENERATED"
    elif refusal_type in {"GOVERNANCE_BLOCKED", "UNSAFE_QUERY"}:
        decision = "BLOCKED"
    else:
        decision = "REFUSED"

    return {
        "decision": decision,
        "selected_tables": explanations.get("selected_tables", []),
        "retrieval_scores": [
            {"model": model, "score": score}
            for model, score in retrieval_scores.items()
        ],
        "retrieval_rankings": retrieval.get("rankings", []),
        "retrieved_metadata": [
            {
                "term": entity.get("term"),
                "matched_token": entity.get("matched_token"),
                "domain": entity.get("domain"),
                "models": entity.get("candidate_models", []),
                "columns": entity.get("candidate_columns", []),
                "score": entity.get("score"),
            }
            for entity in extraction.get("entities_extracted", [])
        ],
        "join_path": explanations.get("join_path", "not evaluated"),
        "join_confidence": explanations.get("join_confidence", 0.0),
        "confidence_score": confidence_score,
        "confidence_level": plan_result.get("confidence_level", ""),
        "confidence_limiting_factor": limiting_factor,
        "show_limiting_factor": (
            confidence_score < 0.85
            and limiting_factor not in ("none", "not_evaluated")
        ),
        "refusal_type": refusal_type,
        "refusal_reason": refusal_reason,
        "show_refusal": refusal_type is not None,
        "warnings": sql_result.get("warnings", []),
        "sql": sql_result.get("sql"),
        "governance_flags": {
            "blocked": governance.get("blocked", False),
            "reason": governance.get("reason"),
            "blocked_models": governance.get("blocked_models", []),
            "blocked_columns": governance.get("blocked_cols", []),
            "restricted_columns": governance.get("restricted_columns", []),
            "unsafe_patterns_detected": governance.get("unsafe_patterns_detected", []),
            "estimated_scan_gb": governance.get("estimated_scan_gb", 0.0),
            "module_scores": governance.get("module_scores", {}),
            "module_results": governance.get("module_results", {}),
        },
        "confidence_components": confidence_step.get("component_scores", {}),
        "explanation_text": (
            (
                f"Planning stopped with {classification.get('failure_type')}: "
                f"{classification.get('reason')}"
            )
            if classification.get("failure_type")
            else plan_result.get("explanation_text")
        ) or sql_result.get("explanation", ""),
    }


def main() -> None:  # pragma: no cover
    if st is None:
        raise ImportError("streamlit is required to run frontend/streamlit_app.py")

    st.set_page_config(page_title="Metadata SQL Assistant", layout="wide")
    st.title("Enterprise Metadata Intelligence Demo")
    st.caption("Phase 6 explainability surface for planner, governance, and SQL generation.")

    user_role = st.selectbox(
        "User role",
        ["analyst", "finance_user", "support_user", "executive"],
        index=0,
    )
    query = st.text_area("Ask a question", value="list all segments", height=120)

    if st.button("Run query"):
        planner, generator, refusal_engine = load_demo_components(user_role=user_role)
        bundle = build_response_bundle(query, planner, generator, refusal_engine)
        ui = bundle["ui_state"]
        classification = bundle["classification"]

        st.subheader("Confidence")
        st.progress(max(min(float(ui["confidence_score"]), 1.0), 0.0))
        st.write(
            f"Score: {ui['confidence_score']:.2f} | Level: {ui['confidence_level'] or 'n/a'}"
        )
        if ui["show_limiting_factor"]:
            st.warning(f"Confidence-limiting factor: {ui['confidence_limiting_factor']}")

        st.subheader("Retrieval")
        st.write(ui["selected_tables"] or ["none"])
        if ui["retrieval_scores"]:
            st.json(ui["retrieval_scores"])

        st.subheader("Join Path")
        st.write(ui["join_path"])
        st.write(f"Join confidence: {ui['join_confidence']:.2f}")

        st.subheader("Explanation")
        st.write(ui["explanation_text"])

        if ui["show_refusal"]:
            st.error(
                f"{ui['refusal_type']}: {ui['refusal_reason']}\n"
                f"{classification.get('recommendation', '')}"
            )
        elif ui["sql"]:
            st.subheader("Generated SQL")
            st.code(ui["sql"], language="sql")


if __name__ == "__main__":  # pragma: no cover
    main()
