import pytest
from sqlmodel import Session, create_engine, SQLModel
from pdf_translator.domain.entities import (
    Project, Page, TranslationProfile, PromptTemplate, PageConversation,
    ChapterSummary, ChapterConversation
)
from pdf_translator.domain.enums import ProviderType, PageStatus
from pdf_translator.adapters.storage.sqlite_repo import (
    SQLitePromptTemplateRepository,
    SQLitePageConversationRepository,
    SQLitePageRepository,
    SQLiteProjectRepository,
    SQLiteProfileRepository,
    SQLiteChapterConversationRepository,
    SQLiteChapterSummaryRepository,
)
from pdf_translator.application.qa_service import QAService
from pdf_translator.application.dtos import (
    PromptTemplateCreateDTO,
    PromptTemplateUpdateDTO,
    PageAskDTO,
    ChapterAskDTO,
)
@pytest.fixture
def qa_test_env():
    engine = create_engine("sqlite:///:memory:", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        # Repositories
        tpl_repo = SQLitePromptTemplateRepository(session)
        convo_repo = SQLitePageConversationRepository(session)
        page_repo = SQLitePageRepository(session)
        proj_repo = SQLiteProjectRepository(session)
        prof_repo = SQLiteProfileRepository(session)
        ch_convo_repo = SQLiteChapterConversationRepository(session)
        ch_summary_repo = SQLiteChapterSummaryRepository(session)
        profile = TranslationProfile(
            name="Test Mock Profile",
            provider_type=ProviderType.MOCK,
            model_name="mock-ai",
        )
        prof_repo.save(profile)

        # Create Project
        project = Project(
            id="proj-123",
            title="Design Patterns Book",
            source_pdf_filename="dp.pdf",
            source_pdf_path="/tmp/dp.pdf",
            storage_dir="/tmp/dp",
            total_pages=10,
            profile_id=profile.id,
        )
        proj_repo.save(project)

        # Create Page
        page = Page(
            id="page-123",
            project_id="proj-123",
            page_number=5,
            status=PageStatus.TRANSLATED,
            source_text="Adapter pattern solves interface incompatibility.",
            latest_translation="الگوی آداپتور ناسازگاری اینترفیس‌ها را حل می‌کند.",
            image_path="/tmp/p5.png",
            thumbnail_path="/tmp/t5.png",
        )
        page_repo.save(page)

        # Create Service
        service = QAService(
            prompt_template_repo=tpl_repo,
            page_conversation_repo=convo_repo,
            page_repo=page_repo,
            project_repo=proj_repo,
            profile_repo=prof_repo,
            chapter_conversation_repo=ch_convo_repo,
            chapter_summary_repo=ch_summary_repo,
        )

        yield {
            "session": session,
            "service": service,
            "page": page,
            "project": project,
            "ch_summary_repo": ch_summary_repo,
            "ch_convo_repo": ch_convo_repo,
        }

@pytest.mark.asyncio
async def test_prompt_template_crud(qa_test_env):
    service = qa_test_env["service"]

    # 1. Create Template
    created = service.create_prompt_template(
        PromptTemplateCreateDTO(
            name="تست پرامپت استادی",
            description="برای تست",
            template="سوال: {question} / متن: {selected_text} / کل: {page_text}",
            is_default=True,
        )
    )
    assert created.id is not None
    assert created.name == "تست پرامپت استادی"
    assert created.is_default is True

    # 2. List Templates
    templates = service.list_prompt_templates()
    assert len(templates) == 1
    assert templates[0].id == created.id

    # 3. Update Template
    updated = service.update_prompt_template(
        created.id,
        PromptTemplateUpdateDTO(name="نام ویرایش شده"),
    )
    assert updated.name == "نام ویرایش شده"

    # 4. Delete Template
    deleted = service.delete_prompt_template(created.id)
    assert deleted is True
    assert len(service.list_prompt_templates()) == 0

@pytest.mark.asyncio
async def test_ask_page_question_with_context_injection(qa_test_env):
    service = qa_test_env["service"]

    # Create a template with variables
    tpl = service.create_prompt_template(
        PromptTemplateCreateDTO(
            name="استاد",
            template="محتوا: {selected_text}\nکانتکست: {page_text}\nسوال: {question}",
            is_default=True,
        )
    )

    # Ask question
    dto = PageAskDTO(
        question="چرا از آداپتور استفاده میکنیم؟",
        selected_text="interface incompatibility",
        prompt_template_id=tpl.id,
    )

    convo = await service.ask_page_question("proj-123", 5, dto)
    assert convo.id is not None
    assert convo.question == "چرا از آداپتور استفاده میکنیم؟"
    assert convo.selected_text == "interface incompatibility"
    assert len(convo.answer) > 0

    # Verify conversation history retrieval
    history = service.list_page_conversations("proj-123", 5)
    assert len(history) == 1
    assert history[0].id == convo.id

@pytest.mark.asyncio
async def test_ask_page_question_unmasks_image_blocks(qa_test_env, monkeypatch):
    service = qa_test_env["service"]
    page = qa_test_env["page"]
    page.source_text = "Here is an architecture diagram:\n![Architecture](/api/projects/proj-123/pages/5/images/1)"
    qa_test_env["session"].add(page)
    qa_test_env["session"].commit()

    # Mock provider to return an answer referencing the image placeholder
    captured_system_prompt = []
    async def mock_translate(*args, **kwargs):
        captured_system_prompt.append(kwargs.get("system_prompt", ""))
        return "همانطور که در [[IMAGE_BLOCK_0]] می‌بینید، فرمول به صورت $$E = mc^2$$ است."

    from pdf_translator.adapters.providers.mock_provider import MockTranslationProvider
    monkeypatch.setattr(MockTranslationProvider, "translate", mock_translate)

    dto = PageAskDTO(
        question="این دیاگرام را توضیح بده",
        selected_text=None,
    )

    convo = await service.ask_page_question("proj-123", 5, dto)
    # Verify image block is restored
    assert "![Architecture](/api/projects/proj-123/pages/5/images/1)" in convo.answer
    assert "[[IMAGE_BLOCK_0]]" not in convo.answer
    assert "$$E = mc^2$$" in convo.answer

    # Verify system prompt has LaTeX instruction
    assert len(captured_system_prompt) == 1
    assert "LaTeX" in captured_system_prompt[0]
    assert "$$" in captured_system_prompt[0]


@pytest.mark.asyncio
async def test_ask_page_question_fallback_image_replacement(qa_test_env, monkeypatch):
    service = qa_test_env["service"]
    page = qa_test_env["page"]
    page.source_text = "Text without explicit markdown image tags"
    qa_test_env["session"].add(page)
    qa_test_env["session"].commit()

    async def mock_translate(*args, **kwargs):
        return "پاسخ شامل [[IMAGE_BLOCK_0]] است."

    from pdf_translator.adapters.providers.mock_provider import MockTranslationProvider
    monkeypatch.setattr(MockTranslationProvider, "translate", mock_translate)

    dto = PageAskDTO(question="تست تصویر")
    convo = await service.ask_page_question("proj-123", 5, dto)
    assert "![تصویر 1](/api/projects/proj-123/pages/5/images/1)" in convo.answer
    assert "[[IMAGE_BLOCK_0]]" not in convo.answer


@pytest.mark.asyncio
async def test_ask_page_question_follow_up_without_new_highlight(qa_test_env, monkeypatch):
    service = qa_test_env["service"]

    captured_prompts = []
    captured_system_prompts = []

    async def mock_translate(*args, **kwargs):
        captured_prompts.append(kwargs.get("source_text", ""))
        captured_system_prompts.append(kwargs.get("system_prompt", ""))
        if len(captured_prompts) == 1:
            return "پاسخ سوال اول: این الگو کلاس‌های ناسازگار را سازگار می‌کند."
        return "پاسخ سوال دوم: در ادامه، مزیت اصلی کاهش وابستگی است."

    from pdf_translator.adapters.providers.mock_provider import MockTranslationProvider
    monkeypatch.setattr(MockTranslationProvider, "translate", mock_translate)

    # 1. Ask initial question with a specific highlight
    dto1 = PageAskDTO(
        question="این بخش چه مفهومی دارد؟",
        selected_text="مفهوم کلیدی آداپتور",
    )
    convo1 = await service.ask_page_question("proj-123", 5, dto1)
    assert convo1.selected_text == "مفهوم کلیدی آداپتور"
    assert "مفهوم کلیدی آداپتور" in captured_prompts[0]

    # 2. Ask follow-up question WITHOUT any new highlight
    dto2 = PageAskDTO(
        question="چه مزایای دیگری دارد؟",
        selected_text=None,
    )
    convo2 = await service.ask_page_question("proj-123", 5, dto2)

    # Verification:
    # A. The follow-up record does NOT save an old or fake highlight
    assert convo2.selected_text is None

    # B. The prompt for follow-up includes prior conversation history
    prompt2 = captured_prompts[1]
    assert "تاریخچه گفتگوی قبلی" in prompt2
    assert "این بخش چه مفهومی دارد؟" in prompt2
    assert "پاسخ سوال اول" in prompt2
    assert "چه مزایای دیگری دارد؟" in prompt2

    # C. The prompt does NOT contain an old {selected_text} block or (کل صفحه / بدون هایلایت خاص)
    assert "(کل صفحه / بدون هایلایت خاص)" not in prompt2
    assert "متن مورد سوال از کتاب" not in prompt2

    # D. System prompt contains instruction for logical continuation
    assert "در ادامه سوال و پاسخ‌های قبلی" in captured_system_prompts[1]


@pytest.mark.asyncio
async def test_ask_chapter_question_section_and_master(qa_test_env, monkeypatch):
    import json
    service = qa_test_env["service"]
    ch_summary_repo = qa_test_env["ch_summary_repo"]

    # Create ChapterSummary with 2 section notes and final summary
    ch = ChapterSummary(
        project_id="proj-123",
        chapter_title="Chapter 1: Architecture",
        start_page=1,
        end_page=5,
        chunk_notes_json=json.dumps([
            {
                "section_index": 1,
                "section_title": "Scalability Basics",
                "start_page": 1,
                "end_page": 3,
                "note": "نوت بخش ۱ درباره مقیاس‌پذیری و بار کاری."
            },
            {
                "section_index": 2,
                "section_title": "Replication",
                "start_page": 4,
                "end_page": 5,
                "note": "نوت بخش ۲ درباره تکثیر داده و دسترسی‌پذیری."
            }
        ], ensure_ascii=False),
        final_summary="# خلاصه جامع فصل اول\n\nاین سند ترکیب تمام بخش‌ها است.",
        status="COMPLETED"
    )
    saved_ch = ch_summary_repo.save(ch)

    captured = []
    async def mock_translate(*args, **kwargs):
        captured.append(kwargs.get("source_text", ""))
        return "پاسخ هوش مصنوعی به سوال در مورد نوت فصل."

    from pdf_translator.adapters.providers.mock_provider import MockTranslationProvider
    monkeypatch.setattr(MockTranslationProvider, "translate", mock_translate)

    # 1. Ask question about Section 2 specifically
    dto1 = ChapterAskDTO(
        question="تکثیر داده در بخش ۲ چه تاثیری بر دسترسی‌پذیری دارد؟",
        section_index=2,
        selected_text="تکثیر داده و دسترسی‌پذیری",
    )
    convo1 = await service.ask_chapter_question(saved_ch.id, dto1)
    assert convo1.chapter_summary_id == saved_ch.id
    assert convo1.section_index == 2
    assert convo1.selected_text == "تکثیر داده و دسترسی‌پذیری"
    assert "نوت بخش ۲ درباره تکثیر داده" in captured[0]

    # 2. Ask question about Master Summary (section_index = None)
    dto2 = ChapterAskDTO(
        question="نتیجه‌گیری کلی فصل چیست؟",
        section_index=None,
    )
    convo2 = await service.ask_chapter_question(saved_ch.id, dto2)
    assert convo2.section_index is None
    assert "خلاصه جامع فصل اول" in captured[1]

    # 3. List conversations for Section 2 vs Master
    sec2_convos = service.list_chapter_conversations(saved_ch.id, section_index=2)
    assert len(sec2_convos) == 1
    assert sec2_convos[0].id == convo1.id

    master_convos = service.list_chapter_conversations(saved_ch.id, section_index=None)
    # When section_index is None, returns all conversations or master
    all_convos = service.list_chapter_conversations(saved_ch.id)
    assert len(all_convos) == 2

    # 4. Delete conversation
    deleted = service.delete_chapter_conversation(convo1.id)
    assert deleted is True
    assert len(service.list_chapter_conversations(saved_ch.id)) == 1
