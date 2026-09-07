"""Application service for Exporting pages and Assembling Books."""
from pathlib import Path
from typing import Optional, List
from pdf_translator.domain.entities import Project, Page
from pdf_translator.domain.enums import PageStatus
from pdf_translator.domain.errors import ProjectNotFoundError, PageNotFoundError, ExportError
from pdf_translator.domain.ports import ProjectRepositoryPort, PageRepositoryPort
from pdf_translator.adapters.storage.file_storage import FileStorageManager
from pdf_translator.adapters.export.markdown_exporter import MarkdownExporter
from pdf_translator.adapters.export.docx_exporter import DocxExporter

class ExportService:
    def __init__(
        self,
        project_repo: ProjectRepositoryPort,
        page_repo: PageRepositoryPort,
        file_storage: FileStorageManager,
    ):
        self.project_repo = project_repo
        self.page_repo = page_repo
        self.file_storage = file_storage
        self.md_exporter = MarkdownExporter()
        self.docx_exporter = DocxExporter()

    def export_page(self, project_id: str, page_number: int, fmt: str = "md") -> Path:
        page = self.page_repo.get_by_project_and_number(project_id, page_number)
        if not page:
            raise PageNotFoundError(project_id, page_number)

        pages_dir = self.file_storage.get_pages_dir(project_id)
        
        if fmt == "docx":
            output_file = pages_dir / f"page_{page_number}.docx"
            return self.docx_exporter.export_page(page, output_file)
        else:
            output_file = pages_dir / f"page_{page_number}.md"
            return self.md_exporter.export_page(page, output_file)

    def assemble_and_export_book(self, project_id: str, fmt: str = "md") -> Path:
        project = self.project_repo.get_by_id(project_id)
        if not project:
            raise ProjectNotFoundError(project_id)

        pages = self.page_repo.list_by_project(project_id)
        if not pages:
            raise ExportError("No pages found in this project.")

        exports_dir = self.file_storage.get_exports_dir(project_id)

        if fmt == "docx":
            output_file = exports_dir / f"{project.title}_Translated.docx"
            return self.docx_exporter.assemble_book(project, pages, output_file)
        else:
            output_file = exports_dir / f"{project.title}_Translated.md"
            return self.md_exporter.assemble_book(project, pages, output_file)
