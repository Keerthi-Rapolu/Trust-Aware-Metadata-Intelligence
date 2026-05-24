"""
tests/test_manifest_ingestor.py

Unit tests for ingestion/manifest_ingestor.py  (Phase 1, Task 1.2)
"""

import json
import pytest
from ingestion.manifest_ingestor import ManifestIngestor


@pytest.fixture
def ingestor():
    return ManifestIngestor()


# ------------------------------------------------------------------ #
# load_manifest                                                        #
# ------------------------------------------------------------------ #

def test_load_manifest_returns_dict(sample_manifest, tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(sample_manifest), encoding="utf-8")
    result = ManifestIngestor().load_manifest(str(path))
    assert isinstance(result, dict)
    assert "nodes" in result


def test_load_manifest_raises_on_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        ManifestIngestor().load_manifest(str(tmp_path / "no_such_file.json"))


# ------------------------------------------------------------------ #
# extract_models                                                       #
# ------------------------------------------------------------------ #

def test_extract_models_count(ingestor, sample_manifest):
    """4 model nodes → 4 model records."""
    records = ingestor.extract_models(sample_manifest)
    assert len(records) == 4


def test_extract_models_record_type(ingestor, sample_manifest):
    records = ingestor.extract_models(sample_manifest)
    for rec in records:
        assert rec["record_type"] == "model"


def test_extract_models_required_fields(ingestor, sample_manifest):
    required = {
        "record_type", "model", "column", "description", "domain",
        "upstream_models", "tags", "owner", "data_type", "pii",
        "description_missing", "metadata_completeness_score", "unique_id",
    }
    for rec in ingestor.extract_models(sample_manifest):
        missing = required - rec.keys()
        assert not missing, f"{rec['model']} missing fields: {missing}"


def test_extract_models_upstream_fct_orders(ingestor, sample_manifest):
    """fct_orders depends on dim_customer only."""
    records = ingestor.extract_models(sample_manifest)
    fct = next(r for r in records if r["model"] == "fct_orders")
    assert fct["upstream_models"] == ["dim_customer"]


def test_extract_models_upstream_support_tickets(ingestor, sample_manifest):
    """support_tickets depends on dim_customer AND fct_orders."""
    records = ingestor.extract_models(sample_manifest)
    st = next(r for r in records if r["model"] == "support_tickets")
    assert set(st["upstream_models"]) == {"dim_customer", "fct_orders"}


def test_extract_models_dim_customer_no_upstream(ingestor, sample_manifest):
    records = ingestor.extract_models(sample_manifest)
    dc = next(r for r in records if r["model"] == "dim_customer")
    assert dc["upstream_models"] == []


def test_extract_models_completeness_full(ingestor, sample_manifest):
    """dim_customer: all 5 columns have descriptions → completeness == 1.0."""
    records = ingestor.extract_models(sample_manifest)
    dc = next(r for r in records if r["model"] == "dim_customer")
    assert dc["metadata_completeness_score"] == 1.0


def test_extract_models_completeness_partial(ingestor, sample_manifest):
    """payment_events: payment_date has no description → completeness < 1.0."""
    records = ingestor.extract_models(sample_manifest)
    pe = next(r for r in records if r["model"] == "payment_events")
    assert 0.0 < pe["metadata_completeness_score"] < 1.0


def test_extract_models_support_tickets_completeness_partial(ingestor, sample_manifest):
    """support_tickets: resolution_date has no description → < 1.0."""
    records = ingestor.extract_models(sample_manifest)
    st = next(r for r in records if r["model"] == "support_tickets")
    assert st["metadata_completeness_score"] < 1.0


def test_extract_models_description_not_missing(ingestor, sample_manifest):
    """dim_customer has a description → description_missing == False."""
    records = ingestor.extract_models(sample_manifest)
    dc = next(r for r in records if r["model"] == "dim_customer")
    assert dc["description_missing"] is False


def test_extract_models_tags_present(ingestor, sample_manifest):
    """dim_customer tagged gold + dimensions."""
    records = ingestor.extract_models(sample_manifest)
    dc = next(r for r in records if r["model"] == "dim_customer")
    assert "gold" in dc["tags"]


def test_extract_models_domain_and_owner(ingestor, sample_manifest):
    records = ingestor.extract_models(sample_manifest)
    dc = next(r for r in records if r["model"] == "dim_customer")
    assert dc["domain"] == "sales"
    assert dc["owner"] == "analytics_team"


# ------------------------------------------------------------------ #
# extract_columns                                                      #
# ------------------------------------------------------------------ #

def test_extract_columns_total_count(ingestor, sample_manifest):
    """dim_customer(5) + fct_orders(5) + payment_events(4) + support_tickets(5) = 19."""
    records = ingestor.extract_columns(sample_manifest)
    assert len(records) == 19


def test_extract_columns_record_type(ingestor, sample_manifest):
    for rec in ingestor.extract_columns(sample_manifest):
        assert rec["record_type"] == "column"


def test_extract_columns_pii_email(ingestor, sample_manifest):
    """email_address in dim_customer must be pii=True, pii_type='email'."""
    records = ingestor.extract_columns(sample_manifest)
    col = next(
        r for r in records
        if r["model"] == "dim_customer" and r["column"] == "email_address"
    )
    assert col["pii"] is True
    assert col["pii_type"] == "email"


def test_extract_columns_pii_phone(ingestor, sample_manifest):
    records = ingestor.extract_columns(sample_manifest)
    col = next(
        r for r in records
        if r["model"] == "dim_customer" and r["column"] == "phone_number"
    )
    assert col["pii"] is True
    assert col["pii_type"] == "phone"


def test_extract_columns_non_pii(ingestor, sample_manifest):
    """customer_id in dim_customer is NOT PII."""
    records = ingestor.extract_columns(sample_manifest)
    col = next(
        r for r in records
        if r["model"] == "dim_customer" and r["column"] == "customer_id"
    )
    assert col["pii"] is False
    assert col["pii_type"] is None


def test_extract_columns_description_missing_payment_date(ingestor, sample_manifest):
    """payment_date in payment_events has empty description."""
    records = ingestor.extract_columns(sample_manifest)
    col = next(
        r for r in records
        if r["model"] == "payment_events" and r["column"] == "payment_date"
    )
    assert col["description_missing"] is True


def test_extract_columns_description_missing_resolution_date(ingestor, sample_manifest):
    records = ingestor.extract_columns(sample_manifest)
    col = next(
        r for r in records
        if r["model"] == "support_tickets" and r["column"] == "resolution_date"
    )
    assert col["description_missing"] is True


def test_extract_columns_description_present(ingestor, sample_manifest):
    """order_id in fct_orders has a description → description_missing == False."""
    records = ingestor.extract_columns(sample_manifest)
    col = next(
        r for r in records
        if r["model"] == "fct_orders" and r["column"] == "order_id"
    )
    assert col["description_missing"] is False


def test_extract_columns_unique_id_format(ingestor, sample_manifest):
    """unique_id for column records should end in .<column_name>."""
    for rec in ingestor.extract_columns(sample_manifest):
        assert rec["unique_id"].endswith(f".{rec['column']}")


# ------------------------------------------------------------------ #
# extract_all                                                          #
# ------------------------------------------------------------------ #

def test_extract_all_combines(ingestor, sample_manifest):
    records = ingestor.extract_all(sample_manifest)
    model_recs = [r for r in records if r["record_type"] == "model"]
    col_recs = [r for r in records if r["record_type"] == "column"]
    assert len(model_recs) == 4
    assert len(col_recs) == 19
