from fastapi import FastAPI
from app.api.router import api_router
from app.core.config import settings

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
    )
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    return app

app = create_app()