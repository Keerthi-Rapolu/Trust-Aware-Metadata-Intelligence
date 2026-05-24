"""
evaluation/failure_taxonomy_tests.py

Structural correctness tests for the Failure Taxonomy.

Verifies:
  - Each failure type returns the required response fields
  - GOVERNANCE_BLOCKED fires before all other failure types
  - UNSAFE_QUERY fires before planner is consulted
  - Ambiguity responses surface conflict candidates
  - Priority ordering is correct
  - Confidence is 0.0 for all hard failures

Design reference:
  EXPANSION_DESIGN.md §9 — Failure Taxonomy
  TASK_PLAN.md § 3.5
"""

import pytest

from generation.refusal_engine import RefusalEngine
from reasoning.query_planner   import QueryPlanner

_REQUIRED_KEYS = {
    "status", "failure_type", "reason", "candidates",
    "recommendation", "confidence", "query", "should_generate_sql", "priority",
}

_ALL_FAILURE_TYPES = [
    "GOVERNANCE_BLOCKED",
    "UNSAFE_QUERY",
    "INSUFFICIENT_SCHEMA",
    "WEAK_JOIN",
    "SEMANTIC_CONFLICT",
    "AMBIGUOUS_JOIN",
    "TEMPORAL_AMBIGUITY",
    "LOW_CONFIDENCE",
]


@pytest.fixture(scope="module")
def engine():
    return RefusalEngine()


@pytest.fixture(scope="module")
def planner(graph, glossary):
    return QueryPlanner(graph=graph, glossary=glossary)


# ── Required response fields ────────────────────────────────────────────────

class TestResponseStructure:

    def _run(self, engine, planner, query):
        plan = planner.plan(query)
        return engine.classify(query, plan)

    def test_success_has_required_keys(self, engine, planner):
        result = self._run(engine, planner, "list all segments")
        assert _REQUIRED_KEYS.issubset(result.keys()), (
            f"Missing keys: {_REQUIRED_KEYS - result.keys()}"
        )

    def test_failure_has_required_keys(self, engine, planner):
        result = self._run(engine, planner, "total revenue")
        assert _REQUIRED_KEYS.issubset(result.keys()), (
            f"Missing keys: {_REQUIRED_KEYS - result.keys()}"
        )

    def test_success_status_is_success(self, engine, planner):
        result = self._run(engine, planner, "list all segments")
        assert result["status"] == "SUCCESS"

    def test_success_failure_type_is_none(self, engine, planner):
        result = self._run(engine, planner, "list all segments")
        assert result["failure_type"] is None

    def test_success_should_generate_sql_true(self, engine, planner):
        result = self._run(engine, planner, "list all segments")
        assert result["should_generate_sql"] is True

    def test_failure_status_is_failure(self, engine, planner):
        result = self._run(engine, planner, "total revenue")
        assert result["status"] == "FAILURE"

    def test_failure_should_generate_sql_false(self, engine, planner):
        result = self._run(engine, planner, "total revenue")
        assert result["should_generate_sql"] is False

    def test_failure_confidence_is_zero(self, engine, planner):
        result = self._run(engine, planner, "total revenue")
        assert result["confidence"] == 0.0

    def test_failure_priority_is_int(self, engine, planner):
        result = self._run(engine, planner, "total revenue")
        assert isinstance(result["priority"], int)

    def test_failure_reason_is_string(self, engine, planner):
        result = self._run(engine, planner, "total revenue")
        assert isinstance(result["reason"], str)
        assert len(result["reason"]) > 0

    def test_failure_recommendation_is_string(self, engine, planner):
        result = self._run(engine, planner, "total revenue")
        assert isinstance(result["recommendation"], str)
        assert len(result["recommendation"]) > 0

    def test_candidates_is_list(self, engine, planner):
        result = self._run(engine, planner, "total revenue")
        assert isinstance(result["candidates"], list)

    def test_query_echoed_in_result(self, engine, planner):
        q = "show segment data"
        result = self._run(engine, planner, q)
        assert result["query"] == q


# ── GOVERNANCE_BLOCKED priority ─────────────────────────────────────────────

class TestGovernancePriority:

    def test_governance_fires_for_pci_model(self, engine, planner):
        """payment entity → payment_events (pci tag) → GOVERNANCE_BLOCKED."""
        plan   = planner.plan("show all payments")
        result = engine.classify("show all payments", plan)
        assert result["failure_type"] == "GOVERNANCE_BLOCKED"

    def test_governance_fires_before_ambiguity(self, engine, planner):
        """
        If both a governance violation and semantic conflict are present,
        governance must win.

        'payment revenue' would trigger governance (payment→payment_events pci)
        AND semantic conflict (revenue has 2 candidate columns).
        Since governance check now runs at step 3.5 (before ambiguity at step 5),
        GOVERNANCE_BLOCKED must be returned.
        """
        plan   = planner.plan("payment revenue analysis")
        result = engine.classify("payment revenue analysis", plan)
        # Governance fires first (step 3.5) before SEMANTIC_CONFLICT (step 5)
        assert result["failure_type"] == "GOVERNANCE_BLOCKED", (
            f"Expected GOVERNANCE_BLOCKED, got {result['failure_type']}"
        )

    def test_governance_priority_rank_is_1(self, engine):
        assert engine.failure_priority("GOVERNANCE_BLOCKED") == 1

    def test_governance_rank_lower_than_semantic_conflict(self, engine):
        assert (
            engine.failure_priority("GOVERNANCE_BLOCKED")
            < engine.failure_priority("SEMANTIC_CONFLICT")
        )

    def test_governance_rank_lower_than_insufficient_schema(self, engine):
        assert (
            engine.failure_priority("GOVERNANCE_BLOCKED")
            < engine.failure_priority("INSUFFICIENT_SCHEMA")
        )


# ── UNSAFE_QUERY priority ────────────────────────────────────────────────────

class TestUnsafeQueryPriority:

    def test_unsafe_query_detected_before_planner(self, engine, planner):
        """UNSAFE_QUERY is detected from query text alone, before the planner runs."""
        result = engine.classify(
            "DELETE all customers from the database",
            {"should_proceed": True, "failure_type": None, "final_confidence": 0.9,
             "step_results": {}, "execution_plan": {}, "confidence_level": "confident",
             "failure_reason": None, "recommendation": None},
        )
        assert result["failure_type"] == "UNSAFE_QUERY"

    def test_unsafe_priority_rank_is_2(self, engine):
        assert engine.failure_priority("UNSAFE_QUERY") == 2

    def test_unsafe_rank_lower_than_insufficient_schema(self, engine):
        assert (
            engine.failure_priority("UNSAFE_QUERY")
            < engine.failure_priority("INSUFFICIENT_SCHEMA")
        )

    def test_drop_table_is_unsafe(self, engine):
        assert engine.is_unsafe("DROP TABLE orders") is True

    def test_truncate_is_unsafe(self, engine):
        assert engine.is_unsafe("TRUNCATE payment_events") is True

    def test_update_set_is_unsafe(self, engine):
        assert engine.is_unsafe("UPDATE customer set email = null") is True

    def test_insert_into_is_unsafe(self, engine):
        assert engine.is_unsafe("INSERT INTO dim_customer values (1)") is True

    def test_create_table_is_unsafe(self, engine):
        assert engine.is_unsafe("CREATE TABLE temp AS SELECT * FROM orders") is True

    def test_select_query_is_not_unsafe(self, engine):
        assert engine.is_unsafe("show all escalations") is False

    def test_normal_aggregation_is_not_unsafe(self, engine):
        assert engine.is_unsafe("total revenue by region") is False

    def test_dump_all_is_unsafe(self, engine):
        assert engine.is_unsafe("dump all data from the database without any filter") is True

    def test_entire_database_is_unsafe(self, engine):
        assert engine.is_unsafe("export all records from the entire database") is True


# ── Priority ordering ────────────────────────────────────────────────────────

class TestPriorityOrdering:

    @pytest.mark.parametrize("higher,lower", [
        ("GOVERNANCE_BLOCKED",  "UNSAFE_QUERY"),
        ("UNSAFE_QUERY",        "INSUFFICIENT_SCHEMA"),
        ("INSUFFICIENT_SCHEMA", "WEAK_JOIN"),
        ("WEAK_JOIN",           "SEMANTIC_CONFLICT"),
        ("SEMANTIC_CONFLICT",   "AMBIGUOUS_JOIN"),
        ("AMBIGUOUS_JOIN",      "TEMPORAL_AMBIGUITY"),
        ("TEMPORAL_AMBIGUITY",  "LOW_CONFIDENCE"),
    ])
    def test_priority_chain(self, engine, higher, lower):
        """Each type must have strictly lower priority rank than the next."""
        assert engine.failure_priority(higher) < engine.failure_priority(lower), (
            f"Expected {higher} priority < {lower} priority"
        )

    def test_highest_priority_failure_selects_governance(self, engine):
        failures = ["SEMANTIC_CONFLICT", "GOVERNANCE_BLOCKED", "LOW_CONFIDENCE"]
        result = engine.highest_priority_failure(failures)
        assert result == "GOVERNANCE_BLOCKED"

    def test_highest_priority_failure_selects_unsafe(self, engine):
        failures = ["INSUFFICIENT_SCHEMA", "LOW_CONFIDENCE", "UNSAFE_QUERY"]
        result = engine.highest_priority_failure(failures)
        assert result == "UNSAFE_QUERY"

    def test_highest_priority_failure_empty_list(self, engine):
        result = engine.highest_priority_failure([])
        assert result is None


# ── Ambiguity surfaces candidates ────────────────────────────────────────────

class TestAmbiguityCandidates:

    def test_semantic_conflict_surfaces_candidates(self, engine, planner):
        """SEMANTIC_CONFLICT must include the conflicting columns in candidates."""
        plan   = planner.plan("total revenue")
        result = engine.classify("total revenue", plan)
        assert result["failure_type"] == "SEMANTIC_CONFLICT"
        assert isinstance(result["candidates"], list)
        assert len(result["candidates"]) >= 2, (
            f"Expected ≥2 conflict candidates, got {result['candidates']}"
        )

    def test_insufficient_schema_has_empty_candidates(self, engine, planner):
        plan   = planner.plan("show me xyz_metric_zz99")
        result = engine.classify("show me xyz_metric_zz99", plan)
        assert result["failure_type"] == "INSUFFICIENT_SCHEMA"
        assert isinstance(result["candidates"], list)

    def test_unsafe_query_has_no_candidates(self, engine):
        result = engine.classify(
            "DELETE all customers",
            {"should_proceed": False, "failure_type": None, "final_confidence": 0.0,
             "step_results": {}, "execution_plan": None, "confidence_level": "refuse",
             "failure_reason": None, "recommendation": None},
        )
        assert result["failure_type"] == "UNSAFE_QUERY"
        assert result["candidates"] == []


# ── Confidence on failure ────────────────────────────────────────────────────

class TestFailureConfidence:

    @pytest.mark.parametrize("query,expected_type", [
        ("total revenue",               "SEMANTIC_CONFLICT"),
        ("show all payments",           "GOVERNANCE_BLOCKED"),
        ("show me xyz_metric_zz99",     "INSUFFICIENT_SCHEMA"),
        ("DELETE all orders",           "UNSAFE_QUERY"),
    ])
    def test_confidence_zero_on_failure(self, engine, planner, query, expected_type):
        plan   = planner.plan(query)
        result = engine.classify(query, plan)
        assert result["failure_type"] == expected_type
        assert result["confidence"] == 0.0, (
            f"Expected confidence=0.0 for {expected_type}, got {result['confidence']}"
        )
