"""Tool definitions and execution handlers for AI interaction."""

import json
from typing import Any, Callable

from uncruft.analyzer import analyze_disk, explain_category
from uncruft.categories import get_all_categories, get_category
from uncruft.cleaner import clean_category
from uncruft.models import Analysis, RiskLevel
from uncruft.scanner import (
    get_disk_usage,
    find_large_files,
    analyze_directory,
    find_old_files,
    run_command,
    find_mail_attachments,
    find_app_data,
    uninstall_app,
    find_duplicates,
    get_storage_breakdown,
    list_applications,
    find_project_artifacts,
    add_protection,
    remove_protection,
    list_protections,
    is_protected,
    is_category_protected,
    ALLOWED_COMMANDS,
    DESTRUCTIVE_COMMANDS,
)

# Tool definitions for llama.cpp function calling
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "scan_disk",
            "description": "Find CLEANABLE items (caches, logs, temp files). Use for 'what can I clean?' or 'help me free space'. Returns: {cleanable_items: [{category_id, name, size_human, risk}], total_cleanable_bytes}. Do NOT use for general 'what's using space' - use get_storage_breakdown instead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_dev": {
                        "type": "boolean",
                        "description": "Include developer artifacts like node_modules, .venv (default: true)",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_disk_status",
            "description": "Quick disk overview. Use for 'how much space do I have?' Returns: {total_gb, used_gb, free_gb, used_percent}. For detailed breakdown, use get_storage_breakdown.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_category",
            "description": "Get detailed explanation of a cleanup category including what it is, why it's safe, and recovery steps.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category_id": {
                        "type": "string",
                        "description": "Category ID (e.g., 'npm_cache', 'docker_data')",
                    }
                },
                "required": ["category_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clean_category",
            "description": "Clean a specific category. Only call after user confirms.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category_id": {
                        "type": "string",
                        "description": "Category ID to clean",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, simulate without deleting (default: false)",
                    },
                },
                "required": ["category_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clean_multiple",
            "description": "Clean multiple categories at once. Only call after user confirms.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of category IDs to clean",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, simulate without deleting",
                    },
                },
                "required": ["category_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_categories",
            "description": "List all available cleanup categories with their risk levels.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    # File search tools
    {
        "type": "function",
        "function": {
            "name": "find_large_files",
            "description": "Find LARGE FILES in any folder. Use for 'find big files', 'files in Documents', 'top 10 files in Downloads'. Pass path parameter for specific folders (e.g., path='~/Documents'). Returns: [{path, size_human, modified}].",
            "parameters": {
                "type": "object",
                "properties": {
                    "min_size_mb": {
                        "type": "integer",
                        "description": "Minimum file size in MB (default: 100)",
                    },
                    "path": {
                        "type": "string",
                        "description": "Path to search (default: home directory)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_directory",
            "description": "Analyze a SPECIFIC FOLDER. Use for 'what's in ~/Downloads?' or 'explore /path'. Returns: {total_size, items: [{name, size_human, type}]}. Requires a path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to analyze (e.g., ~/Downloads, ~/Documents)",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_old_files",
            "description": "Find UNUSED files not accessed recently. Use for 'old files' or 'stale downloads'. Returns: [{path, size_human, days_old}].",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Days since last access (default: 180)",
                    },
                    "path": {
                        "type": "string",
                        "description": "Path to search (default: ~/Downloads)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run whitelisted commands: docker (images, system df, ps), brew (list, outdated), git (status). Returns command output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Full command (e.g., 'docker images', 'brew list')",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_mail_attachments",
            "description": "Find old Mail.app attachments that can be cleaned.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Find attachments older than this many days (default: 365)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_app_data",
            "description": "Find all data associated with an app (caches, preferences, logs, etc.). Use before uninstalling.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "Name of the app (e.g., 'Slack', 'Spotify')",
                    },
                },
                "required": ["app_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "uninstall_app",
            "description": "Uninstall an app and remove all its associated data. Requires user confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "Name of the app to uninstall",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, just show what would be deleted",
                    },
                },
                "required": ["app_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_duplicates",
            "description": "Find duplicate files. Warning: can be slow on large directories.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to search (default: home directory)",
                    },
                    "min_size_mb": {
                        "type": "integer",
                        "description": "Minimum file size in MB to consider (default: 1)",
                    },
                },
                "required": [],
            },
        },
    },
    # Storage overview tools
    {
        "type": "function",
        "function": {
            "name": "get_storage_breakdown",
            "description": "CATEGORY BREAKDOWN of disk usage (Applications, Documents, Developer, Photos, etc). Use for 'what's using my space?' or 'where is space going?'. Returns: {disk: {total, used, free}, categories: [{name, size_human, percent}]}. Do NOT use for cleanup - use scan_disk instead.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_applications",
            "description": "List INSTALLED APPS in /Applications. Use ONLY for 'show my apps' or 'what apps do I have'. NOT for files in Documents/Downloads - use find_large_files for that. Returns: [{name, size_human}].",
            "parameters": {
                "type": "object",
                "properties": {
                    "sort_by": {
                        "type": "string",
                        "description": "Sort: 'size' (default), 'name', or 'date'",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_project_artifacts",
            "description": "Find DEVELOPER BUILD ARTIFACTS (node_modules, target, build, dist, venv). Use for 'clean dev stuff' or 'project cleanup'. Returns: [{path, artifact_type, project_name, size_human}].",
            "parameters": {
                "type": "object",
                "properties": {
                    "min_age_days": {
                        "type": "integer",
                        "description": "Only artifacts older than N days (default: 7)",
                    },
                },
                "required": [],
            },
        },
    },
    # Protection tools
    {
        "type": "function",
        "function": {
            "name": "add_protection",
            "description": "PROTECT a path or category from cleanup. Provide EITHER path OR category_id (one required). Use for 'don't delete X' or 'protect X'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to protect (e.g., ~/Documents/important)",
                    },
                    "category_id": {
                        "type": "string",
                        "description": "Category ID to protect (e.g., 'npm_cache', 'docker_data')",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_protection",
            "description": "UNPROTECT a path or category. Provide EITHER path OR category_id. Use for 'allow cleanup of X' or 'unprotect X'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to unprotect",
                    },
                    "category_id": {
                        "type": "string",
                        "description": "Category ID to unprotect",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_protections",
            "description": "Show all PROTECTED items. Use for 'what's protected?' or 'show whitelist'. Returns: {protected_paths: [], protected_categories: []}.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


class ToolRegistry:
    """Registry of tools available to the AI."""

    def __init__(self, dry_run: bool = False):
        """Initialize tool registry.

        Args:
            dry_run: If True, all cleanup operations are simulated
        """
        self.dry_run = dry_run
        self.cached_analysis: Analysis | None = None
        self.handlers: dict[str, Callable[..., dict[str, Any]]] = {
            "scan_disk": self._scan_disk,
            "get_disk_status": self._get_disk_status,
            "explain_category": self._explain_category,
            "clean_category": self._clean_category,
            "clean_multiple": self._clean_multiple,
            "list_categories": self._list_categories,
            # New comprehensive tools
            "find_large_files": self._find_large_files,
            "analyze_directory": self._analyze_directory,
            "find_old_files": self._find_old_files,
            "run_command": self._run_command,
            "find_mail_attachments": self._find_mail_attachments,
            "find_app_data": self._find_app_data,
            "uninstall_app": self._uninstall_app,
            "find_duplicates": self._find_duplicates,
            # macOS-style storage tools
            "get_storage_breakdown": self._get_storage_breakdown,
            "list_applications": self._list_applications,
            "find_project_artifacts": self._find_project_artifacts,
            # Protection/whitelist tools
            "add_protection": self._add_protection,
            "remove_protection": self._remove_protection,
            "list_protections": self._list_protections,
        }

    def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool and return structured result.

        Args:
            name: Tool name
            args: Tool arguments

        Returns:
            Tool execution result as dict
        """
        handler = self.handlers.get(name)
        if not handler:
            return {"error": f"Unknown tool: {name}"}

        try:
            return handler(**args)
        except Exception as e:
            return {"error": str(e)}

    def _scan_disk(self, include_dev: bool = True) -> dict[str, Any]:
        """Scan disk for cleanable items."""
        self.cached_analysis = analyze_disk(include_dev=include_dev)

        # Format results
        results = []
        for item in self.cached_analysis.scan_results:
            if item.size_bytes > 0:
                results.append({
                    "category_id": item.category_id,
                    "name": item.category_name,
                    "size_human": item.size_human,
                    "size_bytes": item.size_bytes,
                    "risk": item.risk_level.value,
                })

        # Sort by size descending
        results.sort(key=lambda x: x["size_bytes"], reverse=True)

        disk = self.cached_analysis.disk_usage
        return {
            "disk_status": {
                "total_gb": disk.total_gb,
                "used_gb": disk.used_gb,
                "free_gb": disk.free_gb,
                "used_percent": disk.used_percent,
            },
            "cleanable_items": results,
            "total_safe_bytes": self.cached_analysis.total_safe_bytes,
            "total_review_bytes": self.cached_analysis.total_review_bytes,
            "total_cleanable_bytes": self.cached_analysis.total_cleanable_bytes,
        }

    def _get_disk_status(self) -> dict[str, Any]:
        """Get current disk usage."""
        disk = get_disk_usage()
        return {
            "total_gb": disk.total_gb,
            "used_gb": disk.used_gb,
            "free_gb": disk.free_gb,
            "used_percent": disk.used_percent,
        }

    def _explain_category(self, category_id: str) -> dict[str, Any]:
        """Get detailed category explanation."""
        info = explain_category(category_id)
        if not info:
            return {"error": f"Category not found: {category_id}"}
        return info

    def _clean_category(
        self, category_id: str, dry_run: bool | None = None
    ) -> dict[str, Any]:
        """Clean a specific category."""
        # Check if category is protected
        if is_category_protected(category_id):
            return {
                "success": False,
                "category_id": category_id,
                "error": f"Category '{category_id}' is protected. Use remove_protection to unprotect it first.",
                "protected": True,
            }

        # Use instance dry_run if not specified
        actual_dry_run = dry_run if dry_run is not None else self.dry_run

        cat = get_category(category_id)
        if not cat:
            return {"error": f"Category not found: {category_id}"}

        result = clean_category(category_id, dry_run=actual_dry_run)

        return {
            "success": result.success,
            "category_id": category_id,
            "category_name": cat.name,
            "command": cat.cleanup_command,  # Terminal command for manual execution
            "bytes_freed": result.bytes_freed,
            "files_deleted": result.files_deleted,
            "dry_run": actual_dry_run,
            "error": result.error,
        }

    def _clean_multiple(
        self, category_ids: list[str], dry_run: bool | None = None
    ) -> dict[str, Any]:
        """Clean multiple categories."""
        actual_dry_run = dry_run if dry_run is not None else self.dry_run

        results = []
        total_freed = 0
        total_files = 0

        for cat_id in category_ids:
            result = self._clean_category(cat_id, dry_run=actual_dry_run)
            results.append(result)
            if result.get("success"):
                total_freed += result.get("bytes_freed", 0)
                total_files += result.get("files_deleted", 0)

        return {
            "results": results,
            "total_bytes_freed": total_freed,
            "total_files_deleted": total_files,
            "dry_run": actual_dry_run,
        }

    def _list_categories(self) -> dict[str, Any]:
        """List all available categories."""
        categories = []
        for cat in get_all_categories():
            categories.append({
                "id": cat.id,
                "name": cat.name,
                "risk": cat.risk_level.value,
                "description": cat.description,
            })

        # Group by risk level
        safe = [c for c in categories if c["risk"] == "safe"]
        review = [c for c in categories if c["risk"] == "review"]
        risky = [c for c in categories if c["risk"] == "risky"]

        return {
            "safe": safe,
            "review": review,
            "risky": risky,
            "total_count": len(categories),
        }

    # New comprehensive tool handlers

    def _find_large_files(
        self, min_size_mb: int = 100, path: str = "~"
    ) -> dict[str, Any]:
        """Find large files."""
        return {"files": find_large_files(min_size_mb=min_size_mb, path=path)}

    def _analyze_directory(self, path: str) -> dict[str, Any]:
        """Analyze directory contents."""
        return analyze_directory(path)

    def _find_old_files(
        self, days: int = 180, path: str = "~/Downloads"
    ) -> dict[str, Any]:
        """Find old files."""
        return {"files": find_old_files(days=days, path=path)}

    def _run_command(self, command: str) -> dict[str, Any]:
        """Run a whitelisted command."""
        return run_command(command)

    def _find_mail_attachments(self, days: int = 365) -> dict[str, Any]:
        """Find old mail attachments."""
        return {"attachments": find_mail_attachments(days=days)}

    def _find_app_data(self, app_name: str) -> dict[str, Any]:
        """Find all data for an app."""
        return find_app_data(app_name)

    def _uninstall_app(
        self, app_name: str, dry_run: bool | None = None
    ) -> dict[str, Any]:
        """Uninstall an app and its data."""
        actual_dry_run = dry_run if dry_run is not None else self.dry_run
        return uninstall_app(app_name, dry_run=actual_dry_run)

    def _find_duplicates(
        self, path: str = "~", min_size_mb: int = 1
    ) -> dict[str, Any]:
        """Find duplicate files."""
        return find_duplicates(path=path, min_size_mb=min_size_mb)

    # macOS-style storage tool handlers

    def _get_storage_breakdown(self) -> dict[str, Any]:
        """Get storage breakdown by category like macOS Settings."""
        return get_storage_breakdown()

    def _list_applications(self, sort_by: str = "size") -> dict[str, Any]:
        """List all installed applications with sizes."""
        return list_applications(sort_by=sort_by)

    def _find_project_artifacts(self, min_age_days: int = 7) -> dict[str, Any]:
        """Find build artifacts in project directories."""
        return find_project_artifacts(min_age_days=min_age_days)

    # Protection/whitelist handlers

    def _add_protection(
        self, path: str | None = None, category_id: str | None = None
    ) -> dict[str, Any]:
        """Add protection for a path or category."""
        return add_protection(path=path, category_id=category_id)

    def _remove_protection(
        self, path: str | None = None, category_id: str | None = None
    ) -> dict[str, Any]:
        """Remove protection from a path or category."""
        return remove_protection(path=path, category_id=category_id)

    def _list_protections(self) -> dict[str, Any]:
        """List all protected paths and categories."""
        return list_protections()


def format_tool_result(result: dict[str, Any]) -> str:
    """Format tool result for display to user.

    Args:
        result: Tool execution result

    Returns:
        Formatted string for display
    """
    return json.dumps(result, indent=2)
