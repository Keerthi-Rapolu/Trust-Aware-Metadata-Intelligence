# Trust-Aware Metadata Reasoning

![Tests](https://img.shields.io/badge/tests-439%20passing-brightgreen)
![Streamlit](https://img.shields.io/badge/demo-Streamlit-red)
![License](https://img.shields.io/badge/license-MIT-blue)

> A deterministic metadata reasoning system for **SQL generation**, **safe refusal**, and **governance blocking** — before calling an LLM.

This project focuses on trustworthy enterprise text-to-SQL orchestration using semantic metadata retrieval, governance-aware planning, confidence propagation, and explainable reasoning.

Unlike conventional RAG SQL systems, this platform separates metadata reasoning, semantic validation, governance enforcement, and confidence evaluation from final SQL generation.

> **This is a research-grade prototype, not a production database gateway.**

## Paper

[Read Practitioner Architecture Paper](docs/paper.pdf)

GitHub will usually open the PDF in the browser. It can also be downloaded directly from the PDF viewer.

---

## Live Demo

Try the hosted demo:

**[https://trust-aware-metadata-intelligence.streamlit.app/](https://trust-aware-metadata-intelligence.streamlit.app/)**

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

The system evaluates semantic retrieval, join validity, governance constraints, ambiguity detection, and confidence propagation before deciding whether SQL generation is safe and semantically justified.

---

## Why Pure RAG Is Insufficient

Embedding similarity alone cannot reliably determine:

- valid join paths between tables
- metric ambiguity across business definitions
- governance safety for restricted models or PII columns
- warehouse cost risk from unsafe scan patterns
- semantic conflicts between overlapping terms

This system introduces deterministic metadata reasoning before SQL generation to constrain unsafe or ambiguous outputs — going beyond what retrieval similarity can provide.

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

## Enterprise Reasoning Scenarios

### Semantic Metric Ambiguity

Enterprise warehouses often contain multiple competing business definitions for the same metric. When a query targets an ambiguous term, selecting one definition arbitrarily is a correctness failure — not a reasonable default.

```
show revenue by region
```

The system detects that `revenue` maps to multiple semantic definitions: `revenue_gross` and `revenue_net`. Instead of selecting one arbitrarily, the planner triggers a structured refusal and requests clarification before SQL generation proceeds.

### Governance-Constrained Planning

Analytical queries may target restricted models, expose PII columns, or trigger unsafe warehouse scan patterns. The governance layer evaluates all three dimensions before generation is approved.

```
show all payments
```

The governance layer detects restricted model access, potential PII exposure, and unbounded scan risk on `payment_events`. SQL generation is blocked before execution and a structured explanation is returned.

### Insufficient Metadata Grounding

When metadata entities cannot be confidently grounded in the knowledge graph, the planner refuses generation rather than hallucinating columns or fabricating join paths.

```
show me xyz_metric_zz99
```

No semantic metadata match exists in the graph. The planner returns `INSUFFICIENT_SCHEMA` with confidence `0.00` and a structured refusal explanation — no SQL is attempted.

### Confidence-Constrained SQL Generation

SQL generation is only approved when metadata retrieval succeeds, governance checks pass, join reasoning resolves cleanly, and confidence propagation exceeds the generation threshold across all components.

```
show segment data
```

The planner resolves the query to a single grounded metadata model (`dim_customer`) with no governance flags, no ambiguity, and a clean join path. Constrained SQL generation is approved at confidence `0.80`.

---

## Failure Taxonomy

The system recognises eight distinct failure types, evaluated in priority order:

| Failure Type | Trigger |
|---|---|
| `GOVERNANCE_BLOCKED` | Restricted model access, PII exposure, or unsafe scan pattern |
| `UNSAFE_QUERY` | Query matches known destructive or exfiltration patterns |
| `INSUFFICIENT_SCHEMA` | Required metadata entities not found in the graph |
| `WEAK_JOIN` | No valid join path exists between resolved tables |
| `SEMANTIC_CONFLICT` | Multiple conflicting metric definitions for the same term |
| `AMBIGUOUS_JOIN` | Multiple plausible join paths with no clear winner |
| `TEMPORAL_AMBIGUITY` | Time range or date filter cannot be resolved |
| `LOW_CONFIDENCE` | Confidence propagation falls below the generation threshold |

Each failure produces a structured explanation surfaced in the UI and included in evaluation metrics.

---

## Architecture

```mermaid
%%{init: {
  "theme": "base",
  "themeVariables": {
    "background": "#0f172a",
    "primaryTextColor": "#eef2ff",
    "secondaryTextColor": "#e8eefb",
    "lineColor": "#a7b7d6",
    "fontFamily": "Segoe UI, Arial, sans-serif"
  },
  "flowchart": {
    "nodeSpacing": 34,
    "rankSpacing": 42,
    "curve": "basis"
  }
}}%%
flowchart TD
    subgraph P["Reasoning and Planning"]
        A[User Query] --> B[Intent Extraction]
        B --> C[Metadata Retrieval]
        C --> D[Join Reasoning]
        D --> E[Ambiguity Check]
    end

    subgraph T["Trust Gate"]
        E --> F[Governance Validation]
        F --> G[Confidence Propagation]
    end

    subgraph O["Outcomes"]
        G -->|High trust| H[SQL Generation]
        G -->|Low confidence / ambiguity| I[Safe Refusal]
        G -->|Policy risk| J[Governance Block]
        H --> K[SQL Output]
        I --> L[Refusal Explanation]
        J --> M[Blocked Explanation]
    end

    classDef reasoning fill:#c9dcff,stroke:#89a9e8,stroke-width:2px,color:#24324d,rx:8px,ry:8px;
    classDef governance fill:#ffd9c9,stroke:#e0aa8d,stroke-width:2px,color:#4f3428,rx:8px,ry:8px;
    classDef confidence fill:#ccefdc,stroke:#84bc9f,stroke-width:2px,color:#213a30,rx:8px,ry:8px;
    classDef success fill:#bee9df,stroke:#68b7a2,stroke-width:2.5px,color:#173730,rx:8px,ry:8px;
    classDef refusal fill:#ffe8b8,stroke:#d8b065,stroke-width:2.5px,color:#5b460f,rx:8px,ry:8px;
    classDef blocked fill:#f6c8d1,stroke:#d78c9a,stroke-width:2.5px,color:#5a2430,rx:8px,ry:8px;
    classDef neutral fill:#ddd8ff,stroke:#9ca5e7,stroke-width:2px,color:#2d3158,rx:8px,ry:8px;
    classDef group fill:#151d30,stroke:#5d6b86,stroke-width:1.5px,color:#d8e1ef;

    class A neutral;
    class B,C,D,E reasoning;
    class F governance;
    class G confidence;
    class H,K success;
    class I,L refusal;
    class J,M blocked;
    class P,T,O group;

    linkStyle default stroke:#a7b7d6,stroke-width:2px;
    linkStyle 5 stroke:#68b7a2,stroke-width:3px;
    linkStyle 6 stroke:#d8b065,stroke-width:3px;
    linkStyle 7 stroke:#d78c9a,stroke-width:3px;
    linkStyle 8 stroke:#68b7a2,stroke-width:3px;
    linkStyle 9 stroke:#d8b065,stroke-width:3px;
    linkStyle 10 stroke:#d78c9a,stroke-width:3px;
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
Trust-Aware-Metadata-Intelligence/
│
├── ingestion/          # Manifest ingestor, lineage parser, graph store
├── reasoning/          # Query planner, entity extractor, confidence scorer
├── retrieval/          # Embedding ranker, glossary matcher, lineage scorer
├── generation/         # SQL generator, refusal engine
├── governance/         # PII detector, RBAC validator, cost estimator
├── explainability/     # Explanation formatter
├── evaluation/         # Benchmark runner and failure taxonomy tests
├── frontend/           # Streamlit reasoning demo
├── agents/             # Optional sequential orchestration layer
├── docs/               # Design references and architecture docs
└── tests/              # Full test suite (439 passing)
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

**439 tests passing** across ingestion, reasoning, retrieval, governance, generation, explainability, and evaluation modules.

> The benchmark suite intentionally prioritizes trustworthy refusal behavior and governance enforcement over unconstrained SQL generation — which explains the strong Refusal Recall and Governance Recall scores relative to Overall Accuracy.

---

## Demo

The project includes a single-page Streamlit reasoning demo that shows SQL generation, safe refusal behavior, governance blocking, confidence propagation, metadata grounding, and join reasoning — without exposing raw orchestration complexity.

```bash
streamlit run app.py
```

---

## Screenshots

Final README screenshots are still pending capture from the Streamlit demo:

- `SAFE SQL GENERATED`
- `SAFE REFUSAL`
- `GOVERNANCE BLOCK`

Those are the only remaining public-artifact images not yet checked in.

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

This project explores how enterprise text-to-SQL systems can become more trustworthy through:

- deterministic metadata reasoning
- semantic ambiguity detection
- governance-aware planning
- confidence-aware orchestration
- constrained SQL generation

Future directions include dbt manifest ingestion, enterprise lineage reasoning, semantic join inference, and warehouse observability integration.

---

## Key Differentiator

Most text-to-SQL systems ask:

> *Can the LLM generate SQL?*

This project asks:

> **Should the system generate SQL at all?**

That distinction is the foundation of this architecture.

```mermaid
%%{init: {
  "theme": "base",
  "themeVariables": {
    "background": "#0f172a",
    "primaryTextColor": "#eef2ff",
    "secondaryTextColor": "#e8eefb",
    "lineColor": "#a7b7d6",
    "fontFamily": "Segoe UI, Arial, sans-serif"
  },
  "flowchart": {
    "nodeSpacing": 34,
    "rankSpacing": 42,
    "curve": "basis"
  }
}}%%
flowchart LR
    subgraph C1["Conventional Pipeline"]
        A[Conventional SQL] --> B[Schema Retrieval]
        B --> C[LLM SQL Generation]
        C --> D[Unchecked Risk]
    end

    subgraph C2["Trust-Aware Pipeline"]
        E[This System] --> F[Metadata Reasoning]
        F --> G[Governance + Confidence]
        G --> H{Should SQL be generated?}
        H -->|Yes| I[Trusted SQL]
        H -->|No| J[Refuse or Block]
    end

    classDef conventional fill:#d8deea,stroke:#98a6bf,stroke-width:2px,color:#303948,rx:8px,ry:8px;
    classDef conventionalRisk fill:#f3cbd1,stroke:#d28f99,stroke-width:2.5px,color:#57252e,rx:8px,ry:8px;
    classDef trusted fill:#c9dcff,stroke:#89a9e8,stroke-width:2px,color:#24324d,rx:8px,ry:8px;
    classDef trustedGate fill:#ccefdc,stroke:#84bc9f,stroke-width:2px,color:#213a30,rx:8px,ry:8px;
    classDef decision fill:#b9c8f4,stroke:#738ccc,stroke-width:3px,color:#1f2943;
    classDef trustedOutcome fill:#bee9df,stroke:#68b7a2,stroke-width:2.5px,color:#173730,rx:8px,ry:8px;
    classDef blockedOutcome fill:#ffe8b8,stroke:#d8b065,stroke-width:2.5px,color:#5b460f,rx:8px,ry:8px;
    classDef group fill:#151d30,stroke:#5d6b86,stroke-width:1.5px,color:#d8e1ef;

    class A,B,C conventional;
    class D conventionalRisk;
    class E,F trusted;
    class G trustedGate;
    class H decision;
    class I trustedOutcome;
    class J blockedOutcome;
    class C1,C2 group;

    linkStyle default stroke:#a7b7d6,stroke-width:2px;
    linkStyle 2 stroke:#d28f99,stroke-width:3px;
    linkStyle 6 stroke:#68b7a2,stroke-width:3px;
    linkStyle 7 stroke:#d8b065,stroke-width:3px;
```

---

## License

MIT License
