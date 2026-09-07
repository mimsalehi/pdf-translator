"""Web and API routes for AI translation execution and review."""
from pydantic import BaseModel
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from pdf_translator.adapters.storage.db import get_session
from pdf_translator.adapters.storage.sqlite_repo import (
    SQLiteProjectRepository,
    SQLitePageRepository,
    SQLiteProfileRepository,
)
from pdf_translator.application.translation_service import TranslationService
from pdf_translator.domain.errors import (
    PageNotFoundError,
    ProjectNotFoundError,
    TranslationProviderError,
    InvalidStateTransitionError,
)

router = APIRouter()

def get_translation_service(session: Session = Depends(get_session)) -> TranslationService:
    page_repo = SQLitePageRepository(session)
    project_repo = SQLiteProjectRepository(session)
    profile_repo = SQLiteProfileRepository(session)
    return TranslationService(
        page_repo=page_repo,
        project_repo=project_repo,
        profile_repo=profile_repo,
    )

class TranslateRequest(BaseModel):
    custom_instructions: Optional[str] = None

class TranslationDraftRequest(BaseModel):
    draft_text: str

class ApproveFinalRequest(BaseModel):
    final_text: str

@router.post("/api/projects/{project_id}/pages/{page_number}/translate")
async def trigger_translate_api(
    project_id: str,
    page_number: int,
    payload: Optional[TranslateRequest] = None,
    service: TranslationService = Depends(get_translation_service),
):
    try:
        custom_notes = payload.custom_instructions if payload else None
        attempt = await service.translate_page(project_id, page_number, custom_notes)
        return {
            "success": True,
            "translated_text": attempt.edited_text,
            "version_number": attempt.version_number,
            "provider_name": attempt.provider_name,
            "model_name": attempt.model_name,
            "status": "IN_REVIEW",
        }
    except (PageNotFoundError, ProjectNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TranslationProviderError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")

@router.put("/api/projects/{project_id}/pages/{page_number}/translation-draft")
async def save_translation_draft_api(
    project_id: str,
    page_number: int,
    payload: TranslationDraftRequest,
    service: TranslationService = Depends(get_translation_service),
):
    try:
        page = service.save_draft_edit(project_id, page_number, payload.draft_text)
        return {"success": True, "draft_text": page.latest_translation}
    except (PageNotFoundError, ProjectNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/api/projects/{project_id}/pages/{page_number}/approve-final")
async def approve_final_translation_api(
    project_id: str,
    page_number: int,
    payload: ApproveFinalRequest,
    service: TranslationService = Depends(get_translation_service),
):
    try:
        page = service.approve_final_translation(project_id, page_number, payload.final_text)
        return {"success": True, "status": page.status, "approved_text": page.approved_text}
    except (PageNotFoundError, ProjectNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
