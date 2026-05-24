"""
reasoning/confidence_scorer.py

Propagates confidence scores through the query planning pipeline.

Design reference:
  EXPANSION_DESIGN.md §8 — Metadata Confidence Propagation

Formula
-------
  final_confidence = MIN(
      retrieval_score,
      join_path_confidence,
      governance_score,
      completeness_score
  ) × intent_clarity_weight

Thresholds
----------
  ≥ 0.80  confident — proceed to SQL generation
  0.60–0.79  warn — proceed with caveat
  0.40–0.59  surface ambiguity — ask for clarification
  < 0.40  refuse — INSUFFICIENT_SCHEMA or WEAK_JOIN
"""

from typing import List, Optional


_CONFIDENT_THRESHOLD  = 0.80
_WARN_THRESHOLD       = 0.60
_AMBIGUOUS_THRESHOLD  = 0.40

_DEFAULT_GOVERNANCE   = 1.00  # no governance block → full score
_DEFAULT_COMPLETENESS = 1.00  # fallback when no model records available


class ConfidenceScorer:
    """
    Computes and propagates confidence through the reasoning pipeline.
    """

    def score(
        self,
        retrieval_score:    float,
        join_confidence:    float,
        governance_score:   float,
        completeness_score: float,
        intent_clarity:     float,
    ) -> dict:
        """
        Compute the final pipeline confidence score.

        Parameters
        ----------
        retrieval_score    : composite retrieval ranking score (0–1)
        join_confidence    : overall_confidence from JoinPathEngine (0–1)
        governance_score   : governance clearance score (0–1; 0 = hard block)
        completeness_score : avg metadata completeness across candidate models (0–1)
        intent_clarity     : intent_clarity_weight from IntentClassifier (0.60–1.00)

        Returns
        -------
        dict with keys:
          final_confidence   : float — rounded to 4 dp
          confidence_level   : str  — "confident" | "warn" | "ambiguous" | "refuse"
          weakest_factor     : str  — name of the factor that set the MIN
          component_scores   : dict — all five inputs for traceability
          recommendation     : str  — human-readable guidance
        """
        components = {
            "retrieval":    round(retrieval_score,    4),
            "join_path":    round(join_confidence,    4),
            "governance":   round(governance_score,   4),
            "completeness": round(completeness_score, 4),
        }

        # MIN over the four pipeline factors
        min_value  = min(components.values())
        weakest    = min(components, key=components.get)
        final      = round(min_value * intent_clarity, 4)

        level, recommendation = self._classify(final, weakest, governance_score)

        return {
            "final_confidence":  final,
            "confidence_level":  level,
            "weakest_factor":    weakest,
            "component_scores":  {**components, "intent_clarity": round(intent_clarity, 4)},
            "recommendation":    recommendation,
        }

    def score_from_plan(self, plan: dict) -> dict:
        """
        Convenience wrapper: extract all inputs from a partial QueryPlan dict
        and return the scored confidence block.

        Expected plan keys (all optional — defaults applied when missing):
          retrieval_score, join_path_confidence, governance_score,
          completeness_score, intent_clarity_weight
        """
        return self.score(
            retrieval_score    = plan.get("retrieval_score",       1.00),
            join_confidence    = plan.get("join_path_confidence",  1.00),
            governance_score   = plan.get("governance_score",      _DEFAULT_GOVERNANCE),
            completeness_score = plan.get("completeness_score",    _DEFAULT_COMPLETENESS),
            intent_clarity     = plan.get("intent_clarity_weight", 1.00),
        )

    def aggregate_completeness(self, models: List[str], graph) -> float:
        """
        Average completeness over a list of models using graph node metadata.
        Falls back to 1.00 when no nodes carry completeness info.
        """
        scores = []
        for m in models:
            node = graph.graph.nodes.get(m, {})
            c = node.get("completeness")
            if c is not None:
                scores.append(float(c))
        return round(sum(scores) / len(scores), 4) if scores else _DEFAULT_COMPLETENESS

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _classify(
        final: float, weakest: str, governance_score: float
    ) -> tuple:
        """Return (level, recommendation) based on final score and weakest factor."""
        if governance_score == 0.0:
            return (
                "refuse",
                "Query blocked: governance hard-stop on one or more columns. "
                "Contact your data governance team for access.",
            )
        if final >= _CONFIDENT_THRESHOLD:
            return "confident", "Confidence is high — proceed to SQL generation."
        if final >= _WARN_THRESHOLD:
            return (
                "warn",
                f"Confidence is moderate (weakest factor: {weakest}). "
                "Proceeding with a caveat — verify results against source data.",
            )
        if final >= _AMBIGUOUS_THRESHOLD:
            return (
                "ambiguous",
                f"Confidence is low (weakest factor: {weakest}). "
                "Clarification needed before generating SQL.",
            )
        return (
            "refuse",
            f"Confidence too low to generate reliable SQL (weakest factor: {weakest}). "
            "Provide more context or check metadata coverage.",
        )
