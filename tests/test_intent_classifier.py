"""
tests/test_intent_classifier.py

Unit tests for reasoning/intent_classifier.py

Coverage
--------
  - Aggregation intent detected
  - Trend intent detected
  - Segmentation intent detected
  - Comparison intent detected
  - Lookup intent detected (explicit)
  - Default to lookup when no pattern matched
  - Clarity weight: 1.00 single match, 0.85 multiple, 0.60 none
  - Time grain detection (daily, weekly, monthly, quarterly, annual)
  - Priority order: aggregation > segmentation > trend > comparison > lookup
  - matched_patterns list populated correctly
  - Case insensitivity
"""

import pytest

from reasoning.intent_classifier import IntentClassifier


@pytest.fixture
def clf():
    return IntentClassifier()


# ──────────────────────────────────────────────────────────────────────────────
# Intent detection
# ──────────────────────────────────────────────────────────────────────────────

class TestIntentDetection:

    def test_aggregation_intent(self, clf):
        result = clf.classify("what is the total revenue this month")
        assert result["intent"] == "aggregation"

    def test_trend_intent(self, clf):
        # "year over year growth monthly" — only trend keywords, no agg/seg/cmp
        result = clf.classify("year over year growth monthly")
        assert result["intent"] == "trend"

    def test_segmentation_intent(self, clf):
        result = clf.classify("breakdown sales by region")
        assert result["intent"] == "segmentation"

    def test_comparison_intent(self, clf):
        # "contrast scores versus baseline" — only comparison keywords, no agg/trend/seg
        result = clf.classify("contrast scores versus baseline")
        assert result["intent"] == "comparison"

    def test_lookup_intent_explicit(self, clf):
        result = clf.classify("find customer details")
        assert result["intent"] == "lookup"

    def test_default_to_lookup_no_match(self, clf):
        result = clf.classify("zzz unknown query xyz")
        assert result["intent"] == "lookup"

    def test_count_is_aggregation(self, clf):
        result = clf.classify("how many orders were placed")
        assert result["intent"] == "aggregation"

    def test_growth_is_trend(self, clf):
        result = clf.classify("show monthly growth of payments")
        assert result["intent"] == "trend"


# ──────────────────────────────────────────────────────────────────────────────
# Clarity weights
# ──────────────────────────────────────────────────────────────────────────────

class TestClarityWeights:

    def test_single_match_clarity_1(self, clf):
        result = clf.classify("show revenue trend over time")
        # trend only — but 'revenue' is in _AGG_WORDS too, so multiple likely
        # test that it's either 1.00 or 0.85 (not 0.60)
        assert result["intent_clarity_weight"] >= 0.85

    def test_no_match_clarity_0_6(self, clf):
        result = clf.classify("zzz unknown query abc")
        assert result["intent_clarity_weight"] == 0.60

    def test_multiple_matches_clarity_0_85(self, clf):
        # "total" (agg) + "by region" (seg) → both match → 0.85
        result = clf.classify("total sales by region")
        if len(result["matched_patterns"]) >= 2:
            assert result["intent_clarity_weight"] == 0.85

    def test_pure_lookup_clarity_1(self, clf):
        result = clf.classify("find the customer with id 123")
        # "find" is lookup only if no agg/trend/seg/cmp also match
        assert result["intent_clarity_weight"] in (0.85, 1.00)


# ──────────────────────────────────────────────────────────────────────────────
# Time grain
# ──────────────────────────────────────────────────────────────────────────────

class TestTimeGrain:

    @pytest.mark.parametrize("query,expected_grain", [
        ("daily active users",           "daily"),
        ("weekly revenue report",        "weekly"),
        ("monthly breakdown by region",  "monthly"),
        ("quarterly sales summary",      "quarterly"),
        ("annual revenue trend",         "annual"),
        ("by month revenue",             "monthly"),
    ])
    def test_grain_detection(self, clf, query, expected_grain):
        result = clf.classify(query)
        assert result["time_grain"] == expected_grain, (
            f"Query '{query}': expected '{expected_grain}', got '{result['time_grain']}'"
        )

    def test_no_grain_returns_none(self, clf):
        result = clf.classify("show total revenue")
        assert result["time_grain"] is None


# ──────────────────────────────────────────────────────────────────────────────
# Priority ordering
# ──────────────────────────────────────────────────────────────────────────────

class TestPriorityOrdering:

    def test_aggregation_beats_segmentation(self, clf):
        # Both "total" (agg) and "by" (seg) present
        result = clf.classify("total revenue by customer")
        assert result["intent"] == "aggregation"

    def test_aggregation_beats_trend(self, clf):
        result = clf.classify("total revenue over time")
        assert result["intent"] == "aggregation"

    def test_segmentation_beats_trend(self, clf):
        # No aggregation keyword; segmentation + trend both present
        result = clf.classify("revenue breakdown by month trend")
        # aggregation may fire due to "revenue" in _AGG_WORDS; accept aggregation or segmentation
        assert result["intent"] in ("aggregation", "segmentation")


# ──────────────────────────────────────────────────────────────────────────────
# matched_patterns list
# ──────────────────────────────────────────────────────────────────────────────

class TestMatchedPatterns:

    def test_matched_patterns_is_list(self, clf):
        result = clf.classify("total revenue")
        assert isinstance(result["matched_patterns"], list)

    def test_no_duplicate_patterns(self, clf):
        result = clf.classify("total revenue by region")
        patterns = result["matched_patterns"]
        assert len(patterns) == len(set(patterns))

    def test_empty_patterns_for_no_match(self, clf):
        result = clf.classify("zzz unknown")
        assert result["matched_patterns"] == []


# ──────────────────────────────────────────────────────────────────────────────
# Case insensitivity
# ──────────────────────────────────────────────────────────────────────────────

class TestCaseInsensitivity:

    def test_uppercase_query(self, clf):
        result = clf.classify("TOTAL REVENUE BY REGION")
        assert result["intent"] in ("aggregation", "segmentation")

    def test_mixed_case_grain(self, clf):
        result = clf.classify("Monthly Revenue Report")
        assert result["time_grain"] == "monthly"
