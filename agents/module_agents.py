"""
agents/module_agents.py

Thin Phase 7 wrappers over existing pipeline modules.
"""

from typing import Dict, List, Optional

from agents.contracts import AgentContract, BaseAgent
from generation.refusal_engine import RefusalEngine
from generation.sql_generator import SqlGenerator
from governance.governance_evaluator import GovernanceEvaluator
from reasoning.confidence_scorer import ConfidenceScorer
from reasoning.join_path_engine import JoinPathEngine
from reasoning.query_planner import QueryPlanner
from retrieval.embedding_ranker import EmbeddingRanker


class RetrievalAgent(BaseAgent):
    contract = AgentContract(
        agent_name="retrieval",
        wrapped_modules=("retrieval.embedding_ranker.EmbeddingRanker",),
        description="Ranks candidate models using the existing composite retrieval module.",
    )

    def __init__(self, ranker: EmbeddingRanker) -> None:
        self._ranker = ranker

    def run(
        self,
        query: str,
        candidates: List[str],
        selected_models: Optional[List[str]] = None,
        query_history: Optional[Dict[str, float]] = None,
    ) -> dict:
        return self._ranker.rank(
            query,
            candidates,
            selected_models=selected_models,
            query_history=query_history,
        )


class PlanningAgent(BaseAgent):
    contract = AgentContract(
        agent_name="planning",
        wrapped_modules=("reasoning.query_planner.QueryPlanner",),
        description="Runs the deterministic planning pipeline without adding new logic.",
    )

    def __init__(self, planner: QueryPlanner) -> None:
        self._planner = planner

    def run(self, query: str) -> dict:
        return self._planner.plan(query)


class JoinReasoningAgent(BaseAgent):
    contract = AgentContract(
        agent_name="join_reasoning",
        wrapped_modules=("reasoning.join_path_engine.JoinPathEngine",),
        description="Delegates join-path selection to the existing join engine.",
    )

    def __init__(self, join_engine: JoinPathEngine) -> None:
        self._join_engine = join_engine

    def run(self, models: List[str]) -> dict:
        return self._join_engine.find_join_paths(models)


class GovernanceAgent(BaseAgent):
    contract = AgentContract(
        agent_name="governance",
        wrapped_modules=(
            "governance.pii_detector.PiiDetector",
            "governance.rbac_validator.RbacValidator",
            "governance.query_cost_estimator.QueryCostEstimator",
        ),
        description="Evaluates deterministic governance modules and returns their aggregate result.",
    )

    def __init__(self, evaluator: GovernanceEvaluator) -> None:
        self._evaluator = evaluator

    def run(
        self,
        query: str,
        candidate_models: List[str],
        extraction: Optional[dict] = None,
    ) -> dict:
        return self._evaluator.evaluate(
            query=query,
            candidate_models=candidate_models,
            extraction=extraction,
        )


class SQLGenerationAgent(BaseAgent):
    contract = AgentContract(
        agent_name="sql_generation",
        wrapped_modules=("generation.sql_generator.SqlGenerator",),
        description="Generates SQL strictly from the existing execution-plan generator.",
    )

    def __init__(self, generator: SqlGenerator) -> None:
        self._generator = generator

    def run(self, plan_result: dict) -> dict:
        return self._generator.generate(plan_result)


class EvaluationAgent(BaseAgent):
    contract = AgentContract(
        agent_name="evaluation",
        wrapped_modules=(
            "reasoning.confidence_scorer.ConfidenceScorer",
            "generation.refusal_engine.RefusalEngine",
        ),
        description="Reuses the existing confidence scorer and refusal engine for final evaluation.",
    )

    def __init__(
        self,
        confidence_scorer: Optional[ConfidenceScorer] = None,
        refusal_engine: Optional[RefusalEngine] = None,
    ) -> None:
        self._confidence = confidence_scorer or ConfidenceScorer()
        self._refusal = refusal_engine or RefusalEngine()

    def classify(self, query: str, plan_result: dict) -> dict:
        return self._refusal.classify(query, plan_result)

    def recompute_confidence(self, plan_result: dict) -> Optional[dict]:
        step8 = (plan_result.get("step_results", {}) or {}).get("step8_confidence")
        if not step8:
            return None

        components = step8.get("component_scores", {})
        return self._confidence.score(
            retrieval_score=components.get("retrieval", 1.0),
            join_confidence=components.get("join_path", 1.0),
            governance_score=components.get("governance", 1.0),
            completeness_score=components.get("completeness", 1.0),
            intent_clarity=components.get("intent_clarity", 1.0),
        )

    def run(self, query: str, plan_result: dict) -> dict:
        return {
            "classification": self.classify(query, plan_result),
            "confidence_review": self.recompute_confidence(plan_result),
        }
