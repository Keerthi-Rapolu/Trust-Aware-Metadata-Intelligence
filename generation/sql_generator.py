"""
generation/sql_generator.py

Generates SQL from a structured execution plan produced by QueryPlanner.

Design reference:
  EXPANSION_DESIGN.md §6 — Step 9/10 (LLM receives execution plan, not raw metadata)

The generator has TWO modes:

  template  (default, no LLM required)
    Deterministic rule-based SQL assembly from plan fields.
    Guarantees predictable, testable output.

  llm       (requires an llm_fn callable)
    Renders the plan as a structured prompt and passes it to an LLM.
    The LLM sees ONLY the execution plan — never raw manifest / graph data.

Both modes refuse to generate SQL when `plan["should_proceed"]` is False.
"""

from typing import Callable, Optional


class SqlGenerator:
    """
    Converts a QueryPlanner execution plan into a SQL string.

    Parameters
    ----------
    llm_fn : optional callable(prompt: str) -> str
        When provided, SQL is generated via LLM using the plan-based prompt.
        When None, deterministic template mode is used.
    """

    def __init__(self, llm_fn: Optional[Callable] = None):
        self.llm_fn = llm_fn

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def generate(self, plan_result: dict) -> dict:
        """
        Generate SQL from a QueryPlanner result.

        Parameters
        ----------
        plan_result : full dict returned by QueryPlanner.plan()

        Returns
        -------
        dict with keys:
          sql               : str | None — generated SQL (None on refusal)
          mode              : str  — "template" | "llm" | "refused"
          confidence        : float
          confidence_level  : str
          warnings          : list[str]
          failure_type      : str | None
          failure_reason    : str | None
          explanation       : str  — human-readable rationale
        """
        # Honour refusal decision from planner
        if not plan_result.get("should_proceed", False):
            return self._refused(plan_result)

        exec_plan = plan_result.get("execution_plan", {})
        if not exec_plan:
            return self._refused(plan_result)

        if self.llm_fn:
            return self._generate_llm(exec_plan, plan_result)
        return self._generate_template(exec_plan, plan_result)

    def render_prompt(self, execution_plan: dict) -> str:
        """
        Render the structured prompt that is sent to the LLM.
        Exposed publicly so callers can inspect / log what the LLM sees.
        """
        return self._build_prompt(execution_plan)

    # ------------------------------------------------------------------ #
    # Template mode                                                        #
    # ------------------------------------------------------------------ #

    def _generate_template(self, plan: dict, plan_result: dict) -> dict:
        """
        Deterministic SQL assembly from execution plan fields.
        """
        sql = self._assemble_sql(plan)
        return {
            "sql":              sql,
            "mode":             "template",
            "confidence":       plan_result.get("final_confidence", 0.0),
            "confidence_level": plan_result.get("confidence_level", ""),
            "warnings":         plan.get("warnings", []),
            "failure_type":     None,
            "failure_reason":   None,
            "explanation":      (
                plan_result.get("explanation_text")
                or self._explain(plan)
            ),
            "explanation_json": plan_result.get("explanations"),
        }

    def _assemble_sql(self, plan: dict) -> str:
        """
        Rule-based SQL builder.  Produces syntactically correct SELECT
        statements for the supported intent types.
        """
        models   = plan.get("candidate_models", [])
        columns  = plan.get("model_columns", {})
        intent   = plan.get("intent", "lookup")
        grain    = plan.get("time_grain")
        joins    = plan.get("join_path", [])

        if not models:
            return "-- Unable to determine target model"

        primary = models[0]

        # Collect SELECT columns
        select_cols = self._select_columns(models, columns, intent)

        # GROUP BY column (segmentation / trend)
        group_col   = self._group_by_col(plan, intent, grain)

        # FROM + JOIN clause
        from_clause = self._from_clause(primary, joins)

        # Assemble
        lines = [f"SELECT\n    {select_cols}"]
        lines.append(from_clause)
        if group_col:
            lines[-1] += f"\nGROUP BY\n    {group_col}"
            lines[-1] += f"\nORDER BY\n    {group_col}"

        sql = "\n".join(lines) + ";"
        return sql

    def _select_columns(self, models: list, columns: dict, intent: str) -> str:
        """Build the SELECT column list based on intent and available columns."""
        agg_intents = {"aggregation", "trend", "segmentation"}

        all_cols = []
        for m in models:
            for c in columns.get(m, []):
                all_cols.append(f"{m}.{c}")

        if not all_cols:
            # Fall back to wildcard
            return f"{models[0]}.*"

        if intent not in agg_intents:
            return ",\n    ".join(all_cols)

        # Wrap numeric-looking columns in SUM(), keep others bare
        select_parts = []
        for col_ref in all_cols:
            col_name = col_ref.split(".")[-1]
            if any(kw in col_name for kw in ("amount", "revenue", "cost", "price", "count", "qty", "total")):
                select_parts.append(f"SUM({col_ref}) AS total_{col_name}")
            else:
                select_parts.append(col_ref)
        return ",\n    ".join(select_parts) if select_parts else f"{models[0]}.*"

    def _group_by_col(self, plan: dict, intent: str, grain: Optional[str]) -> Optional[str]:
        """Return the GROUP BY expression when applicable."""
        if intent not in ("segmentation", "trend", "aggregation"):
            return None

        # For trend intent with a time grain, look for date columns
        if intent == "trend" and grain:
            for m in plan.get("candidate_models", []):
                for col in plan.get("model_columns", {}).get(m, []):
                    if any(kw in col for kw in ("date", "_dt", "_at", "time", "_ts")):
                        return f"DATE_TRUNC('{grain}', {m}.{col})"

        # For segmentation, use first non-metric column
        for m in plan.get("candidate_models", []):
            for col in plan.get("model_columns", {}).get(m, []):
                if not any(kw in col for kw in ("amount", "revenue", "cost", "price", "id")):
                    return f"{m}.{col}"
        return None

    def _from_clause(self, primary: str, joins: list) -> str:
        """Build FROM + LEFT JOIN lines from join path edges."""
        clause = f"FROM\n    {primary}"
        seen = {primary}
        for edge in joins:
            src = edge.get("from_model", "")
            tgt = edge.get("to_model", "")
            lc  = edge.get("from_column")
            rc  = edge.get("to_column")
            # Add each new model as a LEFT JOIN
            join_model = tgt if tgt not in seen else (src if src not in seen else None)
            if join_model and lc and rc:
                on_src = src if src in seen else tgt
                on_tgt = join_model
                clause += (
                    f"\nLEFT JOIN {join_model}"
                    f"\n    ON {on_src}.{lc} = {on_tgt}.{rc}"
                )
                seen.add(join_model)
        return clause

    def _explain(self, plan: dict) -> str:
        models = plan.get("candidate_models", [])
        intent = plan.get("intent", "lookup")
        conf   = plan.get("confidence", 0.0)
        return (
            f"Generated {intent} query over model(s): {', '.join(models)}. "
            f"Plan confidence: {conf:.2f}."
        )

    # ------------------------------------------------------------------ #
    # LLM mode                                                             #
    # ------------------------------------------------------------------ #

    def _generate_llm(self, plan: dict, plan_result: dict) -> dict:
        prompt = self._build_prompt(plan)
        sql    = self.llm_fn(prompt)
        return {
            "sql":              sql,
            "mode":             "llm",
            "confidence":       plan_result.get("final_confidence", 0.0),
            "confidence_level": plan_result.get("confidence_level", ""),
            "warnings":         plan.get("warnings", []),
            "failure_type":     None,
            "failure_reason":   None,
            "explanation":      (
                plan_result.get("explanation_text")
                or "SQL generated via LLM using structured execution plan."
            ),
            "explanation_json": plan_result.get("explanations"),
        }

    def _build_prompt(self, plan: dict) -> str:
        """
        Render the execution plan as a structured LLM prompt.
        The LLM sees only plan fields — no raw manifest / graph data.
        """
        joins_text = ""
        for edge in plan.get("join_path", []):
            joins_text += f"\n  - {edge.get('join_string', str(edge))}"

        entities_text = ""
        for e in plan.get("entities", []):
            entities_text += (
                f"\n  - {e['term']}: columns={e['columns']}, models={e['models']}"
            )

        warnings_text = ""
        for w in plan.get("warnings", []):
            warnings_text += f"\n  ⚠ {w}"

        return f"""You are a SQL generation assistant. Generate a single SQL query from the structured plan below.
Do NOT use any knowledge outside what is provided in the plan.

=== EXECUTION PLAN ===
Query      : {plan.get('query', '')}
Intent     : {plan.get('intent', 'lookup')}
Time Grain : {plan.get('time_grain') or 'none specified'}
Models     : {', '.join(plan.get('candidate_models', []))}
Confidence : {plan.get('confidence', 0.0):.2f} ({plan.get('confidence_level', '')})

Entities:{entities_text or ' none'}

Join Path:{joins_text or ' single model — no joins required'}

Model → Columns:
{self._format_model_columns(plan.get('model_columns', {}))}
{('Warnings:' + warnings_text) if warnings_text else ''}
=== END PLAN ===

Generate SQL:"""

    @staticmethod
    def _format_model_columns(model_columns: dict) -> str:
        if not model_columns:
            return "  (none)"
        lines = []
        for model, cols in model_columns.items():
            lines.append(f"  {model}: {', '.join(cols) or '(none)'}")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Refusal                                                              #
    # ------------------------------------------------------------------ #

    def _refused(self, plan_result: dict) -> dict:
        return {
            "sql":              None,
            "mode":             "refused",
            "confidence":       plan_result.get("final_confidence", 0.0),
            "confidence_level": plan_result.get("confidence_level", "refuse"),
            "warnings":         [],
            "failure_type":     plan_result.get("failure_type"),
            "failure_reason":   plan_result.get("failure_reason"),
            "explanation":      (
                plan_result.get("explanation_text")
                or plan_result.get("recommendation")
                or "SQL generation refused — see failure_reason for details."
            ),
            "explanation_json": plan_result.get("explanations"),
        }
