FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency resolution
RUN pip install uv

# Copy project files
COPY pyproject.toml uv.lock* ./
COPY main.py ./
COPY agents/ ./agents/

# Install dependencies using uv with pre-release support
RUN uv pip install --system --prerelease=allow -e .

EXPOSE 8088

CMD ["python", "main.py"]
