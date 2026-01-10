"""Main TUI application for uncruft."""

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Footer, Header, Static

from uncruft.tui.screens import CleanupScreen, MainScreen


class UncruftApp(App):
    """Interactive disk cleanup application."""

    TITLE = "uncruft"
    SUB_TITLE = "Smart Mac Disk Cleanup"

    CSS_PATH = "styles.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("?", "help", "Help"),
        Binding("r", "refresh", "Refresh"),
        Binding("d", "toggle_dark", "Toggle Dark"),
        Binding("escape", "back", "Back", show=False),
    ]

    SCREENS = {
        "main": MainScreen,
        "cleanup": CleanupScreen,
    }

    def __init__(self, dry_run: bool = False, include_dev: bool = True):
        super().__init__()
        self.dry_run = dry_run
        self.include_dev = include_dev
        self.analysis = None
        self.selected_items: set[str] = set()

    def on_mount(self) -> None:
        """Called when the app is mounted."""
        self.push_screen("main")

    def action_toggle_dark(self) -> None:
        """Toggle dark mode."""
        self.dark = not self.dark

    def action_refresh(self) -> None:
        """Refresh current screen data."""
        screen = self.screen
        if hasattr(screen, "refresh_data"):
            screen.refresh_data()

    def action_back(self) -> None:
        """Go back to previous screen."""
        if len(self.screen_stack) > 1:
            self.pop_screen()

    def action_help(self) -> None:
        """Show help information."""
        self.notify(
            "Use arrow keys to navigate, Space to select, Enter to view details, C to clean selected",
            title="Help",
            timeout=5,
        )


def run_tui(dry_run: bool = False, include_dev: bool = True) -> None:
    """Run the interactive TUI.

    Args:
        dry_run: If True, don't actually delete files
        include_dev: If True, include developer artifact scanning
    """
    app = UncruftApp(dry_run=dry_run, include_dev=include_dev)
    app.run()
