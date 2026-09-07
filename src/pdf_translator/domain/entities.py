"""Domain entities and database models for PDF Book Translator."""
from datetime import datetime
from typing import Optional, List
from uuid import uuid4
from sqlmodel import SQLModel, Field, Relationship
from pdf_translator.domain.enums import PageStatus, ProviderType

def default_uuid() -> str:
    return str(uuid4())

DEFAULT_SYSTEM_PROMPT = """شما یک مترجم کتاب و متون تخصصی هستید.
وظیفه شما ترجمه روان، انسانی، دقیق و طبیعی متن ورودی به زبان مقصد است.

قوانین حیاتی:
۱. ترجمه باید کاملاً روان، مفهومی و با جمله‌بندی طبیعی زبان فارسی باشد؛ هرگز کلمه‌به‌کلمه و ماشینی ترجمه نکنید.
۲. رعایت دقیق ساختار و تگ‌های مارک‌داون (Markdown):
   - عناوین اصلی و سرفصل‌های فصل را با # یا ## مشخص کنید (مانند: ## تعریف عامل‌های هوش مصنوعی).
   - زیرعنوان‌ها و بخش‌های فرعی را با ### مشخص کنید.
   - بولت‌پوینت‌ها و لیست‌ها را با - یا * شروع کنید.
   - لیست‌های ترتیبی را با 1. و 2. مشخص کنید.
   - اصطلاحات کلیدی یا کلمات تاکیدی را با **bold** یا `code` مشخص کنید.
   - پاراگراف‌ها را با یک خط خالی از هم جدا کنید.
۳. حفظ جایگاه تصاویر و دیاگرام‌ها:
   - تگ‌های تصاویر مانند `![Figure...](/api/...)` را دقیقاً در همان جایگاه میان پاراگراف‌ها حفظ کنید. عنوان داخل کروشه `![...]` را می‌توانید به فارسی ترجمه کنید اما آدرس داخل پرانتز `(...)` را دست‌نخورده نگه دارید.
۴. قوانین اکید برای کدهای برنامه‌نویسی و متغیرها:
   - تمام بلوک‌های کد و تگ‌های [[CODE_BLOCK_...]] باید ۱۰۰٪ بدون هیچ‌گونه ترجمه، تغییر، ادغام یا حذف، با حفظ دقیق ساختار و موقعیت به زبان اصلی منتقل شوند. نیازی به ترجمه کدهای برنامه‌نویسی نیست.
   - نام توابع، متغیرها، کلاس‌ها، دستورات و کدهای درون‌خطی مانند `variable` یا `function_name()` نباید ترجمه شوند و باید داخل بک‌تیک باقی بمانند.
۵. هیچ بخشی از متن را خلاصه نکنید، چیزی اضافه نکنید و هیچ عبارت معناداری را حذف نکنید.
۶. لحن و مقصود نویسنده اصلی را بدون تغییر منتقل کنید.
۷. در خصوص اصطلاحات تخصصی، تنها در مواردی که معادل ترجمه شده ممکن است مبهم باشد، اصل کلمه انگلیسی را در داخل پرانتز بنویسید (مانند: شیء مقدار (Value Object)). از افراط در پرانتزگذاری خودداری کنید.
"""

class TranslationProfile(SQLModel, table=True):
    __tablename__ = "translation_profiles"

    id: str = Field(default_factory=default_uuid, primary_key=True)
    name: str = Field(default="Default Technical English to Persian")
    source_language: str = Field(default="English")
    target_language: str = Field(default="Persian")
    provider_type: ProviderType = Field(default=ProviderType.MOCK)
    model_name: str = Field(default="gemini-1.5-pro")
    api_key: Optional[str] = Field(default=None)
    system_prompt: str = Field(default=DEFAULT_SYSTEM_PROMPT)
    temperature: float = Field(default=0.3)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    projects: List["Project"] = Relationship(back_populates="profile")


class GlossaryItem(SQLModel, table=True):
    __tablename__ = "glossary_items"

    id: str = Field(default_factory=default_uuid, primary_key=True)
    project_id: Optional[str] = Field(default=None, foreign_key="projects.id", index=True)
    source_term: str = Field(index=True)
    target_term: str
    include_parenthesis_english: bool = Field(default=True)
    notes: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Project(SQLModel, table=True):
    __tablename__ = "projects"

    id: str = Field(default_factory=default_uuid, primary_key=True)
    title: str = Field(index=True)
    source_pdf_filename: str
    source_pdf_path: str
    storage_dir: str
    total_pages: int = Field(default=0)
    source_language: str = Field(default="English")
    target_language: str = Field(default="Persian")
    profile_id: Optional[str] = Field(default=None, foreign_key="translation_profiles.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    profile: Optional[TranslationProfile] = Relationship(back_populates="projects")
    pages: List["Page"] = Relationship(back_populates="project", sa_relationship_kwargs={"cascade": "all, delete-orphan"})


class Page(SQLModel, table=True):
    __tablename__ = "pages"

    id: str = Field(default_factory=default_uuid, primary_key=True)
    project_id: str = Field(foreign_key="projects.id", index=True)
    page_number: int = Field(index=True)  # 1-based index
    status: PageStatus = Field(default=PageStatus.READY, index=True)
    source_text: str = Field(default="")
    image_path: str = Field(default="")
    thumbnail_path: str = Field(default="")
    latest_translation: Optional[str] = Field(default=None)
    approved_text: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    project: Optional[Project] = Relationship(back_populates="pages")
    attempts: List["TranslationAttempt"] = Relationship(back_populates="page", sa_relationship_kwargs={"cascade": "all, delete-orphan"})

    def can_transition_to(self, new_status: PageStatus) -> bool:
        """Validates domain lifecycle state transitions for Page according to ADR."""
        if self.status == new_status:
            return True
        allowed_transitions = {
            PageStatus.PENDING: {PageStatus.READY, PageStatus.FAILED},
            PageStatus.READY: {PageStatus.APPROVED_FOR_TRANSLATION, PageStatus.PENDING, PageStatus.FAILED},
            PageStatus.APPROVED_FOR_TRANSLATION: {PageStatus.TRANSLATING, PageStatus.READY, PageStatus.APPROVED_FOR_TRANSLATION, PageStatus.FAILED},
            PageStatus.TRANSLATING: {PageStatus.TRANSLATED, PageStatus.IN_REVIEW, PageStatus.FAILED},
            PageStatus.TRANSLATED: {PageStatus.IN_REVIEW, PageStatus.APPROVED, PageStatus.APPROVED_FOR_TRANSLATION, PageStatus.FAILED},
            PageStatus.IN_REVIEW: {PageStatus.APPROVED, PageStatus.APPROVED_FOR_TRANSLATION, PageStatus.TRANSLATING, PageStatus.FAILED},
            PageStatus.APPROVED: {PageStatus.EXPORTED, PageStatus.IN_REVIEW, PageStatus.APPROVED_FOR_TRANSLATION},
            PageStatus.EXPORTED: {PageStatus.APPROVED, PageStatus.IN_REVIEW},
            PageStatus.FAILED: {PageStatus.READY, PageStatus.APPROVED_FOR_TRANSLATION, PageStatus.TRANSLATING},
        }
        return new_status in allowed_transitions.get(self.status, set())


class TranslationAttempt(SQLModel, table=True):
    __tablename__ = "translation_attempts"

    id: str = Field(default_factory=default_uuid, primary_key=True)
    page_id: str = Field(foreign_key="pages.id", index=True)
    project_id: str = Field(foreign_key="projects.id", index=True)
    page_number: int = Field(index=True)
    version_number: int = Field(default=1)
    provider_name: str
    model_name: str
    prompt_used: str
    raw_response: str
    edited_text: str
    is_approved: bool = Field(default=False)
    operator_notes: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    page: Optional[Page] = Relationship(back_populates="attempts")


class PromptTemplate(SQLModel, table=True):
    __tablename__ = "prompt_templates"

    id: str = Field(default_factory=default_uuid, primary_key=True)
    name: str = Field(index=True)
    description: Optional[str] = Field(default=None)
    template: str
    is_default: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class PageConversation(SQLModel, table=True):
    __tablename__ = "page_conversations"

    id: str = Field(default_factory=default_uuid, primary_key=True)
    project_id: str = Field(foreign_key="projects.id", index=True)
    page_number: int = Field(index=True)
    selected_text: Optional[str] = Field(default=None)
    question: str
    answer: str
    prompt_template_id: Optional[str] = Field(default=None, foreign_key="prompt_templates.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

