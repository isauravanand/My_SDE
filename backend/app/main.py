import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.endpoints import health as health_endpoint
from app.api.v1.endpoints import readiness as readiness_endpoint
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.security import SECURITY_HEADERS
from app.db.session import dispose_engine

settings = get_settings()
setup_logging(log_level=settings.LOG_LEVEL, is_json=(settings.APP_ENV == "production"))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for graceful startup and shutdown."""
    logger.info(
        "Starting %s [env=%s, debug=%s]",
        settings.APP_NAME,
        settings.APP_ENV,
        settings.DEBUG,
    )
    yield
    logger.info("Shutting down %s...", settings.APP_NAME)
    dispose_engine()


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="MySDE AI Software Engineering SaaS Platform Backend API",
    debug=settings.DEBUG,
    lifespan=lifespan,
    docs_url="/docs" if settings.APP_ENV != "production" else None,
    redoc_url="/redoc" if settings.APP_ENV != "production" else None,
)

# ------------------------------------------------------------------------------
# Security Headers Middleware
# ------------------------------------------------------------------------------
@app.middleware("http")
async def add_security_headers_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    for header_name, header_value in SECURITY_HEADERS.items():
        response.headers[header_name] = header_value
    response.headers["X-Request-ID"] = request_id
    return response


# ------------------------------------------------------------------------------
# CORS Middleware
# ------------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------------------
# Exception Handlers
# ------------------------------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", None)
    details = [
        {"field": ".".join(str(loc) for loc in err.get("loc", [])), "issue": err.get("msg", "Invalid value")}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request payload validation failed.",
                "details": details,
                "request_id": request_id,
            }
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", None)
    message = exc.detail if isinstance(exc.detail, str) else "An HTTP error occurred."
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": "HTTP_ERROR",
                "message": message,
                "details": [],
                "request_id": request_id,
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    logger.exception("Unhandled server exception [request_id=%s]: %s", request_id, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred. Please try again later.",
                "details": [],
                "request_id": request_id,
            }
        },
    )


# ------------------------------------------------------------------------------
# Probes & Routes
# ------------------------------------------------------------------------------
# Root-level probes for orchestrators (e.g. Kubernetes, AWS ECS)
app.include_router(health_endpoint.router, tags=["Health"])
app.include_router(readiness_endpoint.router, tags=["Readiness"])

# Versioned API Router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


def main():
    """CLI entrypoint for local execution via uv run backend."""
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
