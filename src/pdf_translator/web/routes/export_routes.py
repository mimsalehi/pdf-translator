"""Web and API routes for Export and Book Assembly."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlmodel import Session

from pdf_translator.adapters.storage.db import get_session
from pdf_translator.adapters.storage.sqlite_repo import SQLiteProjectRepository, SQLitePageRepository
from pdf_translator.adapters.storage.file_storage import FileStorageManager
from pdf_translator.application.export_service import ExportService
from pdf_translator.domain.errors import ProjectNotFoundError, PageNotFoundError, ExportError

router = APIRouter()

def get_export_service(session: Session = Depends(get_session)) -> ExportService:
    project_repo = SQLiteProjectRepository(session)
    page_repo = SQLitePageRepository(session)
    file_storage = FileStorageManager()
    return ExportService(
        project_repo=project_repo,
        page_repo=page_repo,
        file_storage=file_storage,
    )

@router.get("/api/projects/{project_id}/pages/{page_number}/export")
async def export_page_api(
    project_id: str,
    page_number: int,
    format: str = Query("md", pattern="^(md|docx)$"),
    service: ExportService = Depends(get_export_service),
):
    try:
        file_path = service.export_page(project_id, page_number, fmt=format)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if format == "docx" else "text/markdown"
        return FileResponse(file_path, filename=file_path.name, media_type=media_type)
    except (PageNotFoundError, ProjectNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ExportError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/api/projects/{project_id}/export")
async def assemble_and_export_book_api(
    project_id: str,
    format: str = Query("md", pattern="^(md|docx)$"),
    service: ExportService = Depends(get_export_service),
):
    try:
        file_path = service.assemble_and_export_book(project_id, fmt=format)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if format == "docx" else "text/markdown"
        return FileResponse(file_path, filename=file_path.name, media_type=media_type)
    except ProjectNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ExportError as e:
        raise HTTPException(status_code=400, detail=str(e))
