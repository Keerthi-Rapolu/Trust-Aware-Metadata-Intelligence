# Governance

## Overview

Phase 5 adds deterministic governance checks that run in
`reasoning/query_planner.py` before SQL generation.

The planner evaluates three modules:

- `governance/pii_detector.py`
- `governance/rbac_validator.py`
- `governance/query_cost_estimator.py`

If any module returns a hard block, the planner emits
`GOVERNANCE_BLOCKED` and the SQL generator refuses the request.

## Metadata Inputs

Governance runs on metadata already stored in the graph.

Model-level attributes:

- `domain`
- `tags`
- `estimated_scan_gb`
- `partition_column`
- `partition_grain`

Column-level attributes:

- `description`
- `data_type`
- `tags`
- `pii`
- `pii_type`

## PII Detection

`PiiDetector` classifies sensitive access into hard and soft cases.

Hard block indicators:

- model tags: `pci`, `restricted`, `confidential`
- column names or `pii_type` values such as `ssn`, `social_security`,
  `tax_id`, `credit_card`, `account_number`, and `iban`

Soft warning indicators:

- `email`
- `phone`
- `dob`
- `personal_data`

Returned fields include:

- `blocked`
- `severity`
- `pii_columns_detected`
- `blocked_models`
- `governance_safety_score`
- `reason`
- `recommendation`

## RBAC Configuration

`RbacValidator` reads `data/rbac_config.json`.

Current config shape:

```json
{
  "roles": {
    "analyst": {
      "allowed_domains": ["sales", "ops", "finance"],
      "blocked_tags": ["pii", "pci", "restricted", "confidential"]
    }
  }
}
```

Each candidate model is checked against:

- model `domain`
- model `tags`
- caller `user_role`

Returned fields include:

- `blocked`
- `violations`
- `blocked_models`
- `governance_safety_score`

## Query Cost Estimation

`QueryCostEstimator` uses `estimated_scan_gb` and partition metadata from
the graph.

Default threshold:

- `max_scan_gb = 500.0`

Unsafe patterns include:

- unbounded phrases such as `all data`, `everything`, `full history`
- missing time filter on partitioned models
- broad scan intent on very large tables

Returned fields include:

- `blocked`
- `estimated_scan_gb`
- `unsafe_patterns_detected`
- `governance_safety_score`
- `recommendation`

## Planner Integration

`QueryPlanner` runs governance as an early gate, before ambiguity handling
and before confidence scoring.

Planner output stores:

- `step6_governance`
- module-level results under `module_results`
- per-module scores under `module_scores`

This preserves the failure-taxonomy rule that governance has priority over
later semantic reasoning when a query is unsafe.
