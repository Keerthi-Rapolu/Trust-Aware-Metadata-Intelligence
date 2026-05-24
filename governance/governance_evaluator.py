"""
governance/governance_evaluator.py

Shared governance aggregation used by QueryPlanner and Phase 7 agents.
"""

from typing import List, Optional

from governance.pii_detector import PiiDetector
from governance.query_cost_estimator import QueryCostEstimator
from governance.rbac_validator import RbacValidator


class GovernanceEvaluator:
    """
    Aggregates the deterministic Phase 5 governance modules.
    """

    def __init__(
        self,
        graph,
        user_role: str = "analyst",
        rbac_config_path: Optional[str] = None,
        max_scan_gb: float = 500.0,
    ) -> None:
        self.graph = graph
        self.user_role = user_role
        self._pii = PiiDetector()
        self._rbac = RbacValidator(config_path=rbac_config_path)
        self._cost = QueryCostEstimator(max_scan_gb=max_scan_gb)

    def evaluate(
        self,
        query: str,
        candidate_models: List[str],
        extraction: Optional[dict] = None,
    ) -> dict:
        pii = self._pii.detect(query, candidate_models, self.graph)
        rbac = self._rbac.validate(candidate_models, self.graph, self.user_role)
        cost = self._cost.estimate(query, candidate_models, self.graph)

        module_scores = {
            "pii": pii["governance_safety_score"],
            "rbac": rbac["governance_safety_score"],
            "cost": cost["governance_safety_score"],
        }
        score = min(module_scores.values()) if module_scores else 1.0
        blocked = any(result["blocked"] for result in (pii, rbac, cost))

        reasons = [
            result["reason"]
            for result in (pii, rbac, cost)
            if result.get("reason")
        ]
        recommendations = [
            result["recommendation"]
            for result in (pii, rbac, cost)
            if result.get("recommendation")
        ]

        return {
            "blocked": blocked,
            "score": score,
            "reason": reasons[0] if reasons else None,
            "recommendation": recommendations[0] if recommendations else None,
            "blocked_cols": pii.get("pii_columns_detected", []),
            "restricted_columns": pii.get("restricted_columns", []),
            "blocked_models": sorted(
                set(pii.get("blocked_models", [])) | set(rbac.get("blocked_models", []))
            ),
            "unsafe_patterns_detected": cost.get("unsafe_patterns_detected", []),
            "estimated_scan_gb": cost.get("estimated_scan_gb", 0.0),
            "module_scores": module_scores,
            "module_results": {
                "pii": pii,
                "rbac": rbac,
                "cost": cost,
            },
            "extraction": extraction or {},
        }
