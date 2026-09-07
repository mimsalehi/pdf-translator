"""Application Configuration."""
from pathlib import Path
from pydantic import BaseModel
import os

class Settings(BaseModel):
    app_name: str = "PDF Book Translator"
    app_version: str = "0.1.0"
    base_dir: Path = Path(__file__).resolve().parent.parent.parent
    data_dir: Path = Path(os.environ.get("DATA_DIR", str(Path.home() / ".pdf_translator")))
    sqlite_db_path: Path | None = None
    
    def get_data_dir(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir

    def get_db_url(self) -> str:
        if self.sqlite_db_path:
            return f"sqlite:///{self.sqlite_db_path}"
        db_path = self.get_data_dir() / "pdf_translator.db"
        return f"sqlite:///{db_path}"

settings = Settings()
