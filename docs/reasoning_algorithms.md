# Reasoning Algorithms

All algorithms are deterministic — no LLM or network calls required.

---

## 1. Glossary Match Score  (EntityExtractor)

Maps a query token or n-gram to a glossary entry.

```
glossary_match_score = 0.60 × literal_match + 0.40 × semantic_score
```

### literal_match grades

| Score | Condition |
|-------|-----------|
| 1.00  | Normalised token == normalised glossary key |
| 0.90  | Token matches a synonym exactly |
| 0.75  | Key is substring of token, or token is substring of key |
| 0.65  | A synonym is substring of token, or vice versa |
| 0.00  | No match |

### semantic_score

- **embed_fn provided** → cosine similarity between token and glossary description
- **No embed_fn** → best difflib `SequenceMatcher.ratio()` across synonyms + description

**Hit threshold:** `score > 0.65`

### Normalisation

Simple rule-based plural stripping:

```
"customers" → "customer"    (strip trailing "s" when len > 3)
"payments"  → "payment"
"categories"→ "category"    (replace "ies" → "y")
"branches"  → "branch"      (strip "es" when consonant before)
```

---

## 2. Join Path Score  (JoinPathEngine)

Scores each directed edge in the spanning tree connecting candidate models.

```
edge_score = 0.40 × fk_strength
           + 0.25 × lineage_proximity
           + 0.20 × column_similarity
           + 0.15 × historical_frequency
```

### FK strength lookup

| Edge type          | fk_strength |
|--------------------|-------------|
| `explicit_fk`      | 0.90        |
| `lineage_dependency` | 0.45      |
| unknown / None     | 0.20        |

### lineage_proximity (hop score)

| Hops | Score |
|------|-------|
| 1    | 1.00  |
| 2    | 0.70  |
| 3    | 0.40  |
| ≥4   | 0.15  |
| No path | 0.00 |

### column_similarity

| Condition                        | Score |
|----------------------------------|-------|
| Exact column name match          | 1.00  |
| Shared underscore tokens         | 0.80  |
| difflib ratio (fallback)         | 0–1   |
| Either column unknown            | 0.50  |

### historical_frequency

Cold-start default: **0.50** (updated in Phase 4 with query history).

### Decision thresholds

| overall_confidence | Decision        |
|--------------------|-----------------|
| ≥ 0.80             | proceed         |
| 0.60 – 0.79        | warn            |
| 0.40 – 0.59        | surface ambiguity |
| < 0.40             | refuse (WEAK_JOIN) |

**Ambiguity threshold:** `|score_A − score_B| < 0.10` AND both > 0.40

**Example** — `dim_customer → fct_orders` (explicit_fk, 1 hop, `customer_id` match):
```
0.40 × 0.90   = 0.360
0.25 × 1.00   = 0.250
0.20 × 1.00   = 0.200
0.15 × 0.50   = 0.075
─────────────────────
total          = 0.885
```

---

## 3. Ambiguity Detection  (AmbiguityDetector)

Three independent checks, evaluated in priority order.

### SEMANTIC_CONFLICT

Fired when an entity has ≥ 2 candidate columns from the same glossary entry.
Score delta = 0.0 < threshold (0.15) → conflict.

*Example:* "revenue" → `[revenue_gross, revenue_net]`

### AMBIGUOUS_JOIN

Fired when the same entity's candidate models span ≥ 2 distinct domains.

*Example:* "customer" resolving to models in both `sales` and `finance` domains.

### TEMPORAL_AMBIGUITY

Fired when:
- A candidate model has ≥ 2 date/timestamp columns **AND**
- The query contains none of the date filter words (today, last, since, before, month, week, year, quarter, …)

*Note:* Phase 1 graph stores no column lists, so this only fires when column
metadata is explicitly injected into graph node attributes.

---

## 4. Confidence Propagation  (ConfidenceScorer)

```
final_confidence = MIN(
    retrieval_score,
    join_path_confidence,
    governance_score,
    completeness_score
) × intent_clarity_weight
```

The MIN ensures the **weakest link** in the pipeline governs the output confidence.

### intent_clarity_weight

| Matched intents | weight |
|-----------------|--------|
| 1 (unambiguous) | 1.00   |
| 2+ (multiple)   | 0.85   |
| 0 (fallback)    | 0.60   |

### Governance hard-stop

`governance_score = 0.0` → immediate "refuse" regardless of other components.

### Component defaults (Phase 2)

| Component           | Phase 2 value              | Phase where full logic lands |
|---------------------|----------------------------|------------------------------|
| retrieval_score     | 0.80 (constant)            | Phase 4                      |
| join_path_confidence| Computed by JoinPathEngine | Phase 2 ✅                   |
| governance_score    | 1.0 (no block) / 0.0 (PII) | Phase 5                      |
| completeness_score  | avg graph node completeness| Phase 2 ✅                   |
| intent_clarity      | from IntentClassifier      | Phase 2 ✅                   |

---

## 5. Intent Classification  (IntentClassifier)

Keyword-based, fully deterministic.

### Intent priority order

`aggregation > segmentation > trend > comparison > lookup`

### Time grain detection

Regex patterns over the query string:

| Pattern                            | Grain     |
|------------------------------------|-----------|
| `daily \| per day \| each day`     | daily     |
| `weekly \| per week \| each week`  | weekly    |
| `monthly \| per month \| each month`| monthly  |
| `quarterly \| per quarter \| q[1-4]`| quarterly|
| `annual \| annually \| yearly`     | annual    |
