import pytest
from sqlmodel import Session, create_engine, SQLModel
from pdf_translator.domain.entities import Project, Page, TranslationProfile, PromptTemplate, PageConversation
from pdf_translator.domain.enums import ProviderType, PageStatus
from pdf_translator.adapters.storage.sqlite_repo import (
    SQLitePromptTemplateRepository,
    SQLitePageConversationRepository,
    SQLitePageRepository,
    SQLiteProjectRepository,
    SQLiteProfileRepository,
)
from pdf_translator.application.qa_service import QAService
from pdf_translator.application.dtos import (
    PromptTemplateCreateDTO,
    PromptTemplateUpdateDTO,
    PageAskDTO,
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

        # Create Profile (Mock)
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
        )

        yield {
            "session": session,
            "service": service,
            "tpl_repo": tpl_repo,
            "convo_repo": convo_repo,
            "project": project,
            "page": page,
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
