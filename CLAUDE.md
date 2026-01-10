# Claude Code Instructions for uncruft

## Environment Rules

- **NEVER install packages to system Python** - always use the `uncruft` conda environment
- Test using Docker when possible: `docker build -t uncruft-test . && docker run --rm uncruft-test pytest tests/`
- User's conda env: `conda activate uncruft`

## Project Overview

uncruft is an AI-powered Mac disk cleanup CLI. It uses Ollama with Qwen3-1.7B for natural language interaction.

## Prerequisites

```bash
# Install Ollama (one-time)
brew install ollama

# Start Ollama server (keep running in background)
ollama serve

# Pull the model (one-time, ~500 MB)
ollama pull qwen3:0.6b
```

## Key Directories

- `src/uncruft/` - Main package
- `src/uncruft/ai/` - AI chat module (Ollama + Qwen3)
- `src/uncruft/tui/` - Legacy TUI (Textual)
- `tests/` - Pytest tests (178 tests)

## Commands

```bash
uncruft              # AI chat (default)
uncruft chat         # AI chat explicit
uncruft analyze      # Scan disk
uncruft clean --safe # Clean safe items
uncruft explain X    # Explain category
```

## Installation

```bash
conda activate uncruft
pip install -e .
```

## Testing

```bash
# In Docker (preferred)
docker build -t uncruft-test .
docker run --rm uncruft-test pytest tests/ -v

# In conda env
conda activate uncruft
pytest tests/ -v
```

## AI Backend

- **Runtime**: Ollama (HTTP API at localhost:11434)
- **Model**: qwen3:0.6b (~500 MB)
- **Model location**: Managed by Ollama (~/.ollama/models/)
