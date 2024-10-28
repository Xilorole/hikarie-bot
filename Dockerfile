ARG VARIANT=3.12
FROM python:${VARIANT} AS builder

ENV PYTHONDONTWRITEBYTECODE=True
ENV UV_LINK_MODE=copy

WORKDIR /opt

# Copy only the necessary files and directories
COPY .git .git
COPY hikarie_bot hikarie_bot
COPY pyproject.toml uv.lock ./

# Verify the presence of the .git directory
RUN if [ ! -d ".git" ]; then echo ".git directory not found"; exit 1; fi

# hadolint ignore=DL3013,DL3042
RUN pip install --upgrade pip && \
    pip install uv && \
    uv export --frozen --no-dev --format requirements-txt > requirements.txt && \
    uv pip install -r requirements.txt --system

FROM python:${VARIANT}-slim
ARG VARIANT=3.12
COPY --from=builder /usr/local/lib/python*/site-packages /usr/local/lib/python${VARIANT}/site-packages

ENV PYTHONUNBUFFERED=True

WORKDIR /
RUN mkdir .db
COPY hikarie_bot hikarie_bot

CMD [ "python", "-m", "hikarie_bot" ]
