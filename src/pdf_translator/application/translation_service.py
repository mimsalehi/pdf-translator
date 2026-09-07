"""Application service for Translation execution, version history, and final approval."""
from typing import Optional, List
from datetime import datetime
from pdf_translator.domain.entities import Page, TranslationAttempt, TranslationProfile, GlossaryItem
from pdf_translator.domain.enums import PageStatus, ProviderType
from pdf_translator.domain.errors import (
    PageNotFoundError,
    ProjectNotFoundError,
    ProfileNotFoundError,
    InvalidStateTransitionError,
    TranslationProviderError,
)
from pdf_translator.domain.ports import (
    PageRepositoryPort,
    ProjectRepositoryPort,
    ProfileRepositoryPort,
    TranslationProviderPort,
)
from pdf_translator.adapters.providers.mock_provider import MockTranslationProvider
from pdf_translator.adapters.providers.openai_provider import OpenAIProvider
from pdf_translator.adapters.providers.gemini_provider import GeminiProvider
from pdf_translator.adapters.providers.claude_provider import ClaudeProvider
from pdf_translator.adapters.providers.browser_provider import BrowserTranslationProvider
import re

def mask_code_blocks(text: str):
    """
    Replaces all fenced code blocks (``` ... ```) with atomic placeholders [[CODE_BLOCK_i]].
    Returns the masked text and the list of pristine original code blocks.
    """
    code_blocks = []

    def replacer(match):
        idx = len(code_blocks)
        code_blocks.append(match.group(0))
        return f"\n\n[[CODE_BLOCK_{idx}]]\n\n"

    pattern = r'```[a-zA-Z0-9_-]*\n[\s\S]*?```'
    masked_text = re.sub(pattern, replacer, text)
    return masked_text, code_blocks

def unmask_code_blocks(translated_text: str, code_blocks: list) -> str:
    """
    Restores original pristine code blocks verbatim into the translated text.
    Handles escaped underscores (\_), Persian digits, zero-width spaces, LRM/RLM marks, and bracket variations.
    """
    if not code_blocks:
        return translated_text

    result = translated_text
    persian_to_eng = {"۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4", "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9"}

    for idx, original_block in enumerate(code_blocks):
        # 1. Direct match
        token_standard = f"[[CODE_BLOCK_{idx}]]"
        if token_standard in result:
            result = result.replace(token_standard, original_block)
            continue

        # 2. Match regex patterns including markdown-escaped underscores (\_), Persian digits, bidi characters, etc.
        persian_idx = "".join(list(persian_to_eng.keys())[list(persian_to_eng.values()).index(d)] for d in str(idx))
        idx_pattern = f"(?:{idx}|{persian_idx})"

        patterns = [
            rf"`*\[\s*\[\s*[\u200e\u200f\u200c]*CODE[\s\\_]+BLOCK[\s\\_]+{idx_pattern}[\u200e\u200f\u200c]*\s*\]\s*\]`*",
            rf"`*\[\s*[\u200e\u200f\u200c]*CODE[\s\\_]+BLOCK[\s\\_]+{idx_pattern}[\u200e\u200f\u200c]*\s*\]`*",
            rf"```[a-zA-Z0-9_-]*\s*\[\s*\[\s*CODE[\s\\_]+BLOCK[\s\\_]+{idx_pattern}\s*\]\s*\]\s*```",
            rf"`*\[\s*\[\s*(?:بلوک_کد|کد)[\s\\_]+{idx_pattern}\s*\]\s*\]`*",
            rf"\bCODE[\s\\_]+BLOCK[\s\\_]+{idx_pattern}\b",
        ]

        replaced = False
        for pat in patterns:
            if re.search(pat, result, flags=re.IGNORECASE):
                result = re.sub(pat, lambda _: original_block, result, count=1, flags=re.IGNORECASE)
                replaced = True
                break

        if not replaced and len(code_blocks) == 1:
            result = result.rstrip() + "\n\n" + original_block

    # Clean any leftover or unreplaced placeholder tokens from text
    result = re.sub(r"`*\[\s*\[\s*[\u200e\u200f\u200c]*CODE[\s\\_]+BLOCK[\s\\_]+[0-9۰-۹]+[\u200e\u200f\u200c]*\s*\]\s*\]`*\n*", "", result, flags=re.IGNORECASE)
    return result.strip()

def mask_image_blocks(text: str):
    """
    Replaces all markdown image tags (![...](...)) with atomic placeholders [[IMAGE_BLOCK_i]].
    Returns the masked text and the list of pristine original image tags.
    """
    image_blocks = []

    def replacer(match):
        idx = len(image_blocks)
        image_blocks.append(match.group(0))
        return f"\n\n[[IMAGE_BLOCK_{idx}]]\n\n"

    pattern = r'!\[[\s\S]*?\]\(.*?\)'
    masked_text = re.sub(pattern, replacer, text)
    return masked_text, image_blocks

def unmask_image_blocks(translated_text: str, image_blocks: list, original_source_text: str = "") -> str:
    """
    Restores original pristine image tags verbatim into the translated text.
    Handles escaped underscores, Persian digits, bidi characters, and contextual fallbacks.
    """
    if not image_blocks:
        return translated_text

    result = translated_text
    persian_to_eng = {"۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4", "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9"}

    for idx, original_block in enumerate(image_blocks):
        # 1. Direct match
        token_standard = f"[[IMAGE_BLOCK_{idx}]]"
        if token_standard in result:
            result = result.replace(token_standard, original_block)
            continue

        # 2. Match regex variations
        persian_idx = "".join(list(persian_to_eng.keys())[list(persian_to_eng.values()).index(d)] for d in str(idx))
        idx_pattern = f"(?:{idx}|{persian_idx})"

        patterns = [
            rf"`*\[\s*\[\s*[\u200e\u200f\u200c]*IMAGE[\s\\_]+BLOCK[\s\\_]+{idx_pattern}[\u200e\u200f\u200c]*\s*\]\s*\]`*",
            rf"`*\[\s*[\u200e\u200f\u200c]*IMAGE[\s\\_]+BLOCK[\s\\_]+{idx_pattern}[\u200e\u200f\u200c]*\s*\]`*",
            rf"`*\[\s*\[\s*(?:تصویر|تصویر_بلوک|عکس)[\s\\_]+{idx_pattern}\s*\]\s*\]`*",
            rf"\bIMAGE[\s\\_]+BLOCK[\s\\_]+{idx_pattern}\b",
        ]

        replaced = False
        for pat in patterns:
            if re.search(pat, result, flags=re.IGNORECASE):
                result = re.sub(pat, lambda _: original_block, result, count=1, flags=re.IGNORECASE)
                replaced = True
                break

        # 3. Fallback: If AI dropped the placeholder token completely, restore based on context
        if not replaced:
            # Check if source text started with this image block (common case: image at top of page)
            if original_source_text and original_source_text.strip().startswith(original_block):
                result = original_block + "\n\n" + result.lstrip()
                replaced = True
            # Or check if there is a figure caption (e.g. ### شکل or ### Figure) to place it right before
            elif re.search(r'(#{1,4}\s*(?:شکل|تصویر|نمودار|Figure|Diagram)\s*\d+)', result, re.IGNORECASE):
                result = re.sub(r'(#{1,4}\s*(?:شکل|تصویر|نمودار|Figure|Diagram)\s*\d+)', f"{original_block}\n\n\\1", result, count=1, flags=re.IGNORECASE)
                replaced = True
            elif len(image_blocks) == 1:
                if original_source_text and original_source_text.find(original_block) < len(original_source_text) / 2:
                    result = original_block + "\n\n" + result.lstrip()
                else:
                    result = result.rstrip() + "\n\n" + original_block

    # Clean any leftover or unreplaced placeholder tokens from text
    result = re.sub(r"`*\[\s*\[\s*[\u200e\u200f\u200c]*IMAGE[\s\\_]+BLOCK[\s\\_]+[0-9۰-۹]+[\u200e\u200f\u200c]*\s*\]\s*\]`*\n*", "", result, flags=re.IGNORECASE)
    return result.strip()

def is_pure_code_or_media_page(text: str) -> bool:
    """
    Returns True if the page contains ONLY code blocks, image tags, horizontal rules,
    and whitespace, with no translatable human text.
    """
    # 1. Strip fenced code blocks
    cleaned = re.sub(r"```[a-zA-Z0-9_-]*\n[\s\S]*?```", "", text)
    # 2. Strip images: ![...](...)
    cleaned = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", cleaned)
    # 3. Strip horizontal dividers
    cleaned = re.sub(r"^[ \t]*[-*_]{3,}[ \t]*$", "", cleaned, flags=re.MULTILINE)
    # 4. Check if any meaningful words/letters remain (English or other alphabets)
    meaningful_text = re.sub(r"[\s\d\.,:;!?\"'\(\)\[\]\{\}\-_/\\|><+=*&^%$#@~`]+", "", cleaned)
    return len(meaningful_text.strip()) == 0

class TranslationService:
    def __init__(
        self,
        page_repo: PageRepositoryPort,
        project_repo: ProjectRepositoryPort,
        profile_repo: ProfileRepositoryPort,
    ):
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
                raise TranslationProviderError("OpenAI", "API key is missing in translation profile.")
            return OpenAIProvider(api_key=profile.api_key, model_name=profile.model_name, temperature=profile.temperature)
        
        elif profile.provider_type == ProviderType.GEMINI:
            if not profile.api_key:
                raise TranslationProviderError("Gemini", "API key is missing in translation profile.")
            return GeminiProvider(api_key=profile.api_key, model_name=profile.model_name, temperature=profile.temperature)
        
        elif profile.provider_type == ProviderType.CLAUDE:
            if not profile.api_key:
                raise TranslationProviderError("Claude", "API key is missing in translation profile.")
            return ClaudeProvider(api_key=profile.api_key, model_name=profile.model_name, temperature=profile.temperature)
        
        else:
            return MockTranslationProvider()

    async def translate_page(
        self,
        project_id: str,
        page_number: int,
        custom_instructions: Optional[str] = None
    ) -> TranslationAttempt:
        """Executes AI translation for a page."""
        project = self.project_repo.get_by_id(project_id)
        if not project:
            raise ProjectNotFoundError(project_id)

        page = self.page_repo.get_by_project_and_number(project_id, page_number)
        if not page:
            raise PageNotFoundError(project_id, page_number)

        # Get profile
        profile = None
        if project.profile_id:
            profile = self.profile_repo.get_by_id(project.profile_id)
        if not profile:
            profile = self.profile_repo.get_default()

        if not page.source_text.strip():
            raise TranslationProviderError("Engine", "Page source text is empty. Nothing to translate.")

        # If page consists entirely of code blocks, images, or media, bypass AI and pass through instantly
        if is_pure_code_or_media_page(page.source_text):
            translated_result = page.source_text.strip()
            existing_attempts = self.page_repo.list_attempts(page.id)
            version_num = len(existing_attempts) + 1

            attempt = TranslationAttempt(
                page_id=page.id,
                project_id=project.id,
                page_number=page.page_number,
                version_number=version_num,
                provider_name="INSTANT_PASSTHROUGH (Code/Media Only)",
                model_name="N/A",
                prompt_used="Instant pass-through (Page contains only code/media, no translatable text).",
                raw_response=translated_result,
                edited_text=translated_result,
                is_approved=False,
            )
            saved_attempt = self.page_repo.save_attempt(attempt)

            # Update page state to IN_REVIEW
            page.latest_translation = translated_result
            page.status = PageStatus.IN_REVIEW
            page.updated_at = datetime.utcnow()
            self.page_repo.save(page)

            return saved_attempt

        # Update status to TRANSLATING
        page.status = PageStatus.TRANSLATING
        page.updated_at = datetime.utcnow()
        self.page_repo.save(page)

        # Fetch adjacent page boundary context for natural cross-page sentence flow
        boundary_context_parts = []
        if page_number > 1:
            prev_page = self.page_repo.get_by_project_and_number(project_id, page_number - 1)
            if prev_page and prev_page.source_text:
                prev_snippet = prev_page.source_text.strip().split("\n")[-1][-160:]
                boundary_context_parts.append(f"- Previous page ends with: '... {prev_snippet}'")

        next_page = self.page_repo.get_by_project_and_number(project_id, page_number + 1)
        if next_page and next_page.source_text:
            next_snippet = next_page.source_text.strip().split("\n")[0][:160]
            boundary_context_parts.append(f"- Next page starts with: '{next_snippet} ...'")

        boundary_notes = ""
        if boundary_context_parts:
            boundary_notes = (
                "Adjacent Page Boundary Context:\n"
                + "\n".join(boundary_context_parts)
                + "\nRule: If a sentence is split across page boundaries, ensure the translation maintains natural Persian fluency without leaving meaningless incomplete fragments. Translate ONLY the current page's content."
            )
        
        # 1. Mask code blocks and image blocks so AI never modifies, translates, or drops them
        masked_source_text, code_blocks = mask_code_blocks(page.source_text)
        masked_source_text, image_blocks = mask_image_blocks(masked_source_text)

        code_notes = ""
        if code_blocks:
            code_notes = (
                "\n\nقانون حیاتی برای بلوک‌های کد:\n"
                "تگ‌های [[CODE_BLOCK_0]]، [[CODE_BLOCK_1]] و غیره جایگاه بلوک‌های کد برنامه‌نویسی هستند. "
                "این تگ‌ها را دقیقاً با همان فرمت و بدون هیچ‌گونه ترجمه، تغییر، جا‌به‌جایی یا حذف، در همان موقعیت میان پاراگراف‌ها قرار دهید."
            )

        image_notes = ""
        if image_blocks:
            image_notes = (
                "\n\nقانون حیاتی برای تصاویر، نمودارها و دیاگرام‌ها:\n"
                "تگ‌های [[IMAGE_BLOCK_0]]، [[IMAGE_BLOCK_1]] و غیره جایگاه تصاویر، دیاگرام‌ها و نمودارهای صفحه هستند. "
                "این تگ‌ها را دقیقاً با همان فرمت و بدون هیچ‌گونه ترجمه، تغییر، جا‌به‌جایی یا حذف، دقیقاً در همان موقعیت میان پاراگراف‌ها یا بالای عناوین شکل‌ها حفظ کنید."
            )

        combined_notes = boundary_notes + code_notes + image_notes
        if custom_instructions:
            combined_notes += f"\n\nAdditional Instructions: {custom_instructions}"

        provider = self._resolve_provider(profile)
        
        try:
            raw_translated_result = await provider.translate(
                source_text=masked_source_text,
                source_language=project.source_language,
                target_language=project.target_language,
                system_prompt=profile.system_prompt,
                glossary=[],
                context_notes=combined_notes,
            )
            # 2. Restore 100% untouched original code blocks and image blocks
            translated_result = unmask_code_blocks(raw_translated_result, code_blocks)
            translated_result = unmask_image_blocks(translated_result, image_blocks, page.source_text)
        except Exception as e:
            page.status = PageStatus.FAILED
            page.updated_at = datetime.utcnow()
            self.page_repo.save(page)
            raise e

        # Calculate version number
        existing_attempts = self.page_repo.list_attempts(page.id)
        version_num = len(existing_attempts) + 1

        attempt = TranslationAttempt(
            page_id=page.id,
            project_id=project.id,
            page_number=page.page_number,
            version_number=version_num,
            provider_name=profile.provider_type.value,
            model_name=profile.model_name,
            prompt_used=profile.system_prompt,
            raw_response=translated_result,
            edited_text=translated_result,
            is_approved=False,
        )
        saved_attempt = self.page_repo.save_attempt(attempt)

        # Update page state to IN_REVIEW
        page.latest_translation = translated_result
        page.status = PageStatus.IN_REVIEW
        page.updated_at = datetime.utcnow()
        self.page_repo.save(page)

        return saved_attempt

    def save_draft_edit(self, project_id: str, page_number: int, draft_text: str) -> Page:
        page = self.page_repo.get_by_project_and_number(project_id, page_number)
        if not page:
            raise PageNotFoundError(project_id, page_number)

        page.latest_translation = draft_text
        page.updated_at = datetime.utcnow()
        return self.page_repo.save(page)

    def approve_final_translation(self, project_id: str, page_number: int, final_text: str) -> Page:
        page = self.page_repo.get_by_project_and_number(project_id, page_number)
        if not page:
            raise PageNotFoundError(project_id, page_number)

        page.approved_text = final_text.strip()
        page.status = PageStatus.APPROVED
        page.updated_at = datetime.utcnow()
        saved_page = self.page_repo.save(page)

        # Mark latest attempt as approved
        attempts = self.page_repo.list_attempts(page.id)
        if attempts:
            latest = attempts[0]
            latest.edited_text = final_text.strip()
            latest.is_approved = True
            self.page_repo.save_attempt(latest)

        return saved_page
