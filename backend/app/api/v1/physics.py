"""Separate read-only physics resource; public-read conventions are preserved."""

from typing import Annotated

from fastapi import APIRouter, Path, Query, Request

from app.db.session import DatabaseSession
from app.schemas.common import ErrorResponse, UtcDatetime
from app.schemas.physics import PhysicsResult
from app.services import physics_service
from app.services.query_service import query_error

router = APIRouter(tags=["physics"])


@router.get(
    "/transformers/{transformer_id}/physics",
    response_model=PhysicsResult,
    responses={status: {"model": ErrorResponse} for status in (404, 409, 422, 500)},
    description=(
        "Bounded event-time physics results. Thermal values are controlled "
        "synthetic node proxies; unsupported outputs remain null."
    ),
)
def get_physics(
    request: Request,
    db: DatabaseSession,
    transformer_id: Annotated[str, Path(min_length=1, max_length=128)],
    at: Annotated[
        UtcDatetime | None,
        Query(
            description=(
                "Aware UTC event cutoff; default server evaluation time. "
                "Search is limited to the preceding 31 days."
            )
        ),
    ] = None,
):
    for field in request.query_params:
        if field != "at" or len(request.query_params.getlist(field)) != 1:
            query_error(field, "Unknown or repeated physics query parameter")
    return physics_service.read(db, transformer_id, at)
