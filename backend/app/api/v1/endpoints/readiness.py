from datetime import datetime, timezone

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.db.session import check_database_connectivity
from app.schemas.health import DatabaseComponentStatus, ReadinessResponse

router = APIRouter()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={
        200: {"description": "Service and database dependencies are operational", "model": ReadinessResponse},
        503: {"description": "Service or database dependency is unavailable", "model": ReadinessResponse},
    },
    summary="Service Readiness Probe",
    description="Validates database connectivity. Returns 503 if the database is unreachable.",
    tags=["Health"],
)
async def get_readiness():
    is_healthy, latency_ms, error = check_database_connectivity()
    now = datetime.now(timezone.utc)

    if not is_healthy:
        response_body = ReadinessResponse(
            status="unhealthy",
            database=DatabaseComponentStatus(
                status="disconnected",
                latency_ms=latency_ms,
                error="Database connectivity probe failed. Check service logs for details.",
            ),
            timestamp=now,
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response_body.model_dump(mode="json"),
        )

    return ReadinessResponse(
        status="ready",
        database=DatabaseComponentStatus(
            status="connected",
            latency_ms=latency_ms,
            error=None,
        ),
        timestamp=now,
    )
