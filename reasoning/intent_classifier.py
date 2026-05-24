"""
reasoning/intent_classifier.py

Keyword-based analytical intent classification — fully deterministic, no LLM required.

Design reference:
  EXPANSION_DESIGN.md §6 — Step 2: Analytical Intent Inference

Intent types
------------
  aggregation   SUM, COUNT, AVG implied
  trend         over-time / growth / change implied
  segmentation  GROUP BY a dimension implied
  comparison    vs / compare / difference implied
  lookup        find / list / show a single record

intent_clarity_weight
---------------------
  1.00  single unambiguous intent pattern matched
  0.85  two possible intents, primary selected
  0.60  no clear intent pattern detected
"""

import re
from typing import Optional

# --------------------------------------------------------------------- #
# Keyword pattern sets                                                    #
# --------------------------------------------------------------------- #

_AGG_WORDS = frozenset({
    "total", "sum", "count", "average", "avg", "max", "min",
    "how many", "how much", "aggregate", "revenue", "amount",
    "number of", "rate", "percent", "percentage",
})
_TREND_WORDS = frozenset({
    "over time", "by month", "by week", "by quarter", "by year",
    "trend", "growth", "change", "monthly", "weekly", "quarterly",
    "annually", "year over year", "yoy", "mom", "weekly",
    "last 30 days", "last quarter", "last year",
})
_SEG_WORDS = frozenset({
    "by", "per", "breakdown", "split", "grouped", "group by",
    "for each", "each", "segment", "category", "distribution",
})
_CMP_WORDS = frozenset({
    "vs", "versus", "compare", "compared", "difference",
    "between", "contrast", "against", "relative",
})
_LOOKUP_WORDS = frozenset({
    "show me", "find", "list", "get", "which", "who", "what is",
    "look up", "details for", "information about", "profile",
    "specific", "single", "one",
})

# Time grain patterns → grain label
_GRAIN_PATTERNS = [
    (r"\b(daily|per day|each day|by day)\b",       "daily"),
    (r"\b(weekly|per week|each week|by week)\b",    "weekly"),
    (r"\b(monthly|per month|each month|by month)\b","monthly"),
    (r"\b(quarterly|per quarter|by quarter|q[1-4])\b", "quarterly"),
    (r"\b(annual|annually|yearly|per year|by year)\b", "annual"),
]


class IntentClassifier:
    """
    Deterministic keyword-based intent classifier.
    No LLM or external calls required.
    """

    def classify(self, query: str) -> dict:
        """
        Classify the analytical intent of a natural language query.

        Returns
        -------
        dict with keys:
          intent               : str  — primary intent label
          time_grain           : str | None
          intent_clarity_weight: float (1.00 / 0.85 / 0.60)
          matched_patterns     : list[str]  — which intent labels matched
        """
        q = query.lower()
        matched = []

        if self._matches_any(q, _AGG_WORDS):
            matched.append("aggregation")
        if self._matches_any(q, _TREND_WORDS):
            matched.append("trend")
        # Segmentation: "by X" is common — only count if NOT sole word "by"
        if self._matches_any(q, _SEG_WORDS) and len(q.split()) > 2:
            matched.append("segmentation")
        if self._matches_any(q, _CMP_WORDS):
            matched.append("comparison")
        if self._matches_any(q, _LOOKUP_WORDS):
            matched.append("lookup")

        # Deduplicate while preserving order
        seen = set()
        matched = [m for m in matched if not (m in seen or seen.add(m))]

        # Choose primary intent and clarity weight
        if len(matched) == 0:
            intent = "lookup"
            clarity = 0.60
        elif len(matched) == 1:
            intent = matched[0]
            clarity = 1.00
        else:
            # Multiple matches: prefer specificity order
            priority = ["aggregation", "segmentation", "trend", "comparison", "lookup"]
            intent = next((p for p in priority if p in matched), matched[0])
            clarity = 0.85

        time_grain = self._detect_grain(q)

        return {
            "intent": intent,
            "time_grain": time_grain,
            "intent_clarity_weight": clarity,
            "matched_patterns": matched,
        }

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _matches_any(query: str, patterns: frozenset) -> bool:
        return any(p in query for p in patterns)

    @staticmethod
    def _detect_grain(query: str) -> Optional[str]:
        for pattern, label in _GRAIN_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                return label
        return None
