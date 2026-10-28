from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    billing,
    code_rag,
    dashboard,
    execution,
    health,
    integrations_github,
    observability,
    planning,
    projects,
    publishing,
    readiness,
    repair,
    tasks,
    workspaces,
)

api_router = APIRouter()

api_router.include_router(health.router, tags=["Health"])
api_router.include_router(readiness.router, tags=["Readiness"])
api_router.include_router(auth.router)
api_router.include_router(workspaces.router)
api_router.include_router(projects.router)
api_router.include_router(tasks.router)
api_router.include_router(dashboard.router)
api_router.include_router(integrations_github.router)
api_router.include_router(code_rag.router)
api_router.include_router(planning.router)
api_router.include_router(execution.router)
api_router.include_router(repair.router)
api_router.include_router(publishing.router)
api_router.include_router(observability.router)
api_router.include_router(billing.router)

