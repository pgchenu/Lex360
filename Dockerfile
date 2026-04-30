# syntax=docker/dockerfile:1.7

FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build

# Install lex360 from the local source — never modified, just consumed.
COPY pyproject.toml README.md ./
COPY lex360/ ./lex360/
RUN pip install .

# Install gateway runtime deps.
COPY gateway/requirements.txt /tmp/gateway-requirements.txt
RUN pip install -r /tmp/gateway-requirements.txt


FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Non-root user
RUN useradd --create-home --shell /usr/sbin/nologin --uid 10001 gateway

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY gateway/ /app/gateway/

USER gateway
EXPOSE 8000

CMD ["uvicorn", "gateway.server:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
