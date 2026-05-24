"""
agents/orchestrator.py

Sequential, non-autonomous Phase 7 orchestration over the existing modules.
"""

from typing import Callable, Dict, Optional

from agents.module_agents import (
    EvaluationAgent,
    GovernanceAgent,
    JoinReasoningAgent,
    PlanningAgent,
    RetrievalAgent,
    SQLGenerationAgent,
)
from generation.refusal_engine import RefusalEngine
from generation.sql_generator import SqlGenerator
from governance.governance_evaluator import GovernanceEvaluator
from reasoning.confidence_scorer import ConfidenceScorer
from reasoning.join_path_engine import JoinPathEngine
from reasoning.query_planner import QueryPlanner
from retrieval.embedding_ranker import EmbeddingRanker


class SequentialAgentOrchestrator:
    """
    Optional Phase 7 wrapper that preserves the direct-pipeline outputs.
    """

    def __init__(
        self,
        planning_agent: PlanningAgent,
        retrieval_agent: RetrievalAgent,
        join_agent: JoinReasoningAgent,
        governance_agent: GovernanceAgent,
        sql_generation_agent: SQLGenerationAgent,
        evaluation_agent: EvaluationAgent,
    ) -> None:
        self.planning_agent = planning_agent
        self.retrieval_agent = retrieval_agent
        self.join_agent = join_agent
        self.governance_agent = governance_agent
        self.sql_generation_agent = sql_generation_agent
        self.evaluation_agent = evaluation_agent

    @classmethod
    def from_components(
        cls,
        graph,
        glossary: dict,
        embed_fn: Optional[Callable] = None,
        llm_fn: Optional[Callable] = None,
        user_role: str = "analyst",
        rbac_config_path: Optional[str] = None,
        max_scan_gb: float = 500.0,
    ) -> "SequentialAgentOrchestrator":
        planner = QueryPlanner(
            graph=graph,
            glossary=glossary,
            embed_fn=embed_fn,
            user_role=user_role,
            rbac_config_path=rbac_config_path,
            max_scan_gb=max_scan_gb,
        )
        ranker = EmbeddingRanker(graph, glossary, embed_fn)
        join_engine = JoinPathEngine(graph, embed_fn)
        governance = GovernanceEvaluator(
            graph=graph,
            user_role=user_role,
            rbac_config_path=rbac_config_path,
            max_scan_gb=max_scan_gb,
        )
        generator = SqlGenerator(llm_fn=llm_fn)
        evaluation = EvaluationAgent(
            confidence_scorer=ConfidenceScorer(),
            refusal_engine=RefusalEngine(),
        )
        return cls(
            planning_agent=PlanningAgent(planner),
            retrieval_agent=RetrievalAgent(ranker),
            join_agent=JoinReasoningAgent(join_engine),
            governance_agent=GovernanceAgent(governance),
            sql_generation_agent=SQLGenerationAgent(generator),
            evaluation_agent=evaluation,
        )

    def run(self, query: str) -> dict:
        plan_result = self.planning_agent.run(query)
        extraction = (plan_result.get("step_results", {}) or {}).get("step2_extraction", {})
        candidate_models = extraction.get("candidate_models", [])

        retrieval_result = self.retrieval_agent.run(query, candidate_models)
        join_result = self.join_agent.run(candidate_models)
        governance_result = self.governance_agent.run(
            query=query,
            candidate_models=candidate_models,
            extraction=extraction,
        )
        evaluation_bundle = self.evaluation_agent.run(query, plan_result)
        evaluation_result = evaluation_bundle["classification"]
        effective_plan = self._effective_plan_for_sql(plan_result, evaluation_result)
        sql_result = self.sql_generation_agent.run(effective_plan)

        return {
            "query": query,
            "plan_result": plan_result,
            "evaluation_result": evaluation_result,
            "sql_result": sql_result,
            "agent_trace": [
                self.planning_agent.trace({"query": query}, plan_result),
                self.retrieval_agent.trace(
                    {"query": query, "candidates": candidate_models},
                    retrieval_result,
                ),
                self.join_agent.trace({"models": candidate_models}, join_result),
                self.governance_agent.trace(
                    {
                        "query": query,
                        "candidate_models": candidate_models,
                    },
                    governance_result,
                ),
                self.evaluation_agent.trace(
                    {"query": query},
                    evaluation_bundle,
                ),
                self.sql_generation_agent.trace(
                    {"failure_type": effective_plan.get("failure_type")},
                    sql_result,
                ),
            ],
        }

    @staticmethod
    def _effective_plan_for_sql(plan_result: dict, evaluation_result: dict) -> dict:
        if evaluation_result.get("should_generate_sql", False):
            return plan_result

        if evaluation_result.get("failure_type") == plan_result.get("failure_type"):
            return plan_result

        return {
            **plan_result,
            "should_proceed": False,
            "failure_type": evaluation_result.get("failure_type"),
            "failure_reason": evaluation_result.get("reason"),
            "recommendation": evaluation_result.get("recommendation"),
            "confidence_level": "refuse",
            "explanation_text": (
                f"Planning stopped with {evaluation_result.get('failure_type')}: "
                f"{evaluation_result.get('reason')}"
            ),
        }
