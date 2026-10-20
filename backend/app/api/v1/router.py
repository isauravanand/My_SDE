from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    dashboard,
    health,
    integrations_github,
    projects,
    readiness,
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
