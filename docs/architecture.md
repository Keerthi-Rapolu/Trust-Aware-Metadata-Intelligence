# Architecture

## Overview

The system is a deterministic metadata reasoning pipeline that only hands
an LLM a constrained execution plan after retrieval, join analysis,
governance, confidence scoring, and explainability have already run.

## Annotated Flow

```text
Natural-language query
        |
        v
IntentClassifier
  - classify intent
  - detect time grain
        |
        v
EntityExtractor
  - map business terms to candidate models and columns
  - resolve glossary synonyms
        |
        v
MetadataGraph
  - dbt manifest-derived model metadata
  - lineage edges + explicit FK evidence
        |
        v
Governance Gate
  - PII detector
  - RBAC validator
  - query cost estimator
  - hard-stop before SQL generation
        |
        v
JoinPathEngine + AmbiguityDetector
  - choose join path
  - refuse weak joins / conflicting semantics
        |
        v
SemanticRetriever
  - composite 5-factor retrieval score
        |
        v
ConfidenceScorer
  - weakest-link confidence propagation
        |
        v
ExplainabilityFormatter
  - retrieval explanation
  - join explanation
  - confidence explanation
  - refusal explanation
        |
        v
SqlGenerator / RefusalEngine
  - template or LLM SQL generation
  - final refusal guard for unsafe queries
        |
        v
Streamlit frontend / API consumers
```

## Module Roles

- `ingestion/`
  - Parses `manifest.json`, normalizes records, and builds graph-ready metadata.
- `reasoning/`
  - Runs deterministic planning, join reasoning, ambiguity detection, and confidence scoring.
- `retrieval/`
  - Applies composite ranking with semantic, lineage, glossary, historical, and governance signals.
- `governance/`
  - Blocks unsafe access before SQL generation.
- `explainability/`
  - Formats planner evidence into structured JSON and human-readable text.
- `generation/`
  - Produces SQL from the execution plan or returns structured refusals.
- `frontend/`
  - Surfaces confidence, retrieval, joins, and refusals in Streamlit.

## Execution Contract

Planner outputs now carry two explainability forms:

- Structured JSON under `result["explanations"]`
- Human-readable text under `result["explanation_text"]`

When a plan proceeds, the same explanation blocks are copied into the
`execution_plan` so the SQL generator and frontend consume the same
reasoning trace.

## Failure Priority

The architecture preserves the trust ordering established in earlier phases:

1. Governance and unsafe-query checks stop execution first.
2. Join and semantic conflicts stop execution before SQL generation.
3. Low-confidence outcomes refuse even when a model match exists.
4. Explainability records the exact stage and reason for the stop.
