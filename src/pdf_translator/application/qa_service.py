"""Application service for In-Reading AI Assistant and Prompt Template management."""
from typing import List, Optional
from datetime import datetime

from pdf_translator.domain.entities import (
    PageConversation,
    PromptTemplate,
    Project,
    Page,
    TranslationProfile,
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
)
from pdf_translator.application.dtos import (
    PromptTemplateDTO,
    PromptTemplateCreateDTO,
    PromptTemplateUpdateDTO,
    PageConversationDTO,
    PageAskDTO,
)
from pdf_translator.adapters.providers.mock_provider import MockTranslationProvider
from pdf_translator.adapters.providers.openai_provider import OpenAIProvider
from pdf_translator.adapters.providers.gemini_provider import GeminiProvider
from pdf_translator.adapters.providers.claude_provider import ClaudeProvider
from pdf_translator.adapters.providers.browser_provider import BrowserTranslationProvider


class QAService:
    def __init__(
        self,
        prompt_template_repo: PromptTemplateRepositoryPort,
        page_conversation_repo: PageConversationRepositoryPort,
        page_repo: PageRepositoryPort,
        project_repo: ProjectRepositoryPort,
        profile_repo: ProfileRepositoryPort,
    ):
        self.prompt_template_repo = prompt_template_repo
        self.page_conversation_repo = page_conversation_repo
        self.page_repo = page_repo
        self.project_repo = project_repo
        self.profile_repo = profile_repo

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
        selected_text = (dto.selected_text or "").strip()
        if not selected_text:
            selected_text = "(کل صفحه / بدون هایلایت خاص)"

        # 2. Get prompt template
        template_obj = None
        if dto.prompt_template_id:
            template_obj = self.prompt_template_repo.get_by_id(dto.prompt_template_id)
        if not template_obj:
            template_obj = self.prompt_template_repo.get_default()

        if template_obj:
            prompt_raw = template_obj.template
            final_prompt = (
                prompt_raw
                .replace("{selected_text}", selected_text)
                .replace("{page_text}", page_text)
                .replace("{question}", dto.question.strip())
            )
        else:
            final_prompt = f"""متن مورد سوال:
\"\"\"
{selected_text}
\"\"\"

کانتکست صفحه:
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

        # 4. Execute AI generation
        answer = await provider.translate(
            source_text=final_prompt,
            source_language=project.source_language,
            target_language=project.target_language,
            system_prompt="شما یک دستیار هوشمند و منتور آموزشی برای مطالعه کتاب هستید.",
        )

        # 5. Save conversation record
        convo = PageConversation(
            project_id=project_id,
            page_number=page_number,
            selected_text=dto.selected_text if dto.selected_text else None,
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
