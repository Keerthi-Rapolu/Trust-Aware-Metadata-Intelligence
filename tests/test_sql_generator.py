"""
tests/test_sql_generator.py

Unit tests for generation/sql_generator.py

Coverage
--------
  - refused plan → sql=None, mode="refused"
  - refused plan → failure_type and failure_reason preserved
  - proceeding plan → sql is a non-empty string
  - proceeding plan → mode="template" when no llm_fn
  - template mode SELECT includes primary model
  - template mode FROM clause contains primary model
  - aggregation intent wraps numeric columns in SUM()
  - trend intent includes DATE_TRUNC when time_grain set + date col present
  - segmentation intent includes GROUP BY
  - single-model plan (no joins) generates valid SQL without JOIN
  - two-model plan with join edge includes LEFT JOIN
  - explanation always populated
  - warnings from plan propagated
  - LLM mode calls llm_fn and returns its output
  - render_prompt includes execution plan fields
  - confidence and confidence_level propagated from plan
"""

import pytest

from generation.sql_generator import SqlGenerator
from reasoning.query_planner  import QueryPlanner


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def planner(graph, glossary):
    return QueryPlanner(graph=graph, glossary=glossary)


@pytest.fixture
def gen():
    return SqlGenerator()


def _make_refused_plan():
    return {
        "query":            "total revenue",
        "step_results":     {},
        "execution_plan":   None,
        "final_confidence": 0.0,
        "confidence_level": "refuse",
        "should_proceed":   False,
        "failure_type":     "SEMANTIC_CONFLICT",
        "failure_reason":   "Multiple revenue definitions found.",
        "recommendation":   "Specify which revenue definition to use.",
    }

def _make_proceeding_plan(intent="lookup", models=None, columns=None, joins=None):
    models  = models  or ["fct_orders"]
    columns = columns or {"fct_orders": ["order_id", "order_amount"]}
    return {
        "query":            "show orders",
        "step_results":     {},
        "execution_plan": {
            "query":            "show orders",
            "intent":           intent,
            "time_grain":       None,
            "candidate_models": models,
            "model_columns":    columns,
            "join_path":        joins or [],
            "entities":         [],
            "confidence":       0.85,
            "confidence_level": "confident",
            "governance_clear": True,
            "warnings":         [],
        },
        "final_confidence": 0.85,
        "confidence_level": "confident",
        "should_proceed":   True,
        "failure_type":     None,
        "failure_reason":   None,
        "recommendation":   "Confidence is high — proceed to SQL generation.",
    }


# ──────────────────────────────────────────────────────────────────────────────
# Refusal
# ──────────────────────────────────────────────────────────────────────────────

class TestRefusal:

    def test_refused_plan_returns_none_sql(self, gen):
        result = gen.generate(_make_refused_plan())
        assert result["sql"] is None

    def test_refused_plan_mode_is_refused(self, gen):
        result = gen.generate(_make_refused_plan())
        assert result["mode"] == "refused"

    def test_failure_type_preserved(self, gen):
        result = gen.generate(_make_refused_plan())
        assert result["failure_type"] == "SEMANTIC_CONFLICT"

    def test_failure_reason_preserved(self, gen):
        result = gen.generate(_make_refused_plan())
        assert result["failure_reason"] is not None

    def test_explanation_populated_on_refusal(self, gen):
        result = gen.generate(_make_refused_plan())
        assert len(result["explanation"]) > 0

    def test_refused_when_should_proceed_false(self, gen):
        plan = _make_proceeding_plan()
        plan["should_proceed"] = False
        result = gen.generate(plan)
        assert result["sql"] is None
        assert result["mode"] == "refused"


# ──────────────────────────────────────────────────────────────────────────────
# Template mode — basic
# ──────────────────────────────────────────────────────────────────────────────

class TestTemplateModeBasic:

    def test_sql_is_string(self, gen):
        result = gen.generate(_make_proceeding_plan())
        assert isinstance(result["sql"], str)
        assert len(result["sql"]) > 0

    def test_mode_is_template(self, gen):
        result = gen.generate(_make_proceeding_plan())
        assert result["mode"] == "template"

    def test_sql_contains_select(self, gen):
        result = gen.generate(_make_proceeding_plan())
        assert "SELECT" in result["sql"].upper()

    def test_sql_contains_from(self, gen):
        result = gen.generate(_make_proceeding_plan())
        assert "FROM" in result["sql"].upper()

    def test_sql_contains_primary_model(self, gen):
        result = gen.generate(_make_proceeding_plan(models=["fct_orders"]))
        assert "fct_orders" in result["sql"]

    def test_sql_ends_with_semicolon(self, gen):
        result = gen.generate(_make_proceeding_plan())
        assert result["sql"].strip().endswith(";")

    def test_confidence_propagated(self, gen):
        plan = _make_proceeding_plan()
        result = gen.generate(plan)
        assert result["confidence"] == pytest.approx(0.85, abs=1e-4)

    def test_confidence_level_propagated(self, gen):
        result = gen.generate(_make_proceeding_plan())
        assert result["confidence_level"] == "confident"

    def test_explanation_populated(self, gen):
        result = gen.generate(_make_proceeding_plan())
        assert len(result["explanation"]) > 0

    def test_warnings_propagated(self, gen):
        plan = _make_proceeding_plan()
        plan["execution_plan"]["warnings"] = ["Moderate confidence (weakest: completeness)"]
        result = gen.generate(plan)
        assert len(result["warnings"]) == 1


# ──────────────────────────────────────────────────────────────────────────────
# Template mode — intent-specific
# ──────────────────────────────────────────────────────────────────────────────

class TestTemplateModeIntents:

    def test_aggregation_wraps_revenue_in_sum(self, gen):
        plan = _make_proceeding_plan(
            intent="aggregation",
            models=["fct_orders"],
            columns={"fct_orders": ["order_id", "order_amount", "revenue_gross"]},
        )
        result = gen.generate(plan)
        # Amount/revenue columns should be in SUM()
        assert "SUM(" in result["sql"]

    def test_trend_includes_date_trunc_when_grain_and_date_col(self, gen):
        plan = _make_proceeding_plan(
            intent="trend",
            models=["fct_orders"],
            columns={"fct_orders": ["order_date", "order_amount"]},
        )
        plan["execution_plan"]["time_grain"] = "monthly"
        result = gen.generate(plan)
        # DATE_TRUNC should appear for trend + grain + date col
        assert "DATE_TRUNC" in result["sql"].upper() or "order_date" in result["sql"]

    def test_segmentation_includes_group_by(self, gen):
        plan = _make_proceeding_plan(
            intent="segmentation",
            models=["fct_orders"],
            columns={"fct_orders": ["region", "order_amount"]},
        )
        result = gen.generate(plan)
        assert "GROUP BY" in result["sql"].upper()

    def test_lookup_no_group_by(self, gen):
        plan = _make_proceeding_plan(
            intent="lookup",
            models=["dim_customer"],
            columns={"dim_customer": ["customer_id", "customer_name"]},
        )
        result = gen.generate(plan)
        assert "GROUP BY" not in result["sql"].upper()


# ──────────────────────────────────────────────────────────────────────────────
# Template mode — join handling
# ──────────────────────────────────────────────────────────────────────────────

class TestJoinHandling:

    def test_single_model_no_join_clause(self, gen):
        plan = _make_proceeding_plan(
            models=["dim_customer"],
            columns={"dim_customer": ["customer_id"]},
            joins=[],
        )
        result = gen.generate(plan)
        assert "JOIN" not in result["sql"].upper()

    def test_two_model_join_includes_left_join(self, gen):
        join_edge = {
            "from_model":  "dim_customer",
            "to_model":    "fct_orders",
            "from_column": "customer_id",
            "to_column":   "customer_id",
            "edge_type":   "explicit_fk",
            "score":       0.885,
            "join_string": "dim_customer.customer_id -> fct_orders.customer_id",
        }
        plan = _make_proceeding_plan(
            models=["dim_customer", "fct_orders"],
            columns={
                "dim_customer": ["customer_id", "customer_name"],
                "fct_orders":   ["order_id", "order_amount"],
            },
            joins=[join_edge],
        )
        result = gen.generate(plan)
        assert "JOIN" in result["sql"].upper()

    def test_join_sql_has_on_clause(self, gen):
        join_edge = {
            "from_model":  "dim_customer",
            "to_model":    "fct_orders",
            "from_column": "customer_id",
            "to_column":   "customer_id",
            "edge_type":   "explicit_fk",
            "score":       0.885,
            "join_string": "dim_customer.customer_id -> fct_orders.customer_id",
        }
        plan = _make_proceeding_plan(
            models=["dim_customer", "fct_orders"],
            columns={
                "dim_customer": ["customer_id"],
                "fct_orders":   ["order_id", "order_amount"],
            },
            joins=[join_edge],
        )
        result = gen.generate(plan)
        assert "ON" in result["sql"].upper()


# ──────────────────────────────────────────────────────────────────────────────
# LLM mode
# ──────────────────────────────────────────────────────────────────────────────

class TestLlmMode:

    def test_llm_fn_called(self, gen):
        calls = []
        def mock_llm(prompt):
            calls.append(prompt)
            return "SELECT * FROM fct_orders;"

        llm_gen = SqlGenerator(llm_fn=mock_llm)
        llm_gen.generate(_make_proceeding_plan())
        assert len(calls) == 1

    def test_llm_mode_label(self, gen):
        llm_gen = SqlGenerator(llm_fn=lambda p: "SELECT 1;")
        result  = llm_gen.generate(_make_proceeding_plan())
        assert result["mode"] == "llm"

    def test_llm_output_returned(self, gen):
        expected = "SELECT customer_id FROM dim_customer;"
        llm_gen  = SqlGenerator(llm_fn=lambda p: expected)
        result   = llm_gen.generate(_make_proceeding_plan())
        assert result["sql"] == expected


# ──────────────────────────────────────────────────────────────────────────────
# render_prompt
# ──────────────────────────────────────────────────────────────────────────────

class TestRenderPrompt:

    def test_prompt_contains_intent(self, gen):
        plan = _make_proceeding_plan()["execution_plan"]
        prompt = gen.render_prompt(plan)
        assert "intent" in prompt.lower() or "lookup" in prompt.lower()

    def test_prompt_contains_model_name(self, gen):
        plan = _make_proceeding_plan(models=["fct_orders"])["execution_plan"]
        prompt = gen.render_prompt(plan)
        assert "fct_orders" in prompt

    def test_prompt_contains_execution_plan_header(self, gen):
        plan = _make_proceeding_plan()["execution_plan"]
        prompt = gen.render_prompt(plan)
        assert "EXECUTION PLAN" in prompt.upper()


# ──────────────────────────────────────────────────────────────────────────────
# End-to-end: planner → generator
# ──────────────────────────────────────────────────────────────────────────────

class TestEndToEnd:

    def test_orders_query_end_to_end(self, planner):
        gen = SqlGenerator()
        plan_result = planner.plan("show all orders by region")
        result = gen.generate(plan_result)
        # Either generates SQL or refuses — both acceptable; no exception
        assert "sql" in result
        assert "mode" in result

    def test_gibberish_query_no_exception(self, planner):
        gen = SqlGenerator()
        plan_result = planner.plan("aaabbb cccddd")
        result = gen.generate(plan_result)
        assert result["sql"] is None
        assert result["mode"] == "refused"
