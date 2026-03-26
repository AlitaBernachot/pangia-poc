import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from openinference.instrumentation.langchain import LangChainInstrumentor
from phoenix.otel import register

from app.api.routes import router
from app.config import get_settings
from app.db.chroma_client import close_client as close_chroma
from app.db.neo4j_client import close_driver
from app.db.postgis_client import close_pool
from app.db.redis_client import close_redis
from app.db.seed import seed_all

logger = logging.getLogger(__name__)


def _setup_phoenix(settings) -> None:
    """Initialise Arize Phoenix tracing for LangChain/LangGraph agents."""
    tracer_provider = register(
        project_name=settings.phoenix_project_name,
        endpoint=settings.phoenix_collector_endpoint,
    )
    LangChainInstrumentor().instrument(tracer_provider=tracer_provider)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup – initialise Arize Phoenix observability
    settings = get_settings()
    _setup_phoenix(settings)
    if settings.seed_db:
        logger.info("SEED_DB=true – running database seeds …")
        try:
            await seed_all()
        except Exception:
            logger.exception("Database seeding failed – continuing startup anyway.")
    yield
    # shutdown – close all data-store connections
    await close_driver()
    await close_redis()
    await close_pool()
    await close_chroma()


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

    application.include_router(router)

    return application


app = create_app()
