"""
retrieval/lineage_scorer.py

Lineage proximity scoring for composite retrieval ranking.

Design reference:
  EXPANSION_DESIGN.md §10 — Lineage Proximity (0.25 weight)

A candidate model that is one hop away in the lineage graph from a model
already resolved in the current plan ranks higher than one that is
structurally disconnected — regardless of embedding similarity.

Scoring
-------
  anchor_models empty / None → 0.50 (cold-start: no plan context yet)
  candidate == anchor         → 1.00 (trivially proximate)
  1 hop                       → 1.00
  2 hops                      → 0.70
  3 hops                      → 0.40
  4+ hops                     → 0.15
  no path (disconnected)      → 0.00

When multiple anchor models are present, the MAX proximity across all
anchors is returned (best-connection semantics).
"""

from typing import List, Optional

# Hop-score table (mirrors MetadataGraph._HOP_SCORES for consistency)
_HOP_SCORES: dict = {0: 1.00, 1: 1.00, 2: 0.70, 3: 0.40}
_MANY_HOPS:  float = 0.15
_NO_PATH:    float = 0.00
_COLD_START: float = 0.50   # returned when no anchor models are provided


class LineageScorer:
    """
    Scores a candidate model's lineage proximity relative to models already
    selected in the current query plan.

    Parameters
    ----------
    graph : MetadataGraph
        The populated metadata lineage graph.
    """

    def __init__(self, graph) -> None:
        self.graph = graph

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def score(
        self,
        candidate: str,
        anchor_models: Optional[List[str]] = None,
    ) -> float:
        """
        Return a 0–1 proximity score for `candidate` given `anchor_models`.

        Parameters
        ----------
        candidate     : model name to evaluate
        anchor_models : models already resolved in the current plan
                        (None or empty list → cold-start default 0.50)

        Returns
        -------
        float in [0.00, 1.00]
        """
        if not anchor_models:
            return _COLD_START

        best = 0.0
        for anchor in anchor_models:
            if anchor == candidate:
                best = max(best, 1.00)
                continue
            _, hops = self.graph.get_shortest_path(candidate, anchor)
            if hops == -1:
                prox = _NO_PATH
            elif hops >= 4:
                prox = _MANY_HOPS
            else:
                prox = _HOP_SCORES.get(hops, _MANY_HOPS)
            best = max(best, prox)

        return best

    def score_all(
        self,
        candidates: List[str],
        anchor_models: Optional[List[str]] = None,
    ) -> dict:
        """
        Score every candidate model and return ``{model_name: score}``.

        Parameters
        ----------
        candidates    : list of model names to evaluate
        anchor_models : models already in the plan (None → cold-start for all)
        """
        return {c: self.score(c, anchor_models) for c in candidates}
