"""
retrieval/glossary_matcher.py

Business glossary overlap scoring for composite retrieval ranking.

Design reference:
  EXPANSION_DESIGN.md §10 — Business Glossary Overlap (0.15 weight)

A candidate model that is tagged with terms matching the current query
ranks higher than one that only has embedding similarity.

Algorithm
---------
  1. Find glossary entries that reference ``candidate_model``.
  2. Score entries in glossary order using three tiers:
       - Term or synonym appears verbatim (normalised) in query  -> 1.00
       - Term or synonym is a sub-token of a query token         -> 0.75
       - Description word overlap (scaled Jaccard)               -> 0–0.50
  3. Prefer lexical evidence (exact/sub-token) across entries.
     Fall back to the first non-zero description-overlap score only when
     no lexical evidence exists for the candidate model.
     Returns 0.0 if the model is not referenced by any entry.

The glossary order is intentional for the description-overlap fallback.
When a model is represented by multiple business concepts, lexical matches
remain precise, while the earlier entries act as the canonical semantic
fallback. ``get_matching_terms()`` still exposes every matching concept
for explainability.
"""

import re
from typing import List


class GlossaryMatcher:
    """
    Computes how strongly a candidate model aligns with business glossary
    terms present in the query.

    Parameters
    ----------
    glossary : dict
        Loaded from data/glossary.json.
        Schema: {term: {description, synonyms, candidate_models, candidate_columns, domain}}
    """

    def __init__(self, glossary: dict) -> None:
        self.glossary = glossary

    # ------------------------------------------------------------------ #
    # Public API                                                          #
    # ------------------------------------------------------------------ #

    def score(self, query: str, candidate_model: str) -> float:
        """
        Return a 0–1 glossary overlap score for ``candidate_model`` given
        ``query``.

        Returns 0.0 if the model is not referenced by any glossary entry.
        """
        raw_query_tokens = set(self._tokenize(query))
        norm_query_tokens = {self._norm(t) for t in raw_query_tokens}

        fallback = 0.0

        for term, entry in self.glossary.items():
            if candidate_model not in entry.get("candidate_models", []):
                continue
            lexical_score = self._entry_lexical_score(
                term,
                entry,
                raw_query_tokens=raw_query_tokens,
                norm_query_tokens=norm_query_tokens,
            )
            if lexical_score > 0.0:
                return lexical_score

            if fallback == 0.0:
                fallback = self._entry_description_score(
                    entry,
                    norm_query_tokens=norm_query_tokens,
                )

        return fallback

    def score_all(self, query: str, candidates: List[str]) -> dict:
        """
        Score every candidate model for ``query``.

        Returns
        -------
        {model_name: score}
        """
        return {c: self.score(query, c) for c in candidates}

    def get_matching_terms(self, query: str, candidate_model: str) -> List[str]:
        """
        Return glossary terms that (a) reference ``candidate_model`` and
        (b) produce a non-zero match score against ``query``.

        Useful for explainability output.
        """
        raw_query_tokens = set(self._tokenize(query))
        norm_query_tokens = {self._norm(t) for t in raw_query_tokens}
        matched = []

        for term, entry in self.glossary.items():
            if candidate_model not in entry.get("candidate_models", []):
                continue
            if self._entry_lexical_score(
                term,
                entry,
                raw_query_tokens=raw_query_tokens,
                norm_query_tokens=norm_query_tokens,
            ) > 0.0:
                matched.append(term)
                continue
            if self._entry_description_score(
                entry,
                norm_query_tokens=norm_query_tokens,
            ) > 0.0:
                matched.append(term)

        return matched

    # ------------------------------------------------------------------ #
    # Scoring internals                                                   #
    # ------------------------------------------------------------------ #

    def _entry_lexical_score(
        self,
        term: str,
        entry: dict,
        *,
        raw_query_tokens: set,
        norm_query_tokens: set,
    ) -> float:
        """
        Score one glossary entry against the pre-tokenised query token set.
        """
        synonyms = entry.get("synonyms", [])
        all_terms = [term] + synonyms

        # Tier 1: exact term / synonym match
        for text in all_terms:
            norm = self._norm(text)
            if text.lower() in raw_query_tokens or norm in norm_query_tokens:
                return 1.0

        # Tier 2: sub-token containment
        for text in all_terms:
            norm = self._norm(text)
            for query_token in norm_query_tokens:
                if norm and query_token and (norm in query_token or query_token in norm):
                    return 0.75

        return 0.0

    def _entry_description_score(
        self,
        entry: dict,
        *,
        norm_query_tokens: set,
    ) -> float:
        """Return the description-overlap fallback score for one entry."""
        desc_tokens = {self._norm(t) for t in self._tokenize(entry.get("description", ""))}
        if desc_tokens and norm_query_tokens:
            intersection = norm_query_tokens & desc_tokens
            union = norm_query_tokens | desc_tokens
            if union:
                jaccard = len(intersection) / len(union)
                return min(0.50, jaccard * 2.0)
        return 0.0

    # ------------------------------------------------------------------ #
    # Helpers                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Lowercase tokenise, strip punctuation."""
        raw = re.sub(r"[^a-zA-Z0-9_ ]", " ", text)
        return [t.lower() for t in raw.split() if t]

    @staticmethod
    def _norm(s: str) -> str:
        """Normalise term: lowercase, singularise, collapse separators."""
        s = s.lower().strip()
        if s.endswith("ies") and len(s) > 4:
            s = s[:-3] + "y"
        elif s.endswith("s") and len(s) > 3:
            s = s[:-1]
        return s.replace(" ", "_").replace("-", "_")
