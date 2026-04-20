# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

from fastapi import APIRouter

from app.pangiagent.source_registry import get_suggestions

router = APIRouter()


@router.get("/api/suggestions")
async def suggestions() -> dict:
    """Return the list of example queries shown in the frontend suggestion chips."""
    return {"suggestions": get_suggestions()}
