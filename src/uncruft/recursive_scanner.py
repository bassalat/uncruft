"""Recursive directory discovery for developer artifacts.

This module provides functionality to find directories matching patterns
(like node_modules, .venv, __pycache__) recursively across the filesystem.
"""

import os
from pathlib import Path
from typing import Callable, Generator

from uncruft.models import Category, ScanResult
from uncruft.scanner import expand_path, get_directory_size


# Directories to skip during recursive scanning (performance + safety)
SKIP_DIRECTORIES = frozenset(
    {
        ".git",
        ".svn",
        ".hg",
        "Library",  # macOS system library
        "Applications",
        ".Trash",
        "node_modules",  # Don't recurse INTO node_modules looking for more
        ".venv",
        "venv",
        "__pycache__",
    }
)


def find_matching_directories(
    root: Path,
    pattern: str,
    max_depth: int = 15,
    skip_inside_match: bool = True,
) -> Generator[Path, None, None]:
    """
    Find directories matching a pattern recursively.

    Uses os.scandir for performance instead of pathlib.glob().

    Args:
        root: Root directory to start searching from
        pattern: Directory name to match (e.g., 'node_modules', '.venv')
        max_depth: Maximum depth to search (prevents infinite recursion)
        skip_inside_match: If True, don't recurse into matched directories

    Yields:
        Paths to matching directories
    """
    if max_depth <= 0:
        return

    try:
        with os.scandir(root) as entries:
            for entry in entries:
                try:
                    # Skip non-directories and symlinks
                    if not entry.is_dir(follow_symlinks=False):
                        continue

                    name = entry.name

                    # Skip hidden directories (except the ones we're looking for)
                    if name.startswith(".") and name != pattern:
                        # But don't skip .venv if we're looking for .venv
                        if name not in (".venv", ".virtualenv") or pattern not in (
                            ".venv",
                            ".virtualenv",
                        ):
                            continue

                    # Skip known unproductive directories
                    if name in SKIP_DIRECTORIES and name != pattern:
                        continue

                    entry_path = Path(entry.path)

                    # Found a match!
                    if name == pattern:
                        yield entry_path
                        # Don't recurse into the match (no node_modules inside node_modules)
                        if skip_inside_match:
                            continue

                    # Recurse into subdirectories
                    yield from find_matching_directories(
                        entry_path,
                        pattern,
                        max_depth - 1,
                        skip_inside_match,
                    )

                except (PermissionError, OSError):
                    # Skip directories we can't access
                    continue

    except (PermissionError, OSError):
        # Skip roots we can't access
        return


def scan_recursive_category(
    category: Category,
    progress_callback: Callable[[str, int], None] | None = None,
) -> list[ScanResult]:
    """
    Scan a category that uses recursive pattern matching.

    Args:
        category: Category with is_recursive=True, glob_patterns, and search_roots
        progress_callback: Optional callback(path, size_bytes) for each found directory

    Returns:
        List of ScanResults, one per found directory
    """
    if not category.is_recursive:
        return []

    results: list[ScanResult] = []
    seen_paths: set[str] = set()  # Avoid duplicates

    for search_root in category.search_roots:
        root_path = expand_path(search_root)
        if not root_path.exists() or not root_path.is_dir():
            continue

        for pattern in category.glob_patterns:
            # Extract the directory name from pattern (e.g., '**/node_modules' -> 'node_modules')
            pattern_name = pattern.replace("**/", "").replace("*/", "").strip("/")

            for found_dir in find_matching_directories(root_path, pattern_name):
                # Skip duplicates (can happen with overlapping search roots)
                dir_str = str(found_dir)
                if dir_str in seen_paths:
                    continue
                seen_paths.add(dir_str)

                # Calculate size
                try:
                    size, file_count, dir_count = get_directory_size(found_dir)
                except (PermissionError, OSError):
                    continue

                # Skip if below minimum size threshold
                if size < category.min_size_bytes:
                    continue

                result = ScanResult(
                    category_id=category.id,
                    category_name=category.name,
                    path=dir_str,
                    size_bytes=size,
                    file_count=file_count,
                    dir_count=dir_count,
                    risk_level=category.risk_level,
                    exists=True,
                )
                results.append(result)

                if progress_callback:
                    progress_callback(dir_str, size)

    # Sort by size descending
    results.sort(key=lambda r: r.size_bytes, reverse=True)
    return results


def aggregate_recursive_results(
    results: list[ScanResult], category: Category
) -> ScanResult | None:
    """
    Aggregate multiple recursive scan results into a single summary result.

    Args:
        results: List of individual ScanResults from recursive scanning
        category: The category being aggregated

    Returns:
        Single ScanResult summarizing all found directories
    """
    if not results:
        return None

    total_size = sum(r.size_bytes for r in results)
    total_files = sum(r.file_count for r in results)
    total_dirs = sum(r.dir_count for r in results)
    found_count = len(results)

    # Use the largest directory's path for display, with count
    largest = max(results, key=lambda r: r.size_bytes)
    display_path = f"{largest.path} (+{found_count - 1} more)" if found_count > 1 else largest.path

    return ScanResult(
        category_id=category.id,
        category_name=f"{category.name} ({found_count} found)",
        path=display_path,
        size_bytes=total_size,
        file_count=total_files,
        dir_count=total_dirs,
        risk_level=category.risk_level,
        exists=True,
    )
