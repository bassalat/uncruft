"""Tests for analyzer module."""

import pytest
from datetime import datetime

from uncruft.analyzer import (
    analyze_disk,
    explain_category,
    estimate_cleanup_savings,
    filter_by_minimum_size,
    format_size,
    get_category_by_size,
    get_recommendations,
    get_safe_cleanup_targets,
)
from uncruft.models import Analysis, DiskUsage, RiskLevel, ScanResult


def make_scan_result(category_id: str, size: int, risk: RiskLevel) -> ScanResult:
    """Helper to create scan results."""
    return ScanResult(
        category_id=category_id,
        category_name=category_id.replace("_", " ").title(),
        path=f"/test/{category_id}",
        size_bytes=size,
        file_count=10,
        dir_count=2,
        risk_level=risk,
        exists=True,
    )


def make_analysis(results: list[ScanResult]) -> Analysis:
    """Helper to create analysis."""
    return Analysis(
        timestamp=datetime.now(),
        disk_usage=DiskUsage(
            total_bytes=100 * 1024**3,
            used_bytes=80 * 1024**3,
            free_bytes=20 * 1024**3,
        ),
        scan_results=results,
    )


class TestGetRecommendations:
    def test_categorizes_by_risk_level(self):
        results = [
            make_scan_result("safe1", 1000, RiskLevel.SAFE),
            make_scan_result("safe2", 2000, RiskLevel.SAFE),
            make_scan_result("review1", 3000, RiskLevel.REVIEW),
            make_scan_result("risky1", 4000, RiskLevel.RISKY),
        ]
        analysis = make_analysis(results)

        recs = get_recommendations(analysis)

        assert len(recs["safe"]) == 2
        assert len(recs["review"]) == 1
        assert len(recs["risky"]) == 1

    def test_empty_analysis(self):
        analysis = make_analysis([])
        recs = get_recommendations(analysis)

        assert len(recs["safe"]) == 0
        assert len(recs["review"]) == 0
        assert len(recs["risky"]) == 0


class TestExplainCategory:
    def test_existing_category(self):
        info = explain_category("npm_cache")

        assert info is not None
        assert info["id"] == "npm_cache"
        assert "risk_level" in info
        assert "paths" in info
        assert "description" in info

    def test_nonexistent_category(self):
        info = explain_category("nonexistent_category_xyz")
        assert info is None


class TestGetSafeCleanupTargets:
    def test_returns_sorted_by_size(self):
        results = [
            make_scan_result("small", 100, RiskLevel.SAFE),
            make_scan_result("large", 10000, RiskLevel.SAFE),
            make_scan_result("medium", 1000, RiskLevel.SAFE),
        ]
        analysis = make_analysis(results)

        targets = get_safe_cleanup_targets(analysis)

        assert len(targets) == 3
        assert targets[0].category_id == "large"
        assert targets[1].category_id == "medium"
        assert targets[2].category_id == "small"

    def test_excludes_non_safe_items(self):
        results = [
            make_scan_result("safe", 1000, RiskLevel.SAFE),
            make_scan_result("review", 2000, RiskLevel.REVIEW),
        ]
        analysis = make_analysis(results)

        targets = get_safe_cleanup_targets(analysis)

        assert len(targets) == 1
        assert targets[0].category_id == "safe"


class TestEstimateCleanupSavings:
    def test_safe_only(self):
        results = [
            make_scan_result("safe", 1000, RiskLevel.SAFE),
            make_scan_result("review", 2000, RiskLevel.REVIEW),
        ]
        analysis = make_analysis(results)

        savings = estimate_cleanup_savings(analysis, include_review=False)
        assert savings == 1000

    def test_include_review(self):
        results = [
            make_scan_result("safe", 1000, RiskLevel.SAFE),
            make_scan_result("review", 2000, RiskLevel.REVIEW),
        ]
        analysis = make_analysis(results)

        savings = estimate_cleanup_savings(analysis, include_review=True)
        assert savings == 3000


class TestFilterByMinimumSize:
    def test_filters_small_items(self):
        results = [
            make_scan_result("small", 100, RiskLevel.SAFE),
            make_scan_result("large", 10000, RiskLevel.SAFE),
        ]

        filtered = filter_by_minimum_size(results, 500)

        assert len(filtered) == 1
        assert filtered[0].category_id == "large"

    def test_empty_when_all_too_small(self):
        results = [
            make_scan_result("small", 100, RiskLevel.SAFE),
        ]

        filtered = filter_by_minimum_size(results, 500)
        assert len(filtered) == 0


class TestGetCategoryBySize:
    def test_returns_top_n(self):
        results = [
            make_scan_result(f"cat{i}", i * 100, RiskLevel.SAFE)
            for i in range(1, 15)
        ]
        analysis = make_analysis(results)

        top = get_category_by_size(analysis, top_n=5)

        assert len(top) == 5
        # Should be sorted by size descending
        assert top[0].size_bytes > top[1].size_bytes

    def test_excludes_zero_size(self):
        results = [
            make_scan_result("zero", 0, RiskLevel.SAFE),
            make_scan_result("nonzero", 100, RiskLevel.SAFE),
        ]
        analysis = make_analysis(results)

        top = get_category_by_size(analysis, top_n=10)

        assert len(top) == 1
        assert top[0].category_id == "nonzero"


class TestFormatSize:
    def test_bytes(self):
        assert format_size(500) == "500 B"

    def test_kilobytes(self):
        assert format_size(5 * 1000) == "5.0 KB"

    def test_megabytes(self):
        assert format_size(5 * 1000**2) == "5.0 MB"

    def test_gigabytes(self):
        assert format_size(5 * 1000**3) == "5.0 GB"

    def test_fractional_gb(self):
        assert "GB" in format_size(int(1.5 * 1000**3))
