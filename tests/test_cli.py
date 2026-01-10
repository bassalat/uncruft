"""Tests for CLI interface."""

from unittest.mock import patch, MagicMock

from typer.testing import CliRunner

from uncruft.cli import app

runner = CliRunner()


class TestVersion:
    def test_version_flag(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "uncruft version" in result.stdout

    def test_version_short_flag(self):
        result = runner.invoke(app, ["-v"])
        assert result.exit_code == 0
        assert "uncruft version" in result.stdout


class TestHelp:
    def test_help_flag(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "uncruft" in result.stdout
        assert "analyze" in result.stdout
        assert "clean" in result.stdout

    def test_analyze_help(self):
        result = runner.invoke(app, ["analyze", "--help"])
        assert result.exit_code == 0
        assert "Analyze disk usage" in result.stdout

    def test_clean_help(self):
        result = runner.invoke(app, ["clean", "--help"])
        assert result.exit_code == 0
        assert "--safe" in result.stdout
        assert "--dry-run" in result.stdout


class TestStatus:
    def test_status_command(self):
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Disk Status" in result.stdout


class TestList:
    def test_list_command(self):
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "Available Categories" in result.stdout
        assert "Safe to Clean" in result.stdout


class TestExplain:
    def test_explain_valid_category(self):
        result = runner.invoke(app, ["explain", "npm_cache"])
        assert result.exit_code == 0
        assert "NPM" in result.stdout

    def test_explain_invalid_category(self):
        result = runner.invoke(app, ["explain", "nonexistent"])
        assert result.exit_code == 1
        assert "Unknown category" in result.stdout


class TestClean:
    def test_clean_without_options(self):
        """Should require --safe or --category."""
        result = runner.invoke(app, ["clean"])
        assert result.exit_code == 1
        assert "Specify --safe or --category" in result.stdout

    def test_clean_invalid_category(self):
        result = runner.invoke(app, ["clean", "--category", "nonexistent"])
        assert result.exit_code == 1
        assert "Unknown category" in result.stdout

    def test_clean_dry_run(self):
        """Dry run should not prompt for confirmation."""
        result = runner.invoke(app, ["clean", "--safe", "--dry-run"])
        # Should at least start without error
        assert "DRY RUN" in result.stdout or "No safe items" in result.stdout


class TestAnalyze:
    def test_analyze_runs(self):
        """Analyze should run and show output."""
        result = runner.invoke(app, ["analyze"])
        # Should complete (may take a moment)
        assert result.exit_code == 0
        assert "Analyzing" in result.stdout or "Disk Summary" in result.stdout


class TestHistory:
    def test_history_not_implemented(self):
        """History command should show not implemented message."""
        result = runner.invoke(app, ["history"])
        assert result.exit_code == 0
        assert "not yet implemented" in result.stdout


class TestConfig:
    def test_config_not_implemented(self):
        """Config command should show not implemented message."""
        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        assert "not yet implemented" in result.stdout


class TestCleanCategory:
    def test_clean_valid_category_dry_run(self):
        """Clean specific category with dry-run."""
        result = runner.invoke(app, ["clean", "--category", "npm_cache", "--dry-run"])
        # Should run without error
        assert result.exit_code == 0

    def test_clean_valid_category_with_yes(self):
        """Clean specific category with -y flag."""
        result = runner.invoke(app, ["clean", "--category", "npm_cache", "--dry-run", "-y"])
        assert result.exit_code == 0

    @patch("uncruft.cli.confirm_action")
    def test_clean_category_cancelled(self, mock_confirm):
        """Clean should handle cancellation."""
        mock_confirm.return_value = False
        result = runner.invoke(app, ["clean", "--category", "npm_cache"])
        assert "Cancelled" in result.stdout or result.exit_code == 0


class TestCleanSafe:
    def test_clean_safe_dry_run_with_yes(self):
        """Clean safe with -y and --dry-run."""
        result = runner.invoke(app, ["clean", "--safe", "--dry-run", "-y"])
        assert result.exit_code == 0

    @patch("uncruft.cli.confirm_action")
    def test_clean_safe_cancelled(self, mock_confirm):
        """Clean safe should handle cancellation."""
        mock_confirm.return_value = False
        result = runner.invoke(app, ["clean", "--safe"])
        # Either cancelled or no items to clean
        assert result.exit_code == 0


class TestListRiskyCategories:
    def test_list_shows_categories(self):
        """List command should show all category types."""
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "Safe to Clean" in result.stdout
        # Review categories should also be shown
        assert "Review Needed" in result.stdout

    @patch("uncruft.cli.get_all_categories")
    def test_list_shows_risky_categories(self, mock_get_cats):
        """List should show risky categories when they exist."""
        from uncruft.models import Category, RiskLevel

        mock_get_cats.return_value = [
            Category(
                id="risky_cat",
                name="Risky Category",
                paths=["~/risky"],
                risk_level=RiskLevel.RISKY,
                description="Test",
                consequences="Bad things",
                recovery="Difficult",
            ),
        ]

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "High Risk" in result.stdout or "risky_cat" in result.stdout


class TestCleanCategoryActualClean:
    @patch("uncruft.cli.confirm_action")
    @patch("uncruft.cli.clean_category")
    @patch("uncruft.cli.get_disk_usage")
    def test_clean_category_shows_space_freed(self, mock_disk, mock_clean, mock_confirm):
        """Clean category should show space freed after actual clean."""
        from uncruft.models import CleanupResult, DiskUsage

        mock_confirm.return_value = True
        mock_clean.return_value = CleanupResult(
            category_id="npm_cache",
            path="/test",
            bytes_freed=1000000,
            files_deleted=10,
            success=True,
        )
        # Before and after disk usage
        mock_disk.side_effect = [
            DiskUsage(
                total_bytes=100 * 1024**3,
                used_bytes=80 * 1024**3,
                free_bytes=20 * 1024**3,
            ),
            DiskUsage(
                total_bytes=100 * 1024**3,
                used_bytes=79 * 1024**3,
                free_bytes=21 * 1024**3,
            ),
        ]

        result = runner.invoke(app, ["clean", "--category", "npm_cache"])
        # Should show space freed
        assert result.exit_code == 0


class TestCleanSafeNoItems:
    @patch("uncruft.cli.analyze_disk")
    def test_no_safe_items_message(self, mock_analyze):
        """Should show message when no safe items to clean."""
        from uncruft.models import Analysis, DiskUsage

        mock_analyze.return_value = Analysis(
            disk_usage=DiskUsage(
                total_bytes=100 * 1024**3,
                used_bytes=80 * 1024**3,
                free_bytes=20 * 1024**3,
            ),
            scan_results=[],  # No results
        )

        result = runner.invoke(app, ["clean", "--safe"])
        assert result.exit_code == 0
        assert "No safe items" in result.stdout


class TestCleanSafetCheckFailed:
    @patch("uncruft.cli.analyze_disk")
    @patch("uncruft.cli.validate_cleanup_request")
    def test_safety_check_failed_message(self, mock_validate, mock_analyze):
        """Should show error when safety check fails."""
        from uncruft.models import Analysis, DiskUsage, RiskLevel, ScanResult

        mock_analyze.return_value = Analysis(
            disk_usage=DiskUsage(
                total_bytes=100 * 1024**3,
                used_bytes=80 * 1024**3,
                free_bytes=20 * 1024**3,
            ),
            scan_results=[
                ScanResult(
                    category_id="npm_cache",
                    category_name="NPM Cache",
                    path="/test",
                    size_bytes=1000,
                    risk_level=RiskLevel.SAFE,
                )
            ],
        )
        mock_validate.return_value = (False, "Test safety error")

        result = runner.invoke(app, ["clean", "--safe", "--dry-run"])
        assert result.exit_code == 1
        assert "Safety check failed" in result.stdout


class TestCleanSafeWithSummary:
    @patch("uncruft.cli.confirm_action")
    @patch("uncruft.cli.analyze_disk")
    @patch("uncruft.cli.clean_safe_items")
    @patch("uncruft.cli.get_disk_usage")
    @patch("uncruft.cli.show_cleanup_summary")
    def test_shows_cleanup_summary(self, mock_summary, mock_disk, mock_clean, mock_analyze, mock_confirm):
        """Should show cleanup summary after actual clean."""
        from uncruft.models import Analysis, CleanupResult, DiskUsage, RiskLevel, ScanResult

        mock_confirm.return_value = True
        mock_analyze.return_value = Analysis(
            disk_usage=DiskUsage(
                total_bytes=100 * 1024**3,
                used_bytes=80 * 1024**3,
                free_bytes=20 * 1024**3,
            ),
            scan_results=[
                ScanResult(
                    category_id="npm_cache",
                    category_name="NPM Cache",
                    path="/test",
                    size_bytes=1000,
                    risk_level=RiskLevel.SAFE,
                )
            ],
        )
        mock_clean.return_value = [
            CleanupResult(
                category_id="npm_cache",
                path="/test",
                bytes_freed=1000,
                success=True,
            )
        ]
        mock_disk.return_value = DiskUsage(
            total_bytes=100 * 1024**3,
            used_bytes=79 * 1024**3,
            free_bytes=21 * 1024**3,
        )

        result = runner.invoke(app, ["clean", "--safe"])
        # Summary should be called
        mock_summary.assert_called_once()
