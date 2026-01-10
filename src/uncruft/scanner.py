"""Disk scanning functionality for uncruft."""

import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from uncruft.categories import CATEGORIES, get_all_categories
from uncruft.models import Category, DiskUsage, RiskLevel, ScanResult


# =============================================================================
# Performance: Directory Size Cache
# =============================================================================

_size_cache: dict[str, tuple[int, int, int, float]] = {}
CACHE_TTL = 300  # 5 minutes


def clear_size_cache():
    """Clear the directory size cache."""
    _size_cache.clear()


def expand_path(path: str) -> Path:
    """Expand ~ and environment variables in path."""
    return Path(os.path.expanduser(os.path.expandvars(path)))


def get_directory_size_fast(path: Path, max_depth: int = 20) -> tuple[int, int, int]:
    """
    Fast directory size calculation using os.scandir with depth limit.

    This is 2-10x faster than rglob("*") for large directories.

    Args:
        path: Directory to scan
        max_depth: Maximum recursion depth (default: 20)

    Returns:
        Tuple of (total_bytes, file_count, dir_count)
    """
    total_size = 0
    file_count = 0
    dir_count = 0

    def _scan(p: Path, depth: int):
        nonlocal total_size, file_count, dir_count
        if depth > max_depth:
            return
        try:
            with os.scandir(p) as entries:
                for entry in entries:
                    try:
                        if entry.is_file(follow_symlinks=False):
                            total_size += entry.stat().st_size
                            file_count += 1
                        elif entry.is_dir(follow_symlinks=False):
                            dir_count += 1
                            _scan(Path(entry.path), depth + 1)
                    except (PermissionError, OSError):
                        continue
        except (PermissionError, OSError):
            pass

    _scan(path, 0)
    return total_size, file_count, dir_count


def get_directory_size_cached(path: Path, max_depth: int = 20) -> tuple[int, int, int]:
    """
    Cached directory size calculation.

    Returns cached result if available and fresh (within CACHE_TTL).

    Args:
        path: Directory to scan
        max_depth: Maximum recursion depth

    Returns:
        Tuple of (total_bytes, file_count, dir_count)
    """
    key = str(path)
    now = time.time()

    if key in _size_cache:
        size, files, dirs, cached_at = _size_cache[key]
        if now - cached_at < CACHE_TTL:
            return size, files, dirs

    size, files, dirs = get_directory_size_fast(path, max_depth)
    _size_cache[key] = (size, files, dirs, now)
    return size, files, dirs


def get_directory_size(path: Path) -> tuple[int, int, int]:
    """
    Calculate total size of a directory.

    Uses fast cached implementation for performance.

    Returns:
        Tuple of (total_bytes, file_count, dir_count)
    """
    return get_directory_size_cached(path)


def scan_path(path: str, category: Category) -> ScanResult:
    """
    Scan a single path and return the result.

    Args:
        path: Path to scan (may contain ~)
        category: Category this path belongs to

    Returns:
        ScanResult with size and metadata
    """
    expanded_path = expand_path(path)

    if not expanded_path.exists():
        return ScanResult(
            category_id=category.id,
            category_name=category.name,
            path=str(expanded_path),
            size_bytes=0,
            file_count=0,
            dir_count=0,
            risk_level=category.risk_level,
            exists=False,
        )

    try:
        if expanded_path.is_file():
            size = expanded_path.stat().st_size
            return ScanResult(
                category_id=category.id,
                category_name=category.name,
                path=str(expanded_path),
                size_bytes=size,
                file_count=1,
                dir_count=0,
                risk_level=category.risk_level,
                exists=True,
            )
        elif expanded_path.is_dir():
            size, file_count, dir_count = get_directory_size(expanded_path)
            return ScanResult(
                category_id=category.id,
                category_name=category.name,
                path=str(expanded_path),
                size_bytes=size,
                file_count=file_count,
                dir_count=dir_count,
                risk_level=category.risk_level,
                exists=True,
            )
        else:
            return ScanResult(
                category_id=category.id,
                category_name=category.name,
                path=str(expanded_path),
                size_bytes=0,
                file_count=0,
                dir_count=0,
                risk_level=category.risk_level,
                exists=False,
            )
    except (PermissionError, OSError) as e:
        return ScanResult(
            category_id=category.id,
            category_name=category.name,
            path=str(expanded_path),
            size_bytes=0,
            file_count=0,
            dir_count=0,
            risk_level=category.risk_level,
            exists=True,
            error=str(e),
        )


def scan_category(category: Category) -> list[ScanResult]:
    """
    Scan all paths in a category.

    Args:
        category: Category to scan

    Returns:
        List of ScanResults for each path in the category
    """
    # Special handling for Docker - use CLI instead of directory scan
    # The VM disk file is much larger than actual Docker usage
    if category.id == "docker_data":
        return _scan_docker_category(category)

    results = []
    for path in category.paths:
        result = scan_path(path, category)
        results.append(result)
    return results


def _scan_docker_category(category: Category) -> list[ScanResult]:
    """
    Scan Docker using CLI for accurate size.

    Docker Desktop on macOS uses a VM with a virtual disk file that grows
    but doesn't shrink. Scanning the directory shows the VM disk size,
    not actual Docker usage. This function uses the Docker CLI instead.
    """
    try:
        breakdown = get_docker_breakdown()
        if breakdown.get("available"):
            return [ScanResult(
                category_id=category.id,
                category_name=category.name,
                path="Docker Desktop",
                size_bytes=breakdown.get("total_bytes", 0),
                file_count=len(breakdown.get("images", [])),
                dir_count=len(breakdown.get("containers", [])),
                risk_level=category.risk_level,
                exists=True,
            )]
    except Exception:
        pass

    # Fallback to path scan if Docker not available
    results = []
    for path in category.paths:
        result = scan_path(path, category)
        results.append(result)
    return results


def aggregate_category_results(results: list[ScanResult]) -> ScanResult | None:
    """
    Aggregate multiple scan results for the same category into one.

    Args:
        results: List of scan results from the same category

    Returns:
        Single aggregated ScanResult, or None if no results
    """
    if not results:
        return None

    # Use the first result as template
    first = results[0]

    # Find the first existing path for display
    existing_paths = [r.path for r in results if r.exists and r.size_bytes > 0]
    display_path = existing_paths[0] if existing_paths else first.path

    total_size = sum(r.size_bytes for r in results)
    total_files = sum(r.file_count for r in results)
    total_dirs = sum(r.dir_count for r in results)
    any_exists = any(r.exists for r in results)
    errors = [r.error for r in results if r.error]

    return ScanResult(
        category_id=first.category_id,
        category_name=first.category_name,
        path=display_path,
        size_bytes=total_size,
        file_count=total_files,
        dir_count=total_dirs,
        risk_level=first.risk_level,
        exists=any_exists,
        error="; ".join(errors) if errors else None,
    )


def scan_all_categories(
    progress_callback: Callable[[str, int, int], None] | None = None,
    max_workers: int = 4,
    include_dev: bool = False,
) -> list[ScanResult]:
    """
    Scan all categories in parallel.

    Args:
        progress_callback: Optional callback(category_name, current, total)
        max_workers: Number of parallel workers
        include_dev: If True, include recursive developer categories (slower)

    Returns:
        List of aggregated ScanResults (one per category)
    """
    categories = get_all_categories()

    # Separate regular and recursive categories
    regular_categories = [c for c in categories if not c.is_recursive]
    recursive_categories = [c for c in categories if c.is_recursive]

    results: list[ScanResult] = []

    # Scan regular categories in parallel
    regular_total = len(regular_categories)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_category = {
            executor.submit(scan_category, cat): cat for cat in regular_categories
        }

        for i, future in enumerate(as_completed(future_to_category)):
            category = future_to_category[future]

            if progress_callback:
                progress_callback(category.name, i + 1, regular_total)

            try:
                category_results = future.result()
                aggregated = aggregate_category_results(category_results)
                if aggregated:
                    results.append(aggregated)
            except Exception as e:
                results.append(
                    ScanResult(
                        category_id=category.id,
                        category_name=category.name,
                        path=category.paths[0] if category.paths else "",
                        size_bytes=0,
                        file_count=0,
                        dir_count=0,
                        risk_level=category.risk_level,
                        exists=False,
                        error=str(e),
                    )
                )

    # Scan recursive developer categories if requested
    if include_dev and recursive_categories:
        from uncruft.recursive_scanner import (
            aggregate_recursive_results,
            scan_recursive_category,
        )

        for i, category in enumerate(recursive_categories):
            if progress_callback:
                progress_callback(
                    f"Scanning {category.name}...",
                    regular_total + i + 1,
                    regular_total + len(recursive_categories),
                )

            try:
                recursive_results = scan_recursive_category(category)
                if recursive_results:
                    # Add aggregated summary
                    aggregated = aggregate_recursive_results(recursive_results, category)
                    if aggregated:
                        results.append(aggregated)
            except Exception as e:
                results.append(
                    ScanResult(
                        category_id=category.id,
                        category_name=category.name,
                        path=category.search_roots[0] if category.search_roots else "",
                        size_bytes=0,
                        file_count=0,
                        dir_count=0,
                        risk_level=category.risk_level,
                        exists=False,
                        error=str(e),
                    )
                )

    # Sort by size descending
    results.sort(key=lambda r: r.size_bytes, reverse=True)
    return results


def get_disk_usage(mount_point: str = "/") -> DiskUsage:
    """
    Get overall disk usage for a mount point.

    Uses APFS container size to match macOS System Settings.

    Args:
        mount_point: Mount point to check (default: /)

    Returns:
        DiskUsage with total, used, and free bytes
    """
    # Try to get APFS container size (matches macOS System Settings)
    try:
        import subprocess
        result = subprocess.run(
            ["diskutil", "info", mount_point],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            total_bytes = None
            free_bytes = None

            for line in result.stdout.split("\n"):
                if "Container Total Space:" in line:
                    # Parse: "Container Total Space:     245.1 GB (245107195904 Bytes)"
                    match = line.split("(")
                    if len(match) >= 2:
                        bytes_str = match[1].split()[0]
                        total_bytes = int(bytes_str)
                elif "Container Free Space:" in line:
                    match = line.split("(")
                    if len(match) >= 2:
                        bytes_str = match[1].split()[0]
                        free_bytes = int(bytes_str)

            if total_bytes and free_bytes:
                return DiskUsage(
                    total_bytes=total_bytes,
                    used_bytes=total_bytes - free_bytes,
                    free_bytes=free_bytes,
                    mount_point=mount_point,
                )
    except Exception:
        pass

    # Fallback to shutil (works on non-APFS systems)
    usage = shutil.disk_usage(mount_point)
    return DiskUsage(
        total_bytes=usage.total,
        used_bytes=usage.used,
        free_bytes=usage.free,
        mount_point=mount_point,
    )


def quick_scan(category_ids: list[str] | None = None) -> list[ScanResult]:
    """
    Quick scan of specific categories (or all if None).

    Args:
        category_ids: List of category IDs to scan, or None for all

    Returns:
        List of ScanResults
    """
    if category_ids is None:
        return scan_all_categories()

    results = []
    for cat_id in category_ids:
        category = CATEGORIES.get(cat_id)
        if category:
            category_results = scan_category(category)
            aggregated = aggregate_category_results(category_results)
            if aggregated:
                results.append(aggregated)

    results.sort(key=lambda r: r.size_bytes, reverse=True)
    return results


# =============================================================================
# New comprehensive tools
# =============================================================================


def find_large_files(
    min_size_mb: int = 100,
    path: str = "~",
    max_results: int = 50,
) -> list[dict]:
    """
    Find files larger than min_size_mb.

    Args:
        min_size_mb: Minimum file size in MB (default: 100)
        path: Path to search (default: home directory)
        max_results: Maximum number of results to return

    Returns:
        List of dicts with path, size_bytes, size_human
    """
    min_size_bytes = min_size_mb * 1024 * 1024
    expanded_path = expand_path(path)
    large_files = []

    if not expanded_path.exists():
        return []

    try:
        for entry in expanded_path.rglob("*"):
            try:
                if entry.is_file() and not entry.is_symlink():
                    size = entry.stat().st_size
                    if size >= min_size_bytes:
                        large_files.append({
                            "path": str(entry),
                            "size_bytes": size,
                            "size_human": _format_size(size),
                        })
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        pass

    # Sort by size descending and limit results
    large_files.sort(key=lambda x: x["size_bytes"], reverse=True)
    return large_files[:max_results]


def analyze_directory(path: str, max_depth: int = 2) -> dict:
    """
    Get size breakdown of a directory.

    Args:
        path: Directory to analyze
        max_depth: Maximum depth to show (default: 2)

    Returns:
        Dict with total size and breakdown by subdirectory
    """
    expanded_path = expand_path(path)

    if not expanded_path.exists():
        return {"error": f"Path does not exist: {path}"}

    if not expanded_path.is_dir():
        size = expanded_path.stat().st_size
        return {
            "path": str(expanded_path),
            "total_size_bytes": size,
            "total_size_human": _format_size(size),
            "is_file": True,
        }

    # Get total size
    total_size, total_files, total_dirs = get_directory_size(expanded_path)

    # Get breakdown by immediate children
    children = []
    try:
        for entry in expanded_path.iterdir():
            try:
                if entry.is_dir():
                    size, files, dirs = get_directory_size(entry)
                else:
                    size = entry.stat().st_size if entry.is_file() else 0
                    files = 1 if entry.is_file() else 0
                    dirs = 0

                if size > 0:
                    children.append({
                        "name": entry.name,
                        "path": str(entry),
                        "size_bytes": size,
                        "size_human": _format_size(size),
                        "is_dir": entry.is_dir(),
                    })
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        pass

    # Sort by size descending
    children.sort(key=lambda x: x["size_bytes"], reverse=True)

    return {
        "path": str(expanded_path),
        "total_size_bytes": total_size,
        "total_size_human": _format_size(total_size),
        "file_count": total_files,
        "dir_count": total_dirs,
        "children": children[:20],  # Top 20 children
    }


def find_old_files(
    days: int = 180,
    path: str = "~/Downloads",
    max_results: int = 50,
) -> list[dict]:
    """
    Find files not accessed in X days.

    Args:
        days: Number of days since last access (default: 180)
        path: Path to search (default: ~/Downloads)
        max_results: Maximum number of results to return

    Returns:
        List of dicts with path, size, last_accessed
    """
    import time

    expanded_path = expand_path(path)
    cutoff_time = time.time() - (days * 24 * 60 * 60)
    old_files = []

    if not expanded_path.exists():
        return []

    try:
        for entry in expanded_path.rglob("*"):
            try:
                if entry.is_file() and not entry.is_symlink():
                    stat = entry.stat()
                    if stat.st_atime < cutoff_time:
                        old_files.append({
                            "path": str(entry),
                            "size_bytes": stat.st_size,
                            "size_human": _format_size(stat.st_size),
                            "last_accessed_days": int((time.time() - stat.st_atime) / (24 * 60 * 60)),
                        })
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        pass

    # Sort by size descending
    old_files.sort(key=lambda x: x["size_bytes"], reverse=True)
    return old_files[:max_results]


def _format_size(size_bytes: int) -> str:
    """Format bytes as human-readable string (decimal units like macOS)."""
    # Use decimal units (1000) to match macOS System Settings
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1000:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1000
    return f"{size_bytes:.1f} PB"


# Whitelisted commands for run_command
ALLOWED_COMMANDS = {
    "docker images",
    "docker system df",
    "docker system df -v",
    "docker ps -a",
    "docker volume ls",
    "brew cleanup --dry-run",
    "brew list --cask",
    "git gc --dry-run",
}

# Commands that require confirmation (destructive)
DESTRUCTIVE_COMMANDS = {
    "docker system prune -a",
    "docker system prune",
    "docker builder prune -a",
    "docker builder prune",
    "docker volume prune",
    "brew cleanup",
    "git gc",
}


def run_command(command: str) -> dict:
    """
    Run a whitelisted shell command.

    Args:
        command: Command to run (must be in whitelist)

    Returns:
        Dict with success, output, and error fields
    """
    import subprocess

    # Normalize command
    cmd = command.strip()

    # Check if command is allowed
    if cmd not in ALLOWED_COMMANDS and cmd not in DESTRUCTIVE_COMMANDS:
        return {
            "success": False,
            "error": f"Command not allowed: {cmd}",
            "allowed_commands": list(ALLOWED_COMMANDS | DESTRUCTIVE_COMMANDS),
        }

    # Check if destructive (caller should confirm)
    is_destructive = cmd in DESTRUCTIVE_COMMANDS

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return {
            "success": result.returncode == 0,
            "command": cmd,
            "output": result.stdout,
            "error": result.stderr if result.returncode != 0 else None,
            "is_destructive": is_destructive,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "command": cmd,
            "error": "Command timed out after 60 seconds",
        }
    except Exception as e:
        return {
            "success": False,
            "command": cmd,
            "error": str(e),
        }


def find_mail_attachments(days: int = 365) -> list[dict]:
    """
    Find old Mail.app attachments.

    Args:
        days: Find attachments older than this many days

    Returns:
        List of attachment files with paths and sizes
    """
    import time

    mail_path = expand_path("~/Library/Mail")
    cutoff_time = time.time() - (days * 24 * 60 * 60)
    attachments = []

    if not mail_path.exists():
        return []

    # Look for attachments in Mail directories
    try:
        for entry in mail_path.rglob("Attachments/*"):
            try:
                if entry.is_file():
                    stat = entry.stat()
                    if stat.st_mtime < cutoff_time:
                        attachments.append({
                            "path": str(entry),
                            "name": entry.name,
                            "size_bytes": stat.st_size,
                            "size_human": _format_size(stat.st_size),
                            "age_days": int((time.time() - stat.st_mtime) / (24 * 60 * 60)),
                        })
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        pass

    attachments.sort(key=lambda x: x["size_bytes"], reverse=True)
    return attachments


# App data locations for uninstall_app
APP_DATA_LOCATIONS = [
    "~/Library/Application Support/{app}",
    "~/Library/Preferences/*{app}*",
    "~/Library/Preferences/com.{app}*.plist",
    "~/Library/Caches/{app}",
    "~/Library/Caches/com.{app}*",
    "~/Library/Logs/{app}",
    "~/Library/Cookies/{app}*",
    "~/Library/WebKit/{app}",
    "~/Library/Saved Application State/*{app}*",
    "~/Library/LaunchAgents/*{app}*",
    "~/Library/Containers/{app}*",
    "~/Library/Containers/com.{app}*",
    "~/Library/Group Containers/*{app}*",
    "/Applications/{app}.app",
]


def find_app_data(app_name: str) -> list[dict]:
    """
    Find all data associated with an app.

    Args:
        app_name: Name of the app (e.g., "Slack", "Spotify")

    Returns:
        List of paths with sizes that belong to this app
    """
    import glob

    app_data = []
    app_lower = app_name.lower()

    for pattern in APP_DATA_LOCATIONS:
        # Replace {app} with app name
        expanded_pattern = pattern.replace("{app}", app_name)
        expanded_pattern = os.path.expanduser(expanded_pattern)

        # Find matching paths
        for path_str in glob.glob(expanded_pattern):
            path = Path(path_str)
            try:
                if path.exists():
                    if path.is_dir():
                        size, files, dirs = get_directory_size(path)
                    else:
                        size = path.stat().st_size
                        files = 1
                        dirs = 0

                    if size > 0:
                        app_data.append({
                            "path": str(path),
                            "size_bytes": size,
                            "size_human": _format_size(size),
                            "is_dir": path.is_dir(),
                        })
            except (PermissionError, OSError):
                continue

    # Also try lowercase version
    if app_name != app_lower:
        for pattern in APP_DATA_LOCATIONS:
            expanded_pattern = pattern.replace("{app}", app_lower)
            expanded_pattern = os.path.expanduser(expanded_pattern)

            for path_str in glob.glob(expanded_pattern):
                path = Path(path_str)
                # Skip if already found
                if any(d["path"] == str(path) for d in app_data):
                    continue
                try:
                    if path.exists():
                        if path.is_dir():
                            size, files, dirs = get_directory_size(path)
                        else:
                            size = path.stat().st_size
                            files = 1
                            dirs = 0

                        if size > 0:
                            app_data.append({
                                "path": str(path),
                                "size_bytes": size,
                                "size_human": _format_size(size),
                                "is_dir": path.is_dir(),
                            })
                except (PermissionError, OSError):
                    continue

    app_data.sort(key=lambda x: x["size_bytes"], reverse=True)
    total_size = sum(d["size_bytes"] for d in app_data)

    return {
        "app_name": app_name,
        "paths": app_data,
        "total_size_bytes": total_size,
        "total_size_human": _format_size(total_size),
        "path_count": len(app_data),
    }


def uninstall_app(app_name: str, dry_run: bool = False) -> dict:
    """
    Remove an app and all its associated data.

    Args:
        app_name: Name of the app to uninstall
        dry_run: If True, just report what would be deleted

    Returns:
        Dict with deleted paths and total freed space
    """
    app_data = find_app_data(app_name)

    if not app_data["paths"]:
        return {
            "success": False,
            "error": f"No data found for app: {app_name}",
        }

    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "app_name": app_name,
            "would_delete": app_data["paths"],
            "would_free_bytes": app_data["total_size_bytes"],
            "would_free_human": app_data["total_size_human"],
        }

    # Actually delete
    deleted = []
    errors = []
    freed_bytes = 0

    for item in app_data["paths"]:
        path = Path(item["path"])
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            deleted.append(item["path"])
            freed_bytes += item["size_bytes"]
        except (PermissionError, OSError) as e:
            errors.append({"path": item["path"], "error": str(e)})

    return {
        "success": len(errors) == 0,
        "app_name": app_name,
        "deleted": deleted,
        "errors": errors,
        "freed_bytes": freed_bytes,
        "freed_human": _format_size(freed_bytes),
    }


# =============================================================================
# Storage breakdown and applications (macOS-style)
# =============================================================================


# Storage categories like macOS Settings
STORAGE_CATEGORIES = {
    "applications": {
        "name": "Applications",
        "paths": ["/Applications", "~/Applications"],
        "icon": "📦",
    },
    "documents": {
        "name": "Documents",
        "paths": ["~/Documents"],
        "icon": "📄",
    },
    "downloads": {
        "name": "Downloads",
        "paths": ["~/Downloads"],
        "icon": "⬇️",
    },
    "photos": {
        "name": "Photos",
        "paths": ["~/Pictures", "~/Library/Photos"],
        "icon": "🖼️",
    },
    "music": {
        "name": "Music",
        "paths": ["~/Music"],
        "icon": "🎵",
    },
    "movies": {
        "name": "Movies",
        "paths": ["~/Movies"],
        "icon": "🎬",
    },
    "mail": {
        "name": "Mail",
        "paths": ["~/Library/Mail"],
        "icon": "📧",
    },
    "messages": {
        "name": "Messages",
        "paths": ["~/Library/Messages"],
        "icon": "💬",
    },
    "developer": {
        "name": "Developer",
        "paths": [
            "~/Library/Developer",
            "~/.npm",
            "~/.cargo",
            "~/.rustup",
            "~/.gradle",
            "~/.m2",
            "~/.conda",
            "~/.docker",
            "~/go",
        ],
        "icon": "🛠️",
    },
    "icloud": {
        "name": "iCloud Drive",
        "paths": ["~/Library/Mobile Documents"],
        "icon": "☁️",
    },
    "library": {
        "name": "Library (Caches & Data)",
        "paths": ["~/Library/Caches", "~/Library/Application Support"],
        "icon": "📚",
    },
}


def get_storage_breakdown() -> dict:
    """
    Get storage breakdown by category like macOS Settings.

    Uses parallel scanning for better performance.

    Returns:
        Dict with disk status and breakdown by category
    """
    disk = get_disk_usage()

    # Collect all paths to scan with their category info
    scan_tasks = []
    for cat_id, cat_info in STORAGE_CATEGORIES.items():
        for path_str in cat_info["paths"]:
            path = expand_path(path_str)
            if path.exists():
                scan_tasks.append({
                    "cat_id": cat_id,
                    "cat_info": cat_info,
                    "path": path,
                })

    # Scan all paths in parallel
    path_results = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(get_directory_size_cached, task["path"]): task
            for task in scan_tasks
        }
        for future in as_completed(futures):
            task = futures[future]
            try:
                size, files, dirs = future.result()
                path_results[str(task["path"])] = {
                    "size": size,
                    "cat_id": task["cat_id"],
                    "cat_info": task["cat_info"],
                    "path": task["path"],
                }
            except Exception:
                pass

    # Aggregate results by category
    category_totals = {}
    for path_str, result in path_results.items():
        cat_id = result["cat_id"]
        if cat_id not in category_totals:
            category_totals[cat_id] = {
                "info": result["cat_info"],
                "size": 0,
                "primary_path": str(result["path"]),
            }
        category_totals[cat_id]["size"] += result["size"]

    # Build categories list
    categories = []
    accounted_bytes = 0
    for cat_id, data in category_totals.items():
        if data["size"] > 0:
            categories.append({
                "id": cat_id,
                "name": data["info"]["name"],
                "icon": data["info"]["icon"],
                "size_bytes": data["size"],
                "size_human": _format_size(data["size"]),
                "percent": round(data["size"] / disk.used_bytes * 100, 1) if disk.used_bytes > 0 else 0,
                "path": data["primary_path"],
            })
            accounted_bytes += data["size"]

    # Calculate "Other" (system + unaccounted)
    other_bytes = disk.used_bytes - accounted_bytes
    if other_bytes > 0:
        categories.append({
            "id": "other",
            "name": "System & Other",
            "icon": "⚙️",
            "size_bytes": other_bytes,
            "size_human": _format_size(other_bytes),
            "percent": round(other_bytes / disk.used_bytes * 100, 1) if disk.used_bytes > 0 else 0,
            "path": None,
        })

    # Sort by size descending
    categories.sort(key=lambda x: x["size_bytes"], reverse=True)

    return {
        "disk": {
            "total_bytes": disk.total_bytes,
            "total_human": _format_size(disk.total_bytes),
            "used_bytes": disk.used_bytes,
            "used_human": _format_size(disk.used_bytes),
            "free_bytes": disk.free_bytes,
            "free_human": _format_size(disk.free_bytes),
            "used_percent": disk.used_percent,
        },
        "categories": categories,
        "category_count": len(categories),
    }


# System paths that contribute to "System & Other"
SYSTEM_PATHS = [
    {"path": "/System", "name": "macOS System", "description": "Core operating system files"},
    {"path": "/Library", "name": "System Library", "description": "System-wide app support & caches"},
    {"path": "/private/var", "name": "System Data", "description": "Logs, caches, temp files"},
    {"path": "/usr", "name": "Unix Utilities", "description": "Unix programs and libraries"},
    {"path": "/bin", "name": "System Binaries", "description": "Essential command-line tools"},
    {"path": "/sbin", "name": "System Admin", "description": "System administration tools"},
    {"path": "/opt", "name": "Optional Software", "description": "Third-party packages (Homebrew)"},
    {"path": "~/.Trash", "name": "Trash", "description": "Deleted files (can be emptied)"},
    {"path": "~/Library/Mail", "name": "Mail Data", "description": "Email messages and attachments"},
    {"path": "~/Library/Messages", "name": "Messages Data", "description": "iMessage history and attachments"},
    {"path": "~/Library/Containers", "name": "App Containers", "description": "Sandboxed app data"},
    {"path": "~/Library/Group Containers", "name": "Shared App Data", "description": "Data shared between apps"},
]


def get_system_other_breakdown() -> dict:
    """
    Get breakdown of paths that contribute to 'System & Other'.

    Returns:
        Dict with list of system paths and their sizes
    """
    paths = []
    total_scanned = 0

    # Scan system paths in parallel
    scan_tasks = []
    for item in SYSTEM_PATHS:
        path = expand_path(item["path"])
        if path.exists():
            scan_tasks.append({
                "path": path,
                "name": item["name"],
                "description": item["description"],
            })

    # Parallel scanning
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(get_directory_size_cached, task["path"], 10): task  # Limit depth for system dirs
            for task in scan_tasks
        }
        for future in as_completed(futures):
            task = futures[future]
            try:
                size, files, dirs = future.result()
                if size > 0:
                    paths.append({
                        "name": task["name"],
                        "path": str(task["path"]),
                        "description": task["description"],
                        "size_bytes": size,
                        "size_human": _format_size(size),
                        "file_count": files,
                        "accessible": True,
                    })
                    total_scanned += size
            except (PermissionError, OSError):
                # Can't access this path
                paths.append({
                    "name": task["name"],
                    "path": str(task["path"]),
                    "description": task["description"],
                    "size_bytes": 0,
                    "size_human": "N/A",
                    "accessible": False,
                })

    # Sort by size descending
    paths.sort(key=lambda x: x["size_bytes"], reverse=True)

    # Get disk info for context
    disk = get_disk_usage()

    return {
        "paths": paths,
        "count": len(paths),
        "total_scanned_bytes": total_scanned,
        "total_scanned_human": _format_size(total_scanned),
        "disk_used_bytes": disk.used_bytes,
        "disk_used_human": _format_size(disk.used_bytes),
        "note": "Some system files require admin access to scan accurately.",
    }


def list_applications(sort_by: str = "size") -> dict:
    """
    List all installed applications with sizes.

    Args:
        sort_by: Sort order - "size" (default), "name", or "date"

    Returns:
        Dict with list of applications and their sizes
    """
    import time

    apps = []
    app_dirs = [Path("/Applications"), expand_path("~/Applications")]

    for app_dir in app_dirs:
        if not app_dir.exists():
            continue

        try:
            for entry in app_dir.iterdir():
                if entry.suffix == ".app" and entry.is_dir():
                    try:
                        size, _, _ = get_directory_size(entry)
                        stat = entry.stat()
                        last_modified = stat.st_mtime

                        # Try to get last opened time from Launch Services
                        # (fallback to modified time)
                        apps.append({
                            "name": entry.stem,
                            "path": str(entry),
                            "size_bytes": size,
                            "size_human": _format_size(size),
                            "last_modified": time.strftime(
                                "%Y-%m-%d",
                                time.localtime(last_modified)
                            ),
                            "days_since_modified": int(
                                (time.time() - last_modified) / (24 * 60 * 60)
                            ),
                        })
                    except (PermissionError, OSError):
                        continue
        except (PermissionError, OSError):
            continue

    # Sort
    if sort_by == "size":
        apps.sort(key=lambda x: x["size_bytes"], reverse=True)
    elif sort_by == "name":
        apps.sort(key=lambda x: x["name"].lower())
    elif sort_by == "date":
        apps.sort(key=lambda x: x["days_since_modified"], reverse=True)

    total_size = sum(a["size_bytes"] for a in apps)

    return {
        "applications": apps,
        "count": len(apps),
        "total_size_bytes": total_size,
        "total_size_human": _format_size(total_size),
    }


# Build artifacts to find for project purge
PROJECT_ARTIFACTS = [
    "node_modules",
    "target",       # Rust, Maven
    "build",        # Gradle, various
    "dist",         # JS builds
    "venv",         # Python
    ".venv",        # Python
    ".gradle",      # Gradle local
    "__pycache__",  # Python
    ".next",        # Next.js
    ".nuxt",        # Nuxt.js
    ".output",      # Nuxt.js
    "vendor",       # PHP Composer, Go
    "obj",          # C# / Unity
    ".turbo",       # Turborepo cache
    ".parcel-cache", # Parcel bundler
    "Pods",         # CocoaPods
    ".dart_tool",   # Dart/Flutter
]

# Common project directories to search
PROJECT_SEARCH_PATHS = [
    "~/Projects",
    "~/Code",
    "~/code",
    "~/Development",
    "~/dev",
    "~/Developer",
    "~/workspace",
    "~/Workspace",
    "~/GitHub",
    "~/github",
    "~/repos",
    "~/src",
    "~/www",
]


def find_project_artifacts(
    min_age_days: int = 7,
    max_results: int = 100,
) -> dict:
    """
    Find build artifacts in project directories.

    Args:
        min_age_days: Only include artifacts older than this (default: 7 days)
        max_results: Maximum number of results

    Returns:
        Dict with list of artifacts and total size
    """
    import time

    cutoff_time = time.time() - (min_age_days * 24 * 60 * 60)
    artifacts = []

    # Find existing project directories
    search_roots = []
    for path_str in PROJECT_SEARCH_PATHS:
        path = expand_path(path_str)
        if path.exists() and path.is_dir():
            search_roots.append(path)

    # Also check home directory for common project markers
    home = expand_path("~")
    for entry in home.iterdir():
        if entry.is_dir() and not entry.name.startswith("."):
            # Check if it looks like a project directory
            if any((entry / marker).exists() for marker in [".git", "package.json", "Cargo.toml", "go.mod", "pom.xml"]):
                if entry not in search_roots:
                    search_roots.append(entry)

    # Search for artifacts
    for root in search_roots:
        try:
            for artifact_name in PROJECT_ARTIFACTS:
                # Search up to 5 levels deep
                for depth in range(1, 6):
                    pattern = "/".join(["*"] * depth) + f"/{artifact_name}"
                    for match in root.glob(pattern):
                        if not match.is_dir():
                            continue

                        try:
                            stat = match.stat()
                            # Skip recent artifacts
                            if stat.st_mtime > cutoff_time:
                                continue

                            size, files, dirs = get_directory_size(match)
                            if size > 0:
                                # Get project name (parent directory)
                                project_path = match.parent
                                project_name = project_path.name

                                artifacts.append({
                                    "path": str(match),
                                    "artifact_type": artifact_name,
                                    "project_name": project_name,
                                    "project_path": str(project_path),
                                    "size_bytes": size,
                                    "size_human": _format_size(size),
                                    "age_days": int((time.time() - stat.st_mtime) / (24 * 60 * 60)),
                                    "file_count": files,
                                })
                        except (PermissionError, OSError):
                            continue
        except (PermissionError, OSError):
            continue

    # Deduplicate (same path might be found multiple times)
    seen_paths = set()
    unique_artifacts = []
    for artifact in artifacts:
        if artifact["path"] not in seen_paths:
            seen_paths.add(artifact["path"])
            unique_artifacts.append(artifact)

    # Sort by size descending
    unique_artifacts.sort(key=lambda x: x["size_bytes"], reverse=True)

    total_size = sum(a["size_bytes"] for a in unique_artifacts[:max_results])

    return {
        "artifacts": unique_artifacts[:max_results],
        "count": len(unique_artifacts),
        "total_size_bytes": total_size,
        "total_size_human": _format_size(total_size),
        "search_roots": [str(r) for r in search_roots],
    }


def find_duplicates(
    path: str = "~",
    min_size_mb: int = 1,
    max_results: int = 100,
) -> list[dict]:
    """
    Find duplicate files by hash comparison.

    Args:
        path: Path to search
        min_size_mb: Minimum file size to consider (default: 1 MB)
        max_results: Maximum number of duplicate groups to return

    Returns:
        List of duplicate groups with paths and sizes
    """
    import hashlib
    from collections import defaultdict

    min_size_bytes = min_size_mb * 1024 * 1024
    expanded_path = expand_path(path)

    if not expanded_path.exists():
        return []

    # First pass: group by size (fast)
    size_groups: dict[int, list[Path]] = defaultdict(list)

    try:
        for entry in expanded_path.rglob("*"):
            try:
                if entry.is_file() and not entry.is_symlink():
                    size = entry.stat().st_size
                    if size >= min_size_bytes:
                        size_groups[size].append(entry)
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        pass

    # Second pass: hash files with same size
    duplicates = []

    for size, paths in size_groups.items():
        if len(paths) < 2:
            continue

        # Hash these files
        hash_groups: dict[str, list[Path]] = defaultdict(list)

        for file_path in paths:
            try:
                # Read first 8KB for quick hash
                with open(file_path, "rb") as f:
                    chunk = f.read(8192)
                    file_hash = hashlib.md5(chunk).hexdigest()
                hash_groups[file_hash].append(file_path)
            except (PermissionError, OSError):
                continue

        # Find actual duplicates
        for file_hash, hash_paths in hash_groups.items():
            if len(hash_paths) >= 2:
                duplicates.append({
                    "size_bytes": size,
                    "size_human": _format_size(size),
                    "count": len(hash_paths),
                    "wasted_bytes": size * (len(hash_paths) - 1),
                    "wasted_human": _format_size(size * (len(hash_paths) - 1)),
                    "paths": [str(p) for p in hash_paths],
                })

    # Sort by wasted space descending
    duplicates.sort(key=lambda x: x["wasted_bytes"], reverse=True)

    total_wasted = sum(d["wasted_bytes"] for d in duplicates[:max_results])

    return {
        "duplicates": duplicates[:max_results],
        "total_groups": len(duplicates),
        "total_wasted_bytes": total_wasted,
        "total_wasted_human": _format_size(total_wasted),
    }


# =============================================================================
# Whitelist / Protection feature
# =============================================================================

import json

CONFIG_DIR = expand_path("~/.uncruft")
CONFIG_FILE = CONFIG_DIR / "config.json"


def _load_config() -> dict:
    """Load configuration from disk."""
    if not CONFIG_FILE.exists():
        return {"protected_paths": [], "protected_categories": []}

    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"protected_paths": [], "protected_categories": []}


def _save_config(config: dict) -> bool:
    """Save configuration to disk."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
        return True
    except OSError:
        return False


def is_protected(path: str) -> bool:
    """
    Check if a path is protected from cleanup.

    Args:
        path: Path to check (can contain ~)

    Returns:
        True if the path is protected
    """
    config = _load_config()
    expanded = str(expand_path(path))

    for protected in config.get("protected_paths", []):
        protected_expanded = str(expand_path(protected))
        # Check if path is the protected path or a child of it
        if expanded == protected_expanded or expanded.startswith(protected_expanded + "/"):
            return True

    return False


def is_category_protected(category_id: str) -> bool:
    """
    Check if a category is protected from cleanup.

    Args:
        category_id: Category ID to check

    Returns:
        True if the category is protected
    """
    config = _load_config()
    return category_id in config.get("protected_categories", [])


def add_protection(path: str | None = None, category_id: str | None = None) -> dict:
    """
    Add a path or category to the protection list.

    Args:
        path: Path to protect (optional)
        category_id: Category ID to protect (optional)

    Returns:
        Dict with success status and current protections
    """
    if not path and not category_id:
        return {"success": False, "error": "Must specify path or category_id"}

    config = _load_config()

    if path:
        expanded = str(expand_path(path))
        if not Path(expanded).exists():
            return {"success": False, "error": f"Path does not exist: {path}"}

        if expanded not in config.get("protected_paths", []):
            config.setdefault("protected_paths", []).append(expanded)

    if category_id:
        if category_id not in config.get("protected_categories", []):
            config.setdefault("protected_categories", []).append(category_id)

    if _save_config(config):
        return {
            "success": True,
            "protected_paths": config.get("protected_paths", []),
            "protected_categories": config.get("protected_categories", []),
        }
    else:
        return {"success": False, "error": "Failed to save config"}


def remove_protection(path: str | None = None, category_id: str | None = None) -> dict:
    """
    Remove a path or category from the protection list.

    Args:
        path: Path to unprotect (optional)
        category_id: Category ID to unprotect (optional)

    Returns:
        Dict with success status and current protections
    """
    if not path and not category_id:
        return {"success": False, "error": "Must specify path or category_id"}

    config = _load_config()

    if path:
        expanded = str(expand_path(path))
        if expanded in config.get("protected_paths", []):
            config["protected_paths"].remove(expanded)

    if category_id:
        if category_id in config.get("protected_categories", []):
            config["protected_categories"].remove(category_id)

    if _save_config(config):
        return {
            "success": True,
            "protected_paths": config.get("protected_paths", []),
            "protected_categories": config.get("protected_categories", []),
        }
    else:
        return {"success": False, "error": "Failed to save config"}


def list_protections() -> dict:
    """
    List all protected paths and categories.

    Returns:
        Dict with protected paths and categories
    """
    config = _load_config()

    # Get sizes for protected paths
    paths_with_info = []
    for path_str in config.get("protected_paths", []):
        path = Path(path_str)
        try:
            if path.exists():
                if path.is_dir():
                    size, files, _ = get_directory_size(path)
                else:
                    size = path.stat().st_size
                    files = 1
                paths_with_info.append({
                    "path": path_str,
                    "size_bytes": size,
                    "size_human": _format_size(size),
                    "file_count": files,
                    "exists": True,
                })
            else:
                paths_with_info.append({
                    "path": path_str,
                    "exists": False,
                })
        except (PermissionError, OSError):
            paths_with_info.append({
                "path": path_str,
                "error": "Cannot access",
            })

    return {
        "protected_paths": paths_with_info,
        "protected_categories": config.get("protected_categories", []),
        "path_count": len(paths_with_info),
        "category_count": len(config.get("protected_categories", [])),
    }


# =============================================================================
# Category Drill-Down Functions
# =============================================================================


def get_docker_breakdown() -> dict:
    """
    Get detailed Docker usage breakdown.

    Returns:
        Dict with images, containers, volumes, and build cache details
    """
    import re
    import subprocess

    result = {
        "available": False,
        "images": [],
        "containers": [],
        "volumes": [],
        "build_cache_bytes": 0,
        "total_bytes": 0,
        "unused_bytes": 0,
        "error": None,
    }

    # Check if Docker is available
    try:
        check = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if check.returncode != 0:
            result["error"] = "Docker is not running"
            return result
    except (subprocess.TimeoutExpired, FileNotFoundError):
        result["error"] = "Docker is not installed or not running"
        return result

    result["available"] = True

    # Get images
    try:
        img_result = subprocess.run(
            ["docker", "images", "--format", "{{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if img_result.returncode == 0:
            for line in img_result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) >= 4:
                    repo, tag, img_id, size_str = parts[:4]
                    size_bytes = _parse_docker_size(size_str)
                    result["images"].append({
                        "repository": repo,
                        "tag": tag,
                        "id": img_id[:12],
                        "size_bytes": size_bytes,
                        "size_human": size_str,
                        "status": "dangling" if repo == "<none>" else "available",
                    })
    except Exception as e:
        result["error"] = f"Failed to get images: {e}"

    # Get containers
    try:
        cont_result = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{.Names}}\t{{.ID}}\t{{.Status}}\t{{.Size}}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if cont_result.returncode == 0:
            for line in cont_result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) >= 3:
                    name = parts[0]
                    cont_id = parts[1][:12]
                    status = parts[2]
                    size_str = parts[3] if len(parts) > 3 else "0B"
                    # Parse container size (format: "0B (virtual 890MB)")
                    size_bytes = _parse_docker_size(size_str.split()[0] if size_str else "0B")

                    is_running = status.startswith("Up")
                    result["containers"].append({
                        "name": name,
                        "id": cont_id,
                        "status": "running" if is_running else "exited",
                        "status_detail": status,
                        "size_bytes": size_bytes,
                        "size_human": size_str.split()[0] if size_str else "0B",
                    })
    except Exception as e:
        result["error"] = f"Failed to get containers: {e}"

    # Get volumes
    try:
        vol_result = subprocess.run(
            ["docker", "volume", "ls", "--format", "{{.Name}}\t{{.Driver}}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if vol_result.returncode == 0:
            for line in vol_result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split("\t")
                name = parts[0]
                driver = parts[1] if len(parts) > 1 else "local"

                # Get volume size (inspect is slow, so just note it exists)
                result["volumes"].append({
                    "name": name,
                    "driver": driver,
                    "status": "available",  # Would need to check if in use
                })
    except Exception as e:
        result["error"] = f"Failed to get volumes: {e}"

    # Get system df for totals
    try:
        df_result = subprocess.run(
            ["docker", "system", "df"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if df_result.returncode == 0:
            for line in df_result.stdout.strip().split("\n")[1:]:  # Skip header
                parts = line.split()
                if len(parts) >= 4:
                    type_name = parts[0]
                    size_str = parts[3] if len(parts) > 3 else "0B"
                    reclaimable = parts[-1] if "%" in parts[-1] else "0%"

                    if type_name == "Images":
                        # Already have detailed image info
                        pass
                    elif type_name == "Build":
                        result["build_cache_bytes"] = _parse_docker_size(size_str)
    except Exception as e:
        pass

    # Calculate totals
    result["total_bytes"] = (
        sum(i["size_bytes"] for i in result["images"]) +
        sum(c["size_bytes"] for c in result["containers"]) +
        result["build_cache_bytes"]
    )

    # Calculate unused (dangling images + exited containers + build cache)
    result["unused_bytes"] = (
        sum(i["size_bytes"] for i in result["images"] if i["status"] == "dangling") +
        sum(c["size_bytes"] for c in result["containers"] if c["status"] == "exited") +
        result["build_cache_bytes"]
    )

    return result


def _parse_docker_size(size_str: str) -> int:
    """Parse Docker size string to bytes."""
    import re

    if not size_str:
        return 0

    size_str = size_str.strip()
    match = re.match(r"([\d.]+)\s*([KMGT]?B?)", size_str, re.IGNORECASE)
    if not match:
        return 0

    num = float(match.group(1))
    unit = match.group(2).upper()

    multipliers = {
        "B": 1,
        "KB": 1024,
        "MB": 1024**2,
        "GB": 1024**3,
        "TB": 1024**4,
        "K": 1024,
        "M": 1024**2,
        "G": 1024**3,
        "T": 1024**4,
    }

    return int(num * multipliers.get(unit, 1))


def get_node_modules_breakdown() -> dict:
    """
    Get per-project node_modules breakdown.

    Uses depth-limited os.walk for better performance.

    Returns:
        Dict with projects list and total size
    """
    import json as json_module

    projects = []
    total_size = 0
    max_depth = 5  # Only search 5 levels deep

    # Find existing project directories
    search_roots = []
    for path_str in PROJECT_SEARCH_PATHS:
        path = expand_path(path_str)
        if path.exists() and path.is_dir():
            search_roots.append(path)

    # Also check home directory top level (not recursive)
    home = expand_path("~")
    try:
        for entry in home.iterdir():
            if entry.is_dir() and not entry.name.startswith("."):
                # Check if it's a project directory
                if any((entry / marker).exists() for marker in [".git", "package.json"]):
                    if entry not in search_roots:
                        search_roots.append(entry)
    except (PermissionError, OSError):
        pass

    # Find node_modules using depth-limited os.walk
    seen_paths = set()
    nm_paths_to_scan = []

    for root in search_roots:
        root_str = str(root)
        root_depth = root_str.count(os.sep)

        try:
            for dirpath, dirnames, filenames in os.walk(root):
                # Calculate current depth relative to root
                current_depth = dirpath.count(os.sep) - root_depth

                # Stop going deeper if we exceed max_depth
                if current_depth >= max_depth:
                    dirnames.clear()
                    continue

                # Skip hidden directories and node_modules children
                dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "node_modules"]

                # Check if node_modules exists at this level
                nm_path = Path(dirpath) / "node_modules"
                if nm_path.exists() and nm_path.is_dir():
                    if nm_path not in seen_paths:
                        seen_paths.add(nm_path)
                        nm_paths_to_scan.append(nm_path)

        except (PermissionError, OSError):
            continue

    # Scan node_modules directories in parallel
    now = time.time()
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(get_directory_size_cached, nm_path): nm_path
            for nm_path in nm_paths_to_scan
        }
        for future in as_completed(futures):
            nm_path = futures[future]
            try:
                size, files, _ = future.result()
                project_root = nm_path.parent
                stat = nm_path.stat()

                # Get project name from package.json if available
                package_json = project_root / "package.json"
                project_name = project_root.name
                if package_json.exists():
                    try:
                        with open(package_json) as f:
                            pkg = json_module.load(f)
                            project_name = pkg.get("name", project_root.name)
                    except Exception:
                        pass

                days_old = int((now - stat.st_mtime) / (24 * 60 * 60))

                projects.append({
                    "project_name": project_name,
                    "project_path": str(project_root),
                    "node_modules_path": str(nm_path),
                    "size_bytes": size,
                    "size_human": _format_size(size),
                    "file_count": files,
                    "days_since_modified": days_old,
                    "status": "inactive" if days_old > 180 else "active",
                })
                total_size += size

            except (PermissionError, OSError):
                continue

    # Sort by size descending
    projects.sort(key=lambda x: x["size_bytes"], reverse=True)

    inactive = [p for p in projects if p["status"] == "inactive"]

    return {
        "projects": projects,
        "count": len(projects),
        "total_size_bytes": total_size,
        "total_size_human": _format_size(total_size),
        "inactive_count": len(inactive),
        "inactive_size_bytes": sum(p["size_bytes"] for p in inactive),
        "inactive_size_human": _format_size(sum(p["size_bytes"] for p in inactive)),
    }


def get_app_caches_breakdown() -> dict:
    """
    Get per-app cache breakdown from ~/Library/Caches.

    Uses parallel scanning for better performance.

    Returns:
        Dict with apps list and total size
    """
    cache_dir = expand_path("~/Library/Caches")
    apps = []
    total_size = 0

    if not cache_dir.exists():
        return {
            "apps": [],
            "count": 0,
            "total_size_bytes": 0,
            "total_size_human": "0 B",
        }

    # Known browser cache identifiers
    browser_ids = {
        "com.google.Chrome": "Chrome",
        "com.apple.Safari": "Safari",
        "org.mozilla.firefox": "Firefox",
        "com.microsoft.edgemac": "Edge",
        "com.brave.Browser": "Brave",
    }

    # Collect cache directories to scan
    cache_entries = []
    try:
        for entry in cache_dir.iterdir():
            if entry.is_dir():
                cache_entries.append(entry)
    except (PermissionError, OSError):
        pass

    # Scan cache directories in parallel
    entry_sizes = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(get_directory_size_cached, entry): entry
            for entry in cache_entries
        }
        for future in as_completed(futures):
            entry = futures[future]
            try:
                size, files, _ = future.result()
                entry_sizes[entry] = (size, files)
            except Exception:
                pass

    # Build apps list from results
    for entry, (size, files) in entry_sizes.items():
        if size == 0:
            continue

        # Determine app name
        name = entry.name
        bundle_id = entry.name
        is_browser = False

        for bid, browser_name in browser_ids.items():
            if bid in entry.name:
                name = browser_name
                is_browser = True
                break

        # Clean up bundle ID to get readable name
        if not is_browser:
            if name.startswith("com."):
                parts = name.split(".")
                if len(parts) >= 3:
                    name = parts[2].replace("-", " ").title()

        apps.append({
            "name": name,
            "bundle_id": bundle_id,
            "path": str(entry),
            "size_bytes": size,
            "size_human": _format_size(size),
            "file_count": files,
            "is_browser": is_browser,
        })
        total_size += size

    # Sort by size descending
    apps.sort(key=lambda x: x["size_bytes"], reverse=True)

    # Separate browsers
    browsers = [a for a in apps if a["is_browser"]]
    browser_total = sum(b["size_bytes"] for b in browsers)

    return {
        "apps": apps,
        "count": len(apps),
        "total_size_bytes": total_size,
        "total_size_human": _format_size(total_size),
        "browsers": browsers,
        "browser_count": len(browsers),
        "browser_size_bytes": browser_total,
        "browser_size_human": _format_size(browser_total),
    }


def get_huggingface_breakdown() -> dict:
    """
    Get HuggingFace models breakdown.

    Returns:
        Dict with models list and total size
    """
    hf_cache = expand_path("~/.cache/huggingface/hub")
    models = []
    total_size = 0

    if not hf_cache.exists():
        return {
            "models": [],
            "count": 0,
            "total_size_bytes": 0,
            "total_size_human": "0 B",
        }

    try:
        for entry in hf_cache.iterdir():
            if not entry.is_dir():
                continue

            # HuggingFace model dirs are like "models--organization--model-name"
            if not entry.name.startswith("models--"):
                continue

            try:
                size, files, _ = get_directory_size(entry)
                if size == 0:
                    continue

                # Parse model name
                parts = entry.name.replace("models--", "").split("--")
                if len(parts) >= 2:
                    org = parts[0]
                    model = parts[1]
                    name = f"{org}/{model}"
                else:
                    name = entry.name.replace("models--", "")

                models.append({
                    "name": name,
                    "path": str(entry),
                    "size_bytes": size,
                    "size_human": _format_size(size),
                    "file_count": files,
                })
                total_size += size

            except (PermissionError, OSError):
                continue

    except (PermissionError, OSError):
        pass

    # Sort by size descending
    models.sort(key=lambda x: x["size_bytes"], reverse=True)

    return {
        "models": models,
        "count": len(models),
        "total_size_bytes": total_size,
        "total_size_human": _format_size(total_size),
    }
