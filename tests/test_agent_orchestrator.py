"""
tests/test_agent_orchestrator.py

Phase 7 coverage for thin agent wrappers and sequential orchestration.
"""

import pytest

from agents.module_agents import (
    EvaluationAgent,
    GovernanceAgent,
    JoinReasoningAgent,
    PlanningAgent,
    RetrievalAgent,
    SQLGenerationAgent,
)
from agents.orchestrator import SequentialAgentOrchestrator
from generation.refusal_engine import RefusalEngine
from generation.sql_generator import SqlGenerator
from governance.governance_evaluator import GovernanceEvaluator
from reasoning.confidence_scorer import ConfidenceScorer
from reasoning.join_path_engine import JoinPathEngine
from reasoning.query_planner import QueryPlanner
from retrieval.embedding_ranker import EmbeddingRanker


@pytest.fixture(scope="module")
def planner(graph, glossary):
    return QueryPlanner(graph=graph, glossary=glossary)


@pytest.fixture(scope="module")
def ranker(graph, glossary):
    return EmbeddingRanker(graph, glossary, embed_fn=None)


@pytest.fixture(scope="module")
def join_engine(graph):
    return JoinPathEngine(graph, embed_fn=None)


@pytest.fixture(scope="module")
def governance_eval(graph):
    return GovernanceEvaluator(graph=graph)


@pytest.fixture(scope="module")
def generator():
    return SqlGenerator()


@pytest.fixture(scope="module")
def refusal_engine():
    return RefusalEngine()


@pytest.fixture(scope="module")
def evaluation_agent():
    return EvaluationAgent(
        confidence_scorer=ConfidenceScorer(),
        refusal_engine=RefusalEngine(),
    )


class TestAgentContracts:

    def test_contracts_reference_existing_modules(
        self,
        planner,
        ranker,
        join_engine,
        governance_eval,
        generator,
        evaluation_agent,
    ):
        agents = [
            PlanningAgent(planner),
            RetrievalAgent(ranker),
            JoinReasoningAgent(join_engine),
            GovernanceAgent(governance_eval),
            SQLGenerationAgent(generator),
            evaluation_agent,
        ]
        for agent in agents:
            meta = agent.describe()
            assert meta["agent_name"]
            assert meta["wrapped_modules"]
            assert isinstance(meta["wrapped_modules"], list)


class TestWrapperParity:

    def test_retrieval_agent_matches_embedding_ranker(self, ranker):
        agent = RetrievalAgent(ranker)
        query = "show payment details"
        candidates = ["dim_customer", "payment_events"]

        expected = ranker.rank(query, candidates)
        actual = agent.run(query, candidates)
        assert actual == expected

    def test_planning_agent_matches_query_planner(self, planner):
        agent = PlanningAgent(planner)
        query = "show all payments"

        assert agent.run(query) == planner.plan(query)

    def test_join_agent_matches_join_engine(self, join_engine):
        agent = JoinReasoningAgent(join_engine)
        models = ["dim_customer", "fct_orders"]

        assert agent.run(models) == join_engine.find_join_paths(models)

    def test_governance_agent_matches_planner_governance_step(self, planner, governance_eval):
        agent = GovernanceAgent(governance_eval)
        query = "show all payments"
        plan = planner.plan(query)
        extraction = plan["step_results"]["step2_extraction"]
        candidates = extraction["candidate_models"]

        assert agent.run(query, candidates, extraction) == plan["step_results"]["step6_governance"]

    def test_sql_generation_agent_matches_generator(self, planner, generator):
        agent = SQLGenerationAgent(generator)
        plan = planner.plan("list all segments")

        assert agent.run(plan) == generator.generate(plan)

    def test_evaluation_agent_matches_refusal_engine_and_confidence(self, planner, refusal_engine, evaluation_agent):
        query = "list all segments"
        plan = planner.plan(query)

        result = evaluation_agent.run(query, plan)
        assert result["classification"] == refusal_engine.classify(query, plan)
        assert result["confidence_review"] == plan["step_results"]["step8_confidence"]


def _direct_bundle(query: str, planner: QueryPlanner, generator: SqlGenerator, refusal_engine: RefusalEngine) -> dict:
    plan_result = planner.plan(query)
    evaluation_result = refusal_engine.classify(query, plan_result)

    effective_plan = plan_result
    if not evaluation_result.get("should_generate_sql", False):
        if evaluation_result.get("failure_type") != plan_result.get("failure_type"):
            effective_plan = {
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

    return {
        "plan_result": plan_result,
        "evaluation_result": evaluation_result,
        "sql_result": generator.generate(effective_plan),
    }


class TestSequentialOrchestration:

    @pytest.fixture(scope="class")
    def orchestrator(self, graph, glossary):
        return SequentialAgentOrchestrator.from_components(graph=graph, glossary=glossary)

    @pytest.mark.parametrize(
        "query",
        [
            "list all segments",
            "show revenue by region",
            "show all payments",
            "DELETE all customers from the database",
        ],
    )
    def test_orchestrator_matches_direct_pipeline(
        self,
        orchestrator,
        planner,
        generator,
        refusal_engine,
        query,
    ):
        direct = _direct_bundle(query, planner, generator, refusal_engine)
        actual = orchestrator.run(query)

        assert actual["plan_result"] == direct["plan_result"]
        assert actual["evaluation_result"] == direct["evaluation_result"]
        assert actual["sql_result"] == direct["sql_result"]

    def test_orchestrator_trace_has_all_agents(self, orchestrator):
        result = orchestrator.run("show all payments")
        names = [entry["agent_name"] for entry in result["agent_trace"]]

        assert names == [
            "planning",
            "retrieval",
            "join_reasoning",
            "governance",
            "evaluation",
            "sql_generation",
        ]
