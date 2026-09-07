"""Database initialization and session management."""
from sqlmodel import SQLModel, create_engine, Session, select
from typing import Generator
from pdf_translator.config import settings
from pdf_translator.domain.entities import (
    Project, Page, TranslationProfile, TranslationAttempt, GlossaryItem,
    PromptTemplate, PageConversation
)

engine = None

def get_engine():
    global engine
    if engine is None:
        db_url = settings.get_db_url()
        connect_args = {"check_same_thread": False} if "sqlite" in db_url else {}
        engine = create_engine(db_url, echo=False, connect_args=connect_args)
    return engine

def init_db():
    """Create all tables and ensure default profile and prompt templates exist."""
    eng = get_engine()
    SQLModel.metadata.create_all(eng)
    
    with Session(eng) as session:
        # Default Translation Profile
        statement = select(TranslationProfile).where(TranslationProfile.name == "Default Technical English to Persian")
        profile = session.exec(statement).first()
        if not profile:
            profile = TranslationProfile(
                name="Default Technical English to Persian",
                source_language="English",
                target_language="Persian",
                model_name="gemini-1.5-pro",
            )
            session.add(profile)

        # Default Prompt Templates for In-Reading AI Assistant
        existing_templates = session.exec(select(PromptTemplate)).all()
        if not existing_templates:
            defaults = [
                PromptTemplate(
                    name="🧑‍🏫 استاد مفهومی و عمیق",
                    description="توضیح کامل، ریشه‌ای و مفهومی همراه با سناریو و مثال واقعی در صنعت نرم‌افزار",
                    template="""شما یک استاد و مهندس ارشد نرم‌افزار هستید که مفاهیم را عمیق، کاربردی، ساختاریافته و شفاف تدریس می‌کنید.

متن مورد سوال از کتاب:
\"\"\"
{selected_text}
\"\"\"

کانتکست کامل صفحه برای درک زمینه و جریان بحث:
\"\"\"
{page_text}
\"\"\"

سوال کاربر:
{question}

دستورالعمل پاسخ:
- به زبان فارسی بسیار روان، شیوا، محترمانه و ساختاریافته با مارک‌داون پاسخ دهید.
- فلسفه و علت وجودی این مفهوم را باز کنید و یک سناریوی ملموس و واقعی در توسعه نرم‌افزار ارائه دهید.
- نکات کلیدی را با بولت‌پوینت تفکیک کنید.""",
                    is_default=True
                ),
                PromptTemplate(
                    name="💻 تحلیل‌گر تخصصی کد",
                    description="تحلیل خط‌به‌خط ساختار کد، الگوهای طراحی و بررسی مزایا و معایب پیاده‌سازی",
                    template="""شما یک معمار نرم‌افزار و متخصص ارشد کدنویسی هستید.

کد یا متن مورد سوال از کتاب:
\"\"\"
{selected_text}
\"\"\"

کانتکست کامل صفحه:
\"\"\"
{page_text}
\"\"\"

سوال کاربر:
{question}

دستورالعمل پاسخ:
- به زبان فارسی دقیق و تخصصی تحلیل کنید.
- ساختار کد، متغیرها، الگوهای استفاده‌شده و دلایل این شیوه پیاده‌سازی را به تفکیک توضیح دهید.
- نقاط قوت، ریسک‌ها یا روش‌های جایگزین را مشخص کنید.""",
                    is_default=False
                ),
                PromptTemplate(
                    name="👶 توضیح به زبان بسیار ساده (ELI5)",
                    description="توضیح مفاهیم سخت و انتزاعی با تشبیهات ساده از زندگی روزمره",
                    template="""شما یک معلم صبور هستید که سخت‌ترین و تئوریک‌ترین مفاهیم دنیای کامپیوتر را به زبان فوق‌العاده ساده و ملموس (مثل یک تمثیل از زندگی روزمره) توضیح می‌دهید.

متن مورد سوال از کتاب:
\"\"\"
{selected_text}
\"\"\"

کانتکست صفحه:
\"\"\"
{page_text}
\"\"\"

سوال کاربر:
{question}

دستورالعمل پاسخ:
- به زبان فارسی ساده، گیرا، خودمانی و بدون اصطلاحات پیچیده و غیرضروری پاسخ دهید.
- با یک داستان یا تشبیه از زندگی روزمره مفهوم را در ذهن کاربر جا بیندازید.""",
                    is_default=False
                ),
                PromptTemplate(
                    name="⚡ خلاصه سریع و نکات کلیدی",
                    description="پاسخ گلوله‌ای، مستقیم و بدون حاشیه در چند بند کوتاه",
                    template="""شما یک دستیار خلاصه و سریع در مطالعه هستید.

متن مورد سوال:
\"\"\"
{selected_text}
\"\"\"

سوال کاربر:
{question}

دستورالعمل پاسخ:
- بسیار خلاصه، مستقیم و در ۲ الی ۴ بند کوتاه (بولت‌پوینت) پاسخ دهید و از مقدمه‌چینی پرهیز کنید.""",
                    is_default=False
                ),
            ]
            for t in defaults:
                session.add(t)

        session.commit()

def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session
