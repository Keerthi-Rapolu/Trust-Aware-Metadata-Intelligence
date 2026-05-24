# Metadata Graph

## Overview

The metadata graph is a directed graph of dbt models and their lineage relationships.
It is the foundation for join-path inference, lineage proximity scoring, and ambiguity detection.

Design reference: [EXPANSION_DESIGN.md §8 — Metadata Graph Example](../EXPANSION_DESIGN.md#8-metadata-graph-example)

---

## Graph Schema

### Node Type: Model

Each node represents one dbt model.

| Attribute     | Type          | Source                          |
| ------------- | ------------- | ------------------------------- |
| `domain`      | str           | `meta.domain` in manifest       |
| `tags`        | list[str]     | `tags` in manifest node         |
| `owner`       | str           | `meta.owner` in manifest        |
| `completeness`| float (0–1)   | Computed: described cols / total cols |

---

### Edge Types

| Type                 | Source                              | FK Strength Score |
| -------------------- | ----------------------------------- | ----------------- |
| `explicit_fk`        | dbt `relationships` test node       | 0.90              |
| `lineage_dependency` | `depends_on.nodes` without FK test  | 0.45              |

Edges are directed: `upstream → downstream`.

---

## Sample Graph (Development Fixture)

```text
dim_customer
  ├──► fct_orders         (explicit_fk: customer_id → customer_id)
  └──► support_tickets    (explicit_fk: customer_id → customer_id)

fct_orders
  ├──► payment_events     (explicit_fk: order_id → order_id)
  └──► support_tickets    (explicit_fk: order_id → order_id)
```

Source: `data/sample_manifest.json`

---

## Hop → Proximity Score Mapping

Used by `lineage_proximity_score()` in `ingestion/graph_store.py`.

Design reference: [EXPANSION_DESIGN.md §7.1 — lineage_proximity factor](../EXPANSION_DESIGN.md#71-join-path-ranking-algorithm)

| Graph Distance      | Score |
| ------------------- | ----- |
| 1 hop (direct)      | 1.00  |
| 2 hops              | 0.70  |
| 3 hops              | 0.40  |
| 4+ hops             | 0.15  |
| No path found       | 0.00  |

---

## Usage

```python
from ingestion.lineage_parser import LineageParser
from ingestion.manifest_ingestor import ManifestIngestor
from ingestion.graph_store import MetadataGraph

manifest = ManifestIngestor().load_manifest("data/sample_manifest.json")
edges = LineageParser().extract_edges(manifest)
model_recs = ManifestIngestor().extract_models(manifest)

g = MetadataGraph()
g.build_from_edges(edges)
g.add_model_nodes(model_recs)

# Hop distance
path, hops = g.get_shortest_path("dim_customer", "payment_events")
# → (['dim_customer', 'fct_orders', 'payment_events'], 2)

# Proximity score
score = g.lineage_proximity_score("dim_customer", "payment_events")
# → 0.70

# Neighbors within 2 hops
neighbors = g.get_neighbors("dim_customer", depth=2)
# → ['fct_orders', 'support_tickets', 'payment_events']

# Persist
g.save("chroma_store/graph.json")
```

---

## Persistence Format

Graphs are serialised to JSON using NetworkX node-link format.
Default path: `chroma_store/graph.json`
