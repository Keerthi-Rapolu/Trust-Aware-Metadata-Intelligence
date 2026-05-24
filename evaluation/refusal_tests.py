"""
evaluation/refusal_tests.py

Fixture-based evaluation tests for the Honest Refusal Framework.

Runs every query in the evaluation fixture files through the full pipeline
(QueryPlanner → RefusalEngine) and asserts the expected status and failure
type.  Precision, recall, and F1 are reported at the end.

Design reference:
  EXPANSION_DESIGN.md §9 — Evaluation Harness Per Failure Type
  TASK_PLAN.md § 3.4
"""

import json
import pytest
from pathlib import Path

from reasoning.query_planner import QueryPlanner
from generation.refusal_engine import RefusalEngine
from evaluation.evaluator import RefusalEvaluator

# ── Fixture paths ───────────────────────────────────────────────────────────

_FIXTURES_DIR = Path(__file__).parent / "fixtures"

_FIXTURE_FILES = [
    "answerable.json",
    "missing_entity.json",
    "semantic_conflict.json",
    "governance_violation.json",
    "unsafe_query.json",
    "ambiguous_join.json",
]


# ── Session-scoped planner + engine ─────────────────────────────────────────

@pytest.fixture(scope="module")
def planner(graph, glossary):
    return QueryPlanner(graph=graph, glossary=glossary)


@pytest.fixture(scope="module")
def engine():
    return RefusalEngine()


@pytest.fixture(scope="module")
def evaluator(planner, engine):
    return RefusalEvaluator(planner, engine)


# ── Helper to load fixtures ──────────────────────────────────────────────────

def _load_fixture(filename: str):
    path = _FIXTURES_DIR / filename
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _fixture_params(filename: str):
    """Return pytest parametrize args from a fixture file."""
    cases = _load_fixture(filename)
    return [
        pytest.param(
            c["query"],
            c.get("expected_status", "SUCCESS"),
            c.get("expected_failure_type"),
            id=f"{filename.split('.')[0]}/{c['query'][:40]}",
        )
        for c in cases
    ]


# ── Per-fixture parametrized tests ──────────────────────────────────────────

class TestAnswerableQueries:
    @pytest.mark.parametrize("query,exp_status,exp_type",
                             _fixture_params("answerable.json"))
    def test_answerable(self, query, exp_status, exp_type, planner, engine):
        plan   = planner.plan(query)
        result = engine.classify(query, plan)
        assert result["status"] == exp_status, (
            f"Query: '{query}'\n"
            f"  Expected status={exp_status}, got {result['status']}\n"
            f"  failure_type={result['failure_type']}\n"
            f"  reason={result['reason']}"
        )
        assert result["failure_type"] == exp_type, (
            f"Query: '{query}'\n"
            f"  Expected failure_type={exp_type}, got {result['failure_type']}"
        )


class TestMissingEntityQueries:
    @pytest.mark.parametrize("query,exp_status,exp_type",
                             _fixture_params("missing_entity.json"))
    def test_missing_entity(self, query, exp_status, exp_type, planner, engine):
        plan   = planner.plan(query)
        result = engine.classify(query, plan)
        assert result["status"] == exp_status, (
            f"Query: '{query}'\nExpected FAILURE, got {result['status']}\n"
            f"failure_type={result['failure_type']}"
        )
        assert result["failure_type"] == exp_type, (
            f"Query: '{query}'\n"
            f"Expected failure_type={exp_type}, got {result['failure_type']}"
        )


class TestSemanticConflictQueries:
    @pytest.mark.parametrize("query,exp_status,exp_type",
                             _fixture_params("semantic_conflict.json"))
    def test_semantic_conflict(self, query, exp_status, exp_type, planner, engine):
        plan   = planner.plan(query)
        result = engine.classify(query, plan)
        assert result["status"] == "FAILURE"
        assert result["failure_type"] == "SEMANTIC_CONFLICT", (
            f"Query: '{query}'\nExpected SEMANTIC_CONFLICT, got {result['failure_type']}"
        )


class TestGovernanceViolationQueries:
    @pytest.mark.parametrize("query,exp_status,exp_type",
                             _fixture_params("governance_violation.json"))
    def test_governance_violation(self, query, exp_status, exp_type, planner, engine):
        plan   = planner.plan(query)
        result = engine.classify(query, plan)
        assert result["status"] == "FAILURE"
        assert result["failure_type"] == "GOVERNANCE_BLOCKED", (
            f"Query: '{query}'\nExpected GOVERNANCE_BLOCKED, got {result['failure_type']}"
        )


class TestUnsafeQueries:
    @pytest.mark.parametrize("query,exp_status,exp_type",
                             _fixture_params("unsafe_query.json"))
    def test_unsafe_query(self, query, exp_status, exp_type, planner, engine):
        plan   = planner.plan(query)
        result = engine.classify(query, plan)
        assert result["status"] == "FAILURE"
        assert result["failure_type"] == "UNSAFE_QUERY", (
            f"Query: '{query}'\nExpected UNSAFE_QUERY, got {result['failure_type']}"
        )


class TestAmbiguousJoinQueries:
    @pytest.mark.parametrize("query,exp_status,exp_type",
                             _fixture_params("ambiguous_join.json"))
    def test_ambiguous_join(self, query, exp_status, exp_type, planner, engine):
        plan   = planner.plan(query)
        result = engine.classify(query, plan)
        assert result["status"] == exp_status, (
            f"Query: '{query}'\nExpected {exp_status}, got {result['status']}"
        )
        assert result["failure_type"] == exp_type, (
            f"Query: '{query}'\n"
            f"Expected failure_type={exp_type}, got {result['failure_type']}"
        )


# ── Aggregate evaluation report ─────────────────────────────────────────────

class TestEvaluationMetrics:

    def test_aggregate_accuracy_above_threshold(self, evaluator):
        """Overall accuracy across all fixtures must be ≥ 90%."""
        report = evaluator.run_all(str(_FIXTURES_DIR))
        accuracy = report["accuracy"]
        # Print the summary to pytest output
        print(f"\n{report['summary']}")
        for fname, frep in report["per_file"].items():
            print(f"  {frep['summary']}")
        if report["incorrect_details"]:
            print("\nIncorrect predictions:")
            for r in report["incorrect_details"]:
                print(f"  [{r['expected_failure_type']} → {r['got_failure_type']}]"
                      f" '{r['query'][:60]}'")
        assert accuracy >= 0.90, (
            f"Aggregate accuracy {accuracy:.2f} < 0.90 threshold.\n"
            f"{report['summary']}"
        )

    def test_answerable_precision(self, evaluator):
        """Answerable queries must all return SUCCESS (no false refusals)."""
        report = evaluator.run_fixture(str(_FIXTURES_DIR / "answerable.json"))
        incorrect = [r for r in report["results"] if not r["correct"]]
        assert not incorrect, (
            f"Some answerable queries were incorrectly refused:\n"
            + "\n".join(f"  '{r['query']}' → {r['got_failure_type']}"
                        for r in incorrect)
        )

    def test_governance_recall(self, evaluator):
        """All governance violations must be caught (recall = 1.0)."""
        report = evaluator.run_fixture(str(_FIXTURES_DIR / "governance_violation.json"))
        assert report["recall"] == 1.0, (
            f"Governance recall {report['recall']} < 1.0 — some violations missed"
        )

    def test_unsafe_recall(self, evaluator):
        """All unsafe queries must be caught (recall = 1.0)."""
        report = evaluator.run_fixture(str(_FIXTURES_DIR / "unsafe_query.json"))
        assert report["recall"] == 1.0, (
            f"Unsafe query recall {report['recall']} < 1.0"
        )
