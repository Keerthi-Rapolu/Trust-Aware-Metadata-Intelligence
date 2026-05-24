"""
generation/refusal_engine.py

Priority-ordered failure classification and structured response formatter.

Design reference:
  EXPANSION_DESIGN.md §9 — Failure Taxonomy
  EXPANSION_DESIGN.md §7.5 — Refusal Decision Algorithm

Failure type priority (lower number = higher priority)
------------------------------------------------------
  1  GOVERNANCE_BLOCKED   — hard stop; PII/PCI/restricted data
  2  UNSAFE_QUERY         — DML/DDL operations or destructive patterns
  3  INSUFFICIENT_SCHEMA  — no recognisable metadata for query entities
  4  WEAK_JOIN            — no join path exists between required models
  5  SEMANTIC_CONFLICT    — competing metric definitions (score delta < 0.15)
  6  AMBIGUOUS_JOIN       — competing join paths, both > 0.40 confidence
  7  TEMPORAL_AMBIGUITY   — multiple date cols, no filter specified
  8  LOW_CONFIDENCE       — final confidence < 0.40

The UNSAFE_QUERY check is performed by the RefusalEngine independently of
the QueryPlanner (query text analysis only — no metadata required).

All other failures are sourced from the QueryPlanner result and formatted
into the standard structured response.
"""

import re
from typing import List, Optional


# ── Failure priority table ──────────────────────────────────────────────────

_PRIORITY: dict = {
    "GOVERNANCE_BLOCKED":  1,
    "UNSAFE_QUERY":        2,
    "INSUFFICIENT_SCHEMA": 3,
    "WEAK_JOIN":           4,
    "SEMANTIC_CONFLICT":   5,
    "AMBIGUOUS_JOIN":      6,
    "TEMPORAL_AMBIGUITY":  7,
    "LOW_CONFIDENCE":      8,
}

# ── Unsafe query patterns ───────────────────────────────────────────────────

# DML / DDL keywords that must never appear in an analytics query
_DML_PATTERN = re.compile(
    r"\b(?:"
    r"delete\s+(?:from|all\b)"
    r"|drop\s+(?:table|database|schema|index|view|column)"
    r"|truncate(?:\s+table)?"
    r"|insert\s+into"
    r"|update\s+\w[\w.]*\s+set\b"
    r"|create\s+(?:table|database|schema|index|view)"
    r"|alter\s+(?:table|database|schema|column)"
    r"|grant\s+\w+"
    r"|revoke\s+\w+"
    r"|exec(?:ute)?\s+\w+"
    r")\b",
    re.IGNORECASE,
)

# Phrases indicating destructive / unbounded bulk operations
_DUMP_PATTERN = re.compile(
    r"\b(?:"
    r"dump\s+all"
    r"|export\s+all\s+(?:data|records)"
    r"|full\s+(?:table\s+)?dump"
    r"|all\s+data\s+ever"
    r"|entire\s+(?:database|history|table|dataset)"
    r"|without\s+(?:any\s+)?(?:filter|where)"
    r")\b",
    re.IGNORECASE,
)

_UNSAFE_REASONS = {
    "dml":  "Query contains a destructive DML/DDL operation. "
            "This system generates SELECT queries only.",
    "dump": "Query requests an unbounded bulk data operation. "
            "Add filters or aggregate criteria before proceeding.",
}


class RefusalEngine:
    """
    Classifies QueryPlanner results into priority-ordered, structured
    refusal or success responses.

    Usage
    -----
    engine = RefusalEngine()
    result = engine.classify(query, plan_result)
    if not result["should_generate_sql"]:
        print(result["failure_type"], result["reason"])
    """

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def classify(self, query: str, plan_result: dict) -> dict:
        """
        Produce a structured classification result from a planner output.

        Parameters
        ----------
        query       : original natural language query
        plan_result : full dict returned by QueryPlanner.plan()

        Returns
        -------
        dict with keys:
          status             : "SUCCESS" | "FAILURE"
          failure_type       : str | None
          reason             : str | None
          candidates         : list  — conflicting candidates (ambiguity types)
          recommendation     : str | None
          confidence         : float
          query              : str
          should_generate_sql: bool
          priority           : int | None  — priority rank of the failure type
        """
        # ── 1. UNSAFE_QUERY (independent check, highest priority) ──────────
        unsafe_reason = self._unsafe_reason(query)
        if unsafe_reason:
            return self._failure(
                query       = query,
                failure_type= "UNSAFE_QUERY",
                reason      = unsafe_reason,
                candidates  = [],
                recommendation = (
                    "Rephrase as a read-only analytical query. "
                    "Destructive operations are not supported."
                ),
                confidence  = 0.0,
            )

        # ── 2. Planner result — re-apply priority ordering ─────────────────
        planner_failure = plan_result.get("failure_type")
        confidence      = plan_result.get("final_confidence", 0.0)

        if plan_result.get("should_proceed", False):
            # Planner approved — success path
            return self._success(query, confidence, plan_result)

        # Map planner failure into structured response
        if not planner_failure:
            # should_proceed=False but no failure_type → treat as LOW_CONFIDENCE
            planner_failure = "LOW_CONFIDENCE"

        candidates    = self._extract_candidates(plan_result)
        reason        = plan_result.get("failure_reason") or plan_result.get("recommendation", "")
        recommendation = plan_result.get("recommendation", "")

        return self._failure(
            query          = query,
            failure_type   = planner_failure,
            reason         = reason,
            candidates     = candidates,
            recommendation = recommendation,
            confidence     = confidence,
        )

    def is_unsafe(self, query: str) -> bool:
        """Return True if the query matches any unsafe pattern."""
        return self._unsafe_reason(query) is not None

    def failure_priority(self, failure_type: str) -> int:
        """Return the priority rank for a failure type (lower = higher priority)."""
        return _PRIORITY.get(failure_type, 99)

    def highest_priority_failure(self, failure_types: List[str]) -> Optional[str]:
        """
        Given a list of failure type strings, return the one with the
        highest priority (lowest rank number).
        """
        if not failure_types:
            return None
        return min(failure_types, key=lambda ft: _PRIORITY.get(ft, 99))

    # ------------------------------------------------------------------ #
    # Unsafe query detection                                               #
    # ------------------------------------------------------------------ #

    def _unsafe_reason(self, query: str) -> Optional[str]:
        """Return a reason string if the query is unsafe, else None."""
        if _DML_PATTERN.search(query):
            return _UNSAFE_REASONS["dml"]
        if _DUMP_PATTERN.search(query):
            return _UNSAFE_REASONS["dump"]
        return None

    # ------------------------------------------------------------------ #
    # Response builders                                                    #
    # ------------------------------------------------------------------ #

    def _success(self, query: str, confidence: float, plan_result: dict) -> dict:
        level = plan_result.get("confidence_level", "confident")
        return {
            "status":              "SUCCESS",
            "failure_type":        None,
            "reason":              None,
            "candidates":          [],
            "recommendation":      plan_result.get("recommendation"),
            "confidence":          confidence,
            "confidence_level":    level,
            "query":               query,
            "should_generate_sql": True,
            "priority":            None,
            "warnings": (
                plan_result.get("execution_plan", {}) or {}
            ).get("warnings", []),
        }

    def _failure(
        self,
        query:          str,
        failure_type:   str,
        reason:         str,
        candidates:     list,
        recommendation: str,
        confidence:     float,
    ) -> dict:
        return {
            "status":              "FAILURE",
            "failure_type":        failure_type,
            "reason":              reason,
            "candidates":          candidates,
            "recommendation":      recommendation,
            "confidence":          confidence,
            "confidence_level":    "refuse",
            "query":               query,
            "should_generate_sql": False,
            "priority":            _PRIORITY.get(failure_type, 99),
            "warnings":            [],
        }

    # ------------------------------------------------------------------ #
    # Helper: extract candidate list from plan_result                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_candidates(plan_result: dict) -> list:
        """
        Pull conflicting candidates from step_results where available.
        Used by SEMANTIC_CONFLICT, AMBIGUOUS_JOIN, TEMPORAL_AMBIGUITY.
        """
        steps = plan_result.get("step_results", {})

        # From ambiguity detector
        ambiguity = steps.get("step5_ambiguity", {})
        if ambiguity.get("is_ambiguous"):
            return ambiguity.get("conflicts", [])

        # From join path (WEAK_JOIN / AMBIGUOUS_JOIN)
        join = steps.get("step4_join_paths", {})
        if join.get("join_paths"):
            return [
                {"from": e["from_model"], "to": e["to_model"], "score": e["score"]}
                for e in join["join_paths"]
            ]

        return []
