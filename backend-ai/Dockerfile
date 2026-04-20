# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /backend-ai

# System build dependencies required by asyncpg (C extension) and chromadb
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN uv pip install --system -r requirements.txt

COPY app/ ./app/
COPY libs/ ./libs/

EXPOSE 8086

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8086"]
