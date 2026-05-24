"""
tests/test_streamlit_app.py

Phase 6 coverage for frontend view-model helpers.
"""

import pytest

from frontend.streamlit_app import build_response_bundle
from generation.refusal_engine import RefusalEngine
from generation.sql_generator import SqlGenerator
from reasoning.query_planner import QueryPlanner


@pytest.fixture(scope="module")
def planner(graph, glossary):
    return QueryPlanner(graph=graph, glossary=glossary)


@pytest.fixture(scope="module")
def generator():
    return SqlGenerator()


@pytest.fixture(scope="module")
def refusal_engine():
    return RefusalEngine()


@pytest.mark.parametrize(
    "query,expected_failure",
    [
        ("show segment data", None),
        ("show revenue by region", "SEMANTIC_CONFLICT"),
        ("show all payments", "GOVERNANCE_BLOCKED"),
        ("DELETE all customers from the database", "UNSAFE_QUERY"),
    ],
)
def test_ui_state_handles_four_enterprise_scenarios(
    planner,
    generator,
    refusal_engine,
    query,
    expected_failure,
):
    bundle = build_response_bundle(query, planner, generator, refusal_engine)

    ui = bundle["ui_state"]
    classification = bundle["classification"]

    assert len(ui["explanation_text"]) > 0
    assert isinstance(ui["join_path"], str)
    assert 0.0 <= ui["confidence_score"] <= 1.0
    assert ui["decision"] in {"SQL_GENERATED", "REFUSED", "BLOCKED"}
    assert "governance_flags" in ui
    assert "retrieved_metadata" in ui

    if expected_failure is None:
        assert classification["status"] == "SUCCESS"
        assert classification["failure_type"] is None
        assert ui["show_refusal"] is False
        assert ui["decision"] == "SQL_GENERATED"
        assert ui["sql"] is not None
    else:
        assert classification["status"] == "FAILURE"
        assert classification["failure_type"] == expected_failure
        assert ui["show_refusal"] is True
        assert ui["refusal_type"] == expected_failure
        assert len(ui["refusal_reason"]) > 0

        if expected_failure in {"GOVERNANCE_BLOCKED", "UNSAFE_QUERY"}:
            assert ui["decision"] == "BLOCKED"
        else:
            assert ui["decision"] == "REFUSED"
