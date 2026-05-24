"""
evaluation/evaluator.py

Evaluation harness utility for the Honest Refusal Framework.

Loads fixture files, runs queries through the QueryPlanner + RefusalEngine
pipeline, and reports classification metrics (precision, recall, F1).

Usage
-----
  from evaluation.evaluator import RefusalEvaluator
  from reasoning.query_planner import QueryPlanner
  from generation.refusal_engine import RefusalEngine

  evaluator = RefusalEvaluator(planner, RefusalEngine())
  report = evaluator.run_fixture("evaluation/fixtures/semantic_conflict.json")
  print(report["summary"])
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class RefusalEvaluator:
    """
    Runs a fixture file through the planner + refusal engine and
    produces a precision/recall/F1 evaluation report.
    """

    def __init__(self, planner, engine):
        """
        Parameters
        ----------
        planner : QueryPlanner instance
        engine  : RefusalEngine instance
        """
        self.planner = planner
        self.engine  = engine

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def run_fixture(self, fixture_path: str) -> dict:
        """
        Run all queries in a fixture file and return an evaluation report.

        Parameters
        ----------
        fixture_path : path to a JSON fixture file

        Returns
        -------
        dict:
          fixture_path   : str
          total          : int
          correct        : int
          incorrect      : int
          precision      : float  (TP / (TP + FP)) for failure classification
          recall         : float  (TP / (TP + FN)) for failure classification
          f1             : float
          accuracy       : float
          results        : list[dict]  — per-query details
          summary        : str
        """
        fixtures = self._load(fixture_path)
        results  = []

        for fix in fixtures:
            query    = fix["query"]
            exp_status = fix.get("expected_status", "SUCCESS")
            exp_type   = fix.get("expected_failure_type")

            plan_result = self.planner.plan(query)
            classified  = self.engine.classify(query, plan_result)

            got_status = classified["status"]
            got_type   = classified["failure_type"]

            status_match = (got_status == exp_status)
            type_match   = (got_type   == exp_type)
            correct      = status_match and type_match

            results.append({
                "query":                query,
                "expected_status":      exp_status,
                "expected_failure_type": exp_type,
                "got_status":           got_status,
                "got_failure_type":     got_type,
                "status_match":         status_match,
                "type_match":           type_match,
                "correct":              correct,
                "confidence":           classified["confidence"],
                "notes":                fix.get("notes", ""),
            })

        return self._compute_metrics(fixture_path, results)

    def run_all(self, fixtures_dir: str) -> dict:
        """
        Run all fixture files in a directory and return an aggregate report.
        """
        fixture_dir  = Path(fixtures_dir)
        fixture_files = sorted(fixture_dir.glob("*.json"))
        all_results   = []
        per_file      = {}

        for fp in fixture_files:
            report = self.run_fixture(str(fp))
            per_file[fp.name] = report
            all_results.extend(report["results"])

        aggregate = self._compute_metrics(fixtures_dir, all_results)
        aggregate["per_file"] = per_file
        return aggregate

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _load(fixture_path: str) -> List[dict]:
        with open(fixture_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _compute_metrics(source: str, results: List[dict]) -> dict:
        total   = len(results)
        correct = sum(1 for r in results if r["correct"])

        # For classification precision/recall we treat each predicted
        # failure_type as a class.  Correct = TP; wrong type = FP + FN.
        tp = sum(1 for r in results
                 if r["expected_failure_type"] is not None and r["type_match"])
        fp = sum(1 for r in results
                 if r["expected_failure_type"] is None     and r["got_failure_type"] is not None)
        fn = sum(1 for r in results
                 if r["expected_failure_type"] is not None and not r["type_match"])

        precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
        recall    = tp / (tp + fn) if (tp + fn) > 0 else 1.0
        f1        = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )
        accuracy  = correct / total if total > 0 else 0.0

        incorrect_list = [r for r in results if not r["correct"]]
        summary = (
            f"{source}: {correct}/{total} correct | "
            f"precision={precision:.2f} recall={recall:.2f} F1={f1:.2f} "
            f"accuracy={accuracy:.2f}"
        )

        return {
            "fixture_path": source,
            "total":        total,
            "correct":      correct,
            "incorrect":    len(incorrect_list),
            "precision":    round(precision, 4),
            "recall":       round(recall, 4),
            "f1":           round(f1, 4),
            "accuracy":     round(accuracy, 4),
            "results":      results,
            "incorrect_details": incorrect_list,
            "summary":      summary,
        }
