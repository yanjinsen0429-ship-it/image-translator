from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import ensure_runtime_directories, settings


def create_app() -> FastAPI:
    ensure_runtime_directories()

    app = FastAPI(title="Local Image Translation Mock MVP")
    app.include_router(router, prefix="/api")
    app.mount("/static", StaticFiles(directory=settings.frontend_static_dir), name="static")
    app.mount("/storage", StaticFiles(directory=settings.storage_dir), name="storage")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(settings.frontend_dir / "index.html")

    return app


app = create_app()
