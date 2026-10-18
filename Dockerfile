# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:0.11.26@sha256:3d868e555f8f1dbc324afa005066cd11e1053fc4743b9808ca8025283e65efa5 AS uv
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS base

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
    uv sync --locked --no-default-groups --group core --no-editable

FROM base AS runtime

ENV PYTHONUNBUFFERED=1

WORKDIR /opt

RUN groupadd --gid 10001 bot && \
    useradd --uid 10001 --gid bot --no-log-init --create-home bot && \
    mkdir .db && chown bot:bot .db

COPY --from=builder /opt/.venv /opt/.venv

USER bot

FROM runtime AS initial-data

ENV ENV=test
COPY initial-data/ /opt/initial-data/

ENTRYPOINT ["/opt/.venv/bin/python", "-m", "hikarie_bot.initial_data"]

FROM runtime AS bot

CMD ["/opt/.venv/bin/python", "-m", "hikarie_bot", "start"]
