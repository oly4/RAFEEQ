from pathlib import Path

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from rafeeq_backend.api.errors import (
    http_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from rafeeq_backend.api.middleware import request_id_middleware
from rafeeq_backend.api.router import api_router
from rafeeq_backend.config import get_settings
from rafeeq_backend.database import engine
from rafeeq_backend.modules.emergencies.api.device_router import router as device_api_router
from rafeeq_backend.modules.synchronization.api.router import router as sync_api_router
from rafeeq_backend.modules.notifications.api.websocket import router as websocket_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="RAFEEQ Backend", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_allowed_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(request_id_middleware)
    app.add_exception_handler(HTTPException, http_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
    app.include_router(api_router)
    app.include_router(device_api_router)
    app.include_router(sync_api_router)
    app.include_router(websocket_router)

    media_root = Path(__file__).resolve().parents[4] / "data" / "uploads"
    media_root.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=media_root), name="media")

    @app.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    async def ready() -> dict[str, str]:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ready", "environment": settings.app_env}

    return app


app = create_app()
