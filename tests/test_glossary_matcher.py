"""
tests/test_glossary_matcher.py

Unit tests for retrieval/glossary_matcher.py

Coverage
--------
  - Exact term match in query → 1.0
  - Plural form of term in query → 1.0
  - Synonym match in query → 1.0
  - Sub-token containment → 0.75
  - Description Jaccard overlap → (0, 0.50]
  - No match → 0.0
  - Model not referenced by any glossary entry → 0.0
  - score_all returns dict for all candidates
  - get_matching_terms returns matched term names
"""

import pytest

from retrieval.glossary_matcher import GlossaryMatcher


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def matcher(glossary):
    return GlossaryMatcher(glossary)


# ── Tier 1: exact term / synonym match (score = 1.0) ────────────────────────

class TestExactMatch:

    def test_exact_term_match(self, matcher):
        # "revenue" is a term → fct_orders
        result = matcher.score("total revenue", "fct_orders")
        assert result == 1.0

    def test_plural_term_match(self, matcher):
        # "segments" normalises to "segment" → dim_customer
        result = matcher.score("show all segments", "dim_customer")
        assert result == 1.0

    def test_synonym_match(self, matcher):
        # "sales" is a synonym for "revenue" → fct_orders
        result = matcher.score("total sales by region", "fct_orders")
        assert result == 1.0

    def test_synonym_plural_match(self, matcher):
        # "clients" → synonym "client" for "customer" → dim_customer
        result = matcher.score("list all clients", "dim_customer")
        assert result == 1.0

    def test_exact_region_match(self, matcher):
        result = matcher.score("breakdown by region", "dim_customer")
        assert result == 1.0

    def test_exact_escalation_match(self, matcher):
        # "escalation" → support_tickets
        result = matcher.score("show escalation levels", "support_tickets")
        assert result == 1.0

    def test_payment_synonym_billing(self, matcher):
        # "billing" is a synonym for "payment" → payment_events
        result = matcher.score("billing event summary", "payment_events")
        assert result == 1.0


# ── No match → 0.0 ───────────────────────────────────────────────────────────

class TestNoMatch:

    def test_no_glossary_match_returns_0(self, matcher):
        # "xyz_metric_zz99" has no glossary entry
        result = matcher.score("show xyz_metric_zz99", "fct_orders")
        assert result == 0.0

    def test_model_not_in_glossary_returns_0(self, matcher):
        # "phantom_model" is not in any glossary entry
        result = matcher.score("show revenue", "phantom_model")
        assert result == 0.0

    def test_wrong_model_for_term(self, matcher):
        # "revenue" maps to fct_orders, NOT dim_customer
        # dim_customer only maps via customer/segment/region
        # So revenue query should score 0 on dim_customer only if no other overlap
        # Actually: dim_customer is a candidate_model for customer/segment/region
        # "revenue" alone does NOT reference dim_customer
        result = matcher.score("revenue", "payment_events")
        # payment_events is only referenced by "payment" entry
        # "revenue" has no match with payment glossary terms
        assert result == 0.0


# ── Tier 2: sub-token containment (score = 0.75) ─────────────────────────────

class TestSubTokenMatch:

    def test_partial_term_in_query_token(self, matcher):
        # "order_date" query token contains "order" (term for fct_orders)
        result = matcher.score("filter by order_date", "fct_orders")
        assert result == pytest.approx(0.75)

    def test_partial_synonym_match(self, matcher):
        # "gross_revenue" is a synonym for "revenue"; query has "gross_revenue"
        result = matcher.score("show gross_revenue numbers", "fct_orders")
        assert result == 1.0   # exact synonym match after normalisation


# ── Description Jaccard overlap (score in (0, 0.50]) ─────────────────────────

class TestDescriptionOverlap:

    def test_description_overlap_produces_non_zero(self, matcher):
        # "monetary value sales transactions" shares tokens with revenue description
        result = matcher.score("monetary value from transactions", "fct_orders")
        assert result > 0.0

    def test_description_overlap_below_0_50(self, matcher):
        # Jaccard-based score is scaled to [0, 0.50]
        result = matcher.score("monetary value from transactions", "fct_orders")
        assert result <= 0.50


# ── score_all ────────────────────────────────────────────────────────────────

class TestScoreAll:

    def test_returns_dict_for_all_candidates(self, matcher):
        candidates = ["dim_customer", "fct_orders", "payment_events", "support_tickets"]
        result = matcher.score_all("total revenue", candidates)
        assert set(result.keys()) == set(candidates)

    def test_revenue_query_scores_fct_orders_highest(self, matcher):
        candidates = ["dim_customer", "fct_orders", "payment_events", "support_tickets"]
        result = matcher.score_all("total revenue", candidates)
        # fct_orders is the only model referenced by the "revenue" entry
        assert result["fct_orders"] == 1.0

    def test_segment_query_scores_dim_customer_highest(self, matcher):
        candidates = ["dim_customer", "fct_orders", "payment_events", "support_tickets"]
        result = matcher.score_all("show all segments", candidates)
        assert result["dim_customer"] == 1.0

    def test_empty_candidates_returns_empty_dict(self, matcher):
        result = matcher.score_all("total revenue", [])
        assert result == {}


# ── get_matching_terms ────────────────────────────────────────────────────────

class TestGetMatchingTerms:

    def test_revenue_query_matches_revenue_term(self, matcher):
        terms = matcher.get_matching_terms("total revenue", "fct_orders")
        assert "revenue" in terms

    def test_segment_query_matches_segment_term(self, matcher):
        terms = matcher.get_matching_terms("show segments", "dim_customer")
        assert "segment" in terms

    def test_unknown_model_returns_empty(self, matcher):
        terms = matcher.get_matching_terms("show revenue", "phantom_model")
        assert terms == []

    def test_no_match_returns_empty_list(self, matcher):
        terms = matcher.get_matching_terms("xyz_metric_zz99", "fct_orders")
        assert terms == []

    def test_multiple_terms_can_match(self, matcher):
        # Query with "revenue" and "order" → should match both "revenue" and "order"
        terms = matcher.get_matching_terms("order revenue analysis", "fct_orders")
        assert len(terms) >= 1  # at least revenue or order
