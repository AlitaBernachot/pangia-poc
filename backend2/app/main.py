# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from openinference.instrumentation.langchain import LangChainInstrumentor
from phoenix.otel import register

from app.api.routes.chat import router as chat_router
from app.api.routes.suggestions import router as suggestions_router
from app.config import get_settings
from app.db import close_engine
from app.pangiagent.memory import close_redis
from app.pangiagent.source_registry import bootstrap_registry_embeddings

logger = logging.getLogger(__name__)


def _setup_phoenix(settings) -> None:
    """Initialise Arize Phoenix tracing for LangChain agents."""
    tracer_provider = register(
        project_name=settings.phoenix_project_name,
        endpoint=settings.phoenix_collector_endpoint,
    )
    LangChainInstrumentor().instrument(tracer_provider=tracer_provider)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    _setup_phoenix(settings)
    try:
        await bootstrap_registry_embeddings()
    except Exception:
        logger.warning("lifespan: bootstrap_registry_embeddings failed — continuing without ChromaDB routing", exc_info=True)
    print(
        "\n"
        "██████╗  █████╗ ███╗   ██╗ ██████╗ ██╗  █████╗ \n"
        "██╔══██╗██╔══██╗████╗  ██║██╔════╝ ██║ ██╔══██╗\n"
        "██████╔╝███████║██╔██╗ ██║██║  ███╗██║ ███████║\n"
        "██╔═══╝ ██╔══██║██║╚██╗██║██║   ██║██║ ██╔══██║\n"
        "██║     ██║  ██║██║ ╚████║╚██████╔╝██║ ██║  ██║\n"
        "╚═╝     ╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝ ╚═╝  ╚═╝"
        f"  v{settings.app_version} — Geo-AI Platform (V2)\n",
        flush=True,
    )
    yield
    await close_engine()
    await close_redis()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_title,
        version=settings.app_version,
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(chat_router)
    application.include_router(suggestions_router)
    return application


app = create_app()
