# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 AS uv
FROM python:3.14-slim-bookworm@sha256:516b51cb9db2ef061e465c803e50f64361b82cefd91e525b889b967b83e83527 AS base

FROM base AS builder

COPY --from=uv /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /opt

# hadolint ignore=DL3008
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-default-groups --group core --no-install-project

COPY README.md LICENSE ./
COPY hikarie_bot hikarie_bot
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=.git,target=.git \
    uv sync --locked --no-default-groups --group core --no-editable --refresh-package hikarie-bot

FROM base AS runtime

ENV PYTHONUNBUFFERED=1

WORKDIR /opt

RUN groupadd --gid 10001 bot && \
    useradd --uid 10001 --gid bot --no-log-init --create-home bot && \
    mkdir .db && chown bot:bot .db

COPY --from=builder /opt/.venv /opt/.venv

USER 10001:10001

FROM runtime AS bot

# the commit this image is built from, shown in the startup messages (Release passes github.sha)
ARG APP_REVISION=unknown
ENV APP_REVISION=${APP_REVISION}

CMD ["/opt/.venv/bin/python", "-m", "hikarie_bot", "start"]
