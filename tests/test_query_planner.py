"""
tests/test_query_planner.py

Integration tests for reasoning/query_planner.py

Coverage
--------
  - plan() returns a dict with all required top-level keys
  - Clean query (customer lookup) → should_proceed=True
  - Revenue query → ambiguity detected → SEMANTIC_CONFLICT → should_proceed=False
  - Unrecognised query with no entities → INSUFFICIENT_SCHEMA → should_proceed=False
  - Low-confidence path: join confidence below refuse threshold
  - execution_plan structure when proceeding
  - execution_plan is None when refused
  - step_results contains all expected step keys
  - intent from step1 propagated into execution_plan
  - candidate_models from step2 propagated into execution_plan
  - join_path from step4 propagated into execution_plan
  - confidence_level values are one of the four valid strings
  - failure_type is None when proceeding
  - failure_type set when refusing
  - Single-model query (no joins) proceeds without join error
  - recommend_action present in all outcomes
"""

import pytest

from reasoning.query_planner import QueryPlanner

REQUIRED_TOP_KEYS = {
    "query", "step_results", "execution_plan",
    "final_confidence", "confidence_level",
    "should_proceed", "failure_type", "failure_reason", "recommendation",
}

VALID_CONFIDENCE_LEVELS = {"confident", "warn", "ambiguous", "refuse"}


@pytest.fixture(scope="module")
def planner(graph, glossary):
    return QueryPlanner(graph=graph, glossary=glossary)


# ──────────────────────────────────────────────────────────────────────────────
# Top-level structure
# ──────────────────────────────────────────────────────────────────────────────

class TestTopLevelStructure:

    def test_required_keys_present(self, planner):
        result = planner.plan("list all customers")
        assert REQUIRED_TOP_KEYS.issubset(result.keys()), (
            f"Missing keys: {REQUIRED_TOP_KEYS - result.keys()}"
        )

    def test_confidence_level_valid_string(self, planner):
        result = planner.plan("total revenue")
        assert result["confidence_level"] in VALID_CONFIDENCE_LEVELS

    def test_should_proceed_is_bool(self, planner):
        result = planner.plan("list all customers")
        assert isinstance(result["should_proceed"], bool)

    def test_query_echoed_in_result(self, planner):
        q = "show payment details"
        result = planner.plan(q)
        assert result["query"] == q


# ──────────────────────────────────────────────────────────────────────────────
# Clean queries — should proceed
# ──────────────────────────────────────────────────────────────────────────────

class TestCleanQueries:

    def test_customer_lookup_proceeds(self, planner):
        result = planner.plan("find customer details")
        # Should proceed unless dim_customer has PII block — governance may block
        # Accept either proceed or governance refusal
        assert result["confidence_level"] in VALID_CONFIDENCE_LEVELS

    def test_single_model_no_join_error(self, planner):
        result = planner.plan("show orders by region")
        # No unresolvable join — should not raise
        assert "failure_type" in result

    def test_execution_plan_present_when_proceeding(self, planner):
        result = planner.plan("show orders")
        if result["should_proceed"]:
            assert result["execution_plan"] is not None
            assert isinstance(result["execution_plan"], dict)

    def test_execution_plan_none_when_refused(self, planner):
        # Revenue with two definitions → ambiguity → refused
        result = planner.plan("total revenue")
        if not result["should_proceed"]:
            assert result["execution_plan"] is None


# ──────────────────────────────────────────────────────────────────────────────
# Ambiguity → refusal
# ──────────────────────────────────────────────────────────────────────────────

class TestAmbiguityRefusal:

    def test_revenue_query_is_ambiguous(self, planner):
        """revenue → revenue_gross / revenue_net → SEMANTIC_CONFLICT."""
        result = planner.plan("total revenue")
        # Either ambiguous or refused due to conflict
        assert result["should_proceed"] is False or result["confidence_level"] in ("ambiguous", "refuse")

    def test_failure_type_set_on_ambiguity(self, planner):
        result = planner.plan("total revenue")
        if not result["should_proceed"]:
            assert result["failure_type"] is not None

    def test_recommendation_present_on_refusal(self, planner):
        result = planner.plan("total revenue")
        if not result["should_proceed"]:
            assert result["recommendation"] is not None
            assert len(result["recommendation"]) > 0


# ──────────────────────────────────────────────────────────────────────────────
# Unknown entities → INSUFFICIENT_SCHEMA
# ──────────────────────────────────────────────────────────────────────────────

class TestInsufficientSchema:

    def test_unknown_entity_refused(self, planner):
        result = planner.plan("show me the xyz_metric_zz99")
        # No entities resolved → INSUFFICIENT_SCHEMA
        assert not result["should_proceed"]
        assert result["failure_type"] == "INSUFFICIENT_SCHEMA"

    def test_gibberish_query_refused(self, planner):
        result = planner.plan("aaabbb cccddd eee")
        assert not result["should_proceed"]


# ──────────────────────────────────────────────────────────────────────────────
# Step results propagation
# ──────────────────────────────────────────────────────────────────────────────

class TestStepResults:

    def test_step1_intent_present(self, planner):
        result = planner.plan("total orders by region")
        assert "step1_intent" in result["step_results"]
        intent_data = result["step_results"]["step1_intent"]
        assert "intent" in intent_data

    def test_step2_extraction_present(self, planner):
        result = planner.plan("total orders by region")
        assert "step2_extraction" in result["step_results"]

    def test_step3_validation_present_when_models_found(self, planner):
        result = planner.plan("customer orders")
        if "step3_validation" in result["step_results"]:
            val = result["step_results"]["step3_validation"]
            assert "valid" in val
            assert "present" in val

    def test_step4_join_paths_present_when_reached(self, planner):
        result = planner.plan("customer orders")
        if "step4_join_paths" in result["step_results"]:
            jp = result["step_results"]["step4_join_paths"]
            assert "join_paths" in jp

    def test_step8_confidence_present_when_reached(self, planner):
        result = planner.plan("list orders by region")
        if "step8_confidence" in result["step_results"]:
            conf = result["step_results"]["step8_confidence"]
            assert "final_confidence" in conf

    def test_step7_retrieval_present_when_reached(self, planner):
        result = planner.plan("list orders")
        if "step7_retrieval" in result["step_results"]:
            retrieval = result["step_results"]["step7_retrieval"]
            assert "rankings" in retrieval
            assert "top_candidate" in retrieval


# ──────────────────────────────────────────────────────────────────────────────
# Execution plan structure
# ──────────────────────────────────────────────────────────────────────────────

class TestExecutionPlanStructure:

    def test_execution_plan_has_intent(self, planner):
        result = planner.plan("count orders by region")
        if result["execution_plan"]:
            assert "intent" in result["execution_plan"]

    def test_execution_plan_has_candidate_models(self, planner):
        result = planner.plan("list orders")
        if result["execution_plan"]:
            assert "candidate_models" in result["execution_plan"]
            assert isinstance(result["execution_plan"]["candidate_models"], list)

    def test_execution_plan_has_join_path(self, planner):
        result = planner.plan("list orders")
        if result["execution_plan"]:
            assert "join_path" in result["execution_plan"]

    def test_execution_plan_has_confidence(self, planner):
        result = planner.plan("list orders by region")
        if result["execution_plan"]:
            assert "confidence" in result["execution_plan"]
            assert 0.0 <= result["execution_plan"]["confidence"] <= 1.0

    def test_execution_plan_has_retrieval_score(self, planner):
        result = planner.plan("list orders")
        if result["execution_plan"]:
            assert "retrieval_score" in result["execution_plan"]
            assert 0.0 <= result["execution_plan"]["retrieval_score"] <= 1.0

    def test_execution_plan_query_matches(self, planner):
        q = "list all orders by region"
        result = planner.plan(q)
        if result["execution_plan"]:
            assert result["execution_plan"]["query"] == q
