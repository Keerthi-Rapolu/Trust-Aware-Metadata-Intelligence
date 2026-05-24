# Enterprise Metadata Intelligence Platform

## Trust-Aware Enterprise Metadata Reasoning Platform

### Expansion Design Document

---

# 1. Executive Summary

This document defines the expansion strategy for the existing Vector DB Metadata SQL Assistant into a production-oriented **Trust-Aware Enterprise Metadata Reasoning Platform**.

The current system already provides:

* Metadata ingestion
* Vector similarity search
* Semantic retrieval
* SQL generation
* Discovery mode
* Domain-specific metadata handling

The next evolution focuses on:

* Deterministic metadata reasoning before LLM generation
* Semantic Query Planning Engine as the core reasoning layer
* Trustworthy SQL generation with honest refusal
* Semantic join-path reasoning with confidence scoring
* dbt manifest ingestion for real enterprise lineage
* Metadata graph intelligence with trust propagation
* Governance-aware validation and PII protection
* Enterprise-grade failure taxonomy and evaluation benchmarking

The primary architectural goal is:

> Move from "LLM-generated SQL" to "Trust-Aware Enterprise Metadata Reasoning."

This project intentionally avoids becoming another generic AI SQL chatbot.

The system evolves into:

> A metadata-aware semantic reasoning engine that constrains the LLM's search space through deterministic metadata intelligence — understanding enterprise analytics structures, validating ambiguity, and refusing unsafe or unsupported queries.

The critical distinction:

> **Existing systems:** LLM decides everything.
> **This system:** Metadata reasoning engine constrains LLM generation.

That is a fundamentally different architecture.

---

# 2. Problem Statement

Existing text-to-SQL systems suffer from major enterprise limitations:

## 2.1 Hallucinated SQL

LLMs frequently generate:

* Non-existent columns
* Invalid joins
* Unsupported aggregations
* Incorrect assumptions

Example:

User asks:

"Show revenue by product category"

But `product_category` does not exist in the schema.

Typical systems hallucinate:

```sql
SELECT product_category, SUM(revenue)
FROM sales
GROUP BY product_category
```

This creates unsafe enterprise behavior.

---

## 2.2 Lack of Semantic Understanding

Most systems rely only on:

* table names
* column names
* embeddings

But enterprises require understanding of:

* lineage
* ownership
* domain semantics
* join validity
* governance rules
* business concepts

---

## 2.3 No Ambiguity Detection

Enterprise warehouses often contain:

* duplicate customer IDs
* multiple revenue definitions
* competing source systems
* inconsistent dimensions

Current systems blindly choose joins.

---

## 2.4 No Governance Awareness

Most systems ignore:

* PII exposure
* RBAC restrictions
* unsafe scans
* excessive cost
* compliance constraints

---

## 2.5 Query Planning and SQL Generation Are Merged

Most systems do this:

```text
User Query → Retrieve Embeddings → Prompt LLM → SQL Output
```

There is no separation of reasoning from generation.

The LLM is simultaneously deciding:

* which tables to use
* which joins are valid
* what the user meant
* whether metadata exists
* what the governance rules are

This is the core architectural flaw.

---

# 3. Why Existing Text-to-SQL Systems Fail

This section explicitly positions the system against existing approaches.

---

## Sharp Comparison

| Dimension            | Existing Systems                        | This System                              |
| -------------------- | --------------------------------------- | ---------------------------------------- |
| Retrieval            | Embedding similarity only               | Metadata graph reasoning                 |
| SQL Generation       | LLM decides everything                  | Deterministic planning constrains LLM    |
| Query Planning       | Merged with SQL generation              | Explicit separate planning layer         |
| Joins                | Hallucinated or blindly chosen          | Confidence-ranked with lineage evidence  |
| Metadata             | Flat table/column names                 | Lineage-aware, domain-semantic metadata  |
| Governance           | Not considered                          | PII, RBAC, cost validation built-in      |
| Failure Behavior     | Hallucinates SQL                        | Classifies failure type and refuses      |
| Reasoning            | Opaque                                  | Explainable with evidence chains         |
| Ambiguity            | Silently resolved by LLM               | Detected, surfaced, and challenged       |
| Confidence           | Not measured                            | Propagated across the full pipeline      |

---

## Why This Matters Technically

Generic RAG systems ask: *"Which tables are most similar to this query?"*

This system asks: *"Is this query supportable, what is the valid join path, and what is the governance risk?"*

Those are fundamentally different questions.

---

# 4. Why RAG Alone Is Insufficient

> **This section directly attacks the core assumption behind most text-to-SQL systems.**

Retrieval-Augmented Generation is a powerful pattern.

For enterprise metadata reasoning, it is fundamentally insufficient.

---

## 4.1 Semantic Similarity Is Not Relational Validity

RAG retrieves documents based on embedding cosine similarity.

The retrieved documents may be semantically close to the query.

They may still be relationally invalid.

**Example:**

Query: *"Show revenue by customer segment"*

Embedding retrieval returns:
* `fct_orders` — high similarity (contains revenue)
* `dim_product_segment` — high similarity (contains "segment")

But `dim_product_segment` uses `product_id` as its key.

`fct_orders` joins to `dim_customer_segment` via `customer_id`.

The semantically similar model is the wrong model.

RAG cannot detect this.

Only lineage-aware reasoning can.

---

## 4.2 Embeddings Cannot Infer Safe Joins

Vector similarity has no concept of:

* foreign key relationships
* primary key uniqueness
* join cardinality
* fan-out risk
* grain mismatches

Two tables can have very high cosine similarity and still produce a catastrophically wrong join — a many-to-many cross product, a duplicate fan-out, or a broken grain.

RAG has no mechanism to detect or prevent this.

---

## 4.3 Vector Similarity Ignores Governance

A highly similar model can be:

* PII-restricted
* RBAC-protected
* under data retention constraints
* tagged with compliance restrictions

Embedding retrieval treats all documents equally regardless of governance tags.

A RAG system will happily return the most similar model — including a restricted one — and generate SQL against it.

---

## 4.4 Nearest-Neighbor Retrieval Cannot Resolve Ambiguity

Enterprise warehouses frequently have:

* multiple models with nearly identical embeddings
* competing revenue definitions
* duplicate customer ID spaces

Nearest-neighbor retrieval picks the closest match.

It has no mechanism to detect that two candidates are in conflict.

It has no mechanism to ask: *"Which revenue definition do you mean?"*

The system silently picks one and generates SQL.

The user may never know the wrong definition was chosen.

---

## 4.5 RAG Retrieves. It Does Not Reason.

RAG is a retrieval pattern.

It does not:

* traverse lineage graphs
* rank join paths
* propagate confidence across pipeline stages
* classify failure types
* validate governance constraints
* separate query planning from generation

This system introduces a **Semantic Query Planning Engine** that does all of these things before the LLM is invoked.

RAG is one input signal within the retrieval stage.

It is not the reasoning engine.

---

# 5. Proposed Solution

## Trust-Aware Enterprise Metadata Reasoning

Core capabilities:

* **Semantic Query Planning Engine** — separates query planning from SQL generation
* **Deterministic metadata reasoning** — constrains LLM search space before generation
* **Failure taxonomy** — classifies failures before producing output
* **Composite retrieval ranking** — engineered scoring across multiple signals
* **Metadata confidence propagation** — trust degrades when evidence is weak
* **Honest refusal behavior** — refuses rather than hallucinates
* **Governance-aware validation** — PII, RBAC, cost, compliance
* **Explainable reasoning** — evidence chains for every decision

The system becomes:

> A trust-aware metadata reasoning platform for enterprise analytics.

---

# 6. Semantic Query Planning Engine

> **This is the heart of the system.**

The Semantic Query Planning Engine is the primary differentiator from all existing text-to-SQL approaches.

---

## The Core Separation

Every existing system merges query planning with SQL generation.

This system separates them completely:

| Stage           | What Happens                                                    | Who Is Responsible           |
| --------------- | --------------------------------------------------------------- | ---------------------------- |
| Query Planning  | Metadata reasoning, entity resolution, join graph, governance   | Deterministic engine         |
| SQL Generation  | Translating a validated plan into SQL syntax                    | LLM (constrained by plan)    |

The LLM never sees raw metadata.

The LLM only receives a validated, constrained execution plan.

---

## The Reasoning Pipeline

Instead of:

```text
User Query → retrieve embeddings → prompt LLM
```

The system does:

```text
User Query
    ↓
1. Business Entity Extraction
   — Identify nouns, metrics, dimensions, filters in the query
   — Map to enterprise glossary terms

    ↓
2. Analytical Intent Inference
   — Classify intent: aggregation, trend, segmentation, comparison, lookup
   — Identify time grain, granularity, scope

    ↓
3. Candidate Metric Identification
   — Retrieve candidate metrics from metadata graph
   — Score against glossary definitions

    ↓
4. Candidate Dimension Identification
   — Identify dimensional filters and groupings
   — Resolve against warehouse dimension models

    ↓
5. Ambiguity Detection
   — Flag multiple metric definitions
   — Flag duplicate dimension paths
   — Flag competing join candidates

    ↓
6. Metadata Graph Traversal
   — Traverse lineage graph to find model relationships
   — Build candidate join graph

    ↓
7. Join Path Ranking
   — Score each candidate join path
   — Select highest-confidence path

    ↓
8. Governance Validation
   — Check PII exposure
   — Check RBAC restrictions
   — Estimate query cost
   — Block unsafe patterns

    ↓
9. Execution Plan Construction
   — Produce structured SQL plan:
     selected_models, join_paths, filters, aggregations, confidence

    ↓
10. SQL Generation (LLM receives structured plan only)
    — LLM translates plan to SQL syntax
    — LLM does NOT perform reasoning at this stage

    ↓
Final Response OR Honest Refusal
```

---

## Why This Is Technically Significant

The LLM is a translator at the end of the pipeline.

All critical decisions are made deterministically before the LLM is invoked:

* which tables are valid
* which joins are safe
* whether ambiguity exists
* whether governance rules are violated
* what the confidence level is

This means:

* hallucinations are prevented at the planning stage
* governance violations are caught before generation
* refusals are precise and classified
* SQL output is constrained and validated

---

## Execution Plan Output Format

```json
{
  "query_intent": "revenue_aggregation_by_segment",
  "entities_extracted": ["revenue", "customer_segment"],
  "candidate_models": ["fct_orders", "dim_customer"],
  "join_path": [
    "fct_orders.customer_id -> dim_customer.customer_id"
  ],
  "join_confidence": 0.91,
  "ambiguity_detected": false,
  "governance_flags": [],
  "execution_plan": {
    "select": ["dim_customer.segment", "SUM(fct_orders.revenue)"],
    "from": "fct_orders",
    "joins": ["LEFT JOIN dim_customer ON fct_orders.customer_id = dim_customer.customer_id"],
    "group_by": ["dim_customer.segment"]
  },
  "overall_confidence": 0.88
}
```

The LLM receives this plan and generates the final SQL from it.

---

# 7. Reasoning Algorithms

> **This section defines HOW each core computation works — thresholds, formulas, fallback behavior.**

---

## 7.1 Join Path Ranking Algorithm

### Formula

```text
Join Path Score =
  0.40 × foreign_key_strength
+ 0.25 × lineage_proximity
+ 0.20 × semantic_similarity
+ 0.15 × historical_usage_frequency
```

---

### Factor Definitions

#### foreign_key_strength (0.40 weight)

Score based on join relationship type:

| Relationship Type       | Score |
| ----------------------- | ----- |
| Explicit foreign key    | 1.00  |
| dbt relationship test   | 0.90  |
| Documented in manifest  | 0.75  |
| Inferred from column name match | 0.45 |
| Inferred from semantic similarity | 0.20 |

Explicit structural evidence is weighted most heavily because it is deterministic and verifiable.

---

#### lineage_proximity (0.25 weight)

Graph hop distance between the two models being joined:

| Graph Distance | Score |
| -------------- | ----- |
| Direct parent/child (1 hop) | 1.00 |
| Two hops                    | 0.70 |
| Three hops                  | 0.40 |
| Four or more hops           | 0.15 |
| No lineage path found       | 0.00 |

No lineage path found sets this factor to 0.00 regardless of semantic similarity.

---

#### semantic_similarity (0.20 weight)

Cosine similarity between the column embeddings of the two join keys.

Used to validate that column semantics are consistent across models.

Example: `customer_id` in `fct_orders` and `id` in `dim_customer` — semantically similar even though names differ.

---

#### historical_usage_frequency (0.15 weight)

Normalised frequency of this join path appearing in previously answered queries.

```text
historical_score = successful_uses / (successful_uses + failed_uses + 1)
```

Cold-start default: 0.50 until at least 10 historical observations.

---

### Decision Thresholds

| Score Range  | Decision                              |
| ------------ | ------------------------------------- |
| 0.80 – 1.00  | Use this join path                    |
| 0.60 – 0.79  | Use with medium-confidence warning    |
| 0.40 – 0.59  | Surface ambiguity, request confirmation |
| 0.00 – 0.39  | Refuse — WEAK_JOIN failure type       |

---

### Ambiguity Threshold

If two or more candidate join paths score within **0.10 of each other** and both are above 0.40:

```text
|score_path_A - score_path_B| < 0.10
AND score_path_A > 0.40
AND score_path_B > 0.40
```

→ Trigger `AMBIGUOUS_JOIN` failure type.

Do not silently choose one path.

Surface both candidates and request clarification.

---

### Fallback Behavior

If no join path exceeds 0.40:

→ Trigger `WEAK_JOIN` failure type.

If no join path exists at all:

→ Trigger `MISSING_ENTITY` failure type.

Never proceed to SQL generation with an unresolved join below threshold.

---

## 7.2 Ambiguity Detection Algorithm

Ambiguity is evaluated across three dimensions:

### Metric Ambiguity

If two or more metric candidates map to the same extracted entity with a glossary match score within 0.15 of each other:

```text
|gloss_score_A - gloss_score_B| < 0.15
```

→ Trigger `SEMANTIC_CONFLICT` failure type.

Return both definitions and their owning domains.

---

### Dimension Ambiguity

If the same dimension name resolves to models in more than one domain:

Example: `customer_id` found in `dim_customer_crm`, `dim_customer_erp`, and `dim_customer_support`.

→ Trigger `AMBIGUOUS_JOIN` failure type.

Return all three candidates with their domain labels.

---

### Temporal Ambiguity

If a date filter resolves to more than one date column in the selected model:

Example: `fct_orders` contains `order_date`, `ship_date`, `payment_date`.

→ Surface clarification request: *"Which date should be used as the filter?"*

Do not silently choose the first date column.

---

## 7.3 Entity Extraction Algorithm

Entity extraction maps raw query text to known metadata concepts.

### Step 1 — Tokenization

Split query into candidate noun phrases and metric phrases.

### Step 2 — Glossary Lookup

Match each candidate phrase against the enterprise business glossary using:

```text
glossary_match_score =
  0.60 × exact_string_match
+ 0.40 × embedding_similarity_to_glossary_entry
```

Threshold for glossary hit: `glossary_match_score > 0.65`

### Step 3 — Metadata Graph Lookup

For each glossary hit, traverse the graph to find candidate models.

### Step 4 — Unresolved Entity Handling

If a candidate phrase does not hit the glossary threshold:

→ Flag as potential `MISSING_ENTITY`.

→ Continue processing remaining entities.

→ If all primary entities are missing: trigger `INSUFFICIENT_SCHEMA`.

---

## 7.4 Confidence Propagation Algorithm

### Formula

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

### Why MIN and Not AVERAGE

Averaging would allow a strong retrieval score to mask a dangerously weak join.

The `MIN` function enforces that the weakest evidence link in the pipeline governs trust.

A plan is only as trustworthy as its least trustworthy step.

### Component Computation

#### retrieval_confidence

Final composite score from the retrieval ranking formula (Section 10).

#### join_path_confidence

Score of the highest-ranked valid join path from the join ranking algorithm (Section 7.1).

#### governance_safety_score

```text
1.00  — no governance flags
0.50  — soft flag (cost warning, non-critical PII adjacent)
0.00  — hard block (PII column, RBAC violation, unsafe scan)
```

#### metadata_completeness_score

```text
metadata_completeness =
  (columns_with_descriptions / total_columns)
  × (models_with_lineage / total_models_in_plan)
```

#### intent_clarity_weight

```text
1.00 — single unambiguous intent classified
0.85 — two possible intents, highest selected
0.60 — intent unclear, best guess applied
```

### Thresholds

| Confidence Range | System Behavior                               |
| ---------------- | --------------------------------------------- |
| 0.85 – 1.00      | Generate SQL — high confidence                |
| 0.65 – 0.84      | Generate SQL with confidence warning          |
| 0.40 – 0.64      | Surface ambiguity — request clarification     |
| 0.00 – 0.39      | Classify failure type — refuse                |

---

## 7.5 Refusal Decision Algorithm

```text
IF governance_safety_score == 0.00:
    → GOVERNANCE_BLOCKED (hard stop, no further processing)

IF any primary entity unresolved AND no fallback:
    → INSUFFICIENT_SCHEMA

IF join_path_confidence < 0.40:
    → WEAK_JOIN

IF ambiguity_detected == True AND plan_confidence < 0.65:
    → AMBIGUOUS_JOIN or SEMANTIC_CONFLICT (based on ambiguity type)

IF plan_confidence < 0.40:
    → LOW_CONFIDENCE

IF plan_confidence >= 0.40:
    → Proceed to SQL generation
```

Governance blocks are evaluated first and are always hard stops regardless of other scores.

---

# 8. Metadata Graph Example

> **This section makes the metadata graph concrete and shows real traversal behavior.**

---

## 8.1 Example Graph

```text
Nodes (Models):

dim_customer
  → customer_id (PK)
  → segment
  → region
  → domain: sales
  → owner: analytics_team
  → tags: [gold, pii_adjacent]

fct_orders
  → order_id (PK)
  → customer_id (FK → dim_customer)
  → revenue_gross
  → revenue_net
  → order_date
  → domain: sales
  → owner: analytics_team
  → tags: [gold, finance]

payment_events
  → event_id (PK)
  → order_id (FK → fct_orders)
  → payment_status
  → payment_date
  → domain: finance
  → owner: finance_team
  → tags: [silver, pci]

support_tickets
  → ticket_id (PK)
  → customer_id (FK → dim_customer)   ← direct FK to customer
  → order_id (FK → fct_orders)        ← AND direct FK to orders
  → escalation_level
  → resolution_date
  → domain: ops
  → owner: cx_team
  → tags: [silver]

Edges (Relationships):

dim_customer  ──[upstream_of]──→  fct_orders
fct_orders    ──[upstream_of]──→  payment_events
dim_customer  ──[upstream_of]──→  support_tickets
fct_orders    ──[upstream_of]──→  support_tickets
```

---

## 8.2 Traversal Example

**Query:** *"Show customers with failed payments after support escalation"*

### Step 1 — Entity Extraction

| Extracted Entity  | Glossary Match | Resolved Model      |
| ----------------- | -------------- | ------------------- |
| customers         | 0.95           | `dim_customer`      |
| failed payments   | 0.88           | `payment_events`    |
| support escalation| 0.91           | `support_tickets`   |

---

### Step 2 — Graph Traversal

Starting from `dim_customer`, find paths to `payment_events` and `support_tickets`.

```text
Path A (to payment_events):
  dim_customer → fct_orders → payment_events
  Hops: 2
  All edges are explicit foreign keys.

Path B (to support_tickets):
  dim_customer → support_tickets
  Hops: 1
  Direct FK relationship.
```

---

### Step 3 — Join Path Scoring

| Path                                        | FK Strength | Lineage | Semantic | History | Score |
| ------------------------------------------- | ----------- | ------- | -------- | ------- | ----- |
| dim_customer → fct_orders → payment_events  | 1.00        | 0.70    | 0.85     | 0.60    | 0.834 |
| dim_customer → support_tickets              | 1.00        | 1.00    | 0.90     | 0.70    | 0.955 |

Both paths are valid and above threshold.

---

### Step 4 — Ambiguity Check

The two paths are not competing — they serve different entities in the query.

`payment_events` resolves via `fct_orders`.
`support_tickets` resolves directly from `dim_customer`.

No ambiguity detected.

---

### Step 5 — Confidence Cascade

```text
retrieval_confidence:         0.91
join_path_confidence:         0.834   ← weakest join in the plan
governance_safety_score:      0.50    ← payment_events tagged [pci]
metadata_completeness_score:  0.88
intent_clarity_weight:        1.00

Plan Confidence = MIN(0.91, 0.834, 0.50, 0.88) × 1.00
               = 0.50
```

Plan confidence falls to **0.50** due to the PCI governance flag on `payment_events`.

→ System surfaces a governance warning before generating SQL:

```json
{
  "status": "GOVERNANCE_WARNING",
  "reason": "payment_events is tagged [pci]. Ensure user has finance_data access role.",
  "confidence": 0.50,
  "recommendation": "Confirm RBAC clearance before proceeding."
}
```

---

## 8.3 Ambiguity in Graph Traversal

If `payment_events` had two FK paths to `fct_orders`:

```text
Path A: payment_events.order_id → fct_orders.order_id   (score: 0.91)
Path B: payment_events.legacy_order_ref → fct_orders.order_id  (score: 0.85)
```

Score delta = 0.91 - 0.85 = 0.06 < 0.10 threshold.

→ Trigger `AMBIGUOUS_JOIN`.

Do not silently choose Path A.

Surface both and request clarification from user or data engineer.

---

# 9. Failure Taxonomy

> **This makes the system measurable, rigorous, and evaluatable.**

Instead of broadly referring to "hallucinations," the system classifies every failure precisely.

---

## Failure Classification Table

| Failure Type         | Trigger Condition                                      | System Response                         |
| -------------------- | ------------------------------------------------------ | --------------------------------------- |
| Missing Entity       | Requested entity absent from metadata graph            | `INSUFFICIENT_SCHEMA` refusal           |
| Ambiguous Join       | Multiple valid join paths with similar confidence      | `AMBIGUOUS_JOIN` refusal with candidates|
| Semantic Conflict    | Multiple definitions for the same metric               | `SEMANTIC_CONFLICT` warning             |
| Governance Violation | PII column, RBAC restriction, or unsafe scan detected  | `GOVERNANCE_BLOCKED` hard stop          |
| Weak Confidence      | Insufficient lineage evidence for any join path        | `LOW_CONFIDENCE` refusal                |
| Unsafe Query         | Unrestricted table scan or unbounded result set        | `UNSAFE_QUERY` blocked                  |

---

## Failure Output Format

Each failure type returns a structured response:

```json
{
  "status": "AMBIGUOUS_JOIN",
  "failure_type": "ambiguous_join",
  "reason": "Multiple customer ID mappings detected across 3 models.",
  "candidates": [
    {"path": "fct_orders.customer_id -> dim_customer_crm.id", "confidence": 0.71},
    {"path": "fct_orders.customer_id -> dim_customer_erp.id", "confidence": 0.69}
  ],
  "recommendation": "Clarify which customer source system applies.",
  "confidence": 0.14
}
```

---

## Evaluation Harness Per Failure Type

| Category              | Description                                         |
| --------------------- | --------------------------------------------------- |
| Answerable            | Fully supported metadata; expect valid SQL          |
| Missing Entity        | Intentionally absent metadata; expect refusal       |
| Ambiguous Join        | Multiple valid paths; expect AMBIGUOUS_JOIN         |
| Semantic Conflict     | Competing metric definitions; expect warning        |
| Governance Violation  | PII or RBAC constraint; expect GOVERNANCE_BLOCKED   |
| Unsafe Query          | Unbounded scan; expect UNSAFE_QUERY block           |

---

## Evaluation Metrics

| Metric              | Description                                |
| ------------------- | ------------------------------------------ |
| SQL Accuracy        | Correct SQL generation on answerable set   |
| Hallucination Rate  | Invalid column/join generation             |
| Refusal Precision   | Correct refusal on unanswerable queries    |
| Refusal Recall      | Refusal triggered when required            |
| Failure Type F1     | Correct failure classification             |
| Retrieval Precision | Metadata retrieval correctness             |
| Join Accuracy       | Correct join path selection                |
| Plan Accuracy       | Execution plan correctness before LLM      |

---

# 10. Retrieval Ranking Logic

> **This makes retrieval engineered and explainable — not a generic vector demo.**

---

## The Problem With Naive Retrieval

Most systems retrieve metadata using only embedding cosine similarity.

This ignores:

* whether the model is lineage-connected to what was already retrieved
* whether the term appears in the enterprise business glossary
* whether the model has been queried historically for similar intent
* whether the model has governance restrictions

---

## Composite Retrieval Scoring Formula

```text
Final Retrieval Score =
  0.35 × Semantic Similarity
+ 0.25 × Lineage Proximity
+ 0.15 × Business Glossary Overlap
+ 0.15 × Historical Query Relevance
+ 0.10 × Governance Compatibility
```

---

## Factor Definitions

### Semantic Similarity (0.35)

Cosine similarity between query embedding and metadata embedding.

Standard vector retrieval — necessary but not sufficient alone.

### Lineage Proximity (0.25)

Graph distance between candidate model and already-retrieved models in the current plan.

A model one hop away in the lineage graph ranks higher than one that is disconnected.

This prevents retrieving semantically similar but structurally unrelated models.

### Business Glossary Overlap (0.15)

Whether the candidate model or column aligns with enterprise glossary term definitions.

A column tagged with the glossary term `"net_revenue"` scores higher than an untagged column with the same embedding distance.

### Historical Query Relevance (0.15)

Whether this model has appeared in previously answered queries with similar intent.

Cold-start: defaults to 0.0 until query history is available.

### Governance Compatibility (0.10)

Whether the model is accessible under the current user's RBAC role and free of governance flags.

A model with PII or role restrictions scores lower even if semantically relevant.

---

## Ranking Output

```json
{
  "candidate": "fct_orders",
  "scores": {
    "semantic_similarity": 0.82,
    "lineage_proximity": 0.90,
    "glossary_overlap": 0.75,
    "historical_relevance": 0.60,
    "governance_compatibility": 1.00
  },
  "final_score": 0.823,
  "rank": 1
}
```

---

# 11. Metadata Confidence Propagation

> **This is the most advanced concept in the system.**

---

## Core Idea

In most systems, confidence is a single number attached to the final SQL output.

In this system, confidence is propagated across the entire pipeline.

Every weak signal degrades the overall plan confidence.

The system is trust-aware at every layer.

---

## Confidence Degradation Sources

| Source                       | Effect on Confidence              |
| ---------------------------- | --------------------------------- |
| Missing column descriptions  | Moderate degradation              |
| Inferred join (not explicit) | Significant degradation           |
| Weak lineage evidence        | Significant degradation           |
| Ambiguous metric definition  | Major degradation                 |
| No historical precedent      | Minor degradation                 |
| Governance flag present      | Major degradation or full block   |

---

## Example: Confidence Cascade

```json
{
  "retrieval_confidence": 0.88,
  "join_path_confidence": 0.52,
  "governance_safety_score": 1.00,
  "metadata_completeness_score": 0.79,
  "intent_clarity_weight": 0.95,

  "plan_confidence": 0.494,
  "decision": "REFUSAL — join evidence insufficient"
}
```

Even though retrieval was strong (0.88), the weak join path (0.52) governed overall trust and triggered refusal.

---

# 12. Real Enterprise Scenarios

> **These scenarios demonstrate system behavior against messy, realistic enterprise conditions.**

---

## Scenario 1 — Conflicting Revenue Definitions

### Context

The Finance team defines:

```text
gross_revenue: total billed amount before deductions
```

The Sales team defines:

```text
net_revenue: billed amount after discounts and returns
```

Both are stored in `fct_orders`.

Both are tagged with the glossary term `"revenue"` across two domain ontologies.

---

### Query

*"Show total revenue by region for Q3"*

---

### System Behavior

**Entity extraction:**

| Entity    | Glossary Matches                                 |
| --------- | ------------------------------------------------ |
| revenue   | `gross_revenue` (finance domain, score: 0.88)    |
|           | `net_revenue` (sales domain, score: 0.85)        |

Score delta = 0.88 - 0.85 = 0.03 — below the 0.15 ambiguity threshold.

→ Trigger `SEMANTIC_CONFLICT`.

---

### System Response

```json
{
  "status": "SEMANTIC_CONFLICT",
  "failure_type": "semantic_conflict",
  "reason": "Multiple revenue definitions match the query with similar confidence.",
  "candidates": [
    {
      "column": "fct_orders.revenue_gross",
      "definition": "Total billed amount before deductions",
      "domain": "finance",
      "confidence": 0.88
    },
    {
      "column": "fct_orders.revenue_net",
      "definition": "Billed amount after discounts and returns",
      "domain": "sales",
      "confidence": 0.85
    }
  ],
  "recommendation": "Specify whether gross or net revenue is required."
}
```

The system refuses to silently choose one definition.

---

## Scenario 2 — Multi-Hop Join Ambiguity Across Source Systems

### Context

The enterprise has three customer ID spaces:

| Source System | Model                 | Key Column        |
| ------------- | --------------------- | ----------------- |
| CRM           | `dim_customer_crm`    | `crm_customer_id` |
| ERP           | `dim_customer_erp`    | `erp_account_id`  |
| Support       | `dim_customer_support`| `support_user_id` |

`fct_orders` links to `dim_customer_crm`.

`payment_events` links to `dim_customer_erp`.

`support_tickets` links to `dim_customer_support`.

There is NO unified customer master in this warehouse.

---

### Query

*"Show customers who made a purchase and then raised a support ticket within 7 days"*

---

### System Behavior

**Entity extraction:**

| Entity           | Resolved Models                                 |
| ---------------- | ----------------------------------------------- |
| customers        | `dim_customer_crm`, `dim_customer_erp`, `dim_customer_support` |
| purchase         | `fct_orders`                                    |
| support ticket   | `support_tickets`                               |

**Graph traversal:**

```text
Path A: fct_orders → dim_customer_crm → ? → support_tickets
  No direct lineage path between crm and support_tickets.
  Requires crossing source system boundaries.
  Foreign key strength: 0.20 (inferred only)
  Join score: 0.31 — below threshold

Path B: fct_orders.order_id → support_tickets.order_id
  Direct FK found in manifest.
  Hops: 1
  Join score: 0.89
```

**Ambiguity result:**

Path A is below threshold.

Path B provides a direct join via `order_id`, bypassing the need for a unified customer key.

→ System selects Path B with a warning:

```json
{
  "status": "PARTIAL_RESOLUTION",
  "warning": "No unified customer ID exists across CRM, ERP, and Support systems.",
  "resolution": "Joined via order_id instead of customer_id.",
  "join_path": "fct_orders.order_id -> support_tickets.order_id",
  "join_confidence": 0.89,
  "recommendation": "Consider building dim_customer_master for cross-system customer joins."
}
```

The system documents exactly why it chose this path and what is missing.

---

## Scenario 3 — Governance Hard Block on PII Column

### Query

*"Show me the SSN and email for all customers who churned last quarter"*

---

### System Behavior

**Entity extraction:**

| Entity     | Resolved Column             | Governance Tag  |
| ---------- | --------------------------- | --------------- |
| SSN        | `dim_customer.ssn`          | PII: sensitive  |
| email      | `dim_customer.email_address`| PII: personal   |
| churned    | `fct_churn_events.status`   | None            |

**Governance validation:**

`dim_customer.ssn` → hard PII flag → `governance_safety_score = 0.00`

`dim_customer.email_address` → soft PII flag → `governance_safety_score = 0.50`

Governance check fires before any join scoring or plan construction.

→ Hard stop on `ssn`.

---

### System Response

```json
{
  "status": "GOVERNANCE_BLOCKED",
  "failure_type": "governance_violation",
  "reason": "Column 'ssn' is classified as PII: sensitive and cannot be included in query output.",
  "blocked_columns": ["dim_customer.ssn"],
  "restricted_columns": ["dim_customer.email_address"],
  "recommendation": "Remove SSN from query. Email access requires finance_data role.",
  "confidence": 0.00
}
```

No SQL is generated.

No LLM invocation occurs.

The governance check is deterministic and upstream of all generation logic.

---

## Scenario 4 — Unsafe Query Pattern

### Query

*"Just give me everything in the transactions table"*

---

### System Behavior

**Pattern detection:**

No filter, no aggregation, no dimension constraint, no date range.

Resolved model: `fact_transactions` — partitioned table, 4.2B rows, PCI-tagged.

**Query cost estimation:**

Full scan: estimated 18TB read — exceeds `max_scan_gb` threshold (500GB).

→ Trigger `UNSAFE_QUERY`.

---

### System Response

```json
{
  "status": "UNSAFE_QUERY",
  "failure_type": "unsafe_query",
  "reason": "Unbounded scan on PCI-partitioned table. Estimated scan: 18TB.",
  "blocked_query": "SELECT * FROM fact_transactions",
  "recommendation": "Add a date partition filter (e.g., transaction_date >= '2025-01-01') to reduce scan scope."
}
```

---

# 13. Architecture Constraints

> **Honest constraints increase deployability credibility.**

A system that acknowledges its own limits is more trustworthy than one that claims unlimited capability.

---

## 13.1 Metadata Quality Dependency

The system's reasoning is only as good as the underlying metadata.

| Metadata Condition                     | Impact                                       |
| -------------------------------------- | -------------------------------------------- |
| Missing column descriptions            | Lower metadata completeness score; lower plan confidence |
| Undocumented lineage                   | Inferred joins only; lower join confidence   |
| No dbt tests on relationships          | FK strength degrades to inferred level       |
| Stale manifest (not refreshed)         | Metadata may not reflect current warehouse   |
| No business glossary defined           | Glossary overlap factor defaults to 0.0      |

**Implication:** The platform performs best in mature analytics engineering environments with well-maintained dbt projects.

---

## 13.2 Lineage Completeness Requirement

Semantic join-path reasoning depends on lineage graph completeness.

If a valid join path exists in the warehouse but is not documented in the manifest:

* The system will not find it via graph traversal
* It may infer it via column name matching (low confidence)
* Or it will trigger `WEAK_JOIN`

This is intentional.

It is safer to refuse than to silently traverse an undocumented join.

---

## 13.3 Cold-Start Limitations

Two components have cold-start behavior:

### Historical Query Relevance

Defaults to 0.50 until 10+ query observations are available.

Early deployments will have weaker retrieval ranking on this dimension until query history accumulates.

### Confidence Calibration

Confidence thresholds are currently defined manually.

With sufficient labeled query outcomes (correct SQL / incorrect SQL / correct refusal), thresholds can be calibrated per warehouse and per domain.

Pre-calibration thresholds are conservative by design.

---

## 13.4 Cannot Infer Missing Business Semantics

The system resolves ambiguity against what exists in the metadata.

It cannot invent semantics that are not present.

If an enterprise uses an undocumented internal business term that does not appear in the glossary or manifest descriptions:

* Entity extraction will fail to resolve it
* System will trigger `INSUFFICIENT_SCHEMA`

This is correct behavior.

The solution is to enrich the glossary, not to lower the refusal threshold.

---

## 13.5 Multi-Source Warehouse Identity Resolution

When an enterprise has no unified entity layer (e.g., no single `dim_customer_master`):

* Cross-system joins are limited to documented foreign key relationships
* Customer-level analysis spanning CRM, ERP, and Support systems may be unsupportable
* System surfaces this explicitly rather than inventing a join

Resolution of fragmented identity spaces requires data engineering work outside this platform.

---

## 13.6 LLM Translation Assumptions

The SQL generation step assumes the LLM can faithfully translate a structured execution plan into syntactically correct SQL.

For standard SQL dialects (BigQuery, Snowflake, Redshift, Databricks), this assumption is well-supported.

For highly specialized or proprietary SQL dialects, translation accuracy may degrade.

SQL output should be validated against warehouse syntax in production deployments.

---

## 13.7 Performance at Scale

The metadata graph traversal and join path ranking run in-process.

For warehouses with:

* 1,000+ models
* 50,000+ columns
* deeply nested lineage

Graph traversal may require performance optimisation (subgraph pre-indexing, caching frequent traversal paths).

This is a known scaling concern for v1 deployment, not a fundamental architectural limitation.

---

# 14. High-Level Architecture

```text
User Query
    ↓
Business Entity Extraction
  (glossary match + embedding similarity)
    ↓
Analytical Intent Inference
  (aggregation / trend / segmentation / lookup)
    ↓
Semantic Metadata Retrieval
  (composite 5-factor ranking)
    ↓
Metadata Graph Traversal
  (lineage-aware, hop-scored)
    ↓
Join Path Ranking
  (FK strength + lineage + semantic + history)
    ↓
Ambiguity Detection
  (metric, dimension, temporal)
    ↓
Governance Validation
  (PII / RBAC / cost / unsafe scan — hard stop if triggered)
    ↓
Confidence Propagation
  (MIN across all pipeline signals)
    ↓
[Decision Gate]
  ├── Confidence < threshold → Classify Failure Type → Honest Refusal
  └── Confidence ≥ threshold → Execution Plan Construction
                                      ↓
                               SQL Generation
                               (LLM receives structured plan only)
                                      ↓
                               Final SQL Response
```

---

# 15. System Expansion Roadmap

---

## PHASE 1 — dbt Manifest Intelligence

### Objective

Replace static CSV metadata ingestion with real enterprise metadata ingestion using dbt `manifest.json`.

---

### Data Sources — dbt manifest.json

Extract:

* model names and descriptions
* columns and column descriptions
* tags, owners, domains
* upstream/downstream lineage
* dbt relationship tests
* semantic relationships

---

### New Module: `ingestion/manifest_ingestor.py`

Responsibilities:

* Parse `manifest.json`
* Normalize metadata schema
* Build initial metadata graph
* Generate vector embeddings per model/column
* Populate ChromaDB and graph store

---

### Metadata Schema

```json
{
  "model": "fct_orders",
  "column": "customer_id",
  "description": "Unique enterprise customer identifier",
  "domain": "sales",
  "upstream_models": ["dim_customer"],
  "tags": ["finance", "gold"],
  "owner": "analytics_team"
}
```

---

## PHASE 2 — Semantic Query Planning Engine

### Objective

Implement the core planning layer that separates query planning from SQL generation.

---

### New Modules

| Module                          | Responsibility                                      |
| ------------------------------- | --------------------------------------------------- |
| `reasoning/query_planner.py`    | Orchestrates full 10-step planning pipeline         |
| `reasoning/entity_extractor.py` | Extracts business entities from natural language    |
| `reasoning/intent_classifier.py`| Classifies analytical intent                        |
| `reasoning/ambiguity_detector.py`| Detects metric, dimension, and temporal ambiguity  |
| `reasoning/confidence_scorer.py`| Implements confidence propagation                   |

---

### Key Principle

The LLM receives only the structured execution plan.

The LLM never sees raw metadata.

---

## PHASE 3 — Honest Refusal Framework and Failure Taxonomy

### Objective

Prevent hallucinated SQL generation through classified refusal behavior.

---

### New Module: `generation/refusal_engine.py`

Classifies failure type using the taxonomy in Section 9.

Returns structured refusal response with candidates, recommendations, and confidence.

---

## PHASE 4 — Composite Retrieval Ranking

### Objective

Replace naive embedding retrieval with engineered composite scoring (Section 10 formula).

---

### New Modules

| Module                           | Responsibility                                |
| -------------------------------- | --------------------------------------------- |
| `retrieval/embedding_ranker.py`  | Composite retrieval scoring                   |
| `retrieval/lineage_scorer.py`    | Lineage proximity via graph traversal         |
| `retrieval/glossary_matcher.py`  | Enterprise glossary term matching             |

---

## PHASE 5 — Governance-Aware Intelligence

### Objective

Introduce enterprise safety and governance controls evaluated before SQL generation.

---

### New Modules

| Module                                 | Responsibility                         |
| -------------------------------------- | -------------------------------------- |
| `governance/pii_detector.py`           | SSN, email, phone, DOB, financial PII  |
| `governance/rbac_validator.py`         | Role-based model access restriction    |
| `governance/query_cost_estimator.py`   | Scan size, partition, unbounded queries|

---

## PHASE 6 — Explainability Engine

### Objective

Expose system reasoning at every pipeline stage.

---

### Output Example

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

## PHASE 7 — Optional Agentic Architecture

### Objective

Modular reasoning agents as an optional execution layer.

Intentionally lower priority.

The core value of this system is in **reasoning and trust**, not agent orchestration.

---

# 16. Technical Stack

| Component          | Technology                    |
| ------------------ | ----------------------------- |
| Vector Database    | ChromaDB                      |
| Embeddings         | OpenAI / BGE / Instructor     |
| Metadata Graph     | NetworkX / Neo4j              |
| Query Planner      | Custom deterministic engine   |
| SQL Generation     | Claude / OpenAI (plan-only)   |
| Metadata Source    | dbt manifest.json             |
| Evaluation         | pytest + custom harness       |
| API Layer          | FastAPI                       |
| Frontend           | Streamlit                     |
| Observability      | LangSmith / OpenTelemetry     |

---

# 17. Proposed Repository Structure

```text
enterprise-metadata-intelligence/
│
├── ingestion/
│   ├── manifest_ingestor.py
│   ├── lineage_parser.py
│   └── metadata_normalizer.py
│
├── retrieval/
│   ├── semantic_retriever.py
│   ├── embedding_ranker.py
│   ├── lineage_scorer.py
│   ├── glossary_matcher.py
│   └── domain_router.py
│
├── reasoning/
│   ├── query_planner.py          ← heart of the system
│   ├── entity_extractor.py
│   ├── intent_classifier.py
│   ├── join_path_engine.py
│   ├── ambiguity_detector.py
│   └── confidence_scorer.py
│
├── governance/
│   ├── pii_detector.py
│   ├── rbac_validator.py
│   └── query_cost_estimator.py
│
├── generation/
│   ├── sql_planner.py
│   ├── sql_generator.py
│   └── refusal_engine.py
│
├── evaluation/
│   ├── benchmark_runner.py
│   ├── hallucination_tests.py
│   ├── refusal_tests.py
│   ├── failure_taxonomy_tests.py
│   └── retrieval_metrics.py
│
├── frontend/
│   └── streamlit_app.py
│
└── docs/
    ├── architecture.md
    ├── query_planning.md
    ├── reasoning_algorithms.md
    ├── metadata_graph.md
    ├── failure_taxonomy.md
    ├── retrieval_ranking.md
    ├── confidence_propagation.md
    ├── enterprise_scenarios.md
    ├── architecture_constraints.md
    ├── evaluation.md
    └── governance.md
```

---

# 18. Research Positioning

This project intentionally positions itself against generic RAG SQL systems.

---

## Sharp Differentiation

| Dimension              | Generic RAG SQL Systems                 | This System                                |
| ---------------------- | --------------------------------------- | ------------------------------------------ |
| Retrieval              | Embedding similarity                    | Composite 5-factor ranked retrieval        |
| Query Planning         | Merged with generation                  | Explicit deterministic planning stage      |
| SQL Generation         | LLM decides everything                  | LLM translates constrained execution plan  |
| Joins                  | Hallucinated                            | Confidence-ranked via FK strength + lineage|
| Failure Behavior       | Produce invalid SQL                     | Classify failure type and refuse           |
| Ambiguity              | Silent LLM resolution                   | Detected, classified, and surfaced         |
| Governance             | Ignored                                 | Validated at every pipeline stage          |
| Confidence             | Not measured                            | Propagated from retrieval through plan     |
| Reasoning              | Opaque                                  | Explainable with evidence at each step     |
| Enterprise Lineage     | Flat schema metadata                    | dbt manifest with upstream/downstream      |
| RAG                    | Retrieval is the reasoning              | Retrieval is one input signal within planning |

---

## Core Research Claim

> Deterministic metadata reasoning before LLM generation — including explicit join path scoring, failure taxonomy, and confidence propagation — reduces hallucination and enables principled refusal. This is a fundamentally different architecture from embedding-then-generate systems.

---

# 19. Medium Publication Strategy

## Strong Publication Titles

* "Why Enterprise Text-to-SQL Systems Fail: A Taxonomy"
* "Separating Query Planning from SQL Generation: Why It Matters"
* "Why RAG Alone Is Insufficient for Enterprise Metadata Reasoning"
* "Building a Trust-Aware Metadata Reasoning Layer for Enterprise Analytics"
* "Beyond RAG: Deterministic Metadata Planning Before LLM Generation"
* "Honest Refusal in Enterprise AI: A Failure Taxonomy for Metadata Systems"
* "Composite Retrieval Ranking: Moving Beyond Embedding Similarity"

---

# 20. LinkedIn Positioning

Recommended positioning:

> **Trust-Aware Enterprise Metadata Reasoning Platform**

Avoid positioning as:

* SQL chatbot
* AI copilot
* text-to-SQL assistant
* agentic SQL system

Those categories are overcrowded and undifferentiated.

The value of this system is:

* deterministic reasoning before generation
* trust-aware confidence propagation
* classified failure taxonomy
* governance-aware analytics
* principled refusal behavior

NOT autonomous agents.

---

# 21. Future Extensions

* Graph neural networks for lineage-aware embedding
* Query execution feedback loops for historical relevance scoring
* Self-healing metadata graphs from query failure patterns
* Autonomous metadata quality scoring
* Confidence calibration from labeled query outcome history
* Cross-warehouse semantic federation
* Multi-cloud warehouse reasoning
* Enterprise semantic glossary auto-alignment
* Adaptive confidence thresholds per domain and warehouse tier

---

# 22. Final Vision

The long-term vision is:

> A trust-aware semantic reasoning layer between enterprise users and analytical data systems.

The system should:

* extract business intent from natural language
* reason deterministically about metadata before invoking the LLM
* classify failures precisely rather than hallucinating
* propagate confidence across the entire pipeline
* validate governance at every stage
* explain every decision with evidence
* refuse unsafe outputs with precision
* operate honestly within its architectural constraints

This transforms the project from:

> "LLM-generated SQL"

into:

> **"Trust-aware enterprise metadata intelligence and deterministic semantic reasoning."**
