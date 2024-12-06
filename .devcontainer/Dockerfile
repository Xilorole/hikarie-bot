FROM debian:bookworm-slim AS builder

WORKDIR /opt

# The installer requires curl (and certificates) to download the release archive
# hadolint ignore=DL3008
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    curl

SHELL [ "/bin/bash", "-o", "pipefail", "-c" ]

# Download the latest installer
ADD https://astral.sh/uv/install.sh uv-installer.sh
ADD https://starship.rs/install.sh  starship-installer.sh

# Run the installer then remove it
RUN sh uv-installer.sh \
    && sh starship-installer.sh -y


FROM mcr.microsoft.com/vscode/devcontainers/base:bookworm

ENV CARGO_HOME="/opt/.cargo/bin"
ENV PATH="$CARGO_HOME/:$PATH"

ENV PYTHONUNBUFFERED=True
ENV UV_LINK_MODE=copy
ENV JUPYTER_PLATFORM_DIRS=1
ENV VIRTUAL_ENV_DISABLE_PROMPT=1

WORKDIR /opt

COPY --from=builder /usr/local/bin/starship /usr/local/bin/starship
COPY --from=builder /root/.local/bin/uv $CARGO_HOME/uv
COPY ./.python-version ./

RUN uv python pin "$(cat .python-version)"
RUN chown -R vscode $CARGO_HOME
