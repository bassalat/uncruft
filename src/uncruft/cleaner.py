"""Cleanup execution with safety checks for uncruft."""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from uncruft.categories import CATEGORIES, get_category
from uncruft.models import CleanupResult, RiskLevel, ScanResult
from uncruft.scanner import expand_path, get_directory_size

# Paths that should NEVER be deleted
BLOCKED_PATHS = [
    "~/Documents",
    "~/Desktop",
    "~/Pictures",
    "~/Music",
    "~/Movies",
    "~/Code",
    "~/Projects",
    "~/Work",
    "/System",
    "/Library",
    "/Applications",
    "/usr",
    "/bin",
    "/sbin",
    "/var",
    "/private",
    "/Users",
    "~",
]

# Maximum size for single cleanup (safety check)
MAX_CLEANUP_BYTES = 100 * 1024**3  # 100 GB


def is_path_safe(path: Path) -> bool:
    """
    Check if a path is safe to delete.

    Args:
        path: Path to check

    Returns:
        True if safe to delete, False otherwise
    """
    path_str = str(path)

    # Check against blocked paths
    for blocked in BLOCKED_PATHS:
        blocked_expanded = str(expand_path(blocked))
        if path_str == blocked_expanded or path_str.startswith(blocked_expanded + "/"):
            # Check if it's the exact blocked path (not allowed)
            if path_str == blocked_expanded:
                return False

    # Don't allow deleting home directory itself
    home = str(Path.home())
    if path_str == home:
        return False

    return True


def is_inside_allowed_path(path: Path, category_id: str) -> bool:
    """
    Check if path is inside an allowed location for the category.

    Args:
        path: Path to check
        category_id: Category ID

    Returns:
        True if path is inside allowed locations
    """
    category = get_category(category_id)
    if not category:
        return False

    path_str = str(path)
    for allowed_path in category.paths:
        allowed_expanded = str(expand_path(allowed_path))
        if path_str.startswith(allowed_expanded):
            return True

    return False


def delete_path(path: Path, dry_run: bool = False) -> tuple[int, int, str | None]:
    """
    Delete a path (file or directory).

    Args:
        path: Path to delete
        dry_run: If True, don't actually delete

    Returns:
        Tuple of (bytes_freed, files_deleted, error_message)
    """
    if not path.exists():
        return 0, 0, None

    try:
        # Calculate size before deletion
        if path.is_file():
            size = path.stat().st_size
            files = 1
        else:
            size, files, _ = get_directory_size(path)

        if dry_run:
            return size, files, None

        # Actually delete
        if path.is_file():
            path.unlink()
        else:
            shutil.rmtree(path)

        return size, files, None

    except PermissionError as e:
        return 0, 0, f"Permission denied: {e}"
    except OSError as e:
        return 0, 0, f"OS error: {e}"


def clean_category(
    category_id: str,
    dry_run: bool = False,
    progress_callback: Callable[[str, int], None] | None = None,
) -> CleanupResult:
    """
    Clean all paths in a category.

    Args:
        category_id: Category ID to clean
        dry_run: If True, don't actually delete
        progress_callback: Optional callback(path, bytes_freed)

    Returns:
        CleanupResult with total bytes freed
    """
    category = get_category(category_id)
    if not category:
        return CleanupResult(
            category_id=category_id,
            path="",
            bytes_freed=0,
            files_deleted=0,
            success=False,
            error=f"Unknown category: {category_id}",
            dry_run=dry_run,
        )

    # Check if category has a native cleanup command
    if category.cleanup_command and not dry_run:
        return _run_native_cleanup(category_id, category.cleanup_command, dry_run)

    total_bytes = 0
    total_files = 0
    errors = []
    paths_cleaned = []

    for path_str in category.paths:
        path = expand_path(path_str)

        if not path.exists():
            continue

        # Safety checks
        if not is_path_safe(path):
            errors.append(f"Blocked path: {path}")
            continue

        # Delete
        bytes_freed, files_deleted, error = delete_path(path, dry_run)

        if error:
            errors.append(f"{path}: {error}")
        else:
            total_bytes += bytes_freed
            total_files += files_deleted
            paths_cleaned.append(str(path))

            if progress_callback:
                progress_callback(str(path), bytes_freed)

    return CleanupResult(
        category_id=category_id,
        path=paths_cleaned[0] if paths_cleaned else category.paths[0],
        bytes_freed=total_bytes,
        files_deleted=total_files,
        success=len(errors) == 0,
        error="; ".join(errors) if errors else None,
        dry_run=dry_run,
    )


def _run_native_cleanup(
    category_id: str,
    command: str,
    dry_run: bool,
) -> CleanupResult:
    """
    Run a native cleanup command.

    Args:
        category_id: Category ID
        command: Native cleanup command
        dry_run: If True, don't run the command

    Returns:
        CleanupResult
    """
    if dry_run:
        return CleanupResult(
            category_id=category_id,
            path=f"[native command: {command}]",
            bytes_freed=0,  # Can't know without running
            files_deleted=0,
            success=True,
            dry_run=True,
        )

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )

        if result.returncode == 0:
            return CleanupResult(
                category_id=category_id,
                path=f"[native command: {command}]",
                bytes_freed=0,  # Can't determine exact amount
                files_deleted=0,
                success=True,
                dry_run=False,
            )
        else:
            return CleanupResult(
                category_id=category_id,
                path=f"[native command: {command}]",
                bytes_freed=0,
                files_deleted=0,
                success=False,
                error=result.stderr or "Command failed",
                dry_run=False,
            )

    except subprocess.TimeoutExpired:
        return CleanupResult(
            category_id=category_id,
            path=f"[native command: {command}]",
            bytes_freed=0,
            files_deleted=0,
            success=False,
            error="Command timed out",
            dry_run=False,
        )
    except Exception as e:
        return CleanupResult(
            category_id=category_id,
            path=f"[native command: {command}]",
            bytes_freed=0,
            files_deleted=0,
            success=False,
            error=str(e),
            dry_run=False,
        )


def clean_safe_items(
    scan_results: list[ScanResult],
    dry_run: bool = False,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> list[CleanupResult]:
    """
    Clean all safe items from scan results.

    Args:
        scan_results: List of scan results
        dry_run: If True, don't actually delete
        progress_callback: Optional callback(category, current, total)

    Returns:
        List of CleanupResults
    """
    safe_items = [r for r in scan_results if r.risk_level == RiskLevel.SAFE and r.size_bytes > 0]

    results = []
    total = len(safe_items)

    for i, item in enumerate(safe_items):
        if progress_callback:
            progress_callback(item.category_name, i + 1, total)

        result = clean_category(item.category_id, dry_run)
        results.append(result)

    return results


def validate_cleanup_request(
    category_ids: list[str],
    total_bytes: int,
) -> tuple[bool, str | None]:
    """
    Validate a cleanup request for safety.

    Args:
        category_ids: Categories to clean
        total_bytes: Total bytes to be cleaned

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check size limit
    if total_bytes > MAX_CLEANUP_BYTES:
        return False, f"Cleanup exceeds safety limit ({total_bytes / 1024**3:.1f} GB > 100 GB)"

    # Validate categories exist
    for cat_id in category_ids:
        if cat_id not in CATEGORIES:
            return False, f"Unknown category: {cat_id}"

    return True, None


# =============================================================================
# Selective Delete Functions (for drill-down)
# =============================================================================


def delete_docker_item(
    item_type: str,
    item_id: str,
    dry_run: bool = False,
) -> dict:
    """
    Delete a specific Docker image, container, or volume.

    Args:
        item_type: "image", "container", or "volume"
        item_id: Docker ID or name
        dry_run: If True, simulate without deleting

    Returns:
        Dict with success, bytes_freed, and error fields
    """
    if item_type not in ("image", "container", "volume"):
        return {
            "success": False,
            "error": f"Invalid item_type: {item_type}. Must be image, container, or volume.",
        }

    # Build the appropriate command
    if item_type == "image":
        cmd = ["docker", "rmi", item_id]
    elif item_type == "container":
        cmd = ["docker", "rm", item_id]
    elif item_type == "volume":
        cmd = ["docker", "volume", "rm", item_id]

    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "command": " ".join(cmd),
            "item_type": item_type,
            "item_id": item_id,
        }

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode == 0:
            return {
                "success": True,
                "item_type": item_type,
                "item_id": item_id,
                "command": " ".join(cmd),
            }
        else:
            return {
                "success": False,
                "item_type": item_type,
                "item_id": item_id,
                "error": result.stderr.strip() or "Command failed",
            }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Command timed out",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def delete_docker_unused(
    item_type: str | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Delete unused Docker items (dangling images, stopped containers, etc).

    Args:
        item_type: Optional "images", "containers", "volumes", or None for all
        dry_run: If True, simulate without deleting

    Returns:
        Dict with success and details
    """
    if item_type:
        if item_type == "images":
            cmd = ["docker", "image", "prune", "-f"]
        elif item_type == "containers":
            cmd = ["docker", "container", "prune", "-f"]
        elif item_type == "volumes":
            cmd = ["docker", "volume", "prune", "-f"]
        else:
            return {"success": False, "error": f"Invalid item_type: {item_type}"}
    else:
        cmd = ["docker", "system", "prune", "-f"]

    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "command": " ".join(cmd),
        }

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode == 0:
            return {
                "success": True,
                "command": " ".join(cmd),
                "output": result.stdout,
            }
        else:
            return {
                "success": False,
                "error": result.stderr.strip() or "Command failed",
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def delete_node_modules_project(
    project_path: str,
    dry_run: bool = False,
) -> dict:
    """
    Delete node_modules for a specific project.

    Args:
        project_path: Path to the project (containing node_modules)
        dry_run: If True, simulate without deleting

    Returns:
        Dict with success, bytes_freed, and error fields
    """
    path = expand_path(project_path)
    node_modules = path / "node_modules" if not path.name == "node_modules" else path

    if not node_modules.exists():
        return {
            "success": False,
            "error": f"node_modules not found at {node_modules}",
        }

    try:
        size, files, _ = get_directory_size(node_modules)

        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "path": str(node_modules),
                "bytes_freed": size,
                "files_deleted": files,
            }

        shutil.rmtree(node_modules)

        return {
            "success": True,
            "path": str(node_modules),
            "bytes_freed": size,
            "files_deleted": files,
        }

    except PermissionError as e:
        return {
            "success": False,
            "error": f"Permission denied: {e}",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def delete_app_cache(
    app_name_or_path: str,
    dry_run: bool = False,
) -> dict:
    """
    Delete cache for a specific app.

    Args:
        app_name_or_path: App bundle ID, name, or full path
        dry_run: If True, simulate without deleting

    Returns:
        Dict with success, bytes_freed, and error fields
    """
    cache_dir = expand_path("~/Library/Caches")

    # If it's a full path, use directly
    if app_name_or_path.startswith("/") or app_name_or_path.startswith("~"):
        cache_path = expand_path(app_name_or_path)
    else:
        # Search for matching cache directory
        cache_path = None
        search_term = app_name_or_path.lower()

        try:
            for entry in cache_dir.iterdir():
                if search_term in entry.name.lower():
                    cache_path = entry
                    break
        except (PermissionError, OSError):
            pass

        if not cache_path:
            return {
                "success": False,
                "error": f"Cache not found for: {app_name_or_path}",
            }

    if not cache_path.exists():
        return {
            "success": False,
            "error": f"Cache path does not exist: {cache_path}",
        }

    # Safety check - must be inside ~/Library/Caches
    if not str(cache_path).startswith(str(cache_dir)):
        return {
            "success": False,
            "error": f"Path not inside ~/Library/Caches: {cache_path}",
        }

    try:
        size, files, _ = get_directory_size(cache_path)

        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "path": str(cache_path),
                "bytes_freed": size,
                "files_deleted": files,
            }

        shutil.rmtree(cache_path)

        return {
            "success": True,
            "path": str(cache_path),
            "bytes_freed": size,
            "files_deleted": files,
        }

    except PermissionError as e:
        return {
            "success": False,
            "error": f"Permission denied: {e}",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def delete_huggingface_model(
    model_name: str,
    dry_run: bool = False,
) -> dict:
    """
    Delete a specific HuggingFace model.

    Args:
        model_name: Model name (e.g., "facebook/opt-350m") or path
        dry_run: If True, simulate without deleting

    Returns:
        Dict with success, bytes_freed, and error fields
    """
    hf_cache = expand_path("~/.cache/huggingface/hub")

    # Convert model name to cache directory name
    # e.g., "facebook/opt-350m" -> "models--facebook--opt-350m"
    if "/" in model_name:
        cache_name = "models--" + model_name.replace("/", "--")
    else:
        cache_name = model_name

    model_path = hf_cache / cache_name

    # If not found, search for partial match
    if not model_path.exists():
        search_term = model_name.lower().replace("/", "--")
        try:
            for entry in hf_cache.iterdir():
                if search_term in entry.name.lower():
                    model_path = entry
                    break
        except (PermissionError, OSError):
            pass

    if not model_path.exists():
        return {
            "success": False,
            "error": f"Model not found: {model_name}",
        }

    try:
        size, files, _ = get_directory_size(model_path)

        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "path": str(model_path),
                "model_name": model_name,
                "bytes_freed": size,
                "files_deleted": files,
            }

        shutil.rmtree(model_path)

        return {
            "success": True,
            "path": str(model_path),
            "model_name": model_name,
            "bytes_freed": size,
            "files_deleted": files,
        }

    except PermissionError as e:
        return {
            "success": False,
            "error": f"Permission denied: {e}",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
