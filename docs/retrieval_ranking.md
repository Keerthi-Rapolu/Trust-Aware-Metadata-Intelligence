# Retrieval Ranking

## Overview

Phase 4 replaces raw vector-similarity retrieval with a composite,
lineage-aware ranking layer implemented in `retrieval/semantic_retriever.py`
and `retrieval/embedding_ranker.py`.

The goal is to rank candidate models using multiple signals instead of
letting semantic similarity dominate the decision by itself.

## Composite Formula

```text
Final Retrieval Score =
  0.35 × Semantic Similarity
+ 0.25 × Lineage Proximity
+ 0.15 × Business Glossary Overlap
+ 0.15 × Historical Query Relevance
+ 0.10 × Governance Compatibility
```

All factors are bounded to `[0, 1]`.

## Factors

### Semantic Similarity

- Uses cosine similarity when `embed_fn` is provided.
- Falls back to `difflib.SequenceMatcher` otherwise.
- Model semantics are derived from glossary descriptions for that model.

### Lineage Proximity

- Implemented in `retrieval/lineage_scorer.py`.
- Uses graph hop distance relative to already-selected models.
- Scores:
  - `1 hop -> 1.00`
  - `2 hops -> 0.70`
  - `3 hops -> 0.40`
  - `4+ hops -> 0.15`
  - `no anchor models -> 0.50`
  - `no path -> 0.00`

### Business Glossary Overlap

- Implemented in `retrieval/glossary_matcher.py`.
- Prefers direct lexical evidence over description overlap:
  - exact term or synonym match -> `1.00`
  - sub-token containment -> `0.75`
  - description overlap fallback -> `0.00–0.50`

### Historical Query Relevance

- Caller-supplied query history per model.
- Cold-start default: `0.50`.

### Governance Compatibility

- Derived from graph node tags.
- Scores:
  - clean model -> `1.00`
  - soft-flagged model -> `0.50`
  - hard-blocked model (`pii`, `pci`, `restricted`, `confidential`) -> `0.00`

Hard-blocked models are also ranked behind governance-compatible models even
when their lexical similarity is stronger. This keeps unsafe models from
becoming the surfaced top candidate.

## Retriever Interface

`SemanticRetriever` exposes two paths:

- `retrieve(...)`
  - full composite ranking
- `naive_retrieve(...)`
  - semantic-only baseline for comparison and regression testing

## Planner Integration

`reasoning/query_planner.py` now uses `SemanticRetriever` at Step 7.

- `step7_retrieval` stores the ranked candidates and factor breakdown.
- `step7_retrieval_score` stores the plan-level retrieval confidence.
- Plan-level retrieval confidence is the mean composite score across the
  selected candidate models.

This score then feeds directly into `ConfidenceScorer`.
