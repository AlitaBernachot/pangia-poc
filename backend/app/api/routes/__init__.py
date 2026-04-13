from fastapi import APIRouter

from app.api.routes.agents import router as agents_router
from app.api.routes.chat import router as chat_router
from app.api.routes.suggestions import router as suggestions_router

router = APIRouter(prefix="/api", tags=["chat"])

router.include_router(chat_router)
router.include_router(suggestions_router)
router.include_router(agents_router)
