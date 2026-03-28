FROM python:3.11-slim

WORKDIR /backend

# System build dependencies required by asyncpg (C extension) and chromadb
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY libs/ ./libs/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
