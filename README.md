# uncruft

AI-powered Mac disk cleanup CLI - find and remove cruft safely.

uncruft scans your Mac for caches, build artifacts, and unused data, then helps you clean them up with clear explanations of what each item is and whether it's safe to delete.

## Quick Start

```bash
# 1. Install Ollama (AI backend)
brew install ollama

# 2. Start Ollama (keep running in background)
ollama serve

# 3. Pull the AI model (~500 MB, one-time)
ollama pull qwen3:0.6b

# 4. Install uncruft
pip install -e .

# 5. Run it
uncruft
```

## Prerequisites

- **macOS** (tested on Ventura, Sonoma, Sequoia)
- **Python 3.9+**
- **Ollama** - Local AI runtime for natural language features

### Installing Ollama

```bash
# Install via Homebrew
brew install ollama

# Start the Ollama server (run in background or separate terminal)
ollama serve

# Pull the model (one-time, ~500 MB download)
ollama pull qwen3:0.6b
```

The Ollama server must be running for AI features. Without it, uncruft still works but skips AI-powered explanations.

## Installation

### From Source (Development)

```bash
# Clone the repo
git clone https://github.com/yourusername/uncruft.git
cd uncruft

# Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate

# Install in development mode
pip install -e .

# Run
uncruft
```

### With Conda

```bash
# Create and activate environment
conda create -n uncruft python=3.11
conda activate uncruft

# Install
pip install -e .
```

## Usage

### Interactive Mode (Recommended)

```bash
uncruft
```

This launches an interactive menu:

```
Main Menu

1. Show disk status
2. Scan disk for cleanable items
3. Find large files
4. Find old files
5. Explore folder
6. Ask a question
0. Exit
```

### CLI Commands

```bash
# Analyze disk usage
uncruft analyze

# Clean only safe items (caches that auto-regenerate)
uncruft clean --safe

# Clean a specific category
uncruft clean --category npm_cache

# Preview what would be cleaned (dry run)
uncruft clean --safe --dry-run

# Explain what a category contains
uncruft explain conda_cache

# Show current disk status
uncruft status
```

### Common Categories

| Category | Risk | Description |
|----------|------|-------------|
| `npm_cache` | Safe | NPM package cache |
| `pip_cache` | Safe | Python package cache |
| `conda_cache` | Safe | Conda package cache |
| `homebrew_cache` | Safe | Homebrew downloads |
| `app_caches` | Safe | Application caches |
| `docker_data` | Review | Docker images/containers |
| `node_modules` | Safe | Project dependencies |

## Development

### Running Tests

```bash
# With Docker (preferred - isolated environment)
docker build -t uncruft-test .
docker run --rm uncruft-test pytest tests/ -v

# Locally
pip install -e ".[dev]"
pytest tests/ -v
```

### Docker Development Environment

```bash
# Build the dev container
docker-compose build

# Start interactive shell
docker-compose run --rm dev

# Run tests
docker-compose run --rm test

# Run linter
docker-compose run --rm lint
```

### Code Quality

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run linter
ruff check src tests

# Run tests with coverage
pytest --cov=uncruft tests/
```

## How It Works

1. **Scanning** - uncruft scans known locations for caches, build artifacts, and temporary files
2. **Categorization** - Items are categorized by type and risk level (safe, review, risky)
3. **AI Explanations** - Ollama provides natural language explanations of what each item is
4. **Safe Cleanup** - Only items marked "safe" are cleaned automatically; others require confirmation

### Architecture

```
src/uncruft/
├── cli.py          # CLI entry point (Typer)
├── scanner.py      # Disk scanning logic
├── categories.py   # Category definitions
├── models.py       # Data models (Pydantic)
├── analyzer.py     # Analysis functions
├── display.py      # Rich console output
└── ai/
    ├── menu.py     # Interactive menu
    └── tools.py    # AI tool definitions
```

## License

MIT
