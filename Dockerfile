FROM alpine:3.21 AS builder

WORKDIR /opt

# hadolint ignore=DL3018
RUN apk update && \
    apk add --no-cache bash curl ca-certificates git

SHELL [ "/bin/bash", "-o", "pipefail", "-c" ]

ADD https://astral.sh/uv/install.sh uv-installer.sh
RUN sh uv-installer.sh

WORKDIR /opt

# Copy only the necessary files and directories
COPY .git .git
RUN if [ ! -d ".git" ]; then echo ".git directory not found"; exit 1; fi
COPY hikarie_bot hikarie_bot
COPY pyproject.toml uv.lock .python-version ./

# Install the dependencies
ENV PATH="/root/.local/bin:$PATH"
RUN mkdir .db && \
    uv python pin "$(cat .python-version)"

# Verify the presence of the .git directory
CMD [ "uv", "run","--no-group", "jupyter", "hikarie_bot"]
