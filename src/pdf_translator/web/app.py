"""Main FastAPI Application Entrypoint."""
import sys
import asyncio
from pathlib import Path

if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pdf_translator.config import settings
from pdf_translator.adapters.storage.db import init_db
from pdf_translator.web.routes.project_routes import router as project_router
from pdf_translator.web.routes.page_routes import router as page_router
from pdf_translator.web.routes.translation_routes import router as translation_router
from pdf_translator.web.routes.export_routes import router as export_router
from pdf_translator.web.routes.settings_routes import router as settings_router
from pdf_translator.web.routes.qa_routes import router as qa_router
from pdf_translator.web.routes.chapter_routes import router as chapter_router
def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Local-first Human-in-the-Loop PDF Book Translator",
    )

    # Initialize Database
    init_db()

    # Mount static files
    static_dir = Path(__file__).resolve().parent / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Include Routers
    app.include_router(project_router)
    app.include_router(page_router)
    app.include_router(translation_router)
    app.include_router(export_router)
    app.include_router(settings_router)
    app.include_router(qa_router)
    app.include_router(chapter_router)
    return app

app = create_app()
