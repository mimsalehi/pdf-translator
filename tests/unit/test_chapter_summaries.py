import json
import pytest
from pathlib import Path
from sqlmodel import Session, create_engine, SQLModel
from pdf_translator.domain.entities import Project, Page, TranslationProfile, ChapterSummary, ChapterPromptTemplate
from pdf_translator.domain.enums import ProviderType, PageStatus
from pdf_translator.adapters.storage.sqlite_repo import (
    SQLiteChapterSummaryRepository,
    SQLiteChapterPromptTemplateRepository,
    SQLitePageRepository,
    SQLiteProjectRepository,
    SQLiteProfileRepository,
)
from pdf_translator.application.chapter_service import ChapterService
from pdf_translator.application.dtos import (
    ChapterSummaryCreateDTO,
    ChapterSummaryUpdateDTO,
    ChapterPromptTemplateCreateDTO,
    ChapterPromptTemplateUpdateDTO,
)


@pytest.fixture
def chapter_test_env(tmp_path):
    engine = create_engine("sqlite:///:memory:", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ch_repo = SQLiteChapterSummaryRepository(session)
        tpl_repo = SQLiteChapterPromptTemplateRepository(session)
        page_repo = SQLitePageRepository(session)
        proj_repo = SQLiteProjectRepository(session)
        prof_repo = SQLiteProfileRepository(session)

        # Profile
        profile = TranslationProfile(
            name="Test Mock Profile",
            provider_type=ProviderType.MOCK,
            model_name="mock-ai",
        )
        prof_repo.save(profile)

        # Project
        project = Project(
            id="proj-ch-test",
            title="Distributed Systems Book",
            source_pdf_filename="ds.pdf",
            source_pdf_path=str(tmp_path / "ds.pdf"),
            storage_dir=str(tmp_path / "ds_storage"),
            total_pages=20,
            profile_id=profile.id,
        )
        proj_repo.save(project)

        # Create pages 1 to 6 with text
        for p in range(1, 7):
            page = Page(
                id=f"page-{p}",
                project_id=project.id,
                page_number=p,
                status=PageStatus.READY,
                source_text=f"This is section {p} describing replication and fault tolerance in chapter 1.",
                latest_translation=f"این بخش {p} درباره تکثیر داده‌ها و تحمل خطا در فصل ۱ است.",
                image_path=str(tmp_path / f"p{p}.png"),
                thumbnail_path=str(tmp_path / f"t{p}.png"),
            )
            page_repo.save(page)

        # Default chapter template
        default_tpl = ChapterPromptTemplate(
            name="پیش‌فرض تست",
            chunk_template="خلاصه کن: {content_text}",
            synthesis_template="ترکیب کن: {all_chunk_notes}",
            is_default=True,
        )
        tpl_repo.save(default_tpl)

        service = ChapterService(
            chapter_summary_repo=ch_repo,
            chapter_prompt_template_repo=tpl_repo,
            project_repo=proj_repo,
            page_repo=page_repo,
            profile_repo=prof_repo,
        )

        yield {
            "session": session,
            "service": service,
            "project": project,
            "ch_repo": ch_repo,
            "tpl_repo": tpl_repo,
        }


def test_create_chapter_summary_validations(chapter_test_env):
    service = chapter_test_env["service"]
    proj = chapter_test_env["project"]

    # 1. Valid creation
    dto = ChapterSummaryCreateDTO(
        chapter_title="Chapter 1: Foundations",
        start_page=1,
        end_page=5,
        source_type="source"
    )
    created = service.create_chapter_summary(proj.id, dto)
    assert created.id is not None
    assert created.status == "PENDING"
    assert created.start_page == 1
    assert created.end_page == 5

    # 2. Invalid start page > end page
    with pytest.raises(ValueError):
        service.create_chapter_summary(proj.id, ChapterSummaryCreateDTO(
            chapter_title="Bad",
            start_page=6,
            end_page=2
        ))

    # 3. Invalid end page > total pages
    with pytest.raises(ValueError):
        service.create_chapter_summary(proj.id, ChapterSummaryCreateDTO(
            chapter_title="Bad",
            start_page=1,
            end_page=50
        ))


@pytest.mark.asyncio
async def test_process_chapter_summary_map_reduce_flow(chapter_test_env):
    service = chapter_test_env["service"]
    proj = chapter_test_env["project"]

    dto = ChapterSummaryCreateDTO(
        chapter_title="Chapter 1: Replication",
        start_page=1,
        end_page=6,
        source_type="source"
    )
    created = service.create_chapter_summary(proj.id, dto)

    # Process background map-reduce
    await service.process_chapter_summary(created.id)

    # Verify completed state
    summary = service.get_chapter_summary(created.id)
    assert summary.status == "COMPLETED"
    assert summary.progress_percent == 100
    assert summary.final_summary is not None
    assert len(summary.final_summary) > 0
    assert summary.chunk_notes_json is not None


def test_export_chapter_summary_md_and_docx(chapter_test_env):
    service = chapter_test_env["service"]
    proj = chapter_test_env["project"]

    dto = ChapterSummaryCreateDTO(
        chapter_title="Chapter 1",
        start_page=1,
        end_page=3,
        source_type="source"
    )
    created = service.create_chapter_summary(proj.id, dto)

    # Manually populate final summary for export test
    service.update_chapter_summary(created.id, ChapterSummaryUpdateDTO(
        final_summary="# فصل اول\n\nاین یک خلاصه تستی است.\n\n- نکته ۱\n- نکته ۲"
    ))

    # Export MD
    md_path, md_mime = service.export_chapter_summary(created.id, "md")
    assert md_path.exists()
    assert md_mime == "text/markdown"
    assert "فصل اول" in md_path.read_text(encoding="utf-8")

    # Export DOCX
    docx_path, docx_mime = service.export_chapter_summary(created.id, "docx")
    assert docx_path.exists()
    assert docx_path.stat().st_size > 500


def test_chapter_prompt_templates_crud(chapter_test_env):
    service = chapter_test_env["service"]

    # 1. Create Template
    create_dto = ChapterPromptTemplateCreateDTO(
        name="قالب تستی",
        description="توضیح تستی",
        chunk_template="چانک: {content_text}",
        synthesis_template="سنتز: {all_chunk_notes}",
        is_default=False,
    )
    tpl = service.create_chapter_prompt_template(create_dto)
    assert tpl.id is not None
    assert tpl.name == "قالب تستی"

    # 2. List
    tpls = service.list_chapter_prompt_templates()
    assert len(tpls) >= 2

    # 3. Update
    updated = service.update_chapter_prompt_template(tpl.id, ChapterPromptTemplateUpdateDTO(
        name="نام جدید قالب"
    ))
    assert updated.name == "نام جدید قالب"

    # 4. Delete
    deleted = service.delete_chapter_prompt_template(tpl.id)


def test_detect_book_chapters_pdf_toc(chapter_test_env, tmp_path):
    import fitz
    service = chapter_test_env["service"]
    proj = chapter_test_env["project"]

    # Create dummy PDF with TOC outline
    pdf_path = tmp_path / "test_with_toc.pdf"
    doc = fitz.open()
    for _ in range(10):
        doc.new_page()
    doc.set_toc([
        [1, "Cover", 1],
        [1, "Chapter 1. Data Systems Basics", 3],
        [1, "Chapter 2. Advanced Replication", 7],
    ])
    doc.save(str(pdf_path))
    doc.close()

    proj.source_pdf_path = str(pdf_path)
    proj.total_pages = 10
    chapter_test_env["session"].add(proj)
    chapter_test_env["session"].commit()

    detected = service.detect_book_chapters(proj.id)
    assert len(detected) == 3
    # Cover
    assert detected[0].title == "Cover"
    assert detected[0].start_page == 1
    assert detected[0].end_page == 2
    assert detected[0].is_main_chapter is False

    # Chapter 1
    assert "Chapter 1" in detected[1].title
    assert detected[1].start_page == 3
    assert detected[1].end_page == 6
    assert detected[1].page_count == 4
    assert detected[1].is_main_chapter is True

    # Chapter 2
    assert "Chapter 2" in detected[2].title
    assert detected[2].start_page == 7
    assert detected[2].end_page == 10
    assert detected[2].page_count == 4


def test_strip_chapter_trailing_meta():
    from pdf_translator.application.chapter_service import strip_chapter_trailing_meta
    sample = """
# Chapter 1: Scalability
This is the core content of the chapter with deep technical architectural concepts.

## Summary
In summary, we discussed scalability and performance trade-offs.

## References
[1] Martin Kleppmann, Designing Data-Intensive Applications, 2017.
[2] Leslie Lamport, Time, Clocks, and the Ordering of Events in a Distributed System, 1978.
"""
    cleaned = strip_chapter_trailing_meta(sample)
    assert "deep technical architectural concepts" in cleaned
    assert "Summary" not in cleaned
    assert "scalability and performance trade-offs" not in cleaned
    assert "References" not in cleaned
    assert "Martin Kleppmann" not in cleaned
    assert "Leslie Lamport" not in cleaned

@pytest.mark.asyncio
async def test_resume_chapter_summary_skips_cached_chunks(chapter_test_env):
    import json
    service = chapter_test_env["service"]
    proj = chapter_test_env["project"]

    dto = ChapterSummaryCreateDTO(
        chapter_title="Chapter 1: Resume Test",
        start_page=1,
        end_page=4,
        source_type="source"
    )
    created = service.create_chapter_summary(proj.id, dto)

    # Simulate partial failure: section 1 was completed, then failed
    summary_obj = chapter_test_env["ch_repo"].get_by_id(created.id)
    summary_obj.status = "FAILED"
    summary_obj.chunk_notes_json = json.dumps([
        {
            "section_index": 1,
            "section_title": "Section 1 Already Done",
            "start_page": 1,
            "end_page": 2,
            "word_count": 250,
            "note": "نوت استخراج‌شده بخش ۱ از قبل"
        }
    ], ensure_ascii=False)
    chapter_test_env["ch_repo"].save(summary_obj)

    # Resume processing
    await service.process_chapter_summary(created.id, resume=True)

    resumed = service.get_chapter_summary(created.id)
    assert resumed.status == "COMPLETED"
    assert resumed.final_summary is not None
    assert len(resumed.final_summary) > 0

    # Verify pre-cached section was retained
    final_chunks = json.loads(resumed.chunk_notes_json)
    assert any(c.get("note") == "نوت استخراج‌شده بخش ۱ از قبل" for c in final_chunks)

@pytest.mark.asyncio
async def test_chunk_prompts_are_self_contained_across_all_sections(chapter_test_env):
    """Ensures chunk prompts for EVERY section (idx 0, 1, 2...) are fully self-contained."""
    service = chapter_test_env["service"]
    proj = chapter_test_env["project"]

    captured_prompts = []

    class CapturingProvider:
        async def translate(self, source_text, source_language, target_language, system_prompt="", **kwargs):
            captured_prompts.append(source_text)
            if "ترکیب کن" in source_text or "سند نوت‌برداری" in source_text:
                return "# سند جامع و نهایی فصل\n\n- تحلیل معماری نهایی"
            return f"نوت تحلیلی و تخصصی برای بخش: فرمول $x=1$ و اصطلاحات (Terms)."

    service._resolve_provider = lambda profile: CapturingProvider()

    # Configure pages with headings and substantial text so split_chapter_into_heading_sections yields multiple sections
    page_repo = chapter_test_env["session"].query(Page).all()
    for p in page_repo:
        p.source_text = f"# Section {p.page_number}: Technical Architecture\n\n" + ("This discusses distributed consensus and fault tolerance mechanisms in depth. " * 300)
        chapter_test_env["session"].add(p)
    chapter_test_env["session"].commit()

    dto = ChapterSummaryCreateDTO(
        chapter_title="Chapter 1: Distributed Systems",
        start_page=1,
        end_page=6,
        source_type="source"
    )
    created = service.create_chapter_summary(proj.id, dto)

    # Test with default prompt (no template_id) to verify <source_document> is used
    summary_record = chapter_test_env["ch_repo"].get_by_id(created.id)
    summary_record.prompt_template_id = None
    chapter_test_env["ch_repo"].save(summary_record)

    await service.process_chapter_summary(created.id, resume=False)
    assert len(captured_prompts) >= 2
    chunk_prompts = captured_prompts[:-1]

    for prompt in chunk_prompts:
        # Every prompt must be self-contained and NOT rely on 'مطابق با همان اصول و قوانین بالا'
        assert "مطابق با همان اصول و قوانین بالا" not in prompt
        assert "<source_document>" in prompt or "خلاصه کن:" in prompt
        assert "دستورالعمل" in prompt


@pytest.mark.asyncio
async def test_canned_acknowledgement_recovery(chapter_test_env):
    """Verifies that canned responses are detected and retried with reinforced direct prompt."""
    service = chapter_test_env["service"]
    proj = chapter_test_env["project"]

    call_count = 0

    class CannedThenSuccessProvider:
        async def translate(self, source_text, source_language, target_language, system_prompt="", **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call returns a canned filler response
                return "بله، آماده‌ام. لطفاً متن بخش بعدی را ارسال کنید."
            # Retry call returns real notes
            return "# نوت‌های بخش اول\n\n- مکانیزم تحمل خطا (Fault Tolerance) به صورت کامل تحلیل شد."

    service._resolve_provider = lambda profile: CannedThenSuccessProvider()

    dto = ChapterSummaryCreateDTO(
        chapter_title="Chapter 1: Canned Test",
        start_page=1,
        end_page=2,
        source_type="source"
    )
    created = service.create_chapter_summary(proj.id, dto)

    await service.process_chapter_summary(created.id, resume=False)

    summary = service.get_chapter_summary(created.id)
    assert summary.status == "COMPLETED"
    assert call_count >= 2
    chunks = json.loads(summary.chunk_notes_json)
    assert "تحمل خطا" in chunks[0]["note"]


@pytest.mark.asyncio
async def test_safe_insert_multiline_prompt_logic():
    """Tests that _safe_insert_multiline_prompt executes cleanly with Playwright mock/page."""
    from pdf_translator.adapters.providers.browser_manager import BrowserManager
    from unittest.mock import AsyncMock, MagicMock

    bm = BrowserManager.get_instance()
    mock_page = MagicMock()
    mock_page.context.grant_permissions = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value=True)
    mock_page.keyboard.insert_text = AsyncMock()

    multiline = "Line 1\nLine 2\n\nParagraph 2 with LaTeX"
    await bm._safe_insert_multiline_prompt(mock_page, multiline)

    # Verify evaluate was called and native CDP keyboard.insert_text received the entire text
    assert mock_page.evaluate.call_count >= 1
    mock_page.keyboard.insert_text.assert_awaited_with(multiline)

@pytest.mark.asyncio
async def test_submit_and_verify_prompt_presses_enter_when_button_disabled():
    """Ensures Enter is actively pressed when Send button is disabled, fixing stuck submissions."""
    from pdf_translator.adapters.providers.browser_manager import BrowserManager
    from unittest.mock import AsyncMock, MagicMock

    bm = BrowserManager.get_instance()
    mock_page = MagicMock()

    # Mock locator returns
    mock_editor = MagicMock()
    mock_editor.is_visible = AsyncMock(return_value=True)
    mock_editor.focus = AsyncMock()

    mock_send_btn = MagicMock()
    mock_send_btn.is_visible = AsyncMock(return_value=True)
    mock_send_btn.click = AsyncMock()

    mock_stop_btn = MagicMock()
    # Not visible on first check, visible on second check (generation started!)
    mock_stop_btn.is_visible = AsyncMock(side_effect=[False, True])

    def mock_locator(sel):
        loc = MagicMock()
        if "textarea" in sel or "contenteditable" in sel or "ProseMirror" in sel:
            loc.first = mock_editor
        elif "composer" in sel or "send" in sel or "Submit" in sel:
            loc.first = mock_send_btn
        elif "stop" in sel or "Stop" in sel or "توقف" in sel:
            loc.first = mock_stop_btn
        else:
            loc.first = MagicMock()
            loc.count = AsyncMock(return_value=0)
        return loc

    mock_page.locator = mock_locator
    # evaluate returns False for button enabled check (disabled send button)
    mock_page.evaluate = AsyncMock(return_value=False)
    mock_page.keyboard.press = AsyncMock()

    success = await bm._submit_and_verify_prompt(
        page=mock_page,
        provider_name="ChatGPT",
        editor_selector="#prompt-textarea",
        send_button_selector="button[data-testid='send-button']",
        stop_button_selector="button[data-testid='stop-button']",
        max_wait_seconds=3.0,
    )

    assert success is True
    # Verify editor was focused and Enter was pressed
    mock_editor.focus.assert_awaited()
    mock_page.keyboard.press.assert_awaited_with("Enter")


@pytest.mark.asyncio
async def test_submit_and_verify_prompt_clicks_enabled_button():
    """Ensures Send button is clicked directly when it is enabled and ready."""
    from pdf_translator.adapters.providers.browser_manager import BrowserManager
    from unittest.mock import AsyncMock, MagicMock

    bm = BrowserManager.get_instance()
    mock_page = MagicMock()

    mock_editor = MagicMock()
    mock_editor.is_visible = AsyncMock(return_value=True)

    mock_send_btn = MagicMock()
    mock_send_btn.is_visible = AsyncMock(return_value=True)
    mock_send_btn.click = AsyncMock()

    mock_stop_btn = MagicMock()
    mock_stop_btn.is_visible = AsyncMock(side_effect=[False, True])

    def mock_locator(sel):
        loc = MagicMock()
        if "textarea" in sel or "contenteditable" in sel:
            loc.first = mock_editor
        elif "composer" in sel or "send" in sel:
            loc.first = mock_send_btn
        elif "stop" in sel or "Stop" in sel:
            loc.first = mock_stop_btn
        else:
            loc.first = MagicMock()
            loc.count = AsyncMock(return_value=0)
        return loc

    mock_page.locator = mock_locator
    # evaluate returns True for button enabled check
    mock_page.evaluate = AsyncMock(return_value=True)

    success = await bm._submit_and_verify_prompt(
        page=mock_page,
        provider_name="ChatGPT",
        editor_selector="#prompt-textarea",
        send_button_selector="button[data-testid='send-button']",
        stop_button_selector="button[data-testid='stop-button']",
        max_wait_seconds=3.0,
    )

    assert success is True
    mock_send_btn.click.assert_awaited()


@pytest.mark.asyncio
async def test_submit_and_verify_prompt_fails_fast_when_unsubmitted():
    """Ensures RuntimeError is raised within seconds rather than hanging for 6 minutes."""
    from pdf_translator.adapters.providers.browser_manager import BrowserManager
    from unittest.mock import AsyncMock, MagicMock

    bm = BrowserManager.get_instance()
    mock_page = MagicMock()

    mock_editor = MagicMock()
    mock_editor.is_visible = AsyncMock(return_value=True)
    mock_editor.focus = AsyncMock()

    mock_send_btn = MagicMock()
    mock_send_btn.is_visible = AsyncMock(return_value=False)

    mock_stop_btn = MagicMock()
    mock_stop_btn.is_visible = AsyncMock(return_value=False)

    def mock_locator(sel):
        loc = MagicMock()
        if "textarea" in sel:
            loc.first = mock_editor
        elif "send" in sel:
            loc.first = mock_send_btn
        elif "stop" in sel:
            loc.first = mock_stop_btn
        else:
            loc.first = MagicMock()
            loc.count = AsyncMock(return_value=0)
        return loc

    mock_page.locator = mock_locator
    mock_page.evaluate = AsyncMock(return_value="some unsubmitted prompt text")
    mock_page.keyboard.press = AsyncMock()

    with pytest.raises(RuntimeError, match="ارسال پیام به Gemini با کلید Enter یا دکمه ارسال انجام نشد"):
        await bm._submit_and_verify_prompt(
            page=mock_page,
            provider_name="Gemini",
            editor_selector="textarea",
            send_button_selector="button.send",
            stop_button_selector="button.stop",
            max_wait_seconds=0.6,
        )


@pytest.mark.asyncio
async def test_chapter_processing_resets_thread_once_at_start(chapter_test_env):
    """Verifies reset_conversation_thread is called once at chapter start, NOT per chunk."""
    service = chapter_test_env["service"]
    proj = chapter_test_env["project"]

    reset_calls = []

    class MockManager:
        def reset_conversation_thread(self, provider_key="all"):
            reset_calls.append(provider_key)

    class ProviderWithManager:
        def __init__(self):
            self.manager = MockManager()

        async def translate(self, source_text, source_language, target_language, system_prompt="", **kwargs):
            if "سند نوت‌برداری" in source_text or "ترکیب کن" in source_text:
                return "# خلاصه نهایی"
            return "# نوت بخش\n\n- تحلیل عمیق مهندسی"

    service._resolve_provider = lambda profile: ProviderWithManager()

    # Create pages so split_chapter_into_heading_sections yields at least 3 sections
    for p_num in range(1, 7):
        p = service.page_repo.get_by_project_and_number(proj.id, p_num)
        p.source_text = f"# Section {p_num}\n\n" + ("Detailed technical description with architecture notes. " * 300)
        service.page_repo.save(p)

    dto = ChapterSummaryCreateDTO(
        chapter_title="Chapter Multi-Section Thread Test",
        start_page=1,
        end_page=6,
        source_type="source"
    )
    created = service.create_chapter_summary(proj.id, dto)

    await service.process_chapter_summary(created.id, resume=False)

    summary = service.get_chapter_summary(created.id)
    assert summary.status == "COMPLETED"
    # Must be called exactly once at chapter start (not 3+ times per section)
    assert len(reset_calls) == 1


def test_export_chapter_summary_with_partial_sections_before_final_summary(chapter_test_env):
    """Verifies that user can export MD and DOCX even when final_summary is not yet complete but sections are ready."""
    service = chapter_test_env["service"]
    proj = chapter_test_env["project"]

    dto = ChapterSummaryCreateDTO(
        chapter_title="Chapter In Progress",
        start_page=1,
        end_page=4,
        source_type="source"
    )
    created = service.create_chapter_summary(proj.id, dto)

    # Save intermediate chunk notes with NO final_summary
    summary_obj = service.chapter_summary_repo.get_by_id(created.id)
    summary_obj.status = "PROCESSING"
    summary_obj.chunk_notes_json = json.dumps([
        {
            "section_index": 1,
            "section_title": "مقدمه و معماری",
            "start_page": 1,
            "end_page": 2,
            "word_count": 500,
            "note": "این نوت بخش ۱ است که در حین پردازش استخراج شده است."
        },
        {
            "section_index": 2,
            "section_title": "الگوریتم اجماع",
            "start_page": 3,
            "end_page": 4,
            "word_count": 600,
            "note": "این نوت بخش ۲ است."
        }
    ], ensure_ascii=False)
    service.chapter_summary_repo.save(summary_obj)

    # Export MD - must succeed and include the section notes
    md_path, md_mime = service.export_chapter_summary(created.id, "md")
    assert md_path.exists()
    assert md_mime == "text/markdown"
    md_content = md_path.read_text(encoding="utf-8")
    assert "مقدمه و معماری" in md_content
    assert "الگوریتم اجماع" in md_content

    # Export DOCX - must succeed
    docx_path, docx_mime = service.export_chapter_summary(created.id, "docx")
    assert docx_path.exists()
    assert docx_path.stat().st_size > 500


@pytest.mark.asyncio
async def test_incremental_section_availability_during_processing(chapter_test_env):
    """Verifies that chunk_notes_json is progressively updated after each section, enabling immediate reading."""
    service = chapter_test_env["service"]
    proj = chapter_test_env["project"]

    observed_sections_count_during_run = []

    original_save = service.chapter_summary_repo.save
    def spy_save(summary_model):
        if summary_model.chunk_notes_json:
            try:
                parsed = json.loads(summary_model.chunk_notes_json)
                observed_sections_count_during_run.append(len(parsed))
            except Exception:
                pass
        return original_save(summary_model)

    service.chapter_summary_repo.save = spy_save

    # Create pages with 3 clear sections
    for p_num in range(1, 4):
        p = service.page_repo.get_by_project_and_number(proj.id, p_num)
        p.source_text = f"# Section {p_num}\n\n" + ("Deep technical content for architecture section. " * 200)
        service.page_repo.save(p)

    dto = ChapterSummaryCreateDTO(
        chapter_title="Chapter Incremental Test",
        start_page=1,
        end_page=3,
        source_type="source"
    )
    created = service.create_chapter_summary(proj.id, dto)

    await service.process_chapter_summary(created.id, resume=False)

    # Restore save
    service.chapter_summary_repo.save = original_save

    # Check that sections were saved incrementally: 1 section, then 2 sections, then 3 sections
    assert 1 in observed_sections_count_during_run
    assert 2 in observed_sections_count_during_run
    assert 3 in observed_sections_count_during_run

    # Final check
    final_summary = service.get_chapter_summary(created.id)
    assert final_summary.status == "COMPLETED"
    chunks = json.loads(final_summary.chunk_notes_json)
    assert len(chunks) == 3
