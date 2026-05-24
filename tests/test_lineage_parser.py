"""
tests/test_lineage_parser.py

Unit tests for ingestion/lineage_parser.py  (Phase 1, Task 1.3)
"""

import pytest
from ingestion.lineage_parser import LineageParser


@pytest.fixture
def parser():
    return LineageParser()


# ------------------------------------------------------------------ #
# extract_edges                                                        #
# ------------------------------------------------------------------ #

def test_extract_edges_returns_list(parser, sample_manifest):
    assert isinstance(parser.extract_edges(sample_manifest), list)


def test_explicit_fk_count(parser, sample_manifest):
    """4 dbt relationship tests → 4 explicit_fk edges."""
    edges = parser.extract_edges(sample_manifest)
    fk = [e for e in edges if e["edge_type"] == "explicit_fk"]
    assert len(fk) == 4


def test_total_edge_count(parser, sample_manifest):
    """All 4 depends_on lineage edges are covered by FK tests → 4 total unique edges."""
    edges = parser.extract_edges(sample_manifest)
    assert len(edges) == 4


def test_fk_fct_orders_dim_customer(parser, sample_manifest):
    """fct_orders.customer_id → dim_customer.customer_id is explicit_fk."""
    edges = parser.extract_edges(sample_manifest)
    match = next(
        (e for e in edges
         if e["upstream"] == "dim_customer"
         and e["downstream"] == "fct_orders"
         and e["edge_type"] == "explicit_fk"),
        None,
    )
    assert match is not None, "Missing fct_orders→dim_customer FK edge"
    assert match["left_column"] == "customer_id"
    assert match["right_column"] == "customer_id"


def test_fk_payment_events_fct_orders(parser, sample_manifest):
    """payment_events.order_id → fct_orders.order_id is explicit_fk."""
    edges = parser.extract_edges(sample_manifest)
    match = next(
        (e for e in edges
         if e["upstream"] == "fct_orders"
         and e["downstream"] == "payment_events"
         and e["edge_type"] == "explicit_fk"),
        None,
    )
    assert match is not None


def test_fk_support_tickets_dim_customer(parser, sample_manifest):
    edges = parser.extract_edges(sample_manifest)
    match = next(
        (e for e in edges
         if e["upstream"] == "dim_customer"
         and e["downstream"] == "support_tickets"
         and e["edge_type"] == "explicit_fk"),
        None,
    )
    assert match is not None


def test_fk_support_tickets_fct_orders(parser, sample_manifest):
    edges = parser.extract_edges(sample_manifest)
    match = next(
        (e for e in edges
         if e["upstream"] == "fct_orders"
         and e["downstream"] == "support_tickets"
         and e["edge_type"] == "explicit_fk"),
        None,
    )
    assert match is not None


def test_no_duplicate_pairs(parser, sample_manifest):
    """Each (upstream, downstream) pair appears at most once."""
    edges = parser.extract_edges(sample_manifest)
    pairs = [(e["upstream"], e["downstream"]) for e in edges]
    assert len(pairs) == len(set(pairs)), f"Duplicate edge pairs detected: {pairs}"


def test_all_edges_have_required_keys(parser, sample_manifest):
    for edge in parser.extract_edges(sample_manifest):
        for key in ("upstream", "downstream", "edge_type"):
            assert key in edge, f"Edge missing key '{key}': {edge}"


# ------------------------------------------------------------------ #
# _resolve_ref  (static utility)                                       #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize("ref_str,expected", [
    ("ref('dim_customer')",           "dim_customer"),
    ('ref("fct_orders")',             "fct_orders"),
    ("ref('payment_events')",         "payment_events"),
    ("model.analytics.dim_customer",  "dim_customer"),
    ("model.my_project.fct_orders",   "fct_orders"),
    ("plain_model",                   "plain_model"),
    ("",                              ""),
])
def test_resolve_ref(ref_str, expected):
    assert LineageParser._resolve_ref(ref_str) == expected
