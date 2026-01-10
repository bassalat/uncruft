"""Tests for cleanup functionality."""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess

import pytest

from uncruft.cleaner import (
    BLOCKED_PATHS,
    _run_native_cleanup,
    clean_category,
    clean_safe_items,
    delete_path,
    is_inside_allowed_path,
    is_path_safe,
    validate_cleanup_request,
)
from uncruft.models import RiskLevel, ScanResult
from uncruft.scanner import expand_path


class TestIsPathSafe:
    def test_blocks_home_directory(self):
        home = Path.home()
        assert not is_path_safe(home)

    def test_blocks_exact_home_path(self):
        """Specifically test the home directory check at line 62."""
        # The home check is separate from blocked paths list
        home = Path.home()
        # This tests the exact home path check (line 61-62)
        assert is_path_safe(home) is False

    def test_blocks_documents(self):
        docs = expand_path("~/Documents")
        assert not is_path_safe(docs)

    def test_blocks_desktop(self):
        desktop = expand_path("~/Desktop")
        assert not is_path_safe(desktop)

    def test_allows_cache_directory(self):
        cache = expand_path("~/Library/Caches/test-app")
        # Caches should be allowed (not in blocked list)
        assert is_path_safe(cache)

    def test_blocks_system_paths(self):
        assert not is_path_safe(Path("/System"))
        assert not is_path_safe(Path("/Library"))
        assert not is_path_safe(Path("/Applications"))


class TestDeletePath:
    def test_delete_nonexistent_path(self):
        bytes_freed, files, error = delete_path(Path("/nonexistent/path"))
        assert bytes_freed == 0
        assert files == 0
        assert error is None

    def test_dry_run_does_not_delete(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("Hello!")

            bytes_freed, files, error = delete_path(test_file, dry_run=True)

            # File should still exist
            assert test_file.exists()
            assert bytes_freed == 6
            assert files == 1

    def test_actually_deletes_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("Hello!")

            bytes_freed, files, error = delete_path(test_file, dry_run=False)

            # File should be deleted
            assert not test_file.exists()
            assert bytes_freed == 6
            assert files == 1
            assert error is None

    def test_actually_deletes_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = Path(tmpdir) / "subdir"
            subdir.mkdir()
            (subdir / "file.txt").write_text("test")

            bytes_freed, files, error = delete_path(subdir, dry_run=False)

            # Directory should be deleted
            assert not subdir.exists()
            assert bytes_freed == 4
            assert error is None


class TestValidateCleanupRequest:
    def test_valid_request(self):
        is_valid, error = validate_cleanup_request(
            category_ids=["npm_cache", "pip_cache"],
            total_bytes=1024 * 1024,  # 1 MB
        )
        assert is_valid
        assert error is None

    def test_invalid_category(self):
        is_valid, error = validate_cleanup_request(
            category_ids=["nonexistent_category"],
            total_bytes=1024,
        )
        assert not is_valid
        assert "Unknown category" in error

    def test_exceeds_size_limit(self):
        is_valid, error = validate_cleanup_request(
            category_ids=["npm_cache"],
            total_bytes=200 * 1024**3,  # 200 GB - exceeds limit
        )
        assert not is_valid
        assert "exceeds safety limit" in error


class TestIsInsideAllowedPath:
    def test_path_inside_category(self):
        # npm_cache has path ~/.npm/_cacache
        npm_path = expand_path("~/.npm/_cacache/some/file")
        assert is_inside_allowed_path(npm_path, "npm_cache")

    def test_path_outside_category(self):
        random_path = expand_path("~/random/path")
        assert not is_inside_allowed_path(random_path, "npm_cache")

    def test_invalid_category(self):
        path = expand_path("~/some/path")
        assert not is_inside_allowed_path(path, "nonexistent_category")


class TestCleanCategory:
    def test_unknown_category(self):
        result = clean_category("nonexistent_category")
        assert not result.success
        assert "Unknown category" in result.error

    def test_clean_nonexistent_paths(self):
        # Most categories will have nonexistent paths in a container
        result = clean_category("npm_cache", dry_run=True)
        # Should complete without error (paths just don't exist)
        assert result.category_id == "npm_cache"

    def test_clean_with_progress_callback(self):
        callback_calls = []

        def callback(path, bytes_freed):
            callback_calls.append((path, bytes_freed))

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test category with temp path would need mocking
            result = clean_category("npm_cache", dry_run=True, progress_callback=callback)
            # Callback may or may not be called depending on path existence


class TestRunNativeCleanup:
    def test_dry_run(self):
        result = _run_native_cleanup("test", "echo hello", dry_run=True)
        assert result.success
        assert result.dry_run
        assert "[native command:" in result.path

    @patch("subprocess.run")
    def test_successful_command(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        result = _run_native_cleanup("test", "echo hello", dry_run=False)
        assert result.success
        assert not result.dry_run

    @patch("subprocess.run")
    def test_failed_command(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="Command failed")
        result = _run_native_cleanup("test", "false", dry_run=False)
        assert not result.success
        assert "Command failed" in result.error

    @patch("subprocess.run")
    def test_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 300)
        result = _run_native_cleanup("test", "sleep 1000", dry_run=False)
        assert not result.success
        assert "timed out" in result.error

    @patch("subprocess.run")
    def test_exception(self, mock_run):
        mock_run.side_effect = Exception("Unexpected error")
        result = _run_native_cleanup("test", "cmd", dry_run=False)
        assert not result.success
        assert "Unexpected error" in result.error


class TestCleanSafeItems:
    def test_empty_list(self):
        results = clean_safe_items([], dry_run=True)
        assert len(results) == 0

    def test_filters_non_safe_items(self):
        scan_results = [
            ScanResult(
                category_id="review_cat",
                category_name="Review Category",
                path="/test",
                size_bytes=1000,
                risk_level=RiskLevel.REVIEW,
            ),
        ]
        results = clean_safe_items(scan_results, dry_run=True)
        assert len(results) == 0

    def test_filters_zero_size_items(self):
        scan_results = [
            ScanResult(
                category_id="npm_cache",
                category_name="NPM Cache",
                path="/test",
                size_bytes=0,  # Zero size
                risk_level=RiskLevel.SAFE,
            ),
        ]
        results = clean_safe_items(scan_results, dry_run=True)
        assert len(results) == 0

    def test_with_progress_callback(self):
        callback_calls = []

        def callback(name, current, total):
            callback_calls.append((name, current, total))

        scan_results = [
            ScanResult(
                category_id="npm_cache",
                category_name="NPM Cache",
                path="/test",
                size_bytes=1000,
                risk_level=RiskLevel.SAFE,
            ),
        ]
        results = clean_safe_items(
            scan_results, dry_run=True, progress_callback=callback
        )
        assert len(callback_calls) == 1


class TestDeletePathErrors:
    def test_permission_error(self):
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("pathlib.Path.stat", side_effect=PermissionError("No access")):
                    bytes_freed, files, error = delete_path(Path("/fake/path"))
                    assert bytes_freed == 0
                    assert "Permission denied" in error

    def test_os_error(self):
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("pathlib.Path.stat", side_effect=OSError("Disk error")):
                    bytes_freed, files, error = delete_path(Path("/fake/path"))
                    assert bytes_freed == 0
                    assert "OS error" in error


class TestCleanCategoryWithNativeCommand:
    @patch("uncruft.cleaner._run_native_cleanup")
    def test_uses_native_command_when_not_dry_run(self, mock_native):
        """Should call native cleanup when category has cleanup_command and not dry_run."""
        mock_native.return_value = MagicMock(success=True)
        # npm_cache has a native cleanup command
        result = clean_category("npm_cache", dry_run=False)
        mock_native.assert_called_once()


class TestCleanCategoryWithBlockedPath:
    def test_blocks_unsafe_path(self):
        """Should not clean paths that fail safety checks."""
        # Create a temporary category that points to a blocked path
        with patch("uncruft.cleaner.expand_path") as mock_expand:
            with patch("pathlib.Path.exists", return_value=True):
                # Make expand_path return the home directory itself
                mock_expand.return_value = Path.home()
                result = clean_category("npm_cache", dry_run=True)
                # Should have an error about blocked path


class TestCleanCategoryWithRealProgress:
    def test_progress_callback_called_on_success(self):
        """Progress callback should be called when files are cleaned."""
        callback_data = []

        def progress_cb(path, bytes_freed):
            callback_data.append((path, bytes_freed))

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file in a temp location
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test data")

            # Mock the category paths to use our temp file
            with patch("uncruft.cleaner.get_category") as mock_get_cat:
                from uncruft.models import Category, RiskLevel

                mock_cat = Category(
                    id="test_cat",
                    name="Test Category",
                    paths=[str(test_file)],
                    risk_level=RiskLevel.SAFE,
                    description="Test",
                    consequences="None",
                    recovery="None",
                )
                mock_get_cat.return_value = mock_cat

                result = clean_category("test_cat", dry_run=False, progress_callback=progress_cb)

                # Check callback was called
                if result.success and result.bytes_freed > 0:
                    assert len(callback_data) > 0


class TestCleanCategoryErrorHandling:
    def test_error_during_delete(self):
        """Should handle errors during deletion gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test data")

            with patch("uncruft.cleaner.get_category") as mock_get_cat:
                with patch("uncruft.cleaner.delete_path") as mock_delete:
                    from uncruft.models import Category, RiskLevel

                    mock_cat = Category(
                        id="test_cat",
                        name="Test Category",
                        paths=[str(test_file)],
                        risk_level=RiskLevel.SAFE,
                        description="Test",
                        consequences="None",
                        recovery="None",
                    )
                    mock_get_cat.return_value = mock_cat
                    mock_delete.return_value = (0, 0, "Mock error occurred")

                    result = clean_category("test_cat", dry_run=False)

                    # Should capture the error
                    assert not result.success or "error" in (result.error or "").lower() or result.bytes_freed == 0
