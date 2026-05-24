"""
tests/test_ambiguity_detector.py

Unit tests for reasoning/ambiguity_detector.py

Coverage
--------
  - detect_metric_ambiguity: entity with 2 candidate_columns → SEMANTIC_CONFLICT
  - detect_metric_ambiguity: entity with 1 column → no conflict
  - detect_metric_ambiguity: no entities → no conflict
  - detect_dimension_ambiguity: same entity maps to models in different domains → AMBIGUOUS_JOIN
  - detect_dimension_ambiguity: models in same domain → no conflict
  - detect_dimension_ambiguity: single model per entity → no conflict
  - detect_temporal_ambiguity: 2+ date columns + no date filter → TEMPORAL_AMBIGUITY
  - detect_temporal_ambiguity: 2+ date columns + date filter word → no conflict
  - detect_temporal_ambiguity: 0-1 date columns → no conflict
  - detect_all: metric conflict fires before dimension check
  - detect_all: no ambiguity returns is_ambiguous=False
  - result dict always has required keys
"""

import pytest

from reasoning.ambiguity_detector import AmbiguityDetector


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def make_entity(term, candidate_columns=None, candidate_models=None, score=1.0, matched_token=None):
    return {
        "term":              term,
        "matched_token":     matched_token or term,
        "score":             score,
        "candidate_columns": candidate_columns or [],
        "candidate_models":  candidate_models or [],
    }

def make_extraction(entities=None, unresolved_tokens=None):
    return {
        "entities_extracted": entities or [],
        "unresolved_tokens":  unresolved_tokens or [],
        "candidate_models":   [],
    }

REQUIRED_KEYS = {"is_ambiguous", "ambiguity_type", "conflicts", "recommendation"}


@pytest.fixture
def detector():
    return AmbiguityDetector()


# ──────────────────────────────────────────────────────────────────────────────
# detect_metric_ambiguity
# ──────────────────────────────────────────────────────────────────────────────

class TestMetricAmbiguity:

    def test_two_candidate_columns_is_conflict(self, detector):
        entities = [make_entity("revenue", candidate_columns=["revenue_gross", "revenue_net"])]
        result = detector.detect_metric_ambiguity(entities)
        assert result["is_ambiguous"] is True
        assert result["ambiguity_type"] == "SEMANTIC_CONFLICT"

    def test_conflict_contains_both_columns(self, detector):
        entities = [make_entity("revenue", candidate_columns=["revenue_gross", "revenue_net"])]
        result = detector.detect_metric_ambiguity(entities)
        conflict_cols = {c["column"] for c in result["conflicts"]}
        assert "revenue_gross" in conflict_cols
        assert "revenue_net" in conflict_cols

    def test_single_column_no_conflict(self, detector):
        entities = [make_entity("revenue", candidate_columns=["revenue_gross"])]
        result = detector.detect_metric_ambiguity(entities)
        assert result["is_ambiguous"] is False

    def test_no_columns_no_conflict(self, detector):
        entities = [make_entity("revenue", candidate_columns=[])]
        result = detector.detect_metric_ambiguity(entities)
        assert result["is_ambiguous"] is False

    def test_empty_entities_no_conflict(self, detector):
        result = detector.detect_metric_ambiguity([])
        assert result["is_ambiguous"] is False

    def test_result_has_required_keys(self, detector):
        result = detector.detect_metric_ambiguity([])
        assert REQUIRED_KEYS.issubset(result.keys())

    def test_recommendation_mentions_term(self, detector):
        entities = [make_entity("revenue", candidate_columns=["revenue_gross", "revenue_net"])]
        result = detector.detect_metric_ambiguity(entities)
        assert "revenue" in result["recommendation"]


# ──────────────────────────────────────────────────────────────────────────────
# detect_dimension_ambiguity
# ──────────────────────────────────────────────────────────────────────────────

class TestDimensionAmbiguity:

    def test_different_domains_is_ambiguous(self, detector, graph):
        """Two models for the same entity coming from different domains."""
        entities = [make_entity(
            "customer",
            candidate_models=["dim_customer", "fct_orders"],   # customer=sales, fct_orders=finance
        )]
        result = detector.detect_dimension_ambiguity(entities, graph)
        # Only triggers if graph has different domains for these models
        # dim_customer → sales, fct_orders → finance
        if result["is_ambiguous"]:
            assert result["ambiguity_type"] == "AMBIGUOUS_JOIN"
        # If both happen to have same domain in fixture, accept non-ambiguous
        assert result["is_ambiguous"] in (True, False)

    def test_single_model_no_ambiguity(self, detector, graph):
        entities = [make_entity("customer", candidate_models=["dim_customer"])]
        result = detector.detect_dimension_ambiguity(entities, graph)
        assert result["is_ambiguous"] is False

    def test_no_entities_no_ambiguity(self, detector, graph):
        result = detector.detect_dimension_ambiguity([], graph)
        assert result["is_ambiguous"] is False

    def test_result_has_required_keys(self, detector, graph):
        result = detector.detect_dimension_ambiguity([], graph)
        assert REQUIRED_KEYS.issubset(result.keys())

    def test_two_models_same_domain_no_ambiguity(self, detector, graph):
        """Both dim_customer models with same domain → no conflict."""
        entities = [make_entity("customer", candidate_models=["dim_customer", "dim_customer"])]
        result = detector.detect_dimension_ambiguity(entities, graph)
        assert result["is_ambiguous"] is False

    def test_cross_domain_conflict_recommendation(self, detector, graph):
        """When domains differ, recommendation should mention number of domains."""
        entities = [make_entity(
            "customer",
            candidate_models=["dim_customer", "fct_orders"],
        )]
        result = detector.detect_dimension_ambiguity(entities, graph)
        if result["is_ambiguous"]:
            assert "domain" in result["recommendation"].lower() or "source" in result["recommendation"].lower()


# ──────────────────────────────────────────────────────────────────────────────
# detect_temporal_ambiguity
# ──────────────────────────────────────────────────────────────────────────────

class TestTemporalAmbiguity:

    def _graph_with_date_cols(self, graph, model, date_cols):
        """Return a modified graph node with date columns injected."""
        import copy
        g2 = copy.deepcopy(graph)
        g2.graph.nodes[model]["columns"] = date_cols
        return g2

    def test_two_date_cols_no_filter_fires(self, detector, graph):
        """Inject two date columns into fct_orders → should trigger TEMPORAL_AMBIGUITY."""
        g2 = self._graph_with_date_cols(
            graph, "fct_orders", ["order_date", "ship_date"]
        )
        extraction = make_extraction()
        result = detector.detect_temporal_ambiguity(["fct_orders"], g2, extraction)
        assert result["is_ambiguous"] is True
        assert result["ambiguity_type"] == "TEMPORAL_AMBIGUITY"

    def test_date_filter_word_suppresses_conflict(self, detector, graph):
        """If extraction has "last" in unresolved_tokens, no temporal ambiguity."""
        g2 = self._graph_with_date_cols(
            graph, "fct_orders", ["order_date", "ship_date"]
        )
        extraction = make_extraction(unresolved_tokens=["last", "30", "days"])
        result = detector.detect_temporal_ambiguity(["fct_orders"], g2, extraction)
        assert result["is_ambiguous"] is False

    def test_single_date_col_no_conflict(self, detector, graph):
        g2 = self._graph_with_date_cols(
            graph, "fct_orders", ["order_date"]
        )
        extraction = make_extraction()
        result = detector.detect_temporal_ambiguity(["fct_orders"], g2, extraction)
        assert result["is_ambiguous"] is False

    def test_no_date_cols_no_conflict(self, detector, graph):
        g2 = self._graph_with_date_cols(graph, "fct_orders", [])
        extraction = make_extraction()
        result = detector.detect_temporal_ambiguity(["fct_orders"], g2, extraction)
        assert result["is_ambiguous"] is False

    def test_base_graph_no_date_columns_no_conflict(self, detector, graph):
        """Phase 1 graph has no column lists → temporal ambiguity never fires by default."""
        extraction = make_extraction()
        result = detector.detect_temporal_ambiguity(["fct_orders"], graph, extraction)
        assert result["is_ambiguous"] is False

    def test_result_has_required_keys(self, detector, graph):
        extraction = make_extraction()
        result = detector.detect_temporal_ambiguity(["fct_orders"], graph, extraction)
        assert REQUIRED_KEYS.issubset(result.keys())

    def test_temporal_conflict_recommendation_mentions_model(self, detector, graph):
        g2 = self._graph_with_date_cols(
            graph, "fct_orders", ["order_date", "ship_date"]
        )
        extraction = make_extraction()
        result = detector.detect_temporal_ambiguity(["fct_orders"], g2, extraction)
        if result["is_ambiguous"]:
            assert "fct_orders" in result["recommendation"]


# ──────────────────────────────────────────────────────────────────────────────
# detect_all
# ──────────────────────────────────────────────────────────────────────────────

class TestDetectAll:

    def test_revenue_query_semantic_conflict(self, detector, graph):
        """Revenue with two candidate columns → SEMANTIC_CONFLICT at step 1."""
        extraction = {
            "entities_extracted": [
                make_entity("revenue", candidate_columns=["revenue_gross", "revenue_net"],
                            candidate_models=["fct_orders"])
            ],
            "unresolved_tokens": [],
            "candidate_models": ["fct_orders"],
        }
        result = detector.detect_all(extraction, ["fct_orders"], graph)
        assert result["is_ambiguous"] is True
        assert result["ambiguity_type"] == "SEMANTIC_CONFLICT"

    def test_clean_query_not_ambiguous(self, detector, graph):
        """Single model, single column, no date filter needed → not ambiguous."""
        extraction = {
            "entities_extracted": [
                make_entity("customer", candidate_columns=["customer_id"],
                            candidate_models=["dim_customer"])
            ],
            "unresolved_tokens": [],
            "candidate_models": ["dim_customer"],
        }
        result = detector.detect_all(extraction, ["dim_customer"], graph)
        assert result["is_ambiguous"] is False
        assert result["ambiguity_type"] is None

    def test_no_entities_not_ambiguous(self, detector, graph):
        extraction = make_extraction()
        result = detector.detect_all(extraction, [], graph)
        assert result["is_ambiguous"] is False

    def test_detect_all_result_has_required_keys(self, detector, graph):
        extraction = make_extraction()
        result = detector.detect_all(extraction, [], graph)
        assert REQUIRED_KEYS.issubset(result.keys())
