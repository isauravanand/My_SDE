from fastapi import FastAPI

from app.api.routes.health import router as health_router

app = FastAPI(title="My SDE API")
app.include_router(health_router)


def main() -> None:
    import uvicorn

    uvicorn.run("app.main:app", reload=True)
