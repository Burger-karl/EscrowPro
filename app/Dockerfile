FROM python:3.12-slim

WORKDIR /app

# psycopg[binary] avoids needing libpq-dev, but keep build tools minimal
# in case any transitive dep needs to compile.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# uv — same tool devs use locally, so the container build matches
# `uv sync` exactly instead of drifting via a separate requirements.txt.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
