"""Web and API routes for Chapter Summarization and Deep Note-Taking."""
import asyncio
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from fastapi.responses import FileResponse
from sqlmodel import Session
from pdf_translator.adapters.storage.db import get_session, get_engine
from pdf_translator.adapters.storage.sqlite_repo import (
    SQLiteProjectRepository,
    SQLitePageRepository,
    SQLiteProfileRepository,
    SQLiteChapterSummaryRepository,
    SQLiteChapterPromptTemplateRepository,
)
from pdf_translator.application.dtos import (
    ChapterSummaryDTO,
    ChapterSummaryCreateDTO,
    ChapterSummaryUpdateDTO,
    ChapterPromptTemplateDTO,
    ChapterPromptTemplateCreateDTO,
    ChapterPromptTemplateUpdateDTO,
    DetectedChapterDTO,
)
from pdf_translator.domain.errors import ProjectNotFoundError
from pdf_translator.application.chapter_service import ChapterService
from pdf_translator.adapters.pdf.pymupdf_extractor import PyMuPDFExtractor
router = APIRouter(tags=["chapter-summaries"])


def get_chapter_service(session: Session = Depends(get_session)) -> ChapterService:
    return ChapterService(
        chapter_summary_repo=SQLiteChapterSummaryRepository(session),
        chapter_prompt_template_repo=SQLiteChapterPromptTemplateRepository(session),
        project_repo=SQLiteProjectRepository(session),
        page_repo=SQLitePageRepository(session),
        profile_repo=SQLiteProfileRepository(session),
        pdf_extractor=PyMuPDFExtractor(),
    )
async def _run_chapter_summary_background(chapter_id: str, resume: bool = True):
    """Runs long-running map-reduce in a dedicated, unclosed background database session."""
    with Session(get_engine()) as session:
        service = ChapterService(
            chapter_summary_repo=SQLiteChapterSummaryRepository(session),
            chapter_prompt_template_repo=SQLiteChapterPromptTemplateRepository(session),
            project_repo=SQLiteProjectRepository(session),
            page_repo=SQLitePageRepository(session),
            profile_repo=SQLiteProfileRepository(session),
        )
        await service.process_chapter_summary(chapter_id, resume)
# --- Chapter Summaries Endpoints ---

@router.get("/api/projects/{project_id}/chapters", response_model=List[ChapterSummaryDTO])
def list_project_chapters(
    project_id: str,
    service: ChapterService = Depends(get_chapter_service),
):
    """Lists all chapter summaries for a specific project."""
    return service.list_chapter_summaries(project_id)


@router.get("/api/projects/{project_id}/detected-chapters", response_model=List[DetectedChapterDTO])
def get_project_detected_chapters(
    project_id: str,
    service: ChapterService = Depends(get_chapter_service),
):
    """Extracts and returns the book's chapter structure and page boundaries from PDF Table of Contents."""
    try:
        return service.detect_book_chapters(project_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="پروژه یافت نشد.")


@router.post("/api/projects/{project_id}/chapters", response_model=ChapterSummaryDTO, status_code=status.HTTP_201_CREATED)
async def create_chapter_summary(
    project_id: str,
    dto: ChapterSummaryCreateDTO,
    background_tasks: BackgroundTasks,
    service: ChapterService = Depends(get_chapter_service),
):
    """Creates a chapter summary record and kicks off background map-reduce processing."""
    try:
        summary = service.create_chapter_summary(project_id, dto)
        # Launch background map-reduce extraction task with dedicated session
        background_tasks.add_task(_run_chapter_summary_background, summary.id, False)
        return summary
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="پروژه یافت نشد.")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"خطا در ایجاد نوت فصل: {str(e)}")


@router.get("/api/chapters/{chapter_id}", response_model=ChapterSummaryDTO)
def get_chapter_summary(
    chapter_id: str,
    service: ChapterService = Depends(get_chapter_service),
):
    """Retrieves single chapter summary with live progress info."""
    summary = service.get_chapter_summary(chapter_id)
    if not summary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="نوت فصل یافت نشد.")
    return summary


@router.put("/api/chapters/{chapter_id}", response_model=ChapterSummaryDTO)
def update_chapter_summary(
    chapter_id: str,
    dto: ChapterSummaryUpdateDTO,
    service: ChapterService = Depends(get_chapter_service),
):
    """Allows manual editing of title or markdown note."""
    try:
        return service.update_chapter_summary(chapter_id, dto)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/api/chapters/{chapter_id}", status_code=status.HTTP_200_OK)
def delete_chapter_summary(
    chapter_id: str,
    service: ChapterService = Depends(get_chapter_service),
):
    """Deletes a chapter summary."""
    success = service.delete_chapter_summary(chapter_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="نوت فصل یافت نشد.")
    return {"success": True, "message": "نوت فصل حذف شد."}


@router.post("/api/chapters/{chapter_id}/resume", response_model=ChapterSummaryDTO)
async def resume_chapter_summary(
    chapter_id: str,
    background_tasks: BackgroundTasks,
    service: ChapterService = Depends(get_chapter_service),
):
    """Resumes map-reduce processing from the first incomplete section without re-running finished chunks."""
    summary = service.get_chapter_summary(chapter_id)
    if not summary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="نوت فصل یافت نشد.")

    background_tasks.add_task(_run_chapter_summary_background, chapter_id, True)
    return summary


@router.post("/api/chapters/{chapter_id}/regenerate", response_model=ChapterSummaryDTO)
async def regenerate_chapter_summary(
    chapter_id: str,
    background_tasks: BackgroundTasks,
    service: ChapterService = Depends(get_chapter_service),
):
    """Re-triggers AI map-reduce generation from scratch (resetting previous section cache)."""
    summary = service.get_chapter_summary(chapter_id)
    if not summary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="نوت فصل یافت نشد.")

    service.reset_chapter_summary(chapter_id)
    background_tasks.add_task(_run_chapter_summary_background, chapter_id, False)
    return summary


@router.get("/api/chapters/{chapter_id}/export")
def export_chapter_summary(
    chapter_id: str,
    format: str = Query("md", pattern="^(md|docx)$"),
    service: ChapterService = Depends(get_chapter_service),
):
    """Exports chapter note as Markdown (.md) or Microsoft Word (.docx)."""
    try:
        file_path, media_type = service.export_chapter_summary(chapter_id, format)
        return FileResponse(
            path=file_path,
            media_type=media_type,
            filename=file_path.name,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"خطا در ایجاد خروجی: {str(e)}")


# --- Chapter Prompt Templates Endpoints ---

@router.get("/api/chapter-templates", response_model=List[ChapterPromptTemplateDTO])
def list_chapter_prompt_templates(service: ChapterService = Depends(get_chapter_service)):
    return service.list_chapter_prompt_templates()


@router.post("/api/chapter-templates", response_model=ChapterPromptTemplateDTO, status_code=status.HTTP_201_CREATED)
def create_chapter_prompt_template(
    dto: ChapterPromptTemplateCreateDTO,
    service: ChapterService = Depends(get_chapter_service),
):
    return service.create_chapter_prompt_template(dto)


@router.put("/api/chapter-templates/{template_id}", response_model=ChapterPromptTemplateDTO)
def update_chapter_prompt_template(
    template_id: str,
    dto: ChapterPromptTemplateUpdateDTO,
    service: ChapterService = Depends(get_chapter_service),
):
    try:
        return service.update_chapter_prompt_template(template_id, dto)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/api/chapter-templates/{template_id}", status_code=status.HTTP_200_OK)
def delete_chapter_prompt_template(
    template_id: str,
    service: ChapterService = Depends(get_chapter_service),
):
    success = service.delete_chapter_prompt_template(template_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="قالب پرامپت یافت نشد.")
    return {"success": True, "message": "قالب حذف شد."}
