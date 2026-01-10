"""Ollama runtime initialization and management."""

from typing import Any

import httpx
from rich.console import Console

# Ollama configuration
OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen3:0.6b"

# Global state
_initialized: bool = False
_model: str = DEFAULT_MODEL


def is_ollama_running() -> bool:
    """Check if Ollama server is running."""
    try:
        response = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5.0)
        return response.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


def is_model_available(model: str = DEFAULT_MODEL) -> bool:
    """Check if the specified model is available in Ollama."""
    try:
        response = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5.0)
        if response.status_code != 200:
            return False
        models = response.json().get("models", [])
        model_names = [m.get("name", "") for m in models]
        # Check for exact match or model:latest
        return model in model_names or f"{model}:latest" in model_names
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


def is_model_ready(variant: str = "default") -> bool:
    """Check if model is ready (Ollama running + model available)."""
    return is_ollama_running() and is_model_available(_model)


def initialize_model(
    variant: str = "default",
    console: Console | None = None,
    **kwargs,
) -> None:
    """Initialize connection to Ollama.

    Args:
        variant: Model variant (ignored for Ollama, kept for API compat)
        console: Rich console for output
        **kwargs: Additional arguments (ignored, kept for API compat)
    """
    global _initialized

    if _initialized:
        return

    if console is None:
        console = Console()

    # Check Ollama is running
    if not is_ollama_running():
        console.print("[red]Ollama is not running![/red]")
        console.print("\n[bold]To fix this:[/bold]")
        console.print("  1. Install Ollama: [cyan]brew install ollama[/cyan]")
        console.print("  2. Start Ollama:   [cyan]ollama serve[/cyan]")
        console.print(f"  3. Pull model:     [cyan]ollama pull {_model}[/cyan]")
        raise RuntimeError("Ollama not running. Start with: ollama serve")

    # Check model is available
    if not is_model_available(_model):
        console.print(f"[yellow]Model '{_model}' not found. Pulling...[/yellow]")
        try:
            pull_model(_model, console)
        except Exception as e:
            console.print(f"[red]Failed to pull model: {e}[/red]")
            console.print(f"\n[bold]To fix manually:[/bold]")
            console.print(f"  [cyan]ollama pull {_model}[/cyan]")
            raise

    console.print("[green]AI ready![/green]\n")
    _initialized = True


def pull_model(model: str, console: Console | None = None) -> None:
    """Pull a model from Ollama.

    Args:
        model: Model name to pull
        console: Rich console for output
    """
    if console is None:
        console = Console()

    console.print(f"[dim]Downloading {model}... (this may take a few minutes)[/dim]")

    # Use streaming to show progress
    with httpx.stream(
        "POST",
        f"{OLLAMA_URL}/api/pull",
        json={"name": model},
        timeout=600.0,
    ) as response:
        for line in response.iter_lines():
            if line:
                import json
                try:
                    data = json.loads(line)
                    status = data.get("status", "")
                    if "pulling" in status.lower() or "download" in status.lower():
                        completed = data.get("completed", 0)
                        total = data.get("total", 0)
                        if total > 0:
                            pct = completed / total * 100
                            console.print(f"\r[dim]{status}: {pct:.1f}%[/dim]", end="")
                except json.JSONDecodeError:
                    pass

    console.print("\n[green]Model downloaded![/green]")


def get_model() -> str | None:
    """Get the current model name."""
    return _model if _initialized else None


def chat_completion(
    messages: list[dict[str, str]],
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.7,
) -> dict[str, Any]:
    """Create a chat completion via Ollama.

    Args:
        messages: List of chat messages
        tools: Optional list of tools for function calling
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature

    Returns:
        Chat completion response in OpenAI-compatible format
    """
    if not _initialized:
        raise RuntimeError("Model not initialized. Call initialize_model() first.")

    payload: dict[str, Any] = {
        "model": _model,
        "messages": messages,
        "stream": False,
        "think": False,  # Disable thinking mode to prevent internal reasoning from leaking
        "options": {
            "num_predict": max_tokens,
            "temperature": 0.6,       # Lower for more focused, instruction-following output
            "top_p": 0.8,             # Nucleus sampling for balanced diversity
            "top_k": 20,              # Limit candidate tokens for coherence
            "repeat_penalty": 1.3,    # Prevent repetition loops (important for small models)
        },
    }

    if tools:
        payload["tools"] = tools

    try:
        response = httpx.post(
            f"{OLLAMA_URL}/api/chat",
            json=payload,
            timeout=120.0,
        )
        response.raise_for_status()
        result = response.json()

        # Convert Ollama response to OpenAI-compatible format
        return {
            "choices": [
                {
                    "message": result.get("message", {}),
                    "finish_reason": "stop",
                }
            ]
        }
    except httpx.TimeoutException:
        raise RuntimeError("Ollama request timed out. The model may be loading.")
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"Ollama request failed: {e}")
