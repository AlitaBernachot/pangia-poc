from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import get_settings
from app.db.chroma_client import close_client as close_chroma
from app.db.neo4j_client import close_driver
from app.db.postgis_client import close_pool
from app.db.redis_client import close_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
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
