"""
tests/test_explainability_formatter.py

Phase 6 coverage for structured and human-readable explanations.
"""

import pytest

from explainability.formatter import ExplainabilityFormatter
from generation.sql_generator import SqlGenerator
from reasoning.query_planner import QueryPlanner


@pytest.fixture(scope="module")
def planner(graph, glossary):
    return QueryPlanner(graph=graph, glossary=glossary)


@pytest.fixture(scope="module")
def formatter():
    return ExplainabilityFormatter()


class TestPlannerExplainability:

    def test_success_plan_contains_all_explanation_blocks(self, planner):
        result = planner.plan("list all segments")

        assert "explanations" in result
        assert "explanation_text" in result

        explanations = result["explanations"]
        assert "retrieval_explanation" in explanations
        assert "join_explanation" in explanations
        assert "confidence_explanation" in explanations
        assert "refusal_explanation" in explanations

        if result["execution_plan"]:
            plan = result["execution_plan"]
            assert "retrieval_explanation" in plan
            assert "join_explanation" in plan
            assert "confidence_explanation" in plan
            assert "refusal_explanation" in plan
            assert plan["refusal_explanation"]["status"] == "clear"

    def test_failure_plan_keeps_refusal_explanation_without_execution_plan(self, planner):
        result = planner.plan("show all payments")

        assert result["failure_type"] == "GOVERNANCE_BLOCKED"
        assert result["execution_plan"] is None
        assert result["explanations"]["refusal_explanation"]["status"] == "triggered"
        assert result["explanations"]["retrieval_explanation"]["status"] == "not_reached"
        assert result["explanations"]["join_explanation"]["status"] == "not_reached"


class TestFormatterOutput:

    def test_formatter_json_contains_flattened_summary_fields(self, planner, formatter):
        result = planner.plan("list all segments")
        payload = formatter.format_json(result)

        assert "selected_tables" in payload
        assert "retrieval_scores" in payload
        assert "join_path" in payload
        assert "join_confidence" in payload
        assert "confidence_limiting_factor" in payload
        assert "overall_confidence" in payload
        assert "explanation" in payload

    def test_formatter_text_mentions_failure_type_on_refusal(self, planner, formatter):
        result = planner.plan("show all payments")
        text = formatter.format_text(result)

        assert "GOVERNANCE_BLOCKED" in text
        assert len(text) > 0

    def test_sql_generator_propagates_explanation_json(self, planner):
        result = planner.plan("list all segments")
        generated = SqlGenerator().generate(result)

        assert "explanation_json" in generated
        assert generated["explanation_json"] is not None
        assert len(generated["explanation"]) > 0
