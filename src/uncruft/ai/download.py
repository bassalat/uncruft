"""Ollama model availability checks.

Note: Model downloads are handled by Ollama itself.
This module provides utilities for checking model availability.
"""

from rich.console import Console

from uncruft.ai.runtime import (
    DEFAULT_MODEL,
    is_model_available,
    is_ollama_running,
    pull_model,
)


def is_model_downloaded(variant: str = "default") -> bool:
    """Check if model is available in Ollama.

    Args:
        variant: Model variant (ignored for Ollama, kept for API compat)

    Returns:
        True if Ollama is running and model is available
    """
    return is_ollama_running() and is_model_available(DEFAULT_MODEL)


def ensure_model_ready(variant: str = "default", console: Console | None = None) -> None:
    """Ensure Ollama is running and model is available.

    Args:
        variant: Model variant (ignored for Ollama, kept for API compat)
        console: Rich console for output

    Raises:
        RuntimeError: If Ollama is not running
    """
    if console is None:
        console = Console()

    if not is_ollama_running():
        console.print("[red]Ollama is not running![/red]")
        console.print("\n[bold]To start Ollama:[/bold]")
        console.print("  1. Install: [cyan]brew install ollama[/cyan]")
        console.print("  2. Start:   [cyan]ollama serve[/cyan]")
        raise RuntimeError("Ollama not running. Start with: ollama serve")

    if not is_model_available(DEFAULT_MODEL):
        console.print(f"[yellow]Model '{DEFAULT_MODEL}' not found. Pulling...[/yellow]")
        pull_model(DEFAULT_MODEL, console)


def download_model(variant: str = "default", console: Console | None = None) -> None:
    """Download model via Ollama pull.

    Args:
        variant: Model variant (ignored for Ollama, kept for API compat)
        console: Rich console for output
    """
    if console is None:
        console = Console()

    if not is_ollama_running():
        raise RuntimeError("Ollama not running. Start with: ollama serve")

    pull_model(DEFAULT_MODEL, console)
