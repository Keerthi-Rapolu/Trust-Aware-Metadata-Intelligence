"""
tests/test_confidence_scorer.py

Unit tests for reasoning/confidence_scorer.py

Coverage
--------
  - score() returns correct final_confidence using MIN formula
  - intent_clarity_weight is applied as multiplier
  - governance_score=0 → "refuse" regardless of other scores
  - final ≥ 0.80 → "confident"
  - 0.60 ≤ final < 0.80 → "warn"
  - 0.40 ≤ final < 0.60 → "ambiguous"
  - final < 0.40 → "refuse"
  - weakest_factor correctly identifies the MIN contributor
  - component_scores dict contains all five inputs
  - score_from_plan convenience wrapper works
  - aggregate_completeness returns mean of model completeness from graph
  - aggregate_completeness falls back to 1.0 when no completeness data
"""

import pytest

from reasoning.confidence_scorer import ConfidenceScorer


@pytest.fixture
def scorer():
    return ConfidenceScorer()


# ──────────────────────────────────────────────────────────────────────────────
# Core formula
# ──────────────────────────────────────────────────────────────────────────────

class TestCoreFormula:

    def test_high_all_scores_confident(self, scorer):
        result = scorer.score(0.90, 0.90, 1.00, 0.95, 1.00)
        assert result["final_confidence"] == pytest.approx(0.90, abs=1e-4)
        assert result["confidence_level"] == "confident"

    def test_min_is_applied(self, scorer):
        """MIN(0.90, 0.50, 1.00, 0.90) = 0.50 × 1.00 = 0.50."""
        result = scorer.score(0.90, 0.50, 1.00, 0.90, 1.00)
        assert result["final_confidence"] == pytest.approx(0.50, abs=1e-4)

    def test_intent_clarity_multiplies_min(self, scorer):
        """MIN = 0.80; clarity = 0.85 → final ≈ 0.68."""
        result = scorer.score(0.80, 0.80, 1.00, 0.80, 0.85)
        assert result["final_confidence"] == pytest.approx(0.80 * 0.85, abs=1e-4)

    def test_result_has_required_keys(self, scorer):
        result = scorer.score(0.8, 0.8, 1.0, 0.8, 1.0)
        for key in ("final_confidence", "confidence_level", "weakest_factor",
                    "component_scores", "recommendation"):
            assert key in result, f"Missing key: {key}"

    def test_component_scores_contains_all_inputs(self, scorer):
        result = scorer.score(0.80, 0.75, 0.90, 0.85, 0.85)
        cs = result["component_scores"]
        for k in ("retrieval", "join_path", "governance", "completeness", "intent_clarity"):
            assert k in cs


# ──────────────────────────────────────────────────────────────────────────────
# Confidence levels
# ──────────────────────────────────────────────────────────────────────────────

class TestConfidenceLevels:

    def test_confident_level(self, scorer):
        result = scorer.score(0.95, 0.95, 1.00, 0.95, 1.00)
        assert result["confidence_level"] == "confident"

    def test_warn_level(self, scorer):
        # MIN = 0.70, clarity = 1.0 → final = 0.70 → "warn"
        result = scorer.score(0.70, 0.70, 1.00, 0.70, 1.00)
        assert result["confidence_level"] == "warn"

    def test_ambiguous_level(self, scorer):
        # MIN = 0.50, clarity = 1.0 → final = 0.50 → "ambiguous"
        result = scorer.score(0.50, 0.50, 1.00, 0.50, 1.00)
        assert result["confidence_level"] == "ambiguous"

    def test_refuse_level_low_score(self, scorer):
        # MIN = 0.30 → "refuse"
        result = scorer.score(0.30, 0.30, 1.00, 0.30, 1.00)
        assert result["confidence_level"] == "refuse"

    def test_refuse_level_governance_zero(self, scorer):
        """governance_score=0 is always a hard refuse, regardless of other scores."""
        result = scorer.score(0.99, 0.99, 0.00, 0.99, 1.00)
        assert result["confidence_level"] == "refuse"
        assert "governance" in result["recommendation"].lower()

    def test_boundary_0_80_is_confident(self, scorer):
        result = scorer.score(0.80, 0.80, 1.00, 0.80, 1.00)
        assert result["confidence_level"] == "confident"

    def test_boundary_0_60_is_warn(self, scorer):
        result = scorer.score(0.60, 0.60, 1.00, 0.60, 1.00)
        assert result["confidence_level"] == "warn"

    def test_boundary_0_40_is_ambiguous(self, scorer):
        result = scorer.score(0.40, 0.40, 1.00, 0.40, 1.00)
        assert result["confidence_level"] == "ambiguous"


# ──────────────────────────────────────────────────────────────────────────────
# Weakest factor identification
# ──────────────────────────────────────────────────────────────────────────────

class TestWeakestFactor:

    def test_weakest_is_join_path(self, scorer):
        result = scorer.score(0.90, 0.50, 1.00, 0.90, 1.00)
        assert result["weakest_factor"] == "join_path"

    def test_weakest_is_retrieval(self, scorer):
        result = scorer.score(0.50, 0.90, 1.00, 0.90, 1.00)
        assert result["weakest_factor"] == "retrieval"

    def test_weakest_is_completeness(self, scorer):
        result = scorer.score(0.90, 0.90, 1.00, 0.40, 1.00)
        assert result["weakest_factor"] == "completeness"

    def test_weakest_is_governance(self, scorer):
        result = scorer.score(0.90, 0.90, 0.50, 0.90, 1.00)
        assert result["weakest_factor"] == "governance"


# ──────────────────────────────────────────────────────────────────────────────
# score_from_plan convenience wrapper
# ──────────────────────────────────────────────────────────────────────────────

class TestScoreFromPlan:

    def test_score_from_plan_defaults(self, scorer):
        """Empty plan → all defaults to 1.0 → confident."""
        result = scorer.score_from_plan({})
        assert result["confidence_level"] == "confident"
        assert result["final_confidence"] == pytest.approx(1.0, abs=1e-4)

    def test_score_from_plan_with_low_join(self, scorer):
        plan = {
            "retrieval_score":      0.90,
            "join_path_confidence": 0.45,
            "governance_score":     1.00,
            "completeness_score":   0.90,
            "intent_clarity_weight": 1.00,
        }
        result = scorer.score_from_plan(plan)
        assert result["final_confidence"] == pytest.approx(0.45, abs=1e-4)

    def test_score_from_plan_returns_dict(self, scorer):
        result = scorer.score_from_plan({"retrieval_score": 0.75})
        assert isinstance(result, dict)
        assert "final_confidence" in result


# ──────────────────────────────────────────────────────────────────────────────
# aggregate_completeness
# ──────────────────────────────────────────────────────────────────────────────

class TestAggregateCompleteness:

    def test_graph_models_have_completeness(self, scorer, graph):
        """dim_customer has all columns described → completeness should be 1.0."""
        result = scorer.aggregate_completeness(["dim_customer"], graph)
        assert 0.0 <= result <= 1.0

    def test_multi_model_average(self, scorer, graph):
        models = ["dim_customer", "fct_orders"]
        result = scorer.aggregate_completeness(models, graph)
        assert 0.0 <= result <= 1.0

    def test_unknown_model_falls_back_to_1(self, scorer, graph):
        """No completeness info → default 1.0."""
        result = scorer.aggregate_completeness(["nonexistent_model"], graph)
        assert result == 1.0

    def test_empty_model_list_returns_1(self, scorer, graph):
        result = scorer.aggregate_completeness([], graph)
        assert result == 1.0
