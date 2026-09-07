"""Pytest configuration and fixtures."""
import pytest
import pymupdf as fitz
from pathlib import Path
from sqlmodel import SQLModel, create_engine, Session
from fastapi.testclient import TestClient

from pdf_translator.config import settings
from pdf_translator.adapters.storage.db import get_session
from pdf_translator.web.app import create_app

@pytest.fixture
def temp_workspace(tmp_path):
    """Sets up a clean temporary workspace for tests."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_file = data_dir / "test.db"
    
    settings.data_dir = data_dir
    settings.sqlite_db_path = db_file
    
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    
    yield data_dir, engine

@pytest.fixture
def sample_pdf(tmp_path) -> Path:
    """Generates a multi-page sample PDF for testing."""
    pdf_path = tmp_path / "sample_book.pdf"
    doc = fitz.open()
    
    # Page 1
    p1 = doc.new_page()
    p1.insert_text((50, 50), "Chapter 1: Domain-Driven Design\nAn entity is an object with a distinct identity.", fontsize=12)
    
    # Page 2
    p2 = doc.new_page()
    p2.insert_text((50, 50), "Chapter 2: Value Objects\nValue objects measure, quantify, or describe a thing in the domain.", fontsize=12)
    
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path

@pytest.fixture
def client(temp_workspace):
    _, engine = temp_workspace
    
    def override_get_session():
        with Session(engine) as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session
    return TestClient(app)
