"""
tests/test_refusal_engine.py

Unit tests for generation/refusal_engine.py

Coverage
--------
  - classify() returns all required keys
  - SUCCESS path: should_generate_sql=True, failure_type=None
  - FAILURE path: should_generate_sql=False, failure_type set
  - UNSAFE_QUERY: detected before planner regardless of plan_result
  - GOVERNANCE_BLOCKED from plan propagated with priority=1
  - INSUFFICIENT_SCHEMA, SEMANTIC_CONFLICT, LOW_CONFIDENCE paths
  - is_unsafe() returns True for all DML/DDL patterns
  - is_unsafe() returns False for normal analytics queries
  - failure_priority() returns correct rank
  - highest_priority_failure() returns lowest-rank type
  - candidates extracted from step5_ambiguity when present
  - confidence=0.0 on all failure types
  - UNSAFE_QUERY check fires even when plan says should_proceed=True
"""

import pytest

from generation.refusal_engine import RefusalEngine


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def engine():
    return RefusalEngine()


def _make_plan(
    should_proceed=True,
    failure_type=None,
    failure_reason=None,
    recommendation=None,
    confidence=0.85,
    confidence_level="confident",
    step5_ambiguity=None,
    step4_join=None,
    execution_plan=None,
):
    step_results = {}
    if step5_ambiguity is not None:
        step_results["step5_ambiguity"] = step5_ambiguity
    if step4_join is not None:
        step_results["step4_join_paths"] = step4_join
    return {
        "should_proceed":   should_proceed,
        "failure_type":     failure_type,
        "failure_reason":   failure_reason,
        "recommendation":   recommendation,
        "final_confidence": confidence if should_proceed else 0.0,
        "confidence_level": confidence_level,
        "step_results":     step_results,
        "execution_plan":   execution_plan or ({"intent": "lookup"} if should_proceed else None),
    }


_REQUIRED_KEYS = {
    "status", "failure_type", "reason", "candidates",
    "recommendation", "confidence", "query", "should_generate_sql", "priority",
}


# ── Response structure ───────────────────────────────────────────────────────

class TestResponseStructure:

    def test_success_has_required_keys(self, engine):
        result = engine.classify("show segments", _make_plan())
        assert _REQUIRED_KEYS.issubset(result.keys())

    def test_failure_has_required_keys(self, engine):
        result = engine.classify("show xyz",
                                 _make_plan(should_proceed=False, failure_type="INSUFFICIENT_SCHEMA",
                                             failure_reason="No models found", recommendation="check glossary"))
        assert _REQUIRED_KEYS.issubset(result.keys())

    def test_success_status(self, engine):
        result = engine.classify("show segments", _make_plan())
        assert result["status"] == "SUCCESS"

    def test_success_failure_type_none(self, engine):
        result = engine.classify("show segments", _make_plan())
        assert result["failure_type"] is None

    def test_success_should_generate_sql_true(self, engine):
        result = engine.classify("show segments", _make_plan())
        assert result["should_generate_sql"] is True

    def test_success_priority_none(self, engine):
        result = engine.classify("show segments", _make_plan())
        assert result["priority"] is None

    def test_failure_status(self, engine):
        result = engine.classify("show xyz",
                                 _make_plan(should_proceed=False, failure_type="INSUFFICIENT_SCHEMA",
                                             failure_reason="No models", recommendation="check"))
        assert result["status"] == "FAILURE"

    def test_failure_should_generate_sql_false(self, engine):
        result = engine.classify("show xyz",
                                 _make_plan(should_proceed=False, failure_type="INSUFFICIENT_SCHEMA",
                                             failure_reason="No models", recommendation="check"))
        assert result["should_generate_sql"] is False

    def test_failure_confidence_zero(self, engine):
        result = engine.classify("show xyz",
                                 _make_plan(should_proceed=False, failure_type="INSUFFICIENT_SCHEMA",
                                             failure_reason="No models", recommendation="check"))
        assert result["confidence"] == 0.0

    def test_query_echoed(self, engine):
        q = "show region data"
        result = engine.classify(q, _make_plan())
        assert result["query"] == q


# ── UNSAFE_QUERY detection ────────────────────────────────────────────────────

class TestUnsafeQueryDetection:

    def test_unsafe_overrides_success_plan(self, engine):
        """UNSAFE_QUERY must fire even when the planner says should_proceed=True."""
        plan   = _make_plan(should_proceed=True, confidence=0.9)
        result = engine.classify("DELETE all customers from the database", plan)
        assert result["failure_type"] == "UNSAFE_QUERY"
        assert result["should_generate_sql"] is False

    def test_delete_from_detected(self, engine):
        assert engine.is_unsafe("DELETE FROM orders WHERE id = 1")

    def test_delete_all_detected(self, engine):
        assert engine.is_unsafe("DELETE all rows")

    def test_drop_table_detected(self, engine):
        assert engine.is_unsafe("DROP TABLE fct_orders")

    def test_drop_database_detected(self, engine):
        assert engine.is_unsafe("DROP DATABASE analytics")

    def test_truncate_detected(self, engine):
        assert engine.is_unsafe("TRUNCATE TABLE dim_customer")

    def test_truncate_no_table_keyword_detected(self, engine):
        assert engine.is_unsafe("truncate payment_events")

    def test_insert_into_detected(self, engine):
        assert engine.is_unsafe("INSERT INTO dim_customer VALUES (1)")

    def test_update_set_detected(self, engine):
        assert engine.is_unsafe("UPDATE fct_orders set revenue_gross = 0")

    def test_create_table_detected(self, engine):
        assert engine.is_unsafe("CREATE TABLE temp_orders AS SELECT * FROM fct_orders")

    def test_alter_table_detected(self, engine):
        assert engine.is_unsafe("ALTER TABLE fct_orders DROP COLUMN order_date")

    def test_grant_detected(self, engine):
        assert engine.is_unsafe("GRANT SELECT ON fct_orders TO analyst")

    def test_dump_all_detected(self, engine):
        assert engine.is_unsafe("dump all data from the database without any filter")

    def test_entire_database_detected(self, engine):
        assert engine.is_unsafe("export all records from the entire database")

    def test_normal_select_not_unsafe(self, engine):
        assert not engine.is_unsafe("show all segments")

    def test_aggregation_not_unsafe(self, engine):
        assert not engine.is_unsafe("total revenue by region")

    def test_trend_not_unsafe(self, engine):
        assert not engine.is_unsafe("show growth trend over time")

    def test_lookup_not_unsafe(self, engine):
        assert not engine.is_unsafe("find customer by segment")

    def test_case_insensitive_dml(self, engine):
        assert engine.is_unsafe("delete from fct_orders")
        assert engine.is_unsafe("DELETE FROM fct_orders")
        assert engine.is_unsafe("Delete From fct_orders")


# ── Priority ordering ─────────────────────────────────────────────────────────

class TestPriorityOrdering:

    @pytest.mark.parametrize("failure_type,expected_rank", [
        ("GOVERNANCE_BLOCKED",  1),
        ("UNSAFE_QUERY",        2),
        ("INSUFFICIENT_SCHEMA", 3),
        ("WEAK_JOIN",           4),
        ("SEMANTIC_CONFLICT",   5),
        ("AMBIGUOUS_JOIN",      6),
        ("TEMPORAL_AMBIGUITY",  7),
        ("LOW_CONFIDENCE",      8),
    ])
    def test_priority_ranks(self, engine, failure_type, expected_rank):
        assert engine.failure_priority(failure_type) == expected_rank

    def test_unknown_type_high_rank(self, engine):
        assert engine.failure_priority("UNKNOWN_TYPE") == 99

    def test_governance_above_semantic_conflict(self, engine):
        assert (
            engine.failure_priority("GOVERNANCE_BLOCKED")
            < engine.failure_priority("SEMANTIC_CONFLICT")
        )

    def test_unsafe_above_insufficient_schema(self, engine):
        assert (
            engine.failure_priority("UNSAFE_QUERY")
            < engine.failure_priority("INSUFFICIENT_SCHEMA")
        )

    def test_weak_join_above_ambiguous_join(self, engine):
        assert (
            engine.failure_priority("WEAK_JOIN")
            < engine.failure_priority("AMBIGUOUS_JOIN")
        )


# ── highest_priority_failure ──────────────────────────────────────────────────

class TestHighestPriorityFailure:

    def test_selects_governance_from_list(self, engine):
        result = engine.highest_priority_failure(
            ["LOW_CONFIDENCE", "GOVERNANCE_BLOCKED", "SEMANTIC_CONFLICT"]
        )
        assert result == "GOVERNANCE_BLOCKED"

    def test_selects_unsafe_when_no_governance(self, engine):
        result = engine.highest_priority_failure(
            ["INSUFFICIENT_SCHEMA", "UNSAFE_QUERY", "LOW_CONFIDENCE"]
        )
        assert result == "UNSAFE_QUERY"

    def test_single_item(self, engine):
        result = engine.highest_priority_failure(["SEMANTIC_CONFLICT"])
        assert result == "SEMANTIC_CONFLICT"

    def test_empty_list_returns_none(self, engine):
        result = engine.highest_priority_failure([])
        assert result is None


# ── Candidates extraction ─────────────────────────────────────────────────────

class TestCandidatesExtraction:

    def test_semantic_conflict_candidates_from_step5(self, engine):
        conflicts = [
            {"column": "revenue_gross", "entity": "revenue", "score": 1.0},
            {"column": "revenue_net",   "entity": "revenue", "score": 1.0},
        ]
        plan = _make_plan(
            should_proceed=False,
            failure_type="SEMANTIC_CONFLICT",
            failure_reason="Multiple revenue definitions",
            recommendation="Specify which definition",
            step5_ambiguity={
                "is_ambiguous":  True,
                "ambiguity_type": "SEMANTIC_CONFLICT",
                "conflicts":     conflicts,
            },
        )
        result = engine.classify("total revenue", plan)
        assert result["failure_type"] == "SEMANTIC_CONFLICT"
        assert len(result["candidates"]) == 2

    def test_no_step5_candidates_empty(self, engine):
        plan = _make_plan(
            should_proceed=False,
            failure_type="INSUFFICIENT_SCHEMA",
            failure_reason="No models found",
            recommendation="Check glossary",
        )
        result = engine.classify("show xyz", plan)
        assert result["candidates"] == []

    def test_governance_has_empty_candidates(self, engine):
        plan = _make_plan(
            should_proceed=False,
            failure_type="GOVERNANCE_BLOCKED",
            failure_reason="PCI column blocked",
            recommendation="Request access",
        )
        result = engine.classify("show payments", plan)
        assert result["failure_type"] == "GOVERNANCE_BLOCKED"
        assert isinstance(result["candidates"], list)


# ── Failure type mapping ──────────────────────────────────────────────────────

class TestFailureTypeMapping:

    @pytest.mark.parametrize("failure_type", [
        "GOVERNANCE_BLOCKED",
        "INSUFFICIENT_SCHEMA",
        "WEAK_JOIN",
        "SEMANTIC_CONFLICT",
        "AMBIGUOUS_JOIN",
        "LOW_CONFIDENCE",
    ])
    def test_failure_type_propagated(self, engine, failure_type):
        plan = _make_plan(
            should_proceed=False,
            failure_type=failure_type,
            failure_reason=f"{failure_type} reason",
            recommendation="Fix it",
        )
        result = engine.classify("some query", plan)
        assert result["failure_type"] == failure_type

    def test_none_failure_type_becomes_low_confidence(self, engine):
        """should_proceed=False with no failure_type → LOW_CONFIDENCE."""
        plan = _make_plan(
            should_proceed=False,
            failure_type=None,
            failure_reason=None,
            recommendation=None,
        )
        result = engine.classify("some query", plan)
        assert result["failure_type"] == "LOW_CONFIDENCE"
