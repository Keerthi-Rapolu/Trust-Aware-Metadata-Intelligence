"""
reasoning/query_planner.py

Orchestrates the full 10-step Semantic Query Planning Pipeline before
any LLM interaction.

Design reference:
  EXPANSION_DESIGN.md §6 — Semantic Query Planning Engine

Pipeline steps
--------------
  1   Parse query intent (IntentClassifier)
  2   Extract entities from glossary (EntityExtractor)
  3   Validate entities against live graph
  4   Find join paths (JoinPathEngine)
  5   Detect ambiguity (AmbiguityDetector)
  6   Check governance constraints
  7   Compute retrieval score
  8   Propagate confidence (ConfidenceScorer)
  9   Build structured execution plan
  10  Gate: proceed / warn / clarify / refuse

The LLM receives ONLY the structured execution plan — never raw metadata.
"""

from typing import Callable, List, Optional

from ingestion.graph_store import MetadataGraph
from reasoning.intent_classifier  import IntentClassifier
from reasoning.entity_extractor   import EntityExtractor
from reasoning.join_path_engine   import JoinPathEngine
from reasoning.ambiguity_detector import AmbiguityDetector
from reasoning.confidence_scorer  import ConfidenceScorer
from retrieval.semantic_retriever import SemanticRetriever
from governance.governance_evaluator import GovernanceEvaluator
from explainability.formatter import ExplainabilityFormatter


class QueryPlanner:
    """
    Deterministic reasoning layer sitting between the user query and LLM.

    Parameters
    ----------
    graph     : MetadataGraph
    glossary  : dict  (loaded from data/glossary.json)
    embed_fn  : optional embedding callable
    """

    def __init__(
        self,
        graph:    MetadataGraph,
        glossary: dict,
        embed_fn: Optional[Callable] = None,
        user_role: str = "analyst",
        rbac_config_path: Optional[str] = None,
        max_scan_gb: float = 500.0,
    ):
        self.graph    = graph
        self.glossary = glossary
        self.user_role = user_role
        self._intent     = IntentClassifier()
        self._extractor  = EntityExtractor(glossary, graph, embed_fn)
        self._join_engine = JoinPathEngine(graph, embed_fn)
        self._ambiguity  = AmbiguityDetector()
        self._confidence = ConfidenceScorer()
        self._retriever  = SemanticRetriever(graph, glossary, embed_fn)
        self._governance = GovernanceEvaluator(
            graph=graph,
            user_role=user_role,
            rbac_config_path=rbac_config_path,
            max_scan_gb=max_scan_gb,
        )
        self._explainability = ExplainabilityFormatter()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def plan(self, query: str) -> dict:
        """
        Run the full 10-step planning pipeline for a natural language query.

        Returns
        -------
        dict — the structured execution plan:
          query                 : str
          step_results          : dict — intermediate output of each step
          execution_plan        : dict — structured plan for the LLM
          final_confidence      : float
          confidence_level      : str ("confident"|"warn"|"ambiguous"|"refuse")
          should_proceed        : bool
          failure_type          : str | None
          failure_reason        : str | None
          recommendation        : str | None
        """
        steps = {}

        # ── Step 1: Parse query intent ────────────────────────────────────
        intent_result = self._intent.classify(query)
        steps["step1_intent"] = intent_result

        # ── Step 2: Extract entities ──────────────────────────────────────
        extraction = self._extractor.extract(query)
        steps["step2_extraction"] = extraction

        # ── Step 3: Validate entities against live graph ──────────────────
        candidate_models = extraction["candidate_models"]
        validation = self._validate_models(candidate_models)
        steps["step3_validation"] = validation

        if not candidate_models:
            return self._refuse(
                query, steps,
                failure_type   = "INSUFFICIENT_SCHEMA",
                failure_reason = "No recognised models found for query entities.",
                recommendation = (
                    "Check that entity terms appear in the business glossary "
                    "and the graph contains the relevant models."
                ),
            )

        # ── Step 3.5: Governance check (runs BEFORE ambiguity — hard stop) ─
        # Design §9: GOVERNANCE_BLOCKED always takes highest priority.
        governance = self._governance_check(
            extraction=extraction,
            query=query,
            candidate_models=candidate_models,
        )
        steps["step6_governance"] = governance   # key kept for API compatibility

        if governance["blocked"]:
            return self._refuse(
                query, steps,
                failure_type   = "GOVERNANCE_BLOCKED",
                failure_reason = governance["reason"],
                recommendation = governance["recommendation"],
            )

        # ── Step 4: Find join paths ───────────────────────────────────────
        join_result = self._join_engine.find_join_paths(candidate_models)
        steps["step4_join_paths"] = join_result

        if not join_result["all_models_resolved"] and len(candidate_models) > 1:
            return self._refuse(
                query, steps,
                failure_type   = "WEAK_JOIN",
                failure_reason = join_result.get("ambiguity_reason", "No join path found between candidate models."),
                recommendation = "Verify lineage connections between required models.",
            )

        # ── Step 5: Detect ambiguity ──────────────────────────────────────
        ambiguity = self._ambiguity.detect_all(extraction, candidate_models, self.graph)
        steps["step5_ambiguity"] = ambiguity

        if ambiguity["is_ambiguous"]:
            return self._clarify(
                query, steps,
                ambiguity_type = ambiguity["ambiguity_type"],
                conflicts      = ambiguity["conflicts"],
                recommendation = ambiguity["recommendation"],
            )

        # ── Step 7: Compute retrieval score ───────────────────────────────
        retrieval_result = self._retriever.retrieve(query, candidate_models)
        retrieval_score = self._aggregate_retrieval_score(retrieval_result)
        steps["step7_retrieval"] = retrieval_result
        steps["step7_retrieval_score"] = retrieval_score

        ordered_models = [
            item["candidate"] for item in retrieval_result.get("rankings", [])
        ] or candidate_models

        # ── Step 8: Propagate confidence ──────────────────────────────────
        completeness = self._confidence.aggregate_completeness(
            candidate_models, self.graph
        )
        confidence_result = self._confidence.score(
            retrieval_score    = retrieval_score,
            join_confidence    = join_result["overall_confidence"],
            governance_score   = governance["score"],
            completeness_score = completeness,
            intent_clarity     = intent_result["intent_clarity_weight"],
        )
        steps["step8_confidence"] = confidence_result

        if confidence_result["confidence_level"] == "refuse":
            return self._refuse(
                query, steps,
                failure_type   = "LOW_CONFIDENCE",
                failure_reason = confidence_result["recommendation"],
                recommendation = confidence_result["recommendation"],
                final_confidence = confidence_result["final_confidence"],
            )

        # ── Step 9: Build structured execution plan ───────────────────────
        execution_plan = self._build_execution_plan(
            query, intent_result, extraction, join_result,
            confidence_result, governance, ordered_models, retrieval_result
        )
        steps["step9_execution_plan"] = execution_plan

        # ── Step 10: Gate decision ────────────────────────────────────────
        level = confidence_result["confidence_level"]
        should_proceed = level in ("confident", "warn")

        result = {
            "query":            query,
            "step_results":     steps,
            "execution_plan":   execution_plan,
            "final_confidence": confidence_result["final_confidence"],
            "confidence_level": level,
            "should_proceed":   should_proceed,
            "failure_type":     None,
            "failure_reason":   None,
            "recommendation":   confidence_result["recommendation"],
        }
        return self._attach_explainability(result)

    # ------------------------------------------------------------------ #
    # Step implementations                                                 #
    # ------------------------------------------------------------------ #

    def _validate_models(self, candidate_models: List[str]) -> dict:
        """Check that each candidate model exists in the live graph."""
        valid_models = set(self.graph.all_models())
        missing = [m for m in candidate_models if m not in valid_models]
        return {
            "valid":   len(missing) == 0,
            "missing": missing,
            "present": [m for m in candidate_models if m in valid_models],
        }

    def _governance_check(
        self,
        extraction: dict,
        query: str,
        candidate_models: List[str],
    ) -> dict:
        """
        Phase 5 governance evaluation.

        This still runs before ambiguity handling so GOVERNANCE_BLOCKED
        preserves top priority over semantic and join-related failures.
        """
        return self._governance.evaluate(
            query=query,
            candidate_models=candidate_models,
            extraction=extraction,
        )

    @staticmethod
    def _aggregate_retrieval_score(retrieval_result: dict) -> float:
        """
        Collapse per-model retrieval rankings into one plan-level confidence.
        For multi-model plans this uses the mean composite score so the plan
        reflects support across all required models, not just the strongest hit.
        """
        rankings = retrieval_result.get("rankings", [])
        if not rankings:
            return 0.0
        return round(
            sum(item["final_score"] for item in rankings) / len(rankings), 4
        )

    def _build_execution_plan(
        self,
        query:            str,
        intent_result:    dict,
        extraction:       dict,
        join_result:      dict,
        confidence_result: dict,
        governance:       dict,
        ordered_models:   List[str],
        retrieval_result: dict,
    ) -> dict:
        """
        Assemble the structured execution plan that the SQL generator / LLM will use.
        """
        entities   = extraction["entities_extracted"]
        candidate_models = ordered_models

        # Collect columns per model from entities
        model_columns: dict = {}
        for e in entities:
            for m in e.get("candidate_models", []):
                model_columns.setdefault(m, []).extend(e.get("candidate_columns", []))
        # Dedup per model
        model_columns = {m: list(dict.fromkeys(cols)) for m, cols in model_columns.items()}

        return {
            "query":             query,
            "intent":            intent_result["intent"],
            "time_grain":        intent_result.get("time_grain"),
            "candidate_models":  candidate_models,
            "model_columns":     model_columns,
            "join_path":         join_result["join_paths"],
            "retrieval_rankings": retrieval_result.get("rankings", []),
            "retrieval_score":   self._aggregate_retrieval_score(retrieval_result),
            "entities":          [
                {
                    "term":   e["term"],
                    "columns": e.get("candidate_columns", []),
                    "models":  e.get("candidate_models", []),
                }
                for e in entities
            ],
            "confidence":        confidence_result["final_confidence"],
            "confidence_level":  confidence_result["confidence_level"],
            "governance_clear":  not governance["blocked"],
            "warnings":          (
                [f"Moderate confidence (weakest: {confidence_result['weakest_factor']})"]
                if confidence_result["confidence_level"] == "warn"
                else []
            ),
        }

    # ------------------------------------------------------------------ #
    # Terminal-state helpers                                               #
    # ------------------------------------------------------------------ #

    def _refuse(
        self, query: str, steps: dict,
        failure_type: str, failure_reason: str, recommendation: str,
        final_confidence: float = 0.0,
    ) -> dict:
        result = {
            "query":            query,
            "step_results":     steps,
            "execution_plan":   None,
            "final_confidence": final_confidence,
            "confidence_level": "refuse",
            "should_proceed":   False,
            "failure_type":     failure_type,
            "failure_reason":   failure_reason,
            "recommendation":   recommendation,
        }
        return self._attach_explainability(result)

    def _clarify(
        self, query: str, steps: dict,
        ambiguity_type: str, conflicts: list, recommendation: str
    ) -> dict:
        result = {
            "query":            query,
            "step_results":     steps,
            "execution_plan":   None,
            "final_confidence": 0.0,
            "confidence_level": "ambiguous",
            "should_proceed":   False,
            "failure_type":     ambiguity_type,
            "failure_reason":   recommendation,
            "recommendation":   recommendation,
        }
        return self._attach_explainability(result)

    def _attach_explainability(self, result: dict) -> dict:
        explanation_json = self._explainability.format_json(result)
        explanation_text = self._explainability.format_text(result, explanation_json)

        result["explanations"] = explanation_json
        result["explanation_text"] = explanation_text

        execution_plan = result.get("execution_plan")
        if execution_plan is not None:
            execution_plan["retrieval_explanation"] = explanation_json["retrieval_explanation"]
            execution_plan["join_explanation"] = explanation_json["join_explanation"]
            execution_plan["confidence_explanation"] = explanation_json["confidence_explanation"]
            execution_plan["refusal_explanation"] = explanation_json["refusal_explanation"]
            execution_plan["explanation_text"] = explanation_text

        return result
