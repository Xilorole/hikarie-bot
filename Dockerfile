FROM alpine:3.21 AS builder

WORKDIR /opt

RUN apk update && \
    apk add --no-cache bash=5.2.37-r0 curl=8.12.1-r0 ca-certificates=20241121-r1 git=2.47.2-r0 python3=3.12.9-r0

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
    uv python pin "$(cat .python-version)" && \
    uv sync --no-dev

# Verify the presence of the .git directory
CMD [ "uv", "run", "--no-dev", "hikarie_bot"]
