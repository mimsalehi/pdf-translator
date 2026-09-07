"""File system manager for project storage and artifacts."""
from pathlib import Path
import shutil
from typing import Optional
from pdf_translator.config import settings

class FileStorageManager:
    """Manages disk directories and files for each Project."""

    def __init__(self, root_data_dir: Optional[Path] = None):
        self.root_data_dir = root_data_dir or settings.get_data_dir()

    def get_project_dir(self, project_id: str) -> Path:
        project_dir = self.root_data_dir / "projects" / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        return project_dir

    def get_pages_dir(self, project_id: str) -> Path:
        pages_dir = self.get_project_dir(project_id) / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)
        return pages_dir

    def get_exports_dir(self, project_id: str) -> Path:
        exports_dir = self.get_project_dir(project_id) / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        return exports_dir

    def save_source_pdf(self, project_id: str, original_file_path: Path, filename: str) -> Path:
        dest = self.get_project_dir(project_id) / "source.pdf"
        shutil.copy2(original_file_path, dest)
        return dest

    def get_source_pdf_path(self, project_id: str) -> Path:
        return self.get_project_dir(project_id) / "source.pdf"

    def get_page_image_path(self, project_id: str, page_number: int) -> Path:
        return self.get_pages_dir(project_id) / f"page_{page_number}.png"

    def get_page_thumbnail_path(self, project_id: str, page_number: int) -> Path:
        return self.get_pages_dir(project_id) / f"page_{page_number}_thumb.png"

    def delete_project_dir(self, project_id: str) -> bool:
        project_dir = self.root_data_dir / "projects" / project_id
        if project_dir.exists():
            shutil.rmtree(project_dir)
            return True
        return False
