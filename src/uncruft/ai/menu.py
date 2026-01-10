"""Menu-driven interface with AI for input interpretation."""

import json
import os
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from uncruft.ai.runtime import chat_completion, initialize_model, is_model_ready
from uncruft.ai.tools import ToolRegistry
from uncruft.categories import CATEGORIES


class MenuState(Enum):
    """States for the menu state machine."""

    MAIN = auto()
    SCAN_RESULTS = auto()
    LARGE_FILES = auto()
    OLD_FILES = auto()
    EXPLAIN = auto()
    ASK = auto()
    # Drill-down states
    CATEGORY_DRILLDOWN = auto()
    DOCKER_IMAGES = auto()
    DOCKER_CONTAINERS = auto()
    DOCKER_VOLUMES = auto()
    NODE_PROJECTS = auto()
    APP_CACHE_DETAIL = auto()


# Common folder aliases for path interpretation
FOLDER_ALIASES = {
    "home": "~",
    "documents": "~/Documents",
    "downloads": "~/Downloads",
    "desktop": "~/Desktop",
    "applications": "/Applications",
    "library": "~/Library",
    "pictures": "~/Pictures",
    "movies": "~/Movies",
    "music": "~/Music",
}


@dataclass
class MenuSession:
    """Menu-driven session with AI for input interpretation."""

    console: Console
    dry_run: bool = False
    manual_mode: bool = False
    tools: ToolRegistry = field(default_factory=lambda: ToolRegistry())
    state: MenuState = MenuState.MAIN
    scan_results: dict[str, Any] | None = None
    ai_available: bool = False
    # Drill-down state
    selected_category: str | None = None
    drilldown_data: dict[str, Any] | None = None

    def __post_init__(self):
        """Initialize the session."""
        self.tools = ToolRegistry(dry_run=self.dry_run)

    def run(self) -> None:
        """Main menu loop."""
        self._show_welcome()
        self._check_ai()

        while True:
            try:
                if not self._handle_state():
                    break
            except KeyboardInterrupt:
                self.console.print("\n[dim]Goodbye![/dim]")
                break

    def _show_welcome(self) -> None:
        """Display welcome message."""
        self.console.print(
            Panel(
                "[bold blue]Uncruft[/bold blue]\n"
                "[dim]Mac Disk Cleanup[/dim]",
                expand=False,
            )
        )
        if self.manual_mode:
            self.console.print("[cyan]Manual mode: Commands shown but not executed[/cyan]\n")
        elif self.dry_run:
            self.console.print("[yellow]Dry-run mode: No files will be deleted[/yellow]\n")

    def _check_ai(self) -> None:
        """Check if AI is available for input interpretation."""
        if is_model_ready():
            self.ai_available = True
            self.console.print("[dim]AI ready for natural language input[/dim]\n")
        else:
            self.ai_available = False
            self.console.print(
                "[yellow]AI not available - using exact input mode[/yellow]\n"
                "[dim]Start Ollama with 'ollama serve' for natural language input[/dim]\n"
            )

    def _handle_state(self) -> bool:
        """Handle current state, return False to exit."""
        if self.state == MenuState.MAIN:
            return self._main_menu()
        elif self.state == MenuState.SCAN_RESULTS:
            return self._scan_results_menu()
        elif self.state == MenuState.LARGE_FILES:
            return self._large_files_menu()
        elif self.state == MenuState.OLD_FILES:
            return self._old_files_menu()
        elif self.state == MenuState.EXPLAIN:
            return self._explain_menu()
        elif self.state == MenuState.ASK:
            return self._ask_menu()
        # Drill-down states
        elif self.state == MenuState.CATEGORY_DRILLDOWN:
            return self._category_drilldown_menu()
        elif self.state == MenuState.DOCKER_IMAGES:
            return self._docker_images_menu()
        elif self.state == MenuState.DOCKER_CONTAINERS:
            return self._docker_containers_menu()
        elif self.state == MenuState.DOCKER_VOLUMES:
            return self._docker_volumes_menu()
        elif self.state == MenuState.NODE_PROJECTS:
            return self._node_projects_menu()
        elif self.state == MenuState.APP_CACHE_DETAIL:
            return self._app_cache_detail_menu()
        return True

    # ─────────────────────────────────────────────────────────────────────────
    # Main Menu
    # ─────────────────────────────────────────────────────────────────────────

    def _main_menu(self) -> bool:
        """Display and handle main menu."""
        self.console.print("[bold]Main Menu[/bold]\n")
        self.console.print("1. Show disk status")
        self.console.print("2. Scan disk for cleanable items")
        self.console.print("3. Find large files")
        self.console.print("4. Find old files")
        self.console.print("5. Explore folder")
        if self.ai_available:
            self.console.print("6. Ask a question")
            self.console.print("0. Exit")
            max_choice = 6
        else:
            self.console.print("0. Exit")
            max_choice = 5

        choice = self._get_choice(max_choice)

        if choice == 0:
            self.console.print("\n[dim]Goodbye![/dim]")
            return False
        elif choice == 1:
            self._do_disk_status()
        elif choice == 2:
            self._do_scan()
            self.state = MenuState.SCAN_RESULTS
        elif choice == 3:
            self.state = MenuState.LARGE_FILES
        elif choice == 4:
            self.state = MenuState.OLD_FILES
        elif choice == 5:
            self._do_explore_folder()
        elif choice == 6 and self.ai_available:
            self.state = MenuState.ASK

        return True

    # ─────────────────────────────────────────────────────────────────────────
    # Scan Results Menu
    # ─────────────────────────────────────────────────────────────────────────

    def _scan_results_menu(self) -> bool:
        """Display and handle scan results menu."""
        if not self.scan_results:
            self.state = MenuState.MAIN
            return True

        items = self.scan_results.get("cleanable_items", [])
        if not items:
            self.console.print("[yellow]No cleanable items found.[/yellow]")
            self._pause()
            self.state = MenuState.MAIN
            return True

        # Calculate safe total
        safe_items = [i for i in items if i["risk"] == "safe"]
        safe_bytes = sum(i["size_bytes"] for i in safe_items)
        safe_human = self._format_bytes(safe_bytes)

        self.console.print("\n[bold]Scan Results[/bold]\n")
        self.console.print(f"1. Clean all safe items ({safe_human})")
        self.console.print("2. Clean specific category")
        self.console.print("3. Explore a category")
        if self.ai_available:
            self.console.print("4. Explain a category")
            self.console.print("0. Back to main menu")
            max_choice = 4
        else:
            self.console.print("0. Back to main menu")
            max_choice = 3

        choice = self._get_choice(max_choice)

        if choice == 0:
            self.state = MenuState.MAIN
        elif choice == 1:
            self._do_clean_safe()
        elif choice == 2:
            self._do_clean_specific()
        elif choice == 3:
            self._do_explore_category()
        elif choice == 4 and self.ai_available:
            self.state = MenuState.EXPLAIN

        return True

    # ─────────────────────────────────────────────────────────────────────────
    # Large Files Menu
    # ─────────────────────────────────────────────────────────────────────────

    def _large_files_menu(self) -> bool:
        """Handle large files search."""
        self.console.print("\n[bold]Find Large Files[/bold]")
        path = self._get_path_input("Which folder?")

        if path is None:
            self.state = MenuState.MAIN
            return True

        self.console.print(f"\n[dim]Searching {path}...[/dim]")
        result = self.tools.execute("find_large_files", {"path": path, "min_size_mb": 50})

        if "error" in result:
            self.console.print(f"[red]Error: {result['error']}[/red]")
        else:
            files = result.get("files", [])
            if files:
                self._show_files_table(files[:20], "Large Files")
            else:
                self.console.print("[yellow]No large files found.[/yellow]")

        self._pause()
        self.state = MenuState.MAIN
        return True

    # ─────────────────────────────────────────────────────────────────────────
    # Old Files Menu
    # ─────────────────────────────────────────────────────────────────────────

    def _old_files_menu(self) -> bool:
        """Handle old files search."""
        self.console.print("\n[bold]Find Old Files[/bold]")
        path = self._get_path_input("Which folder?", default="~/Downloads")

        if path is None:
            self.state = MenuState.MAIN
            return True

        self.console.print(f"\n[dim]Searching {path}...[/dim]")
        result = self.tools.execute("find_old_files", {"path": path, "days": 180})

        if "error" in result:
            self.console.print(f"[red]Error: {result['error']}[/red]")
        else:
            files = result.get("files", [])
            if files:
                self._show_files_table(files[:20], "Old Files (180+ days)")
            else:
                self.console.print("[yellow]No old files found.[/yellow]")

        self._pause()
        self.state = MenuState.MAIN
        return True

    # ─────────────────────────────────────────────────────────────────────────
    # Explain Menu
    # ─────────────────────────────────────────────────────────────────────────

    def _explain_menu(self) -> bool:
        """Handle category explanation."""
        if not self.scan_results:
            self.state = MenuState.MAIN
            return True

        items = self.scan_results.get("cleanable_items", [])
        available = [i["category_id"] for i in items]

        self.console.print("\n[bold]Explain Category[/bold]")
        self.console.print("[dim]Type category name or number, or 'back' to cancel[/dim]\n")

        # Show available categories
        for i, item in enumerate(items[:10], 1):
            self.console.print(f"  {i}. {item['name']} ({item['size_human']})")

        category_ids = self._get_category_input(available)

        if not category_ids:
            self.state = MenuState.SCAN_RESULTS
            return True

        # Explain the first selected category
        cat_id = category_ids[0]
        self._do_explain_category(cat_id)

        self._pause()
        self.state = MenuState.SCAN_RESULTS
        return True

    # ─────────────────────────────────────────────────────────────────────────
    # Ask Question Menu
    # ─────────────────────────────────────────────────────────────────────────

    def _ask_menu(self) -> bool:
        """Handle free-form questions."""
        self.console.print("\n[bold]Ask a Question[/bold]")
        self.console.print("[dim]Examples: 'Is npm cache safe?', 'How do I recover node_modules?'[/dim]")
        self.console.print("[dim]Type 'back' to return to menu[/dim]\n")

        question = self.console.input("[bold cyan]Question:[/bold cyan] ").strip()

        if not question or question.lower() in ("back", "cancel", "0"):
            self.state = MenuState.MAIN
            return True

        self._do_ask_question(question)
        self._pause()
        self.state = MenuState.MAIN
        return True

    # ─────────────────────────────────────────────────────────────────────────
    # Actions
    # ─────────────────────────────────────────────────────────────────────────

    def _do_scan(self) -> None:
        """Execute disk scan."""
        self.console.print("\n[dim]Scanning disk...[/dim]")
        self.scan_results = self.tools.execute("scan_disk", {"include_dev": True})

        if "error" in self.scan_results:
            self.console.print(f"[red]Error: {self.scan_results['error']}[/red]")
            return

        # Show disk status
        disk = self.scan_results.get("disk_status", {})
        self.console.print(
            f"\n[bold]Disk:[/bold] {disk.get('used_gb', 0):.1f} GB used of "
            f"{disk.get('total_gb', 0):.1f} GB ({disk.get('used_percent', 0):.0f}%)"
        )

        # Show cleanable items table
        items = self.scan_results.get("cleanable_items", [])
        if items:
            table = Table(title="Cleanable Items")
            table.add_column("#", style="dim")
            table.add_column("Category")
            table.add_column("Size", justify="right")
            table.add_column("Risk")

            for i, item in enumerate(items[:15], 1):
                risk_style = "green" if item["risk"] == "safe" else "yellow"
                table.add_row(
                    str(i),
                    item["name"],
                    item["size_human"],
                    f"[{risk_style}]{item['risk']}[/{risk_style}]",
                )

            self.console.print(table)

            total = self._format_bytes(self.scan_results.get("total_cleanable_bytes", 0))
            self.console.print(f"\n[bold]Total reclaimable:[/bold] {total}")

    def _do_disk_status(self) -> None:
        """Show detailed disk status with breakdown and drill-down options."""
        self.console.print("\n[dim]Analyzing disk usage...[/dim]")
        result = self.tools.execute("get_disk_status", {})

        if "error" in result:
            self.console.print(f"[red]Error: {result['error']}[/red]")
            return

        total_gb = result['total_gb']
        used_gb = result['used_gb']
        free_gb = result['free_gb']
        used_percent = result['used_percent']

        # Color based on usage
        if used_percent >= 90:
            status_color = "red"
            status_text = "Critical"
        elif used_percent >= 75:
            status_color = "yellow"
            status_text = "Warning"
        else:
            status_color = "green"
            status_text = "Healthy"

        # Visual progress bar
        bar_width = 40
        filled = int(bar_width * used_percent / 100)
        bar = "█" * filled + "░" * (bar_width - filled)

        self.console.print(f"\n[bold]Disk Status[/bold] [{status_color}]{status_text}[/{status_color}]\n")
        self.console.print(f"[{status_color}]{bar}[/{status_color}] {used_percent:.0f}%")
        self.console.print(f"\n[bold]Used:[/bold]  {used_gb:.1f} GB")
        self.console.print(f"[bold]Free:[/bold]  {free_gb:.1f} GB")
        self.console.print(f"[bold]Total:[/bold] {total_gb:.1f} GB")

        # Get storage breakdown
        self.console.print("\n[dim]Getting storage breakdown...[/dim]")
        breakdown = self.tools.execute("get_storage_breakdown", {})

        categories = []
        if "error" not in breakdown:
            categories = breakdown.get("categories", [])[:8]
            if categories:
                self.console.print("\n[bold]Storage Breakdown[/bold]\n")
                table = Table(show_header=True, header_style="bold")
                table.add_column("#", style="dim")
                table.add_column("Category")
                table.add_column("Size", justify="right")
                table.add_column("", width=20)

                for i, cat in enumerate(categories, 1):
                    name = cat.get("name", "Unknown")
                    size = cat.get("size_human", "?")
                    size_bytes = cat.get("size_bytes", 0)
                    # Mini bar (use total_bytes for accurate percentage)
                    total_bytes = breakdown["disk"].get("total_bytes", 0)
                    if total_bytes > 0:
                        cat_percent = (size_bytes / total_bytes) * 100
                        mini_bar_len = min(int(cat_percent / 5), 20)
                        mini_bar = "▓" * mini_bar_len
                    else:
                        mini_bar = ""
                    table.add_row(str(i), name, size, f"[cyan]{mini_bar}[/cyan]")

                self.console.print(table)

        # Show tip
        if used_percent >= 75:
            self.console.print(f"\n[{status_color}]Tip: Select option 2 from main menu to scan for cleanable items[/{status_color}]")

        # Options
        if categories:
            self.console.print("\n[dim]Enter number to explore category, or 0 to go back[/dim]")
            choice = self._get_choice(len(categories))

            if choice > 0:
                cat = categories[choice - 1]
                path = cat.get("path")
                if path:
                    self._explore_path(path, cat.get("name", "Unknown"))
                elif cat.get("id") == "other":
                    self._show_system_other_breakdown()
                else:
                    self.console.print(f"\n[yellow]{cat.get('name')} cannot be explored.[/yellow]")
                    self._pause()
        else:
            self._pause()

    def _show_system_other_breakdown(self) -> None:
        """Show breakdown of what contributes to System & Other."""
        from uncruft.scanner import get_system_other_breakdown

        self.console.print("\n[dim]Analyzing system paths...[/dim]")
        result = get_system_other_breakdown()

        paths = result.get("paths", [])
        if not paths:
            self.console.print("[yellow]Could not scan system paths.[/yellow]")
            self._pause()
            return

        # Header
        self.console.print("\n[bold]System & Other Breakdown[/bold]\n")
        self.console.print("[dim]This space includes system files, hidden data, and paths not categorized elsewhere.[/dim]\n")

        # Table of paths
        table = Table(title=f"Scanned: {result.get('total_scanned_human', '?')}", show_header=True)
        table.add_column("#", style="dim", width=3)
        table.add_column("Location", style="cyan")
        table.add_column("Size", justify="right", style="green")
        table.add_column("Description", style="dim")

        for i, item in enumerate(paths, 1):
            size_str = item.get("size_human", "N/A")
            if not item.get("accessible"):
                size_str = "[dim]No access[/dim]"

            table.add_row(
                str(i),
                item.get("name", "Unknown"),
                size_str,
                item.get("description", ""),
            )

        self.console.print(table)

        # Note about Trash if present
        trash_item = next((p for p in paths if "Trash" in p.get("name", "")), None)
        if trash_item and trash_item.get("size_bytes", 0) > 0:
            self.console.print(f"\n[yellow]Tip: Your Trash contains {trash_item.get('size_human')}. Empty it to free space.[/yellow]")

        # Note about system files
        self.console.print(f"\n[dim]{result.get('note', '')}[/dim]")

        self._pause()

    def _explore_path(self, path: str, name: str, folder_limit: int = 10, file_limit: int = 10) -> None:
        """Explore a specific path and show its contents."""
        from rich.columns import Columns

        self.console.print(f"\n[dim]Analyzing {name}...[/dim]")
        result = self.tools.execute("analyze_directory", {"path": path})

        if "error" in result:
            self.console.print(f"[red]Error: {result['error']}[/red]")
            self._pause()
            return

        # Tool returns "children" not "items"
        items = result.get("children", [])
        if not items:
            self.console.print(f"[yellow]{name} is empty or inaccessible.[/yellow]")
            self._pause()
            return

        # Separate folders and files
        folders = [item for item in items if item.get("is_dir")]
        files = [item for item in items if not item.get("is_dir")]

        # Show header
        total_size = result.get("total_size_human", result.get("total_size", "unknown"))
        self.console.print(f"\n[bold]{name}[/bold] ({total_size})\n")

        # Folders table
        showing_folders = min(folder_limit, len(folders))
        if folders:
            folder_table = Table(title=f"Folders ({showing_folders}/{len(folders)})", title_style="bold cyan")
            folder_table.add_column("#", style="dim")
            folder_table.add_column("Name")
            folder_table.add_column("Size", justify="right")

            for i, item in enumerate(folders[:folder_limit], 1):
                folder_table.add_row(
                    str(i),
                    item.get("name", "unknown")[:30],
                    item.get("size_human", "?"),
                )
        else:
            folder_table = None

        # Files table
        showing_files = min(file_limit, len(files))
        if files:
            file_table = Table(title=f"Files ({showing_files}/{len(files)})", title_style="bold yellow")
            file_table.add_column("#", style="dim")
            file_table.add_column("Name")
            file_table.add_column("Size", justify="right")

            for i, item in enumerate(files[:file_limit], 1):
                file_table.add_row(
                    str(i),
                    item.get("name", "unknown")[:30],
                    item.get("size_human", "?"),
                )
        else:
            file_table = None

        # Display tables side by side if both exist
        if folder_table and file_table:
            self.console.print(Columns([folder_table, file_table], equal=True, expand=True))
        elif folder_table:
            self.console.print(folder_table)
        elif file_table:
            self.console.print(file_table)

        # Build options
        self.console.print()
        if folders:
            self.console.print("[dim]Enter folder number (1-{}) to explore[/dim]".format(showing_folders))
        if len(folders) > folder_limit:
            self.console.print("[dim]'f' - Show more folders[/dim]")
        if len(files) > file_limit:
            self.console.print("[dim]'l' - Show more files[/dim]")
        self.console.print("[dim]'0' - Go back[/dim]")

        # Get input
        user_input = self.console.input("\n[bold cyan]Select:[/bold cyan] ").strip().lower()

        if user_input == "0" or user_input == "":
            return
        elif user_input == "f" and len(folders) > folder_limit:
            # Show more folders
            self._explore_path(path, name, folder_limit=folder_limit + 20, file_limit=file_limit)
        elif user_input == "l" and len(files) > file_limit:
            # Show more files
            self._explore_path(path, name, folder_limit=folder_limit, file_limit=file_limit + 20)
        elif user_input.isdigit():
            choice = int(user_input)
            if 1 <= choice <= showing_folders:
                selected = folders[choice - 1]
                selected_path = selected.get("path", "")
                if selected_path:
                    self._explore_path(selected_path, selected.get("name", "Unknown"))
            else:
                self.console.print(f"[yellow]Invalid selection. Enter 1-{showing_folders}[/yellow]")
                self._pause()
        else:
            self.console.print("[yellow]Invalid input[/yellow]")
            self._pause()

    def _do_explore_folder(self) -> None:
        """Explore a folder."""
        self.console.print("\n[bold]Explore Folder[/bold]")
        path = self._get_path_input("Which folder?")

        if path is None:
            return

        self.console.print(f"\n[dim]Analyzing {path}...[/dim]")
        result = self.tools.execute("analyze_directory", {"path": path})

        if "error" in result:
            self.console.print(f"[red]Error: {result['error']}[/red]")
        else:
            items = result.get("items", [])
            if items:
                table = Table(title=f"Contents of {path}")
                table.add_column("Name")
                table.add_column("Size", justify="right")
                table.add_column("Type")

                for item in items[:20]:
                    table.add_row(item["name"], item["size_human"], item["type"])

                self.console.print(table)
                self.console.print(f"\n[bold]Total:[/bold] {result.get('total_size', 'unknown')}")
            else:
                self.console.print("[yellow]Folder is empty or inaccessible.[/yellow]")

        self._pause()

    def _do_clean_safe(self) -> None:
        """Clean all safe items."""
        if not self.scan_results:
            return

        items = self.scan_results.get("cleanable_items", [])
        safe_items = [i for i in items if i["risk"] == "safe"]

        if not safe_items:
            self.console.print("[yellow]No safe items to clean.[/yellow]")
            return

        # Calculate total
        total_bytes = sum(i["size_bytes"] for i in safe_items)
        total_human = self._format_bytes(total_bytes)

        self.console.print(f"\n[bold]Safe items to clean ({total_human}):[/bold]")
        for item in safe_items:
            self.console.print(f"  - {item['name']}: {item['size_human']}")

        if not self._confirm("Clean all these items?"):
            return

        # Clean each category
        category_ids = [i["category_id"] for i in safe_items]
        result = self.tools.execute("clean_multiple", {"category_ids": category_ids})

        if "error" in result:
            self.console.print(f"[red]Error: {result['error']}[/red]")
        else:
            freed = self._format_bytes(result.get("total_bytes_freed", 0))
            self.console.print(f"\n[green]Cleaned! Freed {freed}[/green]")

        # Refresh scan results
        self._do_scan()

    def _do_clean_specific(self) -> None:
        """Clean specific categories."""
        if not self.scan_results:
            return

        items = self.scan_results.get("cleanable_items", [])
        available = [i["category_id"] for i in items]

        self.console.print("\n[bold]Clean Specific Category[/bold]")
        self.console.print("[dim]Type category name(s) or number(s), or 'back' to cancel[/dim]\n")

        # Show available categories
        for i, item in enumerate(items[:15], 1):
            risk_style = "green" if item["risk"] == "safe" else "yellow"
            self.console.print(
                f"  {i}. {item['name']} ({item['size_human']}) [{risk_style}]{item['risk']}[/{risk_style}]"
            )

        category_ids = self._get_category_input(available)

        if not category_ids:
            return

        # Show what will be cleaned
        to_clean = [i for i in items if i["category_id"] in category_ids]
        total_bytes = sum(i["size_bytes"] for i in to_clean)
        total_human = self._format_bytes(total_bytes)

        self.console.print(f"\n[bold]Selected ({total_human}):[/bold]")
        for item in to_clean:
            self.console.print(f"  - {item['name']}: {item['size_human']}")

        if not self._confirm("Clean these items?"):
            return

        result = self.tools.execute("clean_multiple", {"category_ids": category_ids})

        if "error" in result:
            self.console.print(f"[red]Error: {result['error']}[/red]")
        else:
            freed = self._format_bytes(result.get("total_bytes_freed", 0))
            self.console.print(f"\n[green]Cleaned! Freed {freed}[/green]")

        # Refresh scan results
        self._do_scan()

    def _do_explain_category(self, category_id: str) -> None:
        """Explain a category using AI."""
        cat = CATEGORIES.get(category_id)
        if not cat:
            self.console.print(f"[red]Unknown category: {category_id}[/red]")
            return

        if not self.ai_available:
            # Fallback to static info
            self.console.print(
                Panel(
                    f"[bold]{cat.name}[/bold]\n\n"
                    f"{cat.description or 'No description'}\n\n"
                    f"[bold]Risk:[/bold] {cat.risk_level.value}\n"
                    f"[bold]Recovery:[/bold] {cat.recovery or 'N/A'}",
                    title=f"About {cat.name}",
                )
            )
            return

        # Use AI for explanation
        prompt = f"""Explain the '{cat.name}' cache/folder to a Mac user in 2-3 sentences:
- What is it?
- Is it safe to delete?
- What happens after deletion?

Category info:
- Description: {cat.description}
- Risk: {cat.risk_level.value}
- Recovery: {cat.recovery or 'Auto-regenerates when needed'}
"""

        self.console.print(f"\n[dim]Getting explanation...[/dim]")

        try:
            initialize_model(console=self.console)
            response = chat_completion(
                messages=[
                    {"role": "system", "content": "You are a helpful Mac cleanup expert. Be concise."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=256,
            )
            content = response["choices"][0]["message"].get("content", "")
            self.console.print(Panel(Markdown(content), title=f"About {cat.name}"))
        except Exception as e:
            self.console.print(f"[red]AI error: {e}[/red]")
            # Fallback
            self.console.print(f"\n{cat.description}")

    def _do_ask_question(self, question: str) -> None:
        """Answer a question using AI."""
        if not self.ai_available:
            self.console.print("[yellow]AI not available. Start Ollama to ask questions.[/yellow]")
            return

        # Build context from categories
        cat_context = "\n".join(
            f"- {c.name} ({c.id}): {c.description}" for c in list(CATEGORIES.values())[:20]
        )

        prompt = f"""Answer this Mac disk cleanup question concisely (2-4 sentences):

Question: {question}

Available cleanup categories:
{cat_context}
"""

        self.console.print(f"\n[dim]Thinking...[/dim]")

        try:
            initialize_model(console=self.console)
            response = chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful Mac disk cleanup expert. Answer questions about caches, cleanup, and disk space concisely.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=512,
            )
            content = response["choices"][0]["message"].get("content", "")
            self.console.print(Panel(Markdown(content), title="Answer"))
        except Exception as e:
            self.console.print(f"[red]AI error: {e}[/red]")

    # ─────────────────────────────────────────────────────────────────────────
    # Category Drill-Down
    # ─────────────────────────────────────────────────────────────────────────

    def _do_explore_category(self) -> None:
        """Select a category to explore in detail."""
        if not self.scan_results:
            return

        items = self.scan_results.get("cleanable_items", [])

        # Categories that support drill-down
        DRILLDOWN_CATEGORIES = {"docker_data", "node_modules", "app_caches"}

        # Show explorable categories first, then others
        explorable = [i for i in items if i["category_id"] in DRILLDOWN_CATEGORIES]
        other = [i for i in items if i["category_id"] not in DRILLDOWN_CATEGORIES]

        # Build display list in the order shown (explorable first, then others)
        display_items = explorable + other[:5]
        available = [i["category_id"] for i in display_items]

        self.console.print("\n[bold]Explore Category[/bold]")
        self.console.print("[dim]Type category name or number, or 'back' to cancel[/dim]\n")

        if explorable:
            self.console.print("[bold cyan]Explorable (with details):[/bold cyan]")
            for i, item in enumerate(explorable, 1):
                self.console.print(f"  {i}. {item['name']} ({item['size_human']})")

        if other:
            offset = len(explorable)
            self.console.print("\n[dim]Other categories:[/dim]")
            for i, item in enumerate(other[:5], offset + 1):
                self.console.print(f"  {i}. {item['name']} ({item['size_human']})")

        category_ids = self._get_category_input(available)

        if not category_ids:
            return

        cat_id = category_ids[0]
        self.selected_category = cat_id

        if cat_id in DRILLDOWN_CATEGORIES:
            self.state = MenuState.CATEGORY_DRILLDOWN
        else:
            self.console.print(f"\n[yellow]Category '{cat_id}' doesn't support detailed exploration.[/yellow]")
            self.console.print("[dim]Try Docker Data, Node Modules, or App Caches.[/dim]")
            self._pause()

    def _category_drilldown_menu(self) -> bool:
        """Handle category drill-down view."""
        cat_id = self.selected_category

        if not cat_id:
            self.state = MenuState.SCAN_RESULTS
            return True

        if cat_id == "docker_data":
            return self._show_docker_drilldown()
        elif cat_id == "node_modules":
            return self._show_node_modules_drilldown()
        elif cat_id == "app_caches":
            return self._show_app_caches_drilldown()
        else:
            self.console.print(f"[yellow]No drill-down available for {cat_id}[/yellow]")
            self._pause()
            self.state = MenuState.SCAN_RESULTS
            return True

    def _show_docker_drilldown(self) -> bool:
        """Show Docker breakdown with submenu."""
        from uncruft.scanner import get_docker_breakdown

        self.console.print("\n[dim]Loading Docker breakdown...[/dim]")
        breakdown = get_docker_breakdown()

        if not breakdown.get("available"):
            self.console.print("[yellow]Docker not available or not running.[/yellow]")
            self._pause()
            self.state = MenuState.SCAN_RESULTS
            return True

        self.drilldown_data = breakdown

        # Show summary
        self.console.print(
            Panel(
                f"[bold]Docker Data[/bold] ({self._format_bytes(breakdown.get('total_bytes', 0))})",
                expand=False,
            )
        )

        # Summary table
        table = Table()
        table.add_column("Type")
        table.add_column("Count", justify="right")
        table.add_column("Size", justify="right")
        table.add_column("Status")

        images = breakdown.get("images", [])
        containers = breakdown.get("containers", [])
        volumes = breakdown.get("volumes", [])
        build_cache = breakdown.get("build_cache_bytes", 0)

        unused_images = len([i for i in images if i.get("status") == "unused"])
        exited_containers = len([c for c in containers if "Exited" in c.get("status", "")])
        dangling_volumes = len([v for v in volumes if v.get("status") == "dangling"])

        image_size = sum(i.get("size_bytes", 0) for i in images)
        container_size = sum(c.get("size_bytes", 0) for c in containers)

        table.add_row(
            "Images",
            str(len(images)),
            self._format_bytes(image_size),
            f"[yellow]{unused_images} unused[/yellow]" if unused_images else "[green]all in use[/green]",
        )
        table.add_row(
            "Containers",
            str(len(containers)),
            self._format_bytes(container_size),
            f"[yellow]{exited_containers} exited[/yellow]" if exited_containers else "[green]all running[/green]",
        )
        table.add_row(
            "Volumes",
            str(len(volumes)),
            "-",
            f"[yellow]{dangling_volumes} dangling[/yellow]" if dangling_volumes else "[green]all in use[/green]",
        )
        if build_cache > 0:
            table.add_row("Build Cache", "-", self._format_bytes(build_cache), "[yellow]all unused[/yellow]")

        self.console.print(table)

        # Calculate reclaimable
        unused_bytes = breakdown.get("unused_bytes", 0)
        self.console.print(f"\n[bold]Reclaimable:[/bold] {self._format_bytes(unused_bytes)}")

        # Menu options
        self.console.print("\n1. View images")
        self.console.print("2. View containers")
        self.console.print("3. View volumes")
        if unused_bytes > 0:
            self.console.print(f"4. Clean all unused ({self._format_bytes(unused_bytes)})")
        self.console.print("0. Back")
        self.console.print("9. Back to main menu")

        max_choice = 9
        choice = self._get_choice(max_choice)

        if choice == 0:
            self.state = MenuState.SCAN_RESULTS
        elif choice == 1:
            self.state = MenuState.DOCKER_IMAGES
        elif choice == 2:
            self.state = MenuState.DOCKER_CONTAINERS
        elif choice == 3:
            self.state = MenuState.DOCKER_VOLUMES
        elif choice == 4 and unused_bytes > 0:
            self._do_docker_prune_all()
        elif choice == 9:
            self.state = MenuState.MAIN

        return True

    def _docker_images_menu(self) -> bool:
        """Show Docker images with delete options."""
        breakdown = self.drilldown_data
        if not breakdown:
            self.state = MenuState.CATEGORY_DRILLDOWN
            return True

        images = breakdown.get("images", [])
        if not images:
            self.console.print("[yellow]No Docker images found.[/yellow]")
            self._pause()
            self.state = MenuState.CATEGORY_DRILLDOWN
            return True

        self.console.print(
            Panel(f"[bold]Docker Images[/bold] ({len(images)} total)", expand=False)
        )

        # Show images table
        table = Table()
        table.add_column("#", style="dim")
        table.add_column("Repository")
        table.add_column("Tag")
        table.add_column("Size", justify="right")
        table.add_column("Status")

        for i, img in enumerate(images[:15], 1):
            repo = img.get("repository", "<none>")
            tag = img.get("tag", "<none>")
            size = self._format_bytes(img.get("size_bytes", 0))
            status = img.get("status", "unknown")
            status_style = "green" if status == "in use" else "yellow"
            table.add_row(str(i), repo, tag, size, f"[{status_style}]{status}[/{status_style}]")

        self.console.print(table)

        if len(images) > 15:
            self.console.print(f"[dim]... and {len(images) - 15} more[/dim]")

        # Options
        unused_images = [i for i in images if i.get("status") == "unused"]
        dangling_images = [i for i in images if i.get("repository") == "<none>"]

        self.console.print("\n1. Delete specific image")
        if unused_images:
            unused_size = sum(i.get("size_bytes", 0) for i in unused_images)
            self.console.print(f"2. Delete all unused ({len(unused_images)} images, {self._format_bytes(unused_size)})")
        if dangling_images:
            dangling_size = sum(i.get("size_bytes", 0) for i in dangling_images)
            opt_num = 3 if unused_images else 2
            self.console.print(f"{opt_num}. Delete dangling only ({self._format_bytes(dangling_size)})")
        self.console.print("0. Back")
        self.console.print("9. Back to main menu")

        max_choice = 9
        choice = self._get_choice(max_choice)

        if choice == 0:
            self.state = MenuState.CATEGORY_DRILLDOWN
        elif choice == 1:
            self._do_delete_docker_image(images)
        elif choice == 2 and unused_images:
            self._do_docker_prune_images()
        elif (choice == 2 and not unused_images and dangling_images) or (choice == 3 and dangling_images):
            self._do_docker_prune_dangling()
        elif choice == 9:
            self.state = MenuState.MAIN

        return True

    def _docker_containers_menu(self) -> bool:
        """Show Docker containers with delete options."""
        breakdown = self.drilldown_data
        if not breakdown:
            self.state = MenuState.CATEGORY_DRILLDOWN
            return True

        containers = breakdown.get("containers", [])
        if not containers:
            self.console.print("[yellow]No Docker containers found.[/yellow]")
            self._pause()
            self.state = MenuState.CATEGORY_DRILLDOWN
            return True

        self.console.print(
            Panel(f"[bold]Docker Containers[/bold] ({len(containers)} total)", expand=False)
        )

        # Show containers table
        table = Table()
        table.add_column("#", style="dim")
        table.add_column("Name")
        table.add_column("Status")
        table.add_column("Size", justify="right")

        for i, cont in enumerate(containers[:15], 1):
            name = cont.get("name", "unknown")
            status = cont.get("status", "unknown")
            size = self._format_bytes(cont.get("size_bytes", 0))
            status_style = "green" if "Up" in status else "yellow"
            table.add_row(str(i), name, f"[{status_style}]{status}[/{status_style}]", size)

        self.console.print(table)

        # Options
        exited = [c for c in containers if "Exited" in c.get("status", "")]

        self.console.print("\n1. Delete specific container")
        if exited:
            exited_size = sum(c.get("size_bytes", 0) for c in exited)
            self.console.print(f"2. Delete all exited ({len(exited)} containers, {self._format_bytes(exited_size)})")
        self.console.print("0. Back")
        self.console.print("9. Back to main menu")

        max_choice = 9
        choice = self._get_choice(max_choice)

        if choice == 0:
            self.state = MenuState.CATEGORY_DRILLDOWN
        elif choice == 1:
            self._do_delete_docker_container(containers)
        elif choice == 2 and exited:
            self._do_docker_prune_containers()
        elif choice == 9:
            self.state = MenuState.MAIN

        return True

    def _docker_volumes_menu(self) -> bool:
        """Show Docker volumes with delete options."""
        breakdown = self.drilldown_data
        if not breakdown:
            self.state = MenuState.CATEGORY_DRILLDOWN
            return True

        volumes = breakdown.get("volumes", [])
        if not volumes:
            self.console.print("[yellow]No Docker volumes found.[/yellow]")
            self._pause()
            self.state = MenuState.CATEGORY_DRILLDOWN
            return True

        self.console.print(
            Panel(f"[bold]Docker Volumes[/bold] ({len(volumes)} total)", expand=False)
        )

        # Show volumes table
        table = Table()
        table.add_column("#", style="dim")
        table.add_column("Name")
        table.add_column("Driver")
        table.add_column("Status")

        for i, vol in enumerate(volumes[:15], 1):
            name = vol.get("name", "unknown")
            driver = vol.get("driver", "local")
            status = vol.get("status", "in use")
            status_style = "green" if status == "in use" else "yellow"
            table.add_row(str(i), name[:40], driver, f"[{status_style}]{status}[/{status_style}]")

        self.console.print(table)

        # Options
        dangling = [v for v in volumes if v.get("status") == "dangling"]

        self.console.print("\n1. Delete specific volume")
        if dangling:
            self.console.print(f"2. Delete all dangling ({len(dangling)} volumes)")
        self.console.print("0. Back")
        self.console.print("9. Back to main menu")

        max_choice = 9
        choice = self._get_choice(max_choice)

        if choice == 0:
            self.state = MenuState.CATEGORY_DRILLDOWN
        elif choice == 1:
            self._do_delete_docker_volume(volumes)
        elif choice == 2 and dangling:
            self._do_docker_prune_volumes()
        elif choice == 9:
            self.state = MenuState.MAIN

        return True

    def _show_node_modules_drilldown(self) -> bool:
        """Show Node modules per-project breakdown."""
        from uncruft.scanner import get_node_modules_breakdown

        self.console.print("\n[dim]Scanning for node_modules...[/dim]")
        breakdown = get_node_modules_breakdown()

        projects = breakdown.get("projects", [])
        if not projects:
            self.console.print("[yellow]No node_modules folders found.[/yellow]")
            self._pause()
            self.state = MenuState.SCAN_RESULTS
            return True

        self.drilldown_data = breakdown
        self.state = MenuState.NODE_PROJECTS
        return True

    def _node_projects_menu(self) -> bool:
        """Show Node projects with delete options."""
        breakdown = self.drilldown_data
        if not breakdown:
            self.state = MenuState.SCAN_RESULTS
            return True

        projects = breakdown.get("projects", [])
        total_size = breakdown.get("total_size_bytes", 0)
        inactive_count = breakdown.get("inactive_count", 0)

        self.console.print(
            Panel(
                f"[bold]Node Modules[/bold] ({len(projects)} projects, {self._format_bytes(total_size)})",
                expand=False,
            )
        )

        # Show projects table
        table = Table()
        table.add_column("#", style="dim")
        table.add_column("Project")
        table.add_column("Size", justify="right")
        table.add_column("Last Modified")
        table.add_column("Status")

        for i, proj in enumerate(projects[:15], 1):
            name = proj.get("project_name", "unknown")
            size = self._format_bytes(proj.get("size_bytes", 0))
            days = proj.get("days_since_modified", 0)
            status = proj.get("status", "active")
            if days > 180:
                modified = f"{days} days ago"
                status_style = "red"
            elif days > 30:
                modified = f"{days} days ago"
                status_style = "yellow"
            else:
                modified = f"{days} days ago"
                status_style = "green"
            table.add_row(str(i), name[:30], size, modified, f"[{status_style}]{status}[/{status_style}]")

        self.console.print(table)

        if len(projects) > 15:
            self.console.print(f"[dim]... and {len(projects) - 15} more[/dim]")

        # Calculate inactive total
        inactive_projects = [p for p in projects if p.get("status") == "inactive"]
        inactive_size = sum(p.get("size_bytes", 0) for p in inactive_projects)

        # Options
        self.console.print("\n1. Delete specific project's node_modules")
        if inactive_projects:
            self.console.print(
                f"2. Delete all inactive ({len(inactive_projects)} projects, {self._format_bytes(inactive_size)})"
            )
        self.console.print("0. Back")
        self.console.print("9. Back to main menu")

        max_choice = 9
        choice = self._get_choice(max_choice)

        if choice == 0:
            self.state = MenuState.SCAN_RESULTS
        elif choice == 1:
            self._do_delete_node_modules(projects)
        elif choice == 2 and inactive_projects:
            self._do_delete_inactive_node_modules(inactive_projects)
        elif choice == 9:
            self.state = MenuState.MAIN

        return True

    def _show_app_caches_drilldown(self) -> bool:
        """Show App caches per-app breakdown."""
        from uncruft.scanner import get_app_caches_breakdown

        self.console.print("\n[dim]Scanning app caches...[/dim]")
        breakdown = get_app_caches_breakdown()

        apps = breakdown.get("apps", [])
        if not apps:
            self.console.print("[yellow]No app caches found.[/yellow]")
            self._pause()
            self.state = MenuState.SCAN_RESULTS
            return True

        self.drilldown_data = breakdown
        self.state = MenuState.APP_CACHE_DETAIL
        return True

    def _app_cache_detail_menu(self) -> bool:
        """Show app cache details with delete options."""
        breakdown = self.drilldown_data
        if not breakdown:
            self.state = MenuState.SCAN_RESULTS
            return True

        apps = breakdown.get("apps", [])
        total_size = breakdown.get("total_size_bytes", 0)
        browsers = breakdown.get("browsers", [])

        self.console.print(
            Panel(
                f"[bold]Application Caches[/bold] ({len(apps)} apps, {self._format_bytes(total_size)})",
                expand=False,
            )
        )

        # Show apps table
        table = Table()
        table.add_column("#", style="dim")
        table.add_column("Application")
        table.add_column("Size", justify="right")
        table.add_column("Type")

        for i, app in enumerate(apps[:15], 1):
            name = app.get("name", "unknown")
            size = self._format_bytes(app.get("size_bytes", 0))
            is_browser = app.get("is_browser", False)
            app_type = "[cyan]browser[/cyan]" if is_browser else "app"
            table.add_row(str(i), name[:35], size, app_type)

        self.console.print(table)

        if len(apps) > 15:
            self.console.print(f"[dim]... and {len(apps) - 15} more[/dim]")

        # Calculate browser cache total
        browser_size = sum(b.get("size_bytes", 0) for b in browsers)

        # Options
        self.console.print("\n1. Delete specific app's cache")
        if browsers:
            self.console.print(f"2. Delete all browser caches ({len(browsers)} browsers, {self._format_bytes(browser_size)})")
        self.console.print("0. Back")
        self.console.print("9. Back to main menu")

        max_choice = 9
        choice = self._get_choice(max_choice)

        if choice == 0:
            self.state = MenuState.SCAN_RESULTS
        elif choice == 1:
            self._do_delete_app_cache(apps)
        elif choice == 2 and browsers:
            self._do_delete_browser_caches(browsers)
        elif choice == 9:
            self.state = MenuState.MAIN

        return True

    # ─────────────────────────────────────────────────────────────────────────
    # Drill-Down Delete Actions
    # ─────────────────────────────────────────────────────────────────────────

    def _do_delete_docker_image(self, images: list[dict]) -> None:
        """Delete a specific Docker image."""
        self.console.print("\n[dim]Enter image number or name (e.g., '2' or 'python')[/dim]")
        user_input = self.console.input("[bold cyan]Image:[/bold cyan] ").strip()

        if not user_input or user_input.lower() in ("back", "cancel", "0"):
            return

        # Find the image
        image = None
        if user_input.isdigit():
            idx = int(user_input) - 1
            if 0 <= idx < len(images):
                image = images[idx]
        else:
            # Search by name
            for img in images:
                repo = img.get("repository", "")
                if user_input.lower() in repo.lower():
                    image = img
                    break

        if not image:
            self.console.print(f"[yellow]Image not found: {user_input}[/yellow]")
            return

        repo = image.get("repository", "<none>")
        tag = image.get("tag", "<none>")
        image_id = image.get("id", "")
        size = self._format_bytes(image.get("size_bytes", 0))

        if not self._confirm(f"Delete {repo}:{tag} ({size})?"):
            return

        from uncruft.cleaner import delete_docker_item

        result = delete_docker_item("image", image_id, dry_run=self.dry_run)

        if result.get("success"):
            self.console.print(f"[green]Deleted {repo}:{tag}[/green]")
        else:
            self.console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")

        self._pause()

    def _do_delete_docker_container(self, containers: list[dict]) -> None:
        """Delete a specific Docker container."""
        self.console.print("\n[dim]Enter container number or name[/dim]")
        user_input = self.console.input("[bold cyan]Container:[/bold cyan] ").strip()

        if not user_input or user_input.lower() in ("back", "cancel", "0"):
            return

        container = None
        if user_input.isdigit():
            idx = int(user_input) - 1
            if 0 <= idx < len(containers):
                container = containers[idx]
        else:
            for cont in containers:
                name = cont.get("name", "")
                if user_input.lower() in name.lower():
                    container = cont
                    break

        if not container:
            self.console.print(f"[yellow]Container not found: {user_input}[/yellow]")
            return

        name = container.get("name", "unknown")
        container_id = container.get("id", "")

        if not self._confirm(f"Delete container {name}?"):
            return

        from uncruft.cleaner import delete_docker_item

        result = delete_docker_item("container", container_id, dry_run=self.dry_run)

        if result.get("success"):
            self.console.print(f"[green]Deleted container {name}[/green]")
        else:
            self.console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")

        self._pause()

    def _do_delete_docker_volume(self, volumes: list[dict]) -> None:
        """Delete a specific Docker volume."""
        self.console.print("\n[dim]Enter volume number or name[/dim]")
        user_input = self.console.input("[bold cyan]Volume:[/bold cyan] ").strip()

        if not user_input or user_input.lower() in ("back", "cancel", "0"):
            return

        volume = None
        if user_input.isdigit():
            idx = int(user_input) - 1
            if 0 <= idx < len(volumes):
                volume = volumes[idx]
        else:
            for vol in volumes:
                name = vol.get("name", "")
                if user_input.lower() in name.lower():
                    volume = vol
                    break

        if not volume:
            self.console.print(f"[yellow]Volume not found: {user_input}[/yellow]")
            return

        name = volume.get("name", "unknown")

        if not self._confirm(f"Delete volume {name}?"):
            return

        from uncruft.cleaner import delete_docker_item

        result = delete_docker_item("volume", name, dry_run=self.dry_run)

        if result.get("success"):
            self.console.print(f"[green]Deleted volume {name}[/green]")
        else:
            self.console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")

        self._pause()

    def _do_docker_prune_all(self) -> None:
        """Prune all unused Docker items."""
        if not self._confirm("Remove all unused Docker images, containers, and volumes?"):
            return

        from uncruft.cleaner import delete_docker_unused

        self.console.print("\n[dim]Cleaning unused Docker data...[/dim]")
        result = delete_docker_unused(dry_run=self.dry_run)

        if result.get("success"):
            freed = self._format_bytes(result.get("bytes_freed", 0))
            self.console.print(f"[green]Cleaned! Freed {freed}[/green]")
        else:
            self.console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")

        self._pause()
        # Refresh drilldown data
        self.state = MenuState.CATEGORY_DRILLDOWN

    def _do_docker_prune_images(self) -> None:
        """Prune unused Docker images."""
        if not self._confirm("Remove all unused Docker images?"):
            return

        from uncruft.cleaner import delete_docker_unused

        self.console.print("\n[dim]Cleaning unused images...[/dim]")
        result = delete_docker_unused(item_type="image", dry_run=self.dry_run)

        if result.get("success"):
            freed = self._format_bytes(result.get("bytes_freed", 0))
            self.console.print(f"[green]Cleaned! Freed {freed}[/green]")
        else:
            self.console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")

        self._pause()

    def _do_docker_prune_dangling(self) -> None:
        """Prune dangling Docker images."""
        if not self._confirm("Remove all dangling (untagged) images?"):
            return

        from uncruft.cleaner import delete_docker_unused

        self.console.print("\n[dim]Cleaning dangling images...[/dim]")
        result = delete_docker_unused(item_type="image", dry_run=self.dry_run)

        if result.get("success"):
            freed = self._format_bytes(result.get("bytes_freed", 0))
            self.console.print(f"[green]Cleaned! Freed {freed}[/green]")
        else:
            self.console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")

        self._pause()

    def _do_docker_prune_containers(self) -> None:
        """Prune stopped Docker containers."""
        if not self._confirm("Remove all stopped containers?"):
            return

        from uncruft.cleaner import delete_docker_unused

        self.console.print("\n[dim]Cleaning stopped containers...[/dim]")
        result = delete_docker_unused(item_type="container", dry_run=self.dry_run)

        if result.get("success"):
            self.console.print("[green]Cleaned stopped containers![/green]")
        else:
            self.console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")

        self._pause()

    def _do_docker_prune_volumes(self) -> None:
        """Prune dangling Docker volumes."""
        if not self._confirm("Remove all dangling volumes?"):
            return

        from uncruft.cleaner import delete_docker_unused

        self.console.print("\n[dim]Cleaning dangling volumes...[/dim]")
        result = delete_docker_unused(item_type="volume", dry_run=self.dry_run)

        if result.get("success"):
            self.console.print("[green]Cleaned dangling volumes![/green]")
        else:
            self.console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")

        self._pause()

    def _do_delete_node_modules(self, projects: list[dict]) -> None:
        """Delete node_modules for a specific project."""
        self.console.print("\n[dim]Enter project number or name[/dim]")
        user_input = self.console.input("[bold cyan]Project:[/bold cyan] ").strip()

        if not user_input or user_input.lower() in ("back", "cancel", "0"):
            return

        project = None
        if user_input.isdigit():
            idx = int(user_input) - 1
            if 0 <= idx < len(projects):
                project = projects[idx]
        else:
            for proj in projects:
                name = proj.get("project_name", "")
                if user_input.lower() in name.lower():
                    project = proj
                    break

        if not project:
            self.console.print(f"[yellow]Project not found: {user_input}[/yellow]")
            return

        name = project.get("project_name", "unknown")
        path = project.get("project_path", "")
        size = self._format_bytes(project.get("size_bytes", 0))

        if not self._confirm(f"Delete node_modules for {name} ({size})?"):
            return

        from uncruft.cleaner import delete_node_modules_project

        result = delete_node_modules_project(path, dry_run=self.dry_run)

        if result.get("success"):
            freed = self._format_bytes(result.get("bytes_freed", 0))
            self.console.print(f"[green]Deleted! Freed {freed}[/green]")
        else:
            self.console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")

        self._pause()

    def _do_delete_inactive_node_modules(self, projects: list[dict]) -> None:
        """Delete node_modules for all inactive projects."""
        total_size = sum(p.get("size_bytes", 0) for p in projects)
        if not self._confirm(
            f"Delete node_modules for {len(projects)} inactive projects ({self._format_bytes(total_size)})?"
        ):
            return

        from uncruft.cleaner import delete_node_modules_project

        self.console.print("\n[dim]Cleaning inactive projects...[/dim]")
        total_freed = 0
        for proj in projects:
            path = proj.get("project_path", "")
            result = delete_node_modules_project(path, dry_run=self.dry_run)
            if result.get("success"):
                total_freed += result.get("bytes_freed", 0)

        self.console.print(f"[green]Cleaned! Freed {self._format_bytes(total_freed)}[/green]")
        self._pause()

    def _do_delete_app_cache(self, apps: list[dict]) -> None:
        """Delete cache for a specific app."""
        self.console.print("\n[dim]Enter app number or name[/dim]")
        user_input = self.console.input("[bold cyan]App:[/bold cyan] ").strip()

        if not user_input or user_input.lower() in ("back", "cancel", "0"):
            return

        app = None
        if user_input.isdigit():
            idx = int(user_input) - 1
            if 0 <= idx < len(apps):
                app = apps[idx]
        else:
            for a in apps:
                name = a.get("name", "")
                if user_input.lower() in name.lower():
                    app = a
                    break

        if not app:
            self.console.print(f"[yellow]App not found: {user_input}[/yellow]")
            return

        name = app.get("name", "unknown")
        path = app.get("path", "")
        size = self._format_bytes(app.get("size_bytes", 0))

        if not self._confirm(f"Delete cache for {name} ({size})?"):
            return

        from uncruft.cleaner import delete_app_cache

        result = delete_app_cache(path, dry_run=self.dry_run)

        if result.get("success"):
            freed = self._format_bytes(result.get("bytes_freed", 0))
            self.console.print(f"[green]Deleted! Freed {freed}[/green]")
        else:
            self.console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")

        self._pause()

    def _do_delete_browser_caches(self, browsers: list[dict]) -> None:
        """Delete all browser caches."""
        total_size = sum(b.get("size_bytes", 0) for b in browsers)
        if not self._confirm(
            f"Delete cache for {len(browsers)} browsers ({self._format_bytes(total_size)})?"
        ):
            return

        from uncruft.cleaner import delete_app_cache

        self.console.print("\n[dim]Cleaning browser caches...[/dim]")
        total_freed = 0
        for browser in browsers:
            path = browser.get("path", "")
            result = delete_app_cache(path, dry_run=self.dry_run)
            if result.get("success"):
                total_freed += result.get("bytes_freed", 0)

        self.console.print(f"[green]Cleaned! Freed {self._format_bytes(total_freed)}[/green]")
        self._pause()

    # ─────────────────────────────────────────────────────────────────────────
    # Input Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _get_choice(self, max_choice: int) -> int:
        """Get menu choice from user."""
        while True:
            try:
                choice = self.console.input("\n[bold cyan]Select:[/bold cyan] ").strip()
                if not choice:
                    continue
                num = int(choice)
                if 0 <= num <= max_choice:
                    return num
                self.console.print(f"[yellow]Please enter 0-{max_choice}[/yellow]")
            except ValueError:
                self.console.print("[yellow]Please enter a number[/yellow]")

    def _get_path_input(self, prompt: str, default: str = "~") -> str | None:
        """Get path input, using AI interpretation if available."""
        if self.ai_available:
            self.console.print(f"[dim]Type folder name naturally, paste path, or 'back' to cancel[/dim]")
        else:
            self.console.print(f"[dim]Enter path (e.g., ~/Documents) or 'back' to cancel[/dim]")

        user_input = self.console.input(f"\n[bold cyan]{prompt}[/bold cyan] ").strip()

        if not user_input or user_input.lower() in ("back", "cancel", "0"):
            return None

        return self._interpret_path(user_input)

    def _interpret_path(self, user_input: str) -> str | None:
        """Interpret user input as a path."""
        stripped = user_input.strip()

        # Pass through exact paths
        if stripped.startswith(("/", "~")):
            return os.path.expanduser(stripped)

        # Check for common aliases (case-insensitive)
        lower = stripped.lower()
        for alias, path in FOLDER_ALIASES.items():
            if alias in lower:
                return os.path.expanduser(path)

        # If AI available, use it to interpret
        if self.ai_available:
            prompt = f"""Convert this folder reference to a macOS path.
User said: "{user_input}"

Common folders: {list(FOLDER_ALIASES.keys())}

Respond with ONLY the path (e.g., ~/Documents) or "UNKNOWN" if unclear."""

            try:
                initialize_model(console=self.console)
                response = chat_completion(
                    messages=[
                        {"role": "system", "content": "Convert folder names to paths. Reply with path only."},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=64,
                )
                path = response["choices"][0]["message"].get("content", "").strip()
                if path and path != "UNKNOWN" and not path.startswith("I"):
                    self.console.print(f"[dim]→ {path}[/dim]")
                    return os.path.expanduser(path)
            except Exception:
                pass

        # Fallback: treat as literal path
        self.console.print(f"[yellow]Couldn't understand '{user_input}'. Try ~/Documents[/yellow]")
        return None

    def _get_category_input(self, available: list[str]) -> list[str]:
        """Get category selection, using AI interpretation if available."""
        user_input = self.console.input("\n[bold cyan]Category:[/bold cyan] ").strip()

        if not user_input or user_input.lower() in ("back", "cancel", "0"):
            return []

        return self._interpret_categories(user_input, available)

    def _interpret_categories(self, user_input: str, available: list[str]) -> list[str]:
        """Interpret user input as category selection."""
        stripped = user_input.strip()

        # Handle number input
        if stripped.isdigit():
            idx = int(stripped) - 1
            if 0 <= idx < len(available):
                return [available[idx]]
            return []

        # Handle comma-separated numbers
        if all(p.strip().isdigit() for p in stripped.split(",")):
            result = []
            for p in stripped.split(","):
                idx = int(p.strip()) - 1
                if 0 <= idx < len(available):
                    result.append(available[idx])
            return result

        # Direct match on category ID
        if stripped in available:
            return [stripped]

        # Partial match on category name/ID
        matches = [c for c in available if stripped.lower() in c.lower()]
        if len(matches) == 1:
            return matches

        # If AI available, use it to interpret
        if self.ai_available and len(available) > 0:
            prompt = f"""Match user's category selection to these available categories:
{available}

User said: "{user_input}"

Respond with a JSON list of matching category IDs, e.g., ["npm_cache", "docker_data"]
If no match, respond with []"""

            try:
                initialize_model(console=self.console)
                response = chat_completion(
                    messages=[
                        {"role": "system", "content": "Match category names. Reply with JSON list only."},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=128,
                )
                content = response["choices"][0]["message"].get("content", "").strip()
                # Extract JSON from response
                if "[" in content:
                    json_str = content[content.find("[") : content.rfind("]") + 1]
                    matches = json.loads(json_str)
                    valid = [m for m in matches if m in available]
                    if valid:
                        self.console.print(f"[dim]→ {', '.join(valid)}[/dim]")
                        return valid
            except Exception:
                pass

        self.console.print(f"[yellow]Couldn't match '{user_input}'. Try a number or exact name.[/yellow]")
        return []

    def _confirm(self, message: str) -> bool:
        """Ask for confirmation."""
        if self.manual_mode:
            self.console.print(f"\n[cyan]{message}[/cyan]")
            self.console.print("[dim]Manual mode: skipping execution[/dim]")
            return False

        if self.dry_run:
            self.console.print(f"[yellow]DRY RUN: {message}[/yellow]")
            return True

        response = self.console.input(f"\n[yellow]{message}[/yellow] [dim](Y/n)[/dim] ").strip().lower()
        return response in ("", "y", "yes")

    def _pause(self) -> None:
        """Pause for user to read output."""
        self.console.input("\n[dim]Press Enter to continue...[/dim]")

    def _show_files_table(self, files: list[dict], title: str) -> None:
        """Display files in a table."""
        table = Table(title=title)
        table.add_column("#", style="dim")
        table.add_column("File")
        table.add_column("Size", justify="right")
        table.add_column("Modified")

        for i, f in enumerate(files, 1):
            table.add_row(
                str(i),
                f.get("path", f.get("name", "unknown")),
                f.get("size_human", "?"),
                f.get("modified", f.get("days_old", "")),
            )

        self.console.print(table)

    def _format_bytes(self, size_bytes: int) -> str:
        """Format bytes as human-readable string (decimal units like macOS)."""
        if size_bytes >= 1000**3:
            return f"{size_bytes / 1000**3:.1f} GB"
        elif size_bytes >= 1000**2:
            return f"{size_bytes / 1000**2:.1f} MB"
        elif size_bytes >= 1000:
            return f"{size_bytes / 1000:.1f} KB"
        return f"{size_bytes} B"


def start_menu(
    console: Console | None = None,
    dry_run: bool = False,
    manual_mode: bool = False,
) -> None:
    """Start the menu-driven interface.

    Args:
        console: Rich console for output
        dry_run: If True, simulate cleanups without deleting
        manual_mode: If True, only show commands without executing
    """
    if console is None:
        console = Console()

    session = MenuSession(console=console, dry_run=dry_run, manual_mode=manual_mode)
    session.run()
