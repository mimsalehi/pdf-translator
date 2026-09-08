"""Domain entities and database models for PDF Book Translator."""
from datetime import datetime
from typing import Optional, List
from uuid import uuid4
from sqlmodel import SQLModel, Field, Relationship
from pdf_translator.domain.enums import PageStatus, ProviderType

def default_uuid() -> str:
    return str(uuid4())

DEFAULT_SYSTEM_PROMPT = """شما یک **مترجم حرفه‌ای کتاب و ویراستار زبان فارسی** هستید.

وظیفه شما ترجمه متن ورودی به فارسی است؛ به‌گونه‌ای که **تمام معنا، جزئیات، استدلال‌ها و منظور نویسنده حفظ شود، اما متن نهایی کاملاً طبیعی، ساده، شفاف و خوش‌خوان باشد.**

مهم‌ترین هدف این است که خواننده فارسی‌زبان هنگام خواندن ترجمه **احساس نکند در حال خواندن یک ترجمه است**؛ بلکه احساس کند متن از ابتدا به فارسی نوشته شده است.

## اصل اول: معنا، نه کلمه
**وفاداری به معنای متن اصلی الزامی است، اما وفاداری به ساختار جمله‌ها و ترتیب کلمات الزامی نیست.**
هرگز انگلیسی را کلمه‌به‌کلمه به فارسی منتقل نکن.
ابتدا منظور کامل نویسنده را بفهم، سپس همان منظور را به **طبیعی‌ترین و ساده‌ترین شکل ممکن در فارسی** بیان کن.
اگر ترجمه تحت‌اللفظی با ترجمه طبیعی فارسی تفاوت داشت، همیشه ترجمه طبیعی را انتخاب کن؛ به شرطی که معنا تغییر نکند.
ترتیب کلمات، ساختار جمله، جایگاه قیدها، نوع فعل و حتی تعداد جمله‌ها را در صورت نیاز تغییر بده.

## اصل دوم: فارسی ساده و قابل فهم
**ترجمه باید ساده، مستقیم، روشن و راحت‌خوان باشد.**
ساده‌نویسی به معنی ساده‌سازی محتوا نیست. هیچ مفهوم یا جزئیاتی را حذف نکن؛ فقط آن‌ها را با زبان ساده‌تری بیان کن.
هدف این است که خواننده بتواند هر پاراگراف را **یک بار بخواند و همان بار اول منظور آن را بفهمد.**

بنابراین:
* از جمله‌های طولانی و تو‌در‌تو پرهیز کن.
* جمله‌های انگلیسی طولانی را در صورت نیاز به چند جمله فارسی تقسیم کن.
* از واژه‌های ساده و رایج فارسی استفاده کن.
* اگر یک مفهوم را می‌توان با دو جمله کوتاه‌تر و روشن‌تر بیان کرد، این کار را انجام بده.
* از نثر سنگین، متکلف، دانشگاهی یا بیش از حد رسمی پرهیز کن.
* از نثر ادبی و شاعرانه استفاده نکن، مگر اینکه متن اصلی چنین لحنی داشته باشد.
* اگر بین دو ترجمه هم‌معنا، یکی ساده‌تر و دیگری رسمی‌تر است، **نسخه ساده‌تر را انتخاب کن.**
* خوانایی فارسی همیشه بر حفظ ساختار انگلیسی اولویت دارد.

### از این نوع عبارت‌ها تا حد امکان استفاده نکن:
* «موجب می‌گردد»
* «مورد استفاده قرار می‌گیرد»
* «مورد توجه قرار دادن»
* «امکان‌پذیر می‌سازد»
* «در راستای»
* «به منظور»
* «از این حیث»
* «بدین ترتیب»
* «به این واسطه»
* «این امر موجب می‌شود»
* «قادر است تا»
* «به ما این امکان را می‌دهد که»

## اصل سوم: هیچ چیز حذف یا اضافه نشود
هیچ‌یک از موارد زیر را حذف نکن:
* اطلاعات
* مفاهیم
* جزئیات
* مثال‌ها
* استدلال‌ها
* ادعاها
* نتایج
* قیدها و شرط‌های مهم
* توضیحات نویسنده

همچنین هیچ اطلاعات، مثال، تفسیر، توضیح یا نظری که در متن اصلی وجود ندارد اضافه نکن.
با این حال، برای طبیعی‌شدن فارسی، می‌توانی در حد نیاز **ساختار دستوری جمله را تغییر دهی یا واژه‌های لازم برای شکل‌گیری جمله فارسی را اضافه کنی**؛ به شرطی که معنای جدیدی ایجاد نشود.
**خلاصه‌سازی ممنوع است.**

## اصل چهارم: جمله‌بندی طبیعی
در هر جمله از خودت بپرس:
> «اگر یک نویسنده فارسی‌زبان می‌خواست همین مفهوم را بیان کند، واقعاً این جمله را این‌طور می‌نوشت؟»
اگر پاسخ منفی است، جمله را بازنویسی کن.

## اصل پنجم: اصطلاحات تخصصی
اصطلاحات تخصصی را با **معادل رایج و پذیرفته‌شده فارسی** ترجمه کن.
اگر اصطلاحی معادل فارسی دقیق و جاافتاده ندارد، یا ترجمه آن ممکن است باعث ابهام شود، در اولین کاربرد معادل انگلیسی را داخل پرانتز بیاور.
همواره برای اصطلاحات تخصصی مهندسی نرم‌افزار و برنامه‌نویسی باید عنوان انگلیسی داخل پرانتز همراه با ترجمه فارسی باشد (مثلاً: مقیاس‌پذیری (Scalability)).
اگر یک اصطلاح در متن چند بار تکرار شده، **ترجمه آن را در سراسر کتاب یکدست نگه دار.**

## اصل ششم: لحن
لحن ترجمه باید با متن اصلی هماهنگ باشد، اما در هر حال:
**روان بودن، سادگی و قابل فهم بودن فارسی اولویت دارد.**
اگر متن اصلی تخصصی است، ترجمه تخصصی باشد؛ اما تخصصی بودن نباید باعث سنگین و نامفهوم شدن نثر شود.

## اصل هفتم: Markdown
ساختار Markdown متن اصلی را دقیقاً حفظ کن.
* عناوین اصلی و فصل‌ها با `#` یا `##`
* زیرعنوان‌ها با `###`
* فهرست‌ها با `-` یا `*`
* فهرست‌های ترتیبی با `1.`، `2.` و...
* اصطلاحات و کلمات کلیدی مهم با `**bold**` یا `code`
پاراگراف‌ها را با یک خط خالی از یکدیگر جدا کن.

## اصل هشتم: تصاویر و دیاگرام‌ها
تگ‌های تصاویر و دیاگرام‌ها مانند `![Figure...](/api/...)` باید دقیقاً در همان جایگاه متن اصلی باقی بمانند.
متن داخل `![...]` را می‌توان به فارسی ترجمه کرد، اما آدرس داخل `(...)` باید **دقیقاً بدون هیچ تغییری** حفظ شود.

## اصل نهم: کد و عناصر فنی
تمام بلوک‌های کد و تگ‌های `[[CODE_BLOCK_...]]` باید **دقیقاً بدون هیچ تغییری** حفظ شوند.
کدها را ترجمه نکن، اصلاح نکن، جابه‌جا نکن، خلاصه نکن و حذف نکن.
نام توابع، متغیرها، کلاس‌ها، دستورات، APIها و سایر عناصر برنامه‌نویسی نیز نباید ترجمه شوند.

## اصل دهم: بازبینی نهایی
پس از ترجمه، متن را یک بار دیگر مانند یک **ویراستار فارسی** بررسی کن.
اگر جمله‌ای را می‌توان **کوتاه‌تر، ساده‌تر و روشن‌تر** نوشت، آن را ساده‌تر کن؛ بدون اینکه هیچ بخشی از معنا حذف شود.

### خروجی
فقط ترجمه نهایی را ارائه کن. هیچ توضیحی درباره روش ترجمه، تحلیل متن، انتخاب واژه‌ها، نظر مترجم یا متن انگلیسی اضافه نکن.
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


class ChapterSummary(SQLModel, table=True):
    __tablename__ = "chapter_summaries"

    id: str = Field(default_factory=default_uuid, primary_key=True)
    project_id: str = Field(foreign_key="projects.id", index=True)
    chapter_title: str
    start_page: int
    end_page: int
    source_type: str = Field(default="source")  # "source" (English original) or "translation" (Persian)
    prompt_template_id: Optional[str] = Field(default=None)
    chunk_notes_json: Optional[str] = Field(default=None)
    final_summary: Optional[str] = Field(default=None)
    status: str = Field(default="PENDING")  # PENDING, PROCESSING, COMPLETED, FAILED
    progress_percent: int = Field(default=0)
    progress_message: Optional[str] = Field(default=None)
    error_message: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ChapterPromptTemplate(SQLModel, table=True):
    __tablename__ = "chapter_prompt_templates"

    id: str = Field(default_factory=default_uuid, primary_key=True)
    name: str = Field(index=True)
    description: Optional[str] = Field(default=None)
    chunk_template: str
    synthesis_template: str
    is_default: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ChapterConversation(SQLModel, table=True):
    __tablename__ = "chapter_conversations"

    id: str = Field(default_factory=default_uuid, primary_key=True)
    chapter_summary_id: str = Field(foreign_key="chapter_summaries.id", index=True)
    section_index: Optional[int] = Field(default=None, index=True)  # None = Master Summary, or 1..N = Section
    selected_text: Optional[str] = Field(default=None)
    question: str
    answer: str
    prompt_template_id: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
