"""
tests/test_metadata_normalizer.py

Unit tests for ingestion/metadata_normalizer.py  (Phase 1, Task 1.4)
"""

import pytest
from ingestion.manifest_ingestor import ManifestIngestor
from ingestion.metadata_normalizer import MetadataNormalizer


@pytest.fixture
def normalizer():
    return MetadataNormalizer()


@pytest.fixture
def raw_records(sample_manifest):
    return ManifestIngestor().extract_all(sample_manifest)


@pytest.fixture
def raw_col_records(sample_manifest):
    return ManifestIngestor().extract_columns(sample_manifest)


# ------------------------------------------------------------------ #
# normalize                                                            #
# ------------------------------------------------------------------ #

def test_normalize_returns_list(normalizer, raw_records):
    assert isinstance(normalizer.normalize(raw_records), list)


def test_normalize_preserves_count(normalizer, raw_records):
    """No duplicates in sample_manifest → record count unchanged."""
    result = normalizer.normalize(raw_records)
    assert len(result) == len(raw_records)


def test_normalize_domain_lowercase(normalizer):
    records = [_make_rec("x", domain="Sales")]
    assert normalizer.normalize(records)[0]["domain"] == "sales"


def test_normalize_domain_stripped(normalizer):
    records = [_make_rec("x", domain="  finance  ")]
    assert normalizer.normalize(records)[0]["domain"] == "finance"


def test_normalize_tags_lowercase(normalizer):
    records = [_make_rec("x", tags=["Gold", "FINANCE"])]
    assert normalizer.normalize(records)[0]["tags"] == ["gold", "finance"]


def test_normalize_tags_empty_removed(normalizer):
    records = [_make_rec("x", tags=["gold", "", "  "])]
    result = normalizer.normalize(records)[0]["tags"]
    assert "" not in result
    assert "  " not in result


def test_normalize_owner_lowercase(normalizer):
    records = [_make_rec("x", owner="Analytics_Team")]
    assert normalizer.normalize(records)[0]["owner"] == "analytics_team"


def test_normalize_description_missing_true_for_empty(normalizer):
    records = [_make_rec("x", description="")]
    assert normalizer.normalize(records)[0]["description_missing"] is True


def test_normalize_description_missing_false_for_filled(normalizer):
    records = [_make_rec("x", description="Some description")]
    assert normalizer.normalize(records)[0]["description_missing"] is False


def test_normalize_deduplicates_by_uid(normalizer):
    records = [
        _make_rec("dup", description="first"),
        _make_rec("dup", description="second"),
    ]
    result = normalizer.normalize(records)
    assert len(result) == 1
    assert result[0]["description"] == "first"  # first wins


def test_normalize_no_uid_not_deduped(normalizer):
    """Records without a unique_id are not deduplicated."""
    records = [
        _make_rec("", description="a"),
        _make_rec("", description="b"),
    ]
    result = normalizer.normalize(records)
    assert len(result) == 2


# ------------------------------------------------------------------ #
# compute_completeness                                                 #
# ------------------------------------------------------------------ #

def test_compute_completeness_keys(normalizer, raw_col_records):
    result = normalizer.compute_completeness(
        normalizer.normalize(raw_col_records)
    )
    expected = {"dim_customer", "fct_orders", "payment_events", "support_tickets"}
    assert expected.issubset(result.keys())


def test_compute_completeness_dim_customer_full(normalizer, raw_col_records):
    """All 5 dim_customer columns have descriptions → 1.0."""
    result = normalizer.compute_completeness(
        normalizer.normalize(raw_col_records)
    )
    assert result["dim_customer"] == 1.0


def test_compute_completeness_fct_orders_full(normalizer, raw_col_records):
    """All 5 fct_orders columns have descriptions → 1.0."""
    result = normalizer.compute_completeness(
        normalizer.normalize(raw_col_records)
    )
    assert result["fct_orders"] == 1.0


def test_compute_completeness_payment_events_partial(normalizer, raw_col_records):
    """payment_events: payment_date empty → 3/4 = 0.75."""
    result = normalizer.compute_completeness(
        normalizer.normalize(raw_col_records)
    )
    assert result["payment_events"] == pytest.approx(0.75, abs=0.01)


def test_compute_completeness_support_tickets_partial(normalizer, raw_col_records):
    """support_tickets: resolution_date empty → 4/5 = 0.80."""
    result = normalizer.compute_completeness(
        normalizer.normalize(raw_col_records)
    )
    assert result["support_tickets"] == pytest.approx(0.80, abs=0.01)


def test_compute_completeness_ignores_model_records(normalizer, raw_records):
    """Model-level records must not be counted in column completeness."""
    result = normalizer.compute_completeness(raw_records)
    # Still correct because only record_type=='column' are counted
    assert result["dim_customer"] == 1.0


# ------------------------------------------------------------------ #
# Helper                                                               #
# ------------------------------------------------------------------ #

def _make_rec(uid: str, *, domain="sales", tags=None, owner="team",
              description="desc") -> dict:
    return {
        "unique_id": uid,
        "domain": domain,
        "tags": tags or [],
        "owner": owner,
        "description": description,
        "record_type": "column",
        "model": "test_model",
        "column": "test_col",
    }
