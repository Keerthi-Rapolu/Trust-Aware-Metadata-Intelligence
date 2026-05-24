"""
governance/pii_detector.py

Detects hard and soft PII/governance violations from the resolved models
and raw query text before SQL generation.
"""

import re
from typing import Dict, List

_HARD_MODEL_TAGS = frozenset({"pci", "restricted", "confidential"})
_HARD_COLUMN_HINTS = frozenset({
    "ssn", "social_security", "social security", "tax_id", "tax id",
    "credit_card", "credit card", "account_number", "account number",
    "iban",
})
_SOFT_COLUMN_HINTS = frozenset({
    "email", "email_address", "email address",
    "phone", "phone_number", "phone number", "mobile",
    "date_of_birth", "date of birth", "dob",
})
_SOFT_PII_TYPES = frozenset({"email", "phone", "dob"})
_HARD_PII_TYPES = frozenset({
    "ssn", "social_security", "tax_id", "credit_card", "account_number", "iban"
})


class PiiDetector:
    """
    Classifies PII and restricted-data exposure risk.

    Hard stop:
      - model tagged pci/restricted/confidential
      - explicit hard-PII columns requested

    Soft warning:
      - personal-contact style columns such as email/phone/dob requested
    """

    def detect(self, query: str, candidate_models: List[str], graph) -> dict:
        query_norm = self._normalise_text(query)
        query_tokens = set(query_norm.split())

        blocked_models: List[str] = []
        blocked_columns: List[str] = []
        restricted_columns: List[str] = []

        for model in candidate_models:
            node = graph.graph.nodes.get(model, {})
            node_tags = {str(tag).lower() for tag in node.get("tags", [])}

            if node_tags & _HARD_MODEL_TAGS:
                blocked_models.append(model)
                continue

            column_info = node.get("column_info", {})
            for column, meta in column_info.items():
                if not self._column_requested(column, query_norm, query_tokens):
                    continue

                pii_type = str(meta.get("pii_type") or "").lower().strip()
                column_ref = f"{model}.{column}"

                if self._is_hard_column(column, pii_type):
                    blocked_columns.append(column_ref)
                elif self._is_soft_column(column, pii_type, meta):
                    restricted_columns.append(column_ref)

        blocked_models = sorted(set(blocked_models))
        blocked_columns = sorted(set(blocked_columns))
        restricted_columns = sorted(set(restricted_columns))

        if blocked_models or blocked_columns:
            reasons = []
            if blocked_models:
                reasons.append(
                    "restricted model access: " + ", ".join(blocked_models)
                )
            if blocked_columns:
                reasons.append(
                    "hard-PII columns requested: " + ", ".join(blocked_columns)
                )
            return {
                "blocked": True,
                "severity": "hard",
                "pii_columns_detected": blocked_columns,
                "blocked_models": blocked_models,
                "restricted_columns": restricted_columns,
                "governance_safety_score": 0.0,
                "reason": "Governance hard-stop triggered by " + "; ".join(reasons) + ".",
                "recommendation": (
                    "Remove restricted models or hard-PII columns from the query "
                    "before proceeding."
                ),
            }

        if restricted_columns:
            return {
                "blocked": False,
                "severity": "soft",
                "pii_columns_detected": [],
                "blocked_models": [],
                "restricted_columns": restricted_columns,
                "governance_safety_score": 0.5,
                "reason": (
                    "Soft-governance warning: personal data columns requested: "
                    + ", ".join(restricted_columns) + "."
                ),
                "recommendation": (
                    "Verify that personal data access is appropriate and limit the "
                    "result set if possible."
                ),
            }

        return {
            "blocked": False,
            "severity": "none",
            "pii_columns_detected": [],
            "blocked_models": [],
            "restricted_columns": [],
            "governance_safety_score": 1.0,
            "reason": None,
            "recommendation": None,
        }

    @staticmethod
    def _normalise_text(text: str) -> str:
        text = text.lower().replace("_", " ")
        text = re.sub(r"[^a-z0-9 ]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _column_requested(self, column: str, query_norm: str, query_tokens: set) -> bool:
        col_norm = self._normalise_text(column)
        if col_norm in query_norm:
            return True

        parts = [part for part in col_norm.split() if part]
        if len(parts) > 1 and all(part in query_tokens for part in parts):
            return True

        return any(
            part in query_tokens
            for part in parts
            if part in {"email", "phone", "mobile", "ssn", "iban", "dob"}
        )

    @staticmethod
    def _is_hard_column(column: str, pii_type: str) -> bool:
        col = column.lower()
        return pii_type in _HARD_PII_TYPES or any(hint in col for hint in _HARD_COLUMN_HINTS)

    @staticmethod
    def _is_soft_column(column: str, pii_type: str, meta: Dict) -> bool:
        col = column.lower()
        tags = {str(tag).lower() for tag in meta.get("tags", [])}
        return (
            bool(meta.get("pii"))
            or pii_type in _SOFT_PII_TYPES
            or any(hint in col for hint in _SOFT_COLUMN_HINTS)
            or "personal_data" in tags
        )
