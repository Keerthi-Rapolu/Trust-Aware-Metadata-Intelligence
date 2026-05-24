"""
retrieval/semantic_retriever.py

High-level retrieval interface wiring the composite EmbeddingRanker.

Design reference:
  EXPANSION_DESIGN.md §10 — Retrieval Ranking Logic
  TASK_PLAN.md  §4.4   — Replace existing retrieval with composite ranker

The old approach in src/query.py used raw ChromaDB cosine similarity as
the sole retrieval signal.  SemanticRetriever replaces that with the
5-factor composite formula, making retrieval explainable and lineage-aware.

Usage
-----
retriever = SemanticRetriever(graph, glossary, embed_fn=None)

# Composite 5-factor retrieval
result = retriever.retrieve("show revenue by segment", candidates, top_k=3)
for item in result["rankings"]:
    print(item["candidate"], item["final_score"], item["scores"])

# Naive semantic-only retrieval (for comparison / regression tests)
naive = retriever.naive_retrieve("show revenue by segment", candidates, top_k=3)
"""

from typing import Callable, Dict, List, Optional

from retrieval.embedding_ranker import EmbeddingRanker


class SemanticRetriever:
    """
    Retrieval interface backed by the composite 5-factor EmbeddingRanker.

    Parameters
    ----------
    graph    : MetadataGraph
    glossary : dict
    embed_fn : callable(str) -> list[float], optional
    """

    def __init__(
        self,
        graph,
        glossary: dict,
        embed_fn: Optional[Callable] = None,
    ) -> None:
        self._ranker = EmbeddingRanker(graph, glossary, embed_fn)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def retrieve(
        self,
        query:           str,
        candidates:      List[str],
        top_k:           Optional[int]           = None,
        selected_models: Optional[List[str]]     = None,
        query_history:   Optional[Dict[str, float]] = None,
    ) -> dict:
        """
        Composite 5-factor retrieval.

        Parameters
        ----------
        query           : natural language query
        candidates      : model names to evaluate
        top_k           : if set, return only the top-k ranked candidates
        selected_models : already-resolved models in the plan (lineage anchor)
        query_history   : {model_name: relevance_score} from past queries

        Returns
        -------
        Same structure as EmbeddingRanker.rank(), optionally truncated to top_k.
        """
        result = self._ranker.rank(
            query,
            candidates,
            selected_models = selected_models,
            query_history   = query_history,
        )
        if top_k is not None and top_k > 0:
            result = dict(result)
            result["rankings"] = result["rankings"][:top_k]
            if result["rankings"]:
                result["top_candidate"] = result["rankings"][0]["candidate"]
            else:
                result["top_candidate"] = None
        return result

    def naive_retrieve(
        self,
        query:      str,
        candidates: List[str],
        top_k:      Optional[int] = None,
    ) -> dict:
        """
        Naive semantic-similarity-only retrieval for comparison and testing.

        Uses only the semantic_similarity factor (weight=1.0); all other
        factors are fixed at their neutral values:
          lineage_proximity       = 0.50 (cold-start)
          glossary_overlap        = 0.00
          historical_relevance    = 0.50 (cold-start)
          governance_compatibility= 1.00

        This mirrors what a naive vector-similarity approach would do.

        Returns
        -------
        dict with the same structure as retrieve(), but using naive scores.
        """
        if not candidates:
            return {"query": query, "rankings": [], "top_candidate": None}

        scored = []
        for model in candidates:
            # Only semantic similarity drives the score
            sem = self._ranker._semantic(query, model)
            scored.append({
                "candidate":  model,
                "scores": {
                    "semantic_similarity":      round(sem,  4),
                    "lineage_proximity":        0.50,
                    "glossary_overlap":         0.00,
                    "historical_relevance":     0.50,
                    "governance_compatibility": 1.00,
                },
                "final_score": round(sem, 4),
                "mode":        "naive",
            })

        scored.sort(key=lambda x: (-x["final_score"], x["candidate"]))
        for i, item in enumerate(scored):
            item["rank"] = i + 1

        top = scored[0]["candidate"] if scored else None
        result = {"query": query, "rankings": scored, "top_candidate": top}
        if top_k is not None and top_k > 0:
            result["rankings"] = result["rankings"][:top_k]
            result["top_candidate"] = (
                result["rankings"][0]["candidate"] if result["rankings"] else None
            )
        return result

    def score_single(
        self,
        query:           str,
        model:           str,
        selected_models: Optional[List[str]]     = None,
        query_history:   Optional[Dict[str, float]] = None,
    ) -> dict:
        """Expose single-model scoring from the underlying ranker."""
        return self._ranker.score_single(
            query, model, selected_models, query_history
        )
