"""
reasoning/join_path_engine.py

Finds, scores, and ranks join paths between candidate models.

Design reference:
  EXPANSION_DESIGN.md §7.1 — Join Path Ranking Algorithm

Formula per edge:
  score = 0.40 × fk_strength
        + 0.25 × lineage_proximity
        + 0.20 × semantic_similarity   (column name similarity)
        + 0.15 × historical_frequency  (cold-start default 0.50)

FK strength lookup
------------------
  explicit_fk (dbt relationship test)  → 0.90
  lineage_dependency (depends_on only) → 0.45
  unknown / no evidence               → 0.20

Decision thresholds (per design §7.1)
---------------------------------------
  ≥ 0.80  proceed
  0.60–0.79  warn
  0.40–0.59  surface ambiguity
  < 0.40  refuse (WEAK_JOIN)

Ambiguity threshold: |score_A - score_B| < 0.10 AND both > 0.40
"""

from difflib import SequenceMatcher
from typing import Callable, Dict, List, Optional, Tuple

from ingestion.graph_store import MetadataGraph

_FK_STRENGTH: Dict[Optional[str], float] = {
    "explicit_fk":        0.90,   # dbt relationship test
    "lineage_dependency": 0.45,   # depends_on, no test
    None:                 0.20,   # no evidence
}

_COLD_START_HISTORY = 0.50
_AMBIGUITY_DELTA    = 0.10
_REFUSE_THRESHOLD   = 0.40
_WARN_THRESHOLD     = 0.60
_PROCEED_THRESHOLD  = 0.80


class JoinPathEngine:
    """
    Computes join paths and their confidence scores for a set of models.
    """

    def __init__(self, graph: MetadataGraph, embed_fn: Optional[Callable] = None):
        self.graph = graph
        self.embed_fn = embed_fn

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def find_join_paths(self, models: List[str]) -> dict:
        """
        Find and score the join path that connects all required models.

        Returns
        -------
        dict with keys:
          join_paths         : list[dict]  — scored edge dicts
          overall_confidence : float
          ambiguity_detected : bool
          ambiguity_reason   : str | None
          all_models_resolved: bool        — True if all models are connected
        """
        deduped = list(dict.fromkeys(models))

        if len(deduped) == 0:
            return self._empty()
        if len(deduped) == 1:
            return self._single(deduped[0])

        edges = self._spanning_edges(deduped)

        if not edges:
            return {
                "join_paths": [],
                "overall_confidence": 0.0,
                "ambiguity_detected": False,
                "ambiguity_reason": "No join path found between candidate models.",
                "all_models_resolved": False,
            }

        overall = min(e["score"] for e in edges)
        ambiguity, reason = self._check_ambiguity(edges, deduped)

        return {
            "join_paths": edges,
            "overall_confidence": round(overall, 4),
            "ambiguity_detected": ambiguity,
            "ambiguity_reason": reason,
            "all_models_resolved": True,
        }

    def score_edge(self, upstream: str, downstream: str) -> float:
        """
        Public scoring function for a single directed graph edge.
        Used by tests and the planner to inspect individual edge scores.
        """
        return self._score_edge(upstream, downstream)

    # ------------------------------------------------------------------ #
    # Spanning path builder                                                #
    # ------------------------------------------------------------------ #

    def _spanning_edges(self, models: List[str]) -> List[dict]:
        """
        Greedy Prim-like approach: start from models[0], repeatedly find
        the best path connecting any unconnected model to the connected set.
        Intermediate models on multi-hop paths are included automatically.
        """
        connected = {models[0]}
        remaining = list(models[1:])
        all_edges: List[dict] = []
        added_pairs = set()

        while remaining:
            best_path: Optional[List[str]] = None
            best_target: Optional[str] = None

            for target in remaining:
                for anchor in list(connected):
                    path, hops = self.graph.get_shortest_path(anchor, target)
                    if hops == -1:
                        continue
                    if best_path is None or hops < len(best_path):
                        best_path = path
                        best_target = target

            if best_path is None:
                break  # target unreachable

            # Add every edge along the path and mark all nodes as connected.
            # The path may run in the reverse direction (get_shortest_path tries
            # both directions), so we must add ALL nodes — not just the tail.
            for node in best_path:
                connected.add(node)

            for i in range(len(best_path) - 1):
                src, tgt = best_path[i], best_path[i + 1]
                pair = (src, tgt)
                if pair not in added_pairs:
                    added_pairs.add(pair)
                    all_edges.append(self._build_edge(src, tgt))

            remaining = [m for m in remaining if m not in connected]

        return all_edges

    # ------------------------------------------------------------------ #
    # Edge scoring                                                         #
    # ------------------------------------------------------------------ #

    def _score_edge(self, upstream: str, downstream: str) -> float:
        """Score one directed edge using the 4-factor formula."""
        edge_data = self.graph.graph.get_edge_data(upstream, downstream) or {}
        edge_type  = edge_data.get("edge_type")
        left_col   = edge_data.get("left_column")
        right_col  = edge_data.get("right_column")

        fk_strength       = _FK_STRENGTH.get(edge_type, _FK_STRENGTH[None])
        lineage_proximity = self.graph.lineage_proximity_score(upstream, downstream)
        semantic_sim      = self._col_similarity(left_col, right_col)
        historical        = _COLD_START_HISTORY

        score = (
            0.40 * fk_strength
            + 0.25 * lineage_proximity
            + 0.20 * semantic_sim
            + 0.15 * historical
        )
        return round(score, 4)

    def _build_edge(self, upstream: str, downstream: str) -> dict:
        edge_data = self.graph.graph.get_edge_data(upstream, downstream) or {}
        score = self._score_edge(upstream, downstream)
        left  = edge_data.get("left_column")
        right = edge_data.get("right_column")
        return {
            "from_model":   upstream,
            "to_model":     downstream,
            "from_column":  left,
            "to_column":    right,
            "edge_type":    edge_data.get("edge_type", "unknown"),
            "score":        score,
            "join_string":  (
                f"{upstream}.{left} -> {downstream}.{right}"
                if left and right
                else f"{upstream} -> {downstream}"
            ),
        }

    # ------------------------------------------------------------------ #
    # Column similarity (semantic_similarity factor)                       #
    # ------------------------------------------------------------------ #

    def _col_similarity(self, col_a: Optional[str], col_b: Optional[str]) -> float:
        """
        Semantic similarity between two join key column names.
        Returns 0.50 when column names unknown (lineage_dependency edges).
        """
        if not col_a or not col_b:
            return 0.50  # no column info → neutral
        if col_a.lower() == col_b.lower():
            return 1.00  # exact match
        # Shared tokens (e.g. "order_id" vs "id")
        a_parts = set(col_a.lower().split("_"))
        b_parts = set(col_b.lower().split("_"))
        if a_parts & b_parts:
            return 0.80
        # Difflib fallback
        return round(SequenceMatcher(None, col_a.lower(), col_b.lower()).ratio(), 4)

    # ------------------------------------------------------------------ #
    # Ambiguity detection                                                  #
    # ------------------------------------------------------------------ #

    def _check_ambiguity(
        self, edges: List[dict], required_models: List[str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Detect if two different edges connecting the same model-pair score
        within AMBIGUITY_DELTA of each other — per design §7.1.
        """
        # Build a map of (from, to) → list of scores
        # (In spanning-tree logic duplicate pairs are removed, so ambiguity
        # here means: two paths to the same model both score > 0.40 and
        # within 0.10 of each other.)
        pair_scores: Dict[Tuple[str, str], List[float]] = {}
        for e in edges:
            k = (e["from_model"], e["to_model"])
            pair_scores.setdefault(k, []).append(e["score"])

        for (src, tgt), scores in pair_scores.items():
            if len(scores) >= 2:
                s = sorted(scores, reverse=True)
                if (
                    abs(s[0] - s[1]) < _AMBIGUITY_DELTA
                    and s[1] > _REFUSE_THRESHOLD
                ):
                    return True, (
                        f"Two competing join paths between {src} and {tgt} "
                        f"scored within {_AMBIGUITY_DELTA} of each other."
                    )
        return False, None

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _empty() -> dict:
        return {
            "join_paths": [],
            "overall_confidence": 1.0,
            "ambiguity_detected": False,
            "ambiguity_reason": None,
            "all_models_resolved": True,
        }

    @staticmethod
    def _single(model: str) -> dict:
        return {
            "join_paths": [],
            "overall_confidence": 1.0,
            "ambiguity_detected": False,
            "ambiguity_reason": None,
            "all_models_resolved": True,
        }
