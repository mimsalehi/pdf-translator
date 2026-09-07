"""Application service for Project management and PDF ingestion."""
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from pdf_translator.domain.entities import Project, Page
from pdf_translator.domain.enums import PageStatus
from pdf_translator.domain.errors import ProjectNotFoundError
from pdf_translator.domain.ports import PDFExtractorPort, ProjectRepositoryPort, PageRepositoryPort
from pdf_translator.adapters.storage.file_storage import FileStorageManager
from pdf_translator.application.dtos import ProjectCreateDTO, ProjectDetailDTO, ProjectListItemDTO, PageSummaryDTO

class ProjectService:
    def __init__(
        self,
        project_repo: ProjectRepositoryPort,
        page_repo: PageRepositoryPort,
        pdf_extractor: PDFExtractorPort,
        file_storage: FileStorageManager,
    ):
        self.project_repo = project_repo
        self.page_repo = page_repo
        self.pdf_extractor = pdf_extractor
        self.file_storage = file_storage

    def create_project(self, dto: ProjectCreateDTO) -> Project:
        """Ingests a PDF file, indexes its pages, extracts source text, and renders images."""
        temp_pdf_path = Path(dto.source_pdf_path)
        if not temp_pdf_path.exists():
            raise FileNotFoundError(f"Source PDF file not found at: {dto.source_pdf_path}")

        # 1. Create Project entity
        project = Project(
            title=dto.title.strip() or dto.original_filename,
            source_pdf_filename=dto.original_filename,
            source_pdf_path="",
            storage_dir="",
            source_language=dto.source_language,
            target_language=dto.target_language,
            profile_id=dto.profile_id,
        )
        project = self.project_repo.save(project)

        # 2. Store PDF in project storage
        stored_pdf_path = self.file_storage.save_source_pdf(
            project_id=project.id,
            original_file_path=temp_pdf_path,
            filename=dto.original_filename,
        )
        project.source_pdf_path = str(stored_pdf_path)
        project.storage_dir = str(self.file_storage.get_project_dir(project.id))

        # 3. Inspect PDF and get total page count instantly
        total_pages = self.pdf_extractor.get_page_count(stored_pdf_path)
        project.total_pages = total_pages
        self.project_repo.save(project)

        # 4. Instant index: Create Page records in DB. Text and images are extracted on-demand.
        for page_num in range(1, total_pages + 1):
            img_path = self.file_storage.get_page_image_path(project.id, page_num)
            thumb_path = self.file_storage.get_page_thumbnail_path(project.id, page_num)

            page = Page(
                project_id=project.id,
                page_number=page_num,
                status=PageStatus.READY,
                source_text="",
                image_path=str(img_path),
                thumbnail_path=str(thumb_path),
            )
            self.page_repo.save(page)

        return project

    def list_projects(self) -> List[ProjectListItemDTO]:
        projects = self.project_repo.list_all()
        results = []
        for p in projects:
            pages = self.page_repo.list_by_project(p.id)
            approved = sum(1 for pg in pages if pg.status == PageStatus.APPROVED or pg.status == PageStatus.EXPORTED)
            pct = (approved / p.total_pages * 100.0) if p.total_pages > 0 else 0.0
            results.append(
                ProjectListItemDTO(
                    id=p.id,
                    title=p.title,
                    source_pdf_filename=p.source_pdf_filename,
                    total_pages=p.total_pages,
                    source_language=p.source_language,
                    target_language=p.target_language,
                    created_at=p.created_at,
                    approved_count=approved,
                    progress_percentage=round(pct, 1),
                )
            )
        return results

    def get_project_detail(self, project_id: str) -> ProjectDetailDTO:
        project = self.project_repo.get_by_id(project_id)
        if not project:
            raise ProjectNotFoundError(project_id)

        pages = self.page_repo.list_by_project(project_id)
        page_dtos = []
        
        counts = {status: 0 for status in PageStatus}
        for pg in pages:
            counts[pg.status] += 1
            preview = None
            if pg.approved_text:
                preview = pg.approved_text[:120] + "..." if len(pg.approved_text) > 120 else pg.approved_text
            elif pg.latest_translation:
                preview = pg.latest_translation[:120] + "..." if len(pg.latest_translation) > 120 else pg.latest_translation

            page_dtos.append(
                PageSummaryDTO(
                    id=pg.id,
                    page_number=pg.page_number,
                    status=pg.status,
                    has_text=bool(pg.source_text and pg.source_text.strip()),
                    thumbnail_url=f"/api/projects/{project.id}/pages/{pg.page_number}/thumbnail",
                    image_url=f"/api/projects/{project.id}/pages/{pg.page_number}/image",
                    latest_translation_preview=preview,
                )
            )

        return ProjectDetailDTO(
            id=project.id,
            title=project.title,
            source_pdf_filename=project.source_pdf_filename,
            total_pages=project.total_pages,
            source_language=project.source_language,
            target_language=project.target_language,
            created_at=project.created_at,
            pages=page_dtos,
            ready_count=counts[PageStatus.READY],
            approved_for_translation_count=counts[PageStatus.APPROVED_FOR_TRANSLATION],
            translating_count=counts[PageStatus.TRANSLATING],
            translated_count=counts[PageStatus.TRANSLATED],
            in_review_count=counts[PageStatus.IN_REVIEW],
            approved_count=counts[PageStatus.APPROVED],
            exported_count=counts[PageStatus.EXPORTED],
            failed_count=counts[PageStatus.FAILED],
        )

    def delete_project(self, project_id: str) -> bool:
        project = self.project_repo.get_by_id(project_id)
        if not project:
            raise ProjectNotFoundError(project_id)
        self.file_storage.delete_project_dir(project_id)
        return self.project_repo.delete(project_id)
