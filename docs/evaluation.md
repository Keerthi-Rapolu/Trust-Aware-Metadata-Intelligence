# Evaluation

## Why This Exists

The system claims three things that should be measurable:

- it refuses unsafe or unsupported queries instead of hallucinating SQL
- it classifies failure modes explicitly
- it propagates confidence through the reasoning pipeline

`evaluation/benchmark_runner.py` exists to turn those claims into a
repeatable benchmark instead of a demo-only narrative.

## Benchmark Categories

The runner groups the current fixture set into five benchmark categories:

- `answerable`
  - queries expected to succeed without refusal
  - source fixture: `evaluation/fixtures/answerable.json`
- `ambiguity`
  - semantic conflicts and ambiguous join behavior
  - source fixtures: `semantic_conflict.json`, `ambiguous_join.json`
- `hallucination`
  - missing-schema cases that should refuse instead of fabricating support
  - source fixture: `missing_entity.json`
- `governance`
  - PII / PCI / RBAC / cost-aware hard stops
  - source fixture: `governance_violation.json`
- `unsafe`
  - DML / DDL / bulk-dump queries rejected before planning
  - source fixture: `unsafe_query.json`

## Metrics

The benchmark runner reports:

- `accuracy`
  - exact match on expected status and expected failure type
- `refusal_precision`
  - among predicted failures, how many were correct failure classifications
- `refusal_recall`
  - among expected failures, how many were caught with the right type
- `failure_type_f1`
  - harmonic mean of refusal precision and refusal recall
- category-level accuracy / recall snapshots
  - especially useful for governance and unsafe-query benchmarks

These metrics are intentionally oriented around trust behavior, not just
SQL emission rate.

## How To Run

Run the grouped benchmark suite:

```bash
python evaluation/benchmark_runner.py
```

Write machine-readable and Markdown outputs:

```bash
python evaluation/benchmark_runner.py \
  --output-json artifacts/benchmark_report.json \
  --output-md artifacts/benchmark_report.md
```

## Current Synthetic-Fixture Baseline

On the current development manifest and fixture set, the grouped benchmark
reports approximately:

- overall accuracy: `0.82`
- refusal precision: `0.82`
- refusal recall: `0.97`
- failure-type F1: `0.89`
- governance recall: `1.00`
- unsafe-query recall: `1.00`
- answerable accuracy: `0.33`

That baseline is important for two reasons:

- refusal behavior is already strong
  - governance and unsafe-query categories are consistently blocked
- answerable-query handling is improving but still incomplete
  - lexical semantic fallback now allows some obvious single-entity questions to proceed, but the synthetic answerable set is still only partially recovered

This is not a reason to hide the benchmark. It is the reason to keep it.

## Interpretation

The current benchmark profile suggests:

- the architecture is already good at safe refusal
- failure taxonomy behavior is mostly reliable
- the next high-leverage tuning area is answerable-query recovery
  - especially broader answerable coverage beyond the strongest single-entity glossary matches

That is a credible engineering story:

- deterministic safety first
- measurable weak spots second
- targeted iteration next

## Relationship To Pytest

The files under `evaluation/` are a benchmark harness and reference test
set, not the primary default pytest collection target.

The canonical way to measure benchmark performance is:

```bash
python evaluation/benchmark_runner.py
```

Unit and integration correctness still live under `tests/`, while the
benchmark runner is the measurement surface for portfolio and publication
use.
