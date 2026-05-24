"""
reasoning/entity_extractor.py

Maps raw query text to known enterprise metadata concepts via glossary lookup.

Design reference:
  EXPANSION_DESIGN.md §7.3 — Entity Extraction Algorithm

Algorithm (per token / n-gram):
  glossary_match_score = 0.60 × literal_match + 0.40 × semantic_score
  Hit threshold: score > 0.65

The "exact_string_match" factor from the design spec is implemented as a
graded literal_match (0–1) to handle plurals, synonyms, and substrings.
The semantic component uses cosine similarity when an embed_fn is provided,
and falls back to difflib string overlap otherwise.
"""

import re
from difflib import SequenceMatcher
from typing import Callable, Dict, List, Optional

MATCH_THRESHOLD = 0.65

_STOP_WORDS = frozenset({
    "show", "me", "get", "give", "find", "list", "all", "the", "a", "an",
    "of", "in", "for", "by", "with", "and", "or", "not", "is", "are",
    "was", "were", "be", "been", "total", "overall", "failed", "successful",
    "my", "our", "each", "after", "before", "during", "which", "that",
    "what", "how", "many", "much", "number", "count", "where", "when",
})


class EntityExtractor:
    """
    Extracts business entities from a natural language query using a
    business glossary and the metadata lineage graph.

    Parameters
    ----------
    glossary : dict
        Loaded from data/glossary.json.
        Schema: {term: {description, synonyms, candidate_models, candidate_columns, domain}}
    graph : MetadataGraph
        Used to validate and cross-reference resolved models.
    embed_fn : callable(str) -> list[float], optional
        Embedding function for semantic similarity.
        Falls back to difflib string overlap when None.
    """

    def __init__(self, glossary: dict, graph, embed_fn: Optional[Callable] = None):
        self.glossary = glossary
        self.graph = graph
        self.embed_fn = embed_fn

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def extract(self, query: str) -> dict:
        """
        Extract entities from a query string.

        Returns
        -------
        dict with keys:
          entities_extracted  : list[dict]   — resolved entities with scores
          unresolved_tokens   : list[str]    — non-stop-word tokens with no hit
          candidate_models    : list[str]    — deduplicated model names (graph-validated)
        """
        tokens = self._tokenize(query)
        ngrams = self._ngrams(tokens, max_n=2)

        # Best hit per glossary term (highest-scoring gram wins)
        best_hits: Dict[str, dict] = {}

        for gram in ngrams:
            for term, entry in self.glossary.items():
                score = self._score(gram, term, entry)
                if score > MATCH_THRESHOLD:
                    if term not in best_hits or score > best_hits[term]["score"]:
                        best_hits[term] = {
                            "term": term,
                            "matched_token": gram,
                            "score": round(score, 4),
                            "candidate_models": list(entry.get("candidate_models", [])),
                            "candidate_columns": list(entry.get("candidate_columns", [])),
                            "domain": entry.get("domain", ""),
                        }

        entities = list(best_hits.values())

        # Validate candidate models against the live graph
        valid_models = set(self.graph.all_models())
        candidate_models: List[str] = []
        for e in entities:
            e["candidate_models"] = [m for m in e["candidate_models"] if m in valid_models]
            for m in e["candidate_models"]:
                if m not in candidate_models:
                    candidate_models.append(m)

        # Unresolved: non-stop-word tokens not captured by any hit
        matched_norms = {self._norm(e["matched_token"]) for e in entities}
        unresolved = [
            t for t in tokens
            if t.lower() not in _STOP_WORDS
            and self._norm(t) not in matched_norms
        ]

        return {
            "entities_extracted": entities,
            "unresolved_tokens": unresolved,
            "candidate_models": candidate_models,
        }

    # ------------------------------------------------------------------ #
    # Scoring                                                              #
    # ------------------------------------------------------------------ #

    def _score(self, gram: str, key: str, entry: dict) -> float:
        """
        glossary_match_score = 0.60 × literal_match + 0.40 × semantic_score
        """
        literal = self._literal(gram, key, entry)
        semantic = self._semantic(gram, entry)
        return 0.60 * literal + 0.40 * semantic

    def _literal(self, gram: str, key: str, entry: dict) -> float:
        """
        Graded 0–1 based on exact/synonym/substring matching after normalisation.

        Score levels:
          1.00  exact match with key (after normalisation)
          0.90  exact match with a synonym
          0.75  key is substring of gram, or gram is substring of key
          0.65  synonym is substring of gram, or gram is substring of synonym
          0.00  no match
        """
        ng = self._norm(gram)
        nk = self._norm(key)
        syns = [self._norm(s) for s in entry.get("synonyms", [])]

        if ng == nk:
            return 1.00
        if ng in syns:
            return 0.90
        if nk in ng or ng in nk:
            return 0.75
        if any(s in ng or ng in s for s in syns):
            return 0.65
        return 0.00

    def _semantic(self, gram: str, entry: dict) -> float:
        """
        Semantic similarity between gram and the glossary entry.
        Uses embed_fn (cosine) when available; falls back to difflib ratio.
        """
        if self.embed_fn:
            return self._cosine_sim(gram, entry.get("description", ""))

        # Fallback: best string overlap across key + synonyms + description
        key_str = next(iter(self.glossary))  # not used directly here
        targets = (
            list(entry.get("synonyms", []))
            + [entry.get("description", "")]
        )
        ng = self._norm(gram)
        scores = [
            SequenceMatcher(None, ng, t.lower()).ratio()
            for t in targets if t
        ]
        return max(scores) if scores else 0.0

    def _cosine_sim(self, a: str, b: str) -> float:
        """Cosine similarity between two embedded strings."""
        import math
        va = self.embed_fn(a)
        vb = self.embed_fn(b)
        dot = sum(x * y for x, y in zip(va, vb))
        na = math.sqrt(sum(x * x for x in va))
        nb = math.sqrt(sum(x * x for x in vb))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    # ------------------------------------------------------------------ #
    # Tokenisation helpers                                                 #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _tokenize(query: str) -> List[str]:
        """Split query into lowercase tokens, strip punctuation."""
        raw = re.sub(r"[^a-zA-Z0-9_ ]", " ", query)
        return [t for t in raw.lower().split() if t]

    @staticmethod
    def _ngrams(tokens: List[str], max_n: int = 2) -> List[str]:
        """Generate 1-grams and 2-grams from token list."""
        result = list(tokens)
        for n in range(2, max_n + 1):
            for i in range(len(tokens) - n + 1):
                result.append(" ".join(tokens[i: i + n]))
        return result

    @staticmethod
    def _norm(s: str) -> str:
        """
        Normalise a string: lowercase, strip, apply simple plural/suffix rules.
        customers → customer  |  payments → payment  |  tickets → ticket
        """
        s = s.lower().strip()
        if s.endswith("ies") and len(s) > 4:
            return s[:-3] + "y"
        if s.endswith("es") and len(s) > 4 and s[-3] not in "aeiou":
            return s[:-2]
        if s.endswith("s") and len(s) > 3:
            return s[:-1]
        return s
