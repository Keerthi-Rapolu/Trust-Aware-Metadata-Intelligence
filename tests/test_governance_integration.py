"""
tests/test_governance_integration.py

Integration tests for Phase 5 governance behavior in QueryPlanner.
"""

import pytest

from generation.sql_generator import SqlGenerator
from reasoning.query_planner import QueryPlanner


@pytest.fixture(scope="module")
def planner(graph, glossary):
    return QueryPlanner(graph=graph, glossary=glossary)


class TestPlannerGovernance:

    def test_governance_blocks_payment_query(self, planner):
        result = planner.plan("show all payments")
        assert result["should_proceed"] is False
        assert result["failure_type"] == "GOVERNANCE_BLOCKED"
        assert result["execution_plan"] is None

    def test_governance_fires_before_ambiguity(self, planner):
        result = planner.plan("payment revenue analysis")
        assert result["failure_type"] == "GOVERNANCE_BLOCKED"
        assert "step5_ambiguity" not in result["step_results"]

    def test_governance_step_contains_module_breakdown(self, planner):
        result = planner.plan("show all payments")
        governance = result["step_results"]["step6_governance"]
        assert "module_results" in governance
        assert {"pii", "rbac", "cost"} == set(governance["module_results"].keys())

    def test_sql_generator_refuses_governance_blocked_plan(self, planner):
        plan_result = planner.plan("show all payments")
        generated = SqlGenerator().generate(plan_result)
        assert generated["mode"] == "refused"
        assert generated["failure_type"] == "GOVERNANCE_BLOCKED"
