"""Anthropic Claude API Translation Provider."""
import httpx
from typing import List, Optional
from pdf_translator.domain.ports import TranslationProviderPort
from pdf_translator.domain.entities import GlossaryItem
from pdf_translator.domain.errors import TranslationProviderError
from pdf_translator.adapters.providers.base import build_translation_prompt

class ClaudeProvider(TranslationProviderPort):
    def __init__(self, api_key: str, model_name: str = "claude-3-5-sonnet-20241022", temperature: float = 0.3):
        self.api_key = api_key
        self.model_name = model_name
        self.temperature = temperature

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

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": self.model_name,
            "max_tokens": 4096,
            "temperature": self.temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": prompt}],
        }

        async with httpx.AsyncClient(timeout=90.0) as client:
            try:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=payload,
                )
                if response.status_code != 200:
                    raise TranslationProviderError("Claude", f"HTTP {response.status_code}: {response.text}")
                
                data = response.json()
                return data["content"][0]["text"].strip()
            except Exception as e:
                raise TranslationProviderError("Claude", str(e))
