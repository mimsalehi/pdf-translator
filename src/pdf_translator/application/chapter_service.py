"""Application service for Chapter Summarization and Deep Note-Taking."""
import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from pdf_translator.domain.entities import (
    ChapterSummary,
    ChapterPromptTemplate,
    Project,
    Page,
    TranslationProfile,
)
from pdf_translator.domain.enums import ProviderType
from pdf_translator.domain.errors import (
    ProjectNotFoundError,
)
from pdf_translator.application.persian_cleanup import clean_markdown_persian
from pdf_translator.domain.ports import (
    ChapterSummaryRepositoryPort,
    ChapterPromptTemplateRepositoryPort,
    ProjectRepositoryPort,
    PageRepositoryPort,
    ProfileRepositoryPort,
    PDFExtractorPort,
    TranslationProviderPort,
)
from pdf_translator.application.dtos import (
    ChapterSummaryDTO,
    ChapterSummaryCreateDTO,
    ChapterSummaryUpdateDTO,
    ChapterPromptTemplateDTO,
    ChapterPromptTemplateCreateDTO,
    ChapterPromptTemplateUpdateDTO,
    DetectedChapterDTO,
)
from pdf_translator.adapters.providers.mock_provider import MockTranslationProvider
from pdf_translator.adapters.providers.openai_provider import OpenAIProvider
from pdf_translator.adapters.providers.gemini_provider import GeminiProvider
from pdf_translator.adapters.providers.claude_provider import ClaudeProvider
from pdf_translator.adapters.providers.browser_provider import BrowserTranslationProvider
from pdf_translator.adapters.pdf.pymupdf_extractor import PyMuPDFExtractor
from pdf_translator.adapters.export.docx_exporter import render_markdown_paragraph_to_docx
from docx import Document


def strip_chapter_trailing_meta(text: str) -> str:
    """
    Removes author's end-of-chapter Summary, Conclusion, References, and Bibliography.
    The note-taking pipeline should ONLY process the actual technical body of the chapter,
    never the author's 1-page summary rehash or bibliography lists.
    """
    trailing_pattern = (
        r'(?:\n|^)\s*#{1,3}\s*(?:'
        r'Summary|Chapter\s+Summary|Concluding\s+Remarks|Conclusion|In\s+Summary|'
        r'References|Bibliography|Further\s+Reading|Works\s+Cited|Suggested\s+Reading|'
        r'خلاصه\s+فصل|خلاصه|جمع‌بندی|نتیجه‌گیری|منابع|مراجع|منابع\s+و\s+مآخذ'
        r')\b[\s\S]*$'
    )
    cleaned = re.sub(trailing_pattern, '', text, flags=re.IGNORECASE).strip()
    # Strip unheaded citation blocks at the very end (e.g. [1] ..., [2] ...)
    cleaned = re.sub(r'(?:\n\s*\[\d+\][^\n]+){3,}\s*$', '', cleaned).strip()
    return cleaned

def is_canned_acknowledgement(text: str) -> bool:
    """Detects conversational bot filler (e.g. 'بله بفرستید', 'آماده‌ام') that is not actual notes."""
    clean = (text or "").strip()
    if len(clean) < 320 and re.search(
        r'(?:بله|آماده[‌\s]?ام|ارسال کنید|بفرستید|متن بخش بعدی|در خدمتم|رویکرد|بخش موردنظر|متن را ارسال)',
        clean,
        re.I
    ):
        return True
    return False


def split_chapter_into_heading_sections(page_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Splits chapter pages by Heading 1 (#) or groups of Heading 2 (##):
    1. Truncates any References/Bibliography section from chapter end.
    2. Identifies all Markdown headings (# and ##).
    3. Groups small subsections logically (~400 to ~2600 words per section).
    """
    if not page_items:
        return []

    # Combine pages with page markers to track page boundaries per section
    full_text_blocks = []
    for item in page_items:
        p_num = item["page_number"]
        txt = item["text"]
        full_text_blocks.append(f"<!-- PAGE_{p_num} -->\n{txt}")

    combined = "\n\n".join(full_text_blocks)
    combined = strip_chapter_trailing_meta(combined)

    # Split by lines starting with # or ##
    heading_pattern = r'(?:\n|^)(#{1,2}\s+[^\n]+)'
    parts = re.split(heading_pattern, combined)

    raw_sections = []
    intro_text = parts[0].strip()
    if intro_text:
        clean_intro = re.sub(r'<!-- PAGE_\d+ -->\n*', '', intro_text).strip()
        if len(clean_intro.split()) > 20:
            raw_sections.append({
                "title": "مقدمه و پیش‌زمینه فصل (Introduction)",
                "level": 1,
                "text": intro_text
            })

    i = 1
    while i < len(parts):
        heading_line = parts[i].strip()
        body_text = parts[i + 1].strip() if i + 1 < len(parts) else ""
        level = 1 if heading_line.startswith("# ") else 2
        title = re.sub(r'^#{1,2}\s+', '', heading_line).strip()
        full_section_text = f"{heading_line}\n\n{body_text}".strip()

        raw_sections.append({
            "title": title,
            "level": level,
            "text": full_section_text
        })
        i += 2

    # Fallback if no headings found in the text: fallback to ~4 page slices
    if not raw_sections:
        chunks = []
        cur_pages, cur_text, cur_words = [], [], 0
        for item in page_items:
            words = len(item["text"].split())
            if cur_pages and (len(cur_pages) >= 4 or cur_words + words > 3000):
                chunks.append({
                    "section_index": len(chunks) + 1,
                    "section_title": f"صفحات {cur_pages[0]} الی {cur_pages[-1]}",
                    "start_page": cur_pages[0],
                    "end_page": cur_pages[-1],
                    "word_count": cur_words,
                    "text": "\n\n".join(cur_text)
                })
                cur_pages, cur_text, cur_words = [], [], 0
            cur_pages.append(item["page_number"])
            cur_text.append(item["text"])
            cur_words += words
        if cur_pages:
            chunks.append({
                "section_index": len(chunks) + 1,
                "section_title": f"صفحات {cur_pages[0]} الی {cur_pages[-1]}",
                "start_page": cur_pages[0],
                "end_page": cur_pages[-1],
                "word_count": cur_words,
                "text": "\n\n".join(cur_text)
            })
        return chunks

    def extract_page_bounds(txt, def_s, def_e):
        matches = [int(m) for m in re.findall(r'<!-- PAGE_(\d+) -->', txt)]
        if matches:
            return min(matches), max(matches)
        return def_s, def_e

    # Group headings into cohesive macro-sections based on headings (~1000 to ~1600 words per section)
    macro_sections = []
    curr_titles = []
    curr_text = []
    curr_words = 0
    TARGET_WORDS = 1500
    MIN_CHUNK_WORDS = 650

    for s in raw_sections:
        words = len(s["text"].split())

        # If adding this heading section exceeds target and current chunk has substantial content, seal it
        if curr_text and (curr_words + words > TARGET_WORDS) and curr_words >= MIN_CHUNK_WORDS:
            macro_sections.append({
                "titles": list(curr_titles),
                "text": "\n\n".join(curr_text),
                "word_count": curr_words
            })
            curr_titles = []
            curr_text = []
            curr_words = 0

        # Filter out standalone chapter banner titles from compound title
        if not re.search(r'^(chapter|فصل)\s+\d+', s["title"], re.I) or len(s["text"].split()) > 100:
            curr_titles.append(s["title"])
        curr_text.append(s["text"])
        curr_words += words

    if curr_text:
        macro_sections.append({
            "titles": list(curr_titles),
            "text": "\n\n".join(curr_text),
            "word_count": curr_words
        })

    # Merge trailing short section (< 500 words) into previous section
    if len(macro_sections) > 1 and macro_sections[-1]["word_count"] < 500:
        last = macro_sections.pop()
        macro_sections[-1]["titles"].extend(last["titles"])
        macro_sections[-1]["text"] += "\n\n" + last["text"]
        macro_sections[-1]["word_count"] += last["word_count"]
    final_sections = []
    for idx, ms in enumerate(macro_sections):
        sp, ep = extract_page_bounds(ms["text"], page_items[0]["page_number"], page_items[-1]["page_number"])
        clean_text = re.sub(r'<!-- PAGE_\d+ -->\n*', '', ms["text"]).strip()

        clean_titles = [re.sub(r'^(chapter\s+\d+\.?\s*|#+\s*)', '', t, flags=re.I).strip() for t in ms["titles"] if t.strip()]
        if len(clean_titles) == 1:
            sec_title = clean_titles[0]
        elif len(clean_titles) == 2:
            sec_title = f"{clean_titles[0]} و {clean_titles[1]}"
        elif len(clean_titles) > 2:
            sec_title = f"{clean_titles[0]}، {clean_titles[1]} تا {clean_titles[-1]}"
        else:
            sec_title = f"سرفصل‌های صفحات {sp} الی {ep}"

        final_sections.append({
            "section_index": idx + 1,
            "section_title": sec_title,
            "sub_headings": clean_titles,
            "start_page": sp,
            "end_page": ep,
            "word_count": len(clean_text.split()),
            "text": clean_text
        })

    return final_sections
logger = logging.getLogger(__name__)


class ChapterService:
    def __init__(
        self,
        chapter_summary_repo: ChapterSummaryRepositoryPort,
        chapter_prompt_template_repo: ChapterPromptTemplateRepositoryPort,
        project_repo: ProjectRepositoryPort,
        page_repo: PageRepositoryPort,
        profile_repo: ProfileRepositoryPort,
        pdf_extractor: Optional[PDFExtractorPort] = None,
    ):
        self.chapter_summary_repo = chapter_summary_repo
        self.chapter_prompt_template_repo = chapter_prompt_template_repo
        self.project_repo = project_repo
        self.page_repo = page_repo
        self.profile_repo = profile_repo
        self.pdf_extractor = pdf_extractor or PyMuPDFExtractor()

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

    def create_chapter_summary(self, project_id: str, dto: ChapterSummaryCreateDTO) -> ChapterSummaryDTO:
        """Validates boundaries and scaffolds a new ChapterSummary record."""
        project = self.project_repo.get_by_id(project_id)
        if not project:
            raise ProjectNotFoundError(project_id)

        if dto.start_page < 1 or dto.end_page < dto.start_page or dto.end_page > project.total_pages:
            raise ValueError(
                f"بازه صفحات نامعتبر است (صفحات ۱ تا {project.total_pages} مجاز هستند)."
            )

        summary = ChapterSummary(
            project_id=project_id,
            chapter_title=dto.chapter_title.strip() or f"Chapter ({dto.start_page} - {dto.end_page})",
            start_page=dto.start_page,
            end_page=dto.end_page,
            source_type=dto.source_type or "source",
            prompt_template_id=dto.prompt_template_id,
            status="PENDING",
            progress_percent=0,
            progress_message="آماده برای پردازش...",
        )
        saved = self.chapter_summary_repo.save(summary)
        return self._to_summary_dto(saved)

    def get_chapter_summary(self, summary_id: str) -> Optional[ChapterSummaryDTO]:
        summary = self.chapter_summary_repo.get_by_id(summary_id)
        return self._to_summary_dto(summary) if summary else None

    def list_chapter_summaries(self, project_id: str) -> List[ChapterSummaryDTO]:
        summaries = self.chapter_summary_repo.list_by_project(project_id)
        return [self._to_summary_dto(s) for s in summaries]

    def update_chapter_summary(self, summary_id: str, dto: ChapterSummaryUpdateDTO) -> ChapterSummaryDTO:
        summary = self.chapter_summary_repo.get_by_id(summary_id)
        if not summary:
            raise ValueError(f"Chapter summary {summary_id} not found")

        if dto.chapter_title is not None:
            summary.chapter_title = dto.chapter_title.strip()
        if dto.final_summary is not None:
            summary.final_summary = dto.final_summary.strip()
        summary.updated_at = datetime.utcnow()

        saved = self.chapter_summary_repo.save(summary)
        return self._to_summary_dto(saved)


    def detect_book_chapters(self, project_id: str) -> List[DetectedChapterDTO]:
        """
        Extracts chapter boundaries from the PDF's digital Table of Contents (bookmarks/outlines).
        Falls back to heading analysis if no digital bookmarks exist.
        """
        project = self.project_repo.get_by_id(project_id)
        if not project:
            raise ProjectNotFoundError(project_id)

        if not project.source_pdf_path or not Path(project.source_pdf_path).exists():
            return []

        import fitz
        doc = fitz.open(project.source_pdf_path)
        try:
            total_pages = len(doc)
            toc = doc.get_toc()  # list of [lvl, title, page]
        finally:
            doc.close()

        detected: List[DetectedChapterDTO] = []

        if toc:
            level_1 = [e for e in toc if e[0] == 1]
            level_2 = [e for e in toc if e[0] == 2]

            has_chapters_in_l2 = any(re.search(r'chapter\s+\d+', e[1], re.I) for e in level_2)
            has_chapters_in_l1 = any(re.search(r'chapter\s+\d+', e[1], re.I) for e in level_1)

            items_to_use = level_2 if (has_chapters_in_l2 and not has_chapters_in_l1) else level_1
            if not items_to_use:
                items_to_use = toc

            for i, item in enumerate(items_to_use):
                lvl, title, start_p = item
                if start_p < 1:
                    start_p = 1
                if start_p > total_pages:
                    continue

                if i + 1 < len(items_to_use):
                    next_p = items_to_use[i + 1][2]
                    end_p = min(total_pages, max(start_p, next_p - 1))
                else:
                    end_p = total_pages

                clean_title = title.strip()
                page_count = max(1, end_p - start_p + 1)
                is_frontmatter = clean_title.lower() in {
                    "cover", "copyright", "title page", "table of contents", "contents", "toc"
                }
                is_main = bool(re.search(r'^(chapter|part|فصل|بخش)\b', clean_title, re.I)) or (
                    not is_frontmatter and page_count >= 4
                )

                detected.append(DetectedChapterDTO(
                    title=clean_title,
                    start_page=start_p,
                    end_page=end_p,
                    page_count=page_count,
                    level=lvl,
                    is_main_chapter=is_main,
                ))

        # Fallback: If no TOC entries found from PDF outline, scan pages for # Chapter headings
        if not detected:
            for p_num in range(1, project.total_pages + 1):
                p = self.page_repo.get_by_project_and_number(project_id, p_num)
                if not p:
                    continue
                txt = (p.source_text or p.approved_text or p.latest_translation or "").strip()
                match = re.search(r'^\s*#\s+(Chapter\s+\d+.*?|فصل\s+\d+.*?)$', txt, re.MULTILINE | re.IGNORECASE)
                if match:
                    detected.append(DetectedChapterDTO(
                        title=match.group(1).strip(),
                        start_page=p_num,
                        end_page=p_num,  # updated in loop below
                        page_count=1,
                        level=1,
                        is_main_chapter=True,
                    ))

            for idx in range(len(detected)):
                if idx + 1 < len(detected):
                    detected[idx].end_page = max(detected[idx].start_page, detected[idx + 1].start_page - 1)
                else:
                    detected[idx].end_page = project.total_pages
                detected[idx].page_count = max(1, detected[idx].end_page - detected[idx].start_page + 1)

        return detected
    def delete_chapter_summary(self, summary_id: str) -> bool:
        return self.chapter_summary_repo.delete(summary_id)

    def reset_chapter_summary(self, summary_id: str) -> Optional[ChapterSummary]:
        """Resets chunk cache and status to start fresh generation from scratch."""
        summary = self.chapter_summary_repo.get_by_id(summary_id)
        if not summary:
            return None
        summary.chunk_notes_json = None
        summary.intermediate_summaries_json = None
        summary.final_summary = None
        summary.status = "PENDING"
        summary.progress_percent = 0
        summary.progress_message = "آماده برای تولید مجدد از ابتدا..."
        summary.error_message = None
        summary.updated_at = datetime.utcnow()
        return self.chapter_summary_repo.save(summary)

    async def process_chapter_summary(self, summary_id: str, resume: bool = True):
        """
        Asynchronous background task implementing section-by-section technical note extraction:
        1. Gathers and on-demand extracts pages text.
        2. Splits by Headings (# and ##) and trims trailing references.
        3. Extracts rich technical notes per heading section (skipping already-cached sections if resuming).
        """
        summary = self.chapter_summary_repo.get_by_id(summary_id)
        if not summary:
            return

        try:
            summary.status = "PROCESSING"
            summary.progress_percent = max(5, summary.progress_percent if resume else 5)
            summary.progress_message = "در حال بارگذاری و تحلیل سرفصل‌های فصل..."
            summary.error_message = None
            self.chapter_summary_repo.save(summary)

            project = self.project_repo.get_by_id(summary.project_id)
            if not project:
                raise ProjectNotFoundError(summary.project_id)

            # 1. Collect page contents (with on-demand source text extraction)
            page_items = []
            for p_num in range(summary.start_page, summary.end_page + 1):
                page = self.page_repo.get_by_project_and_number(project.id, p_num)
                if not page:
                    continue

                if summary.source_type == "translation":
                    txt = (page.approved_text or page.latest_translation or page.source_text or "").strip()
                else:
                    # Default: source text
                    txt = (page.source_text or "").strip()
                    if not txt and project.source_pdf_path and Path(project.source_pdf_path).exists():
                        images_dir = Path(project.storage_dir) / "images" if project.storage_dir else None
                        txt = self.pdf_extractor.extract_page_content(
                            Path(project.source_pdf_path),
                            p_num,
                            project.id,
                            images_dir
                        )
                        page.source_text = txt
                        self.page_repo.save(page)

                if txt:
                    page_items.append({"page_number": p_num, "text": txt})

            if not page_items:
                raise ValueError("هیچ متنی در بازه صفحات انتخاب‌شده برای این فصل یافت نشد.")

            # 2. Split chapter into logical Heading sections (and strip references & author summary)
            sections = split_chapter_into_heading_sections(page_items)
            total_sections = len(sections)
            if not sections:
                raise ValueError("هیچ بخشی برای خلاصه‌سازی یافت نشد.")

            # Automatically synchronize true chapter boundaries (excluding stripped author's Summary & References)
            actual_end_page = max(s["end_page"] for s in sections)
            actual_start_page = min(s["start_page"] for s in sections)
            if actual_end_page < summary.end_page:
                logger.info(f"Trimming chapter {summary.id} boundary from {summary.end_page} to {actual_end_page} (stripped trailing author summary/references).")
                summary.end_page = actual_end_page
            if actual_start_page > summary.start_page:
                summary.start_page = actual_start_page

            summary.progress_percent = 10
            summary.progress_message = f"فصل به {total_sections} بخش بر اساس سرفصل‌ها تفکیک شد (صفحات {summary.start_page} تا {summary.end_page}). شروع نوت‌برداری..."
            self.chapter_summary_repo.save(summary)
            profile = None
            if project.profile_id:
                profile = self.profile_repo.get_by_id(project.profile_id)
            if not profile:
                profile = self.profile_repo.get_default()

            provider = self._resolve_provider(profile)

            template_obj = None
            if summary.prompt_template_id:
                template_obj = self.chapter_prompt_template_repo.get_by_id(summary.prompt_template_id)
            if not template_obj:
                template_obj = self.chapter_prompt_template_repo.get_default()

            # 4. Phase 1: Map (Extract technical notes per heading section with Resume support)
            # Build lookup of already completed section notes if resume is requested
            existing_notes_map: Dict[str, Dict[str, Any]] = {}
            if resume and summary.chunk_notes_json:
                try:
                    saved_chunks = json.loads(summary.chunk_notes_json)
                    if isinstance(saved_chunks, list):
                        for item in saved_chunks:
                            if item.get("section_title"):
                                existing_notes_map[item["section_title"]] = item
                            if item.get("section_index"):
                                existing_notes_map[str(item["section_index"])] = item
                except Exception:
                    existing_notes_map = {}
            # Reset conversation thread once at chapter start so the entire chapter starts with a clean slate
            if hasattr(provider, "manager"):
                provider.manager.reset_conversation_thread("all")

            chunk_notes = []
            for idx, sec in enumerate(sections):
                # Check if this section was already processed and cached
                cached = existing_notes_map.get(sec["section_title"]) or existing_notes_map.get(str(idx + 1))
                if cached and cached.get("note"):
                    chunk_notes.append(cached)
                    continue

                pct = 10 + int(((idx + 1) / total_sections) * 90)
                summary.progress_percent = pct
                summary.progress_message = f"در حال استخراج نوت بخش {idx + 1} از {total_sections}: «{sec['section_title'][:40]}...» (صفحات {sec['start_page']} تا {sec['end_page']})..."
                self.chapter_summary_repo.save(summary)

                # Build complete, self-contained prompt for every section (same robust pattern as page translation)
                sec_title = sec["section_title"]
                sp = sec["start_page"]
                ep = sec["end_page"]
                sec_text = sec["text"]

                if template_obj:
                    chunk_prompt = (
                        template_obj.chunk_template
                        .replace("{chapter_title}", f"{summary.chapter_title} - {sec_title}")
                        .replace("{start_page}", str(sp))
                        .replace("{end_page}", str(ep))
                        .replace("{content_text}", sec_text)
                    )
                    chunk_prompt += "\n\nدستورالعمل خروجی: مستقیماً فقط نوت‌های مفهومی، عمیق و تخصصی این بخش را بنویسید. بدون هیچ‌گونه مقدمه، احوالپرسی یا تعارف."
                else:
                    chunk_prompt = f"""شما یک معمار و مهندس ارشد نرم‌افزار، پژوهشگر برجسته و ویراستار متون تخصصی هستید.
متن زیر از بخش {idx + 1} با عنوان «{sec_title}» فصل «{summary.chapter_title}» (صفحات {sp} تا {ep}) است.

متن ورودی این بخش جهت تحلیل و استخراج نوت:
<source_document>
{sec_text}
</source_document>

دستورالعمل دقیق نوت‌برداری:
۱. ایده‌های اصلی، صورت‌مسئله‌ها، مفاهیم معماری، مکانیزم‌های فنی، الگوریتم‌ها و مصالحه‌ها (Trade-offs) را عمیق و موشکافانه استخراج کنید.
۲. لحن و نثر: کاملاً روان، خودمانی، ساده، شیوا و خوش‌خوان فارسی (بدون عبارات خشک اداری یا ترجمه‌های مکانیکی و تحت‌اللفظی؛ مثل یک معمار نرم‌افزار ارشد که با لحنی خودمانی، رسا و گیرا برای همکارش مبحث را توضیح می‌دهد).
۳. اصطلاحات تخصصی انگلیسی را حتماً با ذکر عنوان انگلیسی در پرانتز قید نمایید (مانند: سازگاری نهایی (Eventual Consistency)).
۴. فرمول‌های ریاضی و متغیرها در قالب استاندارد LaTeX ($...$ و $$...$$) نوشته شوند.
۵. از کلی‌گویی پرهیز کنید؛ چرایی تصمیمات و نکات فنی کلیدی را کامل پوشش دهید.

دستورالعمل خروجی:
مستقیماً و بلافاصله فقط خود نوت‌های استخراج‌شده این بخش را ارسال کنید؛ بدون هیچ‌گونه مقدمه، احوالپرسی، تعارف («بله»، «در ادامه نوت‌ها را مشاهده می‌کنید») یا جملات آغازین و پایانی اضافی."""
                # Attempt extraction with retry and anti-loop safeguard
                note = None
                for attempt in range(2):
                    try:
                        note = await provider.translate(
                            source_text=chunk_prompt,
                            source_language=project.source_language,
                            target_language="Persian",
                            system_prompt="",
                        )
                        if is_canned_acknowledgement(note):
                            logger.warning(f"Canned acknowledgement detected for section {idx + 1}, retrying with reinforced prompt...")
                            strict_retry_prompt = f"دستور اکید: هیچ‌گونه جمله هماهنگی، سلام، تعارف یا تأییدیه ننویسید. بلافاصله و مستقیماً فقط خود نوت‌های استخراج‌شده این بخش را ارسال نمایید:\n\n{chunk_prompt}"
                            retry_res = await provider.translate(
                                source_text=strict_retry_prompt,
                                source_language=project.source_language,
                                target_language="Persian",
                                system_prompt="",
                            )
                            if retry_res and not is_canned_acknowledgement(retry_res):
                                note = retry_res
                        if note:
                            note = clean_markdown_persian(note)
                        break
                    except Exception as err:
                        if attempt == 0:
                            if hasattr(provider, "manager"):
                                provider.manager.reset_conversation_thread("all")
                            await asyncio.sleep(2.0)
                        else:
                            raise err
                chunk_notes.append({
                    "section_index": idx + 1,
                    "section_title": sec["section_title"],
                    "start_page": sec["start_page"],
                    "end_page": sec["end_page"],
                    "word_count": sec["word_count"],
                    "note": note.strip() if note else ""
                })

                summary.chunk_notes_json = json.dumps(chunk_notes, ensure_ascii=False)
                self.chapter_summary_repo.save(summary)
            # 5. Complete: All section notes extracted
            summary.status = "COMPLETED"
            summary.progress_percent = 100
            summary.progress_message = f"نوت‌برداری {total_sections} بخش فصل با موفقیت تکمیل شد."
            summary.updated_at = datetime.utcnow()
            self.chapter_summary_repo.save(summary)

        except Exception as e:
            logger.error(f"Error processing chapter summary {summary_id}: {e}", exc_info=True)
            summary.status = "FAILED"
            summary.error_message = str(e)
            completed_count = len(chunk_notes) if 'chunk_notes' in locals() else 0
            if completed_count > 0:
                summary.progress_message = f"توقف به دلیل خطا ({completed_count} بخش ذخیره شد). می‌توانید با دکمه «ادامه پردازش» بدون تکرار از همین نقطه ادامه دهید."
            else:
                summary.progress_message = f"خطا در پردازش فصل: {str(e)}"
            summary.updated_at = datetime.utcnow()
            self.chapter_summary_repo.save(summary)
    def export_chapter_summary(self, summary_id: str, format_type: str = "md") -> tuple[Path, str]:
        """Exports chapter section notes as Markdown or DOCX file."""
        summary = self.chapter_summary_repo.get_by_id(summary_id)
        if not summary or not summary.chunk_notes_json:
            raise ValueError(f"Chapter summary {summary_id} not found or has no notes yet")

        project = self.project_repo.get_by_id(summary.project_id)
        safe_title = re.sub(r'[\\/*?:"<>| ]', '_', summary.chapter_title)[:40]
        export_dir = Path(project.storage_dir) / "exports" if project and project.storage_dir else Path.home() / ".pdf_translator" / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        sections = []
        try:
            sections = json.loads(summary.chunk_notes_json)
        except Exception:
            pass

        if format_type.lower() == "docx":
            filename = f"Chapter_{summary.start_page}_{summary.end_page}_{safe_title}.docx"
            out_file = export_dir / filename
            doc = Document()

            # Title
            title_p = doc.add_paragraph()
            title_p.add_run(summary.chapter_title).bold = True
            doc.add_paragraph(f"صفحات {summary.start_page} الی {summary.end_page}")
            doc.add_paragraph("=" * 40)

            # Section-by-Section notes
            if sections:
                for s in sections:
                    p_s = doc.add_paragraph()
                    p_s.add_run(f"بخش {s.get('section_index')}: {s.get('section_title')} (صفحات {s.get('start_page')} الی {s.get('end_page')})").bold = True
                    for par in (s.get("note") or "").split("\n\n"):
                        if par.strip():
                            render_markdown_paragraph_to_docx(doc, par, project.storage_dir if project else None)
                    doc.add_paragraph("-" * 20)

            doc.save(str(out_file))
            return out_file, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            filename = f"Chapter_{summary.start_page}_{summary.end_page}_{safe_title}.md"
            out_file = export_dir / filename
            content = f"# {summary.chapter_title}\n\n**صفحات:** {summary.start_page} الی {summary.end_page}\n\n---\n\n"

            # Section-by-Section notes in markdown
            if sections:
                for s in sections:
                    content += f"## بخش {s.get('section_index')}: {s.get('section_title')}\n"
                    content += f"**صفحات {s.get('start_page')} الی {s.get('end_page')}**\n\n"
                    content += f"{s.get('note')}\n\n---\n\n"

            out_file.write_text(content, encoding="utf-8")
            return out_file, "text/markdown"

    # --- Chapter Prompt Templates Management ---
    def list_chapter_prompt_templates(self) -> List[ChapterPromptTemplateDTO]:
        tpls = self.chapter_prompt_template_repo.list_all()
        return [self._to_template_dto(t) for t in tpls]

    def create_chapter_prompt_template(self, dto: ChapterPromptTemplateCreateDTO) -> ChapterPromptTemplateDTO:
        if dto.is_default:
            # Unset existing defaults
            for t in self.chapter_prompt_template_repo.list_all():
                if t.is_default:
                    t.is_default = False
                    self.chapter_prompt_template_repo.save(t)

        template = ChapterPromptTemplate(
            name=dto.name.strip(),
            description=dto.description.strip() if dto.description else None,
            chunk_template=dto.chunk_template.strip(),
            synthesis_template=(dto.synthesis_template or "").strip() if dto.synthesis_template else None,
            is_default=dto.is_default,
        )
        saved = self.chapter_prompt_template_repo.save(template)
        return self._to_template_dto(saved)

    def update_chapter_prompt_template(self, template_id: str, dto: ChapterPromptTemplateUpdateDTO) -> ChapterPromptTemplateDTO:
        tpl = self.chapter_prompt_template_repo.get_by_id(template_id)
        if not tpl:
            raise ValueError(f"Template {template_id} not found")

        if dto.is_default is True:
            for t in self.chapter_prompt_template_repo.list_all():
                if t.id != template_id and t.is_default:
                    t.is_default = False
                    self.chapter_prompt_template_repo.save(t)
            tpl.is_default = True
        elif dto.is_default is False:
            tpl.is_default = False

        if dto.name is not None:
            tpl.name = dto.name.strip()
        if dto.description is not None:
            tpl.description = dto.description.strip()
        if dto.chunk_template is not None:
            tpl.chunk_template = dto.chunk_template.strip()
        if dto.synthesis_template is not None:
            tpl.synthesis_template = dto.synthesis_template.strip() if dto.synthesis_template else None
        tpl.updated_at = datetime.utcnow()

        saved = self.chapter_prompt_template_repo.save(tpl)
        return self._to_template_dto(saved)

    def delete_chapter_prompt_template(self, template_id: str) -> bool:
        return self.chapter_prompt_template_repo.delete(template_id)


    @staticmethod
    def _to_summary_dto(s: ChapterSummary) -> ChapterSummaryDTO:
        return ChapterSummaryDTO(
            id=s.id,
            project_id=s.project_id,
            chapter_title=s.chapter_title,
            start_page=s.start_page,
            end_page=s.end_page,
            source_type=s.source_type,
            prompt_template_id=s.prompt_template_id,
            chunk_notes_json=s.chunk_notes_json,
            intermediate_summaries_json=getattr(s, "intermediate_summaries_json", None),
            final_summary=s.final_summary,
            status=s.status,
            progress_percent=s.progress_percent,
            progress_message=s.progress_message,
            error_message=s.error_message,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
    @staticmethod
    def _to_template_dto(t: ChapterPromptTemplate) -> ChapterPromptTemplateDTO:
        return ChapterPromptTemplateDTO(
            id=t.id,
            name=t.name,
            description=t.description,
            chunk_template=t.chunk_template,
            synthesis_template=t.synthesis_template,
            is_default=t.is_default,
            created_at=t.created_at,
            updated_at=t.updated_at,
        )
