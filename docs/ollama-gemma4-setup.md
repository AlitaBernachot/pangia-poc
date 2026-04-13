# Ollama + Gemma 4 Setup Guide

This guide explains how to run a local **Ollama** server with the **Gemma 4** model inside the PangIA Docker Compose stack, and how to configure the backend agents to use it.

---

## Table of Contents

- [Ollama + Gemma 4 Setup Guide](#ollama--gemma-4-setup-guide)
  - [Table of Contents](#table-of-contents)
  - [Overview](#overview)
  - [Create the Ollama Volume (first-time setup)](#create-the-ollama-volume-first-time-setup)
  - [Start the Stack](#start-the-stack)
  - [Quick Smoke Test](#quick-smoke-test)
  - [Pull the Gemma 4 Model](#pull-the-gemma-4-model)
  - [Configure Backend Agents to Use Gemma 4](#configure-backend-agents-to-use-gemma-4)
  - [GPU Acceleration (Optional)](#gpu-acceleration-optional)
  - [Running Ollama Outside Docker](#running-ollama-outside-docker)
  - [CPU Performance Tuning](#cpu-performance-tuning)
    - [1. Allocate all CPU threads to Ollama](#1-allocate-all-cpu-threads-to-ollama)
    - [2. Remove Docker CPU/memory caps](#2-remove-docker-cpumemory-caps)
    - [3. Use a quantized model variant](#3-use-a-quantized-model-variant)
    - [4. Prevent memory swapping](#4-prevent-memory-swapping)
  - [Troubleshooting](#troubleshooting)

---

## Overview

The Docker Compose stack includes an **Ollama** service that:

- Exposes a local LLM REST API on port **11434**
- Persists downloaded models in a named Docker volume (`ollama_data`)
- Is reachable from the backend container at `http://ollama:11434`

The backend `model_config.py` already supports the `ollama` provider via `langchain-ollama`. Setting `<AGENT>_MODEL_PROVIDER=ollama` and `<AGENT>_MODEL_NAME=<model>` for any agent routes that agent's LLM calls to the local Ollama server.

---

## Create the Ollama Volume (first-time setup)

The `ollama_data` volume is declared as **external** in `docker-compose.yml`, which means Docker Compose will **never create or delete it automatically**. This protects downloaded model weights from being wiped by `docker compose down -v`.

Create the volume once before the first `docker compose up`:

```bash
docker volume create ollama_data
```

> **Why no project prefix?**
> Docker Compose only adds the `<project>_` prefix to volumes it **manages itself**. External volumes are referenced by their **exact name** — so the volume must be named `ollama_data`, not `pangia-poc_ollama_data`.

> **`docker compose down -v` safe?**
> Yes — because the volume is external, `-v` will remove the other volumes (neo4j, postgis, redis…) but will leave `ollama_data` untouched.

---

## Start the Stack

```bash
docker compose up -d
```

The `ollama` service starts automatically alongside all other services. Verify it is healthy:

```bash
docker compose ps ollama
```

You should see `healthy` in the status column.

---

## Quick Smoke Test

To test Ollama in isolation (without starting the full stack):

```bash
# Démarrer seulement Ollama en Docker
docker compose up ollama -d

# Vérifier les modèles disponibles
docker compose exec ollama ollama list

# Tester une inférence (petit modèle rapide même en CPU)
docker compose exec ollama ollama run gemma4:e2b "Say hi"
```

---

## Pull the Gemma 4 Model

Once the Ollama container is running, pull the Gemma 4 model into it. This downloads the model weights into the `ollama_data` volume so they persist across restarts.

```bash
# Pull the default (recommended) Gemma 4 variant (e4b, 9.6 GB)
docker compose exec ollama ollama pull gemma4

# Or pull a specific variant:
docker compose exec ollama ollama pull gemma4:e2b          # 2B MoE — lightest
docker compose exec ollama ollama pull gemma4:e4b          # 4B MoE — default
docker compose exec ollama ollama pull gemma4:26b          # 26B — high quality
docker compose exec ollama ollama pull gemma4:31b          # 31B — best quality (requires lots of RAM/VRAM)
```

> **Available tags**
>
> | Tag | Size | Context | Input |
> |---|---|---|---|
> | `gemma4:latest` / `gemma4:e4b` | 9.6 GB | 128K | Text, Image |
> | `gemma4:e2b` | 7.2 GB | 128K | Text, Image |
> | `gemma4:26b` | 18 GB | 256K | Text, Image |
> | `gemma4:31b` | 20 GB | 256K | Text, Image |
> | `gemma4:e2b-it-q4_K_M` | 7.2 GB | 128K | Text, Image |
> | `gemma4:e2b-it-q8_0` | 8.1 GB | 128K | Text, Image |
> | `gemma4:e2b-it-bf16` | 10 GB | 128K | Text, Image |
> | `gemma4:e4b-it-q4_K_M` | 9.6 GB | 128K | Text, Image |
> | `gemma4:e4b-it-q8_0` | 12 GB | 128K | Text, Image |
> | `gemma4:e4b-it-bf16` | 16 GB | 128K | Text, Image |
> | `gemma4:26b-a4b-it-q4_K_M` | 18 GB | 256K | Text, Image |
> | `gemma4:26b-a4b-it-q8_0` | 28 GB | 256K | Text, Image |
> | `gemma4:31b-it-q4_K_M` | 20 GB | 256K | Text, Image |
> | `gemma4:31b-it-q8_0` | 34 GB | 256K | Text, Image |
> | `gemma4:31b-it-bf16` | 63 GB | 256K | Text, Image |
> | `gemma4:31b-cloud` | — | 256K | Text, Image |
>
> GPU users: see [GPU Acceleration](#gpu-acceleration-optional) below.

Verify the model is available:

```bash
docker compose exec ollama ollama list
```

---

## Configure Backend Agents to Use Gemma 4

Add the following to your `.env` file (copy from `.env.example` as a starting point):

```env
# ── Ollama ────────────────────────────────────────────────────────────────────
# (already set automatically inside Docker; override only for local dev)
# OLLAMA_BASE_URL=http://localhost:11434

# ── Option A: route ALL agents to Gemma 4 via the global fallback ─────────────
MODEL_PROVIDER=ollama
MODEL_NAME=gemma4

# ── Option B: route specific agents only ──────────────────────────────────────
# Per-agent settings take priority over the global MODEL_PROVIDER / MODEL_NAME.
NEO4J_AGENT_MODEL_PROVIDER=ollama
NEO4J_AGENT_MODEL_NAME=gemma4

RDF_AGENT_MODEL_PROVIDER=ollama
RDF_AGENT_MODEL_NAME=gemma4

VECTOR_CHROMA_AGENT_MODEL_PROVIDER=ollama
VECTOR_CHROMA_AGENT_MODEL_NAME=gemma4

POSTGIS_AGENT_MODEL_PROVIDER=ollama
POSTGIS_AGENT_MODEL_NAME=gemma4

MAPVIZ_AGENT_MODEL_PROVIDER=ollama
MAPVIZ_AGENT_MODEL_NAME=gemma4

DATAVIZ_AGENT_MODEL_PROVIDER=ollama
DATAVIZ_AGENT_MODEL_NAME=gemma4

# Router and merge typically benefit from a stronger model.
# Keep them on OpenAI or point them at a larger Gemma 4 variant:
# ROUTER_MODEL_PROVIDER=ollama
# ROUTER_MODEL_NAME=gemma4:26b
# MERGE_MODEL_PROVIDER=ollama
# MERGE_MODEL_NAME=gemma4:26b
```

Restart the backend after updating `.env`:

```bash
docker compose restart backend
```

---

## GPU Acceleration (Optional)

To use your NVIDIA GPU for faster inference:

1. Install the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) on your host machine.
2. Uncomment the `deploy` block in the `ollama` service inside `docker-compose.yml`:

```yaml
ollama:
  image: ollama/ollama:latest
  # ...
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: all
            capabilities: [gpu]
```

3. Restart the Ollama service:

```bash
docker compose up -d --force-recreate ollama
```

Verify GPU is detected:

```bash
docker compose exec ollama ollama run gemma4 "Hello"
# Look for "GPU layers" in the output
```

---

## Running Ollama Outside Docker

If you prefer to run Ollama directly on your host machine (instead of inside Docker):

1. [Download and install Ollama](https://ollama.com/download) for your OS.
2. Pull the model:

   ```bash
   ollama pull gemma4
   ```

3. Start the Ollama server:

   ```bash
   ollama serve
   ```

4. Update `.env` to point the backend at your host Ollama instance:

   ```env
   OLLAMA_BASE_URL=http://host.docker.internal:11434
   ```

   > On Linux, replace `host.docker.internal` with your host's IP address on the Docker bridge network (usually `172.17.0.1`).

5. Optionally remove the `ollama` service from the Compose stack or disable it:

   ```bash
   docker compose stop ollama
   ```

---

## CPU Performance Tuning

When running without a GPU, inference is slow by default. The following Docker Compose overrides can significantly reduce latency.

### 1. Allocate all CPU threads to Ollama

By default Ollama auto-detects available threads, but inside Docker the count may be wrong. Override it explicitly in `docker-compose.yml`:

```yaml
ollama:
  environment:
    # Set to the number of physical cores on your host (check with `nproc`)
    - OLLAMA_NUM_THREADS=8
    # Keep only 1 model loaded at a time to avoid RAM pressure
    - OLLAMA_MAX_LOADED_MODELS=1
    # Disable parallel request processing (no benefit on CPU, wastes memory)
    - OLLAMA_NUM_PARALLEL=1
    # Enable Flash Attention (reduces memory bandwidth, speeds up inference)
    - OLLAMA_FLASH_ATTENTION=1
```

Check your core count:
```bash
nproc --all
```

### 2. Remove Docker CPU/memory caps

Make sure no `cpus` or `mem_limit` is set on the `ollama` service, or raise them:

```yaml
ollama:
  deploy:
    resources:
      limits:
        cpus: '0'        # 0 = no limit
        memory: 16G      # adjust to your available RAM
```

### 3. Use a quantized model variant

Quantized models are faster and use less RAM with minimal quality loss:

```bash
# q4_K_M is the best CPU trade-off (speed vs quality)
docker compose exec ollama ollama pull gemma4:e2b-it-q4_K_M
```

Then update `.env`:
```env
MODEL_NAME=gemma4:e2b-it-q4_K_M
```

### 4. Prevent memory swapping

Add `mem_swappiness` to keep the model in RAM and avoid swap thrashing:

```yaml
ollama:
  sysctls:
    - vm.swappiness=10
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `ollama` container stuck in `starting` | Wait for the health check to pass (~20 s). Run `docker compose logs ollama` to see errors. |
| Model pull fails with a network error | Check your internet connection and Docker DNS settings. |
| Backend agent returns `Unknown model provider 'ollama'` | Ensure `langchain-ollama` is installed (`pip install langchain-ollama`). It is included in `requirements.txt` by default. |
| Out-of-memory when running `gemma4:26b` or `gemma4:31b` | Switch to `gemma4:e4b` (9.6 GB) or `gemma4:e2b` (7.2 GB), or enable GPU acceleration. |
| `http://ollama:11434` unreachable from backend | Make sure the backend `depends_on` the `ollama` service (already configured) and that the `ollama` container is healthy. |
