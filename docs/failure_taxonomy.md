# Failure Taxonomy

**Design reference:** `EXPANSION_DESIGN.md §9 — Failure Taxonomy`

Every query that cannot be safely answered receives a **named failure type**, a structured response, and a human-readable recommendation.  No SQL is generated until all failures are resolved.

---

## Priority Order

| Priority | Failure Type          | Trigger Condition                                         | Hard Stop |
|----------|-----------------------|----------------------------------------------------------|-----------|
| 1        | `GOVERNANCE_BLOCKED`  | Query touches PII/PCI/restricted model (model-level tag) | ✅ Yes    |
| 2        | `UNSAFE_QUERY`        | DML/DDL keyword or destructive bulk-operation pattern    | ✅ Yes    |
| 3        | `INSUFFICIENT_SCHEMA` | No recognisable entities → no graph models found         | ✅ Yes    |
| 4        | `WEAK_JOIN`           | Required models not connected in the lineage graph       | ✅ Yes    |
| 5        | `SEMANTIC_CONFLICT`   | Entity maps to ≥2 candidate columns, score delta < 0.15  | ✅ Yes    |
| 6        | `AMBIGUOUS_JOIN`      | Two competing join paths both score > 0.40, delta < 0.10 | ✅ Yes    |
| 7        | `TEMPORAL_AMBIGUITY`  | ≥2 date columns in model, no date filter in query        | ✅ Yes    |
| 8        | `LOW_CONFIDENCE`      | Final confidence score < 0.40                            | ✅ Yes    |

Lower priority number = **checked and returned first**.  GOVERNANCE_BLOCKED always wins.

---

## Structured Response Format

```json
{
  "status":              "FAILURE",
  "failure_type":        "SEMANTIC_CONFLICT",
  "reason":              "Multiple 'revenue' definitions found: revenue_gross, revenue_net. Specify which definition is required.",
  "candidates":          [
    {"column": "revenue_gross", "entity": "revenue", "score": 1.0},
    {"column": "revenue_net",   "entity": "revenue", "score": 1.0}
  ],
  "recommendation":      "Specify which definition is required.",
  "confidence":          0.0,
  "confidence_level":    "refuse",
  "query":               "total revenue",
  "should_generate_sql": false,
  "priority":            5
}
```

---

## Failure Type Details

### 1. GOVERNANCE_BLOCKED
**When:** A candidate model has a `pii` or `pci` tag in the metadata graph.

**Example:** Query mentions `payment` → resolves to `payment_events` (tag: `pci`) → hard block.

**Response:**
- `reason`: names the blocked model(s)/column(s)
- `recommendation`: directs user to data governance team
- `candidates`: empty (no ambiguity to surface)

**Note:** Checked at Step 3.5 of the planning pipeline — BEFORE ambiguity detection — so it always wins over SEMANTIC_CONFLICT or AMBIGUOUS_JOIN even when both conditions apply.

---

### 2. UNSAFE_QUERY
**When:** The query text contains DML/DDL operations or destructive patterns.

**Detected patterns (DML/DDL):**
- `DELETE FROM …` / `DELETE ALL`
- `DROP TABLE …` / `DROP DATABASE …`
- `TRUNCATE [TABLE] …`
- `INSERT INTO …`
- `UPDATE … SET …`
- `CREATE TABLE …` / `CREATE DATABASE …`
- `ALTER TABLE …`
- `GRANT … TO …` / `REVOKE … FROM …`

**Detected patterns (bulk/destructive):**
- `dump all data … without any filter`
- `export all records from entire database`
- `full table dump`

**Detection:** Independent of planner — checked from query text alone, before any metadata lookup.

---

### 3. INSUFFICIENT_SCHEMA
**When:** Entity extraction produces zero candidate models (all query tokens either are stop words or have no glossary match above the 0.65 threshold).

**Example:** `"show me xyz_metric_zz99"` → no glossary hit → no candidate models.

**Response:**
- `reason`: "No recognised models found for query entities"
- `recommendation`: suggests checking glossary coverage and graph completeness

---

### 4. WEAK_JOIN
**When:** Multiple candidate models are required but no path exists in the lineage graph connecting them.

**Example:** Two models from completely separate ingestion pipelines with no `depends_on` links.

**Response:**
- `reason`: "No join path found between candidate models"
- `candidates`: the disconnected model pair
- `recommendation`: check lineage documentation

---

### 5. SEMANTIC_CONFLICT
**When:** A single glossary entity maps to ≥2 candidate columns, and the score delta between them is < 0.15 (equal confidence → ambiguous).

**Example:** `revenue` → `[revenue_gross, revenue_net]` — both Finance and Sales definitions present.

**Response:**
- `reason`: lists all conflicting column names
- `candidates`: list of `{column, entity, score}` dicts
- `recommendation`: ask user which definition to use

---

### 6. AMBIGUOUS_JOIN
**When:** The same entity's candidate models span ≥2 domains (competing source systems) or two competing join paths both score > 0.40 and within 0.10 of each other.

**Response:**
- `reason`: identifies the competing domains or paths
- `candidates`: list of competing `{model, domain}` dicts

---

### 7. TEMPORAL_AMBIGUITY
**When:** A candidate model has ≥2 date/timestamp columns (matching `date|_dt|_ts|timestamp|_at|time` suffix) AND the query contains no date filter vocabulary (`today`, `last`, `since`, `before`, `month`, `week`, `year`, `quarter`, `day`, etc.).

**Response:**
- `reason`: names the model and lists its date columns
- `recommendation`: ask user which date column to filter on

**Note:** Only fires when column metadata is injected into graph node attributes.  Phase 1 graph stores no column lists, so this is dormant by default until metadata enrichment (Phase 5).

---

### 8. LOW_CONFIDENCE
**When:** `final_confidence = MIN(retrieval, join_path, governance, completeness) × intent_clarity < 0.40`

**Response:**
- `reason`: the recommendation from ConfidenceScorer
- `weakest_factor`: identifies which component caused the low score

---

## Evaluation Harness

Fixture files live in `evaluation/fixtures/`:

| File                       | Category             | Expected failure_type   |
|----------------------------|----------------------|-------------------------|
| `answerable.json`          | clean queries        | `null` (SUCCESS)        |
| `missing_entity.json`      | unknown entities     | `INSUFFICIENT_SCHEMA`   |
| `semantic_conflict.json`   | metric ambiguity     | `SEMANTIC_CONFLICT`     |
| `governance_violation.json`| PCI/PII data access  | `GOVERNANCE_BLOCKED`    |
| `unsafe_query.json`        | DML/DDL operations   | `UNSAFE_QUERY`          |
| `ambiguous_join.json`      | join path conflicts  | varies (see notes)      |

Run evaluation:
```bash
python -m pytest evaluation/ -v
```

See `evaluation/evaluator.py` for the `RefusalEvaluator` class and metric calculation.

---

## Implementation Reference

| Component             | Module                           |
|-----------------------|----------------------------------|
| `RefusalEngine`       | `generation/refusal_engine.py`   |
| Priority constants    | `_PRIORITY` dict in refusal_engine |
| Unsafe patterns       | `_DML_PATTERN`, `_DUMP_PATTERN`  |
| Governance check      | `QueryPlanner._governance_check()` (step 3.5) |
| Evaluation harness    | `evaluation/evaluator.py`        |
| Fixture tests         | `evaluation/refusal_tests.py`    |
| Taxonomy tests        | `evaluation/failure_taxonomy_tests.py` |
