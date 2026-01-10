"""Tests for recursive directory scanning."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from uncruft.models import Category, RiskLevel
from uncruft.recursive_scanner import (
    aggregate_recursive_results,
    find_matching_directories,
    scan_recursive_category,
)


class TestFindMatchingDirectories:
    def test_finds_matching_directory(self, tmp_path):
        """Find a single matching directory."""
        # Create a node_modules directory
        node_modules = tmp_path / "project" / "node_modules"
        node_modules.mkdir(parents=True)
        (node_modules / "package.json").write_text("{}")

        results = list(find_matching_directories(tmp_path, "node_modules"))
        assert len(results) == 1
        assert results[0] == node_modules

    def test_finds_nested_directories(self, tmp_path):
        """Find node_modules in multiple projects."""
        # Create multiple projects with node_modules
        for project in ["project1", "project2", "project3"]:
            node_modules = tmp_path / project / "node_modules"
            node_modules.mkdir(parents=True)

        results = list(find_matching_directories(tmp_path, "node_modules"))
        assert len(results) == 3

    def test_skips_nested_node_modules(self, tmp_path):
        """Don't scan node_modules inside node_modules."""
        # Create nested node_modules
        outer = tmp_path / "project" / "node_modules"
        inner = outer / "some-package" / "node_modules"
        inner.mkdir(parents=True)

        results = list(find_matching_directories(tmp_path, "node_modules"))
        # Should only find the outer one
        assert len(results) == 1
        assert results[0] == outer

    def test_handles_permission_error(self, tmp_path):
        """Gracefully handle permission errors."""
        # Create a directory we can scan
        accessible = tmp_path / "accessible" / "node_modules"
        accessible.mkdir(parents=True)

        # Mock permission error for another directory
        with patch("os.scandir") as mock_scandir:
            # First call works, second raises PermissionError
            mock_scandir.side_effect = PermissionError("Access denied")

            # Should not raise, just return empty
            results = list(find_matching_directories(tmp_path, "node_modules"))
            assert len(results) == 0

    def test_respects_max_depth(self, tmp_path):
        """Respect maximum depth limit."""
        # Create deeply nested structure
        deep = tmp_path
        for i in range(20):
            deep = deep / f"level{i}"
        node_modules = deep / "node_modules"
        node_modules.mkdir(parents=True)

        # With max_depth=5, should not find it
        results = list(find_matching_directories(tmp_path, "node_modules", max_depth=5))
        assert len(results) == 0

        # With higher max_depth, should find it
        results = list(find_matching_directories(tmp_path, "node_modules", max_depth=25))
        assert len(results) == 1

    def test_finds_hidden_directories(self, tmp_path):
        """Find .venv directories (hidden)."""
        venv = tmp_path / "project" / ".venv"
        venv.mkdir(parents=True)

        results = list(find_matching_directories(tmp_path, ".venv"))
        assert len(results) == 1
        assert results[0] == venv


class TestScanRecursiveCategory:
    @pytest.fixture
    def node_modules_category(self):
        return Category(
            id="node_modules",
            name="Node Modules",
            paths=[],
            glob_patterns=["**/node_modules"],
            search_roots=["PLACEHOLDER"],  # Will be replaced in tests
            is_recursive=True,
            min_size_bytes=0,  # No minimum for tests
            risk_level=RiskLevel.SAFE,
            description="Node.js dependencies",
            consequences="Reinstall with npm",
            recovery="npm install",
        )

    def test_scans_recursive_category(self, tmp_path, node_modules_category):
        """Scan a recursive category and return results."""
        # Create node_modules with some content
        node_modules = tmp_path / "project" / "node_modules"
        node_modules.mkdir(parents=True)
        (node_modules / "react" / "index.js").parent.mkdir()
        (node_modules / "react" / "index.js").write_text("module.exports = {}")

        # Update search roots to use tmp_path
        node_modules_category.search_roots = [str(tmp_path)]

        results = scan_recursive_category(node_modules_category)
        assert len(results) == 1
        assert results[0].category_id == "node_modules"
        assert results[0].size_bytes > 0

    def test_respects_min_size(self, tmp_path, node_modules_category):
        """Skip directories below minimum size."""
        # Create small node_modules
        node_modules = tmp_path / "project" / "node_modules"
        node_modules.mkdir(parents=True)
        (node_modules / "tiny.txt").write_text("x")  # Very small

        node_modules_category.search_roots = [str(tmp_path)]
        node_modules_category.min_size_bytes = 1024 * 1024  # 1MB minimum

        results = scan_recursive_category(node_modules_category)
        assert len(results) == 0  # Too small

    def test_returns_empty_for_non_recursive(self, tmp_path):
        """Return empty for non-recursive categories."""
        category = Category(
            id="test",
            name="Test",
            paths=["~/test"],
            is_recursive=False,
            risk_level=RiskLevel.SAFE,
            description="Test",
            consequences="Test",
            recovery="Test",
        )

        results = scan_recursive_category(category)
        assert results == []

    def test_avoids_duplicates(self, tmp_path, node_modules_category):
        """Avoid duplicate results from overlapping search roots."""
        node_modules = tmp_path / "project" / "node_modules"
        node_modules.mkdir(parents=True)

        # Use overlapping search roots
        node_modules_category.search_roots = [
            str(tmp_path),
            str(tmp_path / "project"),  # Overlaps with tmp_path
        ]

        results = scan_recursive_category(node_modules_category)
        # Should only find it once despite overlapping roots
        assert len(results) == 1

    def test_calls_progress_callback(self, tmp_path, node_modules_category):
        """Call progress callback for each found directory."""
        node_modules = tmp_path / "project" / "node_modules"
        node_modules.mkdir(parents=True)
        (node_modules / "test.js").write_text("test")

        node_modules_category.search_roots = [str(tmp_path)]

        callbacks = []

        def track_callback(path, size):
            callbacks.append((path, size))

        scan_recursive_category(node_modules_category, progress_callback=track_callback)
        assert len(callbacks) == 1
        assert callbacks[0][1] > 0  # Size should be positive


class TestAggregateRecursiveResults:
    def test_aggregates_multiple_results(self):
        """Aggregate multiple scan results into one summary."""
        from uncruft.models import ScanResult

        category = Category(
            id="node_modules",
            name="Node Modules",
            paths=[],
            is_recursive=True,
            risk_level=RiskLevel.SAFE,
            description="Test",
            consequences="Test",
            recovery="Test",
        )

        results = [
            ScanResult(
                category_id="node_modules",
                category_name="Node Modules",
                path="/path/project1/node_modules",
                size_bytes=100_000_000,
                file_count=1000,
                dir_count=100,
                risk_level=RiskLevel.SAFE,
                exists=True,
            ),
            ScanResult(
                category_id="node_modules",
                category_name="Node Modules",
                path="/path/project2/node_modules",
                size_bytes=50_000_000,
                file_count=500,
                dir_count=50,
                risk_level=RiskLevel.SAFE,
                exists=True,
            ),
        ]

        aggregated = aggregate_recursive_results(results, category)

        assert aggregated is not None
        assert aggregated.size_bytes == 150_000_000
        assert aggregated.file_count == 1500
        assert aggregated.dir_count == 150
        assert "2 found" in aggregated.category_name
        assert "+1 more" in aggregated.path

    def test_returns_none_for_empty_results(self):
        """Return None for empty results."""
        category = Category(
            id="test",
            name="Test",
            paths=[],
            is_recursive=True,
            risk_level=RiskLevel.SAFE,
            description="Test",
            consequences="Test",
            recovery="Test",
        )

        aggregated = aggregate_recursive_results([], category)
        assert aggregated is None

    def test_single_result_no_more_text(self):
        """Single result shouldn't have '+X more' text."""
        from uncruft.models import ScanResult

        category = Category(
            id="node_modules",
            name="Node Modules",
            paths=[],
            is_recursive=True,
            risk_level=RiskLevel.SAFE,
            description="Test",
            consequences="Test",
            recovery="Test",
        )

        results = [
            ScanResult(
                category_id="node_modules",
                category_name="Node Modules",
                path="/path/project/node_modules",
                size_bytes=100_000_000,
                file_count=1000,
                dir_count=100,
                risk_level=RiskLevel.SAFE,
                exists=True,
            ),
        ]

        aggregated = aggregate_recursive_results(results, category)

        assert aggregated is not None
        assert "+0 more" not in aggregated.path
        assert aggregated.path == "/path/project/node_modules"
