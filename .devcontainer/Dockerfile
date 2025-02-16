# to use hadolint binary
FROM hadolint/hadolint:latest-alpine AS hadolint

FROM alpine:3.21 AS builder

WORKDIR /opt

RUN apk update && \
    apk add --no-cache bash=5.2.37-r0 curl=8.12.1-r0 ca-certificates=20241121-r1

SHELL [ "/bin/bash", "-o", "pipefail", "-c" ]

ADD https://astral.sh/uv/install.sh uv-installer.sh
ADD https://starship.rs/install.sh  starship-installer.sh

RUN sh uv-installer.sh \
    && sh starship-installer.sh -y


FROM mcr.microsoft.com/vscode/devcontainers/base:alpine

# Add hadolint and GitHub CLI
RUN apk update && \
    apk add --no-cache musl-dev=1.2.5-r0 linux-headers=6.6-r0 github-cli=2.47.0-r4

ENV CARGO_HOME="/opt/.cargo/bin"
ENV PATH="$CARGO_HOME:$PATH"
ENV PYTHONUNBUFFERED=True
ENV UV_LINK_MODE=copy
ENV JUPYTER_PLATFORM_DIRS=1
ENV VIRTUAL_ENV_DISABLE_PROMPT=1

WORKDIR /opt

COPY --from=builder /usr/local/bin/starship /usr/local/bin/starship
COPY --from=builder /root/.local/bin/uv $CARGO_HOME/uv
COPY --from=hadolint /bin/hadolint /usr/local/bin/hadolint
COPY ./.python-version ./

RUN uv python pin "$(cat .python-version)"
RUN chown -R vscode "$CARGO_HOME"
