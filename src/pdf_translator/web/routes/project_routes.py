"""Web and API routes for Projects."""
import tempfile
import shutil
from pathlib import Path
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Request, UploadFile, File, Form, HTTPException, status
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from pdf_translator.adapters.storage.db import get_session
from pdf_translator.adapters.storage.sqlite_repo import SQLiteProjectRepository, SQLitePageRepository
from pdf_translator.adapters.storage.file_storage import FileStorageManager
from pdf_translator.adapters.pdf.pymupdf_extractor import PyMuPDFExtractor
from pdf_translator.adapters.article.http_article_fetcher import HttpArticleFetcher
from pdf_translator.adapters.providers.browser_manager import BrowserManager
from pdf_translator.application.project_service import ProjectService
from pdf_translator.application.dtos import ProjectCreateDTO, ArticleProjectCreateDTO
from pdf_translator.domain.enums import SourceType
from pdf_translator.domain.errors import ProjectNotFoundError, ArticleFetchError
from pdf_translator.domain.ports import ArticleFetcherPort

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

def get_article_fetcher() -> ArticleFetcherPort:
    """Plain HTTP first; the operator's Chrome (shared with browser providers) handles bot-protected or JS-rendered sites."""
    return HttpArticleFetcher(page_renderer=BrowserManager.get_instance())

def get_project_service(
    session: Session = Depends(get_session),
    article_fetcher: ArticleFetcherPort = Depends(get_article_fetcher),
) -> ProjectService:
    project_repo = SQLiteProjectRepository(session)
    page_repo = SQLitePageRepository(session)
    pdf_extractor = PyMuPDFExtractor()
    file_storage = FileStorageManager()
    return ProjectService(
        project_repo=project_repo,
        page_repo=page_repo,
        pdf_extractor=pdf_extractor,
        file_storage=file_storage,
        article_fetcher=article_fetcher,
    )

class CreateArticleProjectRequest(BaseModel):
    url: str
    title: str = ""
    source_language: str = "English"
    target_language: str = "Persian"

@router.get("/", response_class=HTMLResponse)
async def project_list_page(
    request: Request,
    service: ProjectService = Depends(get_project_service)
):
    projects = service.list_projects()
    return templates.TemplateResponse(
        request=request,
        name="project_list.html",
        context={"projects": projects, "title": "Projects"}
    )

@router.post("/api/projects", status_code=status.HTTP_201_CREATED)
async def create_project_api(
    title: str = Form(""),
    source_language: str = Form("English"),
    target_language: str = Form("Persian"),
    file: UploadFile = File(...),
    service: ProjectService = Depends(get_project_service)
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    # Save uploaded file to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        dto = ProjectCreateDTO(
            title=title.strip() or Path(file.filename).stem,
            source_pdf_path=str(tmp_path),
            original_filename=file.filename,
            source_language=source_language,
            target_language=target_language,
        )
        project = service.create_project(dto)
        return {"success": True, "project_id": project.id, "total_pages": project.total_pages}
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

@router.post("/api/projects/article", status_code=status.HTTP_201_CREATED)
async def create_article_project_api(
    payload: CreateArticleProjectRequest,
    service: ProjectService = Depends(get_project_service)
):
    dto = ArticleProjectCreateDTO(
        url=payload.url,
        title=payload.title,
        source_language=payload.source_language,
        target_language=payload.target_language,
    )
    try:
        project = await service.create_article_project(dto)
    except ArticleFetchError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"success": True, "project_id": project.id, "total_pages": project.total_pages}

@router.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_detail_page(
    project_id: str,
    request: Request,
    service: ProjectService = Depends(get_project_service)
):
    try:
        project = service.get_project_detail(project_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")

    return templates.TemplateResponse(
        request=request,
        name="project_detail.html",
        context={"project": project, "title": project.title}
    )

@router.get("/projects/{project_id}/reader", response_class=HTMLResponse)
async def project_reader_view(
    request: Request,
    project_id: str,
    session: Session = Depends(get_session),
    service: ProjectService = Depends(get_project_service)
):
    project_repo = SQLiteProjectRepository(session)
    page_repo = SQLitePageRepository(session)
    project = project_repo.get_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    pages = page_repo.list_by_project(project_id)
    return templates.TemplateResponse(
        request=request,
        name="book_reader.html",
        context={
            "title": f"Reading: {project.title}",
            "project": project,
            "pages": pages,
        }
    )

@router.get("/api/projects/{project_id}/pages/{page_num}/thumbnail")
async def get_page_thumbnail(
    project_id: str,
    page_num: int,
    session: Session = Depends(get_session)
):
    file_storage = FileStorageManager()
    project_repo = SQLiteProjectRepository(session)
    project = project_repo.get_by_id(project_id)
    if project and project.source_type == SourceType.ARTICLE:
        # An article has no rendered page; its lead image serves as the cover.
        lead_image = Path(project.storage_dir) / "images" / f"page_{page_num}_img_1.png"
        if not lead_image.exists():
            raise HTTPException(status_code=404, detail="Article has no images")
        return FileResponse(lead_image, media_type="image/png")

    thumb_path = file_storage.get_page_thumbnail_path(project_id, page_num)
    if not thumb_path.exists():
        if not project or not project.source_pdf_path or not Path(project.source_pdf_path).exists():
            raise HTTPException(status_code=404, detail="Thumbnail not found")
        pdf_extractor = PyMuPDFExtractor()
        pdf_extractor.render_thumbnail(Path(project.source_pdf_path), page_num, thumb_path, max_width=300)
    return FileResponse(thumb_path, media_type="image/png")

@router.get("/api/projects/{project_id}/pages/{page_num}/image")
async def get_page_image(
    project_id: str,
    page_num: int,
    session: Session = Depends(get_session)
):
    file_storage = FileStorageManager()
    img_path = file_storage.get_page_image_path(project_id, page_num)
    if not img_path.exists():
        project_repo = SQLiteProjectRepository(session)
        project = project_repo.get_by_id(project_id)
        if not project or not project.source_pdf_path or not Path(project.source_pdf_path).exists():
            raise HTTPException(status_code=404, detail="Image not found")
        pdf_extractor = PyMuPDFExtractor()
        pdf_extractor.render_page_image(Path(project.source_pdf_path), page_num, img_path, dpi=150)

    return FileResponse(img_path, media_type="image/png")

@router.get("/api/projects/{project_id}/pages/{page_num}/images/{image_idx}")
async def get_page_embedded_diagram(
    project_id: str,
    page_num: int,
    image_idx: int,
    session: Session = Depends(get_session)
):
    project_repo = SQLiteProjectRepository(session)
    project = project_repo.get_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    images_dir = Path(project.storage_dir) / "images"
    image_path = images_dir / f"page_{page_num}_img_{image_idx}.png"

    if not image_path.exists() and project.source_type == SourceType.PDF:
        pdf_path = Path(project.source_pdf_path)
        if project.source_pdf_path and pdf_path.exists():
            extractor = PyMuPDFExtractor()
            extractor.extract_page_content(
                pdf_path,
                page_num,
                project_id=project.id,
                images_dir=images_dir
            )

    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Embedded diagram not found")

    return FileResponse(image_path, media_type="image/png")

@router.delete("/api/projects/{project_id}")
async def delete_project_api(
    project_id: str,
    service: ProjectService = Depends(get_project_service)
):
    try:
        service.delete_project(project_id)
        return {"success": True}
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")
