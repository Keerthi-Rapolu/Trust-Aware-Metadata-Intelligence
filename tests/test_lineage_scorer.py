"""
tests/test_lineage_scorer.py

Unit tests for retrieval/lineage_scorer.py

Coverage
--------
  - Cold-start default when no anchor models provided
  - Same-model anchor scores 1.0
  - 1-hop model scores 1.0
  - 2-hop model scores 0.70
  - No-path (disconnected) model scores 0.0
  - MAX is taken across multiple anchors
  - score_all returns {model: score} dict for all candidates
  - Node not in graph handled gracefully (returns 0.0)
"""

import pytest

from ingestion.graph_store import MetadataGraph
from retrieval.lineage_scorer import LineageScorer, _COLD_START, _NO_PATH


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def simple_graph():
    """
    Linear lineage chain:  node_a → node_b → node_c
    Plus an isolated node: node_x  (no edges)

    Hop distances:
      node_a ↔ node_b : 1 hop
      node_a ↔ node_c : 2 hops
      node_x → any    : no path
    """
    mg = MetadataGraph()
    mg.graph.add_edge("node_a", "node_b", edge_type="explicit_fk",
                      left_column="id", right_column="a_id")
    mg.graph.add_edge("node_b", "node_c", edge_type="lineage_dependency",
                      left_column=None, right_column=None)
    mg.graph.add_node("node_x")   # isolated
    return mg


@pytest.fixture(scope="module")
def scorer(simple_graph):
    return LineageScorer(simple_graph)


# ── Cold-start ───────────────────────────────────────────────────────────────

class TestColdStart:

    def test_none_anchors_returns_cold_start(self, scorer):
        assert scorer.score("node_a", None) == _COLD_START

    def test_empty_anchors_returns_cold_start(self, scorer):
        assert scorer.score("node_a", []) == _COLD_START

    def test_cold_start_value_is_0_50(self, scorer):
        assert _COLD_START == 0.50

    def test_cold_start_for_unknown_model(self, scorer):
        assert scorer.score("totally_unknown", None) == _COLD_START


# ── Exact same model ─────────────────────────────────────────────────────────

class TestSameModel:

    def test_same_model_as_anchor_scores_1(self, scorer):
        assert scorer.score("node_a", ["node_a"]) == 1.00

    def test_same_model_among_multiple_anchors(self, scorer):
        assert scorer.score("node_b", ["node_x", "node_b"]) == 1.00


# ── Hop scoring ──────────────────────────────────────────────────────────────

class TestHopScoring:

    def test_one_hop_scores_1(self, scorer):
        # node_a → node_b : 1 hop
        result = scorer.score("node_b", ["node_a"])
        assert result == 1.00

    def test_reverse_one_hop_scores_1(self, scorer):
        # node_b ← node_a : 1 hop (both directions tried)
        result = scorer.score("node_a", ["node_b"])
        assert result == 1.00

    def test_two_hops_scores_0_70(self, scorer):
        # node_a → node_b → node_c : 2 hops
        result = scorer.score("node_c", ["node_a"])
        assert result == pytest.approx(0.70)

    def test_no_path_scores_0(self, scorer):
        # node_x is isolated; no path to node_a
        result = scorer.score("node_x", ["node_a"])
        assert result == _NO_PATH

    def test_disconnected_candidate_scores_0(self, scorer):
        result = scorer.score("node_a", ["node_x"])
        assert result == _NO_PATH


# ── Multiple anchors — MAX semantics ─────────────────────────────────────────

class TestMultipleAnchors:

    def test_max_of_two_anchors(self, scorer):
        # node_c:
        #   anchor node_b → 1 hop → 1.00
        #   anchor node_x → no path → 0.00
        # MAX = 1.00
        result = scorer.score("node_c", ["node_b", "node_x"])
        assert result == 1.00

    def test_better_anchor_wins(self, scorer):
        # node_c:
        #   anchor node_a → 2 hops → 0.70
        #   anchor node_b → 1 hop  → 1.00
        result = scorer.score("node_c", ["node_a", "node_b"])
        assert result == 1.00

    def test_all_disconnected_anchors_returns_0(self, scorer):
        result = scorer.score("node_a", ["node_x"])
        assert result == _NO_PATH


# ── score_all ────────────────────────────────────────────────────────────────

class TestScoreAll:

    def test_returns_dict_for_all_candidates(self, scorer):
        result = scorer.score_all(["node_a", "node_b", "node_c"])
        assert set(result.keys()) == {"node_a", "node_b", "node_c"}

    def test_score_all_cold_start(self, scorer):
        result = scorer.score_all(["node_a", "node_b"], anchor_models=None)
        assert all(v == _COLD_START for v in result.values())

    def test_score_all_with_anchor(self, scorer):
        result = scorer.score_all(["node_a", "node_c"], anchor_models=["node_b"])
        assert result["node_a"] == 1.00     # 1 hop from node_b
        assert result["node_c"] == 1.00     # 1 hop from node_b

    def test_score_all_empty_candidates(self, scorer):
        result = scorer.score_all([], anchor_models=["node_a"])
        assert result == {}


# ── Sample manifest integration ──────────────────────────────────────────────

class TestWithSampleGraph:
    """
    Verify lineage_scorer works correctly on the actual sample_manifest graph
    (dim_customer → fct_orders → payment_events).
    """

    def test_fct_orders_one_hop_from_dim_customer(self, graph):
        """fct_orders depends_on dim_customer → 1 hop."""
        scorer = LineageScorer(graph)
        result = scorer.score("fct_orders", ["dim_customer"])
        assert result == 1.00

    def test_payment_events_one_hop_from_fct_orders(self, graph):
        scorer = LineageScorer(graph)
        result = scorer.score("payment_events", ["fct_orders"])
        assert result == 1.00

    def test_payment_events_two_hops_from_dim_customer(self, graph):
        scorer = LineageScorer(graph)
        result = scorer.score("payment_events", ["dim_customer"])
        assert result == pytest.approx(0.70)

    def test_dim_customer_not_reachable_from_payment_events_direct(self, graph):
        """
        payment_events depends_on fct_orders (FK).  fct_orders depends_on
        dim_customer.  get_shortest_path tries both directions, so it will
        find the path dim_customer → fct_orders → payment_events (2 hops).
        """
        scorer = LineageScorer(graph)
        result = scorer.score("dim_customer", ["payment_events"])
        # Path exists in reverse direction → 2 hops
        assert result == pytest.approx(0.70)
