"""Custom widgets for uncruft TUI."""

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.reactive import reactive
from textual.widgets import Static

from uncruft.analyzer import explain_category
from uncruft.models import DiskUsage, RiskLevel


class DiskUsageBar(Static):
    """Visual disk usage indicator with progress bar."""

    usage_percent: reactive[float] = reactive(0.0)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.disk_usage: DiskUsage | None = None

    def update_usage(self, disk_usage: DiskUsage) -> None:
        """Update with new disk usage data."""
        self.disk_usage = disk_usage
        self.usage_percent = disk_usage.used_percent

    def render(self) -> str:
        """Render the disk usage bar."""
        if not self.disk_usage:
            return "[dim]Loading disk usage...[/dim]"

        du = self.disk_usage
        bar_width = 40
        filled = int(bar_width * du.used_percent / 100)
        empty = bar_width - filled

        # Color based on usage
        if du.used_percent >= 90:
            color = "red"
            status = "CRITICAL"
        elif du.used_percent >= 75:
            color = "yellow"
            status = "WARNING"
        else:
            color = "green"
            status = "OK"

        bar = f"[{color}]{'█' * filled}[/{color}][dim]{'░' * empty}[/dim]"

        return (
            f"[bold]Disk Usage:[/bold] [{color}]{status}[/{color}]\n"
            f"{bar} {du.used_percent:.0f}%\n"
            f"[dim]Free: {du.free_gb:.0f} GB / Total: {du.total_gb:.0f} GB[/dim]"
        )


class CategoryDetail(VerticalScroll):
    """Panel showing detailed category information."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_category: str | None = None
        self.expanded: bool = False

    def compose(self) -> ComposeResult:
        yield Static("Select a category to see details", id="detail-content")

    def show_category(self, category_id: str, expanded: bool = False) -> None:
        """Display information about a category."""
        self.current_category = category_id
        self.expanded = expanded

        info = explain_category(category_id)
        if not info:
            self._update_content("[red]Category not found[/red]")
            return

        # Build rich content
        risk = info.get("risk_level", "unknown")
        risk_color = {"safe": "green", "review": "yellow", "risky": "red"}.get(risk, "white")

        content_parts = [
            f"[bold]{info['name']}[/bold]",
            f"Risk: [{risk_color}]{risk.upper()}[/{risk_color}]",
            "",
        ]

        # What is it?
        if info.get("what_is_it"):
            content_parts.append("[bold cyan]What is it?[/bold cyan]")
            content_parts.append(info["what_is_it"])
            content_parts.append("")
        elif info.get("description"):
            content_parts.append("[bold]Description[/bold]")
            content_parts.append(info["description"])
            content_parts.append("")

        # Only show more details if expanded or has rich content
        if expanded or info.get("why_safe"):
            # Why safe?
            if info.get("why_safe"):
                content_parts.append("[bold green]Why safe to delete?[/bold green]")
                content_parts.append(info["why_safe"])
                content_parts.append("")

            # Space impact
            if info.get("space_impact"):
                content_parts.append("[bold yellow]Space Impact[/bold yellow]")
                content_parts.append(info["space_impact"])
                content_parts.append("")

            # Recovery steps
            if info.get("recovery_steps"):
                content_parts.append("[bold]Recovery Steps[/bold]")
                for i, step in enumerate(info["recovery_steps"], 1):
                    content_parts.append(f"  {i}. {step}")
                content_parts.append("")

            # Pro tip
            if info.get("pro_tip"):
                content_parts.append("[bold blue]Pro Tip[/bold blue]")
                content_parts.append(info["pro_tip"])
                content_parts.append("")

            # Edge cases
            if info.get("edge_cases"):
                content_parts.append("[bold red]Warning[/bold red]")
                content_parts.append(info["edge_cases"])
                content_parts.append("")

        # Paths or patterns
        if info.get("is_recursive"):
            content_parts.append("[dim]Patterns:[/dim]")
            for pattern in info.get("glob_patterns", [])[:3]:
                content_parts.append(f"  [dim]{pattern}[/dim]")
        elif info.get("paths"):
            content_parts.append("[dim]Paths:[/dim]")
            for path in info["paths"][:3]:
                content_parts.append(f"  [dim]{path}[/dim]")
            if len(info["paths"]) > 3:
                content_parts.append(f"  [dim]...and {len(info['paths']) - 3} more[/dim]")

        # Cleanup command
        if info.get("cleanup_command"):
            content_parts.append("")
            content_parts.append(f"[dim]Native command:[/dim] {info['cleanup_command']}")

        self._update_content("\n".join(content_parts))

    def _update_content(self, content: str) -> None:
        """Update the detail content."""
        try:
            detail = self.query_one("#detail-content", Static)
            detail.update(content)
        except Exception:
            pass  # Widget may not be mounted yet
