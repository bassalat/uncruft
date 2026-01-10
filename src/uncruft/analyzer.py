"""Analysis and recommendation logic for uncruft."""

from datetime import datetime

from uncruft.categories import CATEGORIES, get_category
from uncruft.models import Analysis, Category, DiskUsage, RiskLevel, ScanResult
from uncruft.scanner import get_disk_usage, scan_all_categories


def analyze_disk(
    progress_callback=None,
    include_dev: bool = False,
) -> Analysis:
    """
    Perform full disk analysis.

    Args:
        progress_callback: Optional callback for progress updates
        include_dev: Whether to include recursive developer category scanning

    Returns:
        Analysis object with disk usage and scan results
    """
    # Get overall disk usage
    disk_usage = get_disk_usage()

    # Scan all categories
    scan_results = scan_all_categories(
        progress_callback=progress_callback,
        include_dev=include_dev,
    )

    return Analysis(
        timestamp=datetime.now(),
        disk_usage=disk_usage,
        scan_results=scan_results,
    )


def get_recommendations(analysis: Analysis) -> dict[str, list[ScanResult]]:
    """
    Get categorized recommendations from analysis.

    Args:
        analysis: Analysis object

    Returns:
        Dict with 'safe', 'review', 'risky' lists of ScanResults
    """
    return {
        "safe": analysis.safe_items,
        "review": analysis.review_items,
        "risky": analysis.risky_items,
    }


def explain_category(category_id: str) -> dict | None:
    """
    Get detailed explanation for a category.

    Args:
        category_id: Category ID to explain

    Returns:
        Dict with category details, or None if not found
    """
    category = get_category(category_id)
    if not category:
        return None

    result = {
        "id": category.id,
        "name": category.name,
        "paths": category.paths,
        "risk_level": category.risk_level.value,
        "description": category.description,
        "consequences": category.consequences,
        "recovery": category.recovery,
        "cleanup_command": category.cleanup_command,
        # Recursive scanning info
        "is_recursive": category.is_recursive,
        "glob_patterns": category.glob_patterns,
        "search_roots": category.search_roots,
        # Rich knowledge base content
        "what_is_it": category.what_is_it,
        "why_safe": category.why_safe,
        "space_impact": category.space_impact,
        "recovery_steps": category.recovery_steps,
        "pro_tip": category.pro_tip,
        "edge_cases": category.edge_cases,
    }

    return result


def get_safe_cleanup_targets(analysis: Analysis) -> list[ScanResult]:
    """
    Get list of safe cleanup targets sorted by size.

    Args:
        analysis: Analysis object

    Returns:
        List of ScanResults that are safe to clean
    """
    return sorted(analysis.safe_items, key=lambda r: r.size_bytes, reverse=True)


def estimate_cleanup_savings(analysis: Analysis, include_review: bool = False) -> int:
    """
    Estimate total bytes that can be freed.

    Args:
        analysis: Analysis object
        include_review: Whether to include 'review' items

    Returns:
        Total bytes that can be freed
    """
    total = analysis.total_safe_bytes
    if include_review:
        total += analysis.total_review_bytes
    return total


def filter_by_minimum_size(results: list[ScanResult], min_bytes: int) -> list[ScanResult]:
    """
    Filter scan results by minimum size.

    Args:
        results: List of scan results
        min_bytes: Minimum size in bytes

    Returns:
        Filtered list of results
    """
    return [r for r in results if r.size_bytes >= min_bytes]


def get_category_by_size(analysis: Analysis, top_n: int = 10) -> list[ScanResult]:
    """
    Get top N categories by size.

    Args:
        analysis: Analysis object
        top_n: Number of top categories to return

    Returns:
        List of top N ScanResults by size
    """
    sorted_results = sorted(
        [r for r in analysis.scan_results if r.size_bytes > 0],
        key=lambda r: r.size_bytes,
        reverse=True,
    )
    return sorted_results[:top_n]


def format_size(size_bytes: int) -> str:
    """
    Format bytes to human-readable string.

    Args:
        size_bytes: Size in bytes

    Returns:
        Human-readable size string
    """
    if size_bytes >= 1000**3:
        return f"{size_bytes / (1000**3):.1f} GB"
    elif size_bytes >= 1000**2:
        return f"{size_bytes / (1000**2):.1f} MB"
    elif size_bytes >= 1000:
        return f"{size_bytes / 1000:.1f} KB"
    else:
        return f"{size_bytes} B"
