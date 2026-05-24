"""
tests/test_semantic_retriever.py

Integration tests for retrieval/semantic_retriever.py

Coverage
--------
  - composite retrieval returns ranker-like structure
  - top_k truncation preserves the top candidate
  - composite retrieval can differ from naive semantic-only retrieval
  - governance-blocked model is demoted in composite retrieval
"""

import pytest

from retrieval.semantic_retriever import SemanticRetriever


@pytest.fixture(scope="module")
def retriever(graph, glossary):
    return SemanticRetriever(graph, glossary, embed_fn=None)


class TestOutputStructure:

    def test_retrieve_returns_required_keys(self, retriever):
        result = retriever.retrieve("show segments", ["dim_customer", "payment_events"])
        assert {"query", "rankings", "top_candidate"}.issubset(result.keys())

    def test_top_k_truncates_rankings(self, retriever):
        result = retriever.retrieve(
            "show revenue by region",
            ["dim_customer", "fct_orders", "payment_events"],
            top_k=2,
        )
        assert len(result["rankings"]) == 2
        assert result["top_candidate"] == result["rankings"][0]["candidate"]


class TestCompositeVsNaive:

    def test_composite_retrieval_demotes_governance_blocked_model(self, retriever):
        result = retriever.retrieve(
            "show payment amounts",
            ["dim_customer", "payment_events"],
        )
        assert result["top_candidate"] == "dim_customer"

    def test_naive_retrieval_prefers_payment_events_for_payment_query(self, retriever):
        result = retriever.naive_retrieve(
            "show payment amounts",
            ["dim_customer", "payment_events"],
        )
        assert result["top_candidate"] == "payment_events"

    def test_composite_and_naive_ordering_differ(self, retriever):
        composite = retriever.retrieve(
            "show payment amounts",
            ["dim_customer", "payment_events"],
        )
        naive = retriever.naive_retrieve(
            "show payment amounts",
            ["dim_customer", "payment_events"],
        )
        assert composite["top_candidate"] != naive["top_candidate"]
