"""Domain ports (interfaces) for PDF Book Translator."""
from abc import ABC, abstractmethod
from typing import List, Optional
from pathlib import Path
from pdf_translator.domain.entities import Project, Page, TranslationProfile, TranslationAttempt, GlossaryItem

class PDFExtractorPort(ABC):
    """Port for inspecting and extracting text and images from PDF documents."""

    @abstractmethod
    def get_page_count(self, pdf_path: Path) -> int:
        """Returns total pages in the PDF."""
        pass

    @abstractmethod
    def extract_page_content(
        self,
        pdf_path: Path,
        page_number: int,
        project_id: Optional[str] = None,
        images_dir: Optional[Path] = None
    ) -> str:
        """Extracts text content and diagrams from a given 1-based page number."""
        pass

    @abstractmethod
    def render_page_image(self, pdf_path: Path, page_number: int, output_image_path: Path, dpi: int = 150) -> Path:
        """Renders the given 1-based page number to a PNG image file."""
        pass

    @abstractmethod
    def render_thumbnail(self, pdf_path: Path, page_number: int, output_image_path: Path, max_width: int = 300) -> Path:
        """Renders a thumbnail image of the page."""
        pass


class ProjectRepositoryPort(ABC):
    """Port for Project persistence."""

    @abstractmethod
    def save(self, project: Project) -> Project:
        pass

    @abstractmethod
    def get_by_id(self, project_id: str) -> Optional[Project]:
        pass

    @abstractmethod
    def list_all(self) -> List[Project]:
        pass

    @abstractmethod
    def delete(self, project_id: str) -> bool:
        pass


class PageRepositoryPort(ABC):
    """Port for Page persistence."""

    @abstractmethod
    def save(self, page: Page) -> Page:
        pass

    @abstractmethod
    def get_by_id(self, page_id: str) -> Optional[Page]:
        pass

    @abstractmethod
    def get_by_project_and_number(self, project_id: str, page_number: int) -> Optional[Page]:
        pass

    @abstractmethod
    def list_by_project(self, project_id: str) -> List[Page]:
        pass

    @abstractmethod
    def save_attempt(self, attempt: TranslationAttempt) -> TranslationAttempt:
        pass

    @abstractmethod
    def list_attempts(self, page_id: str) -> List[TranslationAttempt]:
        pass


class ProfileRepositoryPort(ABC):
    """Port for TranslationProfile persistence."""

    @abstractmethod
    def save(self, profile: TranslationProfile) -> TranslationProfile:
        pass

    @abstractmethod
    def get_by_id(self, profile_id: str) -> Optional[TranslationProfile]:
        pass

    @abstractmethod
    def get_default(self) -> TranslationProfile:
        pass

    @abstractmethod
    def list_all(self) -> List[TranslationProfile]:
        pass


class TranslationProviderPort(ABC):
    """Port for AI translation engines."""

    @abstractmethod
    async def translate(
        self,
        source_text: str,
        source_language: str,
        target_language: str,
        system_prompt: str,
        glossary: Optional[List[GlossaryItem]] = None,
        context_notes: Optional[str] = None,
    ) -> str:
        """Executes translation and returns translated text."""
        pass


class ExportPort(ABC):
    """Port for exporting pages and books."""

    @abstractmethod
    def export_page_markdown(self, page: Page, output_path: Path) -> Path:
        pass

    @abstractmethod
    def export_page_docx(self, page: Page, output_path: Path) -> Path:
        pass

    @abstractmethod
    def assemble_book_markdown(self, project: Project, pages: List[Page], output_path: Path) -> Path:
        pass

    @abstractmethod
    def assemble_book_docx(self, project: Project, pages: List[Page], output_path: Path) -> Path:
        pass


class PromptTemplateRepositoryPort(ABC):
    """Port for PromptTemplate persistence."""

    @abstractmethod
    def save(self, template: "PromptTemplate") -> "PromptTemplate":
        pass

    @abstractmethod
    def get_by_id(self, template_id: str) -> Optional["PromptTemplate"]:
        pass

    @abstractmethod
    def get_default(self) -> Optional["PromptTemplate"]:
        pass

    @abstractmethod
    def list_all(self) -> List["PromptTemplate"]:
        pass

    @abstractmethod
    def delete(self, template_id: str) -> bool:
        pass


class PageConversationRepositoryPort(ABC):
    """Port for Page Q&A Conversation persistence."""

    @abstractmethod
    def save(self, conversation: "PageConversation") -> "PageConversation":
        pass

    @abstractmethod
    def list_by_page(self, project_id: str, page_number: int) -> List["PageConversation"]:
        pass

    @abstractmethod
    def delete(self, conversation_id: str) -> bool:
        pass


class ChapterSummaryRepositoryPort(ABC):
    """Port for ChapterSummary persistence."""

    @abstractmethod
    def save(self, summary: "ChapterSummary") -> "ChapterSummary":
        pass

    @abstractmethod
    def get_by_id(self, summary_id: str) -> Optional["ChapterSummary"]:
        pass

    @abstractmethod
    def list_by_project(self, project_id: str) -> List["ChapterSummary"]:
        pass

    @abstractmethod
    def delete(self, summary_id: str) -> bool:
        pass


class ChapterPromptTemplateRepositoryPort(ABC):
    """Port for ChapterPromptTemplate persistence."""

    @abstractmethod
    def save(self, template: "ChapterPromptTemplate") -> "ChapterPromptTemplate":
        pass

    @abstractmethod
    def get_by_id(self, template_id: str) -> Optional["ChapterPromptTemplate"]:
        pass

    @abstractmethod
    def get_default(self) -> Optional["ChapterPromptTemplate"]:
        pass

    @abstractmethod
    def list_all(self) -> List["ChapterPromptTemplate"]:
        pass

    @abstractmethod
    def delete(self, template_id: str) -> bool:
        pass


class ChapterConversationRepositoryPort(ABC):
    """Port for Chapter Q&A Conversation persistence."""

    @abstractmethod
    def save(self, conversation: "ChapterConversation") -> "ChapterConversation":
        pass

    @abstractmethod
    def list_by_chapter(self, chapter_summary_id: str, section_index: Optional[int] = None) -> List["ChapterConversation"]:
        pass

    @abstractmethod
    def delete(self, conversation_id: str) -> bool:
        pass

