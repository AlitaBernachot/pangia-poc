# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

from fastapi import APIRouter

from app.api.routes.agents import router as agents_router
from app.api.routes.suggestions import router as suggestions_router

router = APIRouter(prefix="/api", tags=["seeder"])

router.include_router(suggestions_router)
router.include_router(agents_router)
