"""Browser Automation Translation Provider implementing TranslationProviderPort."""
from typing import List, Optional
from pdf_translator.domain.ports import TranslationProviderPort
from pdf_translator.domain.entities import GlossaryItem
from pdf_translator.domain.enums import ProviderType
from pdf_translator.domain.errors import TranslationProviderError
from pdf_translator.adapters.providers.base import build_translation_prompt
from pdf_translator.adapters.providers.browser_manager import BrowserManager

class BrowserTranslationProvider(TranslationProviderPort):
    def __init__(self, provider_type: ProviderType, session_tag: str = "default"):
        self.provider_type = provider_type
        self.session_tag = session_tag
        self.manager = BrowserManager.get_instance()
    async def translate(
        self,
        source_text: str,
        source_language: str,
        target_language: str,
        system_prompt: str,
        glossary: Optional[List[GlossaryItem]] = None,
        context_notes: Optional[str] = None,
    ) -> str:
        prompt = build_translation_prompt(
            source_text=source_text,
            source_language=source_language,
            target_language=target_language,
            system_prompt=system_prompt,
            glossary=glossary,
            context_notes=context_notes,
        )

        try:
            if self.provider_type == ProviderType.BROWSER_CHATGPT:
                return await self.manager.translate_with_chatgpt(prompt, session_tag=self.session_tag)
            elif self.provider_type == ProviderType.BROWSER_GEMINI:
                return await self.manager.translate_with_gemini(prompt, session_tag=self.session_tag)
            elif self.provider_type == ProviderType.BROWSER_CLAUDE:
                return await self.manager.translate_with_claude(prompt, session_tag=self.session_tag)
            else:
                return await self.manager.translate_with_chatgpt(prompt, session_tag=self.session_tag)
        except Exception as e:
            raise TranslationProviderError(f"Browser ({self.provider_type.value})", str(e))
