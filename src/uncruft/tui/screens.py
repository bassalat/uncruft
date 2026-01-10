"""TUI screens for uncruft."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Label,
    LoadingIndicator,
    ProgressBar,
    Static,
)

from uncruft.analyzer import analyze_disk, explain_category
from uncruft.categories import get_category
from uncruft.cleaner import clean_category
from uncruft.models import RiskLevel, ScanResult
from uncruft.tui.widgets import CategoryDetail, DiskUsageBar


class MainScreen(Screen):
    """Main analysis screen with category browser."""

    BINDINGS = [
        Binding("enter", "view_details", "Details"),
        Binding("space", "toggle_select", "Select"),
        Binding("c", "cleanup", "Clean Selected"),
        Binding("a", "select_all_safe", "Select Safe"),
        Binding("u", "deselect_all", "Deselect All"),
        Binding("r", "refresh", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()

        with Container(id="main-container"):
            yield DiskUsageBar(id="disk-bar")

            with Horizontal(id="content"):
                with Vertical(id="left-panel"):
                    yield Static("[bold]Categories[/bold]", id="cat-header")
                    yield DataTable(id="category-table")
                    yield Static("", id="selection-info")

                with Vertical(id="right-panel"):
                    yield CategoryDetail(id="category-detail")

        yield Footer()

    def on_mount(self) -> None:
        """Initialize the screen."""
        table = self.query_one("#category-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("", "Category", "Size", "Risk")

        # Start loading data
        self.refresh_data()

    def refresh_data(self) -> None:
        """Scan and refresh category data."""
        self.notify("Scanning disk...", timeout=2)

        # Run analysis in worker to not block UI
        self.run_worker(self._load_data, thread=True)

    async def _load_data(self) -> None:
        """Load data in background."""
        app = self.app

        def progress_callback(name, current, total):
            pass  # Could update a progress indicator

        app.analysis = analyze_disk(
            progress_callback=progress_callback,
            include_dev=app.include_dev,
        )

        # Update UI on main thread
        self.call_from_thread(self._update_table)

    def _update_table(self) -> None:
        """Update the table with scan results."""
        app = self.app
        table = self.query_one("#category-table", DataTable)
        disk_bar = self.query_one("#disk-bar", DiskUsageBar)

        # Clear existing rows
        table.clear()

        if not app.analysis:
            return

        # Update disk bar
        disk_bar.update_usage(app.analysis.disk_usage)

        # Add rows for each scan result with size > 0
        for result in app.analysis.scan_results:
            if result.size_bytes > 0:
                is_selected = result.category_id in app.selected_items
                checkbox = "[green]X[/green]" if is_selected else "[ ]"

                risk_style = {
                    RiskLevel.SAFE: "[green]safe[/green]",
                    RiskLevel.REVIEW: "[yellow]review[/yellow]",
                    RiskLevel.RISKY: "[red]risky[/red]",
                }.get(result.risk_level, "?")

                table.add_row(
                    checkbox,
                    result.category_name,
                    result.size_human,
                    risk_style,
                    key=result.category_id,
                )

        self._update_selection_info()
        self.notify("Scan complete!", timeout=2)

    def _update_selection_info(self) -> None:
        """Update the selection info text."""
        app = self.app
        info = self.query_one("#selection-info", Static)

        if not app.selected_items:
            info.update("[dim]No items selected[/dim]")
            return

        total_bytes = 0
        if app.analysis:
            for result in app.analysis.scan_results:
                if result.category_id in app.selected_items:
                    total_bytes += result.size_bytes

        # Format size
        if total_bytes >= 1024**3:
            size_str = f"{total_bytes / (1024**3):.1f} GB"
        elif total_bytes >= 1024**2:
            size_str = f"{total_bytes / (1024**2):.1f} MB"
        else:
            size_str = f"{total_bytes / 1024:.1f} KB"

        info.update(f"[bold]{len(app.selected_items)}[/bold] selected: [cyan]{size_str}[/cyan]")

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Show details when row is highlighted."""
        if event.row_key is None:
            return

        category_id = str(event.row_key.value)
        detail = self.query_one("#category-detail", CategoryDetail)
        detail.show_category(category_id)

    def action_toggle_select(self) -> None:
        """Toggle selection of current item."""
        table = self.query_one("#category-table", DataTable)
        if table.cursor_row is None:
            return

        row_key = table.get_row_at(table.cursor_row)
        if not row_key:
            return

        # Get category_id from row key
        category_id = str(table.get_row_key(table.cursor_row))

        app = self.app
        if category_id in app.selected_items:
            app.selected_items.remove(category_id)
        else:
            app.selected_items.add(category_id)

        # Refresh table to show updated checkboxes
        self._update_table()

        # Re-highlight the same row
        table.move_cursor(row=table.cursor_row)

    def action_select_all_safe(self) -> None:
        """Select all safe items."""
        app = self.app
        if not app.analysis:
            return

        for result in app.analysis.safe_items:
            app.selected_items.add(result.category_id)

        self._update_table()
        self.notify("Selected all safe items")

    def action_deselect_all(self) -> None:
        """Deselect all items."""
        self.app.selected_items.clear()
        self._update_table()
        self.notify("Cleared selection")

    def action_view_details(self) -> None:
        """View details of current item."""
        table = self.query_one("#category-table", DataTable)
        if table.cursor_row is None:
            return

        category_id = str(table.get_row_key(table.cursor_row))
        detail = self.query_one("#category-detail", CategoryDetail)
        detail.show_category(category_id, expanded=True)

    def action_cleanup(self) -> None:
        """Start cleanup of selected items."""
        app = self.app
        if not app.selected_items:
            self.notify("No items selected", severity="warning")
            return

        # Push cleanup screen
        app.push_screen("cleanup")


class CleanupScreen(Screen):
    """Cleanup confirmation and execution screen."""

    BINDINGS = [
        Binding("y", "confirm", "Yes, Clean"),
        Binding("n", "cancel", "Cancel"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()

        with Container(id="cleanup-container"):
            yield Static("[bold]Cleanup Preview[/bold]", id="cleanup-title")
            yield DataTable(id="cleanup-table")
            yield Static("", id="cleanup-total")

            with Horizontal(id="cleanup-buttons"):
                yield Button("Clean", variant="success", id="btn-clean")
                yield Button("Cancel", variant="default", id="btn-cancel")

            yield Static("", id="cleanup-status")

        yield Footer()

    def on_mount(self) -> None:
        """Initialize cleanup screen."""
        table = self.query_one("#cleanup-table", DataTable)
        table.add_columns("Category", "Size", "Risk")

        app = self.app
        total_bytes = 0

        if app.analysis:
            for result in app.analysis.scan_results:
                if result.category_id in app.selected_items:
                    risk_style = {
                        RiskLevel.SAFE: "[green]safe[/green]",
                        RiskLevel.REVIEW: "[yellow]review[/yellow]",
                        RiskLevel.RISKY: "[red]risky[/red]",
                    }.get(result.risk_level, "?")

                    table.add_row(
                        result.category_name,
                        result.size_human,
                        risk_style,
                    )
                    total_bytes += result.size_bytes

        # Show total
        if total_bytes >= 1024**3:
            size_str = f"{total_bytes / (1024**3):.1f} GB"
        else:
            size_str = f"{total_bytes / (1024**2):.1f} MB"

        total_label = self.query_one("#cleanup-total", Static)
        total_label.update(f"\n[bold]Total to clean: {size_str}[/bold]")

        if app.dry_run:
            status = self.query_one("#cleanup-status", Static)
            status.update("\n[yellow]DRY RUN - No files will be deleted[/yellow]")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-clean":
            self.action_confirm()
        elif event.button.id == "btn-cancel":
            self.action_cancel()

    def action_confirm(self) -> None:
        """Execute cleanup."""
        app = self.app
        status = self.query_one("#cleanup-status", Static)

        if app.dry_run:
            status.update("\n[yellow]DRY RUN complete - no files were deleted[/yellow]")
            self.notify("Dry run complete", timeout=3)
        else:
            status.update("\n[cyan]Cleaning...[/cyan]")
            self.run_worker(self._execute_cleanup, thread=True)

    async def _execute_cleanup(self) -> None:
        """Execute cleanup in background."""
        app = self.app
        results = []

        for category_id in app.selected_items:
            result = clean_category(category_id, dry_run=app.dry_run)
            results.append(result)

        # Update UI
        self.call_from_thread(self._show_results, results)

    def _show_results(self, results) -> None:
        """Show cleanup results."""
        status = self.query_one("#cleanup-status", Static)

        success_count = sum(1 for r in results if r.success)
        total_freed = sum(r.bytes_freed for r in results if r.success)

        if total_freed >= 1024**3:
            size_str = f"{total_freed / (1024**3):.1f} GB"
        else:
            size_str = f"{total_freed / (1024**2):.1f} MB"

        status.update(
            f"\n[bold green]Cleanup complete![/bold green]\n"
            f"{success_count} items cleaned, {size_str} freed"
        )

        # Clear selection
        self.app.selected_items.clear()

        self.notify(f"Cleaned {size_str}!", timeout=5)

    def action_cancel(self) -> None:
        """Cancel and return to main screen."""
        self.app.pop_screen()
