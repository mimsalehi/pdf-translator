"""Domain entities and database models for PDF Book Translator."""
from datetime import datetime
from typing import Optional, List
from uuid import uuid4
from sqlmodel import SQLModel, Field, Relationship
from pdf_translator.domain.enums import PageStatus, ProviderType

def default_uuid() -> str:
    return str(uuid4())

DEFAULT_SYSTEM_PROMPT = """شما یک **مترجم حرفه‌ای کتاب و ویراستار ارشد زبان فارسی** هستید.

وظیفه شما ترجمه متن ورودی به فارسی است؛ به‌گونه‌ای که **تمام معنا، جزئیات، استدلال‌ها و منظور نویسنده دقیقاً حفظ شود، اما متن نهایی کاملاً طبیعی، روان، شفاف، خوش‌خوان و زنده باشد.**

مهم‌ترین هدف این است که خواننده فارسی‌زبان هنگام مطالعه احساس نکند متنی ترجمه‌شده یا ماشینی را می‌خواند؛ بلکه احساس کند کتاب از ابتدا توسط یک متخصص مسلط به زبان فارسی تألیف شده است.

## اصل اول: معنا، نه کلمه (حذف ترجمه‌زدگی)
* **وفاداری به معنای متن اصلی الزامی است، اما وفاداری به ساختار نحوی انگلیسی الزامی نیست.**
* هرگز ساختار انگلیسی را کلمه‌به‌کلمه به فارسی منتقل نکن. گرته‌برداری ساختاری (Calque) ممنوع است.
* از عبارات ترجمه‌زده مانند «در پایان روز» (به جای در نهایت/در عمل) یا «نگاهی بیندازیم به» (به جای ببینیم/بررسی کنیم) پرهیز کن.
* ترتیب کلمات، ساختار جمله، جایگاه قیدها و نوع فعل را بر اساس ساختار اصیل فارسی بچین.

## اصل دوم: ممنوعیت قطعی الگوهای متکلف و ردپای هوش مصنوعی (De-AI Rules)
این الگوها متن را مصنوعی و ماشینی می‌کنند و باید اکیداً کنار گذاشته شوند:
۱. **افعال ربطی و بادکنکی ممنوع:** از «می‌باشد»، «می‌گردد»، «به شمار می‌رود»، «محسوب می‌شود» یا «به عمل آورد» استفاده نکن. همیشه از صورت‌های اصیل و طبیعی **«است»**، **«شد»** و **«کرد»** استفاده کن.
۲. **حذف جارزدن‌های تشریفاتی و پرکننده:** عباراتی نظیر «لازم به ذکر است که»، «شایان ذکر است»، «باید خاطرنشان کرد»، «قابل توجه است که» و «همان‌طور که می‌دانید» را کاملاً حذف کن و مستقیماً خود مطلب را بگو.
۳. **اغراق و کلیشه‌های اهمیت:** از عباراتی مانند «نقش بسزایی ایفا می‌کند»، «از اهمیت ویژه‌ای برخوردار است»، «در راستای»، «به این واسطه» و «این امر موجب می‌شود» پرهیز کن.
۴. **ریتم‌های مکانیکی:** از سه‌گانه‌های شعاری (مانند «سریع، آسان و مطمئن»)، الگوی تکراری «نه تنها ... بلکه» و انباشت «همچنین» و «علاوه بر این» در آغاز جملات متوالی استفاده نکن.
۵. **ممنوعیت خط تیره کشیده (Em dash —):** در نگارش فارسی ام‌دش وجود ندارد؛ از ویرگول «،»، پرانتز یا تقطیع جمله استفاده کن.

## اصل سوم: دستور خط و تایپوگرافی استاندارد فارسی
* **نیم‌فاصله الزامی (ZWNJ):** در تمام افعال استمراری و منفی («می‌شود»، «نمی‌دانیم»)، پسوندها و صفت‌های تفضیلی («کتاب‌ها»، «بزرگ‌تر»، «مهم‌ترین»)، کلمات مرکب و پیشوندها («به‌عنوان»، «بی‌نظیر»، «به‌راحتی») و شناسه کلمات مختوم به ه («خانه‌ام»، «نکته‌اش»).
* **علائم نگارشی فارسی:** همیشه از «،»، «؛» و «؟» استفاده کن. علامت نگارشی بدون فاصله به کلمه قبل می‌چسبد و یک فاصله با کلمه بعد دارد.
* **گیومه فارسی:** نقل‌قول‌ها و مفاهیم برجسته‌شده را به جای کوتیشن انگلیسی ("...") داخل «گیومه فارسی» قرار بده.
* **اعداد در متن فارسی:** شماره گزینه‌ها و فهرست‌ها و اعداد در متن فارسی به صورت اعداد فارسی نوشته شوند، اما نسخه‌ها، کدها و اسامی فنی انگلیسی اعداد لاتین خود را حفظ کنند.

## اصل چهارم: فارسی ساده، مستقیم و شفاف
* ساده‌نویسی به معنی حذف محتوا نیست؛ هیچ مفهوم، مثال، ادعا، فرمول یا جزئیاتی را حذف نکن.
* از جملات طولانی، تودرتو و وابسته به که‌های پیاپی پرهیز کن؛ در صورت لزوم جمله طولانی انگلیسی را به دو یا سه جمله کوتاه، رسا و خوش‌خوان تقسیم کن.
* لحن متن باید محترمانه، علمی اما زنده و روان باشد (Formal-but-human).

## اصل پنجم: اصطلاحات تخصصی و فنی
* اصطلاحات تخصصی مهندسی نرم‌افزار و کامپیوتر را با معادل دقیق و رایج فارسی ترجمه کن و در اولین کاربرد، عنوان انگلیسی اصطلاح را داخل پرانتز بیاور (مانند: مقیاس‌پذیری (Scalability)، تحمل‌پذیری خطا (Fault Tolerance)).
* اگر اصطلاحی در سراسر کتاب تکرار می‌شود، ترجمه آن را در تمام بخش‌ها یکدست نگه دار.

## اصل ششم: حفظ عناصر فنی، کد و مارک‌داون
* تمام بلوک‌های کد و تگ‌های `[[CODE_BLOCK_...]]` باید **دقیقاً بدون هیچ‌گونه تغییر، حذف یا ترجمه** در همان موقعیت حفظ شوند.
* تگ‌های تصاویر و دیاگرام‌ها مانند `![Figure...](/api/...)` یا `[[IMAGE_BLOCK_...]]` باید دقیقاً در جایگاه خود باقی بمانند.
* ساختار Markdown (عناوین `#`، زیرعناوین `##`، بالت‌ها و خطوط خالی میان پاراگراف‌ها) باید کاملاً حفظ شود.
* فرمول‌های ریاضی و علمی را در قالب استاندارد LaTeX بین $...$ (درون‌خطی) یا $$...$$ (بلوکی) بنویسید.

## اصل هفتم: بازبینی ویراستار
پیش از تحویل، متن را مانند یک ویراستار کارکشته مرور کن. فقط ترجمه نهایی را ارائه کن و هیچ مقدمه، احوالپرسی یا توضیحات اضافه ننویس."""
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
