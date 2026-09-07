"""API routes for In-Reading AI Assistant and Prompt Template management."""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from sqlmodel import Session

from pdf_translator.adapters.storage.db import get_session
from pdf_translator.adapters.storage.sqlite_repo import (
    SQLitePromptTemplateRepository,
    SQLitePageConversationRepository,
    SQLitePageRepository,
    SQLiteProjectRepository,
    SQLiteProfileRepository,
)
from pdf_translator.application.qa_service import QAService
from pdf_translator.application.dtos import (
    PromptTemplateDTO,
    PromptTemplateCreateDTO,
    PromptTemplateUpdateDTO,
    PageConversationDTO,
    PageAskDTO,
)
from pdf_translator.domain.errors import ProjectNotFoundError, PageNotFoundError, TranslationProviderError

router = APIRouter(tags=["in-reading-qa"])

def get_qa_service(session: Session = Depends(get_session)) -> QAService:
    return QAService(
        prompt_template_repo=SQLitePromptTemplateRepository(session),
        page_conversation_repo=SQLitePageConversationRepository(session),
        page_repo=SQLitePageRepository(session),
        project_repo=SQLiteProjectRepository(session),
        profile_repo=SQLiteProfileRepository(session),
    )


# --- Prompt Templates Management Endpoints ---

@router.get("/api/prompt-templates", response_model=List[PromptTemplateDTO])
def list_prompt_templates(service: QAService = Depends(get_qa_service)):
    return service.list_prompt_templates()


@router.post("/api/prompt-templates", response_model=PromptTemplateDTO, status_code=status.HTTP_201_CREATED)
def create_prompt_template(dto: PromptTemplateCreateDTO, service: QAService = Depends(get_qa_service)):
    return service.create_prompt_template(dto)


@router.put("/api/prompt-templates/{template_id}", response_model=PromptTemplateDTO)
def update_prompt_template(template_id: str, dto: PromptTemplateUpdateDTO, service: QAService = Depends(get_qa_service)):
    try:
        return service.update_prompt_template(template_id, dto)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/api/prompt-templates/{template_id}", status_code=status.HTTP_200_OK)
def delete_prompt_template(template_id: str, service: QAService = Depends(get_qa_service)):
    success = service.delete_prompt_template(template_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt template not found.")
    return {"success": True, "message": "Prompt template deleted."}


# --- Page Q&A Assistant Endpoints ---

@router.get("/api/projects/{project_id}/pages/{page_number}/conversations", response_model=List[PageConversationDTO])
def get_page_conversations(project_id: str, page_number: int, service: QAService = Depends(get_qa_service)):
    return service.list_page_conversations(project_id, page_number)


@router.post("/api/projects/{project_id}/pages/{page_number}/ask", response_model=PageConversationDTO)
async def ask_page_question(
    project_id: str,
    page_number: int,
    dto: PageAskDTO,
    service: QAService = Depends(get_qa_service),
):
    try:
        return await service.ask_page_question(project_id, page_number, dto)
    except (ProjectNotFoundError, PageNotFoundError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except TranslationProviderError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"QA failed: {str(e)}")


@router.delete("/api/conversations/{conversation_id}", status_code=status.HTTP_200_OK)
def delete_conversation(conversation_id: str, service: QAService = Depends(get_qa_service)):
    success = service.delete_page_conversation(conversation_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return {"success": True, "message": "Conversation deleted."}
