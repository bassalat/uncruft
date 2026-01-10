"""Rich terminal display for uncruft."""

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

from uncruft.models import Analysis, CleanupResult, DiskUsage, RiskLevel, ScanResult

console = Console()


def risk_icon(risk_level: RiskLevel) -> str:
    """Get icon for risk level."""
    icons = {
        RiskLevel.SAFE: "[green]✓[/green]",
        RiskLevel.REVIEW: "[yellow]![/yellow]",
        RiskLevel.RISKY: "[red]✗[/red]",
    }
    return icons.get(risk_level, "?")


def risk_label(risk_level: RiskLevel) -> str:
    """Get styled label for risk level."""
    labels = {
        RiskLevel.SAFE: "[green]Safe[/green]",
        RiskLevel.REVIEW: "[yellow]Review[/yellow]",
        RiskLevel.RISKY: "[red]Risky[/red]",
    }
    return labels.get(risk_level, "Unknown")


def format_size(size_bytes: int) -> str:
    """Format bytes to human-readable string (decimal units like macOS)."""
    if size_bytes >= 1000**3:
        return f"{size_bytes / (1000**3):.1f} GB"
    elif size_bytes >= 1000**2:
        return f"{size_bytes / (1000**2):.1f} MB"
    elif size_bytes >= 1000:
        return f"{size_bytes / 1000:.1f} KB"
    else:
        return f"{size_bytes} B"


def show_disk_summary(disk_usage: DiskUsage) -> None:
    """Display disk usage summary."""
    used_percent = disk_usage.used_percent

    # Color based on usage
    if used_percent >= 90:
        color = "red"
    elif used_percent >= 75:
        color = "yellow"
    else:
        color = "green"

    table = Table(title="Disk Summary", show_header=True, header_style="bold")
    table.add_column("Total", justify="right")
    table.add_column("Used", justify="right")
    table.add_column("Free", justify="right")
    table.add_column("Usage", justify="right")

    table.add_row(
        f"{disk_usage.total_gb:.0f} GB",
        f"{disk_usage.used_gb:.0f} GB",
        f"[bold]{disk_usage.free_gb:.0f} GB[/bold]",
        f"[{color}]{used_percent:.0f}%[/{color}]",
    )

    console.print(table)
    console.print()


def show_analysis(analysis: Analysis) -> None:
    """Display full analysis results."""
    # Disk summary
    show_disk_summary(analysis.disk_usage)

    # Safe items
    if analysis.safe_items:
        console.print("[bold green]✓ Safe to Clean[/bold green]")
        table = Table(show_header=True, header_style="bold green")
        table.add_column("Category", style="green")
        table.add_column("Size", justify="right")
        table.add_column("Files", justify="right")
        table.add_column("Path")

        for item in sorted(analysis.safe_items, key=lambda x: x.size_bytes, reverse=True):
            if item.size_bytes > 0:
                table.add_row(
                    item.category_name,
                    format_size(item.size_bytes),
                    str(item.file_count),
                    item.path,
                )

        console.print(table)
        console.print(
            f"[green]Total safe to clean: {format_size(analysis.total_safe_bytes)}[/green]"
        )
        console.print()

    # Review items
    if analysis.review_items:
        console.print("[bold yellow]! Review Needed[/bold yellow]")
        table = Table(show_header=True, header_style="bold yellow")
        table.add_column("Category", style="yellow")
        table.add_column("Size", justify="right")
        table.add_column("Files", justify="right")
        table.add_column("Path")

        for item in sorted(analysis.review_items, key=lambda x: x.size_bytes, reverse=True):
            if item.size_bytes > 0:
                table.add_row(
                    item.category_name,
                    format_size(item.size_bytes),
                    str(item.file_count),
                    item.path,
                )

        console.print(table)
        console.print(
            f"[yellow]Total needs review: {format_size(analysis.total_review_bytes)}[/yellow]"
        )
        console.print()

    # Summary
    total_cleanable = analysis.total_safe_bytes + analysis.total_review_bytes
    console.print(
        Panel(
            f"[bold]Potential space to reclaim:[/bold] {format_size(total_cleanable)}\n"
            f"  Safe: {format_size(analysis.total_safe_bytes)}\n"
            f"  Review: {format_size(analysis.total_review_bytes)}",
            title="Summary",
            border_style="blue",
        )
    )


def show_cleanup_preview(items: list[ScanResult], dry_run: bool = False) -> None:
    """Display cleanup preview."""
    if dry_run:
        console.print("[yellow]DRY RUN - No files will be deleted[/yellow]\n")

    table = Table(title="Cleanup Preview", show_header=True, header_style="bold")
    table.add_column("", width=3)
    table.add_column("Category")
    table.add_column("Size", justify="right")
    table.add_column("Risk")

    total = 0
    for item in items:
        table.add_row(
            risk_icon(item.risk_level),
            item.category_name,
            format_size(item.size_bytes),
            risk_label(item.risk_level),
        )
        total += item.size_bytes

    console.print(table)
    console.print(f"\n[bold]Total to clean: {format_size(total)}[/bold]")


def show_cleanup_progress() -> Progress:
    """Create and return a progress bar for cleanup."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    )


def show_cleanup_result(result: CleanupResult) -> None:
    """Display result of a single cleanup operation."""
    if result.success:
        console.print(
            f"  [green]✓[/green] {result.category_id}: {format_size(result.bytes_freed)} freed"
        )
    else:
        console.print(f"  [red]✗[/red] {result.category_id}: {result.error}")


def show_cleanup_summary(
    results: list[CleanupResult],
    disk_before: DiskUsage,
    disk_after: DiskUsage,
) -> None:
    """Display cleanup summary."""
    total_freed = sum(r.bytes_freed for r in results if r.success)
    success_count = sum(1 for r in results if r.success)
    failure_count = sum(1 for r in results if not r.success)

    console.print()
    console.print("[bold green]Cleanup Complete![/bold green]")
    console.print()

    table = Table(show_header=False)
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Space freed", format_size(total_freed))
    table.add_row("Items cleaned", str(success_count))
    if failure_count > 0:
        table.add_row("[red]Failed[/red]", str(failure_count))
    table.add_row("Free space before", f"{disk_before.free_gb:.1f} GB")
    table.add_row("Free space after", f"[bold green]{disk_after.free_gb:.1f} GB[/bold green]")

    console.print(table)


def show_category_explanation(category_info: dict) -> None:
    """Display detailed category explanation with rich knowledge base content."""
    risk = category_info["risk_level"]
    risk_color = {"safe": "green", "review": "yellow", "risky": "red"}.get(risk, "white")

    # Header with name and risk level
    console.print(Panel(
        f"[bold]{category_info['name']}[/bold]\n"
        f"Risk Level: [{risk_color}]{risk.upper()}[/{risk_color}]",
        border_style=risk_color,
    ))

    # Show paths or patterns for recursive categories
    if category_info.get("is_recursive"):
        console.print("\n[bold]Scan Patterns:[/bold]")
        for pattern in category_info.get("glob_patterns", []):
            console.print(f"  • {pattern}")
        console.print("\n[bold]Search Locations:[/bold]")
        for root in category_info.get("search_roots", [])[:5]:  # Limit to 5
            console.print(f"  • {root}")
    elif category_info.get("paths"):
        console.print("\n[bold]Paths:[/bold]")
        for path in category_info["paths"]:
            console.print(f"  • {path}")

    # Rich explanation - "What is it?"
    console.print()
    if category_info.get("what_is_it"):
        console.print(Panel(
            category_info["what_is_it"],
            title="[bold cyan]What is it?[/bold cyan]",
            border_style="cyan",
        ))
    else:
        console.print(f"[bold]What is it?[/bold]\n{category_info['description']}")

    # "Why safe to delete?"
    if category_info.get("why_safe"):
        console.print(Panel(
            category_info["why_safe"],
            title="[bold green]Why safe to delete?[/bold green]",
            border_style="green",
        ))
    else:
        console.print()
        console.print(f"[bold]What happens if deleted?[/bold]\n{category_info['consequences']}")

    # Space impact
    if category_info.get("space_impact"):
        console.print(Panel(
            category_info["space_impact"],
            title="[bold yellow]Space Impact[/bold yellow]",
            border_style="yellow",
        ))

    # Recovery steps
    if category_info.get("recovery_steps"):
        console.print("\n[bold]Recovery Steps:[/bold]")
        for i, step in enumerate(category_info["recovery_steps"], 1):
            console.print(f"  {i}. {step}")
    else:
        console.print()
        console.print(f"[bold]How to recover?[/bold]\n{category_info['recovery']}")

    # Pro tip
    if category_info.get("pro_tip"):
        console.print()
        console.print(Panel(
            f"[bold]Tip:[/bold] {category_info['pro_tip']}",
            border_style="blue",
        ))

    # Edge cases / warnings
    if category_info.get("edge_cases"):
        console.print()
        console.print(Panel(
            f"[bold]Warning:[/bold] {category_info['edge_cases']}",
            border_style="red",
        ))

    # Native cleanup command
    if category_info.get("cleanup_command"):
        console.print()
        console.print(f"[dim]Native cleanup command:[/dim] [bold]{category_info['cleanup_command']}[/bold]")


def show_status(disk_usage: DiskUsage) -> None:
    """Display quick status."""
    used_percent = disk_usage.used_percent

    if used_percent >= 90:
        status = "[red]CRITICAL[/red]"
    elif used_percent >= 75:
        status = "[yellow]WARNING[/yellow]"
    else:
        status = "[green]OK[/green]"

    console.print(f"Disk Status: {status}")
    console.print(f"  Total: {disk_usage.total_gb:.0f} GB")
    console.print(f"  Used:  {disk_usage.used_gb:.0f} GB ({used_percent:.0f}%)")
    console.print(f"  Free:  {disk_usage.free_gb:.0f} GB")


def show_scanning_progress() -> Progress:
    """Create progress bar for scanning."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    )


def confirm_action(message: str) -> bool:
    """Ask for confirmation."""
    from rich.prompt import Confirm

    return Confirm.ask(message)
