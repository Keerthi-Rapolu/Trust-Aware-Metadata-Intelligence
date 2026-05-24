"""
evaluation/benchmark_runner.py

Executable benchmark harness for the metadata reasoning pipeline.

This runner turns the existing fixture set into a reproducible scorecard
covering answerable queries, ambiguity handling, hallucination resistance,
governance blocking, and unsafe-query refusal behavior.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.evaluator import RefusalEvaluator
from generation.refusal_engine import RefusalEngine
from ingestion.graph_store import MetadataGraph
from ingestion.lineage_parser import LineageParser
from ingestion.manifest_ingestor import ManifestIngestor
from reasoning.query_planner import QueryPlanner


DEFAULT_FIXTURE_GROUPS: Dict[str, dict] = {
    "answerable": {
        "fixture_files": ["answerable.json"],
        "description": "Queries expected to succeed without refusal.",
    },
    "ambiguity": {
        "fixture_files": ["semantic_conflict.json", "ambiguous_join.json"],
        "description": "Queries where the system should surface semantic or join ambiguity.",
    },
    "hallucination": {
        "fixture_files": ["missing_entity.json"],
        "description": "Queries with missing schema coverage that should refuse instead of hallucinating.",
    },
    "governance": {
        "fixture_files": ["governance_violation.json"],
        "description": "Queries that must be blocked by deterministic governance checks.",
    },
    "unsafe": {
        "fixture_files": ["unsafe_query.json"],
        "description": "Queries rejected by the refusal engine before planning.",
    },
}


def build_default_planner(
    repo_root: Path,
    user_role: str = "analyst",
    embed_fn=None,
) -> QueryPlanner:
    """Build a planner from the development manifest and glossary."""
    data_dir = repo_root / "data"
    manifest_path = data_dir / "sample_manifest.json"
    glossary_path = data_dir / "glossary.json"

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    with open(glossary_path, "r", encoding="utf-8") as f:
        glossary = json.load(f)

    ingestor = ManifestIngestor()
    parser = LineageParser()
    graph = MetadataGraph()
    graph.add_model_nodes(ingestor.extract_all(manifest))

    for edge in parser.extract_edges(manifest):
        graph.graph.add_edge(
            edge["upstream"],
            edge["downstream"],
            edge_type=edge["edge_type"],
            left_column=edge.get("left_column"),
            right_column=edge.get("right_column"),
        )

    return QueryPlanner(graph=graph, glossary=glossary, embed_fn=embed_fn, user_role=user_role)


class BenchmarkRunner:
    """Runs grouped fixture benchmarks and produces a scorecard."""

    def __init__(
        self,
        planner: QueryPlanner,
        engine: Optional[RefusalEngine] = None,
        fixtures_dir: str | Path = "evaluation/fixtures",
    ) -> None:
        self.planner = planner
        self.engine = engine or RefusalEngine()
        self.fixtures_dir = Path(fixtures_dir)
        self.evaluator = RefusalEvaluator(planner, self.engine)

    def run_fixture_group(
        self,
        group_name: str,
        fixture_files: List[str],
        description: str = "",
    ) -> dict:
        """Run one logical benchmark category over one or more fixture files."""
        all_results = []
        per_file = {}

        for fixture_name in fixture_files:
            fixture_path = self.fixtures_dir / fixture_name
            report = self.evaluator.run_fixture(str(fixture_path))
            per_file[fixture_name] = report
            all_results.extend(report["results"])

        aggregate = self.evaluator._compute_metrics(group_name, all_results)
        aggregate["group_name"] = group_name
        aggregate["description"] = description
        aggregate["fixture_files"] = fixture_files
        aggregate["per_file"] = per_file
        return aggregate

    def run_default_benchmarks(self) -> dict:
        """Run the standard grouped benchmark suite."""
        groups = {}
        all_results = []

        for group_name, cfg in DEFAULT_FIXTURE_GROUPS.items():
            report = self.run_fixture_group(
                group_name=group_name,
                fixture_files=cfg["fixture_files"],
                description=cfg["description"],
            )
            groups[group_name] = report
            all_results.extend(report["results"])

        overall = self.evaluator._compute_metrics("overall", all_results)
        scorecard = self._scorecard(groups, overall)

        return {
            "fixtures_dir": str(self.fixtures_dir),
            "benchmark_groups": groups,
            "overall": overall,
            "scorecard": scorecard,
        }

    def render_markdown(self, report: dict) -> str:
        """Render a human-readable benchmark summary."""
        overall = report["overall"]
        scorecard = report["scorecard"]
        lines = [
            "# Benchmark Report",
            "",
            "## Overall",
            "",
            f"- Total cases: `{overall['total']}`",
            f"- Correct: `{overall['correct']}`",
            f"- Accuracy: `{overall['accuracy']:.2f}`",
            f"- Refusal precision: `{overall['precision']:.2f}`",
            f"- Refusal recall: `{overall['recall']:.2f}`",
            f"- Failure-type F1: `{overall['f1']:.2f}`",
            "",
            "## Scorecard",
            "",
        ]

        for key, value in scorecard.items():
            lines.append(f"- {key}: `{value:.2f}`")

        lines.extend(["", "## Categories", ""])

        for group_name, group_report in report["benchmark_groups"].items():
            lines.append(f"### {group_name.title()}")
            if group_report.get("description"):
                lines.append(group_report["description"])
            lines.append("")
            lines.append(f"- Fixtures: `{', '.join(group_report['fixture_files'])}`")
            lines.append(f"- Accuracy: `{group_report['accuracy']:.2f}`")
            lines.append(f"- Precision: `{group_report['precision']:.2f}`")
            lines.append(f"- Recall: `{group_report['recall']:.2f}`")
            lines.append(f"- F1: `{group_report['f1']:.2f}`")
            lines.append(f"- Correct: `{group_report['correct']}/{group_report['total']}`")
            lines.append("")

        return "\n".join(lines).strip() + "\n"

    def save_json(self, report: dict, output_path: str | Path) -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

    def save_markdown(self, report: dict, output_path: str | Path) -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.render_markdown(report))

    @staticmethod
    def _scorecard(groups: Dict[str, dict], overall: dict) -> dict:
        return {
            "overall_accuracy": overall["accuracy"],
            "refusal_precision": overall["precision"],
            "refusal_recall": overall["recall"],
            "failure_type_f1": overall["f1"],
            "answerable_accuracy": groups["answerable"]["accuracy"],
            "ambiguity_accuracy": groups["ambiguity"]["accuracy"],
            "hallucination_accuracy": groups["hallucination"]["accuracy"],
            "governance_recall": groups["governance"]["recall"],
            "unsafe_recall": groups["unsafe"]["recall"],
        }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the metadata reasoning benchmark suite.")
    parser.add_argument(
        "--fixtures-dir",
        default="evaluation/fixtures",
        help="Directory containing evaluation fixture JSON files.",
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="Optional path to write the structured report as JSON.",
    )
    parser.add_argument(
        "--output-md",
        default=None,
        help="Optional path to write the benchmark summary as Markdown.",
    )
    parser.add_argument(
        "--user-role",
        default="analyst",
        help="Role used when constructing the default planner.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    planner = build_default_planner(repo_root=REPO_ROOT, user_role=args.user_role)
    runner = BenchmarkRunner(
        planner=planner,
        engine=RefusalEngine(),
        fixtures_dir=args.fixtures_dir,
    )
    report = runner.run_default_benchmarks()
    print(runner.render_markdown(report))

    if args.output_json:
        runner.save_json(report, args.output_json)
    if args.output_md:
        runner.save_markdown(report, args.output_md)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
