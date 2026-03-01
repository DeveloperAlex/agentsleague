FROM python:3.12-slim

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml ./

# Install dependencies (pre-release allowed, system-wide)
RUN uv pip install --system --pre -r pyproject.toml

# Copy application source
COPY . .

# The hosting adapter listens on port 8088
EXPOSE 8088

CMD ["python", "main.py"]
