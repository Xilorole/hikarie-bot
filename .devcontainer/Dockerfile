################################
# prepare step
################################

FROM hadolint/hadolint:v2.15.1-alpine@sha256:a1d49ae1a4e83c1dbad26b8c1ad7588c8bd1e04f4866b34ad3cac50335198552 AS hadolint
FROM ghcr.io/astral-sh/uv:0.11.26@sha256:3d868e555f8f1dbc324afa005066cd11e1053fc4743b9808ca8025283e65efa5 AS uv

################################
# build step
################################

FROM alpine:3.22 AS builder

# hadolint ignore=DL3018
RUN apk add --no-cache bash curl ca-certificates

SHELL [ "/bin/bash", "-o", "pipefail", "-c" ]

ADD https://starship.rs/install.sh starship-installer.sh

RUN sh starship-installer.sh -y --version v1.27.0

################################
# install step
################################

FROM mcr.microsoft.com/vscode/devcontainers/base:alpine@sha256:190bccaf23c9e88f21734f82b08b597310efcd4aa9240faf7e96d98c228753e3

# Add hadolint and GitHub CLI
# hadolint ignore=DL3018
RUN apk add --no-cache github-cli musl-dev linux-headers

WORKDIR /opt


ENV BIN_PATH="/usr/local/bin"
ENV UV_PYTHON_INSTALL_DIR="/opt/python"

COPY --from=hadolint /bin/hadolint $BIN_PATH/hadolint
COPY --from=builder /usr/local/bin/starship $BIN_PATH/starship
COPY --from=uv /uv $BIN_PATH/uv
COPY --from=uv /uvx $BIN_PATH/uvx
COPY ./.python-version ./

RUN uv python install "$(cat .python-version)"
