# Trust-Aware Metadata Reasoning

> A deterministic metadata reasoning system that decides whether to generate SQL, refuse a query, or block execution — before calling an LLM.

This project focuses on trustworthy enterprise text-to-SQL orchestration using semantic metadata retrieval, governance-aware planning, confidence propagation, and explainable reasoning.

Unlike conventional RAG SQL systems, this platform separates:

- metadata reasoning
- semantic validation
- governance enforcement
- confidence evaluation

from final SQL generation.

---

## Why This Exists

Most enterprise text-to-SQL systems fail because they:

- hallucinate columns
- invent joins
- ignore governance constraints
- silently choose ambiguous metrics
- generate unsafe queries

This project explores a different approach:

> **Deterministic metadata reasoning before LLM generation.**

The system evaluates semantic retrieval, join validity, governance constraints, ambiguity detection, and confidence propagation before deciding whether SQL generation is allowed.

---

## Core Capabilities

### Deterministic Query Planning

The system performs structured reasoning before SQL generation:

```
User Query
    ↓
Intent Extraction
    ↓
Metadata Retrieval
    ↓
Join Path Reasoning
    ↓
Governance Validation
    ↓
Confidence Propagation
    ↓
SQL Generation OR Safe Refusal
```

### Honest Refusal Behavior

Instead of hallucinating unsupported SQL, the system explicitly refuses queries when metadata is insufficient or ambiguous.

```
SAFE REFUSAL · Semantic Conflict

Multiple 'revenue' definitions found:
  - revenue_gross
  - revenue_net

Specify which definition is required.
```

### Governance-Aware Planning

The planner evaluates RBAC restrictions, PII exposure, unsafe scan patterns, and excessive warehouse cost risk before SQL execution.

```
GOVERNANCE BLOCK

Restricted model access detected:
  payment_events

Estimated Scan:
  18,000 GB
```

### Composite Retrieval Ranking

Metadata retrieval combines multiple enterprise-aware signals:

| Signal | Purpose |
|--------|---------|
| Semantic Similarity | Query relevance |
| Lineage Proximity | Upstream/downstream relationship strength |
| Glossary Overlap | Business terminology alignment |
| Historical Relevance | Prior analytical usage |
| Governance Compatibility | Policy-aware retrieval filtering |

Formula: `0.35 × Semantic + 0.25 × Lineage + 0.15 × Glossary + 0.15 × Historical + 0.10 × Governance`

### Confidence Propagation

Confidence is not treated as a single score. The system propagates confidence across retrieval quality, join reasoning, governance validation, metadata completeness, and intent clarity.

```
Retrieval            0.80  ████████░░
Join Path            1.00  ██████████
Governance           1.00  ██████████
Completeness         1.00  ██████████
Intent Clarity       1.00  ██████████
```

---

## Example Scenarios

### Safe SQL Generation

| Query | `show segment data` |
|-------|---------------------|
| Decision | **SAFE SQL GENERATED** |
| Confidence | 0.80 |

### Semantic Conflict Detection

| Query | `show revenue by region` |
|-------|--------------------------|
| Decision | **SAFE REFUSAL** |
| Reason | Multiple revenue definitions detected. |

### Insufficient Schema Detection

| Query | `show me the xyz_metric_zz99` |
|-------|-------------------------------|
| Decision | **SAFE REFUSAL** |
| Reason | No recognised metadata entities found. |

### Governance Blocking

| Query | `show all payments` |
|-------|---------------------|
| Decision | **GOVERNANCE BLOCK** |
| Reason | Restricted model access + unsafe scan pattern detected. |

---

## Architecture

```
User Query
    ↓
Intent Extraction
    ↓
Metadata Retrieval
    ↓
Join Path Reasoning
    ↓
Ambiguity Detection
    ↓
Governance Validation
    ↓
Confidence Propagation
    ↓
SQL Generation / Refusal / Block
```

---

## Reasoning Philosophy

This project intentionally avoids:

- unconstrained agentic execution
- blind prompt-based SQL generation
- pure embedding retrieval
- opaque LLM-only orchestration

Instead, it focuses on:

- deterministic metadata planning
- constrained SQL generation
- explainable reasoning
- trustworthy refusal behavior
- governance-aware orchestration

---

## Repository Structure

```
enterprise-metadata-intelligence/
│
├── evaluation/         # Benchmark runner and failure taxonomy tests
├── frontend/           # Streamlit reasoning demo
├── governance/         # PII detector, RBAC validator, cost estimator
├── ingestion/          # Manifest ingestor, lineage parser, graph store
├── reasoning/          # Query planner, entity extractor, confidence scorer
├── retrieval/          # Embedding ranker, glossary matcher, lineage scorer
├── generation/         # SQL generator, refusal engine
├── explainability/     # Explanation formatter
├── agents/             # Agent orchestrator and module agents
├── docs/               # Design references and architecture docs
└── tests/              # Full test suite
```

---

## Evaluation

Current synthetic benchmark baseline:

| Metric | Score |
|--------|-------|
| Overall Accuracy | 0.73 |
| Refusal Precision | 0.74 |
| Refusal Recall | 0.97 |
| Failure-Type F1 | 0.84 |
| Ambiguity Accuracy | 0.92 |
| Hallucination Accuracy | 0.88 |
| Governance Recall | 1.00 |
| Unsafe Recall | 1.00 |

---

## Demo

The project includes a single-page Streamlit reasoning demo.

The demo shows SQL generation, safe refusal behavior, governance blocking, confidence propagation, metadata grounding, and join reasoning — without exposing raw orchestration complexity.

```bash
streamlit run app.py
```

---

## Screenshots

**Safe SQL Generation**

<img width="1709" height="1051" alt="image" src="https://github.com/user-attachments/assets/613b9803-32c7-45cb-8937-9c48956d9597" />

**Semantic Conflict Refusal**

*Add screenshot here.*

**Governance Blocking**

*Add screenshot here.*

---

## Running Locally

### Install

```bash
pip install -r requirements.txt
```

### Start Demo

```bash
streamlit run app.py
```

### Run Tests

```bash
pytest -q
```

---

## Research Direction

This project explores trustworthy enterprise AI, metadata intelligence, semantic reasoning systems, governance-aware orchestration, explainable SQL planning, and confidence-aware AI systems.

Future directions include:

- dbt manifest ingestion
- metadata graph traversal
- enterprise lineage reasoning
- semantic join inference
- warehouse observability integration

---

## Key Differentiator

Most text-to-SQL systems ask:

> *Can the LLM generate SQL?*

This project asks:

> **Should the system generate SQL at all?**

That distinction is the foundation of this architecture.

---

## License

MIT License
