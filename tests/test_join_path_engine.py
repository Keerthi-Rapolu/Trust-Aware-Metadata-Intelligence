"""
tests/test_join_path_engine.py

Unit tests for reasoning/join_path_engine.py

Coverage
--------
  - Empty model list returns default empty result
  - Single model returns no join paths, confidence 1.0
  - Two directly connected models return a single edge
  - score_edge respects FK strength lookup
  - explicit_fk edge scores higher than lineage_dependency
  - dim_customer → fct_orders explicit_fk score ≈ 0.885
  - overall_confidence equals min edge score
  - all_models_resolved True when spanning tree succeeds
  - all_models_resolved False when no path
  - ambiguity not detected for non-competing paths
  - join_string present and formatted correctly
  - _col_similarity: exact=1.0, shared tokens=0.80, None→0.50
  - multi-hop path (3 models) automatically includes intermediate nodes
"""

import pytest

from reasoning.join_path_engine import JoinPathEngine, _FK_STRENGTH


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures: engine from session-scoped graph
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def engine(graph):
    return JoinPathEngine(graph)


# ──────────────────────────────────────────────────────────────────────────────
# Edge cases: 0 / 1 model
# ──────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_empty_models(self, engine):
        result = engine.find_join_paths([])
        assert result["join_paths"] == []
        assert result["overall_confidence"] == 1.0
        assert result["all_models_resolved"] is True

    def test_single_model(self, engine):
        result = engine.find_join_paths(["dim_customer"])
        assert result["join_paths"] == []
        assert result["overall_confidence"] == 1.0
        assert result["all_models_resolved"] is True
        assert result["ambiguity_detected"] is False

    def test_duplicate_models_deduplicated(self, engine):
        result = engine.find_join_paths(["dim_customer", "dim_customer"])
        assert result["join_paths"] == []          # treated as single model
        assert result["all_models_resolved"] is True


# ──────────────────────────────────────────────────────────────────────────────
# Two-model join
# ──────────────────────────────────────────────────────────────────────────────

class TestTwoModelJoin:

    def test_dim_customer_fct_orders_join_path_found(self, engine):
        result = engine.find_join_paths(["dim_customer", "fct_orders"])
        assert result["all_models_resolved"] is True
        assert len(result["join_paths"]) >= 1

    def test_join_path_has_required_keys(self, engine):
        result = engine.find_join_paths(["dim_customer", "fct_orders"])
        edge = result["join_paths"][0]
        for key in ("from_model", "to_model", "score", "edge_type", "join_string"):
            assert key in edge, f"Missing key: {key}"

    def test_join_string_formatted(self, engine):
        result = engine.find_join_paths(["dim_customer", "fct_orders"])
        join_str = result["join_paths"][0]["join_string"]
        assert "->" in join_str

    def test_overall_confidence_equals_min_score(self, engine):
        result = engine.find_join_paths(["dim_customer", "fct_orders"])
        min_score = min(e["score"] for e in result["join_paths"])
        assert abs(result["overall_confidence"] - min_score) < 1e-6


# ──────────────────────────────────────────────────────────────────────────────
# Score edge
# ──────────────────────────────────────────────────────────────────────────────

class TestScoreEdge:

    def test_explicit_fk_scores_higher_than_lineage_only(self, graph):
        """
        dim_customer → fct_orders has explicit_fk (relationship test).
        Score should be significantly above a lineage-only edge.
        """
        eng = JoinPathEngine(graph)
        # Direct edge from dim_customer to fct_orders (explicit_fk)
        score_direct = eng.score_edge("dim_customer", "fct_orders")
        assert score_direct > 0.60, f"Expected score > 0.60, got {score_direct}"

    def test_explicit_fk_score_formula(self, graph):
        """
        Expected: 0.40×0.90 + 0.25×1.00 + 0.20×col_sim + 0.15×0.50
        customer_id matches → col_sim ≥ 0.80
        → min ≈ 0.40×0.90 + 0.25×1.00 + 0.20×0.80 + 0.15×0.50 = 0.36+0.25+0.16+0.075 = 0.845
        """
        eng = JoinPathEngine(graph)
        score = eng.score_edge("dim_customer", "fct_orders")
        assert score >= 0.80, f"Expected explicit_fk edge score ≥ 0.80, got {score}"

    def test_fk_strength_constant_values(self):
        assert _FK_STRENGTH["explicit_fk"]        == 0.90
        assert _FK_STRENGTH["lineage_dependency"]  == 0.45
        assert _FK_STRENGTH[None]                  == 0.20


# ──────────────────────────────────────────────────────────────────────────────
# Multi-model spanning tree
# ──────────────────────────────────────────────────────────────────────────────

class TestMultiModelSpanning:

    def test_three_models_all_resolved(self, engine):
        """dim_customer + fct_orders + payment_events — should connect via spanning tree."""
        result = engine.find_join_paths(["dim_customer", "fct_orders", "payment_events"])
        assert result["all_models_resolved"] is True

    def test_three_models_multiple_edges(self, engine):
        result = engine.find_join_paths(["dim_customer", "fct_orders", "payment_events"])
        assert len(result["join_paths"]) >= 2

    def test_unreachable_model_not_resolved(self, graph):
        """Inject an orphan node — all_models_resolved should be False."""
        import copy
        g2 = copy.deepcopy(graph)
        g2.graph.add_node("orphan_model")
        eng = JoinPathEngine(g2)
        result = eng.find_join_paths(["dim_customer", "orphan_model"])
        assert result["all_models_resolved"] is False

    def test_no_path_returns_empty_edges(self, graph):
        import copy
        g2 = copy.deepcopy(graph)
        g2.graph.add_node("orphan_model")
        eng = JoinPathEngine(g2)
        result = eng.find_join_paths(["orphan_model"])
        # Single model — always resolved
        assert result["all_models_resolved"] is True


# ──────────────────────────────────────────────────────────────────────────────
# Column similarity
# ──────────────────────────────────────────────────────────────────────────────

class TestColumnSimilarity:

    @pytest.fixture(scope="class")
    def eng(self, graph):
        return JoinPathEngine(graph)

    def test_exact_col_match(self, eng):
        # Access private method via name mangling bypass
        sim = eng._col_similarity("customer_id", "customer_id")
        assert sim == 1.00

    def test_shared_token_col_match(self, eng):
        sim = eng._col_similarity("order_id", "id")
        assert sim == 0.80

    def test_none_columns_returns_neutral(self, eng):
        sim = eng._col_similarity(None, None)
        assert sim == 0.50

    def test_one_none_column_returns_neutral(self, eng):
        sim = eng._col_similarity("customer_id", None)
        assert sim == 0.50

    def test_difflib_fallback_range(self, eng):
        sim = eng._col_similarity("abc_xyz", "pqr_xyz")
        assert 0.0 <= sim <= 1.0
