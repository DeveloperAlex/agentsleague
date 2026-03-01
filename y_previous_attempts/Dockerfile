FROM python:3.12-slim

# Install uv for fast, reproducible dependency installation
RUN pip install --no-cache-dir uv

WORKDIR /app

COPY . user_agent/
WORKDIR /app/user_agent

# Install pre-release packages using uv (pinned versions in requirements.txt)
# RUN uv pip install --system --pre -r requirements.txt
RUN uv lock
RUN uv sync

EXPOSE 8088

CMD ["python", "main.py"]
