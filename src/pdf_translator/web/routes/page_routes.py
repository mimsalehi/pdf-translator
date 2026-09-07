"""Web and API routes for Page inspection and HITL workflow."""
from pathlib import Path
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from pdf_translator.adapters.storage.db import get_session
from pdf_translator.adapters.storage.sqlite_repo import SQLiteProjectRepository, SQLitePageRepository
from pdf_translator.adapters.pdf.pymupdf_extractor import PyMuPDFExtractor
from pdf_translator.application.page_service import PageService
from pdf_translator.domain.errors import PageNotFoundError, ProjectNotFoundError, InvalidStateTransitionError

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

def get_page_service(session: Session = Depends(get_session)) -> PageService:
    project_repo = SQLiteProjectRepository(session)
    page_repo = SQLitePageRepository(session)
    pdf_extractor = PyMuPDFExtractor()
    return PageService(page_repo=page_repo, project_repo=project_repo, pdf_extractor=pdf_extractor)

class UpdateSourceTextRequest(BaseModel):
    source_text: str

@router.get("/projects/{project_id}/pages/{page_number}", response_class=HTMLResponse)
async def page_workspace_view(
    project_id: str,
    page_number: int,
    request: Request,
    service: PageService = Depends(get_page_service)
):
    try:
        page_dto = service.get_page_detail(project_id, page_number)
    except (ProjectNotFoundError, PageNotFoundError):
        raise HTTPException(status_code=404, detail="Page or project not found")

    return templates.TemplateResponse(
        request=request,
        name="page_workspace.html",
        context={"page": page_dto, "title": f"Page {page_number} - {page_dto.project_title}"}
    )

@router.get("/api/projects/{project_id}/pages/{page_number}")
async def get_page_api(
    project_id: str,
    page_number: int,
    service: PageService = Depends(get_page_service)
):
    try:
        return service.get_page_detail(project_id, page_number)
    except (ProjectNotFoundError, PageNotFoundError):
        raise HTTPException(status_code=404, detail="Page or project not found")

@router.put("/api/projects/{project_id}/pages/{page_number}/source-text")
async def update_page_source_text(
    project_id: str,
    page_number: int,
    payload: UpdateSourceTextRequest,
    service: PageService = Depends(get_page_service)
):
    try:
        updated = service.update_source_text(project_id, page_number, payload.source_text)
        return {"success": True, "source_text": updated.source_text, "status": updated.status}
    except PageNotFoundError:
        raise HTTPException(status_code=404, detail="Page not found")

@router.post("/api/projects/{project_id}/pages/{page_number}/re-extract")
async def re_extract_page_text(
    project_id: str,
    page_number: int,
    session: Session = Depends(get_session),
    service: PageService = Depends(get_page_service)
):
    project_repo = SQLiteProjectRepository(session)
    project = project_repo.get_by_id(project_id)
    if not project or not Path(project.source_pdf_path).exists():
        raise HTTPException(status_code=404, detail="Project or source PDF not found")
    
    clean_text = service._extract_page_with_stitching(project, page_number)
    updated = service.update_source_text(project_id, page_number, clean_text)
    return {"success": True, "source_text": updated.source_text}

@router.post("/api/projects/{project_id}/pages/{page_number}/approve-for-translation")
async def approve_for_translation_api(
    project_id: str,
    page_number: int,
    service: PageService = Depends(get_page_service)
):
    try:
        updated = service.approve_for_translation(project_id, page_number)
        return {"success": True, "status": updated.status}
    except PageNotFoundError:
        raise HTTPException(status_code=404, detail="Page not found")
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
