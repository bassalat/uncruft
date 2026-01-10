"""Data models for uncruft."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Risk level for cleanup categories."""

    SAFE = "safe"  # No data loss, auto-recoverable
    REVIEW = "review"  # Manual recovery, user judgment needed
    RISKY = "risky"  # Potential data loss, expert knowledge required


class Category(BaseModel):
    """Definition of a cleanup category."""

    # Core identification
    id: str = Field(..., description="Unique identifier for the category")
    name: str = Field(..., description="Human-readable name")
    paths: list[str] = Field(default_factory=list, description="Paths to scan (supports ~ expansion)")
    risk_level: RiskLevel = Field(..., description="Risk level for this category")

    # Recursive scanning support
    glob_patterns: list[str] = Field(
        default_factory=list,
        description="Glob patterns for recursive discovery (e.g., '**/node_modules')",
    )
    search_roots: list[str] = Field(
        default_factory=list,
        description="Root directories to search for glob patterns",
    )
    is_recursive: bool = Field(
        default=False,
        description="Whether this category uses recursive directory discovery",
    )
    min_size_bytes: int = Field(
        default=0,
        description="Minimum size in bytes to include in results",
    )

    # Basic explanation (backwards compatible)
    description: str = Field(..., description="What this category contains")
    consequences: str = Field(..., description="What happens if deleted")
    recovery: str = Field(..., description="How to recover if needed")
    cleanup_command: Optional[str] = Field(
        None, description="Optional native cleanup command (e.g., 'conda clean --all')"
    )

    # Rich explanation fields (AI-quality knowledge base)
    what_is_it: Optional[str] = Field(
        None,
        description="Detailed technical explanation of what these files are",
    )
    why_safe: Optional[str] = Field(
        None,
        description="Detailed explanation of why it's safe to delete",
    )
    space_impact: Optional[str] = Field(
        None,
        description="Typical size range and how fast it regrows",
    )
    recovery_steps: list[str] = Field(
        default_factory=list,
        description="Step-by-step recovery instructions",
    )
    pro_tip: Optional[str] = Field(
        None,
        description="Developer-focused advice or best practices",
    )
    edge_cases: Optional[str] = Field(
        None,
        description="When NOT to delete, gotchas to watch for",
    )


class ScanResult(BaseModel):
    """Result of scanning a single category."""

    category_id: str = Field(..., description="Category identifier")
    category_name: str = Field(..., description="Human-readable category name")
    path: str = Field(..., description="Path that was scanned")
    size_bytes: int = Field(..., description="Total size in bytes")
    file_count: int = Field(0, description="Number of files")
    dir_count: int = Field(0, description="Number of directories")
    risk_level: RiskLevel = Field(..., description="Risk level")
    exists: bool = Field(True, description="Whether the path exists")
    error: Optional[str] = Field(None, description="Error message if scan failed")

    @property
    def size_gb(self) -> float:
        """Size in gigabytes (decimal, like macOS)."""
        return self.size_bytes / (1000**3)

    @property
    def size_mb(self) -> float:
        """Size in megabytes (decimal, like macOS)."""
        return self.size_bytes / (1000**2)

    @property
    def size_human(self) -> str:
        """Human-readable size string (decimal units like macOS)."""
        if self.size_bytes >= 1000**3:
            return f"{self.size_gb:.1f} GB"
        elif self.size_bytes >= 1000**2:
            return f"{self.size_mb:.1f} MB"
        elif self.size_bytes >= 1000:
            return f"{self.size_bytes / 1000:.1f} KB"
        else:
            return f"{self.size_bytes} B"


class DiskUsage(BaseModel):
    """Overall disk usage information."""

    total_bytes: int = Field(..., description="Total disk size in bytes")
    used_bytes: int = Field(..., description="Used space in bytes")
    free_bytes: int = Field(..., description="Free space in bytes")
    mount_point: str = Field("/", description="Mount point")

    @property
    def total_gb(self) -> float:
        """Total size in GB (decimal, like macOS)."""
        return self.total_bytes / (1000**3)

    @property
    def used_gb(self) -> float:
        """Used space in GB (decimal, like macOS)."""
        return self.used_bytes / (1000**3)

    @property
    def free_gb(self) -> float:
        """Free space in GB (decimal, like macOS)."""
        return self.free_bytes / (1000**3)

    @property
    def used_percent(self) -> float:
        """Percentage of disk used."""
        return (self.used_bytes / self.total_bytes) * 100 if self.total_bytes > 0 else 0


class Analysis(BaseModel):
    """Complete disk analysis result."""

    timestamp: datetime = Field(default_factory=datetime.now)
    disk_usage: DiskUsage
    scan_results: list[ScanResult] = Field(default_factory=list)

    @property
    def safe_items(self) -> list[ScanResult]:
        """Items that are safe to clean."""
        return [r for r in self.scan_results if r.risk_level == RiskLevel.SAFE and r.size_bytes > 0]

    @property
    def review_items(self) -> list[ScanResult]:
        """Items that need user review."""
        return [
            r for r in self.scan_results if r.risk_level == RiskLevel.REVIEW and r.size_bytes > 0
        ]

    @property
    def risky_items(self) -> list[ScanResult]:
        """Items that are risky to clean."""
        return [
            r for r in self.scan_results if r.risk_level == RiskLevel.RISKY and r.size_bytes > 0
        ]

    @property
    def total_safe_bytes(self) -> int:
        """Total bytes that can be safely cleaned."""
        return sum(r.size_bytes for r in self.safe_items)

    @property
    def total_review_bytes(self) -> int:
        """Total bytes that need review."""
        return sum(r.size_bytes for r in self.review_items)

    @property
    def total_cleanable_bytes(self) -> int:
        """Total bytes that could potentially be cleaned."""
        return sum(r.size_bytes for r in self.scan_results if r.size_bytes > 0)


class CleanupResult(BaseModel):
    """Result of a cleanup operation."""

    category_id: str = Field(..., description="Category that was cleaned")
    path: str = Field(..., description="Path that was cleaned")
    bytes_freed: int = Field(..., description="Bytes freed by cleanup")
    files_deleted: int = Field(0, description="Number of files deleted")
    success: bool = Field(True, description="Whether cleanup succeeded")
    error: Optional[str] = Field(None, description="Error message if failed")
    dry_run: bool = Field(False, description="Whether this was a dry run")


class CleanupSession(BaseModel):
    """A complete cleanup session with multiple results."""

    id: str = Field(..., description="Unique session ID")
    timestamp: datetime = Field(default_factory=datetime.now)
    results: list[CleanupResult] = Field(default_factory=list)
    disk_before: DiskUsage
    disk_after: Optional[DiskUsage] = None

    @property
    def total_bytes_freed(self) -> int:
        """Total bytes freed in this session."""
        return sum(r.bytes_freed for r in self.results if r.success)

    @property
    def success_count(self) -> int:
        """Number of successful cleanups."""
        return sum(1 for r in self.results if r.success)

    @property
    def failure_count(self) -> int:
        """Number of failed cleanups."""
        return sum(1 for r in self.results if not r.success)
