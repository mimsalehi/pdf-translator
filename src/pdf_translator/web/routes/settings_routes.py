"""Web and API routes for Profiles and Settings."""
from pathlib import Path
from fastapi import APIRouter, Depends, Request, Form, HTTPException, File, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session
from datetime import datetime

from pdf_translator.adapters.storage.db import get_session
from pdf_translator.adapters.storage.sqlite_repo import SQLiteProfileRepository
from pdf_translator.domain.entities import TranslationProfile
from pdf_translator.domain.enums import ProviderType
from pdf_translator.application.backup_service import BackupService

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    session: Session = Depends(get_session)
):
    profile_repo = SQLiteProfileRepository(session)
    profile = profile_repo.get_default()
    
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={"profile": profile, "title": "Settings & AI Profiles"}
    )

@router.post("/settings")
async def update_settings(
    name: str = Form(...),
    provider_type: ProviderType = Form(...),
    model_name: str = Form(...),
    api_key: str = Form(""),
    system_prompt: str = Form(...),
    temperature: float = Form(0.3),
    session: Session = Depends(get_session)
):
    profile_repo = SQLiteProfileRepository(session)
    profile = profile_repo.get_default()
    
    profile.name = name.strip()
    profile.provider_type = provider_type
    profile.model_name = model_name.strip()
    if api_key.strip():
        profile.api_key = api_key.strip()
    profile.system_prompt = system_prompt.replace("\r\n", "\n").replace("\r", "\n").strip()
    profile.temperature = temperature
    profile.updated_at = datetime.utcnow()
    
    profile_repo.save(profile)
    return RedirectResponse(url="/settings?saved=true", status_code=303)

@router.post("/api/browser/launch-login")
async def launch_browser_login(
    target_url: str = Form("https://chatgpt.com")
):
    from pdf_translator.adapters.providers.browser_manager import BrowserManager
    manager = BrowserManager.get_instance()
    import asyncio
    asyncio.create_task(manager.open_browser_for_login(target_url))
    return {"success": True, "message": f"Browser opened for {target_url}. Please log in."}

@router.post("/api/browser/new-chat")
async def reset_browser_chat_thread():
    from pdf_translator.adapters.providers.browser_manager import BrowserManager
    manager = BrowserManager.get_instance()
    manager.reset_conversation_thread("all")
    return {"success": True, "message": "Conversation thread reset. Next translation will start a fresh chat."}


@router.get("/api/backup/export")
async def export_backup():
    """Creates and downloads a complete zip backup archive containing SQLite DB and all projects."""
    try:
        service = BackupService()
        zip_path, media_type = service.create_backup()
        return FileResponse(
            path=zip_path,
            media_type=media_type,
            filename=zip_path.name,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"خطا در ایجاد فایل پشتیبان: {str(e)}"
        )


@router.post("/api/backup/restore")
async def restore_backup(
    backup_file: UploadFile = File(...)
):
    """Restores database and project files from uploaded zip archive and rebases paths."""
    if not backup_file.filename or not backup_file.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="فایل ارسالی باید دارای پسوند .zip باشد."
        )

    import tempfile
    import shutil
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        temp_path = Path(tmp.name)
        try:
            shutil.copyfileobj(backup_file.file, tmp)
        finally:
            tmp.close()

    try:
        service = BackupService()
        result = service.restore_backup(temp_path)
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"خطای سرور در بازیابی فایل پشتیبان: {str(e)}"
        )
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
