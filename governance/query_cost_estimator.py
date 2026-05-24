"""
governance/query_cost_estimator.py

Detects unbounded scan risk from the resolved models and user query.
"""

import re


class QueryCostEstimator:
    """
    Estimates scan size and blocks obviously unsafe full-history scans.
    """

    def __init__(self, max_scan_gb: float = 500.0):
        self.max_scan_gb = float(max_scan_gb)

    def estimate(self, query: str, candidate_models, graph) -> dict:
        query_norm = query.lower()
        has_time_filter = self._has_time_filter(query_norm)
        asks_for_everything = self._asks_for_everything(query_norm)

        estimated_scan_gb = 0.0
        unsafe_patterns = []

        for model in candidate_models:
            node = graph.graph.nodes.get(model, {})
            full_scan_gb = node.get("estimated_scan_gb")
            partition_column = node.get("partition_column")

            if full_scan_gb is None:
                continue

            estimated_scan_gb = max(estimated_scan_gb, float(full_scan_gb))

            if asks_for_everything:
                unsafe_patterns.append(f"unbounded_model_scan:{model}")

            if partition_column and not has_time_filter:
                unsafe_patterns.append(
                    f"missing_partition_filter:{model}.{partition_column}"
                )

        unsafe_patterns = sorted(set(unsafe_patterns))
        blocked = bool(unsafe_patterns) and estimated_scan_gb > self.max_scan_gb

        if blocked:
            return {
                "blocked": True,
                "estimated_scan_gb": round(estimated_scan_gb, 2),
                "unsafe_patterns_detected": unsafe_patterns,
                "governance_safety_score": 0.0,
                "reason": (
                    f"Estimated scan {estimated_scan_gb:.2f}GB exceeds threshold "
                    f"{self.max_scan_gb:.2f}GB."
                ),
                "recommendation": (
                    "Add a date filter or narrower business constraint before "
                    "querying large partitioned models."
                ),
            }

        return {
            "blocked": False,
            "estimated_scan_gb": round(estimated_scan_gb, 2),
            "unsafe_patterns_detected": unsafe_patterns,
            "governance_safety_score": 1.0,
            "reason": None,
            "recommendation": None,
        }

    @staticmethod
    def _has_time_filter(query_norm: str) -> bool:
        time_words = {
            "today", "yesterday", "week", "month", "quarter", "year",
            "daily", "weekly", "monthly", "quarterly", "annual",
            "last", "this", "previous", "since", "between", "before", "after",
        }
        if re.search(r"\b20\d{2}\b", query_norm):
            return True
        return any(word in query_norm for word in time_words)

    @staticmethod
    def _asks_for_everything(query_norm: str) -> bool:
        patterns = (
            "everything", "all data", "all records", "full history",
            "history", "all payments", "all orders", "all customers",
            "show all", "list all", "give me everything",
        )
        return any(pattern in query_norm for pattern in patterns)
