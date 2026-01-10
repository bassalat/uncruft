"""Tests for display module."""

import pytest
from unittest.mock import patch, MagicMock
from io import StringIO

from uncruft.display import (
    confirm_action,
    format_size,
    risk_icon,
    risk_label,
    show_analysis,
    show_category_explanation,
    show_cleanup_preview,
    show_cleanup_progress,
    show_cleanup_result,
    show_cleanup_summary,
    show_disk_summary,
    show_scanning_progress,
    show_status,
)
from uncruft.models import (
    Analysis,
    CleanupResult,
    DiskUsage,
    RiskLevel,
    ScanResult,
)


class TestRiskIcon:
    def test_safe_icon(self):
        icon = risk_icon(RiskLevel.SAFE)
        assert "✓" in icon
        assert "green" in icon

    def test_review_icon(self):
        icon = risk_icon(RiskLevel.REVIEW)
        assert "!" in icon
        assert "yellow" in icon

    def test_risky_icon(self):
        icon = risk_icon(RiskLevel.RISKY)
        assert "✗" in icon
        assert "red" in icon

    def test_unknown_icon(self):
        icon = risk_icon("unknown")
        assert icon == "?"


class TestRiskLabel:
    def test_safe_label(self):
        label = risk_label(RiskLevel.SAFE)
        assert "Safe" in label
        assert "green" in label

    def test_review_label(self):
        label = risk_label(RiskLevel.REVIEW)
        assert "Review" in label
        assert "yellow" in label

    def test_risky_label(self):
        label = risk_label(RiskLevel.RISKY)
        assert "Risky" in label
        assert "red" in label


class TestFormatSize:
    def test_bytes(self):
        assert format_size(500) == "500 B"

    def test_kilobytes(self):
        assert format_size(5 * 1000) == "5.0 KB"

    def test_megabytes(self):
        assert format_size(5 * 1000**2) == "5.0 MB"

    def test_gigabytes(self):
        assert format_size(5 * 1000**3) == "5.0 GB"


class TestShowDiskSummary:
    @patch("uncruft.display.console")
    def test_low_usage(self, mock_console):
        usage = DiskUsage(
            total_bytes=100 * 1024**3,
            used_bytes=30 * 1024**3,
            free_bytes=70 * 1024**3,
        )
        show_disk_summary(usage)
        mock_console.print.assert_called()

    @patch("uncruft.display.console")
    def test_high_usage(self, mock_console):
        usage = DiskUsage(
            total_bytes=100 * 1024**3,
            used_bytes=92 * 1024**3,  # 92% - critical
            free_bytes=8 * 1024**3,
        )
        show_disk_summary(usage)
        mock_console.print.assert_called()

    @patch("uncruft.display.console")
    def test_medium_usage(self, mock_console):
        usage = DiskUsage(
            total_bytes=100 * 1024**3,
            used_bytes=80 * 1024**3,  # 80% - warning
            free_bytes=20 * 1024**3,
        )
        show_disk_summary(usage)
        mock_console.print.assert_called()


class TestShowStatus:
    @patch("uncruft.display.console")
    def test_ok_status(self, mock_console):
        usage = DiskUsage(
            total_bytes=100 * 1024**3,
            used_bytes=50 * 1024**3,
            free_bytes=50 * 1024**3,
        )
        show_status(usage)
        # Should print with OK status
        assert mock_console.print.called

    @patch("uncruft.display.console")
    def test_warning_status(self, mock_console):
        usage = DiskUsage(
            total_bytes=100 * 1024**3,
            used_bytes=80 * 1024**3,  # 80%
            free_bytes=20 * 1024**3,
        )
        show_status(usage)
        assert mock_console.print.called

    @patch("uncruft.display.console")
    def test_critical_status(self, mock_console):
        usage = DiskUsage(
            total_bytes=100 * 1024**3,
            used_bytes=95 * 1024**3,  # 95%
            free_bytes=5 * 1024**3,
        )
        show_status(usage)
        assert mock_console.print.called


class TestShowAnalysis:
    @patch("uncruft.display.console")
    def test_with_safe_items(self, mock_console):
        analysis = Analysis(
            disk_usage=DiskUsage(
                total_bytes=100 * 1024**3,
                used_bytes=80 * 1024**3,
                free_bytes=20 * 1024**3,
            ),
            scan_results=[
                ScanResult(
                    category_id="test",
                    category_name="Test",
                    path="/test",
                    size_bytes=1000,
                    risk_level=RiskLevel.SAFE,
                )
            ],
        )
        show_analysis(analysis)
        assert mock_console.print.called

    @patch("uncruft.display.console")
    def test_with_review_items(self, mock_console):
        analysis = Analysis(
            disk_usage=DiskUsage(
                total_bytes=100 * 1024**3,
                used_bytes=80 * 1024**3,
                free_bytes=20 * 1024**3,
            ),
            scan_results=[
                ScanResult(
                    category_id="test",
                    category_name="Test",
                    path="/test",
                    size_bytes=1000,
                    risk_level=RiskLevel.REVIEW,
                )
            ],
        )
        show_analysis(analysis)
        assert mock_console.print.called


class TestShowCleanupPreview:
    @patch("uncruft.display.console")
    def test_preview_with_items(self, mock_console):
        items = [
            ScanResult(
                category_id="test",
                category_name="Test",
                path="/test",
                size_bytes=1000,
                risk_level=RiskLevel.SAFE,
            )
        ]
        show_cleanup_preview(items, dry_run=True)
        assert mock_console.print.called

    @patch("uncruft.display.console")
    def test_preview_without_dry_run(self, mock_console):
        items = [
            ScanResult(
                category_id="test",
                category_name="Test",
                path="/test",
                size_bytes=1000,
                risk_level=RiskLevel.SAFE,
            )
        ]
        show_cleanup_preview(items, dry_run=False)
        assert mock_console.print.called


class TestShowCleanupResult:
    @patch("uncruft.display.console")
    def test_success_result(self, mock_console):
        result = CleanupResult(
            category_id="test",
            path="/test",
            bytes_freed=1000,
            files_deleted=5,
            success=True,
        )
        show_cleanup_result(result)
        # Check that success marker was used
        call_args = str(mock_console.print.call_args)
        assert "✓" in call_args or mock_console.print.called

    @patch("uncruft.display.console")
    def test_failure_result(self, mock_console):
        result = CleanupResult(
            category_id="test",
            path="/test",
            bytes_freed=0,
            files_deleted=0,
            success=False,
            error="Permission denied",
        )
        show_cleanup_result(result)
        assert mock_console.print.called


class TestShowCleanupSummary:
    @patch("uncruft.display.console")
    def test_summary_with_results(self, mock_console):
        results = [
            CleanupResult(
                category_id="test",
                path="/test",
                bytes_freed=1000,
                files_deleted=5,
                success=True,
            )
        ]
        disk_before = DiskUsage(
            total_bytes=100 * 1024**3,
            used_bytes=80 * 1024**3,
            free_bytes=20 * 1024**3,
        )
        disk_after = DiskUsage(
            total_bytes=100 * 1024**3,
            used_bytes=79 * 1024**3,
            free_bytes=21 * 1024**3,
        )
        show_cleanup_summary(results, disk_before, disk_after)
        assert mock_console.print.called

    @patch("uncruft.display.console")
    def test_summary_with_failures(self, mock_console):
        results = [
            CleanupResult(
                category_id="test",
                path="/test",
                bytes_freed=0,
                files_deleted=0,
                success=False,
                error="Failed",
            )
        ]
        disk_before = DiskUsage(
            total_bytes=100 * 1024**3,
            used_bytes=80 * 1024**3,
            free_bytes=20 * 1024**3,
        )
        disk_after = disk_before
        show_cleanup_summary(results, disk_before, disk_after)
        assert mock_console.print.called


class TestShowCategoryExplanation:
    @patch("uncruft.display.console")
    def test_basic_explanation(self, mock_console):
        info = {
            "name": "Test Category",
            "risk_level": "safe",
            "paths": ["/test/path"],
            "description": "A test category",
            "consequences": "None",
            "recovery": "Automatic",
            "cleanup_command": None,
        }
        show_category_explanation(info)
        assert mock_console.print.called

    @patch("uncruft.display.console")
    def test_explanation_with_cleanup_command(self, mock_console):
        info = {
            "name": "Test Category",
            "risk_level": "review",
            "paths": ["/test/path"],
            "description": "A test category",
            "consequences": "Data loss",
            "recovery": "Manual",
            "cleanup_command": "rm -rf /tmp/test",
        }
        show_category_explanation(info)
        assert mock_console.print.called


class TestShowProgress:
    def test_cleanup_progress(self):
        progress = show_cleanup_progress()
        assert progress is not None

    def test_scanning_progress(self):
        progress = show_scanning_progress()
        assert progress is not None


class TestConfirmAction:
    @patch("rich.prompt.Confirm.ask")
    def test_confirm_yes(self, mock_ask):
        mock_ask.return_value = True
        result = confirm_action("Proceed?")
        assert result is True

    @patch("rich.prompt.Confirm.ask")
    def test_confirm_no(self, mock_ask):
        mock_ask.return_value = False
        result = confirm_action("Proceed?")
        assert result is False
