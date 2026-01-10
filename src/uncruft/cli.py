"""CLI interface for uncruft."""

from typing import Optional

import typer
from rich.console import Console

from uncruft import __version__
from uncruft.analyzer import analyze_disk, explain_category, get_recommendations
from uncruft.categories import CATEGORIES, get_all_categories
from uncruft.cleaner import clean_category, clean_safe_items, validate_cleanup_request
from uncruft.display import (
    confirm_action,
    console,
    show_analysis,
    show_category_explanation,
    show_cleanup_preview,
    show_cleanup_result,
    show_cleanup_summary,
    show_scanning_progress,
    show_status,
)
from uncruft.models import RiskLevel
from uncruft.scanner import get_disk_usage

# Create Typer app
app = typer.Typer(
    name="uncruft",
    help="AI-powered Mac disk cleanup CLI - remove cruft safely",
    add_completion=False,
)


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"uncruft version {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """uncruft - AI-powered Mac disk cleanup CLI."""
    # If no command specified, launch menu
    if ctx.invoked_subcommand is None:
        ctx.invoke(menu)


@app.command()
def analyze(
    dev: bool = typer.Option(
        False,
        "--dev",
        help="Include developer artifacts (node_modules, .venv, build dirs) - slower but more thorough",
    ),
) -> None:
    """Analyze disk usage and show recommendations."""
    if dev:
        console.print("[bold blue]Analyzing disk usage (including developer artifacts)...[/bold blue]\n")
        console.print("[dim]This may take a minute - scanning for node_modules, .venv, etc.[/dim]\n")
    else:
        console.print("[bold blue]Analyzing disk usage...[/bold blue]\n")

    # Estimate total categories to scan
    all_cats = get_all_categories()
    regular_cats = [c for c in all_cats if not c.is_recursive]
    recursive_cats = [c for c in all_cats if c.is_recursive]
    total_cats = len(regular_cats) + (len(recursive_cats) if dev else 0)

    # Show progress
    with show_scanning_progress() as progress:
        task = progress.add_task("Scanning categories...", total=total_cats)

        def update_progress(name: str, current: int, total: int):
            progress.update(task, completed=current, description=f"Scanning {name}...")

        analysis = analyze_disk(progress_callback=update_progress, include_dev=dev)

    console.print()
    show_analysis(analysis)

    # Show next steps
    if analysis.safe_items:
        console.print()
        console.print("[dim]Run [bold]uncruft clean --safe[/bold] to clean safe items[/dim]")
        console.print(
            "[dim]Run [bold]uncruft explain <category>[/bold] to learn more about a category[/dim]"
        )

    if not dev:
        console.print()
        console.print(
            "[dim]Tip: Run [bold]uncruft analyze --dev[/bold] to find node_modules, .venv, and build artifacts[/dim]"
        )


@app.command()
def clean(
    safe: bool = typer.Option(False, "--safe", help="Clean only safe items"),
    category: Optional[str] = typer.Option(
        None, "--category", "-c", help="Clean specific category"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Simulate without deleting"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip confirmation prompts"),
) -> None:
    """Execute cleanup operations."""
    if not safe and not category:
        console.print("[red]Error: Specify --safe or --category[/red]")
        console.print("  uncruft clean --safe           # Clean all safe items")
        console.print("  uncruft clean --category npm   # Clean specific category")
        raise typer.Exit(1)

    # Get disk usage before
    disk_before = get_disk_usage()

    if category:
        # Clean specific category
        if category not in CATEGORIES:
            console.print(f"[red]Unknown category: {category}[/red]")
            console.print("\nAvailable categories:")
            for cat_id in sorted(CATEGORIES.keys()):
                console.print(f"  • {cat_id}")
            raise typer.Exit(1)

        cat = CATEGORIES[category]
        console.print(f"[bold]Cleaning: {cat.name}[/bold]")
        console.print(f"Risk level: {cat.risk_level.value}")

        if not yes and not dry_run:
            if not confirm_action("Proceed with cleanup?"):
                console.print("[yellow]Cancelled[/yellow]")
                raise typer.Exit(0)

        result = clean_category(category, dry_run=dry_run)
        show_cleanup_result(result)

        if not dry_run:
            disk_after = get_disk_usage()
            console.print(f"\nSpace freed: {disk_after.free_gb - disk_before.free_gb:.1f} GB")

    elif safe:
        # Clean all safe items
        console.print("[bold]Scanning for safe items to clean...[/bold]\n")

        with show_scanning_progress() as progress:
            task = progress.add_task("Scanning...", total=len(CATEGORIES))

            def update_progress(name: str, current: int, total: int):
                progress.update(task, completed=current)

            analysis = analyze_disk(progress_callback=update_progress)

        safe_items = [
            r for r in analysis.scan_results if r.risk_level == RiskLevel.SAFE and r.size_bytes > 0
        ]

        if not safe_items:
            console.print("[yellow]No safe items to clean.[/yellow]")
            raise typer.Exit(0)

        # Show preview
        console.print()
        show_cleanup_preview(safe_items, dry_run=dry_run)

        # Validate
        total_bytes = sum(r.size_bytes for r in safe_items)
        category_ids = [r.category_id for r in safe_items]
        is_valid, error = validate_cleanup_request(category_ids, total_bytes)

        if not is_valid:
            console.print(f"[red]Safety check failed: {error}[/red]")
            raise typer.Exit(1)

        # Confirm
        if not yes and not dry_run:
            console.print()
            if not confirm_action("Proceed with cleanup?"):
                console.print("[yellow]Cancelled[/yellow]")
                raise typer.Exit(0)

        # Execute cleanup
        console.print("\n[bold]Cleaning...[/bold]")

        def cleanup_progress(name: str, current: int, total: int):
            pass  # Progress shown via results

        results = clean_safe_items(safe_items, dry_run=dry_run, progress_callback=cleanup_progress)

        # Show results
        for result in results:
            show_cleanup_result(result)

        if not dry_run:
            disk_after = get_disk_usage()
            show_cleanup_summary(results, disk_before, disk_after)


@app.command()
def explain(
    category: str = typer.Argument(..., help="Category to explain"),
) -> None:
    """Explain a category in detail."""
    info = explain_category(category)

    if not info:
        console.print(f"[red]Unknown category: {category}[/red]")
        console.print("\nAvailable categories:")
        for cat_id in sorted(CATEGORIES.keys()):
            cat = CATEGORIES[cat_id]
            console.print(f"  • [bold]{cat_id}[/bold] - {cat.name}")
        raise typer.Exit(1)

    show_category_explanation(info)


@app.command()
def status() -> None:
    """Show current disk usage summary."""
    disk_usage = get_disk_usage()
    show_status(disk_usage)


@app.command()
def history() -> None:
    """Show past cleanup operations."""
    console.print("[yellow]Cleanup history not yet implemented.[/yellow]")
    console.print("[dim]This feature will be available in a future version.[/dim]")


@app.command()
def config() -> None:
    """Open or show configuration."""
    console.print("[yellow]Configuration not yet implemented.[/yellow]")
    console.print("[dim]This feature will be available in a future version.[/dim]")


@app.command(name="list")
def list_categories() -> None:
    """List all cleanup categories."""
    console.print("[bold]Available Categories[/bold]\n")

    all_cats = get_all_categories()

    # Separate regular and developer (recursive) categories
    regular_cats = [c for c in all_cats if not c.is_recursive]
    dev_cats = [c for c in all_cats if c.is_recursive]

    # Group regular categories by risk level
    safe = [c for c in regular_cats if c.risk_level == RiskLevel.SAFE]
    review = [c for c in regular_cats if c.risk_level == RiskLevel.REVIEW]
    risky = [c for c in regular_cats if c.risk_level == RiskLevel.RISKY]

    if safe:
        console.print("[green]Safe to Clean:[/green]")
        for cat in safe:
            console.print(f"  • [bold]{cat.id}[/bold] - {cat.name}")
        console.print()

    if review:
        console.print("[yellow]Review Needed:[/yellow]")
        for cat in review:
            console.print(f"  • [bold]{cat.id}[/bold] - {cat.name}")
        console.print()

    if risky:
        console.print("[red]High Risk:[/red]")
        for cat in risky:
            console.print(f"  • [bold]{cat.id}[/bold] - {cat.name}")
        console.print()

    # Developer categories (recursive scanning)
    if dev_cats:
        console.print("[cyan]Developer Artifacts (use --dev flag):[/cyan]")
        for cat in dev_cats:
            risk_color = "green" if cat.risk_level == RiskLevel.SAFE else "yellow"
            console.print(f"  • [bold]{cat.id}[/bold] - {cat.name} [{risk_color}]{cat.risk_level.value}[/{risk_color}]")
        console.print()

    console.print("[dim]Run [bold]uncruft explain <category>[/bold] for details[/dim]")
    console.print("[dim]Run [bold]uncruft analyze --dev[/bold] to scan for developer artifacts[/dim]")


@app.command()
def menu(
    dry_run: bool = typer.Option(False, "--dry-run", help="Simulate cleanup without deleting"),
    manual: bool = typer.Option(False, "--manual", help="Only show commands, never execute"),
) -> None:
    """Interactive menu-driven cleanup (default).

    This is the default command when running 'uncruft' without arguments.

    Uses menus for actions with AI for natural language input interpretation.
    """
    from uncruft.ai.menu import start_menu

    start_menu(console=console, dry_run=dry_run, manual_mode=manual)


@app.command()
def chat(
    dry_run: bool = typer.Option(False, "--dry-run", help="Simulate cleanup without deleting"),
    manual: bool = typer.Option(False, "--manual", help="Only show commands, never execute (for manual cleanup)"),
) -> None:
    """AI chat interface (experimental).

    Natural language conversation for disk cleanup.
    Use 'uncruft menu' for more reliable menu-driven interface.
    """
    from uncruft.ai.conversation import start_chat

    start_chat(console=console, dry_run=dry_run, manual_mode=manual)


@app.command()
def tui(
    dry_run: bool = typer.Option(False, "--dry-run", help="Simulate cleanup without deleting"),
    no_dev: bool = typer.Option(False, "--no-dev", help="Skip developer artifact scanning"),
) -> None:
    """Launch interactive TUI interface (legacy)."""
    try:
        from uncruft.tui import run_tui

        run_tui(dry_run=dry_run, include_dev=not no_dev)
    except ImportError:
        console.print("[red]TUI not available.[/red]")
        console.print("Install with: [bold]pip install uncruft[tui][/bold]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
