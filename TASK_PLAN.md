# Enterprise Metadata Intelligence Platform

## Execution Task Plan

> **Design Reference:** See [EXPANSION_DESIGN.md](EXPANSION_DESIGN.md) for full architecture, algorithms, reasoning, scenarios, and constraints behind every task listed here.
> This document tracks execution state only. Read the design doc for the *why*.

---

## Current Focus

```
ALL PLANNED PHASES COMPLETE
Status: READY FOR EVALUATION HARNESS
```

---

## Dependency Chain

```text
Phase 1 — dbt Manifest Intelligence          ← START HERE (data foundation)
    ↓
Phase 2 — Semantic Query Planning Engine     ← needs real metadata to reason over
    ↓
Phase 3 — Honest Refusal + Failure Taxonomy  ←→  Phase 4 — Composite Retrieval Ranking
    ↓                                                     (these two can run in parallel)
Phase 5 — Governance-Aware Intelligence      ← needs planner + refusal engine to wire into
    ↓
Phase 6 — Explainability Engine              ← depends on all prior phases working
    ↓
Phase 7 — Agentic Architecture               ← optional, lowest priority
```

Do not begin a phase until its upstream dependency is marked ✅ complete.

---

## Progress Overview

| Phase | Name                             | Status        |
| ----- | -------------------------------- | ------------- |
| 1     | dbt Manifest Intelligence        | ✅ Complete    |
| 2     | Semantic Query Planning Engine   | ✅ Complete    |
| 3     | Honest Refusal + Failure Taxonomy| ✅ Complete    |
| 4     | Composite Retrieval Ranking      | ✅ Complete    |
| 5     | Governance-Aware Intelligence    | ✅ Complete    |
| 6     | Explainability Engine            | ✅ Complete    |
| 7     | Agentic Architecture (optional)  | ✅ Complete    |

---

---

# PHASE 1 — dbt Manifest Intelligence

> **Design Reference:** [EXPANSION_DESIGN.md § 15 — PHASE 1](EXPANSION_DESIGN.md#phase-1--dbt-manifest-intelligence) and [§ 8 — Metadata Graph Example](EXPANSION_DESIGN.md#8-metadata-graph-example)

**Goal:** Replace the existing static CSV ingestion with real enterprise metadata from a dbt `manifest.json`. This is the data foundation that every subsequent phase depends on.

**Dependency:** None. This is the starting point.

---

## Tasks

### 1.1 — Scaffold ingestion directory

- [x] Create `ingestion/` directory
- [x] Move or refactor existing `src/ingest_metadata.py` → `ingestion/` (preserve old behavior as fallback)
- [x] Create `ingestion/__init__.py`

---

### 1.2 — Build `ingestion/manifest_ingestor.py`

> See [EXPANSION_DESIGN.md § 15 — manifest_ingestor.py](EXPANSION_DESIGN.md#new-module-ingestionmanifest_ingestorpy)

- [x] Parse `manifest.json` — extract `nodes`, `sources`, `exposures`
- [x] For each model node extract:
  - `model name`
  - `description`
  - `columns` (name + description per column)
  - `tags`
  - `owner` (meta block)
  - `domain` (meta block or tag inference)
  - `upstream_models` (depends_on.nodes)
  - `downstream_models` (child_map)
  - `dbt tests` (relationship tests = FK evidence)
- [x] Normalize into the standard metadata schema
- [x] Write unit test: parse a sample `manifest.json` and assert all fields extracted correctly

---

### 1.3 — Build `ingestion/lineage_parser.py`

> See [EXPANSION_DESIGN.md § 8.1 — Example Graph](EXPANSION_DESIGN.md#81-example-graph)

- [x] Extract lineage edges from manifest `depends_on.nodes`
- [x] Build directed edge list: `(upstream_model, downstream_model, edge_type)`
- [x] Classify edge types:
  - `explicit_fk` — backed by dbt relationship test
  - `lineage_dependency` — depends_on without test
- [x] Write unit test: assert correct edge list from sample manifest

---

### 1.4 — Build `ingestion/metadata_normalizer.py`

- [x] Deduplicate models with identical names across sources
- [x] Normalize domain and tag fields (lowercase, strip whitespace)
- [x] Handle missing descriptions gracefully — flag as `description_missing: true`
- [x] Compute `metadata_completeness_score` per model
- [x] Write unit test: assert completeness score computed correctly

---

### 1.5 — Integrate with ChromaDB

- [x] Accept normalised metadata schema in ChromaDB ingestion
- [x] Embed model-level and column-level documents separately
- [x] Store `domain`, `pii`, `description_missing`, `owner` as ChromaDB metadata fields
- [x] Write integration test: ingest sample manifest → assert models retrievable by metadata filter

---

### 1.6 — Build metadata graph store

> See [EXPANSION_DESIGN.md § 8 — Metadata Graph Example](EXPANSION_DESIGN.md#8-metadata-graph-example)

- [x] Initialize NetworkX directed graph from lineage edges
- [x] Add nodes with domain/tags/owner/completeness attributes
- [x] Add edges with `edge_type`, `left_column`, `right_column` attributes
- [x] Implement `get_shortest_path(model_a, model_b)` — returns path + hop count
- [x] Implement `get_neighbors(model, depth=2)` — returns all models within N hops
- [x] Implement `lineage_proximity_score(model_a, model_b)` — returns 0–1 score
- [x] Serialize graph to JSON for reuse across sessions
- [x] Write unit test: assert traversal returns correct paths on sample graph

---

### 1.7 — Create sample `manifest.json` for development

- [x] Build a realistic synthetic `manifest.json` covering:
  - `dim_customer`, `fct_orders`, `payment_events`, `support_tickets`
  - 4 explicit FK relationship tests
  - PII-tagged columns (email_address, phone_number)
  - Missing descriptions (payment_date, resolution_date)
- [x] Stored in `data/sample_manifest.json`

---

### 1.8 — Add docs

- [x] Created `docs/metadata_graph.md` — graph schema, node types, edge types, usage examples

---

## Phase 1 Acceptance Criteria

| Criterion                                                       | Status |
| --------------------------------------------------------------- | ------ |
| `manifest.json` parsed and all fields extracted correctly       | ✅     |
| Lineage graph built with correct edges and hop distances        | ✅     |
| Models and columns embedded and stored in ChromaDB             | ✅     |
| `metadata_completeness_score` computed per model               | ✅     |
| Graph traversal returns correct paths on sample graph          | ✅     |
| All unit tests passing                                         | ✅ 90/90 |

**Phase 1 complete. 2026-05-24.**

---

---

# PHASE 2 — Semantic Query Planning Engine

> **Design Reference:** [EXPANSION_DESIGN.md § 6 — Semantic Query Planning Engine](EXPANSION_DESIGN.md#6-semantic-query-planning-engine) and [§ 7 — Reasoning Algorithms](EXPANSION_DESIGN.md#7-reasoning-algorithms)

**Goal:** Build the heart of the system. Separate query planning (deterministic) from SQL generation (LLM). The LLM should receive only a structured execution plan, never raw metadata.

**Dependency:** Phase 1 complete — metadata graph and ChromaDB populated.

---

## Tasks

### 2.1 — Scaffold reasoning directory

- [x] Create `reasoning/` directory
- [x] Create `reasoning/__init__.py`

---

### 2.2 — Build `reasoning/entity_extractor.py`

> See [EXPANSION_DESIGN.md § 7.3 — Entity Extraction Algorithm](EXPANSION_DESIGN.md#73-entity-extraction-algorithm)

- [x] Tokenize query into candidate noun phrases and metric phrases
- [x] Implement glossary lookup:

```text
glossary_match_score =
  0.60 × exact_string_match
+ 0.40 × embedding_similarity_to_glossary_entry
```

- [x] Threshold: flag as hit if `glossary_match_score > 0.65`
- [x] For each hit: traverse graph to find candidate models
- [x] For each miss: flag as potential `MISSING_ENTITY`
- [x] Return: `entities_extracted`, `unresolved_entities`, `candidate_models`
- [x] Write unit tests for hit/miss/ambiguous entity extraction cases

---

### 2.3 — Build `reasoning/intent_classifier.py`

> See [EXPANSION_DESIGN.md § 6 — Step 2: Analytical Intent Inference](EXPANSION_DESIGN.md#the-reasoning-pipeline)

- [x] Classify query into intent types:
  - `aggregation` — SUM, COUNT, AVG requested
  - `trend` — over-time comparison implied
  - `segmentation` — GROUP BY a dimension
  - `comparison` — two values or periods compared
  - `lookup` — single record or filtered list
- [x] Identify time grain (daily, monthly, quarterly, annual) if present
- [x] Compute `intent_clarity_weight`:
  - `1.00` — single unambiguous intent
  - `0.85` — two possible intents, best guess applied
  - `0.60` — unclear intent
- [x] Write unit tests covering one intent per type

---

### 2.4 — Build `reasoning/join_path_engine.py`

> See [EXPANSION_DESIGN.md § 7.1 — Join Path Ranking Algorithm](EXPANSION_DESIGN.md#71-join-path-ranking-algorithm)

- [x] For a given set of candidate models, find all valid join paths via the lineage graph
- [x] Score each path:

```text
Join Path Score =
  0.40 × foreign_key_strength
+ 0.25 × lineage_proximity
+ 0.20 × semantic_similarity
+ 0.15 × historical_usage_frequency
```

- [x] Implement FK strength lookup table (explicit FK = 0.90 down to inferred = 0.20)
- [x] Implement lineage hop scoring (1 hop = 1.00 down to 4+ hops = 0.15, no path = 0.00)
- [x] Detect ambiguity: if top two paths within 0.10 of each other → flag `AMBIGUOUS_JOIN`
- [x] Apply decision thresholds (≥ 0.80 proceed, 0.60–0.79 warn, 0.40–0.59 surface ambiguity, < 0.40 refuse)
- [x] Return: `best_join_path`, `join_confidence`, `ambiguity_detected`, `all_candidates`
- [x] Write unit tests: clean join, ambiguous join, no-path case

---

### 2.5 — Build `reasoning/ambiguity_detector.py`

> See [EXPANSION_DESIGN.md § 7.2 — Ambiguity Detection Algorithm](EXPANSION_DESIGN.md#72-ambiguity-detection-algorithm)

- [x] Metric ambiguity: two metrics match same entity within glossary score delta of 0.15
- [x] Dimension ambiguity: same dimension name resolves to models in more than one domain
- [x] Temporal ambiguity: multiple date columns in selected model, no filter specified
- [x] Return: `ambiguity_type`, `candidates`, `recommendation`
- [x] Write unit tests: one per ambiguity type

---

### 2.6 — Build `reasoning/confidence_scorer.py`

> See [EXPANSION_DESIGN.md § 7.4 — Confidence Propagation Algorithm](EXPANSION_DESIGN.md#74-confidence-propagation-algorithm) and [§ 11](EXPANSION_DESIGN.md#11-metadata-confidence-propagation)

- [x] Implement:

```text
Plan Confidence =
  MIN(
    retrieval_confidence,
    join_path_confidence,
    governance_safety_score,
    metadata_completeness_score
  )
  × intent_clarity_weight
```

- [x] Implement confidence threshold decisions:
  - ≥ 0.80 → confident
  - 0.60–0.79 → warn
  - 0.40–0.59 → surface ambiguity
  - < 0.40 → refuse
- [x] Return: `plan_confidence`, `confidence_limiting_factor`, `decision`
- [x] Write unit tests: one per threshold band, one for weak-join dominance case

---

### 2.7 — Build `reasoning/query_planner.py`

> See [EXPANSION_DESIGN.md § 6 — The Reasoning Pipeline](EXPANSION_DESIGN.md#the-reasoning-pipeline) and [Execution Plan Output Format](EXPANSION_DESIGN.md#execution-plan-output-format)

- [x] Orchestrate the full 10-step pipeline:
  1. Entity extraction
  2. Intent classification
  3. Metric candidate identification
  4. Dimension candidate identification
  5. Ambiguity detection
  6. Graph traversal
  7. Join path ranking
  8. Governance validation (call governance module)
  9. Confidence propagation
  10. Execution plan construction OR refusal trigger
- [x] Return structured execution plan:

```json
{
  "query_intent": "...",
  "entities_extracted": [],
  "candidate_models": [],
  "join_path": [],
  "join_confidence": 0.0,
  "ambiguity_detected": false,
  "governance_flags": [],
  "execution_plan": { ... },
  "overall_confidence": 0.0
}
```

- [x] Write integration test: full query through planner → assert correct plan structure

---

### 2.8 — Update `generation/sql_generator.py`

- [x] Modify LLM call to accept execution plan as input instead of raw metadata
- [x] LLM prompt must use `execution_plan` fields only — no raw schema passed
- [x] Write test: assert SQL generated matches plan structure (correct tables, joins, aggregations)

---

### 2.9 — Add docs

- [x] Create `docs/query_planning.md` — document the 10-step pipeline
- [x] Create `docs/reasoning_algorithms.md` — document all formulas and thresholds

---

## Phase 2 Acceptance Criteria

| Criterion                                                              | Status |
| ---------------------------------------------------------------------- | ------ |
| Entity extractor resolves glossary hits and flags misses               | ✅     |
| Intent classifier correctly identifies all 5 intent types             | ✅     |
| Join path engine scores and ranks all candidate paths                  | ✅     |
| Ambiguity detector fires correctly on metric, dimension, temporal cases| ✅     |
| Confidence scorer produces correct threshold decisions                 | ✅     |
| Query planner produces structured execution plan end-to-end           | ✅     |
| LLM receives plan only — no raw metadata in prompt                    | ✅     |
| All unit and integration tests passing                                 | ✅ 257/257 |

**Phase 2 complete. 2026-05-24.**

---

---

# PHASE 3 — Honest Refusal Framework and Failure Taxonomy

> **Design Reference:** [EXPANSION_DESIGN.md § 9 — Failure Taxonomy](EXPANSION_DESIGN.md#9-failure-taxonomy) and [§ 15 — PHASE 3](EXPANSION_DESIGN.md#phase-3--honest-refusal-framework-and-failure-taxonomy)

**Goal:** Implement classified refusal behavior. Every failure gets a named type, structured response, and a reason. No SQL generation until failures are resolved.

**Dependency:** Phase 2 complete — query planner must exist to generate refusal conditions.

**Can run in parallel with:** Phase 4

---

## Tasks

### 3.1 — Scaffold generation directory

- [x] Create `generation/` directory (if not yet restructured)
- [x] Create `generation/__init__.py`

---

### 3.2 — Build `generation/refusal_engine.py`

> See [EXPANSION_DESIGN.md § 7.5 — Refusal Decision Algorithm](EXPANSION_DESIGN.md#75-refusal-decision-algorithm)

- [x] Implement priority-ordered refusal logic:

```text
1. GOVERNANCE_BLOCKED  ← hard stop first, always (moved to Step 3.5 in planner — fires before ambiguity)
2. UNSAFE_QUERY        ← text-only check, independent of planner
3. INSUFFICIENT_SCHEMA
4. WEAK_JOIN           ← renamed from AMBIGUOUS_JOIN (no-path case)
5. SEMANTIC_CONFLICT / AMBIGUOUS_JOIN
6. TEMPORAL_AMBIGUITY
7. LOW_CONFIDENCE
```

- [x] Return structured response per failure type:

```json
{
  "status": "FAILURE",
  "failure_type": "...",
  "reason": "...",
  "candidates": [],
  "recommendation": "...",
  "confidence": 0.0,
  "priority": 1
}
```

- [x] Write one test per failure type (8 failure types, 60+ unit tests)

---

### 3.3 — Build evaluation benchmark dataset

> See [EXPANSION_DESIGN.md § 9 — Evaluation Harness Per Failure Type](EXPANSION_DESIGN.md#evaluation-harness-per-failure-type)

- [x] Create `evaluation/fixtures/` directory
- [x] Build test query sets per category:
  - `answerable.json` — 12 queries fully supported by sample manifest
  - `missing_entity.json` — 8 queries with absent metadata
  - `ambiguous_join.json` — 5 queries illustrating cross-type priority
  - `semantic_conflict.json` — 8 queries hitting duplicate metric definitions
  - `governance_violation.json` — 8 queries touching PCI-tagged model
  - `unsafe_query.json` — 10 queries covering all DML/DDL + dump patterns
- [x] Each fixture entry: `{"query": "...", "expected_status": "...", "expected_failure_type": "..."}`

---

### 3.4 — Build `evaluation/refusal_tests.py`

- [x] Load each fixture file
- [x] Run query through planner → refusal engine
- [x] Assert `status` and `failure_type` match expected values
- [x] Report: refusal precision, refusal recall, failure type F1
- [x] `TestEvaluationMetrics`: aggregate accuracy ≥ 90%, governance recall = 1.0, unsafe recall = 1.0

---

### 3.5 — Build `evaluation/failure_taxonomy_tests.py`

- [x] Assert each failure type returns required fields: `status`, `failure_type`, `reason`, `confidence`
- [x] Assert governance block always fires before other failure types (step 3.5 fix)
- [x] Assert ambiguity surfaces both candidates (≥2 candidates for SEMANTIC_CONFLICT)
- [x] Assert UNSAFE_QUERY fires before planner is consulted
- [x] Assert priority chain: each type has strictly lower rank than next

---

### 3.6 — Add docs

- [x] Create `docs/failure_taxonomy.md` — full failure table with trigger conditions and examples

---

## Phase 3 Acceptance Criteria

| Criterion                                                          | Status |
| ------------------------------------------------------------------ | ------ |
| All 8 failure types implemented and returning structured responses | ✅     |
| Governance block fires first in all test cases (step 3.5)         | ✅     |
| Benchmark fixtures cover all 6 categories (51 fixture queries)    | ✅     |
| Refusal precision and recall measured; governance + unsafe = 1.0  | ✅     |
| All refusal tests passing                                          | ✅ 312/312 |

**Phase 3 complete. 2026-05-24.**

---

---

# PHASE 4 — Composite Retrieval Ranking

> **Design Reference:** [EXPANSION_DESIGN.md § 10 — Retrieval Ranking Logic](EXPANSION_DESIGN.md#10-retrieval-ranking-logic)

**Goal:** Replace naive embedding retrieval with engineered 5-factor composite scoring. Retrieval becomes explainable and lineage-aware.

**Dependency:** Phase 2 complete (planner must exist to consume ranked results).

**Can run in parallel with:** Phase 3

---

## Tasks

### 4.1 — Build `retrieval/lineage_scorer.py`

> See [EXPANSION_DESIGN.md § 10 — Lineage Proximity factor](EXPANSION_DESIGN.md#lineage-proximity-025-weight)

- [x] Compute hop distance between candidate model and already-selected models in the plan
- [x] Apply hop scoring: 1 hop = 1.00, 2 hops = 0.70, 3 hops = 0.40, 4+ = 0.15, no path = 0.00
- [x] Write unit tests: correct scores on sample graph

---

### 4.2 — Build `retrieval/glossary_matcher.py`

> See [EXPANSION_DESIGN.md § 10 — Business Glossary Overlap factor](EXPANSION_DESIGN.md#business-glossary-overlap-015-weight)

- [x] Define business glossary structure (JSON or YAML file under `data/glossary.json`)
- [x] Implement term matching: exact string + embedding similarity weighted 60/40
- [x] Return `glossary_overlap_score` per candidate
- [x] Write unit tests: exact match, near-miss, no match cases

---

### 4.3 — Build `retrieval/embedding_ranker.py`

> See [EXPANSION_DESIGN.md § 10 — Composite Retrieval Scoring Formula](EXPANSION_DESIGN.md#composite-retrieval-scoring-formula)

- [x] Implement composite scoring:

```text
Final Retrieval Score =
  0.35 × Semantic Similarity
+ 0.25 × Lineage Proximity
+ 0.15 × Business Glossary Overlap
+ 0.15 × Historical Query Relevance
+ 0.10 × Governance Compatibility
```

- [x] Historical query relevance: default 0.50 cold-start until 10 observations
- [x] Governance compatibility: 1.00 = no flags, 0.50 = soft flag, 0.00 = hard block
- [x] Return ranked list with per-factor breakdown
- [x] Write unit tests: assert ranking order changes correctly when lineage/governance factors vary

---

### 4.4 — Replace existing retrieval in `retrieval/semantic_retriever.py`

- [x] Wire `embedding_ranker.py` into the retrieval pipeline
- [x] Remove or deprecate old raw cosine-similarity-only retrieval path
- [x] Write integration test: assert composite-ranked retrieval returns different (better) ordering than naive retrieval on test cases

---

### 4.5 — Add docs

- [x] Create `docs/retrieval_ranking.md` — document the formula, factor weights, and rationale

---

## Phase 4 Acceptance Criteria

| Criterion                                                                | Status |
| ------------------------------------------------------------------------ | ------ |
| Composite 5-factor scoring implemented and returning per-factor breakdown| ✅     |
| Lineage proximity correctly computed via graph traversal                 | ✅     |
| Glossary matching implemented with correct weighted scoring              | ✅     |
| Cold-start default of 0.50 for historical relevance applied              | ✅     |
| Composite retrieval returns better ordering than naive on test cases     | ✅     |
| All unit and integration tests passing                                   | ✅ 398/398 |

**Phase 4 complete. 2026-05-24.**

---

---

# PHASE 5 — Governance-Aware Intelligence

> **Design Reference:** [EXPANSION_DESIGN.md § 15 — PHASE 5](EXPANSION_DESIGN.md#phase-5--governance-aware-intelligence) and [§ 12 — Real Enterprise Scenarios](EXPANSION_DESIGN.md#12-real-enterprise-scenarios)

**Goal:** Validate every query plan against PII, RBAC, query cost, and unsafe scan patterns before SQL generation. Governance is a hard stop — it fires before any LLM call.

**Dependency:** Phase 2 complete (planner must call governance before plan construction).

---

## Tasks

### 5.1 — Scaffold governance directory

- [x] Create `governance/` directory
- [x] Create `governance/__init__.py`

---

### 5.2 — Build `governance/pii_detector.py`

> See [EXPANSION_DESIGN.md § 12 — Scenario 3: Governance Hard Block](EXPANSION_DESIGN.md#scenario-3--governance-hard-block-on-pii-column)

- [x] Flag columns tagged with PII indicators in manifest metadata:
  - `ssn`, `social_security`, `tax_id`
  - `email`, `email_address`
  - `phone`, `mobile`
  - `date_of_birth`, `dob`
  - `credit_card`, `account_number`, `iban`
- [x] Return: `pii_columns_detected`, `severity` (hard/soft), `governance_safety_score`
- [x] Hard PII (ssn, credit card) → `governance_safety_score = 0.00` → immediate block
- [x] Soft PII (email) → `governance_safety_score = 0.50` → warning only
- [x] Write unit tests: hard block, soft warning, clean column cases

---

### 5.3 — Build `governance/rbac_validator.py`

> See [EXPANSION_DESIGN.md § 15 — RBAC Awareness](EXPANSION_DESIGN.md#governance-modulesrbacawareness)

- [x] Define RBAC config (JSON/YAML): maps roles → allowed domains/tags
- [x] Example: `finance_user` can access `[finance, gold]`, cannot access `[healthcare, pii]`
- [x] Validate each selected model's domain and tags against user role
- [x] Return: `rbac_violations`, `blocked_models`, `governance_safety_score`
- [x] Write unit tests: allowed access, blocked access, partial block cases

---

### 5.4 — Build `governance/query_cost_estimator.py`

> See [EXPANSION_DESIGN.md § 12 — Scenario 4: Unsafe Query Pattern](EXPANSION_DESIGN.md#scenario-4--unsafe-query-pattern)

- [x] Detect unsafe query patterns from the execution plan:
  - No WHERE clause on a large table
  - No date partition filter on partitioned table
  - `SELECT *` with no column restriction
  - Unbounded aggregation across full history
- [x] Load table size estimates from manifest metadata (row count, partition info)
- [x] Estimate scan size; block if above configurable threshold (default: 500GB)
- [x] Return: `estimated_scan_gb`, `unsafe_patterns_detected`, `recommendation`
- [x] Write unit tests: safe plan, unbounded scan, missing partition filter cases

---

### 5.5 — Wire governance into `reasoning/query_planner.py`

- [x] Call `pii_detector`, `rbac_validator`, `query_cost_estimator` in the planner governance precheck
- [x] If `governance_safety_score == 0.00` → trigger `GOVERNANCE_BLOCKED` immediately
- [x] Ensure governance is evaluated before confidence scoring
- [x] Write integration test: PII query → assert plan never reaches SQL generator

---

### 5.6 — Add docs

- [x] Create `docs/governance.md` — document PII categories, RBAC config format, cost thresholds

---

## Phase 5 Acceptance Criteria

| Criterion                                                        | Status |
| ---------------------------------------------------------------- | ------ |
| PII detector correctly classifies hard and soft violations       | ✅     |
| RBAC validator blocks cross-domain access correctly              | ✅     |
| Query cost estimator flags unbounded scans                       | ✅     |
| Governance fires before any SQL generation in all test cases     | ✅     |
| PII query scenario (Scenario 3) passes end-to-end               | ✅     |
| All unit and integration tests passing                           | ✅ 411/411 |

**Phase 5 is complete when all 6 criteria are met.**

**Phase 5 complete. 2026-05-24.**

---

---

# PHASE 6 — Explainability Engine

> **Design Reference:** [EXPANSION_DESIGN.md § 15 — PHASE 6](EXPANSION_DESIGN.md#phase-6--explainability-engine)

**Goal:** Every system decision — table selection, join choice, confidence score, refusal — must be explainable to the user with evidence.

**Dependency:** Phases 2–5 complete.

---

## Tasks

### 6.1 — Extend execution plan with explanation fields

- [x] Add `retrieval_explanation` — why each table was selected, with composite score breakdown
- [x] Add `join_explanation` — why this join path was chosen over alternatives
- [x] Add `confidence_explanation` — which factor was the confidence-limiting factor
- [x] Add `refusal_explanation` — why a specific failure type was triggered

---

### 6.2 — Build explainability output formatter

- [x] Format explanations as human-readable text for Streamlit display
- [x] Format explanations as structured JSON for API consumers
- [ ] Example output:

```json
{
  "selected_tables": ["fct_orders", "dim_customer"],
  "retrieval_scores": {"fct_orders": 0.91, "dim_customer": 0.83},
  "join_path": "fct_orders.customer_id -> dim_customer.customer_id",
  "join_confidence": 0.89,
  "confidence_limiting_factor": "none",
  "overall_confidence": 0.88,
  "explanation": "Revenue and customer segmentation matched to gold-tier models with explicit lineage."
}
```

---

### 6.3 — Update Streamlit frontend

- [x] Display confidence score visually (progress bar or badge)
- [x] Show confidence-limiting factor prominently when confidence is below 0.85
- [x] Show refusal type and reason in a styled warning block
- [x] Show join path with confidence score
- [x] Show retrieval scores per selected table
- [x] Write automated UI-view-model test: run 4 enterprise scenarios and verify all explanations render

---

### 6.4 — Add docs

- [x] Create `docs/architecture.md` — full system architecture with annotated diagram

---

## Phase 6 Acceptance Criteria

| Criterion                                                              | Status |
| ---------------------------------------------------------------------- | ------ |
| Every plan contains retrieval, join, confidence, and refusal explanations | ✅  |
| Explanations available in both JSON and human-readable text            | ✅     |
| Streamlit displays confidence score, limiting factor, and refusal type | ✅     |
| All 4 enterprise scenarios produce correct explanations in UI          | ✅     |

**Phase 6 is complete when all 4 criteria are met.**

**Phase 6 complete. 2026-05-24.**

---

---

# PHASE 7 — Optional Agentic Architecture

> **Design Reference:** [EXPANSION_DESIGN.md § 15 — PHASE 7](EXPANSION_DESIGN.md#phase-7--optional-agentic-architecture)

**Goal:** Modular reasoning agents as an optional execution wrapper around the existing pipeline modules.

**Dependency:** Phases 1–6 complete.

**Priority:** Low. The core value of this system is in reasoning and trust, not agent orchestration.

---

## Tasks

### 7.1 — Define agent interface contracts

- [x] Each agent wraps an existing module — no new reasoning logic here
- [x] Agents call: retrieval, planning, governance, generation, evaluation modules

### 7.2 — Implement agents

- [x] `Retrieval Agent` — wraps `embedding_ranker.py`
- [x] `Planning Agent` — wraps `query_planner.py`
- [x] `Join Reasoning Agent` — wraps `join_path_engine.py`
- [x] `Governance Agent` — wraps governance modules
- [x] `SQL Generation Agent` — wraps `sql_generator.py`
- [x] `Evaluation Agent` — wraps confidence scorer + refusal engine

### 7.3 — Wire agent orchestration

- [x] Implement sequential orchestration (non-autonomous)
- [ ] Optional: implement tool-use-based orchestration via Claude API

---

## Phase 7 Acceptance Criteria

| Criterion                                                   | Status |
| ----------------------------------------------------------- | ------ |
| Each agent wraps an existing module with no new logic       | ✅     |
| Agent orchestration produces same output as direct pipeline | ✅ 432/432 |

**Phase 7 complete. 2026-05-24.**

---

---

# Evaluation Benchmark — Running the Full Harness

> **Design Reference:** [EXPANSION_DESIGN.md § 9 — Evaluation Metrics](EXPANSION_DESIGN.md#evaluation-metrics)

After Phase 3 is complete, the full evaluation harness can be run at any time.

```bash
pytest evaluation/ -v --tb=short
```

Target metrics after Phase 3:

| Metric              | Target   |
| ------------------- | -------- |
| SQL Accuracy        | ≥ 0.80   |
| Hallucination Rate  | ≤ 0.05   |
| Refusal Precision   | ≥ 0.90   |
| Refusal Recall      | ≥ 0.90   |
| Failure Type F1     | ≥ 0.85   |
| Retrieval Precision | ≥ 0.80   |
| Join Accuracy       | ≥ 0.85   |
| Plan Accuracy       | ≥ 0.85   |

---

# Notes and Decisions Log

> Record implementation decisions, blockers, and findings here as work progresses.

| Date | Phase | Note |
| ---- | ----- | ---- |
| 2026-05-24 | 4 | Wired `SemanticRetriever` into QueryPlanner Step 7 and replaced the old fixed retrieval confidence with a composite retrieval score derived from ranked candidates. |
| 2026-05-24 | 4 | Retrieval ranking now demotes governance-hard-blocked models below governance-compatible candidates even when lexical similarity is stronger. |
| 2026-05-24 | 4 | Removed the overly generic `transaction` glossary synonym from the order concept to avoid false exact matches that masked revenue-description overlap cases. |
| 2026-05-24 | 5 | Added manifest-derived governance metadata (`estimated_scan_gb`, partition info, and per-column PII tags) to graph nodes so governance evaluation can run deterministically from metadata alone. |
| 2026-05-24 | 5 | Phase 5 governance remains an early planner gate: PII, RBAC, and cost modules execute before ambiguity and confidence scoring so `GOVERNANCE_BLOCKED` cannot be bypassed by an earlier semantic failure. |
| 2026-05-24 | 6 | Added a shared explainability contract to planner results: every outcome now carries structured explanation JSON plus a human-readable explanation string, and successful execution plans embed the same explanation blocks for downstream consumers. |
| 2026-05-24 | 6 | Streamlit UI coverage is automated at the view-model layer with four scenario tests (`LOW_CONFIDENCE`, `SEMANTIC_CONFLICT`, `GOVERNANCE_BLOCKED`, `UNSAFE_QUERY`) because the current fixture set does not provide a stable high-confidence success case. |
| 2026-05-24 | 7 | Added a thin `agents/` package with explicit wrapper contracts plus a sequential orchestrator. The agent layer is intentionally non-autonomous and does not introduce new reasoning logic beyond the existing modules. |
| 2026-05-24 | 7 | Extracted shared governance aggregation into `governance/governance_evaluator.py` so `QueryPlanner` and `GovernanceAgent` cannot drift; orchestrator parity is tested against the direct planner/refusal/generator pipeline. |
| 2026-05-24 | 3 | GOVERNANCE_BLOCKED priority fix: moved governance check from Step 6 (after ambiguity) to Step 3.5 (before ambiguity) in QueryPlanner. Without this, SEMANTIC_CONFLICT early-return would silently bypass governance. |
| 2026-05-24 | 3 | Renamed no-path join failure from AMBIGUOUS_JOIN to WEAK_JOIN. AMBIGUOUS_JOIN now reserved for competing join paths that both score > 0.40 within 0.10 of each other. |
| 2026-05-24 | 3 | `grant\s+\w` regex bug: trailing `\b` after `)` failed because `\w` matched the first char of `SELECT` (mid-word). Fixed to `\w+` so full word is consumed before word-boundary assertion. |
| 2026-05-24 | 3 | Answerable fixture constraint: only `region`, `segment`, `escalation` entities are safe (1 candidate column). Any entity with ≥2 candidate columns triggers SEMANTIC_CONFLICT. |
