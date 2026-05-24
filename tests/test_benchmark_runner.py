"""
tests/test_benchmark_runner.py

Coverage for the executable benchmark harness.
"""

from pathlib import Path

import pytest

from evaluation.benchmark_runner import (
    DEFAULT_FIXTURE_GROUPS,
    BenchmarkRunner,
    build_default_planner,
)
from evaluation.evaluator import RefusalEvaluator
from generation.refusal_engine import RefusalEngine
from reasoning.query_planner import QueryPlanner


@pytest.fixture(scope="module")
def planner(graph, glossary):
    return QueryPlanner(graph=graph, glossary=glossary)


@pytest.fixture(scope="module")
def runner(planner):
    return BenchmarkRunner(planner=planner, engine=RefusalEngine(), fixtures_dir="evaluation/fixtures")


class TestDefaultPlannerFactory:

    def test_build_default_planner_returns_query_planner(self):
        repo_root = Path(__file__).resolve().parent.parent
        planner = build_default_planner(repo_root=repo_root)
        assert planner.__class__.__name__ == "QueryPlanner"


class TestBenchmarkRunner:

    def test_run_default_benchmarks_has_expected_groups(self, runner):
        report = runner.run_default_benchmarks()
        assert set(report["benchmark_groups"].keys()) == set(DEFAULT_FIXTURE_GROUPS.keys())

    def test_overall_total_matches_group_totals(self, runner):
        report = runner.run_default_benchmarks()
        total = sum(group["total"] for group in report["benchmark_groups"].values())
        assert report["overall"]["total"] == total

    def test_scorecard_has_expected_metrics(self, runner):
        report = runner.run_default_benchmarks()
        expected = {
            "overall_accuracy",
            "refusal_precision",
            "refusal_recall",
            "failure_type_f1",
            "answerable_accuracy",
            "ambiguity_accuracy",
            "hallucination_accuracy",
            "governance_recall",
            "unsafe_recall",
        }
        assert expected.issubset(report["scorecard"].keys())

    def test_benchmark_runner_matches_refusal_evaluator_aggregate(self, runner, planner):
        report = runner.run_default_benchmarks()
        direct = RefusalEvaluator(planner, RefusalEngine()).run_all("evaluation/fixtures")

        assert report["overall"]["total"] == direct["total"]
        assert report["overall"]["correct"] == direct["correct"]
        assert report["overall"]["accuracy"] == direct["accuracy"]
        assert report["overall"]["precision"] == direct["precision"]
        assert report["overall"]["recall"] == direct["recall"]
        assert report["overall"]["f1"] == direct["f1"]

    def test_render_markdown_contains_category_headings(self, runner):
        report = runner.run_default_benchmarks()
        markdown = runner.render_markdown(report)

        assert "# Benchmark Report" in markdown
        for group_name in DEFAULT_FIXTURE_GROUPS:
            assert f"### {group_name.title()}" in markdown

    def test_save_json_and_markdown(self, runner, tmp_path):
        report = runner.run_default_benchmarks()
        json_path = tmp_path / "benchmark.json"
        md_path = tmp_path / "benchmark.md"

        runner.save_json(report, json_path)
        runner.save_markdown(report, md_path)

        assert json_path.exists()
        assert md_path.exists()
