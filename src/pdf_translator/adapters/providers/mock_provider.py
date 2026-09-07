"""Mock translation provider for testing and offline development."""
import asyncio
from typing import List, Optional
from pdf_translator.domain.ports import TranslationProviderPort
from pdf_translator.domain.entities import GlossaryItem

class MockTranslationProvider(TranslationProviderPort):
    def __init__(self, delay_seconds: float = 0.05):
        self.delay_seconds = delay_seconds

    async def translate(
        self,
        source_text: str,
        source_language: str,
        target_language: str,
        system_prompt: str,
        glossary: Optional[List[GlossaryItem]] = None,
        context_notes: Optional[str] = None,
    ) -> str:
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)

        # Realistic mock translation logic
        lines = source_text.strip().split("\n")
        translated_lines = []
        for line in lines:
            if not line.strip():
                translated_lines.append("")
                continue
            if line.startswith("#"):
                translated_lines.append(f"{line} (ترجمه)")
            else:
                # Apply glossary if matches
                translated_line = f"ترجمه روان: {line}"
                if glossary:
                    for g in glossary:
                        if g.source_term.lower() in line.lower():
                            replacement = f"{g.target_term} ({g.source_term})" if g.include_parenthesis_english else g.target_term
                            translated_line = translated_line.replace(g.source_term, replacement)
                translated_lines.append(translated_line)

        return "\n".join(translated_lines)
