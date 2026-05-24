"""
ingestion/graph_store.py

Directed graph of dbt models and their lineage relationships.
Used by the Semantic Query Planning Engine for:
  - join path inference
  - lineage proximity scoring
  - neighbour discovery

Design reference:
  EXPANSION_DESIGN.md §8  — Metadata Graph Example
  EXPANSION_DESIGN.md §7.1 — lineage_proximity factor in Join Path Ranking

Node attributes stored per model
---------------------------------
  domain, tags, owner, completeness, column_info, estimated_scan_gb,
  partition_column, partition_grain

Edge attributes stored per relationship
----------------------------------------
  edge_type   : "explicit_fk" | "lineage_dependency"
  left_column : str | None
  right_column: str | None

Hop → proximity score mapping  (§7.1)
--------------------------------------
  1 hop  → 1.00
  2 hops → 0.70
  3 hops → 0.40
  4+ hops → 0.15
  no path → 0.00
"""

import json
from pathlib import Path
from typing import List, Optional, Tuple

try:
    import networkx as nx
    _NX_AVAILABLE = True
except ImportError:
    _NX_AVAILABLE = False

# Hop-score lookup (§7.1)
_HOP_SCORES = {1: 1.00, 2: 0.70, 3: 0.40}
_MANY_HOPS_SCORE = 0.15
_NO_PATH_SCORE = 0.00


class MetadataGraph:
    """
    Thin wrapper around a NetworkX DiGraph for metadata lineage reasoning.
    """

    def __init__(self) -> None:
        if not _NX_AVAILABLE:
            raise ImportError(
                "networkx is required. Install with: pip install networkx"
            )
        self.graph: "nx.DiGraph" = nx.DiGraph()

    # ------------------------------------------------------------------ #
    # Build                                                                #
    # ------------------------------------------------------------------ #

    def build_from_edges(self, edges: List[dict]) -> None:
        """
        Populate the graph from a list of lineage edge dicts produced by
        LineageParser.extract_edges().

        If an edge already exists for a pair and the new edge is 'explicit_fk',
        the edge is upgraded (FK column details are added).
        """
        for edge in edges:
            up = edge["upstream"]
            dn = edge["downstream"]

            for node in (up, dn):
                if not self.graph.has_node(node):
                    self.graph.add_node(node)

            if self.graph.has_edge(up, dn):
                # Upgrade to explicit_fk if we now have stronger evidence
                if edge["edge_type"] == "explicit_fk":
                    attrs = self.graph[up][dn]
                    attrs["edge_type"] = "explicit_fk"
                    if edge.get("left_column"):
                        attrs["left_column"] = edge["left_column"]
                        attrs["right_column"] = edge["right_column"]
            else:
                self.graph.add_edge(
                    up,
                    dn,
                    edge_type=edge["edge_type"],
                    left_column=edge.get("left_column"),
                    right_column=edge.get("right_column"),
                )

    def add_model_nodes(self, model_records: List[dict]) -> None:
        """
        Ensure all model nodes carry model-level and column-level governance
        attributes. Called after build_from_edges so attribute-less nodes get
        decorated.
        """
        for rec in model_records:
            model = rec["model"]
            if not self.graph.has_node(model):
                self.graph.add_node(model)
            attrs = self.graph.nodes[model]
            attrs.setdefault("column_info", {})
            attrs.setdefault("pii_columns", [])
            attrs.setdefault("restricted_columns", [])

            if rec.get("record_type") == "model":
                attrs["domain"] = rec.get("domain", "")
                attrs["tags"] = rec.get("tags", [])
                attrs["owner"] = rec.get("owner", "")
                attrs["completeness"] = rec.get("metadata_completeness_score", 0.0)
                attrs["estimated_scan_gb"] = rec.get("estimated_scan_gb")
                attrs["partition_column"] = rec.get("partition_column")
                attrs["partition_grain"] = rec.get("partition_grain")
                continue

            if rec.get("record_type") != "column":
                continue

            column = rec.get("column")
            if not column:
                continue

            attrs["column_info"][column] = {
                "description": rec.get("description", ""),
                "data_type": rec.get("data_type"),
                "tags": rec.get("tags", []),
                "pii": bool(rec.get("pii", False)),
                "pii_type": rec.get("pii_type"),
                "description_missing": bool(rec.get("description_missing", False)),
            }

            if rec.get("pii"):
                attrs["pii_columns"] = sorted(
                    set(attrs.get("pii_columns", [])) | {column}
                )
            if any(
                tag in {"pci", "restricted", "confidential"}
                for tag in rec.get("tags", [])
            ):
                attrs["restricted_columns"] = sorted(
                    set(attrs.get("restricted_columns", [])) | {column}
                )

    # ------------------------------------------------------------------ #
    # Query                                                                #
    # ------------------------------------------------------------------ #

    def get_shortest_path(
        self, model_a: str, model_b: str
    ) -> Tuple[List[str], int]:
        """
        Shortest directed path between two models (tries both directions).

        Returns
        -------
        (path_nodes, hop_count)
        ([],  -1) when no path exists in either direction.
        """
        for src, tgt in [(model_a, model_b), (model_b, model_a)]:
            try:
                path = nx.shortest_path(self.graph, source=src, target=tgt)
                return path, len(path) - 1
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue
        return [], -1

    def get_neighbors(self, model: str, depth: int = 2) -> List[str]:
        """
        All models reachable within `depth` hops (undirected — both
        upstream and downstream).  The origin model is excluded.
        """
        if not self.graph.has_node(model):
            return []
        undirected = self.graph.to_undirected()
        try:
            ego = nx.ego_graph(undirected, model, radius=depth)
            return [n for n in ego.nodes() if n != model]
        except nx.NodeNotFound:
            return []

    def lineage_proximity_score(self, model_a: str, model_b: str) -> float:
        """
        Return a 0–1 proximity score based on hop distance.
        Design reference: EXPANSION_DESIGN.md §7.1 — lineage_proximity factor.
        """
        _, hops = self.get_shortest_path(model_a, model_b)
        if hops == -1:
            return _NO_PATH_SCORE
        if hops >= 4:
            return _MANY_HOPS_SCORE
        return _HOP_SCORES.get(hops, _MANY_HOPS_SCORE)

    def get_edge_type(self, model_a: str, model_b: str) -> Optional[str]:
        """
        Return the edge_type attribute for the edge between model_a and
        model_b (either direction), or None if no edge exists.
        """
        for src, tgt in [(model_a, model_b), (model_b, model_a)]:
            if self.graph.has_edge(src, tgt):
                return self.graph[src][tgt].get("edge_type")
        return None

    def all_models(self) -> List[str]:
        """Return all model node names."""
        return list(self.graph.nodes())

    def node_count(self) -> int:
        return self.graph.number_of_nodes()

    def edge_count(self) -> int:
        return self.graph.number_of_edges()

    # ------------------------------------------------------------------ #
    # Persistence                                                          #
    # ------------------------------------------------------------------ #

    def save(self, path: str) -> None:
        """Serialise graph to JSON (NetworkX node-link format)."""
        data = nx.node_link_data(self.graph)
        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load(self, path: str) -> None:
        """Deserialise graph from JSON."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # NetworkX 3.x changed kwargs; handle both versions gracefully
        try:
            self.graph = nx.node_link_graph(data, directed=True, multigraph=False)
        except TypeError:
            self.graph = nx.node_link_graph(data)
