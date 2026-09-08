"""Base utilities and prompt construction for Translation Providers."""
from typing import List, Optional
from pdf_translator.domain.entities import GlossaryItem

def build_translation_prompt(
    source_text: str,
    source_language: str,
    target_language: str,
    system_prompt: str,
    glossary: Optional[List[GlossaryItem]] = None,
    context_notes: Optional[str] = None,
) -> str:
    """Builds a structured prompt adhering to ADR translation principles."""
    clean_sys_prompt = (system_prompt or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    clean_source = (source_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()

    # If system_prompt is empty, source_text is already a complete standalone prompt; return it directly
    if not clean_sys_prompt:
        return clean_source

    glossary_section = ""
    if glossary and len(glossary) > 0:
        glossary_lines = []
        for g in glossary:
            rule = f"- '{g.source_term}' → '{g.target_term}'"
            if g.include_parenthesis_english:
                rule += f" (در صورت لزوم با ذکر انگلیسی در پرانتز: {g.target_term} ({g.source_term}))"
            glossary_lines.append(rule)
        glossary_section = "\n\n### واژه‌نامه تخصصی (Glossary) که باید رعایت شود:\n" + "\n".join(glossary_lines)

    context_section = ""
    if context_notes:
        clean_context = context_notes.replace("\r\n", "\n").replace("\r", "\n").strip()
        context_section = f"\n\n### بافت و زمینه صفحات قبلی:\n{clean_context}"

    prompt = f"""{clean_sys_prompt}

زبان مبدأ: {source_language}
زبان مقصد: {target_language}
{glossary_section}
{context_section}

متن ورودی جهت ترجمه:
<source_document>
{clean_source}
</source_document>

ترجمه نهایی (فقط متن ترجمه شده را با همان ساختار دقیق مارک‌داون، حفظ کامل تگ‌های تصاویر و حفظ ۱۰۰٪ دست‌نخورده کدهای درون ``` خروجی دهید. بدون هیچ‌گونه مقدمه، نتیجه‌گیری یا توضیحات اضافی):
"""
    return prompt.replace("\r\n", "\n").replace("\r", "\n")
