"""Tests for data models."""

import pytest
from datetime import datetime

from uncruft.models import (
    Analysis,
    Category,
    CleanupResult,
    CleanupSession,
    DiskUsage,
    RiskLevel,
    ScanResult,
)


class TestRiskLevel:
    def test_risk_levels_exist(self):
        assert RiskLevel.SAFE == "safe"
        assert RiskLevel.REVIEW == "review"
        assert RiskLevel.RISKY == "risky"


class TestScanResult:
    def test_size_human_bytes(self):
        result = ScanResult(
            category_id="test",
            category_name="Test",
            path="/test",
            size_bytes=500,
            risk_level=RiskLevel.SAFE,
        )
        assert result.size_human == "500 B"

    def test_size_human_kb(self):
        result = ScanResult(
            category_id="test",
            category_name="Test",
            path="/test",
            size_bytes=5000,
            risk_level=RiskLevel.SAFE,
        )
        assert "KB" in result.size_human

    def test_size_human_mb(self):
        result = ScanResult(
            category_id="test",
            category_name="Test",
            path="/test",
            size_bytes=5_000_000,
            risk_level=RiskLevel.SAFE,
        )
        assert "MB" in result.size_human

    def test_size_human_gb(self):
        result = ScanResult(
            category_id="test",
            category_name="Test",
            path="/test",
            size_bytes=5_000_000_000,
            risk_level=RiskLevel.SAFE,
        )
        assert "GB" in result.size_human

    def test_size_gb_property(self):
        result = ScanResult(
            category_id="test",
            category_name="Test",
            path="/test",
            size_bytes=1000**3,  # 1 GB in decimal
            risk_level=RiskLevel.SAFE,
        )
        assert result.size_gb == 1.0


class TestDiskUsage:
    def test_disk_usage_percentages(self):
        usage = DiskUsage(
            total_bytes=100 * 1000**3,  # 100 GB in decimal
            used_bytes=80 * 1000**3,    # 80 GB in decimal
            free_bytes=20 * 1000**3,    # 20 GB in decimal
        )
        assert usage.used_percent == 80.0
        assert usage.total_gb == 100.0
        assert usage.used_gb == 80.0
        assert usage.free_gb == 20.0


class TestAnalysis:
    def test_analysis_categorizes_results(self):
        safe_result = ScanResult(
            category_id="safe1",
            category_name="Safe 1",
            path="/safe",
            size_bytes=1000,
            risk_level=RiskLevel.SAFE,
        )
        review_result = ScanResult(
            category_id="review1",
            category_name="Review 1",
            path="/review",
            size_bytes=2000,
            risk_level=RiskLevel.REVIEW,
        )

        analysis = Analysis(
            disk_usage=DiskUsage(
                total_bytes=100 * 1024**3,
                used_bytes=80 * 1024**3,
                free_bytes=20 * 1024**3,
            ),
            scan_results=[safe_result, review_result],
        )

        assert len(analysis.safe_items) == 1
        assert len(analysis.review_items) == 1
        assert analysis.total_safe_bytes == 1000
        assert analysis.total_review_bytes == 2000


class TestCategory:
    def test_category_creation(self):
        cat = Category(
            id="test_cat",
            name="Test Category",
            paths=["~/test"],
            risk_level=RiskLevel.SAFE,
            description="A test category",
            consequences="None",
            recovery="Automatic",
        )
        assert cat.id == "test_cat"
        assert cat.risk_level == RiskLevel.SAFE


class TestCleanupResult:
    def test_cleanup_result_success(self):
        result = CleanupResult(
            category_id="test",
            path="/test",
            bytes_freed=1000,
            files_deleted=5,
            success=True,
        )
        assert result.success
        assert result.bytes_freed == 1000

    def test_cleanup_result_failure(self):
        result = CleanupResult(
            category_id="test",
            path="/test",
            bytes_freed=0,
            files_deleted=0,
            success=False,
            error="Permission denied",
        )
        assert not result.success
        assert result.error == "Permission denied"


class TestAnalysisTotalCleanable:
    def test_total_cleanable_bytes(self):
        """Test total_cleanable_bytes property."""
        analysis = Analysis(
            disk_usage=DiskUsage(
                total_bytes=100 * 1024**3,
                used_bytes=80 * 1024**3,
                free_bytes=20 * 1024**3,
            ),
            scan_results=[
                ScanResult(
                    category_id="safe1",
                    category_name="Safe 1",
                    path="/safe",
                    size_bytes=1000,
                    risk_level=RiskLevel.SAFE,
                ),
                ScanResult(
                    category_id="review1",
                    category_name="Review 1",
                    path="/review",
                    size_bytes=2000,
                    risk_level=RiskLevel.REVIEW,
                ),
                ScanResult(
                    category_id="empty",
                    category_name="Empty",
                    path="/empty",
                    size_bytes=0,  # Zero size should be excluded
                    risk_level=RiskLevel.SAFE,
                ),
            ],
        )
        assert analysis.total_cleanable_bytes == 3000

    def test_risky_items(self):
        """Test risky_items property."""
        analysis = Analysis(
            disk_usage=DiskUsage(
                total_bytes=100 * 1024**3,
                used_bytes=80 * 1024**3,
                free_bytes=20 * 1024**3,
            ),
            scan_results=[
                ScanResult(
                    category_id="risky1",
                    category_name="Risky 1",
                    path="/risky",
                    size_bytes=5000,
                    risk_level=RiskLevel.RISKY,
                ),
            ],
        )
        assert len(analysis.risky_items) == 1
        assert analysis.risky_items[0].category_id == "risky1"


class TestCleanupSession:
    def test_session_creation(self):
        session = CleanupSession(
            id="test-session",
            disk_before=DiskUsage(
                total_bytes=100 * 1024**3,
                used_bytes=80 * 1024**3,
                free_bytes=20 * 1024**3,
            ),
            results=[
                CleanupResult(
                    category_id="test1",
                    path="/test1",
                    bytes_freed=1000,
                    files_deleted=5,
                    success=True,
                ),
                CleanupResult(
                    category_id="test2",
                    path="/test2",
                    bytes_freed=2000,
                    files_deleted=10,
                    success=True,
                ),
            ],
        )
        assert session.id == "test-session"
        assert len(session.results) == 2

    def test_total_bytes_freed(self):
        session = CleanupSession(
            id="test-session",
            disk_before=DiskUsage(
                total_bytes=100 * 1024**3,
                used_bytes=80 * 1024**3,
                free_bytes=20 * 1024**3,
            ),
            results=[
                CleanupResult(
                    category_id="test1",
                    path="/test1",
                    bytes_freed=1000,
                    success=True,
                ),
                CleanupResult(
                    category_id="test2",
                    path="/test2",
                    bytes_freed=2000,
                    success=True,
                ),
                CleanupResult(
                    category_id="test3",
                    path="/test3",
                    bytes_freed=500,
                    success=False,  # Failed - should not count
                ),
            ],
        )
        assert session.total_bytes_freed == 3000

    def test_success_count(self):
        session = CleanupSession(
            id="test-session",
            disk_before=DiskUsage(
                total_bytes=100 * 1024**3,
                used_bytes=80 * 1024**3,
                free_bytes=20 * 1024**3,
            ),
            results=[
                CleanupResult(
                    category_id="test1",
                    path="/test1",
                    bytes_freed=1000,
                    success=True,
                ),
                CleanupResult(
                    category_id="test2",
                    path="/test2",
                    bytes_freed=2000,
                    success=True,
                ),
                CleanupResult(
                    category_id="test3",
                    path="/test3",
                    bytes_freed=0,
                    success=False,
                ),
            ],
        )
        assert session.success_count == 2

    def test_failure_count(self):
        session = CleanupSession(
            id="test-session",
            disk_before=DiskUsage(
                total_bytes=100 * 1024**3,
                used_bytes=80 * 1024**3,
                free_bytes=20 * 1024**3,
            ),
            results=[
                CleanupResult(
                    category_id="test1",
                    path="/test1",
                    bytes_freed=1000,
                    success=True,
                ),
                CleanupResult(
                    category_id="test2",
                    path="/test2",
                    bytes_freed=0,
                    success=False,
                    error="Error 1",
                ),
                CleanupResult(
                    category_id="test3",
                    path="/test3",
                    bytes_freed=0,
                    success=False,
                    error="Error 2",
                ),
            ],
        )
        assert session.failure_count == 2
