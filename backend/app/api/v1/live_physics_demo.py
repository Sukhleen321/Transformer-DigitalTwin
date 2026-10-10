"""Read-only, explicitly isolated versioned demonstration resource."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.config import Settings, get_settings
from app.db.session import DatabaseSession
from app.schemas.live_physics_demo import LivePhysicsDemoResult
from app.services.live_physics_demo import read
from app.services.query_service import query_error

router = APIRouter(tags=["live-physics-demo"])


@router.get(
    "/demo/transformers/{transformer_id}/physics",
    response_model=LivePhysicsDemoResult,
    description="Opt-in fictional live simulation. Never operational transformer physics.",
)
def get_live_demo(
    request: Request,
    transformer_id: str,
    db: DatabaseSession,
    settings: Annotated[Settings, Depends(get_settings)],
):
    if request.query_params:
        query_error("query", "Demo endpoint accepts no query parameters")
    return read(db, transformer_id, settings=settings)
