"""Backup and Restore Service for full database and projects portability."""
import json
import logging
import os
import platform
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from pdf_translator.config import settings
from pdf_translator.adapters.storage.db import init_db, reset_engine

logger = logging.getLogger(__name__)


class BackupService:
    """Manages full application backup and restoration with automatic path rebasing."""
    def __init__(self, data_dir: Path | None = None):
        self.data_dir = (data_dir or settings.get_data_dir()).resolve()

    def get_db_path(self) -> Path:
        """Resolves active SQLite database file path."""
        if settings.sqlite_db_path:
            return Path(settings.sqlite_db_path).resolve()
        return (self.data_dir / "pdf_translator.db").resolve()
    def create_backup(self, output_dir: Path | None = None) -> tuple[Path, str]:
        """
        Creates a complete point-in-time backup archive containing:
        1. Point-in-time safe snapshot of SQLite database (via sqlite3.backup).
        2. Entire projects/ directory (source PDFs, extracted images, pages, exports).
        3. Metadata manifest.json with system information.
        """
        self.data_dir.mkdir(parents=True, exist_ok=True)
        export_dir = (output_dir or (self.data_dir / "exports")).resolve()
        export_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")
        backup_filename = f"pdf_translator_backup_{timestamp}.zip"
        backup_zip_path = export_dir / backup_filename

        db_path = self.get_db_path()
        projects_dir = self.data_dir / "projects"

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            temp_db_snapshot = temp_dir_path / "pdf_translator.db"

            # 1. Atomic point-in-time snapshot of SQLite database
            if db_path.exists():
                src_conn = sqlite3.connect(str(db_path))
                dst_conn = sqlite3.connect(str(temp_db_snapshot))
                try:
                    src_conn.backup(dst_conn)
                finally:
                    dst_conn.close()
                    src_conn.close()
            else:
                # If DB doesn't exist on disk yet, initialize it
                init_db()
                src_conn = sqlite3.connect(str(db_path))
                dst_conn = sqlite3.connect(str(temp_db_snapshot))
                try:
                    src_conn.backup(dst_conn)
                finally:
                    dst_conn.close()
                    src_conn.close()

            # Count projects inside snapshot
            projects_count = 0
            try:
                chk_conn = sqlite3.connect(str(temp_db_snapshot))
                c = chk_conn.cursor()
                c.execute("SELECT COUNT(*) FROM projects")
                projects_count = c.fetchone()[0]
                chk_conn.close()
            except Exception as e:
                logger.warning(f"Could not count projects in backup snapshot: {e}")

            # 2. Generate manifest metadata
            manifest_data = {
                "app_name": settings.app_name,
                "version": settings.app_version,
                "created_at": datetime.utcnow().isoformat() + "Z",
                "platform": platform.platform(),
                "python_version": platform.python_version(),
                "projects_count": projects_count,
                "format_version": 1,
            }
            manifest_file = temp_dir_path / "manifest.json"
            manifest_file.write_text(json.dumps(manifest_data, indent=2, ensure_ascii=False), encoding="utf-8")

            # 3. Create zip archive
            with zipfile.ZipFile(backup_zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
                # Add database snapshot
                zf.write(temp_db_snapshot, arcname="pdf_translator.db")
                # Add manifest
                zf.write(manifest_file, arcname="manifest.json")

                # Add projects directory
                if projects_dir.exists():
                    for root, _, files in os.walk(projects_dir):
                        for file in files:
                            full_path = Path(root) / file
                            rel_path = full_path.relative_to(self.data_dir)
                            zf.write(full_path, arcname=str(rel_path.as_posix()))

        logger.info(f"Created backup at {backup_zip_path} with {projects_count} projects.")
        return backup_zip_path, "application/zip"

    def restore_backup(self, zip_file_path: Path) -> dict[str, Any]:
        """
        Safely restores application database and project files from a backup zip archive:
        1. Validates zip file integrity and safety (prevents path traversal / Zip Slip).
        2. Creates safety rollback backup of existing DB if present.
        3. Extracts database and project assets.
        4. Re-bases all absolute paths in database (projects.storage_dir, projects.source_pdf_path,
           pages.image_path, pages.thumbnail_path) to target computer's data_dir.
        5. Refreshes DB engine pool and runs migrations/checks.
        """
        if not zip_file_path.exists() or not zipfile.is_zipfile(zip_file_path):
            raise ValueError("فایل ارائه‌شده یک فایل فشرده (ZIP) معتبر نیست.")

        self.data_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.get_db_path()

        with zipfile.ZipFile(zip_file_path, mode="r") as zf:
            namelist = zf.namelist()

            # Find database in archive
            db_entry = next((name for name in namelist if name == "pdf_translator.db" or name.endswith("/pdf_translator.db")), None)
            if not db_entry:
                raise ValueError("فایل پشتیبان نامعتبر است: دیتابیس `pdf_translator.db` در آرشیو یافت نشد.")

            # Validate against Zip Slip
            for member in zf.infolist():
                resolved = (self.data_dir / member.filename).resolve()
                if not str(resolved).startswith(str(self.data_dir)):
                    raise ValueError(f"مسیر نامعتبر یا ناامن در فایل زیپ شناسایی شد: {member.filename}")

            # Read manifest if present
            manifest_info = {}
            if "manifest.json" in namelist:
                try:
                    manifest_info = json.loads(zf.read("manifest.json").decode("utf-8"))
                except Exception:
                    manifest_info = {}

            # Safety backup of existing database before overwriting
            if db_path.exists():
                safety_bak = db_path.with_suffix(".db.bak")
                try:
                    shutil.copy2(db_path, safety_bak)
                    logger.info(f"Safety backup created at {safety_bak}")
                except Exception as err:
                    logger.warning(f"Could not create safety backup: {err}")

            # Close active SQLAlchemy engine connections
            reset_engine()

            # Extract database
            with zf.open(db_entry) as src, open(db_path, "wb") as dst:
                shutil.copyfileobj(src, dst)

            # Extract projects directory and files
            for member in zf.infolist():
                if member.filename.startswith("projects/") and not member.is_dir():
                    target_file = self.data_dir / member.filename
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(target_file, "wb") as dst:
                        shutil.copyfileobj(src, dst)

        # 4. Critical Step: Rebase all paths in restored SQLite database to this machine's data_dir
        restored_projects_count = 0
        restored_pages_count = 0
        try:
            conn = sqlite3.connect(str(db_path))
            c = conn.cursor()

            c.execute("SELECT id FROM projects")
            rows = c.fetchall()
            restored_projects_count = len(rows)

            for (project_id,) in rows:
                new_project_dir = (self.data_dir / "projects" / project_id).resolve()
                new_source_pdf = (new_project_dir / "source.pdf").resolve()
                new_pages_dir = (new_project_dir / "pages").resolve()

                # Update project paths
                c.execute(
                    "UPDATE projects SET storage_dir = ?, source_pdf_path = ? WHERE id = ?",
                    (str(new_project_dir), str(new_source_pdf), project_id),
                )

                # Update pages image & thumbnail paths
                c.execute(
                    """
                    UPDATE pages SET
                        image_path = ? || '/page_' || page_number || '.png',
                        thumbnail_path = ? || '/page_' || page_number || '_thumb.png'
                    WHERE project_id = ?
                    """,
                    (str(new_pages_dir), str(new_pages_dir), project_id),
                )
                restored_pages_count += c.rowcount

            conn.commit()
            conn.close()
            logger.info(f"Rebased paths for {restored_projects_count} projects and {restored_pages_count} pages.")
        except Exception as err:
            logger.error(f"Error rebasing paths in restored database: {err}", exc_info=True)
            raise ValueError(f"خطا در به‌روزرسانی مسیرهای پروژه‌ها در سیستم جدید: {str(err)}")

        # 5. Reinitialize and refresh DB engine
        reset_engine()
        init_db()

        return {
            "success": True,
            "message": "بازیابی دیتابیس و فایل‌های پروژه‌ها با موفقیت انجام شد.",
            "projects_restored": restored_projects_count,
            "pages_restored": restored_pages_count,
            "target_data_dir": str(self.data_dir),
            "manifest": manifest_info,
        }
