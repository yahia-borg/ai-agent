# syntax=docker/dockerfile:1.4
# ^^^ Required for BuildKit cache mount syntax (--mount=type=cache)
FROM nvidia/cuda:12.6.1-runtime-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Africa/Cairo \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=0 \
    PIP_CACHE_DIR=/root/.cache/pip

WORKDIR /app

# ── System packages ────────────────────────────────────────────────────────
# Cache mount keeps /var/cache/apt between builds — no re-download on rebuild.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3.11-venv \
    python3-pip \
    gcc \
    g++ \
    postgresql-client \
    fonts-dejavu \
    libyaml-dev \
    && apt-get purge -y --auto-remove software-properties-common

# Set Python 3.11 as default
RUN ln -sf /usr/bin/python3.11 /usr/bin/python3 && \
    ln -sf /usr/bin/python3.11 /usr/bin/python && \
    python3.11 -m ensurepip --upgrade

# ── PyTorch (separate layer — huge wheel, rarely changes) ──────────────────
# Cache mount keeps the ~2 GB torch wheel in /root/.cache/pip across rebuilds.
# This layer only re-runs when the torch index URL or version changes.
RUN --mount=type=cache,target=/root/.cache/pip \
    python3 -m pip install --break-system-packages \
    torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cu124

# ── Python dependencies ────────────────────────────────────────────────────
# Copy requirements first so this layer is only invalidated when requirements.txt changes.
# Cache mount keeps all previously downloaded wheels — only new/updated packages download.
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    python3 -m pip install --break-system-packages -r requirements.txt

# ── Application code ───────────────────────────────────────────────────────
# Copied last — code changes do not invalidate the dependency layers above.
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
