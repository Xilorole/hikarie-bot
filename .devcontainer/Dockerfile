################################
# prepare step
################################

FROM hadolint/hadolint:latest-alpine AS hadolint

################################
# build step
################################

# hadolint ignore=DL3007
FROM alpine:latest AS builder

# hadolint ignore=DL3018
RUN apk update && \
    apk add --no-cache bash curl ca-certificates gcc musl-dev linux-headers

SHELL [ "/bin/bash", "-o", "pipefail", "-c" ]

ADD https://astral.sh/uv/install.sh uv-installer.sh
ADD https://starship.rs/install.sh starship-installer.sh

RUN sh uv-installer.sh \
    && sh starship-installer.sh -y

################################
# install step
################################

FROM mcr.microsoft.com/vscode/devcontainers/base:alpine

# Add hadolint and GitHub CLI
# hadolint ignore=DL3018
RUN apk update && \
    apk add --no-cache github-cli musl-dev linux-headers

WORKDIR /opt


ENV BIN_PATH="/usr/local/bin"

COPY --from=hadolint /bin/hadolint $BIN_PATH/hadolint
COPY --from=builder /usr/local/bin/starship $BIN_PATH/starship
COPY --from=builder /root/.local/bin/uv $BIN_PATH/uv
COPY --from=builder /root/.local/bin/uvx $BIN_PATH/uvx
COPY ./.python-version ./

RUN uv python pin "$(cat .python-version)"
