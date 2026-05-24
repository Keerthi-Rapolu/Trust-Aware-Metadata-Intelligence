"""
app.py

Single-page Streamlit reasoning demo for the metadata SQL assistant.

UI changes (2026-05-24):
  1. Top summary banner — immediate visual understanding of outcome
  2. Confidence breakdown bars — inline label + bar + value on one row
  3. Governance horizontal badges — no text wrapping, white-space:nowrap
  4. SQL code block with syntax highlighting (language="sql")
  5. Advanced Debug Trace — compact summary + downloadable full JSON
"""

from __future__ import annotations

import json
from typing import List

import pandas as pd
import streamlit as st

from frontend.streamlit_app import build_response_bundle, load_demo_components


APP_TITLE = "Trust-Aware Metadata Reasoning Demo"
APP_SUBTITLE = (
    "A single-page reasoning demo that shows how the system decides to "
    "generate SQL, refuse, or block a query."
)

SAMPLE_QUERIES = {
    "Answerable Query": "show segment data",
    "Ambiguous Join": "show revenue by region",
    "Missing Schema": "show me the xyz_metric_zz99",
    "Governance Block": "show all payments",
}


# ── Session helpers ───────────────────────────────────────────────────────────

def _set_query(query: str) -> None:
    st.session_state["demo_query"] = query


# ── Badge helpers ─────────────────────────────────────────────────────────────

def _badge(decision: str) -> str:
    colors = {
        "SQL_GENERATED": "#0f766e",
        "REFUSED": "#9a3412",
        "BLOCKED": "#991b1b",
    }
    color = colors.get(decision, "#334155")
    return (
        f"<span style='display:inline-block;padding:0.35rem 0.65rem;"
        f"border-radius:999px;background:{color};color:white;font-weight:700;"
        f"letter-spacing:0.02em;white-space:nowrap'>{decision}</span>"
    )


def _mini_badge(text: str, color: str) -> str:
    return (
        f"<span style='display:inline-block;padding:0.2rem 0.55rem;"
        f"border-radius:999px;font-size:0.78rem;font-weight:700;"
        f"letter-spacing:0.02em;color:white;background:{color};"
        f"white-space:nowrap'>{text}</span>"
    )


# ── CSS ───────────────────────────────────────────────────────────────────────

def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        .pipeline-step {
            border: 1px solid rgba(148, 163, 184, 0.35);
            border-radius: 14px;
            padding: 0.8rem;
            text-align: center;
            background: white;
            min-height: 110px;
        }
        .pipeline-step .step-name {
            font-size: 0.88rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
        }
        .pipeline-step .step-state {
            font-size: 0.95rem;
            font-weight: 700;
        }
        .conf-bar-row {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            margin-bottom: 0.65rem;
        }
        .conf-bar-label {
            width: 120px;
            font-weight: 600;
            font-size: 0.88rem;
            color: #1e293b;
            flex-shrink: 0;
        }
        .conf-bar-track {
            flex: 1;
            background: #e2e8f0;
            border-radius: 5px;
            height: 10px;
            overflow: hidden;
        }
        .conf-bar-fill {
            height: 10px;
            border-radius: 5px;
        }
        .conf-bar-value {
            width: 36px;
            text-align: right;
            font-size: 0.88rem;
            font-weight: 700;
            color: #1e293b;
            flex-shrink: 0;
        }
        .gov-badge-row {
            display: flex;
            gap: 0.75rem;
            flex-wrap: nowrap;
            margin-top: 0.5rem;
            overflow-x: auto;
        }
        .gov-badge {
            border-radius: 10px;
            padding: 0.55rem 0.9rem;
            min-width: 90px;
            flex-shrink: 0;
        }
        .gov-badge .gov-label {
            font-size: 0.72rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.2rem;
        }
        .gov-badge .gov-value {
            font-size: 1.0rem;
            font-weight: 800;
            white-space: nowrap;
        }
        .summary-banner {
            border-radius: 12px;
            padding: 1.2rem 1.5rem;
            margin-bottom: 1.5rem;
        }
        .summary-banner .banner-title {
            font-size: 1.25rem;
            font-weight: 800;
        }
        .summary-banner .banner-detail {
            font-size: 0.93rem;
            margin-top: 0.35rem;
        }
        .muted-note {
            color: #475569;
            font-size: 0.9rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ── Top summary banner ────────────────────────────────────────────────────────

def _render_top_banner(ui: dict, classification: dict) -> None:
    """
    Prominent full-width outcome banner.  First thing the user sees after
    running a query — communicates the decision immediately.
    """
    decision      = ui["decision"]
    confidence    = ui["confidence_score"]
    refusal_type  = ui.get("refusal_type")
    reason        = ui.get("refusal_reason") or ""
    gov_blocked   = ui.get("governance_flags", {}).get("blocked", False)
    recommendation = classification.get("recommendation", "")

    if decision == "SQL_GENERATED":
        bg, border, fg = "#dcfce7", "#16a34a", "#15803d"
        title  = "✅  SAFE SQL GENERATED"
        detail = (
            f"Confidence: {confidence:.2f}"
            + (" · No governance violations detected" if not gov_blocked else "")
        )
    elif refusal_type == "GOVERNANCE_BLOCKED":
        bg, border, fg = "#fee2e2", "#dc2626", "#991b1b"
        title  = "🚫  GOVERNANCE BLOCK"
        detail = reason or "Access denied by governance policy."
    elif refusal_type == "UNSAFE_QUERY":
        bg, border, fg = "#fee2e2", "#dc2626", "#991b1b"
        title  = "⛔  UNSAFE QUERY BLOCKED"
        detail = reason or "DML/DDL or destructive bulk-operation detected."
    elif refusal_type == "SEMANTIC_CONFLICT":
        bg, border, fg = "#fff7ed", "#ea580c", "#9a3412"
        title  = "⚠️  SAFE REFUSAL  ·  Semantic Conflict"
        detail = reason or "Multiple metric definitions found — clarification required."
    elif refusal_type == "INSUFFICIENT_SCHEMA":
        bg, border, fg = "#fff7ed", "#ea580c", "#9a3412"
        title  = "⚠️  SAFE REFUSAL  ·  Insufficient Schema"
        detail = reason or "No recognised entities found in the metadata graph."
    else:
        bg, border, fg = "#fff7ed", "#ea580c", "#9a3412"
        title  = f"⚠️  SAFE REFUSAL  ·  {refusal_type or 'REFUSED'}"
        detail = reason or "Query could not be safely answered."

    extra = f"<div class='banner-detail' style='color:{fg};opacity:0.75;'>{recommendation}</div>" if recommendation else ""

    st.markdown(
        f"""
        <div class='summary-banner' style='background:{bg};border:1.5px solid {border};'>
          <div class='banner-title' style='color:{fg};'>{title}</div>
          <div class='banner-detail' style='color:{fg};'>{detail}</div>
          {extra}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Confidence breakdown — label + value on one line, bar below ───────────────

def _render_confidence_breakdown(ui: dict) -> None:
    st.subheader("Confidence Breakdown")
    components = ui.get("confidence_components", {})
    if not components:
        st.caption("Confidence propagation was not reached for this query.")
        return

    labels = [
        ("retrieval",      "Retrieval"),
        ("join_path",      "Join Path"),
        ("governance",     "Governance"),
        ("completeness",   "Completeness"),
        ("intent_clarity", "Intent Clarity"),
    ]
    for key, label in labels:
        value   = float(components.get(key, 0.0))
        clamped = max(0.0, min(1.0, value))
        # Single line: label (bold) + value (monospace) — then bar below
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;"
            f"align-items:baseline;margin-bottom:2px;'>"
            f"<span style='font-weight:600;font-size:0.88rem;'>{label}</span>"
            f"<span style='font-family:monospace;font-size:0.88rem;font-weight:700;"
            f"color:#1e293b;'>{value:.2f}</span></div>",
            unsafe_allow_html=True,
        )
        st.progress(clamped)
        st.markdown("<div style='margin-bottom:6px;'></div>", unsafe_allow_html=True)


# ── Governance — st.metric cards (4 columns, no wrapping) ────────────────────

def _render_governance(ui: dict) -> None:
    st.subheader("Governance Evaluation")
    flags   = ui.get("governance_flags", {})
    modules = flags.get("module_results", {})
    pii     = modules.get("pii", {})
    rbac    = modules.get("rbac", {})
    cost    = modules.get("cost", {})

    pii_bad  = bool(pii.get("blocked"))
    rbac_bad = bool(rbac.get("blocked"))
    cost_gb  = float(cost.get("estimated_scan_gb", flags.get("estimated_scan_gb", 0.0)) or 0.0)
    unsafe   = cost.get("unsafe_patterns_detected", flags.get("unsafe_patterns_detected", [])) or []
    cost_bad = bool(cost.get("blocked")) or cost_gb > 500

    def _gov_card(label: str, value: str, state: str) -> str:
        """
        Inline HTML card — no emoji, safe for PDF export.
        state: "ok" | "warn" | "bad"
        """
        bg     = {"ok": "#dcfce7", "warn": "#fff7ed", "bad": "#fee2e2"}[state]
        border = {"ok": "#86efac", "warn": "#fdba74", "bad": "#fca5a5"}[state]
        fg     = {"ok": "#15803d", "warn": "#9a3412", "bad": "#991b1b"}[state]
        return (
            f"<div style='background:{bg};border:1px solid {border};"
            f"border-radius:8px;padding:0.6rem 0.9rem;text-align:center;'>"
            f"<div style='font-size:0.72rem;font-weight:700;text-transform:uppercase;"
            f"letter-spacing:0.05em;color:{fg};margin-bottom:0.25rem;'>{label}</div>"
            f"<div style='font-size:1.05rem;font-weight:800;color:{fg};"
            f"white-space:nowrap;'>{value}</div>"
            f"</div>"
        )

    pii_state  = "bad" if pii_bad  else "ok"
    rbac_state = "bad" if rbac_bad else "ok"
    cost_state = "bad" if cost_bad else ("warn" if cost_gb > 100 else "ok")

    cards_html = (
        "<div style='display:grid;grid-template-columns:repeat(4,1fr);"
        "gap:0.75rem;margin-top:0.5rem;'>"
        + _gov_card("PII",            "BLOCKED" if pii_bad  else "CLEAR",   pii_state)
        + _gov_card("RBAC",           "BLOCKED" if rbac_bad else "CLEAR",   rbac_state)
        + _gov_card("Cost Risk",      "HIGH" if cost_bad else ("MEDIUM" if cost_gb > 100 else "LOW"), cost_state)
        + _gov_card("Estimated Scan", f"{cost_gb:,.0f} GB",                 "ok")
        + "</div>"
    )
    st.markdown(cards_html, unsafe_allow_html=True)

    if unsafe:
        st.markdown("**Unsafe patterns detected:**")
        for p in unsafe:
            st.write(f"- {p}")


# ── Pipeline ──────────────────────────────────────────────────────────────────

def _pipeline_steps(bundle: dict) -> List[dict]:
    plan           = bundle["plan_result"]
    classification = bundle["classification"]
    sql            = bundle["sql_result"]
    steps          = plan.get("step_results", {}) or {}

    def _s(label: str, color: str) -> str:
        return _mini_badge(label, color)

    sql_state = (
        _s("COMPLETE", "#0f766e") if sql.get("sql") else (
            _s("BLOCKED",  "#991b1b") if classification.get("failure_type") in {"GOVERNANCE_BLOCKED", "UNSAFE_QUERY"}
            else _s("STOPPED", "#9a3412")
        )
    )
    conf_state = (
        _s("COMPLETE", "#0f766e") if "step8_confidence" in steps else (
            _s("SKIPPED", "#64748b") if classification.get("failure_type") == "GOVERNANCE_BLOCKED"
            else _s("STOPPED", "#9a3412")
        )
    )

    return [
        {"name": "Intent Extraction",    "state": _s("COMPLETE", "#0f766e") if "step1_intent"    in steps else _s("PENDING", "#64748b")},
        {"name": "Metadata Retrieval",   "state": _s("COMPLETE", "#0f766e") if steps.get("step2_extraction") else _s("PENDING", "#64748b")},
        {"name": "Join Reasoning",       "state": _s("COMPLETE", "#0f766e") if "step4_join_paths" in steps else _s("SKIPPED", "#64748b")},
        {"name": "Governance Check",     "state": _s("COMPLETE", "#0f766e") if "step6_governance" in steps else _s("PENDING", "#64748b")},
        {"name": "Confidence Scoring",   "state": conf_state},
        {"name": "SQL Generation",       "state": sql_state},
    ]


def _render_pipeline(bundle: dict) -> None:
    st.subheader("Reasoning Pipeline")
    cols = st.columns(6)
    for col, step in zip(cols, _pipeline_steps(bundle)):
        with col:
            st.markdown(
                f"<div class='pipeline-step'>"
                f"<div class='step-name'>{step['name']}</div>"
                f"<div class='step-state'>{step['state']}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )


# ── Summary row ───────────────────────────────────────────────────────────────

# Map internal factor keys to natural language for display
_FACTOR_NATURAL: dict = {
    "retrieval":      "retrieval signal strength",
    "join_path":      "join path confidence",
    "governance":     "governance safety score",
    "completeness":   "metadata completeness",
    "intent_clarity": "intent clarity",
}

# Human-readable labels for the summary row (avoid raw enum values)
_DECISION_LABEL: dict = {
    "SQL_GENERATED": "Safe SQL",
    "REFUSED":       "Safe Refusal",
    "BLOCKED":       "Blocked",
}


def _render_summary_row(ui: dict, classification: dict) -> None:
    status_col, confidence_col, failure_col = st.columns([1.1, 1.5, 1.5])

    with status_col:
        st.markdown("**Status**")
        label = _DECISION_LABEL.get(ui["decision"], ui["decision"])
        st.markdown(_badge(ui["decision"]).replace(ui["decision"], label), unsafe_allow_html=True)

    with confidence_col:
        st.markdown("**Confidence**")
        st.progress(max(min(float(ui["confidence_score"]), 1.0), 0.0))
        conf_level = ui.get("confidence_level") or "n/a"
        if conf_level == "refuse" and ui.get("refusal_type") in {"GOVERNANCE_BLOCKED", "UNSAFE_QUERY"}:
            conf_level = "blocked"
        st.caption(f"{ui['confidence_score']:.2f} · {conf_level}")

    with failure_col:
        st.markdown("**Failure Type**")
        st.write(ui["refusal_type"] or "—")

    if ui.get("show_limiting_factor"):
        raw_factor = ui["confidence_limiting_factor"]
        natural    = _FACTOR_NATURAL.get(raw_factor, raw_factor)
        st.warning(f"Confidence limited by {natural}.")


# ── Metadata tables ───────────────────────────────────────────────────────────

def _flatten_metadata_rows(ui: dict) -> List[dict]:
    rows = []
    for item in ui["retrieved_metadata"]:
        models  = item.get("models",  []) or [""]
        columns = item.get("columns", []) or [""]
        for model in models:
            for column in columns:
                rows.append(
                    {
                        "Entity":        item.get("term"),
                        "Matched Column": column,
                        "Model":         model,
                        "Domain":        item.get("domain") or "unknown",
                        "Match Score":   round(float(item.get("score") or 0.0), 2),
                    }
                )
    return rows


def _retrieval_table(ui: dict) -> pd.DataFrame:
    rows = []
    for item in ui.get("retrieval_rankings", []):
        scores = item.get("scores", {})
        rows.append(
            {
                "Candidate":  item.get("candidate"),
                "Semantic":   round(float(scores.get("semantic_similarity",     0.0)), 2),
                "Lineage":    round(float(scores.get("lineage_proximity",        0.0)), 2),
                "Glossary":   round(float(scores.get("glossary_overlap",         0.0)), 2),
                "History":    round(float(scores.get("historical_relevance",     0.0)), 2),
                "Governance": round(float(scores.get("governance_compatibility", 0.0)), 2),
                "Final":      round(float(item.get("final_score",               0.0)), 2),
            }
        )
    return pd.DataFrame(rows)


def _decision_record(ui: dict, classification: dict) -> pd.DataFrame:
    priority = classification.get("priority")
    priority_label = (
        "Governance Critical" if priority == 1
        else "Unsafe Query"   if priority == 2
        else "Normal"         if classification.get("status") == "SUCCESS"
        else "Reasoning Refusal"
    )
    return pd.DataFrame(
        [
            {"Field": "Status",       "Value": classification.get("status")},
            {"Field": "SQL Generated","Value": "Yes" if ui.get("sql") else "No"},
            {"Field": "Confidence",   "Value": f"{ui['confidence_score']:.2f}"},
            {"Field": "Failure Type", "Value": ui.get("refusal_type") or "None"},
            {"Field": "Priority",     "Value": priority_label},
        ]
    )


# ── Debug trace — compact summary + download ──────────────────────────────────

def _render_debug_trace(bundle: dict) -> None:
    """
    Compact trace summary with a download button for the full JSON.
    Does NOT dump the entire nested object into the page.
    """
    ui     = bundle["ui_state"]
    plan   = bundle["plan_result"]
    steps  = plan.get("step_results", {}) or {}
    extr   = steps.get("step2_extraction", {})
    intent = (steps.get("step1_intent") or {}).get("intent") or plan.get("intent", "—")

    candidate_models = extr.get("candidate_models") or ui.get("selected_tables") or []
    retrieval_score  = round(float(plan.get("final_confidence") or 0.0), 2)
    join_conf        = round(float(ui.get("join_confidence") or 0.0), 2)
    gov_status       = "blocked" if ui.get("governance_flags", {}).get("blocked") else "clear"
    final_decision   = ui["decision"]

    summary_lines = [
        ("Intent",           intent),
        ("Candidate Models", ", ".join(candidate_models) if candidate_models else "none"),
        ("Retrieval Score",  retrieval_score),
        ("Join Confidence",  join_conf),
        ("Governance",       gov_status),
        ("Final Decision",   final_decision),
    ]

    col_info, col_dl = st.columns([3, 1])
    with col_info:
        for label, value in summary_lines:
            st.markdown(f"**{label}:** {value}")
    with col_dl:
        try:
            full_json = json.dumps(bundle, indent=2, default=str)
        except Exception:
            full_json = "{}"
        st.download_button(
            label="⬇ Download Full JSON",
            data=full_json,
            file_name="debug_trace.json",
            mime="application/json",
            use_container_width=True,
        )


# ── System Decision Summary ───────────────────────────────────────────────────

def _render_decision_summary(ui: dict, classification: dict) -> None:
    """
    Plain-language explanation of what the reasoning engine determined —
    one bullet per decision point.  Makes the system feel explainable,
    not opaque.
    """
    decision     = ui["decision"]
    refusal_type = ui.get("refusal_type")
    candidates   = ui.get("selected_tables") or []
    gov_blocked  = ui.get("governance_flags", {}).get("blocked", False)
    join_path    = ui.get("join_path", "")
    join_ok      = join_path and join_path not in ("not evaluated", "—", "")

    bullets: list[str] = []

    # Metadata resolution
    if candidates:
        bullets.append(f"metadata resolution succeeded — matched **{', '.join(candidates)}**")
    else:
        bullets.append("no metadata entities could be resolved from the query")

    # Governance
    if refusal_type == "GOVERNANCE_BLOCKED" or gov_blocked:
        bullets.append("a **governance violation** was detected — query access is blocked")
    else:
        bullets.append("no governance violations were detected")

    # Semantic / schema issues
    if refusal_type == "SEMANTIC_CONFLICT":
        bullets.append("a **semantic conflict** exists — multiple metric definitions match equally")
    elif refusal_type == "INSUFFICIENT_SCHEMA":
        bullets.append("no recognised schema entities could be found for this query")
    elif refusal_type == "WEAK_JOIN":
        bullets.append("no valid join path exists between the required models")
    elif refusal_type == "TEMPORAL_AMBIGUITY":
        bullets.append("multiple date columns exist — a date filter must be specified")
    elif refusal_type not in {"GOVERNANCE_BLOCKED", "UNSAFE_QUERY"} and not refusal_type:
        if join_ok:
            bullets.append(f"join path resolved — {join_path}")
        bullets.append("no semantic ambiguity was detected")

    # Final outcome
    if decision == "SQL_GENERATED":
        bullets.append("SQL generation was **approved**")
    elif refusal_type == "UNSAFE_QUERY":
        bullets.append("the query was **blocked** — DML/DDL or destructive pattern detected")
    else:
        bullets.append("SQL generation was **refused** — clarification is required before proceeding")

    st.markdown("**The system determined that:**")
    for b in bullets:
        st.markdown(f"- {b}")


# ── Main reasoning render ─────────────────────────────────────────────────────

def _render_reasoning(bundle: dict) -> None:
    ui             = bundle["ui_state"]
    classification = bundle["classification"]

    # 1. Top summary banner — immediate visual outcome
    _render_top_banner(ui, classification)

    # 2. Quick summary row (decision badge, confidence bar, failure type)
    _render_summary_row(ui, classification)

    # 3. Pipeline step indicators
    _render_pipeline(bundle)

    st.divider()

    left, right = st.columns([1.35, 1])

    with left:
        # SQL — syntax highlighted
        st.subheader("Generated SQL")
        if ui["sql"]:
            st.code(ui["sql"], language="sql")
        else:
            st.code("-- No SQL generated for this query.", language="sql")

        st.subheader("System Decision Summary")
        _render_decision_summary(ui, classification)
        if ui.get("explanation_text"):
            st.caption(ui["explanation_text"])

        st.subheader("Join Path")
        st.write(ui["join_path"] or "—")
        st.caption(f"Join confidence: {ui['join_confidence']:.2f}")

        # Retrieved metadata table
        st.subheader("Retrieved Metadata")
        rows = _flatten_metadata_rows(ui)
        if rows:
            st.table(pd.DataFrame(rows))
        else:
            st.write("No grounded metadata entities were retrieved.")

        # Composite retrieval scores table
        table = _retrieval_table(ui)
        if not table.empty:
            st.subheader("Composite Retrieval Scores")
            st.table(table)

    with right:
        # Confidence breakdown — inline bars
        _render_confidence_breakdown(ui)

        st.divider()

        # Governance — horizontal badges
        _render_governance(ui)

        st.divider()

        # Decision record
        st.subheader("Decision Record")
        st.table(_decision_record(ui, classification))

        # Warnings
        warnings = ui.get("warnings", []) or []
        if warnings:
            st.subheader("Warnings")
            for w in warnings:
                st.warning(w)

    # 4. Compact debug trace (collapsed by default)
    with st.expander("Advanced Debug Trace"):
        _render_debug_trace(bundle)


# ── App entry point ───────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon="🧭",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    if "demo_query" not in st.session_state:
        st.session_state["demo_query"] = SAMPLE_QUERIES["Answerable Query"]

    _inject_styles()

    st.title(APP_TITLE)
    st.caption(APP_SUBTITLE)

    st.markdown(
        "This page is intentionally a **reasoning demo**, not a dashboard. "
        "It shows how the system grounds metadata, validates joins and governance, "
        "and decides whether to generate SQL, refuse, or block — *before* calling an LLM."
    )

    # Sample query quick-launch buttons
    sample_cols = st.columns(4)
    for col, (label, query) in zip(sample_cols, SAMPLE_QUERIES.items()):
        with col:
            if st.button(label, use_container_width=True):
                _set_query(query)

    # Query input
    with st.container(border=True):
        st.markdown("**Natural Language Question**")
        query = st.text_area(
            label="Query",
            label_visibility="collapsed",
            key="demo_query",
            height=100,
        )

        control_cols = st.columns([1.2, 1, 2])
        with control_cols[0]:
            run_query = st.button(
                "▶  Run Query Reasoning",
                type="primary",
                use_container_width=True,
            )
        with control_cols[1]:
            role = st.selectbox(
                "Role",
                ["analyst", "finance_user", "support_user", "executive"],
                index=0,
            )

    if run_query:
        with st.spinner("Running reasoning pipeline…"):
            planner, generator, refusal_engine = load_demo_components(user_role=role)
            bundle = build_response_bundle(query, planner, generator, refusal_engine)
        _render_reasoning(bundle)


if __name__ == "__main__":
    main()
