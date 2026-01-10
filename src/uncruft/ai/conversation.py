"""Conversation management for interactive chat sessions."""

import json
import re
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from uncruft.ai.prompts import SYSTEM_PROMPT
from uncruft.ai.runtime import chat_completion, initialize_model
from uncruft.ai.tools import TOOL_DEFINITIONS, ToolRegistry

# Destructive tools that require user confirmation before execution
DESTRUCTIVE_TOOLS = {"clean_category", "clean_multiple", "uninstall_app"}

# Patterns that indicate a bad response ending (small models often use these)
BAD_ENDING_PATTERNS = [
    "would you like",
    "let me know",
    "feel free",
    "is there anything else",
    "if you'd like",
    "if you need",
    "do you want",
]

# Pattern to detect existing numbered options at end of response
HAS_NUMBERED_OPTIONS = re.compile(r"\n\d+\.\s+\S.+\n\d+\.\s+\S", re.MULTILINE)

# Context-aware options to append based on last tool executed
CONTEXT_OPTIONS = {
    "scan_disk": [
        "Clean all safe items",
        "Clean specific category",
        "Find large files",
        "Exit",
    ],
    "get_storage_breakdown": [
        "Scan for cleanable items",
        "Explore largest category",
        "Find large files",
        "Exit",
    ],
    "get_disk_status": [
        "Scan for cleanable items",
        "Show storage breakdown",
        "Find large files",
        "Exit",
    ],
    "find_large_files": [
        "Delete a file",
        "Find more files",
        "Scan disk",
        "Exit",
    ],
    "find_old_files": [
        "Delete old files",
        "Find large files",
        "Scan disk",
        "Exit",
    ],
    "analyze_directory": [
        "Analyze parent folder",
        "Find large files here",
        "Scan disk",
        "Exit",
    ],
    "explain_category": [
        "Clean this category",
        "Protect this category",
        "Scan disk",
        "Exit",
    ],
    "clean_category": [
        "Clean another category",
        "Scan disk again",
        "Show disk status",
        "Exit",
    ],
    "clean_multiple": [
        "Clean more categories",
        "Scan disk again",
        "Show disk status",
        "Exit",
    ],
    "list_applications": [
        "Uninstall an app",
        "Find app data",
        "Scan disk",
        "Exit",
    ],
    "default": [
        "Scan disk for cleanable items",
        "Show disk status",
        "Find large files",
        "Exit",
    ],
}


@dataclass
class ChatSession:
    """Manages a single chat session with the AI."""

    console: Console
    dry_run: bool = False
    manual_mode: bool = False  # Only show commands, never execute
    tools: ToolRegistry = field(default_factory=lambda: ToolRegistry())
    messages: list[dict[str, Any]] = field(default_factory=list)
    _last_tool_name: str | None = field(default=None, repr=False)

    def __post_init__(self):
        """Initialize session with system prompt."""
        self.tools = ToolRegistry(dry_run=self.dry_run)
        # Just system prompt - few-shot examples were causing model confusion
        # The post-processing function handles ensuring numbered endings
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self._last_tool_name = None

    def _expand_number_input(self, user_input: str) -> str:
        """Expand single-digit input into explicit command.

        When user types "2" after seeing options like:
          1. Scan disk  2. Show disk status  3. Find files
        This expands "2" to "Show disk status" so the AI understands.
        """
        stripped = user_input.strip()

        # Only handle single digits 1-9
        if not (len(stripped) == 1 and stripped.isdigit() and stripped != "0"):
            return user_input

        num = int(stripped)

        # Get options based on last tool (or default)
        options = CONTEXT_OPTIONS.get(self._last_tool_name, CONTEXT_OPTIONS["default"])

        if 1 <= num <= len(options):
            return options[num - 1]

        return user_input

    def _ensure_numbered_ending(self, response: str, last_tool: str | None) -> str:
        """Ensure response ends with numbered options.

        Small models often end with open questions like "Would you like to...?"
        This post-processes the response to guarantee numbered options at the end.

        Args:
            response: The AI's response text
            last_tool: Name of the last tool executed (for context-aware options)

        Returns:
            Response with numbered options appended if needed
        """
        if not response:
            return response

        # Check if already has numbered options at end (must be in last 300 chars)
        last_300 = response[-300:] if len(response) > 300 else response
        if HAS_NUMBERED_OPTIONS.search(last_300):
            # Has numbered options - but still check for bad endings after them
            last_100_lower = response[-100:].lower()
            has_trailing_bad = any(pattern in last_100_lower for pattern in BAD_ENDING_PATTERNS)
            if not has_trailing_bad:
                return response  # Good numbered ending with no trailing bad phrase

        # Get context-appropriate options based on last tool
        options = CONTEXT_OPTIONS.get(last_tool, CONTEXT_OPTIONS["default"])

        # Build numbered options string
        options_str = "\n\n**Next Steps:**\n"
        for i, opt in enumerate(options, 1):
            options_str += f"{i}. {opt}\n"

        # Remove bad ending phrases if present
        cleaned = response.rstrip()
        for pattern in BAD_ENDING_PATTERNS:
            # Check if pattern is in the last part of the response
            pattern_pos = cleaned.lower().rfind(pattern)
            if pattern_pos != -1 and pattern_pos > len(cleaned) - 200:
                # Find sentence boundary before the bad pattern
                before_pattern = cleaned[:pattern_pos]
                # Look for last sentence end (. or newline followed by content)
                last_period = before_pattern.rfind(".")
                last_newline = before_pattern.rfind("\n")
                cut_point = max(last_period, last_newline)
                if cut_point > 0:
                    cleaned = cleaned[:cut_point + 1].rstrip()
                break

        return cleaned + options_str

    def chat(self, user_input: str) -> str:
        """Process user input and return AI response.

        Args:
            user_input: User's message

        Returns:
            AI response text
        """
        # Expand number selections (e.g., "2" -> "Show disk status")
        expanded_input = self._expand_number_input(user_input)

        # Add user message (use expanded version)
        self.messages.append({"role": "user", "content": expanded_input})

        # Get AI response
        response = chat_completion(
            messages=self.messages,
            tools=TOOL_DEFINITIONS,
            max_tokens=1024,
            temperature=0.7,
        )

        assistant_message = response["choices"][0]["message"]

        # Check for tool calls
        if tool_calls := assistant_message.get("tool_calls"):
            return self._handle_tool_calls(assistant_message, tool_calls)

        # Regular text response (no tool called)
        content = assistant_message.get("content", "")
        content = self._ensure_numbered_ending(content, None)
        self.messages.append({"role": "assistant", "content": content})
        return content

    def _handle_tool_calls(
        self, assistant_message: dict[str, Any], tool_calls: list[dict[str, Any]],
        depth: int = 0
    ) -> str:
        """Execute tools and continue conversation.

        Args:
            assistant_message: The assistant's message with tool calls
            tool_calls: List of tool calls to execute
            depth: Current recursion depth (to prevent infinite loops)

        Returns:
            Final response after tool execution
        """
        # Prevent infinite recursion
        MAX_TOOL_DEPTH = 5
        if depth >= MAX_TOOL_DEPTH:
            self.messages.append({
                "role": "assistant",
                "content": "I've made several tool calls. Let me summarize what I found."
            })
            return "I've gathered the information. What would you like to know?"

        # Add assistant message with tool calls
        self.messages.append(assistant_message)

        # Execute each tool call
        for tool_call in tool_calls:
            function_name = tool_call["function"]["name"]
            function_args = tool_call["function"]["arguments"]

            # Track last tool for context-aware post-processing
            self._last_tool_name = function_name

            # Parse arguments if they're a JSON string (Ollama sometimes returns strings)
            if isinstance(function_args, str):
                try:
                    function_args = json.loads(function_args)
                except json.JSONDecodeError:
                    function_args = {}

            # Require confirmation for destructive operations
            if function_name in DESTRUCTIVE_TOOLS:
                if not self._confirm_destructive_action(function_name, function_args):
                    # User declined - add cancelled result
                    self.messages.append({
                        "role": "tool",
                        "tool_name": function_name,
                        "content": json.dumps({"cancelled": True, "reason": "User declined"}),
                    })
                    continue

            # Show what's happening
            self.console.print(f"[dim]Executing: {function_name}...[/dim]")

            # Execute the tool
            result = self.tools.execute(function_name, function_args)

            # Mark errors clearly so AI can distinguish from valid data
            if isinstance(result, dict) and "error" in result:
                result["_is_error"] = True

            # Add tool result to messages
            self.messages.append({
                "role": "tool",
                "tool_name": function_name,
                "content": json.dumps(result),
            })

        # Get follow-up response from AI
        response = chat_completion(
            messages=self.messages,
            tools=TOOL_DEFINITIONS,
            max_tokens=1024,
            temperature=0.7,
        )

        follow_up = response["choices"][0]["message"]

        # Handle nested tool calls (if AI wants to call more tools)
        if follow_up.get("tool_calls"):
            return self._handle_tool_calls(follow_up, follow_up["tool_calls"], depth + 1)

        # Post-process to ensure numbered options at end
        content = follow_up.get("content", "")
        content = self._ensure_numbered_ending(content, self._last_tool_name)
        self.messages.append({"role": "assistant", "content": content})
        return content

    def _confirm_destructive_action(self, function_name: str, args: dict) -> bool:
        """Prompt user to confirm destructive action.

        Args:
            function_name: Name of the destructive tool
            args: Tool arguments

        Returns:
            True if user confirms, False if declined
        """
        if function_name == "clean_category":
            category = args.get("category_id", "unknown")
            msg = f"Delete files in [bold]{category}[/bold]?"
        elif function_name == "clean_multiple":
            categories = args.get("category_ids", [])
            msg = f"Delete files in [bold]{', '.join(categories)}[/bold]?"
        elif function_name == "uninstall_app":
            app = args.get("app_name", "unknown")
            msg = f"Uninstall [bold]{app}[/bold] and all its data?"
        else:
            msg = f"Execute {function_name}?"

        # Manual mode: never execute, only show commands
        if self.manual_mode:
            self.console.print(f"\n[cyan]📋 {msg}[/cyan]")
            self.console.print("[dim]Manual mode: Copy the command above to run yourself[/dim]")
            return False  # Never execute in manual mode

        if self.dry_run:
            self.console.print(f"[yellow]DRY RUN: {msg}[/yellow]")
            return True  # Auto-confirm in dry-run mode

        self.console.print(f"\n[yellow]⚠ {msg}[/yellow] [dim](Y/n)[/dim] ", end="")
        response = input().strip().lower()

        return response in ("", "y", "yes")


def start_chat(
    console: Console | None = None,
    dry_run: bool = False,
    manual_mode: bool = False,
    variant: str = "default",
) -> None:
    """Start an interactive chat session.

    Args:
        console: Rich console for output
        dry_run: If True, simulate cleanups without deleting
        manual_mode: If True, only show commands without executing
        variant: Model variant to use
    """
    if console is None:
        console = Console()

    # Welcome message
    console.print(
        Panel(
            "[bold blue]Uncruft AI Chat[/bold blue]\n"
            "[dim]Natural language disk cleanup assistant[/dim]",
            expand=False,
        )
    )

    if manual_mode:
        console.print("[cyan]Manual mode: Commands will be shown but not executed[/cyan]\n")
    elif dry_run:
        console.print("[yellow]Dry-run mode: No files will be deleted[/yellow]\n")

    console.print("[dim]Type 'exit' or 'quit' to leave. Type 'help' for tips.[/dim]\n")

    # Initialize model
    with console.status("[dim]Loading AI model...[/dim]"):
        initialize_model(variant=variant, console=console)

    console.print("[green]Ready![/green] How can I help clean your disk?\n")

    # Create session
    session = ChatSession(console=console, dry_run=dry_run, manual_mode=manual_mode)

    # Main chat loop
    while True:
        try:
            user_input = console.input("[bold cyan]You:[/bold cyan] ").strip()

            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit", "q"):
                console.print("\n[dim]Goodbye![/dim]")
                break

            if user_input.lower() == "help":
                _show_help(console)
                continue

            # Process with status indicator
            with console.status("[dim]Thinking...[/dim]"):
                response = session.chat(user_input)

            # Display response as markdown
            console.print()
            console.print(Markdown(response))
            console.print()

        except KeyboardInterrupt:
            console.print("\n[dim]Interrupted. Goodbye![/dim]")
            break
        except Exception as e:
            console.print(f"\n[red]Error: {e}[/red]\n")


def _show_help(console: Console) -> None:
    """Show help tips."""
    console.print(
        Panel(
            """[bold]Tips:[/bold]

- "scan my disk" - See what's using space
- "what's in npm cache?" - Explain a category
- "clean docker and npm" - Clean specific items
- "clean all safe items" - Clean everything marked safe

[bold]Examples:[/bold]

- "What's eating my disk?"
- "Is it safe to delete conda cache?"
- "Clean the browser caches"
- "How do I recover node_modules?"

[dim]Type 'exit' to quit[/dim]""",
            title="Help",
            expand=False,
        )
    )
