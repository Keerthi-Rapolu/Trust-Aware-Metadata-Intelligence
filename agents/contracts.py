"""
agents/contracts.py

Explicit interface metadata for thin module-wrapping agents.
"""

from dataclasses import dataclass
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class AgentContract:
    agent_name: str
    wrapped_modules: Tuple[str, ...]
    description: str


class BaseAgent:
    """Common metadata and trace helpers for all Phase 7 agents."""

    contract: AgentContract

    def describe(self) -> Dict[str, Any]:
        return {
            "agent_name": self.contract.agent_name,
            "wrapped_modules": list(self.contract.wrapped_modules),
            "description": self.contract.description,
        }

    def trace(self, input_payload: Dict[str, Any], output_payload: Any) -> Dict[str, Any]:
        return {
            **self.describe(),
            "input": input_payload,
            "output": output_payload,
        }
