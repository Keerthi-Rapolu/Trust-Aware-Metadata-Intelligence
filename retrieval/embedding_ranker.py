"""
retrieval/embedding_ranker.py

Composite 5-factor retrieval scoring for enterprise metadata ranking.

Design reference:
  EXPANSION_DESIGN.md §10 — Composite Retrieval Scoring Formula

Formula
-------
  Final Retrieval Score =
    0.35 × Semantic Similarity
  + 0.25 × Lineage Proximity
  + 0.15 × Business Glossary Overlap
  + 0.15 × Historical Query Relevance
  + 0.10 × Governance Compatibility

All factors are bounded [0, 1].

Factor details
--------------
semantic_similarity
    Cosine similarity between query embedding and the model's description
    embedding.  Falls back to difflib SequenceMatcher string overlap when
    no embed_fn is provided.  Model description is derived by aggregating
    glossary entries that reference the model (so "fct_orders" gets the
    revenue/order descriptions).

lineage_proximity
    Hop-distance score from LineageScorer relative to models already
    selected in the plan.  Cold-start 0.50 when no anchor models exist.

glossary_overlap
    Query-to-model glossary alignment from GlossaryMatcher.
    1.0 = exact term match; 0.75 = sub-token; 0.0 = no glossary coverage.

historical_relevance
    Caller-supplied per-model score from past query observations.
    Cold-start default 0.50 until history is populated.

governance_compatibility
    Derived from MetadataGraph node tag attributes:
      1.00 — no governance flags
      0.50 — soft flag (description_missing or sensitive tag)
      0.00 — hard block (pii, pci, restricted, confidential tag)

Output format
-------------
{
  "query": "...",
  "rankings": [
    {
      "candidate": "fct_orders",
      "scores": {
        "semantic_similarity":     0.82,
        "lineage_proximity":       0.90,
        "glossary_overlap":        0.75,
        "historical_relevance":    0.50,
        "governance_compatibility": 1.00
      },
      "final_score": 0.7895,
      "rank": 1
    },
    ...
  ],
  "top_candidate": "fct_orders"
}
"""

import math
from difflib import SequenceMatcher
from typing import Callable, Dict, List, Optional

from retrieval.lineage_scorer   import LineageScorer
from retrieval.glossary_matcher import GlossaryMatcher

# Factor weights — must sum to 1.0
_W_SEMANTIC   = 0.35
_W_LINEAGE    = 0.25
_W_GLOSSARY   = 0.15
_W_HISTORICAL = 0.15
_W_GOVERNANCE = 0.10

_COLD_START_HISTORICAL: float = 0.50

# Tags that affect governance score
_HARD_BLOCK_TAGS = frozenset({"pii", "pci", "restricted", "confidential"})
_SOFT_FLAG_TAGS  = frozenset({"sensitive"})


class EmbeddingRanker:
    """
    Ranks candidate metadata models using the composite 5-factor scoring
    formula from EXPANSION_DESIGN.md §10.

    Parameters
    ----------
    graph    : MetadataGraph  — provides lineage proximity and governance tags
    glossary : dict           — business glossary for overlap scoring
    embed_fn : callable(str) -> list[float], optional
               When provided, semantic similarity uses cosine distance
               between query and model-description embeddings.
               When None, falls back to SequenceMatcher string overlap.
    """

    def __init__(
        self,
        graph,
        glossary: dict,
        embed_fn: Optional[Callable] = None,
    ) -> None:
        self.graph    = graph
        self.glossary = glossary
        self.embed_fn = embed_fn
        self._lineage  = LineageScorer(graph)
        self._glossary = GlossaryMatcher(glossary)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def rank(
        self,
        query:           str,
        candidates:      List[str],
        selected_models: Optional[List[str]]     = None,
        query_history:   Optional[Dict[str, float]] = None,
    ) -> dict:
        """
        Score and rank all candidate models for a query.

        Parameters
        ----------
        query           : natural language query
        candidates      : model names to evaluate
        selected_models : models already resolved in the current plan
                          (used for lineage proximity scoring)
        query_history   : {model_name: relevance_score} from past similar queries;
                          cold-start default 0.50 for absent models

        Returns
        -------
        dict — see module docstring for output format
        """
        if not candidates:
            return {"query": query, "rankings": [], "top_candidate": None}

        scored = []
        for model in candidates:
            factors = self._score_factors(
                query, model,
                selected_models = selected_models or [],
                query_history   = query_history   or {},
            )
            final = self._composite(factors)
            scored.append({
                "candidate":   model,
                "scores":      factors,
                "final_score": round(final, 4),
            })

        # Governance-hard-blocked models are never surfaced ahead of
        # governance-compatible candidates, even if their lexical match is
        # stronger. Within each governance bucket, use the composite score.
        scored.sort(
            key=lambda x: (
                x["scores"]["governance_compatibility"] == 0.0,
                -x["final_score"],
                x["candidate"],
            )
        )
        for i, item in enumerate(scored):
            item["rank"] = i + 1

        top = scored[0]["candidate"] if scored else None
        return {"query": query, "rankings": scored, "top_candidate": top}

    def score_single(
        self,
        query:           str,
        model:           str,
        selected_models: Optional[List[str]]     = None,
        query_history:   Optional[Dict[str, float]] = None,
    ) -> dict:
        """
        Compute and return the full factor breakdown for one model.

        Returns
        -------
        {
          "candidate":   str,
          "scores":      {factor: float, ...},
          "final_score": float
        }
        """
        factors = self._score_factors(
            query, model,
            selected_models = selected_models or [],
            query_history   = query_history   or {},
        )
        return {
            "candidate":   model,
            "scores":      factors,
            "final_score": round(self._composite(factors), 4),
        }

    # ------------------------------------------------------------------ #
    # Factor computation                                                   #
    # ------------------------------------------------------------------ #

    def _score_factors(
        self,
        query:           str,
        model:           str,
        selected_models: List[str],
        query_history:   Dict[str, float],
    ) -> dict:
        return {
            "semantic_similarity":      round(self._semantic(query, model),                   4),
            "lineage_proximity":        round(self._lineage.score(model, selected_models),    4),
            "glossary_overlap":         round(self._glossary.score(query, model),             4),
            "historical_relevance":     round(self._historical(model, query_history),         4),
            "governance_compatibility": round(self._governance(model),                        4),
        }

    @staticmethod
    def _composite(factors: dict) -> float:
        return (
            _W_SEMANTIC   * factors["semantic_similarity"]
          + _W_LINEAGE    * factors["lineage_proximity"]
          + _W_GLOSSARY   * factors["glossary_overlap"]
          + _W_HISTORICAL * factors["historical_relevance"]
          + _W_GOVERNANCE * factors["governance_compatibility"]
        )

    # ── Semantic similarity ─────────────────────────────────────────────

    def _semantic(self, query: str, model: str) -> float:
        """
        Cosine similarity when embed_fn available; SequenceMatcher otherwise.
        Model description is built from glossary entries that reference it,
        so semantics are grounded in business meaning rather than technical names.
        """
        desc = self._model_description(model)

        if self.embed_fn:
            va = self.embed_fn(query)
            vb = self.embed_fn(desc)
            return self._cosine(va, vb)

        return self._semantic_fallback(query, model, desc)

    def _semantic_fallback(self, query: str, model: str, desc: str) -> float:
        """
        Lexical fallback used when no embedding function is available.

        This intentionally gives strong credit to exact glossary-grounded
        matches so obvious single-entity queries can still succeed in the
        synthetic offline/demo environment.
        """
        raw_query_tokens = set(self._tokenize(query))
        norm_query_tokens = {self._norm(t) for t in raw_query_tokens}

        alias_tokens = set()
        alias_scores = []
        for term, entry in self.glossary.items():
            if model not in entry.get("candidate_models", []):
                continue

            aliases = [term, model] + entry.get("synonyms", [])
            for alias in aliases:
                alias_tokens.add(self._norm(alias))
                alias_scores.append(
                    SequenceMatcher(None, query.lower(), alias.lower()).ratio()
                )

        if alias_tokens & norm_query_tokens:
            return 1.0

        for alias in alias_tokens:
            for token in norm_query_tokens:
                if alias and token and (alias in token or token in alias):
                    return 0.85

        desc_similarity = SequenceMatcher(None, query.lower(), desc.lower()).ratio()
        alias_similarity = max(alias_scores) if alias_scores else 0.0
        return max(desc_similarity, alias_similarity)

    def _model_description(self, model: str) -> str:
        """
        Aggregate a human-readable description for a model by collecting
        all glossary entry descriptions that reference it.
        Falls back to the model name if no glossary entry references it.
        """
        parts = []
        for term, entry in self.glossary.items():
            if model in entry.get("candidate_models", []):
                desc = entry.get("description", "")
                if desc:
                    parts.append(desc)
                # Also include the term itself for exact-match semantics
                parts.append(term)
                parts.extend(entry.get("synonyms", []))
        return " ".join(parts) if parts else model

    @staticmethod
    def _tokenize(text: str) -> list:
        cleaned = "".join(ch.lower() if (ch.isalnum() or ch == "_") else " " for ch in text)
        return [token for token in cleaned.split() if token]

    @staticmethod
    def _norm(text: str) -> str:
        text = text.lower().strip()
        if text.endswith("ies") and len(text) > 4:
            text = text[:-3] + "y"
        elif text.endswith("s") and len(text) > 3:
            text = text[:-1]
        return text.replace(" ", "_").replace("-", "_")

    @staticmethod
    def _cosine(va: list, vb: list) -> float:
        dot = sum(x * y for x, y in zip(va, vb))
        na  = math.sqrt(sum(x * x for x in va))
        nb  = math.sqrt(sum(x * x for x in vb))
        if na == 0 or nb == 0:
            return 0.0
        return max(0.0, min(1.0, dot / (na * nb)))

    # ── Historical relevance ────────────────────────────────────────────

    @staticmethod
    def _historical(model: str, history: Dict[str, float]) -> float:
        """
        Return the historical relevance score; defaults to 0.50 cold-start.
        """
        return history.get(model, _COLD_START_HISTORICAL)

    # ── Governance compatibility ────────────────────────────────────────

    def _governance(self, model: str) -> float:
        """
        Derive governance compatibility from MetadataGraph node tags.

        1.00 — no governance flags
        0.50 — soft flag (sensitive tag or description_missing node attribute)
        0.00 — hard block (pii, pci, restricted, confidential tag)
        """
        node = self.graph.graph.nodes.get(model, {})
        tags = frozenset(t.lower() for t in node.get("tags", []))

        if tags & _HARD_BLOCK_TAGS:
            return 0.00
        if tags & _SOFT_FLAG_TAGS or node.get("description_missing"):
            return 0.50
        return 1.00
