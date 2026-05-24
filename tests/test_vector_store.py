"""
tests/test_vector_store.py

Integration tests — Phase 1, Task 1.5

Ingest sample manifest into a temporary ChromaDB instance using the
mock_embed_fn (no Ollama required).  Verifies that:

  - all 23 records (4 model + 19 column) are stored
  - metadata fields (domain, pii, description_missing) are queryable
  - PII-tagged columns are retrievable by metadata filter
"""

import pytest
import chromadb
from chromadb.config import Settings

from ingestion.manifest_ingestor import ManifestIngestor
from ingestion.metadata_normalizer import MetadataNormalizer


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _record_to_text(rec: dict) -> str:
    """Convert a normalised metadata record to embeddable text."""
    parts = [
        f"Model: {rec.get('model', '')}",
        f"Column: {rec.get('column') or ''}",
        f"Description: {rec.get('description', '')}",
        f"Domain: {rec.get('domain', '')}",
        f"Tags: {', '.join(rec.get('tags', []))}",
    ]
    return "\n".join(p for p in parts if p.split(": ", 1)[-1].strip())


def _build_chroma_meta(rec: dict) -> dict:
    """Flatten record to ChromaDB-compatible metadata (string values only)."""
    return {
        "model":               rec.get("model", ""),
        "column":              str(rec.get("column") or ""),
        "domain":              rec.get("domain", ""),
        "record_type":         rec.get("record_type", ""),
        "pii":                 str(rec.get("pii", False)),
        "description_missing": str(rec.get("description_missing", False)),
        "owner":               rec.get("owner", ""),
    }


def _populate_collection(collection, records, mock_embed_fn):
    """Embed and add all records to collection."""
    for rec in records:
        uid = rec.get("unique_id", "")
        if not uid:
            continue
        text = _record_to_text(rec)
        collection.add(
            ids=[uid],
            documents=[text],
            embeddings=[mock_embed_fn(text)],
            metadatas=[_build_chroma_meta(rec)],
        )


# ------------------------------------------------------------------ #
# Fixtures                                                             #
# ------------------------------------------------------------------ #

@pytest.fixture(scope="module")
def normalised_records(sample_manifest):
    ingestor = ManifestIngestor()
    normalizer = MetadataNormalizer()
    return normalizer.normalize(ingestor.extract_all(sample_manifest))


@pytest.fixture(scope="module")
def chroma_collection(normalised_records, mock_embed_fn, tmp_path_factory):
    tmp = tmp_path_factory.mktemp("chroma")
    client = chromadb.PersistentClient(
        path=str(tmp),
        settings=Settings(anonymized_telemetry=False),
    )
    col = client.get_or_create_collection("manifest_test")
    _populate_collection(col, normalised_records, mock_embed_fn)
    return col


# ------------------------------------------------------------------ #
# Tests                                                                #
# ------------------------------------------------------------------ #

def test_total_record_count(chroma_collection):
    """4 model-level + 19 column-level = 23 records stored."""
    assert chroma_collection.count() == 23


def test_model_records_stored(chroma_collection):
    results = chroma_collection.get(where={"record_type": "model"})
    assert len(results["ids"]) == 4


def test_column_records_stored(chroma_collection):
    results = chroma_collection.get(where={"record_type": "column"})
    assert len(results["ids"]) == 19


def test_pii_columns_stored(chroma_collection):
    """email_address and phone_number must be queryable as pii=True."""
    results = chroma_collection.get(where={"pii": "True"})
    col_names = {m["column"] for m in results["metadatas"]}
    assert "email_address" in col_names
    assert "phone_number" in col_names


def test_pii_count(chroma_collection):
    """Exactly 2 PII columns in sample manifest."""
    results = chroma_collection.get(where={"pii": "True"})
    assert len(results["ids"]) == 2


def test_dim_customer_model_stored(chroma_collection):
    results = chroma_collection.get(
        where={"$and": [{"model": "dim_customer"}, {"record_type": "model"}]}
    )
    assert len(results["ids"]) == 1


def test_description_missing_columns_stored(chroma_collection):
    """2 columns with empty descriptions (payment_date, resolution_date)."""
    results = chroma_collection.get(where={"description_missing": "True"})
    col_names = {m["column"] for m in results["metadatas"] if m["column"]}
    assert "payment_date" in col_names
    assert "resolution_date" in col_names


def test_domain_field_stored(chroma_collection):
    """finance domain records should be retrievable."""
    results = chroma_collection.get(where={"domain": "finance"})
    assert len(results["ids"]) > 0


def test_metadata_embedding_dimensions(chroma_collection, mock_embed_fn):
    """Embeddings stored are 384-dimensional."""
    results = chroma_collection.get(
        limit=1,
        include=["embeddings"],
    )
    assert len(results["embeddings"][0]) == 384
