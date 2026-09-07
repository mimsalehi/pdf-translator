"""OpenAI API Translation Provider."""
import httpx
from typing import List, Optional
from pdf_translator.domain.ports import TranslationProviderPort
from pdf_translator.domain.entities import GlossaryItem
from pdf_translator.domain.errors import TranslationProviderError
from pdf_translator.adapters.providers.base import build_translation_prompt

class OpenAIProvider(TranslationProviderPort):
    def __init__(self, api_key: str, model_name: str = "gpt-4o", temperature: float = 0.3):
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
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model_name,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        }

        async with httpx.AsyncClient(timeout=90.0) as client:
            try:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )
                if response.status_code != 200:
                    raise TranslationProviderError("OpenAI", f"HTTP {response.status_code}: {response.text}")
                
                data = response.json()
                return data["choices"][0]["message"]["content"].strip()
            except Exception as e:
                raise TranslationProviderError("OpenAI", str(e))
