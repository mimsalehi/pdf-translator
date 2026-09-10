"""Database initialization and session management."""
from sqlmodel import SQLModel, create_engine, Session, select, text
import json
from typing import Generator
from pdf_translator.application.persian_cleanup import clean_markdown_persian
from pdf_translator.config import settings
from pdf_translator.domain.entities import (
    DEFAULT_SYSTEM_PROMPT,
    Project, Page, TranslationProfile, TranslationAttempt, GlossaryItem,
    PromptTemplate, PageConversation, ChapterSummary, ChapterPromptTemplate,
    ChapterConversation
)

engine = None

def get_engine():
    global engine
    if engine is None:
        db_url = settings.get_db_url()
        connect_args = {"check_same_thread": False} if "sqlite" in db_url else {}
        engine = create_engine(db_url, echo=False, connect_args=connect_args)
    return engine

def reset_engine():
    """Closes all active connections and resets engine instance."""
    global engine
    if engine is not None:
        try:
            engine.dispose()
        except Exception:
            pass
        engine = None

def init_db():
    """Create all tables and ensure default profile and prompt templates exist."""
    eng = get_engine()
    SQLModel.metadata.create_all(eng)
    with eng.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE chapter_summaries ADD COLUMN intermediate_summaries_json TEXT"))
            conn.commit()
        except Exception:
            pass

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
                system_prompt=DEFAULT_SYSTEM_PROMPT,
            )
            session.add(profile)
        elif "De-AI Rules" not in profile.system_prompt:
            # Upgrade system prompt to latest standard with De-AI and orthography rules
            profile.system_prompt = DEFAULT_SYSTEM_PROMPT
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
- به زبان فارسی بسیار روان، شیوا، محترمانه و ساختاریافته (Formal-but-human) با مارک‌داون پاسخ دهید.
- از عبارات متکلف و فعل‌های بادکنکی نظیر «می‌باشد»، «می‌گردد» یا «لازم به ذکر است» پرهیز کرده و از افعال طبیعی «است»، «شد» و «کرد» استفاده کنید.
- نیم‌فاصله‌ها (ZWNJ) و گیومه فارسی «...» را رعایت فرمایید و از خط تیره کشیده (—) پرهیز نمایید.
- فلسفه و علت وجودی این مفهوم را باز کنید و یک سناریوی ملموس و واقعی در توسعه نرم‌افزار ارائه دهید.
- در صورت وجود فرمول‌های ریاضی یا علمی، آن‌ها را در قالب استاندارد LaTeX بین $...$ (درون‌خطی) یا $$...$$ (بلوکی) بنویسید.
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


        # Default Prompt Templates for Chapter Summaries & Deep Note-Taking
        existing_chapter_templates = session.exec(select(ChapterPromptTemplate)).all()
        if not existing_chapter_templates:
            chapter_defaults = [
                ChapterPromptTemplate(
                    name="🧑‍🎓 نوت‌برداری جامع مفهومی و مهندسی (پیش‌فرض)",
                    description="استخراج کامل صورت‌مسئله‌ها، مکانیزم‌های معماری، فرمول‌های ریاضی و جدول مصالحه‌ها (Trade-offs) بر اساس ۱۰ اصل ترجمه و ویرایش حرفه‌ای",
                    chunk_template="""شما یک **مترجم حرفه‌ای کتاب، ویراستار زبان فارسی و معمار ارشد نرم‌افزار** هستید.
وظیفه شما مطالعه دقیق و استخراج نوت‌های تخصصی، مفهومی و عمیق از بخش «{chapter_title}» (صفحات {start_page} تا {end_page}) است.

متن ورودی این بخش از کتاب:
\"\"\"
{content_text}
\"\"\"

قوانین و اصول حاکم بر نوت‌برداری:
۱. معنا، نه کلمه: اصلاً کلمه‌به‌کلمه ترجمه نکنید. مفهوم و استدلال نویسنده را درک کرده و به روان‌ترین، خوش‌خوان‌ترین و طبیعی‌ترین شکل در فارسی بیان کنید.
۲. حذف ردپای هوش مصنوعی و نثر متکلف: از افعال «است/شد/کرد» به جای «می‌باشد/می‌گردد/به عمل آمد» استفاده کنید. عبارات پرکننده و تشریفاتی نظیر «لازم به ذکر است»، «شایان ذکر است»، «در راستای»، «نقش بسزایی ایفا می‌کند» و خط تیره‌های کشیده (Em-dash —) را کاملاً کنار بگذارید.
۳. دستور خط و نیم‌فاصله: نیم‌فاصله‌ها (ZWNJ) در افعال («می‌شود»)، وندها («کتاب‌ها»، «بزرگ‌تر») و پیشوندها («به‌عنوان») را دقیق رعایت نمایید و از «گیومه فارسی» استفاده کنید.
۴. عدم حذف جزئیات: هیچ استدلال، مثال، مکانیزم، چالش یا فرمولی را حذف نکنید؛ از کلی‌گویی و خلاصه سطحی پرهیز کنید.
۵. اصطلاحات تخصصی مهندسی: همواره عنوان انگلیسی اصطلاحات تخصصی را در اولین کاربرد در پرانتز قید کنید (مانند: مقیاس‌پذیری (Scalability)، تکثیر داده‌ها (Replication)).
۶. فرمول‌ها و ریاضیات: فرمول‌های ریاضی، علمی و محاسباتی را حتماً در قالب استاندارد LaTeX بین $...$ (درون‌خطی) یا $$...$$ (بلوکی) بنویسید.
۷. عناصر فنی: نام متغیرها، توابع و اصطلاحات کدنویسی باید دست‌نخورده به انگلیسی باقی بمانند.
۸. بازبینی نهایی: متن نوت را مانند یک ویراستار بازخوانی کنید تا جملات طولانی و انگلیسی‌زده نشوند.

خروجی باید شامل استخراج کامل صورت‌مسئله‌ها، مفاهیم معماری، نحوه عملکرد مکانیزم‌ها، چرایی تصمیمات فنی و نکات طلایی باشد.""",
                    is_default=True
                ),
                ChapterPromptTemplate(
                    name="⚡ خلاصه سریع و نکات کلیدی فصل",
                    description="مرور فشرده و متمرکز بر بولت‌پوینت‌های طلایی و تصمیم‌گیری‌های فنی در زمان کوتاه",
                    chunk_template="""شما یک متخصص خلاصه‌سازی سریع متون فنی هستید. متن زیر از فصل «{chapter_title}» (صفحات {start_page} تا {end_page}) را بررسی کنید و نکات کلیدی آن را بدون حاشیه استخراج نمایید.

متن بخش:
\"\"\"
{content_text}
\"\"\"

دستورالعمل:
- نکات کلیدی، تعاریف و چالش‌ها را به صورت بولت‌پوینت‌های کوتاه، مستقیم و دقیق به فارسی استخراج کنید.
- فرمول‌های موجود را در قالب LaTeX درج کنید.""",
                ),
            ]
            for ct in chapter_defaults:
                session.add(ct)

        # Mark any interrupted/stalled chapter summaries as FAILED on startup so they do not stay stuck at 0%
        stalled_summaries = session.exec(
            select(ChapterSummary).where(ChapterSummary.status.in_(["PENDING", "PROCESSING"]))
        ).all()
        for s in stalled_summaries:
            s.status = "FAILED"
            s.progress_message = "پردازش با ری‌استارت سرور متوقف شد."
            s.error_message = "پردازش با ری‌استارت سرور متوقف شد. لطفاً دکمه تلاش مجدد را بزنید."
            session.add(s)

        # Normalize existing chapter summaries chunk_notes_json with proper markdown emphasis
        try:
            all_summaries = session.exec(select(ChapterSummary)).all()
            for cs in all_summaries:
                if cs.chunk_notes_json:
                    try:
                        notes_data = json.loads(cs.chunk_notes_json)
                        changed = False
                        for n in notes_data:
                            old_n = n.get("note", "")
                            if old_n:
                                new_n = clean_markdown_persian(old_n)
                                if new_n != old_n:
                                    n["note"] = new_n
                                    changed = True
                        if changed:
                            cs.chunk_notes_json = json.dumps(notes_data, ensure_ascii=False)
                            session.add(cs)
                    except Exception:
                        pass
        except Exception:
            pass
        session.commit()

def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session
