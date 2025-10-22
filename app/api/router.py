from fastapi import APIRouter

from app.api.endpoints import calls, webhooks

router = APIRouter()

router.include_router(calls.router, prefix="/calls", tags=["calls"])
router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
