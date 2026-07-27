# syntax=docker/dockerfile:1.7

FROM python:3.12.10-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN python -m pip install --no-cache-dir uv==0.8.14

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY tdx ./tdx
COPY qmt ./qmt
RUN uv sync --frozen --no-dev

FROM python:3.12.10-slim-bookworm AS runtime

ENV APP_ENV=production \
    LOG_LEVEL=INFO \
    PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN groupadd --gid 10001 mist \
    && useradd --uid 10001 --gid mist --no-create-home --home-dir /nonexistent mist \
    && mkdir -p /app /var/lib/mist-datasource/qmt \
    && chown -R mist:mist /app /var/lib/mist-datasource

WORKDIR /app
COPY --from=builder --chown=mist:mist /app /app

USER 10001:10001

EXPOSE 9001 9002

CMD ["uvicorn", "tdx.main:app", "--host", "0.0.0.0", "--port", "9001"]
