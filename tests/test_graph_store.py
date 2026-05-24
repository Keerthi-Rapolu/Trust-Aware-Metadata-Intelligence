"""
tests/test_graph_store.py

Unit tests for ingestion/graph_store.py  (Phase 1, Task 1.6)

Graph built from sample_manifest.json:

  dim_customer ──► fct_orders       (explicit_fk: customer_id)
  fct_orders   ──► payment_events   (explicit_fk: order_id)
  dim_customer ──► support_tickets  (explicit_fk: customer_id)
  fct_orders   ──► support_tickets  (explicit_fk: order_id)

Expected hop distances (directed, both-direction search):
  dim_customer  → fct_orders        : 1
  dim_customer  → payment_events    : 2  (via fct_orders)
  dim_customer  → support_tickets   : 1
  fct_orders    → support_tickets   : 1
  payment_events → support_tickets  : -1 (no directed path either way)
"""

import pytest
from ingestion.graph_store import MetadataGraph
from ingestion.lineage_parser import LineageParser
from ingestion.manifest_ingestor import ManifestIngestor


@pytest.fixture(scope="module")
def graph(sample_manifest):
    g = MetadataGraph()
    edges = LineageParser().extract_edges(sample_manifest)
    model_recs = ManifestIngestor().extract_models(sample_manifest)
    g.build_from_edges(edges)
    g.add_model_nodes(model_recs)
    return g


# ------------------------------------------------------------------ #
# Build / structure                                                    #
# ------------------------------------------------------------------ #

def test_node_count(graph):
    assert graph.node_count() == 4


def test_all_models(graph):
    assert set(graph.all_models()) == {
        "dim_customer", "fct_orders", "payment_events", "support_tickets"
    }


def test_edge_count(graph):
    assert graph.edge_count() == 4


def test_node_attributes_domain(graph):
    assert graph.graph.nodes["dim_customer"]["domain"] == "sales"
    assert graph.graph.nodes["payment_events"]["domain"] == "finance"


def test_node_attributes_owner(graph):
    assert graph.graph.nodes["dim_customer"]["owner"] == "analytics_team"
    assert graph.graph.nodes["payment_events"]["owner"] == "finance_team"


def test_node_attributes_completeness_full(graph):
    assert graph.graph.nodes["dim_customer"]["completeness"] == 1.0


def test_node_attributes_completeness_partial(graph):
    assert graph.graph.nodes["payment_events"]["completeness"] < 1.0


# ------------------------------------------------------------------ #
# get_shortest_path                                                    #
# ------------------------------------------------------------------ #

def test_path_one_hop(graph):
    path, hops = graph.get_shortest_path("dim_customer", "fct_orders")
    assert hops == 1
    assert path[0] == "dim_customer"
    assert path[-1] == "fct_orders"


def test_path_two_hops(graph):
    _, hops = graph.get_shortest_path("dim_customer", "payment_events")
    assert hops == 2


def test_path_direct_to_support_tickets(graph):
    _, hops = graph.get_shortest_path("dim_customer", "support_tickets")
    assert hops == 1


def test_path_reverse_direction(graph):
    """Reverse lookup: fct_orders ← dim_customer is also 1 hop."""
    _, hops = graph.get_shortest_path("fct_orders", "dim_customer")
    assert hops == 1


def test_path_no_connection(graph):
    """payment_events and support_tickets share no directed path either way."""
    path, hops = graph.get_shortest_path("payment_events", "support_tickets")
    assert hops == -1
    assert path == []


# ------------------------------------------------------------------ #
# lineage_proximity_score                                              #
# ------------------------------------------------------------------ #

def test_proximity_one_hop(graph):
    assert graph.lineage_proximity_score("dim_customer", "fct_orders") == 1.00


def test_proximity_two_hops(graph):
    assert graph.lineage_proximity_score("dim_customer", "payment_events") == 0.70


def test_proximity_no_path(graph):
    assert graph.lineage_proximity_score("payment_events", "support_tickets") == 0.00


# ------------------------------------------------------------------ #
# get_neighbors                                                        #
# ------------------------------------------------------------------ #

def test_neighbors_depth_1(graph):
    """dim_customer depth=1: fct_orders and support_tickets."""
    neighbors = set(graph.get_neighbors("dim_customer", depth=1))
    assert "fct_orders" in neighbors
    assert "support_tickets" in neighbors
    assert "dim_customer" not in neighbors


def test_neighbors_depth_2(graph):
    """dim_customer depth=2: also includes payment_events."""
    neighbors = set(graph.get_neighbors("dim_customer", depth=2))
    assert "payment_events" in neighbors


def test_neighbors_leaf_node(graph):
    """payment_events depth=1: fct_orders (via undirected neighbour)."""
    neighbors = set(graph.get_neighbors("payment_events", depth=1))
    assert "fct_orders" in neighbors


def test_neighbors_unknown_node(graph):
    assert graph.get_neighbors("nonexistent_model", depth=2) == []


# ------------------------------------------------------------------ #
# get_edge_type                                                        #
# ------------------------------------------------------------------ #

def test_edge_type_explicit_fk(graph):
    assert graph.get_edge_type("dim_customer", "fct_orders") == "explicit_fk"


def test_edge_type_reverse_explicit_fk(graph):
    """get_edge_type is direction-agnostic."""
    assert graph.get_edge_type("fct_orders", "dim_customer") == "explicit_fk"


def test_edge_type_none_for_no_edge(graph):
    assert graph.get_edge_type("payment_events", "support_tickets") is None


# ------------------------------------------------------------------ #
# save / load                                                          #
# ------------------------------------------------------------------ #

def test_save_and_load_roundtrip(graph, tmp_path):
    path = str(tmp_path / "graph.json")
    graph.save(path)

    loaded = MetadataGraph()
    loaded.load(path)

    assert loaded.node_count() == graph.node_count()
    assert loaded.edge_count() == graph.edge_count()
    assert set(loaded.all_models()) == set(graph.all_models())
    # Edge type preserved
    assert loaded.get_edge_type("dim_customer", "fct_orders") == "explicit_fk"


def test_save_creates_parent_dirs(graph, tmp_path):
    nested = str(tmp_path / "subdir" / "deep" / "graph.json")
    graph.save(nested)
    import os
    assert os.path.exists(nested)
