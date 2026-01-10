# Dockerfile for uncruft development
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast package management
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy dependency files first (better layer caching)
COPY pyproject.toml README.md ./

# Create src directory structure for editable install
RUN mkdir -p src/uncruft && touch src/uncruft/__init__.py

# Install dependencies
RUN uv pip install --system -e ".[dev]"

# Copy source code
COPY . .

# Re-install with actual source
RUN uv pip install --system -e ".[dev]"

# Default command
CMD ["uncruft", "--help"]
