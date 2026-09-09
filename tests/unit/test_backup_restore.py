"""Tests for Backup and Restore Service and API routes."""
import json
import sqlite3
import zipfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, select

from pdf_translator.application.backup_service import BackupService
from pdf_translator.config import settings
from pdf_translator.domain.entities import Project, Page, PageStatus, TranslationProfile
from pdf_translator.web.app import create_app


@pytest.fixture
def backup_test_env(tmp_path, monkeypatch):
    """Creates a self-contained test environment with custom data_dir and db."""
    data_dir = tmp_path / "data_dir"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "pdf_translator.db"

    monkeypatch.setattr(settings, "data_dir", data_dir)
    monkeypatch.setattr(settings, "sqlite_db_path", db_path)

    engine = create_engine(f"sqlite:///{db_path.as_posix()}", echo=False)
    from pdf_translator.adapters.storage import db
    monkeypatch.setattr(db, "engine", engine)
    db.init_db()

    # Create dummy project and page
    with Session(engine) as session:
        profile = session.exec(select(TranslationProfile)).first()
        proj = Project(
            id="proj-test-123",
            title="Distributed Systems Book",
            source_pdf_filename="dist_sys.pdf",
            source_pdf_path=str(data_dir / "projects" / "proj-test-123" / "source.pdf"),
            storage_dir=str(data_dir / "projects" / "proj-test-123"),
            total_pages=2,
            profile_id=profile.id if profile else None,
        )
        session.add(proj)

        p1 = Page(
            project_id="proj-test-123",
            page_number=1,
            status=PageStatus.APPROVED,
            source_text="Chapter 1 Introduction",
            approved_text="فصل اول مقدمه",
            image_path=str(data_dir / "projects" / "proj-test-123" / "pages" / "page_1.png"),
            thumbnail_path=str(data_dir / "projects" / "proj-test-123" / "pages" / "page_1_thumb.png"),
        )
        session.add(p1)
        session.commit()

    # Create dummy physical files on disk
    project_dir = data_dir / "projects" / "proj-test-123"
    pages_dir = project_dir / "pages"
    images_dir = project_dir / "images"
    pages_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    (project_dir / "source.pdf").write_bytes(b"%PDF-1.5 test content")
    (pages_dir / "page_1.png").write_bytes(b"\x89PNG test page image")
    (pages_dir / "page_1_thumb.png").write_bytes(b"\x89PNG test thumb image")
    (images_dir / "page_1_img_1.png").write_bytes(b"\x89PNG test extracted diagram")

    return {
        "data_dir": data_dir,
        "db_path": db_path,
        "engine": engine,
        "project_id": "proj-test-123",
    }


def test_create_backup_archive(backup_test_env, tmp_path):
    """Verifies that create_backup produces a valid zip with db, manifest, and project files."""
    data_dir = backup_test_env["data_dir"]
    service = BackupService(data_dir=data_dir)

    out_dir = tmp_path / "exports"
    zip_path, mime_type = service.create_backup(output_dir=out_dir)

    assert zip_path.exists()
    assert mime_type == "application/zip"
    assert zipfile.is_zipfile(zip_path)

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        assert "pdf_translator.db" in names
        assert "manifest.json" in names
        assert "projects/proj-test-123/source.pdf" in names
        assert "projects/proj-test-123/pages/page_1.png" in names
        assert "projects/proj-test-123/images/page_1_img_1.png" in names

        # Check manifest
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        assert manifest["projects_count"] == 1
        assert manifest["format_version"] == 1


def test_restore_backup_and_rebase_paths(backup_test_env, tmp_path, monkeypatch):
    """
    Simulates moving a backup from Machine A to Machine B:
    Verifies that files are restored and all paths in SQLite are updated to Machine B's data_dir.
    """
    machine_a_dir = backup_test_env["data_dir"]
    service_a = BackupService(data_dir=machine_a_dir)

    # 1. Create backup on Machine A
    zip_path, _ = service_a.create_backup()

    # 2. Simulate Machine B with a completely different directory path
    machine_b_dir = tmp_path / "machine_b_user" / "target_data"
    machine_b_dir.mkdir(parents=True, exist_ok=True)
    machine_b_db = machine_b_dir / "pdf_translator.db"

    monkeypatch.setattr(settings, "data_dir", machine_b_dir)
    monkeypatch.setattr(settings, "sqlite_db_path", machine_b_db)

    service_b = BackupService(data_dir=machine_b_dir)
    result = service_b.restore_backup(zip_path)

    assert result["success"] is True
    assert result["projects_restored"] == 1

    # Verify physical files exist in Machine B's location
    restored_proj_dir = machine_b_dir / "projects" / "proj-test-123"
    assert (restored_proj_dir / "source.pdf").exists()
    assert (restored_proj_dir / "pages" / "page_1.png").exists()
    assert (restored_proj_dir / "images" / "page_1_img_1.png").exists()

    # Verify database was rebased to Machine B's paths
    conn = sqlite3.connect(str(machine_b_db))
    c = conn.cursor()

    c.execute("SELECT storage_dir, source_pdf_path FROM projects WHERE id = ?", ("proj-test-123",))
    storage_dir, source_pdf_path = c.fetchone()

    # Must point to Machine B and NOT Machine A!
    assert str(machine_b_dir) in storage_dir
    assert str(machine_a_dir) not in storage_dir
    assert str(machine_b_dir) in source_pdf_path
    assert str(machine_a_dir) not in source_pdf_path
    assert storage_dir == str(restored_proj_dir)
    assert source_pdf_path == str(restored_proj_dir / "source.pdf")

    # Check page paths
    c.execute("SELECT image_path, thumbnail_path FROM pages WHERE project_id = ?", ("proj-test-123",))
    img_path, thumb_path = c.fetchone()
    assert str(machine_b_dir) in img_path
    assert str(machine_a_dir) not in img_path
    assert str(machine_b_dir) in thumb_path

    conn.close()


def test_restore_invalid_zip_fails(tmp_path):
    """Verifies that invalid or non-db zip files are cleanly rejected with ValueError."""
    service = BackupService(data_dir=tmp_path)

    # 1. Non-zip file
    fake_file = tmp_path / "corrupt.zip"
    fake_file.write_bytes(b"not a real zip file content")
    with pytest.raises(ValueError, match="فایل ارائه‌شده یک فایل فشرده"):
        service.restore_backup(fake_file)

    # 2. Zip file missing pdf_translator.db
    empty_zip = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty_zip, "w") as zf:
        zf.writestr("some_random_file.txt", "hello")

    with pytest.raises(ValueError, match="دیتابیس `pdf_translator.db` در آرشیو یافت نشد"):
        service.restore_backup(empty_zip)


def test_backup_api_export_and_restore(backup_test_env, tmp_path, monkeypatch):
    """Tests FastAPI endpoints GET /api/backup/export and POST /api/backup/restore."""
    app = create_app()
    client = TestClient(app)

    # 1. Export backup via API
    res = client.get("/api/backup/export")
    assert res.status_code == 200
    assert "application/zip" in res.headers["content-type"]
    assert len(res.content) > 1000

    temp_zip = tmp_path / "downloaded_backup.zip"
    temp_zip.write_bytes(res.content)
    assert zipfile.is_zipfile(temp_zip)

    # 2. Restore backup via API
    with open(temp_zip, "rb") as f:
        res_post = client.post(
            "/api/backup/restore",
            files={"backup_file": ("my_backup.zip", f, "application/zip")}
        )

    assert res_post.status_code == 200
    data = res_post.json()
    assert data["success"] is True
    assert data["projects_restored"] >= 1

    # 3. Invalid extension test
    with open(temp_zip, "rb") as f:
        bad_res = client.post(
            "/api/backup/restore",
            files={"backup_file": ("backup.tar.gz", f, "application/gzip")}
        )
    assert bad_res.status_code == 400
    assert "باید دارای پسوند .zip باشد" in bad_res.json()["detail"]
