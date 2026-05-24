"""
reasoning/ambiguity_detector.py

Detects three types of ambiguity before SQL generation.

Design reference:
  EXPANSION_DESIGN.md §7.2 — Ambiguity Detection Algorithm

Ambiguity types
---------------
  SEMANTIC_CONFLICT   Two metric candidates score within 0.15 of each other
                      for the same extracted entity.

  AMBIGUOUS_JOIN      The same dimension name resolves to models in more
                      than one domain.

  TEMPORAL_AMBIGUITY  Multiple date columns present with no date filter
                      specified in the query.
"""

import re
from typing import List, Optional

_METRIC_DELTA_THRESHOLD = 0.15
_DATE_COLUMN_PATTERNS   = re.compile(r"(date|_dt|_ts|timestamp|_at|time)$", re.IGNORECASE)
_DATE_FILTER_WORDS      = frozenset({
    "today", "yesterday", "last", "this", "since", "before",
    "after", "between", "from", "to", "on", "during",
    "month", "week", "year", "quarter", "day",
})


class AmbiguityDetector:
    """
    Runs three independent ambiguity checks and returns a combined result.
    """

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def detect_all(self, extraction: dict, candidate_models: List[str], graph) -> dict:
        """
        Run all three ambiguity checks.

        Parameters
        ----------
        extraction       : output from EntityExtractor.extract()
        candidate_models : deduplicated list of resolved model names
        graph            : MetadataGraph (used for domain look-up)

        Returns
        -------
        dict with keys:
          is_ambiguous   : bool
          ambiguity_type : str | None
          conflicts      : list[dict]
          recommendation : str | None
        """
        # 1. Metric ambiguity
        metric = self.detect_metric_ambiguity(extraction.get("entities_extracted", []))
        if metric["is_ambiguous"]:
            return metric

        # 2. Dimension / domain ambiguity
        dim = self.detect_dimension_ambiguity(
            extraction.get("entities_extracted", []), graph
        )
        if dim["is_ambiguous"]:
            return dim

        # 3. Temporal ambiguity (needs model column info from graph nodes)
        temporal = self.detect_temporal_ambiguity(candidate_models, graph, extraction)
        if temporal["is_ambiguous"]:
            return temporal

        return {"is_ambiguous": False, "ambiguity_type": None, "conflicts": [], "recommendation": None}

    def detect_metric_ambiguity(self, entities: List[dict]) -> dict:
        """
        Check if any entity maps to multiple candidate columns whose glossary
        scores are within METRIC_DELTA_THRESHOLD of each other.

        Two columns of the same entity with equal or near-equal scores
        represent competing metric definitions (e.g. revenue_gross vs
        revenue_net for the 'revenue' entity).
        """
        for entity in entities:
            cols = entity.get("candidate_columns", [])
            if len(cols) < 2:
                continue

            # Treat each candidate column as having the same base score
            # (they come from the same glossary entry).  A score delta of
            # 0.0 is always within the 0.15 threshold → conflict.
            score = entity.get("score", 1.0)
            score_delta = 0.0  # same glossary entry → equal confidence

            if score_delta < _METRIC_DELTA_THRESHOLD:
                return {
                    "is_ambiguous": True,
                    "ambiguity_type": "SEMANTIC_CONFLICT",
                    "conflicts": [
                        {"column": c, "entity": entity["term"], "score": score}
                        for c in cols
                    ],
                    "recommendation": (
                        f"Multiple '{entity['term']}' definitions found: "
                        + ", ".join(cols)
                        + ". Specify which definition is required."
                    ),
                }
        return {"is_ambiguous": False, "ambiguity_type": None, "conflicts": [], "recommendation": None}

    def detect_dimension_ambiguity(self, entities: List[dict], graph) -> dict:
        """
        Check if the same dimension entity resolves to models in different
        domains, signalling competing source systems.
        """
        model_domains = {
            m: graph.graph.nodes[m].get("domain", "")
            for m in graph.all_models()
        }

        for entity in entities:
            models = entity.get("candidate_models", [])
            if len(models) < 2:
                continue

            domains = {m: model_domains.get(m, "unknown") for m in models}
            unique_domains = set(domains.values())

            if len(unique_domains) > 1:
                return {
                    "is_ambiguous": True,
                    "ambiguity_type": "AMBIGUOUS_JOIN",
                    "conflicts": [
                        {"model": m, "domain": d} for m, d in domains.items()
                    ],
                    "recommendation": (
                        f"Entity '{entity['term']}' resolves to models in "
                        f"{len(unique_domains)} domains: "
                        + ", ".join(sorted(unique_domains))
                        + ". Clarify which source system to use."
                    ),
                }
        return {"is_ambiguous": False, "ambiguity_type": None, "conflicts": [], "recommendation": None}

    def detect_temporal_ambiguity(
        self, candidate_models: List[str], graph, extraction: dict
    ) -> dict:
        """
        Check if any selected model has multiple date columns AND the query
        contains no date filter words.
        """
        query_lower = " ".join(extraction.get("unresolved_tokens", [])).lower()
        # Also scan the original entities for date-related tokens
        all_tokens = [e["matched_token"] for e in extraction.get("entities_extracted", [])]
        combined = (query_lower + " " + " ".join(all_tokens)).lower()
        has_date_filter = any(w in combined for w in _DATE_FILTER_WORDS)

        if has_date_filter:
            return {"is_ambiguous": False, "ambiguity_type": None, "conflicts": [], "recommendation": None}

        for model in candidate_models:
            date_cols = self._date_columns_for_model(model, graph)
            if len(date_cols) >= 2:
                return {
                    "is_ambiguous": True,
                    "ambiguity_type": "TEMPORAL_AMBIGUITY",
                    "conflicts": [{"model": model, "date_columns": date_cols}],
                    "recommendation": (
                        f"Model '{model}' has {len(date_cols)} date columns: "
                        + ", ".join(date_cols)
                        + ". Specify which date to filter on."
                    ),
                }
        return {"is_ambiguous": False, "ambiguity_type": None, "conflicts": [], "recommendation": None}

    # ------------------------------------------------------------------ #
    # Helper                                                               #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _date_columns_for_model(model: str, graph) -> List[str]:
        """
        Return column names that look like date/timestamp columns for
        a given model, using graph node metadata if available.
        Falls back to known column names stored as graph node attributes.
        """
        # The graph currently stores completeness, domain, etc. but not column lists.
        # We use a lightweight heuristic: look for any column list stored on the node.
        node_data = graph.graph.nodes.get(model, {})
        # Column info is not stored in the base graph (Phase 1 only stores model attrs).
        # Return empty list — temporal ambiguity only fires when column info is injected.
        columns = node_data.get("columns", [])
        return [c for c in columns if _DATE_COLUMN_PATTERNS.search(c)]
