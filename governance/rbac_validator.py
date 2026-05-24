"""
governance/rbac_validator.py

Role-based access validation for resolved metadata models.
"""

import json
from pathlib import Path
from typing import Optional


_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "data" / "rbac_config.json"


class RbacValidator:
    """
    Validates model domain/tag access against a configured user role.
    """

    def __init__(self, config_path: Optional[str] = None):
        path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
        with open(path, "r", encoding="utf-8") as f:
            self.config = json.load(f)

    def validate(self, candidate_models, graph, user_role: str = "analyst") -> dict:
        role_cfg = self.config.get(user_role) or self.config["analyst"]
        allowed_domains = set(role_cfg.get("allowed_domains", []))
        blocked_tags = set(role_cfg.get("blocked_tags", []))

        violations = []
        blocked_models = []

        for model in candidate_models:
            node = graph.graph.nodes.get(model, {})
            domain = str(node.get("domain", "")).lower()
            tags = {str(tag).lower() for tag in node.get("tags", [])}

            domain_blocked = allowed_domains and domain not in allowed_domains
            tag_blocked = bool(tags & blocked_tags)

            if domain_blocked or tag_blocked:
                blocked_models.append(model)
                reason_parts = []
                if domain_blocked:
                    reason_parts.append(f"domain '{domain}' not allowed")
                if tag_blocked:
                    reason_parts.append(
                        "blocked tags: " + ", ".join(sorted(tags & blocked_tags))
                    )
                violations.append({
                    "model": model,
                    "reason": "; ".join(reason_parts),
                })

        blocked_models = sorted(set(blocked_models))
        blocked = bool(blocked_models)

        return {
            "blocked": blocked,
            "violations": violations,
            "blocked_models": blocked_models,
            "governance_safety_score": 0.0 if blocked else 1.0,
            "reason": (
                "RBAC restriction on model(s): " + ", ".join(blocked_models) + "."
                if blocked_models else None
            ),
            "recommendation": (
                f"Use a role with access to the requested domain/models or "
                f"remove restricted models from the query."
                if blocked else None
            ),
        }
