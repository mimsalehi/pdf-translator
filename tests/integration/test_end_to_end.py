"""Comprehensive End-to-End Vertical Slice Tests for PDF Book Translator."""
from pathlib import Path
from fastapi.testclient import TestClient

def test_full_hitl_translation_lifecycle(client: TestClient, sample_pdf: Path):
    # 0. Check static assets are served correctly
    css_resp = client.get("/static/css/app.css")
    assert css_resp.status_code == 200
    assert "body" in css_resp.text

    js_resp = client.get("/static/js/app.js")
    assert js_resp.status_code == 200
    assert "openModal" in js_resp.text

    # 1. Start with clean dashboard
    response = client.get("/")
    assert response.status_code == 200
    assert "Projects" in response.text

    # 2. Upload PDF & Create Project
    with open(sample_pdf, "rb") as f:
        create_resp = client.post(
            "/api/projects",
            data={
                "title": "Domain-Driven Design",
                "source_language": "English",
                "target_language": "Persian",
            },
            files={"file": ("sample_book.pdf", f, "application/pdf")},
        )
    assert create_resp.status_code == 201
    project_id = create_resp.json()["project_id"]
    total_pages = create_resp.json()["total_pages"]
    assert total_pages == 2

    # 3. View Project Detail Page
    detail_resp = client.get(f"/projects/{project_id}")
    assert detail_resp.status_code == 200
    assert "Domain-Driven Design" in detail_resp.text
    assert "Page 1" in detail_resp.text
    assert "Page 2" in detail_resp.text

    # 4. View Page 1 Workspace
    page1_resp = client.get(f"/projects/{project_id}/pages/1")
    assert page1_resp.status_code == 200
    assert "Page 1 of 2" in page1_resp.text

    # 5. Operator edits source text on Page 1
    edit_source_resp = client.put(
        f"/api/projects/{project_id}/pages/1/source-text",
        json={"source_text": "Chapter 1: Domain-Driven Design\nAn Entity is an object with an identity."},
    )
    assert edit_source_resp.status_code == 200
    assert edit_source_resp.json()["success"] is True

    # 6. Operator approves Page 1 for AI Translation (HITL Approval)
    approve_for_ai = client.post(f"/api/projects/{project_id}/pages/1/approve-for-translation")
    assert approve_for_ai.status_code == 200
    assert approve_for_ai.json()["status"] == "APPROVED_FOR_TRANSLATION"

    # 7. AI Translation is executed
    translate_resp = client.post(
        f"/api/projects/{project_id}/pages/1/translate",
        json={"custom_instructions": "Keep terminology clean"},
    )
    assert translate_resp.status_code == 200
    trans_data = translate_resp.json()
    assert trans_data["success"] is True
    assert "ترجمه" in trans_data["translated_text"]
    assert trans_data["status"] == "IN_REVIEW"

    # 8. Operator edits the translated draft text
    draft_resp = client.put(
        f"/api/projects/{project_id}/pages/1/translation-draft",
        json={"draft_text": "فصل ۱: طراحی دامنه‌محور\nیک موجودیت شیئی با هویت مشخص است."},
    )
    assert draft_resp.status_code == 200
    assert draft_resp.json()["success"] is True

    # 9. Operator approves final translation (HITL Final Approval)
    final_approve_resp = client.post(
        f"/api/projects/{project_id}/pages/1/approve-final",
        json={"final_text": "فصل ۱: طراحی دامنه‌محور\nیک موجودیت شیئی با هویت مشخص است."},
    )
    assert final_approve_resp.status_code == 200
    assert final_approve_resp.json()["status"] == "APPROVED"

    # 10. Export Page 1 to Markdown and DOCX
    page_md_resp = client.get(f"/api/projects/{project_id}/pages/1/export?format=md")
    assert page_md_resp.status_code == 200
    assert "Page 1" in page_md_resp.text
    assert "طراحی دامنه‌محور" in page_md_resp.text

    page_docx_resp = client.get(f"/api/projects/{project_id}/pages/1/export?format=docx")
    assert page_docx_resp.status_code == 200
    assert len(page_docx_resp.content) > 0

    # 11. Assemble and Export Full Book (Markdown & DOCX)
    book_md_resp = client.get(f"/api/projects/{project_id}/export?format=md")
    assert book_md_resp.status_code == 200
    assert "Domain-Driven Design" in book_md_resp.text

    book_docx_resp = client.get(f"/api/projects/{project_id}/export?format=docx")
    assert book_docx_resp.status_code == 200
    assert len(book_docx_resp.content) > 0

    # 12. Settings view and update
    settings_view = client.get("/settings")
    assert settings_view.status_code == 200
    assert "Translation Profiles & AI Engines" in settings_view.text

    update_settings = client.post(
        "/settings",
        data={
            "name": "Custom Persian Profile",
            "provider_type": "mock",
            "model_name": "mock-model",
            "api_key": "test-key-123",
            "system_prompt": "Custom prompt rules",
            "temperature": 0.2,
        },
        follow_redirects=True,
    )
    assert update_settings.status_code == 200
    assert "Custom Persian Profile" in update_settings.text

    # 13. Delete Project and cascade cleanup
    delete_resp = client.delete(f"/api/projects/{project_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["success"] is True

    # Ensure project detail returns 404
    detail_after_del = client.get(f"/projects/{project_id}")
    assert detail_after_del.status_code == 404
