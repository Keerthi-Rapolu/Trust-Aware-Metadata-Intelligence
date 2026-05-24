"""
explainability/formatter.py

Structured and human-readable explanations for planner outcomes.
"""

from typing import List


class ExplainabilityFormatter:
    """Build explainability payloads for planner outcomes."""

    def format_json(self, plan_result: dict) -> dict:
        steps = plan_result.get("step_results", {}) or {}
        exec_plan = plan_result.get("execution_plan") or {}
        failure_type = plan_result.get("failure_type")
        failure_reason = plan_result.get("failure_reason")

        retrieval = self._retrieval_explanation(plan_result, exec_plan, steps)
        join = self._join_explanation(plan_result, steps)
        confidence = self._confidence_explanation(plan_result, steps)
        refusal = self._refusal_explanation(plan_result, failure_type, failure_reason)

        return {
            "selected_tables": retrieval["selected_tables"],
            "retrieval_scores": retrieval["retrieval_scores"],
            "join_path": join["join_path_text"],
            "join_confidence": join["join_confidence"],
            "confidence_limiting_factor": confidence["confidence_limiting_factor"],
            "overall_confidence": confidence["overall_confidence"],
            "refusal_type": refusal["failure_type"],
            "refusal_reason": refusal["reason"],
            "explanation": self._summary_text(retrieval, join, confidence, refusal),
            "retrieval_explanation": retrieval,
            "join_explanation": join,
            "confidence_explanation": confidence,
            "refusal_explanation": refusal,
        }

    def format_text(self, plan_result: dict, explanation_json: dict | None = None) -> str:
        payload = explanation_json or self.format_json(plan_result)
        parts = [
            payload["retrieval_explanation"]["explanation"],
            payload["join_explanation"]["explanation"],
            payload["confidence_explanation"]["explanation"],
            payload["refusal_explanation"]["explanation"],
        ]
        return " ".join(part for part in parts if part).strip()

    def _retrieval_explanation(self, plan_result: dict, exec_plan: dict, steps: dict) -> dict:
        retrieval = steps.get("step7_retrieval")
        selected_tables = exec_plan.get("candidate_models", [])

        if not retrieval:
            return {
                "status": "not_reached",
                "selected_tables": selected_tables,
                "retrieval_scores": {},
                "top_candidate": None,
                "factor_breakdown": {},
                "explanation": self._not_reached_reason("retrieval ranking", plan_result),
            }

        rankings = retrieval.get("rankings", [])
        retrieval_scores = {
            item["candidate"]: item["final_score"]
            for item in rankings
        }
        factor_breakdown = {
            item["candidate"]: item.get("scores", {})
            for item in rankings
        }
        ranked_text = ", ".join(
            f"{name} ({score:.2f})"
            for name, score in retrieval_scores.items()
        )
        return {
            "status": "evaluated",
            "selected_tables": selected_tables or list(retrieval_scores.keys()),
            "retrieval_scores": retrieval_scores,
            "top_candidate": retrieval.get("top_candidate"),
            "factor_breakdown": factor_breakdown,
            "explanation": (
                f"Selected tables: {ranked_text or 'none'}. "
                "Composite retrieval blended semantic similarity, lineage, glossary, "
                "history, and governance compatibility."
            ),
        }

    def _join_explanation(self, plan_result: dict, steps: dict) -> dict:
        join = steps.get("step4_join_paths")
        if not join:
            return {
                "status": "not_reached",
                "join_path": [],
                "join_path_text": "not evaluated",
                "join_confidence": 0.0,
                "ambiguity_detected": False,
                "explanation": self._not_reached_reason("join path analysis", plan_result),
            }

        join_strings = [
            edge.get("join_string", f"{edge.get('from_model')} -> {edge.get('to_model')}")
            for edge in join.get("join_paths", [])
        ]
        if not join_strings:
            join_text = "single model — no joins required"
            explanation = (
                "No join path was required because the query resolved to a single model."
            )
        else:
            join_text = " | ".join(join_strings)
            explanation = (
                f"Chosen join path: {join_text}. "
                f"Join confidence is {join.get('overall_confidence', 0.0):.2f}."
            )

        return {
            "status": "evaluated",
            "join_path": join_strings,
            "join_path_text": join_text,
            "join_confidence": join.get("overall_confidence", 0.0),
            "ambiguity_detected": join.get("ambiguity_detected", False),
            "explanation": explanation,
        }

    def _confidence_explanation(self, plan_result: dict, steps: dict) -> dict:
        confidence = steps.get("step8_confidence")
        overall_confidence = plan_result.get("final_confidence", 0.0)

        if not confidence:
            return {
                "status": "not_reached",
                "overall_confidence": overall_confidence,
                "confidence_level": plan_result.get("confidence_level", "refuse"),
                "confidence_limiting_factor": "not_evaluated",
                "component_scores": {},
                "explanation": self._not_reached_reason("confidence propagation", plan_result),
            }

        overall_confidence = confidence.get("final_confidence", overall_confidence)
        weakest = confidence.get("weakest_factor", "unknown")
        component_scores = confidence.get("component_scores", {})
        limiting_factor = weakest
        if overall_confidence >= 0.85 and all(
            score >= 0.85 for score in component_scores.values()
        ):
            limiting_factor = "none"

        if limiting_factor == "none":
            explanation = (
                f"Overall confidence is {overall_confidence:.2f}. "
                "No material limiting factor was detected."
            )
        else:
            explanation = (
                f"Overall confidence is {overall_confidence:.2f}. "
                f"The limiting factor is {limiting_factor}."
            )

        return {
            "status": "evaluated",
            "overall_confidence": overall_confidence,
            "confidence_level": confidence.get(
                "confidence_level",
                plan_result.get("confidence_level", ""),
            ),
            "confidence_limiting_factor": limiting_factor,
            "component_scores": component_scores,
            "explanation": explanation,
        }

    def _refusal_explanation(
        self,
        plan_result: dict,
        failure_type: str | None,
        failure_reason: str | None,
    ) -> dict:
        if failure_type:
            return {
                "status": "triggered",
                "failure_type": failure_type,
                "reason": failure_reason,
                "recommendation": plan_result.get("recommendation"),
                "explanation": (
                    f"Planning stopped with {failure_type}: "
                    f"{failure_reason or 'no reason provided'}."
                ),
            }

        return {
            "status": "clear",
            "failure_type": None,
            "reason": None,
            "recommendation": plan_result.get("recommendation"),
            "explanation": "No refusal triggered. Planner approved SQL generation.",
        }

    @staticmethod
    def _not_reached_reason(stage: str, plan_result: dict) -> str:
        failure_type = plan_result.get("failure_type")
        if failure_type:
            return (
                f"{stage.capitalize()} was skipped because planning stopped with "
                f"{failure_type}."
            )
        return f"{stage.capitalize()} was not evaluated."

    @staticmethod
    def _summary_text(
        retrieval: dict,
        join: dict,
        confidence: dict,
        refusal: dict,
    ) -> str:
        parts: List[str] = [
            retrieval.get("explanation", ""),
            join.get("explanation", ""),
            confidence.get("explanation", ""),
            refusal.get("explanation", ""),
        ]
        return " ".join(part for part in parts if part).strip()
