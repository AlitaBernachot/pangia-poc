# Ollama + Gemma 4 Setup Guide

This guide explains how to run a local **Ollama** server with the **Gemma 4** model inside the PangIA Docker Compose stack, and how to configure the backend agents to use it.

---

## Table of Contents

- [Overview](#overview)
- [Start the Stack](#start-the-stack)
- [Pull the Gemma 4 Model](#pull-the-gemma-4-model)
- [Configure Backend Agents to Use Gemma 4](#configure-backend-agents-to-use-gemma-4)
- [GPU Acceleration (Optional)](#gpu-acceleration-optional)
- [Running Ollama Outside Docker](#running-ollama-outside-docker)
- [Troubleshooting](#troubleshooting)

---

## Overview

The Docker Compose stack includes an **Ollama** service that:

- Exposes a local LLM REST API on port **11434**
- Persists downloaded models in a named Docker volume (`ollama_data`)
- Is reachable from the backend container at `http://ollama:11434`

The backend `model_config.py` already supports the `ollama` provider via `langchain-ollama`. Setting `<AGENT>_MODEL_PROVIDER=ollama` and `<AGENT>_MODEL_NAME=<model>` for any agent routes that agent's LLM calls to the local Ollama server.

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

## Pull the Gemma 4 Model

Once the Ollama container is running, pull the Gemma 4 model into it. This downloads the model weights into the `ollama_data` volume so they persist across restarts.

```bash
# Pull the default (recommended) Gemma 4 variant
docker compose exec ollama ollama pull gemma4

# Or pull a specific parameter size:
docker compose exec ollama ollama pull gemma4:9b    # 9 billion parameters
docker compose exec ollama ollama pull gemma4:27b   # 27 billion parameters (requires more RAM/VRAM)
```

> **Disk & RAM requirements**
>
> | Variant | Approx. model size | Minimum RAM (CPU) |
> |---|---|---|
> | `gemma4:9b` (default) | ~6 GB | 16 GB |
> | `gemma4:27b` | ~18 GB | 32 GB |
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

# ── Use Gemma 4 for specific agents ───────────────────────────────────────────

# Route all agents to Gemma 4 by setting each pair:
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
# ROUTER_MODEL_NAME=gemma4:27b
# MERGE_MODEL_PROVIDER=ollama
# MERGE_MODEL_NAME=gemma4:27b
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

## Troubleshooting

| Problem | Solution |
|---|---|
| `ollama` container stuck in `starting` | Wait for the health check to pass (~20 s). Run `docker compose logs ollama` to see errors. |
| Model pull fails with a network error | Check your internet connection and Docker DNS settings. |
| Backend agent returns `Unknown model provider 'ollama'` | Ensure `langchain-ollama` is installed (`pip install langchain-ollama`). It is included in `requirements.txt` by default. |
| Out-of-memory when running `gemma4:27b` | Switch to `gemma4:9b`, or enable GPU acceleration. |
| `http://ollama:11434` unreachable from backend | Make sure the backend `depends_on` the `ollama` service (already configured) and that the `ollama` container is healthy. |
