from fastapi import APIRouter

from app.db.themes import get_active_theme

router = APIRouter()


@router.get("/suggestions")
async def suggestions() -> dict:
    theme = get_active_theme()
    return {"suggestions": theme.suggestions}
