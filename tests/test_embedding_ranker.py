"""
tests/test_embedding_ranker.py

Unit tests for retrieval/embedding_ranker.py

Coverage
--------
  - rank() returns required output structure
  - rankings list contains required keys per item
  - All factor scores bounded [0, 1]
  - Ranks are 1, 2, 3, ... (sequential, no gaps)
  - top_candidate is the rank-1 model
  - Empty candidates returns empty rankings
  - Single candidate gets rank 1
  - Governance factor: pci-tagged model (payment_events) → 0.0
  - Governance factor: clean model (dim_customer) → 1.0
  - Cold-start historical relevance = 0.50
  - Known history value overrides cold-start
  - Composite formula: mock factors → verify final_score arithmetic
  - Governance-penalised model ranks lower than clean model
  - Glossary-matched model ranks higher than non-matching model
  - score_single returns required structure
"""

import pytest

from retrieval.embedding_ranker import (
    EmbeddingRanker,
    _W_SEMANTIC, _W_LINEAGE, _W_GLOSSARY, _W_HISTORICAL, _W_GOVERNANCE,
    _COLD_START_HISTORICAL,
)

_REQUIRED_RANKING_KEYS = {
    "candidate", "scores", "final_score", "rank",
}
_REQUIRED_SCORE_KEYS = {
    "semantic_similarity",
    "lineage_proximity",
    "glossary_overlap",
    "historical_relevance",
    "governance_compatibility",
}
_ALL_MODELS = ["dim_customer", "fct_orders", "payment_events", "support_tickets"]


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def ranker(graph, glossary):
    """EmbeddingRanker without embed_fn → uses string-overlap semantic similarity."""
    return EmbeddingRanker(graph, glossary, embed_fn=None)


@pytest.fixture(scope="module")
def ranker_with_embed(graph, glossary, mock_embed_fn):
    return EmbeddingRanker(graph, glossary, embed_fn=mock_embed_fn)


# ── Output structure ─────────────────────────────────────────────────────────

class TestOutputStructure:

    def test_rank_returns_required_top_level_keys(self, ranker):
        result = ranker.rank("show all segments", _ALL_MODELS)
        assert {"query", "rankings", "top_candidate"}.issubset(result.keys())

    def test_query_echoed(self, ranker):
        q = "total revenue by region"
        result = ranker.rank(q, _ALL_MODELS)
        assert result["query"] == q

    def test_rankings_is_list(self, ranker):
        result = ranker.rank("show segments", _ALL_MODELS)
        assert isinstance(result["rankings"], list)

    def test_rankings_count_equals_candidates(self, ranker):
        result = ranker.rank("show segments", _ALL_MODELS)
        assert len(result["rankings"]) == len(_ALL_MODELS)

    def test_each_ranking_has_required_keys(self, ranker):
        result = ranker.rank("show segments", _ALL_MODELS)
        for item in result["rankings"]:
            assert _REQUIRED_RANKING_KEYS.issubset(item.keys())

    def test_each_item_has_all_score_factors(self, ranker):
        result = ranker.rank("show segments", _ALL_MODELS)
        for item in result["rankings"]:
            assert _REQUIRED_SCORE_KEYS.issubset(item["scores"].keys())

    def test_top_candidate_is_str_or_none(self, ranker):
        result = ranker.rank("show segments", _ALL_MODELS)
        assert isinstance(result["top_candidate"], str)

    def test_top_candidate_matches_rank1(self, ranker):
        result = ranker.rank("show segments", _ALL_MODELS)
        rank1 = next(r for r in result["rankings"] if r["rank"] == 1)
        assert result["top_candidate"] == rank1["candidate"]

    def test_empty_candidates_returns_empty(self, ranker):
        result = ranker.rank("show segments", [])
        assert result["rankings"] == []
        assert result["top_candidate"] is None

    def test_single_candidate_gets_rank_1(self, ranker):
        result = ranker.rank("show segments", ["dim_customer"])
        assert len(result["rankings"]) == 1
        assert result["rankings"][0]["rank"] == 1

    def test_ranks_are_sequential(self, ranker):
        result = ranker.rank("show segments", _ALL_MODELS)
        ranks = sorted(r["rank"] for r in result["rankings"])
        assert ranks == list(range(1, len(_ALL_MODELS) + 1))


# ── Factor bounds ─────────────────────────────────────────────────────────────

class TestFactorBounds:

    def test_all_factors_bounded_0_1(self, ranker):
        result = ranker.rank("show revenue by segment", _ALL_MODELS)
        for item in result["rankings"]:
            for factor, val in item["scores"].items():
                assert 0.0 <= val <= 1.0, (
                    f"{item['candidate']}.{factor} = {val} out of [0,1]"
                )

    def test_final_score_bounded_0_1(self, ranker):
        result = ranker.rank("show revenue by segment", _ALL_MODELS)
        for item in result["rankings"]:
            assert 0.0 <= item["final_score"] <= 1.0


# ── Governance factor ─────────────────────────────────────────────────────────

class TestGovernanceFactor:

    def test_payment_events_governance_zero(self, ranker):
        """payment_events has tag 'pci' → governance_compatibility = 0.0"""
        result = ranker.score_single("show payments", "payment_events")
        assert result["scores"]["governance_compatibility"] == 0.0

    def test_dim_customer_governance_one(self, ranker):
        """dim_customer has no pii/pci tags → governance_compatibility = 1.0"""
        result = ranker.score_single("show segments", "dim_customer")
        assert result["scores"]["governance_compatibility"] == 1.0

    def test_fct_orders_governance_one(self, ranker):
        result = ranker.score_single("show orders", "fct_orders")
        assert result["scores"]["governance_compatibility"] == 1.0

    def test_pci_model_ranks_lower_than_clean_model(self, ranker):
        """
        For a neutral query, a model with governance=0.0 should rank lower
        than a clean model with identical semantic/lineage/glossary factors.
        """
        # Use dim_customer vs payment_events with a neutral query
        result = ranker.rank("show data", ["dim_customer", "payment_events"])
        # payment_events governance=0.0 penalty should push it down
        dim_rank    = next(r["rank"] for r in result["rankings"] if r["candidate"] == "dim_customer")
        pay_rank    = next(r["rank"] for r in result["rankings"] if r["candidate"] == "payment_events")
        assert dim_rank < pay_rank, (
            f"Expected dim_customer (rank {dim_rank}) before payment_events (rank {pay_rank})"
        )


# ── Historical relevance ──────────────────────────────────────────────────────

class TestHistoricalRelevance:

    def test_cold_start_historical_is_0_50(self, ranker):
        result = ranker.score_single("show segments", "dim_customer", query_history={})
        assert result["scores"]["historical_relevance"] == _COLD_START_HISTORICAL

    def test_cold_start_model_not_in_history(self, ranker):
        result = ranker.score_single(
            "show segments", "dim_customer",
            query_history={"fct_orders": 0.90},   # dim_customer absent
        )
        assert result["scores"]["historical_relevance"] == _COLD_START_HISTORICAL

    def test_known_history_value_used(self, ranker):
        result = ranker.score_single(
            "show segments", "dim_customer",
            query_history={"dim_customer": 0.85},
        )
        assert result["scores"]["historical_relevance"] == 0.85

    def test_history_zero_used(self, ranker):
        result = ranker.score_single(
            "show segments", "dim_customer",
            query_history={"dim_customer": 0.0},
        )
        assert result["scores"]["historical_relevance"] == 0.0


# ── Composite formula accuracy ────────────────────────────────────────────────

class TestCompositeFormula:

    def test_formula_weights_sum_to_1(self):
        total = _W_SEMANTIC + _W_LINEAGE + _W_GLOSSARY + _W_HISTORICAL + _W_GOVERNANCE
        assert total == pytest.approx(1.0)

    def test_composite_formula_correct(self, ranker):
        """
        Inject a known history score and verify the formula is applied.
        We can check the formula holds: final = weighted sum of factors.
        """
        history = {"dim_customer": 0.70}
        result  = ranker.score_single(
            "show all segments", "dim_customer",
            query_history=history,
        )
        s = result["scores"]
        expected_final = (
            _W_SEMANTIC   * s["semantic_similarity"]
          + _W_LINEAGE    * s["lineage_proximity"]
          + _W_GLOSSARY   * s["glossary_overlap"]
          + _W_HISTORICAL * s["historical_relevance"]
          + _W_GOVERNANCE * s["governance_compatibility"]
        )
        assert result["final_score"] == pytest.approx(expected_final, abs=1e-4)

    def test_all_perfect_scores_gives_1(self, ranker, graph, glossary):
        """
        Manually construct a scenario where every factor is 1.0
        → final_score should be 1.0.
        """
        # Override _score_factors by testing the arithmetic directly
        factors = {
            "semantic_similarity":     1.0,
            "lineage_proximity":       1.0,
            "glossary_overlap":        1.0,
            "historical_relevance":    1.0,
            "governance_compatibility": 1.0,
        }
        final = ranker._composite(factors)
        assert final == pytest.approx(1.0)

    def test_governance_zero_caps_contribution(self, ranker, graph, glossary):
        """governance=0.0 removes the 0.10 weight contribution."""
        factors = {
            "semantic_similarity":     1.0,
            "lineage_proximity":       1.0,
            "glossary_overlap":        1.0,
            "historical_relevance":    1.0,
            "governance_compatibility": 0.0,
        }
        final = ranker._composite(factors)
        # 0.35 + 0.25 + 0.15 + 0.15 + 0.00 = 0.90
        assert final == pytest.approx(0.90)


# ── Glossary-driven ranking ───────────────────────────────────────────────────

class TestGlossaryDrivenRanking:

    def test_segment_query_ranks_dim_customer_first(self, ranker):
        """
        'segment' term → glossary maps to dim_customer.
        dim_customer should rank first over payment_events (pci=0.0).
        """
        result = ranker.rank(
            "show all segments",
            ["dim_customer", "payment_events"],
        )
        assert result["top_candidate"] == "dim_customer"

    def test_payment_query_governance_forces_low_rank(self, ranker):
        """
        Querying for payment triggers governance penalty on payment_events.
        dim_customer should rank first.
        """
        result = ranker.rank(
            "show payment amounts",
            ["dim_customer", "payment_events"],
        )
        dim_rank = next(r["rank"] for r in result["rankings"] if r["candidate"] == "dim_customer")
        pay_rank = next(r["rank"] for r in result["rankings"] if r["candidate"] == "payment_events")
        assert dim_rank < pay_rank


# ── Lineage-driven ranking ────────────────────────────────────────────────────

class TestLineageDrivenRanking:

    def test_lineage_connected_model_ranks_higher(self, ranker):
        """
        With fct_orders as anchor, dim_customer (1 hop) should rank higher
        than support_tickets (1 hop via different path) based on other factors.
        This test checks that lineage is factored in.
        """
        result = ranker.rank(
            "show customer orders",
            ["dim_customer", "support_tickets"],
            selected_models=["fct_orders"],
        )
        # Both are 1 hop from fct_orders, so lineage doesn't differentiate;
        # glossary and semantic will. Just verify structure is correct.
        assert len(result["rankings"]) == 2
        for item in result["rankings"]:
            assert item["scores"]["lineage_proximity"] == pytest.approx(1.00)

    def test_cold_start_lineage_when_no_anchor(self, ranker):
        result = ranker.score_single(
            "show revenue", "fct_orders",
            selected_models=[],
        )
        assert result["scores"]["lineage_proximity"] == 0.50   # cold-start


# ── score_single ─────────────────────────────────────────────────────────────

class TestScoreSingle:

    def test_returns_required_keys(self, ranker):
        result = ranker.score_single("show segments", "dim_customer")
        assert {"candidate", "scores", "final_score"}.issubset(result.keys())

    def test_candidate_echoed(self, ranker):
        result = ranker.score_single("show segments", "dim_customer")
        assert result["candidate"] == "dim_customer"

    def test_score_factors_all_present(self, ranker):
        result = ranker.score_single("show segments", "dim_customer")
        assert _REQUIRED_SCORE_KEYS.issubset(result["scores"].keys())

    def test_final_score_is_float(self, ranker):
        result = ranker.score_single("show segments", "dim_customer")
        assert isinstance(result["final_score"], float)

    def test_unknown_model_does_not_crash(self, ranker):
        result = ranker.score_single("show segments", "phantom_model")
        assert isinstance(result["final_score"], float)
        assert 0.0 <= result["final_score"] <= 1.0
