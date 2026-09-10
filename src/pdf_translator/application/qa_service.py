"""Application service for In-Reading AI Assistant and Prompt Template management."""
import re
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from pdf_translator.domain.entities import (
    PageConversation,
    PromptTemplate,
    Project,
    Page,
    TranslationProfile,
    ChapterConversation,
    ChapterSummary,
)
from pdf_translator.domain.enums import ProviderType
from pdf_translator.domain.errors import (
    PageNotFoundError,
    ProjectNotFoundError,
    TranslationProviderError,
)
from pdf_translator.domain.ports import (
    PageRepositoryPort,
    ProjectRepositoryPort,
    ProfileRepositoryPort,
    PromptTemplateRepositoryPort,
    PageConversationRepositoryPort,
    TranslationProviderPort,
    ChapterConversationRepositoryPort,
    ChapterSummaryRepositoryPort,
)
from pdf_translator.application.dtos import (
    PromptTemplateDTO,
    PromptTemplateCreateDTO,
    PromptTemplateUpdateDTO,
    PageConversationDTO,
    PageAskDTO,
    ChapterConversationDTO,
    ChapterAskDTO,
)
from pdf_translator.adapters.providers.mock_provider import MockTranslationProvider
from pdf_translator.adapters.providers.openai_provider import OpenAIProvider
from pdf_translator.adapters.providers.gemini_provider import GeminiProvider
from pdf_translator.adapters.providers.claude_provider import ClaudeProvider
from pdf_translator.adapters.providers.browser_provider import BrowserTranslationProvider
from pdf_translator.application.translation_service import (
    unmask_image_blocks,
    unmask_code_blocks,
)


class QAService:
    def __init__(
        self,
        prompt_template_repo: PromptTemplateRepositoryPort,
        page_conversation_repo: PageConversationRepositoryPort,
        page_repo: PageRepositoryPort,
        project_repo: ProjectRepositoryPort,
        profile_repo: ProfileRepositoryPort,
        chapter_conversation_repo: Optional[ChapterConversationRepositoryPort] = None,
        chapter_summary_repo: Optional[ChapterSummaryRepositoryPort] = None,
    ):
        self.prompt_template_repo = prompt_template_repo
        self.page_conversation_repo = page_conversation_repo
        self.page_repo = page_repo
        self.project_repo = project_repo
        self.profile_repo = profile_repo
        self.chapter_conversation_repo = chapter_conversation_repo
        self.chapter_summary_repo = chapter_summary_repo
    def _resolve_provider(self, profile: TranslationProfile) -> TranslationProviderPort:
        if profile.provider_type in {
            ProviderType.BROWSER_CHATGPT,
            ProviderType.BROWSER_GEMINI,
            ProviderType.BROWSER_CLAUDE,
        }:
            return BrowserTranslationProvider(profile.provider_type)
        elif profile.provider_type == ProviderType.OPENAI:
            if not profile.api_key:
                raise TranslationProviderError("OpenAI", "API key is missing in profile.")
            return OpenAIProvider(api_key=profile.api_key, model_name=profile.model_name, temperature=profile.temperature)
        elif profile.provider_type == ProviderType.GEMINI:
            if not profile.api_key:
                raise TranslationProviderError("Gemini", "API key is missing in profile.")
            return GeminiProvider(api_key=profile.api_key, model_name=profile.model_name, temperature=profile.temperature)
        elif profile.provider_type == ProviderType.CLAUDE:
            if not profile.api_key:
                raise TranslationProviderError("Claude", "API key is missing in profile.")
            return ClaudeProvider(api_key=profile.api_key, model_name=profile.model_name, temperature=profile.temperature)
        else:
            return MockTranslationProvider()

    def list_prompt_templates(self) -> List[PromptTemplateDTO]:
        templates = self.prompt_template_repo.list_all()
        return [
            PromptTemplateDTO(
                id=t.id,
                name=t.name,
                description=t.description,
                template=t.template,
                is_default=t.is_default,
                created_at=t.created_at,
                updated_at=t.updated_at,
            )
            for t in templates
        ]

    def create_prompt_template(self, dto: PromptTemplateCreateDTO) -> PromptTemplateDTO:
        template = PromptTemplate(
            name=dto.name,
            description=dto.description,
            template=dto.template,
            is_default=dto.is_default,
        )
        saved = self.prompt_template_repo.save(template)
        return PromptTemplateDTO(
            id=saved.id,
            name=saved.name,
            description=saved.description,
            template=saved.template,
            is_default=saved.is_default,
            created_at=saved.created_at,
            updated_at=saved.updated_at,
        )

    def update_prompt_template(self, template_id: str, dto: PromptTemplateUpdateDTO) -> PromptTemplateDTO:
        template = self.prompt_template_repo.get_by_id(template_id)
        if not template:
            raise ValueError(f"PromptTemplate {template_id} not found")

        if dto.name is not None:
            template.name = dto.name
        if dto.description is not None:
            template.description = dto.description
        if dto.template is not None:
            template.template = dto.template
        if dto.is_default is not None:
            template.is_default = dto.is_default
        template.updated_at = datetime.utcnow()

        saved = self.prompt_template_repo.save(template)
        return PromptTemplateDTO(
            id=saved.id,
            name=saved.name,
            description=saved.description,
            template=saved.template,
            is_default=saved.is_default,
            created_at=saved.created_at,
            updated_at=saved.updated_at,
        )

    def delete_prompt_template(self, template_id: str) -> bool:
        return self.prompt_template_repo.delete(template_id)

    def list_page_conversations(self, project_id: str, page_number: int) -> List[PageConversationDTO]:
        convos = self.page_conversation_repo.list_by_page(project_id, page_number)
        return [
            PageConversationDTO(
                id=c.id,
                project_id=c.project_id,
                page_number=c.page_number,
                selected_text=c.selected_text,
                question=c.question,
                answer=c.answer,
                prompt_template_id=c.prompt_template_id,
                created_at=c.created_at,
            )
            for c in convos
        ]

    def delete_page_conversation(self, conversation_id: str) -> bool:
        return self.page_conversation_repo.delete(conversation_id)

    async def ask_page_question(
        self,
        project_id: str,
        page_number: int,
        dto: PageAskDTO,
    ) -> PageConversationDTO:
        project = self.project_repo.get_by_id(project_id)
        if not project:
            raise ProjectNotFoundError(project_id)

        page = self.page_repo.get_by_project_and_number(project_id, page_number)
        if not page:
            raise PageNotFoundError(project_id, page_number)

        # 1. Determine the relevant text of this page for rich context
        page_text = (page.approved_text or page.latest_translation or page.source_text or "").strip()

        # Check for new highlight vs follow-up question
        has_new_highlight = bool(dto.selected_text and dto.selected_text.strip())
        selected_text = dto.selected_text.strip() if has_new_highlight else ""

        # Retrieve previous conversation history on this page for continuation context
        previous_convos = self.page_conversation_repo.list_by_page(project_id, page_number)
        history_text = ""
        if previous_convos:
            history_lines = []
            for c in previous_convos[-4:]:  # last 4 turns
                snippet_hint = f" (نقل‌قول مربوطه: «{c.selected_text[:60]}...»)" if c.selected_text else ""
                history_lines.append(f"کاربر: {c.question}{snippet_hint}\nپاسخ دستیار: {c.answer}")
            history_text = "\n\n".join(history_lines)

        # Collect image blocks from source text and translations
        image_blocks = []
        img_pattern = r'!\[[\s\S]*?\]\(.*?\)'
        for source_candidate in [page.source_text, page.latest_translation, page.approved_text]:
            if source_candidate:
                for block in re.findall(img_pattern, source_candidate):
                    if block not in image_blocks:
                        image_blocks.append(block)

        # If no explicit image blocks in text, check for embedded image files on disk
        if not image_blocks and project.storage_dir:
            images_dir = Path(project.storage_dir) / "images"
            if images_dir.exists():
                for f in sorted(images_dir.glob(f"page_{page_number}_img_*.png")):
                    m = re.search(r'_img_(\d+)\.png$', f.name)
                    if m:
                        i_idx = m.group(1)
                        img_tag = f"![Figure {i_idx}](/api/projects/{project_id}/pages/{page_number}/images/{i_idx})"
                        if img_tag not in image_blocks:
                            image_blocks.append(img_tag)

        # If page_text still contains unmasked tokens, resolve them for context
        if image_blocks and ("IMAGE_BLOCK" in page_text or "تصویر_بلوک" in page_text):
            page_text = unmask_image_blocks(page_text, image_blocks, page.source_text or "")

        # 2. Get prompt template
        template_obj = None
        if dto.prompt_template_id:
            template_obj = self.prompt_template_repo.get_by_id(dto.prompt_template_id)
        if not template_obj:
            template_obj = self.prompt_template_repo.get_default()

        if has_new_highlight:
            # Case A: User explicitly selected a new text snippet
            full_context = page_text
            if history_text:
                full_context += f"\n\nتاریخچه گفتگوی قبلی در این صفحه:\n\"\"\"\n{history_text}\n\"\"\""

            if template_obj:
                prompt_raw = template_obj.template
                final_prompt = (
                    prompt_raw
                    .replace("{selected_text}", selected_text)
                    .replace("{page_text}", full_context)
                    .replace("{question}", dto.question.strip())
                )
            else:
                final_prompt = f"""متن مورد سوال از کتاب:
\"\"\"
{selected_text}
\"\"\"

کانتکست صفحه:
\"\"\"
{full_context}
\"\"\"

سوال:
{dto.question.strip()}"""
        else:
            # Case B: Follow-up question (no new highlight) - do NOT inject old highlight
            full_context = page_text
            if history_text:
                full_context += f"\n\nتاریخچه گفتگوی قبلی در این صفحه (پاسخ باید در ادامه گفتگوی قبلی باشد):\n\"\"\"\n{history_text}\n\"\"\""

            if template_obj:
                prompt_raw = template_obj.template
                # Remove the {selected_text} block so no old or blank quote is injected
                prompt_clean = re.sub(
                    r'(?:\n|^)[^\n]*?(?:متن مورد سوال|کد یا متن مورد سوال|متن مورد سوال از کتاب)[^\n]*?\n*"""\s*\{selected_text\}\s*"""\n*',
                    '\n',
                    prompt_raw,
                    flags=re.IGNORECASE
                )
                prompt_clean = prompt_clean.replace("{selected_text}", "")
                final_prompt = (
                    prompt_clean
                    .replace("{page_text}", full_context)
                    .replace("{question}", dto.question.strip())
                )
            else:
                if history_text:
                    final_prompt = f"""کانتکست صفحه:
\"\"\"
{page_text}
\"\"\"

تاریخچه گفتگوی قبلی در این صفحه:
\"\"\"
{history_text}
\"\"\"

سوال جدید کاربر (در ادامه گفتگوی بالا):
{dto.question.strip()}"""
                else:
                    final_prompt = f"""کانتکست صفحه:
\"\"\"
{page_text}
\"\"\"

سوال:
{dto.question.strip()}"""
        # 3. Resolve profile & provider
        profile = None
        if project.profile_id:
            profile = self.profile_repo.get_by_id(project.profile_id)
        if not profile:
            profile = self.profile_repo.get_default()

        provider = self._resolve_provider(profile)

        # 4. Execute AI generation with explicit LaTeX and structure prompt
        system_prompt = (
            "شما یک دستیار هوشمند، دقیق و منتور آموزشی برای مطالعه کتاب هستید.\n"
            "- در صورت وجود تاریخچه گفتگوی قبلی، پاسخ را به صورت منسجم و در ادامه سوال و پاسخ‌های قبلی ارائه دهید و از تکرار مجدد مقدمات خودداری نمایید.\n"
            "- فرمول‌های ریاضی و علمی را حتماً با استانداردهای LaTeX بنویسید (برای فرمول‌های درون‌خطی از $...$ و برای فرمول‌های مستقل/بلوکی از $$...$$ استفاده کنید).\n"
            "- ساختار پاسخ را بسیار زیبا و خوانا با عناوین، بولت‌پوینت‌ها و بلوک‌های کد مناسب قالب‌بندی کنید.\n"
            "- در صورت ارجاع به تصاویر یا نمودارهای صفحه، از تگ‌های مارک‌داون تصویر موجود در کانتکست مانند ![نام تصویر](/api/projects/.../images/...) استفاده کنید."
        )

        answer = await provider.translate(
            source_text=final_prompt,
            source_language=project.source_language,
            target_language=project.target_language,
            system_prompt=system_prompt,
        )

        # 5. Restore/unmask images in AI answer if referenced as placeholders
        if image_blocks:
            answer = unmask_image_blocks(answer, image_blocks, page.source_text or "")

        # Fallback substitution for any remaining [[IMAGE_BLOCK_i]] patterns
        def _fallback_image_replace(match):
            idx_str = match.group(1)
            persian_to_eng = {"۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4", "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9"}
            eng_num = "".join(persian_to_eng.get(ch, ch) for ch in idx_str)
            try:
                val = int(eng_num)
                img_no = val + 1
            except ValueError:
                img_no = 1
            return f"\n\n![تصویر {img_no}](/api/projects/{project_id}/pages/{page_number}/images/{img_no})\n\n"

        answer = re.sub(
            r"`*\[\s*\[\s*[\u200e\u200f\u200c]*(?:IMAGE[\s\\_]+BLOCK|تصویر|تصویر_بلوک|عکس)[\s\\_]+([0-9۰-۹]+)[\u200e\u200f\u200c]*\s*\]\s*\]`*",
            _fallback_image_replace,
            answer,
            flags=re.IGNORECASE,
        )
        # 5. Save conversation record
        convo = PageConversation(
            project_id=project_id,
            page_number=page_number,
            selected_text=selected_text if has_new_highlight else None,
            question=dto.question.strip(),
            answer=answer.strip(),
            prompt_template_id=template_obj.id if template_obj else None,
        )
        saved = self.page_conversation_repo.save(convo)

        return PageConversationDTO(
            id=saved.id,
            project_id=saved.project_id,
            page_number=saved.page_number,
            selected_text=saved.selected_text,
            question=saved.question,
            answer=saved.answer,
            prompt_template_id=saved.prompt_template_id,
            created_at=saved.created_at,
        )

    def list_chapter_conversations(
        self,
        chapter_summary_id: str,
        section_index: Optional[int] = None
    ) -> List[ChapterConversationDTO]:
        if not self.chapter_conversation_repo:
            return []
        convos = self.chapter_conversation_repo.list_by_chapter(chapter_summary_id, section_index)
        return [
            ChapterConversationDTO(
                id=c.id,
                chapter_summary_id=c.chapter_summary_id,
                section_index=c.section_index,
                selected_text=c.selected_text,
                question=c.question,
                answer=c.answer,
                prompt_template_id=c.prompt_template_id,
                created_at=c.created_at,
            )
            for c in convos
        ]

    def delete_chapter_conversation(self, conversation_id: str) -> bool:
        if not self.chapter_conversation_repo:
            return False
        return self.chapter_conversation_repo.delete(conversation_id)

    async def ask_chapter_question(
        self,
        chapter_summary_id: str,
        dto: ChapterAskDTO,
    ) -> ChapterConversationDTO:
        if not self.chapter_summary_repo or not self.chapter_conversation_repo:
            raise ValueError("Chapter repositories not configured in QAService")

        summary = self.chapter_summary_repo.get_by_id(chapter_summary_id)
        if not summary:
            raise ValueError(f"Chapter summary {chapter_summary_id} not found")

        project = self.project_repo.get_by_id(summary.project_id)
        if not project:
            raise ProjectNotFoundError(summary.project_id)

        # 1. Determine relevant context from section notes
        sec_idx = dto.section_index if (dto.section_index is not None and dto.section_index > 0) else None
        context_title = summary.chapter_title
        context_body = ""

        if summary.chunk_notes_json:
            import json
            try:
                chunks = json.loads(summary.chunk_notes_json)
                if sec_idx is not None:
                    target_chunk = next((c for c in chunks if c.get("section_index") == sec_idx), None)
                    if target_chunk:
                        context_title = f"{summary.chapter_title} - بخش {sec_idx}: {target_chunk.get('section_title', '')} (صفحات {target_chunk.get('start_page')}-{target_chunk.get('end_page')})"
                        context_body = target_chunk.get("note", "")
                else:
                    context_title = f"{summary.chapter_title} (مجموع نوت‌های بخش‌ها)"
                    context_body = "\n\n---\n\n".join([
                        f"### بخش {c.get('section_index')}: {c.get('section_title')} (صفحات {c.get('start_page')}-{c.get('end_page')}):\n{c.get('note', '')}"
                        for c in chunks
                    ])
            except Exception:
                pass
        # Retrieve previous conversation history on this chapter note/section
        previous_convos = self.chapter_conversation_repo.list_by_chapter(chapter_summary_id, sec_idx)
        history_text = ""
        if previous_convos:
            history_lines = []
            for c in previous_convos[-4:]:
                snippet_hint = f" (نقل‌قول مربوطه: «{c.selected_text[:60]}...»)" if c.selected_text else ""
                history_lines.append(f"کاربر: {c.question}{snippet_hint}\nپاسخ دستیار: {c.answer}")
            history_text = "\n\n".join(history_lines)

        has_new_highlight = bool(dto.selected_text and dto.selected_text.strip())
        selected_text = dto.selected_text.strip() if has_new_highlight else ""

        full_context = f"موضوع: {context_title}\n\nمتن نوت و خلاصه فصل:\n{context_body}"
        if history_text:
            full_context += f"\n\nتاریخچه گفتگوی قبلی در این نوت:\n\"\"\"\n{history_text}\n\"\"\""

        # Template resolution
        template_obj = None
        if dto.prompt_template_id:
            template_obj = self.prompt_template_repo.get_by_id(dto.prompt_template_id)
        if not template_obj:
            template_obj = self.prompt_template_repo.get_default()

        if has_new_highlight:
            if template_obj:
                final_prompt = (
                    template_obj.template
                    .replace("{selected_text}", selected_text)
                    .replace("{page_text}", full_context)
                    .replace("{question}", dto.question.strip())
                )
            else:
                final_prompt = f"متن مورد سوال از نوت:\n\"\"\"\n{selected_text}\n\"\"\"\n\nکانتکست نوت فصل:\n\"\"\"\n{full_context}\n\"\"\"\n\nسوال:\n{dto.question.strip()}"
        else:
            if template_obj:
                prompt_clean = re.sub(
                    r'(?:\n|^)[^\n]*?(?:متن مورد سوال|کد یا متن مورد سوال|متن مورد سوال از کتاب)[^\n]*?\n*"""\s*\{selected_text\}\s*"""\n*',
                    '\n',
                    template_obj.template,
                    flags=re.IGNORECASE
                ).replace("{selected_text}", "")
                final_prompt = (
                    prompt_clean
                    .replace("{page_text}", full_context)
                    .replace("{question}", dto.question.strip())
                )
            else:
                final_prompt = f"کانتکست نوت فصل:\n\"\"\"\n{full_context}\n\"\"\"\n\nسوال:\n{dto.question.strip()}"

        # Resolve provider
        profile = None
        if project.profile_id:
            profile = self.profile_repo.get_by_id(project.profile_id)
        if not profile:
            profile = self.profile_repo.get_default()

        provider = self._resolve_provider(profile)

        system_instruction = (
            "شما دستیار هوشمند مطالعه و پژوهش هستید. پاسخ‌ها باید کاملاً ساختاریافته، دقیق، تحلیلی، عمیق و به زبان فارسی روان، خودمانی و شیوا ارائه شوند. "
            "فرمول‌های ریاضی، متغیرها و معادلات علمی حتماً باید در قالب استاندارد LaTeX بین $...$ (درون‌خطی) یا $$...$$ (بلوکی) نوشته شوند."
        )

        answer = await provider.translate(
            source_text=final_prompt,
            source_language=project.source_language,
            target_language="Persian",
            system_prompt=system_instruction,
        )

        convo = ChapterConversation(
            chapter_summary_id=chapter_summary_id,
            section_index=sec_idx,
            selected_text=selected_text if has_new_highlight else None,
            question=dto.question.strip(),
            answer=answer.strip(),
            prompt_template_id=template_obj.id if template_obj else None,
        )
        saved = self.chapter_conversation_repo.save(convo)

        return ChapterConversationDTO(
            id=saved.id,
            chapter_summary_id=saved.chapter_summary_id,
            section_index=saved.section_index,
            selected_text=saved.selected_text,
            question=saved.question,
            answer=saved.answer,
            prompt_template_id=saved.prompt_template_id,
            created_at=saved.created_at,
        )
