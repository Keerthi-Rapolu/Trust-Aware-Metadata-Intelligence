"""
ingestion/metadata_normalizer.py

Normalises metadata records produced by ManifestIngestor.

Design reference: EXPANSION_DESIGN.md §15 — PHASE 1, Task 1.4

Responsibilities
----------------
1. Lowercase + strip domain, tags, owner
2. Ensure description_missing flag is set correctly
3. Deduplicate by unique_id
4. Compute metadata_completeness_score per model from column records
"""

from typing import Dict, List


class MetadataNormalizer:

    def normalize(self, records: List[dict]) -> List[dict]:
        """
        Normalise a list of metadata records and return a new deduplicated list.

        Steps applied per record:
        - domain  → lowercase, stripped
        - tags    → each tag lowercase, stripped; empty tags removed
        - owner   → lowercase, stripped
        - description_missing recomputed from description field
        - duplicates (same unique_id) dropped; first occurrence wins
        """
        seen: set = set()
        normalized: List[dict] = []

        for raw in records:
            rec = dict(raw)  # shallow copy — do not mutate caller's data

            rec["domain"] = self._clean(rec.get("domain", ""))
            rec["owner"] = self._clean(rec.get("owner", ""))
            rec["tags"] = [
                self._clean(t) for t in rec.get("tags", []) if str(t).strip()
            ]
            rec["description_missing"] = not bool(
                str(rec.get("description", "")).strip()
            )

            uid = rec.get("unique_id", "")
            if uid:
                if uid in seen:
                    continue
                seen.add(uid)

            normalized.append(rec)

        return normalized

    def compute_completeness(self, records: List[dict]) -> Dict[str, float]:
        """
        Compute metadata_completeness_score per model from column records.

        Returns {model_name: score} where score = described_cols / total_cols.
        Only column records (record_type == 'column') are counted.
        """
        model_stats: Dict[str, Dict[str, int]] = {}

        for rec in records:
            if rec.get("record_type") != "column":
                continue
            model = rec["model"]
            if model not in model_stats:
                model_stats[model] = {"total": 0, "described": 0}
            model_stats[model]["total"] += 1
            if not rec.get("description_missing", True):
                model_stats[model]["described"] += 1

        return {
            model: (
                round(v["described"] / v["total"], 4) if v["total"] > 0 else 0.0
            )
            for model, v in model_stats.items()
        }

    # ------------------------------------------------------------------ #

    @staticmethod
    def _clean(value) -> str:
        return str(value).strip().lower()
