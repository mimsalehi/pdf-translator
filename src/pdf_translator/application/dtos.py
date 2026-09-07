"""Data Transfer Objects (DTOs) for application use-cases."""
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from pdf_translator.domain.enums import PageStatus, ProviderType

class ProjectCreateDTO(BaseModel):
    title: str
    source_pdf_path: str
    original_filename: str
    source_language: str = "English"
    target_language: str = "Persian"
    profile_id: Optional[str] = None

class PageSummaryDTO(BaseModel):
    id: str
    page_number: int
    status: PageStatus
    has_text: bool
    thumbnail_url: str
    image_url: str
    latest_translation_preview: Optional[str] = None

class ProjectDetailDTO(BaseModel):
    id: str
    title: str
    source_pdf_filename: str
    total_pages: int
    source_language: str
    target_language: str
    created_at: datetime
    pages: List[PageSummaryDTO]
    
    # Progress stats
    ready_count: int = 0
    approved_for_translation_count: int = 0
    translating_count: int = 0
    translated_count: int = 0
    in_review_count: int = 0
    approved_count: int = 0
    exported_count: int = 0
    failed_count: int = 0

class ProjectListItemDTO(BaseModel):
    id: str
    title: str
    source_pdf_filename: str
    total_pages: int
    source_language: str
    target_language: str
    created_at: datetime
    approved_count: int
    progress_percentage: float

class PageDetailDTO(BaseModel):
    id: str
    project_id: str
    project_title: str
    page_number: int
    total_pages: int
    status: PageStatus
    source_text: str
    image_url: str
    thumbnail_url: str
    latest_translation: Optional[str] = None
    approved_text: Optional[str] = None
    prev_page_number: Optional[int] = None
    next_page_number: Optional[int] = None
    attempts: List[dict] = []

class ProfileDTO(BaseModel):
    id: str
    name: str
    source_language: str
    target_language: str
    provider_type: ProviderType
    model_name: str
    api_key_masked: str
    system_prompt: str
    temperature: float


class PromptTemplateDTO(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    template: str
    is_default: bool
    created_at: datetime
    updated_at: datetime


class PromptTemplateCreateDTO(BaseModel):
    name: str
    description: Optional[str] = None
    template: str
    is_default: bool = False


class PromptTemplateUpdateDTO(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    template: Optional[str] = None
    is_default: Optional[bool] = None


class PageConversationDTO(BaseModel):
    id: str
    project_id: str
    page_number: int
    selected_text: Optional[str] = None
    question: str
    answer: str
    prompt_template_id: Optional[str] = None
    created_at: datetime


class PageAskDTO(BaseModel):
    question: str
    selected_text: Optional[str] = None
    prompt_template_id: Optional[str] = None

