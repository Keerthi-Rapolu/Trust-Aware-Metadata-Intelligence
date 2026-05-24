"""
ingestion/manifest_ingestor.py

Parses a dbt manifest.json and produces normalised metadata records.

Design reference: EXPANSION_DESIGN.md §15 — PHASE 1, Task 1.2

Normalised record schema
------------------------
{
    "record_type":                "model" | "column",
    "model":                      str,
    "column":                     str | None,
    "description":                str,
    "domain":                     str,
    "upstream_models":            list[str],
    "tags":                       list[str],
    "owner":                      str,
    "data_type":                  str | None,
    "pii":                        bool,
    "pii_type":                   str | None,
    "description_missing":        bool,
    "metadata_completeness_score": float | None,   # set at model level only
    "estimated_scan_gb":          float | None,
    "partition_column":           str | None,
    "partition_grain":            str | None,
    "unique_id":                  str,
}
"""

import json
from pathlib import Path
from typing import Callable, List, Optional

MANIFEST_MODEL_PREFIX = "model."


class ManifestIngestor:
    """
    Parses a dbt manifest.json and produces normalised metadata records.
    Embedding is intentionally decoupled — pass an embed_fn if you need
    vectors; leave it None for pure metadata extraction (and tests).
    """

    def __init__(self, embed_fn: Optional[Callable[[str], List[float]]] = None):
        """
        Parameters
        ----------
        embed_fn : callable(text) -> list[float], optional
            Embedding function.  If None the ingestor still extracts
            metadata correctly; ChromaDB ingestion is the caller's job.
        """
        self.embed_fn = embed_fn

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def load_manifest(self, path: str) -> dict:
        """Load and return the raw manifest.json as a dict."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"manifest.json not found at: {p}")
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)

    def extract_models(self, manifest: dict) -> List[dict]:
        """
        Return one model-level record per dbt model node.
        record_type == 'model'
        """
        records: List[dict] = []
        nodes = manifest.get("nodes", {})
        parent_map = manifest.get("parent_map", {})

        for uid, node in nodes.items():
            if node.get("resource_type") != "model":
                continue

            model_name = node["name"]
            columns = node.get("columns", {})
            total_cols = len(columns)
            described_cols = sum(
                1 for c in columns.values()
                if str(c.get("description", "")).strip()
            )
            completeness = (
                round(described_cols / total_cols, 4) if total_cols > 0 else 0.0
            )

            upstream_models = [
                u.split(".")[-1]
                for u in parent_map.get(uid, [])
                if u.startswith(MANIFEST_MODEL_PREFIX)
            ]

            records.append({
                "record_type": "model",
                "model": model_name,
                "column": None,
                "description": node.get("description", "").strip(),
                "domain": node.get("meta", {}).get("domain", ""),
                "upstream_models": upstream_models,
                "tags": list(node.get("tags", [])),
                "owner": node.get("meta", {}).get("owner", ""),
                "data_type": None,
                "pii": False,
                "pii_type": None,
                "description_missing": not bool(node.get("description", "").strip()),
                "metadata_completeness_score": completeness,
                "estimated_scan_gb": node.get("meta", {}).get("estimated_scan_gb"),
                "partition_column": node.get("meta", {}).get("partition_column"),
                "partition_grain": node.get("meta", {}).get("partition_grain"),
                "unique_id": uid,
            })

        return records

    def extract_columns(self, manifest: dict) -> List[dict]:
        """
        Return one column-level record per column across all dbt model nodes.
        record_type == 'column'
        """
        records: List[dict] = []
        nodes = manifest.get("nodes", {})
        parent_map = manifest.get("parent_map", {})

        for uid, node in nodes.items():
            if node.get("resource_type") != "model":
                continue

            model_name = node["name"]
            upstream_models = [
                u.split(".")[-1]
                for u in parent_map.get(uid, [])
                if u.startswith(MANIFEST_MODEL_PREFIX)
            ]
            model_tags = list(node.get("tags", []))
            model_domain = node.get("meta", {}).get("domain", "")
            model_owner = node.get("meta", {}).get("owner", "")

            for col_name, col in node.get("columns", {}).items():
                col_tags = list(col.get("tags", []))
                col_meta = col.get("meta", {}) or {}
                pii = bool(col_meta.get("pii", False)) or "pii" in col_tags
                pii_type = col_meta.get("pii_type") or None

                # Merge model + column tags, deduplicated
                merged_tags = list(dict.fromkeys(model_tags + col_tags))

                records.append({
                    "record_type": "column",
                    "model": model_name,
                    "column": col_name,
                    "description": col.get("description", "").strip(),
                    "domain": model_domain,
                    "upstream_models": upstream_models,
                    "tags": merged_tags,
                    "owner": model_owner,
                    "data_type": col.get("data_type", ""),
                    "pii": pii,
                    "pii_type": pii_type,
                    "description_missing": not bool(
                        str(col.get("description", "")).strip()
                    ),
                    "metadata_completeness_score": None,
                    "estimated_scan_gb": None,
                    "partition_column": None,
                    "partition_grain": None,
                    "unique_id": f"{uid}.{col_name}",
                })

        return records

    def extract_all(self, manifest: dict) -> List[dict]:
        """Return combined model-level + column-level records."""
        return self.extract_models(manifest) + self.extract_columns(manifest)
