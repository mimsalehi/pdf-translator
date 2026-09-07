"""Google Gemini API Translation Provider."""
import httpx
from typing import List, Optional
from pdf_translator.domain.ports import TranslationProviderPort
from pdf_translator.domain.entities import GlossaryItem
from pdf_translator.domain.errors import TranslationProviderError
from pdf_translator.adapters.providers.base import build_translation_prompt

class GeminiProvider(TranslationProviderPort):
    def __init__(self, api_key: str, model_name: str = "gemini-1.5-pro", temperature: float = 0.3):
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

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": self.temperature,
            },
        }

        async with httpx.AsyncClient(timeout=90.0) as client:
            try:
                response = await client.post(url, json=payload)
                if response.status_code != 200:
                    raise TranslationProviderError("Gemini", f"HTTP {response.status_code}: {response.text}")
                
                data = response.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    raise TranslationProviderError("Gemini", "No response candidates returned.")
                return candidates[0]["content"]["parts"][0]["text"].strip()
            except Exception as e:
                raise TranslationProviderError("Gemini", str(e))
