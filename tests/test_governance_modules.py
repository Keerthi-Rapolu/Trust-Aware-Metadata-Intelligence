"""
tests/test_governance_modules.py

Unit tests for Phase 5 governance modules.
"""

import pytest

from governance.pii_detector import PiiDetector
from governance.query_cost_estimator import QueryCostEstimator
from governance.rbac_validator import RbacValidator
from ingestion.graph_store import MetadataGraph


@pytest.fixture(scope="module")
def governance_graph():
    graph = MetadataGraph()

    graph.graph.add_node(
        "dim_customer",
        domain="sales",
        tags=["gold", "dimensions"],
        owner="analytics_team",
        completeness=1.0,
        estimated_scan_gb=8,
        partition_column=None,
        partition_grain=None,
        column_info={
            "customer_id": {
                "description": "Customer identifier",
                "data_type": "integer",
                "tags": [],
                "pii": False,
                "pii_type": None,
                "description_missing": False,
            },
            "email_address": {
                "description": "Customer email",
                "data_type": "varchar",
                "tags": ["pii", "personal_data"],
                "pii": True,
                "pii_type": "email",
                "description_missing": False,
            },
            "phone_number": {
                "description": "Customer phone",
                "data_type": "varchar",
                "tags": ["pii", "personal_data"],
                "pii": True,
                "pii_type": "phone",
                "description_missing": False,
            },
        },
    )

    graph.graph.add_node(
        "fct_orders",
        domain="sales",
        tags=["gold", "facts"],
        owner="analytics_team",
        completeness=1.0,
        estimated_scan_gb=120,
        partition_column="order_date",
        partition_grain="daily",
        column_info={},
    )

    graph.graph.add_node(
        "support_tickets",
        domain="ops",
        tags=["silver"],
        owner="cx_team",
        completeness=0.8,
        estimated_scan_gb=25,
        partition_column="resolution_date",
        partition_grain="daily",
        column_info={},
    )

    graph.graph.add_node(
        "payment_events",
        domain="finance",
        tags=["silver", "pci"],
        owner="finance_team",
        completeness=0.75,
        estimated_scan_gb=18000,
        partition_column="payment_date",
        partition_grain="daily",
        column_info={
            "payment_status": {
                "description": "Payment result",
                "data_type": "varchar",
                "tags": [],
                "pii": False,
                "pii_type": None,
                "description_missing": False,
            }
        },
    )

    return graph


class TestPiiDetector:

    def test_pci_model_is_hard_block(self, governance_graph):
        result = PiiDetector().detect(
            "show payment status",
            ["payment_events"],
            governance_graph,
        )
        assert result["blocked"] is True
        assert result["severity"] == "hard"
        assert result["governance_safety_score"] == 0.0

    def test_email_column_is_soft_warning(self, governance_graph):
        result = PiiDetector().detect(
            "show customer email addresses",
            ["dim_customer"],
            governance_graph,
        )
        assert result["blocked"] is False
        assert result["severity"] == "soft"
        assert result["governance_safety_score"] == 0.5
        assert "dim_customer.email_address" in result["restricted_columns"]

    def test_clean_query_is_allowed(self, governance_graph):
        result = PiiDetector().detect(
            "list customer ids",
            ["dim_customer"],
            governance_graph,
        )
        assert result["blocked"] is False
        assert result["governance_safety_score"] == 1.0


class TestRbacValidator:

    def test_analyst_can_access_sales_model(self, governance_graph):
        result = RbacValidator().validate(
            ["fct_orders"],
            governance_graph,
            user_role="analyst",
        )
        assert result["blocked"] is False
        assert result["governance_safety_score"] == 1.0

    def test_support_user_blocked_from_finance_model(self, governance_graph):
        result = RbacValidator().validate(
            ["payment_events"],
            governance_graph,
            user_role="support_user",
        )
        assert result["blocked"] is True
        assert "payment_events" in result["blocked_models"]
        assert result["governance_safety_score"] == 0.0

    def test_partial_block_surfaces_blocked_model(self, governance_graph):
        result = RbacValidator().validate(
            ["support_tickets", "payment_events"],
            governance_graph,
            user_role="support_user",
        )
        assert result["blocked"] is True
        assert result["blocked_models"] == ["payment_events"]


class TestQueryCostEstimator:

    def test_large_partitioned_scan_is_blocked_without_time_filter(self, governance_graph):
        result = QueryCostEstimator(max_scan_gb=500.0).estimate(
            "show all payments",
            ["payment_events"],
            governance_graph,
        )
        assert result["blocked"] is True
        assert result["estimated_scan_gb"] == 18000.0
        assert any(
            pattern.startswith("missing_partition_filter:")
            for pattern in result["unsafe_patterns_detected"]
        )

    def test_time_bounded_query_is_not_blocked(self, governance_graph):
        result = QueryCostEstimator(max_scan_gb=500.0).estimate(
            "show payments for 2025 by status",
            ["payment_events"],
            governance_graph,
        )
        assert result["blocked"] is False

    def test_small_model_scan_is_allowed(self, governance_graph):
        result = QueryCostEstimator(max_scan_gb=500.0).estimate(
            "list all customers",
            ["dim_customer"],
            governance_graph,
        )
        assert result["blocked"] is False
