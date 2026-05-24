"""
ingestion/lineage_parser.py

Extracts lineage edges and FK relationships from a dbt manifest.

Design reference: EXPANSION_DESIGN.md §15 — PHASE 1, Task 1.3

Edge dict schema
----------------
{
    "upstream":     str,   # model name
    "downstream":   str,   # model name
    "edge_type":    "explicit_fk" | "lineage_dependency",
    "left_column":  str | None,   # FK column on downstream model
    "right_column": str | None,   # PK column on upstream model
}

Edge type precedence
--------------------
explicit_fk > lineage_dependency

When both exist for the same pair, explicit_fk wins (higher FK strength score).
"""

from typing import List

MANIFEST_MODEL_PREFIX = "model."


class LineageParser:
    """
    Extracts two categories of edges from a dbt manifest:

    1. explicit_fk  — backed by a dbt ``relationships`` test node.
       FK strength score: 0.90  (dbt relationship test documented)

    2. lineage_dependency — from ``depends_on.nodes`` with no test.
       FK strength score: 0.45  (column name match inferred)
    """

    def extract_edges(self, manifest: dict) -> List[dict]:
        """
        Return a deduplicated list of lineage edges.
        explicit_fk edges take precedence over lineage_dependency for the
        same (upstream, downstream) pair.
        """
        explicit_fks = self._collect_explicit_fks(manifest)
        lineage_edges = self._collect_lineage_edges(manifest)

        fk_pairs = {(e["upstream"], e["downstream"]) for e in explicit_fks}

        merged = list(explicit_fks)
        for edge in lineage_edges:
            if (edge["upstream"], edge["downstream"]) not in fk_pairs:
                merged.append(edge)

        return merged

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _collect_explicit_fks(self, manifest: dict) -> List[dict]:
        """
        Scan test nodes for dbt ``relationships`` tests.
        Each such test encodes: downstream.left_column → upstream.right_column.
        """
        edges: List[dict] = []
        nodes = manifest.get("nodes", {})

        for _, node in nodes.items():
            if node.get("resource_type") != "test":
                continue
            test_meta = node.get("test_metadata", {})
            if test_meta.get("name") != "relationships":
                continue

            kwargs = test_meta.get("kwargs", {})
            downstream = self._resolve_ref(kwargs.get("model", ""))
            upstream = self._resolve_ref(kwargs.get("to", ""))
            left_column = kwargs.get("column_name", "")
            right_column = kwargs.get("field", "")

            if upstream and downstream:
                edges.append({
                    "upstream": upstream,
                    "downstream": downstream,
                    "edge_type": "explicit_fk",
                    "left_column": left_column or None,
                    "right_column": right_column or None,
                })

        return edges

    def _collect_lineage_edges(self, manifest: dict) -> List[dict]:
        """
        Build edges from depends_on.nodes for every model node.
        These are structural lineage edges without column-level detail.
        """
        edges: List[dict] = []
        nodes = manifest.get("nodes", {})

        for _, node in nodes.items():
            if node.get("resource_type") != "model":
                continue
            downstream = node["name"]
            for dep_uid in node.get("depends_on", {}).get("nodes", []):
                if not dep_uid.startswith(MANIFEST_MODEL_PREFIX):
                    continue
                upstream = dep_uid.split(".")[-1]
                edges.append({
                    "upstream": upstream,
                    "downstream": downstream,
                    "edge_type": "lineage_dependency",
                    "left_column": None,
                    "right_column": None,
                })

        return edges

    @staticmethod
    def _resolve_ref(ref_str: str) -> str:
        """
        Normalise dbt ref strings to bare model names.

        "ref('dim_customer')"              -> "dim_customer"
        'ref("fct_orders")'                -> "fct_orders"
        "model.analytics.dim_customer"     -> "dim_customer"
        """
        if not ref_str:
            return ""
        s = ref_str.strip()
        if s.lower().startswith("ref("):
            # strip ref( ... )
            inner = s[4:].rstrip(")").strip().strip("'\"")
            return inner
        if "." in s:
            return s.split(".")[-1]
        return s
