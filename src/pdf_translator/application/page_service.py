"""Application service for Page inspection, source text editing, and pre-translation approval."""
from pathlib import Path
from typing import Optional, List
from datetime import datetime
from pdf_translator.domain.entities import Project, Page, TranslationAttempt
from pdf_translator.domain.enums import PageStatus
from pdf_translator.domain.errors import PageNotFoundError, ProjectNotFoundError, InvalidStateTransitionError
from pdf_translator.domain.ports import PageRepositoryPort, ProjectRepositoryPort, PDFExtractorPort
from pdf_translator.application.dtos import PageDetailDTO

class PageService:
    def __init__(
        self,
        page_repo: PageRepositoryPort,
        project_repo: ProjectRepositoryPort,
        pdf_extractor: Optional[PDFExtractorPort] = None,
    ):
        self.page_repo = page_repo
        self.project_repo = project_repo
        self.pdf_extractor = pdf_extractor

    def _extract_page_with_stitching(self, project: Project, page_number: int) -> str:
        """Extracts page text and embedded diagrams with cross-page sentence stitching."""
        from pdf_translator.adapters.pdf.pymupdf_extractor import stitch_page_boundaries
        pdf_path = Path(project.source_pdf_path)
        images_dir = Path(project.storage_dir) / "images"
        total_pages = project.total_pages

        # 1. Extract current page
        curr_text = self.pdf_extractor.extract_page_content(
            pdf_path,
            page_number,
            project_id=project.id,
            images_dir=images_dir
        )

        # If previous page had an incomplete trailing sentence:
        if page_number > 1:
            prev_raw = self.pdf_extractor.extract_page_content(
                pdf_path,
                page_number - 1,
                project_id=project.id,
                images_dir=images_dir
            )
            stitched_pair = stitch_page_boundaries([prev_raw, curr_text])
            curr_text = stitched_pair[1]

        # 2. Append trailing fragment from next page if current page ends with incomplete sentence
        if page_number < total_pages:
            next_raw = self.pdf_extractor.extract_page_content(
                pdf_path,
                page_number + 1,
                project_id=project.id,
                images_dir=images_dir
            )
            stitched_pair = stitch_page_boundaries([curr_text, next_raw])
            curr_text = stitched_pair[0]

        return curr_text

    def get_page_detail(self, project_id: str, page_number: int) -> PageDetailDTO:
        project = self.project_repo.get_by_id(project_id)
        if not project:
            raise ProjectNotFoundError(project_id)

        page = self.page_repo.get_by_project_and_number(project_id, page_number)
        if not page:
            raise PageNotFoundError(project_id, page_number)

        # On-demand text extraction with cross-page boundary stitching
        if not page.source_text and self.pdf_extractor and project.source_pdf_path:
            pdf_path = Path(project.source_pdf_path)
            if pdf_path.exists():
                try:
                    page.source_text = self._extract_page_with_stitching(project, page_number)
                    self.page_repo.save(page)
                except Exception:
                    pass

        attempts = self.page_repo.list_attempts(page.id)
        attempts_dto = [
            {
                "id": a.id,
                "version_number": a.version_number,
                "provider_name": a.provider_name,
                "model_name": a.model_name,
                "edited_text": a.edited_text,
                "is_approved": a.is_approved,
                "created_at": a.created_at.isoformat(),
            }
            for a in attempts
        ]

        prev_page = page_number - 1 if page_number > 1 else None
        next_page = page_number + 1 if page_number < project.total_pages else None

        return PageDetailDTO(
            id=page.id,
            project_id=project.id,
            project_title=project.title,
            page_number=page.page_number,
            total_pages=project.total_pages,
            status=page.status,
            source_text=page.source_text,
            image_url=f"/api/projects/{project.id}/pages/{page.page_number}/image",
            thumbnail_url=f"/api/projects/{project.id}/pages/{page.page_number}/thumbnail",
            latest_translation=page.latest_translation,
            approved_text=page.approved_text,
            prev_page_number=prev_page,
            next_page_number=next_page,
            attempts=attempts_dto,
        )

    def update_source_text(self, project_id: str, page_number: int, new_source_text: str) -> Page:
        page = self.page_repo.get_by_project_and_number(project_id, page_number)
        if not page:
            raise PageNotFoundError(project_id, page_number)

        page.source_text = new_source_text.strip()
        page.updated_at = datetime.utcnow()
        return self.page_repo.save(page)

    def approve_for_translation(self, project_id: str, page_number: int) -> Page:
        page = self.page_repo.get_by_project_and_number(project_id, page_number)
        if not page:
            raise PageNotFoundError(project_id, page_number)

        # Idempotent if already approved
        if page.status == PageStatus.APPROVED_FOR_TRANSLATION:
            return page

        if not page.can_transition_to(PageStatus.APPROVED_FOR_TRANSLATION):
            raise InvalidStateTransitionError(
                current_status=page.status.value,
                target_status=PageStatus.APPROVED_FOR_TRANSLATION.value,
                reason="Page must be in READY, FAILED, or IN_REVIEW state to be approved for translation."
            )

        page.status = PageStatus.APPROVED_FOR_TRANSLATION
        page.updated_at = datetime.utcnow()
        return self.page_repo.save(page)

    def reset_to_ready(self, project_id: str, page_number: int) -> Page:
        page = self.page_repo.get_by_project_and_number(project_id, page_number)
        if not page:
            raise PageNotFoundError(project_id, page_number)

        page.status = PageStatus.READY
        page.updated_at = datetime.utcnow()
        return self.page_repo.save(page)
