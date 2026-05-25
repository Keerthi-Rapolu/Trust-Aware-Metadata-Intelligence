# Query Planning Pipeline

The `QueryPlanner` orchestrates a deterministic 10-step pipeline before any LLM
interaction. The LLM receives only a **structured execution plan** — it never sees
raw manifest data, graph adjacency lists, or glossary definitions.

---

## Pipeline Overview

```
Query
  │
  ▼ Step 1  IntentClassifier.classify()
  │         → intent, time_grain, intent_clarity_weight
  ▼ Step 2  EntityExtractor.extract()
  │         → entities_extracted, candidate_models, unresolved_tokens
  ▼ Step 3  Validate candidate_models against live graph
  │         → REFUSE (INSUFFICIENT_SCHEMA) if no models found
  ▼ Step 4  JoinPathEngine.find_join_paths()
  │         → join_paths, overall_confidence, all_models_resolved
  ▼ Step 5  AmbiguityDetector.detect_all()
  │         → CLARIFY if is_ambiguous
  ▼ Step 6  Governance check (Phase 2: PII/PCI model-level)
  │         → REFUSE (GOVERNANCE_BLOCKED) if blocked
  ▼ Step 7  Retrieval score (Phase 2: constant 0.80; full ranking in Phase 4)
  ▼ Step 8  ConfidenceScorer.score()
  │         → final_confidence, confidence_level
  ▼ Step 9  Build structured execution_plan dict
  ▼ Step 10 Gate: confident / warn → proceed | ambiguous / refuse → stop
  │
  ▼
Execution Plan → SqlGenerator.generate()
```

---

## Execution Plan Format

```json
{
  "query":            "show orders by region",
  "intent":           "segmentation",
  "time_grain":       null,
  "candidate_models": ["fct_orders", "dim_customer"],
  "model_columns":    {
    "fct_orders":   ["order_id", "order_date"],
    "dim_customer": ["region"]
  },
  "join_path": [
    {
      "from_model":  "dim_customer",
      "to_model":    "fct_orders",
      "from_column": "customer_id",
      "to_column":   "customer_id",
      "edge_type":   "explicit_fk",
      "score":       0.885
    }
  ],
  "entities": [
    {"term": "order",  "columns": ["order_id", "order_date"], "models": ["fct_orders"]},
    {"term": "region", "columns": ["region"],                 "models": ["dim_customer"]}
  ],
  "confidence":       0.80,
  "confidence_level": "confident",
  "governance_clear": true,
  "warnings":         []
}
```

---

## Failure Modes

| failure_type          | When triggered                                          | should_proceed |
|-----------------------|--------------------------------------------------------|----------------|
| `INSUFFICIENT_SCHEMA` | No entities resolve to known graph models              | `False`        |
| `AMBIGUOUS_JOIN`      | Required models are not connected in the lineage graph | `False`        |
| `SEMANTIC_CONFLICT`   | Entity maps to 2+ columns with equal confidence        | `False`        |
| `GOVERNANCE_BLOCKED`  | Query touches a PII/PCI-tagged model                   | `False`        |
| `LOW_CONFIDENCE`      | Final confidence < 0.40                                | `False`        |

---

## Confidence Gate

| Level      | Threshold         | Action                                 |
|------------|-------------------|----------------------------------------|
| confident  | ≥ 0.80            | Proceed to SQL generation              |
| warn       | 0.60 – 0.79       | Proceed with caveat in warnings[]      |
| ambiguous  | 0.40 – 0.59       | Request clarification, no SQL          |
| refuse     | < 0.40 or blocked | Return failure_type + failure_reason   |

---

## Class Reference

| Class           | Module                            | Responsibility                      |
|-----------------|-----------------------------------|-------------------------------------|
| `QueryPlanner`  | `reasoning/query_planner.py`      | Orchestrates all 10 steps           |
| `IntentClassifier` | `reasoning/intent_classifier.py` | Step 1 — keyword intent detection  |
| `EntityExtractor`  | `reasoning/entity_extractor.py`  | Step 2 — glossary entity mapping   |
| `JoinPathEngine`   | `reasoning/join_path_engine.py`  | Step 4 — join path scoring         |
| `AmbiguityDetector`| `reasoning/ambiguity_detector.py`| Step 5 — three-type ambiguity check|
| `ConfidenceScorer` | `reasoning/confidence_scorer.py` | Step 8 — MIN-based confidence      |
| `SqlGenerator`     | `generation/sql_generator.py`    | Step 10 — plan → SQL               |
