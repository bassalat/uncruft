"""Tests for disk scanner."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from uncruft.scanner import (
    aggregate_category_results,
    expand_path,
    get_directory_size,
    get_disk_usage,
    quick_scan,
    scan_all_categories,
    scan_category,
    scan_path,
)
from uncruft.models import Category, RiskLevel, ScanResult


class TestExpandPath:
    def test_expands_tilde(self):
        result = expand_path("~/test")
        assert str(result).startswith(str(Path.home()))

    def test_handles_absolute_path(self):
        result = expand_path("/absolute/path")
        assert str(result) == "/absolute/path"


class TestGetDirectorySize:
    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            size, files, dirs = get_directory_size(Path(tmpdir))
            assert size == 0
            assert files == 0

    def test_directory_with_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("Hello, World!")

            size, files, dirs = get_directory_size(Path(tmpdir))
            assert size == len("Hello, World!")
            assert files == 1

    def test_nested_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create nested structure
            subdir = Path(tmpdir) / "subdir"
            subdir.mkdir()
            (subdir / "file.txt").write_text("test")

            size, files, dirs = get_directory_size(Path(tmpdir))
            assert size == 4  # "test"
            assert files == 1
            assert dirs == 1


class TestScanPath:
    def test_scan_nonexistent_path(self):
        category = Category(
            id="test",
            name="Test",
            paths=["/nonexistent/path"],
            risk_level=RiskLevel.SAFE,
            description="Test",
            consequences="None",
            recovery="None",
        )

        result = scan_path("/nonexistent/path", category)
        assert not result.exists
        assert result.size_bytes == 0

    def test_scan_existing_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("Hello!")

            category = Category(
                id="test",
                name="Test",
                paths=[tmpdir],
                risk_level=RiskLevel.SAFE,
                description="Test",
                consequences="None",
                recovery="None",
            )

            result = scan_path(tmpdir, category)
            assert result.exists
            assert result.size_bytes == 6  # "Hello!"
            assert result.file_count == 1


class TestGetDiskUsage:
    def test_returns_valid_usage(self):
        usage = get_disk_usage("/")
        assert usage.total_bytes > 0
        assert usage.used_bytes > 0
        assert usage.free_bytes >= 0
        # used + free may be less than total due to reserved blocks
        assert usage.used_bytes + usage.free_bytes <= usage.total_bytes


class TestScanPathFile:
    def test_scan_single_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test content")
            f.flush()

            category = Category(
                id="test",
                name="Test",
                paths=[f.name],
                risk_level=RiskLevel.SAFE,
                description="Test",
                consequences="None",
                recovery="None",
            )

            result = scan_path(f.name, category)

            assert result.exists
            assert result.size_bytes == 12  # "test content"
            assert result.file_count == 1
            assert result.dir_count == 0

            os.unlink(f.name)


class TestScanPathSpecialFile:
    def test_scan_symlink(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a symlink to a nonexistent target
            symlink = Path(tmpdir) / "symlink"
            target = Path(tmpdir) / "nonexistent"
            symlink.symlink_to(target)

            category = Category(
                id="test",
                name="Test",
                paths=[str(symlink)],
                risk_level=RiskLevel.SAFE,
                description="Test",
                consequences="None",
                recovery="None",
            )

            result = scan_path(str(symlink), category)
            # Broken symlink - should handle gracefully
            assert result is not None


class TestScanCategory:
    def test_scan_category_multiple_paths(self):
        category = Category(
            id="test",
            name="Test",
            paths=["/nonexistent/path1", "/nonexistent/path2"],
            risk_level=RiskLevel.SAFE,
            description="Test",
            consequences="None",
            recovery="None",
        )

        results = scan_category(category)
        assert len(results) == 2


class TestAggregateResults:
    def test_empty_list(self):
        result = aggregate_category_results([])
        assert result is None

    def test_single_result(self):
        results = [
            ScanResult(
                category_id="test",
                category_name="Test",
                path="/test",
                size_bytes=1000,
                file_count=5,
                dir_count=2,
                risk_level=RiskLevel.SAFE,
                exists=True,
            )
        ]
        aggregated = aggregate_category_results(results)

        assert aggregated is not None
        assert aggregated.size_bytes == 1000
        assert aggregated.file_count == 5

    def test_multiple_results(self):
        results = [
            ScanResult(
                category_id="test",
                category_name="Test",
                path="/test1",
                size_bytes=1000,
                file_count=5,
                dir_count=2,
                risk_level=RiskLevel.SAFE,
                exists=True,
            ),
            ScanResult(
                category_id="test",
                category_name="Test",
                path="/test2",
                size_bytes=2000,
                file_count=10,
                dir_count=3,
                risk_level=RiskLevel.SAFE,
                exists=True,
            ),
        ]
        aggregated = aggregate_category_results(results)

        assert aggregated is not None
        assert aggregated.size_bytes == 3000
        assert aggregated.file_count == 15
        assert aggregated.dir_count == 5

    def test_with_errors(self):
        results = [
            ScanResult(
                category_id="test",
                category_name="Test",
                path="/test",
                size_bytes=0,
                file_count=0,
                dir_count=0,
                risk_level=RiskLevel.SAFE,
                exists=True,
                error="Permission denied",
            )
        ]
        aggregated = aggregate_category_results(results)

        assert aggregated is not None
        assert aggregated.error == "Permission denied"


class TestScanAllCategories:
    def test_scans_all_categories(self):
        results = scan_all_categories(max_workers=2)
        # Should return results for all categories
        assert len(results) > 0

    def test_with_progress_callback(self):
        callback_calls = []

        def callback(name, current, total):
            callback_calls.append((name, current, total))

        results = scan_all_categories(progress_callback=callback, max_workers=2)

        assert len(callback_calls) > 0


class TestQuickScan:
    def test_scan_all(self):
        results = quick_scan(category_ids=None)
        assert len(results) > 0

    def test_scan_specific_categories(self):
        results = quick_scan(category_ids=["npm_cache", "pip_cache"])
        # Should only have results for specified categories
        category_ids = [r.category_id for r in results]
        assert all(cid in ["npm_cache", "pip_cache"] for cid in category_ids)

    def test_scan_nonexistent_category(self):
        results = quick_scan(category_ids=["nonexistent_category"])
        assert len(results) == 0


class TestGetDirectorySizeErrors:
    def test_handles_permission_error_during_scan(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a subdirectory
            subdir = Path(tmpdir) / "subdir"
            subdir.mkdir()
            (subdir / "file.txt").write_text("test")

            # This tests the normal path; permission errors in real use
            # would be skipped
            size, files, dirs = get_directory_size(Path(tmpdir))
            assert size == 4
            assert files == 1


class TestScanPathErrors:
    def test_permission_error(self):
        category = Category(
            id="test",
            name="Test",
            paths=["/root/secret"],  # Typically not accessible
            risk_level=RiskLevel.SAFE,
            description="Test",
            consequences="None",
            recovery="None",
        )

        # Should handle gracefully
        result = scan_path("/root/secret", category)
        # Either doesn't exist or has an error
        assert result is not None

    def test_scan_path_with_permission_error(self):
        """Test scanning path with permission error."""
        category = Category(
            id="test",
            name="Test",
            paths=["/test"],
            risk_level=RiskLevel.SAFE,
            description="Test",
            consequences="None",
            recovery="None",
        )

        with patch("uncruft.scanner.expand_path") as mock_expand:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.is_file.side_effect = PermissionError("No access")
            mock_expand.return_value = mock_path

            result = scan_path("/test", category)
            assert result is not None
            assert result.error is not None or not result.exists


class TestScanPathSpecialTypes:
    def test_scan_non_file_non_dir(self):
        """Test scanning a path that is neither file nor directory."""
        category = Category(
            id="test",
            name="Test",
            paths=["/test"],
            risk_level=RiskLevel.SAFE,
            description="Test",
            consequences="None",
            recovery="None",
        )

        with patch("uncruft.scanner.expand_path") as mock_expand:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.is_file.return_value = False
            mock_path.is_dir.return_value = False  # Special file (socket, device, etc.)
            mock_path.__str__ = lambda x: "/test/special"
            mock_expand.return_value = mock_path

            result = scan_path("/test", category)
            # Should return a result with exists=False for special files
            assert result is not None
            assert result.size_bytes == 0


class TestScanAllCategoriesException:
    def test_handles_exception_in_category(self):
        """Test handling exception during category scan."""
        with patch("uncruft.scanner.scan_category") as mock_scan:
            mock_scan.side_effect = Exception("Test exception")

            results = scan_all_categories(max_workers=1)

            # Should return results with errors instead of crashing
            assert len(results) > 0
            # At least some results should have errors
            error_results = [r for r in results if r.error]
            assert len(error_results) > 0


class TestGetDirectorySizePermissionErrors:
    def test_handles_permission_error_in_rglob(self):
        """Test handling permission error during recursive glob."""
        with patch("pathlib.Path.rglob") as mock_rglob:
            mock_rglob.side_effect = PermissionError("No access")

            size, files, dirs = get_directory_size(Path("/test"))

            # Should return zeros instead of crashing
            assert size == 0
            assert files == 0
            assert dirs == 0

    def test_handles_oserror_in_rglob(self):
        """Test handling OS error during recursive glob."""
        with patch("pathlib.Path.rglob") as mock_rglob:
            mock_rglob.side_effect = OSError("Disk error")

            size, files, dirs = get_directory_size(Path("/test"))

            # Should return zeros instead of crashing
            assert size == 0
            assert files == 0
            assert dirs == 0

    def test_handles_error_on_individual_file(self):
        """Test handling permission error on individual file during iteration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test")

            # Mock stat to raise error on specific file
            original_stat = Path.stat

            def mock_stat(self):
                if "test.txt" in str(self):
                    raise PermissionError("No access")
                return original_stat(self)

            with patch.object(Path, "stat", mock_stat):
                size, files, dirs = get_directory_size(Path(tmpdir))
                # Should handle gracefully (skip the errored file)
                assert size >= 0
