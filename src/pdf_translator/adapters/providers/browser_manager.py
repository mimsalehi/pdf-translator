"""Native Chrome CDP Automation Manager with silent background tab execution."""
from pathlib import Path
import os
import shutil
import asyncio
import subprocess
import re
from typing import Optional, Dict
from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page as PlaywrightPage
from pdf_translator.config import settings

def sanitize_markdown_code_blocks(md_text: str) -> str:
    """Removes excessive empty lines inside code fences while preserving exact indentation."""
    def clean_code(match):
        fence_start = match.group(1)
        body = match.group(2)
        fence_end = match.group(3)
        cleaned_lines = [line.rstrip() for line in body.split("\n")]
        res = "\n".join(cleaned_lines)
        res = re.sub(r'\n{3,}', '\n\n', res).strip("\n")
        return f"{fence_start}{res}\n{fence_end}"
    
    return re.sub(r'(```[a-zA-Z0-9_-]*\n)(.*?)(```)', clean_code, md_text, flags=re.DOTALL)

def find_chrome_executable() -> str:
    """Finds Google Chrome, Chromium, or Edge executable on Windows, Linux, and macOS."""
    import sys
    if sys.platform == "win32":
        win_candidates = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
        ]
        for p in win_candidates:
            if os.path.exists(p):
                return p
        return shutil.which("chrome") or shutil.which("msedge") or "chrome"

    elif sys.platform == "darwin":
        mac_candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ]
        for p in mac_candidates:
            if os.path.exists(p):
                return p
        return shutil.which("google-chrome") or "google-chrome"

    else:
        linux_candidates = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/snap/bin/chromium",
            "/usr/bin/brave-browser",
        ]
        for p in linux_candidates:
            if os.path.exists(p):
                return p
        return shutil.which("google-chrome") or shutil.which("chromium") or "google-chrome"

def convert_chat_html_to_markdown(html_content: str) -> str:
    """
    Converts browser assistant HTML to clean Markdown.
    Extracts <pre><code> blocks cleanly, preserving 100% exact syntax, indentation,
    variable names, and language tags, while removing toolbar 'Copy code' buttons.
    """
    from bs4 import BeautifulSoup
    from markdownify import markdownify as md

    soup = BeautifulSoup(html_content, "html.parser")

    # Strip buttons, forms, svgs, edit controls, and suggestion chips
    for el in soup.find_all(["button", "form", "svg"]):
        el.decompose()
    for tag in soup.find_all(attrs={"class": re.compile(r'(?:suggestion|action|toolbar|feedback|chip|button)', re.I)}):
        tag.decompose()

    code_blocks = []
    for idx, pre in enumerate(soup.find_all("pre")):
        code_tag = pre.find("code")
        lang = ""
        if code_tag:
            classes = code_tag.get("class", [])
            for c in classes:
                if c.startswith("language-"):
                    lang = c.replace("language-", "").strip()
                    break
            code_text = code_tag.get_text()
        else:
            code_text = pre.get_text()
            
        code_text = code_text.strip("\r\n")
        # Remove any leading 'Copy code' or language name toolbar artifact
        code_text = re.sub(r'^(?:[a-zA-Z0-9_-]+\s*)?Copy(?:\s*code)?\s*\n', '', code_text, flags=re.IGNORECASE)
        
        token = f"CODEBLOCKTOKEN{idx}XYZ"
        code_blocks.append((token, lang, code_text))
        
        # Replace pre with placeholder text in a paragraph
        new_p = soup.new_tag("p")
        new_p.string = token
        pre.replace_with(new_p)

    # 2. Convert remaining HTML (prose, headings, lists) to Markdown
    raw_md = md(str(soup), heading_style="ATX", bullets="-").strip()

    # 3. Restore code blocks with exact language tag and perfect indents
    for token, lang, code_text in code_blocks:
        fence = f"```{lang}\n{code_text}\n```" if lang else f"```\n{code_text}\n```"
        raw_md = raw_md.replace(token, fence)

    # 4. Strip LLM wrapper tags if present (e.g. <source_document>, </source_document>, ```markdown)
    raw_md = re.sub(r'<\/?source_document>', '', raw_md, flags=re.IGNORECASE)
    raw_md = re.sub(r'<\/?translation>', '', raw_md, flags=re.IGNORECASE)

    # Clean double empty lines inside Markdown
    raw_md = re.sub(r"\n{3,}", "\n\n", raw_md)
    return sanitize_markdown_code_blocks(raw_md.strip())

class BrowserManager:
    """
    Manages native Google Chrome automation via Chrome DevTools Protocol (CDP).
    Runs silently in background tabs without switching or stealing focus from the workspace.
    Zero bot detection risk (genuine native Chrome, navigator.webdriver = False).
    """
    _instance: Optional["BrowserManager"] = None

    def __init__(self, user_data_dir: Optional[Path] = None):
        self.user_data_dir = user_data_dir or (settings.get_data_dir() / "browser_profile")
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        self.chrome_path = find_chrome_executable()
        self.cdp_url = "http://127.0.0.1:9222"
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._session_locks: Dict[str, asyncio.Lock] = {}
        self._global_connect_lock = asyncio.Lock()
        self._reset_thread_flags: Dict[str, bool] = {}

    def _get_lock(self, session_tag: str = "default") -> asyncio.Lock:
        if session_tag not in self._session_locks:
            self._session_locks[session_tag] = asyncio.Lock()
        return self._session_locks[session_tag]

    async def _safe_insert_multiline_prompt(self, page: PlaywrightPage, prompt: str):
        """
        Fast and atomic multiline prompt insertion into ProseMirror/rich-text editors.
        Inserts instantly via document.execCommand('insertText') without Enter submits.
        """
        clean_text = (prompt or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not clean_text:
            return

        # 1. Primary Method: Fast atomic document.execCommand('insertText') on contenteditable DIV/textarea
        inserted = False
        try:
            inserted = await page.evaluate("""(text) => {
                const el = document.querySelector('div#prompt-textarea[contenteditable="true"]')
                        || document.querySelector('#prompt-textarea')
                        || document.querySelector('rich-textarea div[contenteditable="true"]')
                        || document.querySelector('div.ql-editor')
                        || document.querySelector('div.ProseMirror')
                        || document.querySelector('div[contenteditable="true"]')
                        || document.querySelector('textarea')
                        || document.activeElement;
                if (!el) return false;
                el.focus();
                document.execCommand('selectAll', false, null);
                document.execCommand('delete', false, null);
                const ok = document.execCommand('insertText', false, text);
                try {
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                } catch(e) {}
                const curLen = (el.innerText || el.textContent || el.value || '').trim().length;
                return ok && curLen >= Math.min(text.length * 0.8, 20);
            }""", clean_text)
        except Exception:
            inserted = False

        if inserted:
            return

        # 2. If initial execCommand did not insert, ensure editor click and retry
        editor_loc = page.locator('#prompt-textarea, rich-textarea div[contenteditable="true"], div.ql-editor, div.ProseMirror, div[contenteditable="true"], textarea').first
        try:
            if await editor_loc.is_visible(timeout=800):
                await editor_loc.click(force=True, timeout=1200)
        except Exception:
            pass

        try:
            inserted = await page.evaluate("""(text) => {
                const el = document.activeElement || document.querySelector('#prompt-textarea');
                if (!el) return false;
                return document.execCommand('insertText', false, text);
            }""", clean_text)
        except Exception:
            inserted = False

        # 3. Fallback: direct atomic text insertion via CDP
        if not inserted:
            await page.keyboard.insert_text(clean_text)
    async def _submit_and_verify_prompt(
        self,
        page: PlaywrightPage,
        provider_name: str,
        editor_selector: str,
        send_button_selector: str,
        stop_button_selector: str,
        user_turn_selector: Optional[str] = None,
        max_wait_seconds: float = 6.0,
    ) -> bool:
        """
        Submits prompt once and verifies generation starts without Enter key spamming.
        """
        baseline_user_count = 0
        if user_turn_selector:
            try:
                baseline_user_count = await page.locator(user_turn_selector).count()
            except Exception:
                baseline_user_count = 0

        editor = page.locator(editor_selector).first
        send_btn = page.locator(
            f"{send_button_selector}, button.composer-submit-button-color:not([aria-label='Start Voice']), button[data-testid='send-button'], button#composer-submit-button, button[aria-label*='Send' i]"
        ).first
        stop_btn = page.locator(stop_button_selector).first

        btn_is_enabled = False
        try:
            if await send_btn.is_visible(timeout=500):
                btn_is_enabled = await page.evaluate("""(sel) => {
                    const btn = document.querySelector(sel)
                             || document.querySelector('button[data-testid="send-button"]')
                             || document.querySelector('button#composer-submit-button')
                             || document.querySelector('button.composer-submit-button-color:not([aria-label="Start Voice"])');
                    if (!btn) return false;
                    if (btn.disabled) return false;
                    if (btn.getAttribute('aria-disabled') === 'true') return false;
                    if (btn.getAttribute('data-disabled') === 'true') return false;
                    if (btn.classList.contains('disabled')) return false;
                    return true;
                }""", send_button_selector)
        except Exception:
            btn_is_enabled = False

        # 2. Trigger submission ONCE
        if btn_is_enabled:
            try:
                await send_btn.click(timeout=1000)
            except Exception:
                pass
        else:
            try:
                if await editor.is_visible(timeout=300):
                    await editor.focus()
                    await asyncio.sleep(0.05)
                await page.evaluate("""() => {
                    const el = document.querySelector('div#prompt-textarea.ProseMirror p')
                            || document.querySelector('div#prompt-textarea p')
                            || document.querySelector('div#prompt-textarea')
                            || document.querySelector('form textarea')
                            || document.querySelector('textarea');
                    if (el) el.focus();
                }""")
                await page.keyboard.press("Enter")
            except Exception:
                pass

        start_time = asyncio.get_event_loop().time()
        retried = False
        while (asyncio.get_event_loop().time() - start_time) < max_wait_seconds:
            await asyncio.sleep(0.08)

            try:
                if await stop_btn.is_visible(timeout=30):
                    return True
            except Exception:
                pass

            if user_turn_selector:
                try:
                    curr_user_count = await page.locator(user_turn_selector).count()
                    if curr_user_count > baseline_user_count:
                        return True
                except Exception:
                    pass

            try:
                cur_text = await page.evaluate("""(sel) => {
                    const el = document.querySelector(sel);
                    return el ? (el.innerText || el.value || '').trim() : '';
                }""", editor_selector)
                if len(cur_text) == 0:
                    return True
            except Exception:
                pass

            # If 0.8s passed with zero response, attempt ONE single fallback retry
            if not retried and (asyncio.get_event_loop().time() - start_time) > 0.8:
                retried = True
                try:
                    if await send_btn.is_visible(timeout=100):
                        await send_btn.click(timeout=300)
                    if await editor.is_visible(timeout=100):
                        await editor.focus()
                        await page.keyboard.press("Enter")
                except Exception:
                    pass
        try:
            if await stop_btn.is_visible(timeout=100):
                return True
        except Exception:
            pass

        if user_turn_selector:
            try:
                if await page.locator(user_turn_selector).count() > baseline_user_count:
                    return True
            except Exception:
                pass

        raise RuntimeError(
            f"ارسال پیام به {provider_name} با کلید Enter یا دکمه ارسال انجام نشد. لطفاً تب مرورگر را بررسی نمایید."
        )
    @classmethod
    def get_instance(cls) -> "BrowserManager":
        if cls._instance is None:
            cls._instance = BrowserManager()
        return cls._instance

    def _start_native_chrome_process(self, start_url: str = "https://chatgpt.com"):
        """Launches real native Google Chrome with debugging port enabled."""
        cmd = [
            self.chrome_path,
            "--remote-debugging-port=9222",
            f"--user-data-dir={self.user_data_dir}",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
            "--start-maximized",
        ]
        import sys
        popen_kwargs = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            # Windows detached process flags
            creation_flags = 0
            if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
                creation_flags |= subprocess.CREATE_NEW_PROCESS_GROUP
            if hasattr(subprocess, "DETACHED_PROCESS"):
                creation_flags |= subprocess.DETACHED_PROCESS
            popen_kwargs["creationflags"] = creation_flags
        else:
            popen_kwargs["start_new_session"] = True

        subprocess.Popen(cmd, **popen_kwargs)

    async def _clean_disconnect(self):
        """Cleanly disconnects and resets Playwright / Browser instances upon closed transport."""
        try:
            if self._browser:
                await self._browser.close()
        except Exception:
            pass
        self._browser = None

        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
        self._playwright = None

    async def _ensure_cdp_connected(self, default_url: str):
        """Ensures active and healthy CDP connection to native Chrome on port 9222."""
        if self._browser is not None:
            try:
                if self._browser.is_connected():
                    return
            except Exception:
                pass
            await self._clean_disconnect()

        if self._playwright is None:
            try:
                self._playwright = await async_playwright().start()
            except NotImplementedError as e:
                raise RuntimeError(
                    "خطای NotImplementedError در اتصال به مرورگر در سیستم‌عامل ویندوز رخ داده است.\n"
                    "علت: اجرای سرور با فلگ --reload در ویندوز باعث فعال شدن SelectorEventLoop می‌شود که از subprocess پشتیبانی نمی‌کند.\n"
                    "راه‌حل: لطفاً سرور را بدون --reload اجرا کنید:\n"
                    "python -m pdf_translator.main یا uvicorn pdf_translator.web.app:app"
                ) from e
        # Connect to port 9222
        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(self.cdp_url, timeout=2000)
        except Exception:
            self._start_native_chrome_process(default_url)
            for _ in range(12):
                await asyncio.sleep(1.0)
                try:
                    self._browser = await self._playwright.chromium.connect_over_cdp(self.cdp_url, timeout=2000)
                    break
                except Exception:
                    pass

        if self._browser is None:
            hint = "launch_chrome_ai.bat" if sys.platform == "win32" else "./launch_chrome_ai.sh"
            raise RuntimeError(f"Could not connect to Google Chrome on port 9222. Please start Chrome with {hint}")

    async def get_or_create_page(
        self,
        domain_keyword: str,
        default_url: str,
        force_new_chat: bool = False,
        session_tag: str = "default"
    ) -> PlaywrightPage:
        """Connects over CDP and retrieves or creates a tab dedicated to this session_tag."""
        async with self._global_connect_lock:
            await self._ensure_cdp_connected(default_url)

        flag_key = f"{domain_keyword}:{session_tag}"
        should_new_chat = force_new_chat or self._reset_thread_flags.pop(flag_key, False) or self._reset_thread_flags.pop(domain_keyword, False) or self._reset_thread_flags.pop("all", False)

        for attempt in range(2):
            try:
                context = self._browser.contexts[0] if self._browser.contexts else await self._browser.new_context()

                # 1. Search for existing tab dedicated to this session_tag
                target_page = None
                for p in context.pages:
                    if domain_keyword in p.url and getattr(p, "_pdf_session_tag", "default") == session_tag:
                        target_page = p
                        break

                # 2. If no tab found for this session_tag
                # 2. If no tab found with exact session_tag, check if any open tab for this provider exists
                if target_page is None:
                    matching_pages = [p for p in context.pages if domain_keyword in p.url]
                    if matching_pages:
                        # Adopt existing open tab for this provider!
                        target_page = matching_pages[0]
                        setattr(target_page, "_pdf_session_tag", session_tag)
                    else:
                        # Only open a new tab if no tab for this provider is open at all!
                        target_page = await context.new_page()
                        setattr(target_page, "_pdf_session_tag", session_tag)
                        await target_page.goto(default_url, wait_until="domcontentloaded", timeout=20000)
                        should_new_chat = False

                # 3. Handle fresh new chat thread in this tab
                if should_new_chat:
                    try:
                        new_chat_btn = target_page.locator('button[data-testid="create-new-chat-button"], a[data-testid="create-new-chat-button"], button[aria-label*="New chat" i], button[aria-label*="چت جدید" i]').first
                        if await new_chat_btn.is_visible(timeout=1200):
                            await new_chat_btn.click()
                            await asyncio.sleep(0.8)
                        else:
                            await target_page.keyboard.press("Control+Shift+O")
                            await asyncio.sleep(0.5)
                    except Exception:
                        pass
                try:
                    await target_page.context.grant_permissions(["clipboard-read", "clipboard-write"])
                except Exception:
                    pass
                return target_page
            except Exception as e:
                if attempt == 0:
                    await self._clean_disconnect()
                    async with self._global_connect_lock:
                        await self._ensure_cdp_connected(default_url)
                    await asyncio.sleep(1.0)
                else:
                    raise e
    async def open_browser_for_login(self, target_url: str = "https://chatgpt.com"):
        """Opens or brings the native Chrome browser to the front for manual logging in."""
        keyword = "chatgpt" if "chatgpt" in target_url else ("gemini" if "gemini" in target_url else "claude")
        page = await self.get_or_create_page(keyword, target_url, force_new_chat=True)
        try:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
            await page.bring_to_front()
        except Exception:
            pass
        return page

    def reset_conversation_thread(self, provider_key: str = "all"):
        """Forces the next translation to start a fresh chat thread."""
        self._reset_thread_flags[provider_key] = True

    async def _start_fresh_chat(self, page: PlaywrightPage, default_url: str = "https://chatgpt.com"):
        """Opens a clean new chat conversation in the current tab to avoid context bloat or stuck threads."""
        try:
            clicked = await page.evaluate("""() => {
                const btn = document.querySelector('button[data-testid="create-new-chat-button"]')
                         || document.querySelector('a[data-testid="create-new-chat-button"]')
                         || document.querySelector('button[aria-label*="New chat" i]');
                if (btn) {
                    btn.click();
                    return true;
                }
                return false;
            }""")
            if clicked:
                await asyncio.sleep(0.8)
                return
        except Exception:
            pass
        try:
            await page.goto(default_url, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(0.8)
        except Exception:
            pass
    async def translate_with_chatgpt(self, prompt: str, timeout_seconds: int = 360, session_tag: str = "default") -> str:
        """Automates translation silently in the background ChatGPT tab without tab switching."""
        async with self._get_lock(session_tag):
            for attempt in range(2):
                try:
                    page = await self.get_or_create_page("chatgpt.com", "https://chatgpt.com", force_new_chat=False, session_tag=session_tag)
                    return await self._do_chatgpt_translation(page, prompt, timeout_seconds)
                except Exception as e:
                    err_msg = str(e).lower()
                    if ("crash" in err_msg or "closed" in err_msg or "destroyed" in err_msg or "session closed" in err_msg) and attempt == 0:
                        logger.warning("ChatGPT tab crashed or closed. Resetting connection and retrying...")
                        await self._clean_disconnect()
                        await asyncio.sleep(2.0)
                        continue
                    raise e
    async def _do_chatgpt_translation(self, page: PlaywrightPage, prompt: str, timeout_seconds: int = 360) -> str:
        # Dismiss any ChatGPT popups/overlays if present (e.g. "Stay logged out", "What's new")
        try:
            await page.evaluate("""() => {
                const dismissBtns = document.querySelectorAll(
                    'button[aria-label="Close"], [data-testid="close-button"], button[aria-label="Dismiss"]'
                );
                for (const b of dismissBtns) {
                    try { b.click(); } catch(e) {}
                }
            }""")
        except Exception:
            pass

        # Press Escape to dismiss any stray popovers, tooltips, or open menus
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        # Locate and focus visible editor (wait up to 20s if tab is hydrating)
        editor = page.locator("div#prompt-textarea, div.ProseMirror, div[contenteditable='true']").first
        await editor.wait_for(state="visible", timeout=20000)
        try:
            await editor.click(force=True, timeout=1500)
        except Exception:
            pass

        # 1. Clear input completely
        try:
            await page.keyboard.press("ControlOrMeta+A")
            await page.keyboard.press("Backspace")
        except Exception:
            pass

        # Record baseline identity of the last assistant turn BEFORE sending
        baseline_info = await page.evaluate("""() => {
            const assts = document.querySelectorAll('div[data-message-author-role="assistant"]');
            if (assts.length === 0) return { lastId: null };
            const last = assts[assts.length - 1];
            return {
                lastId: last.getAttribute('data-message-id') || (last.textContent || '').trim().substring(0, 50)
            };
        }""")

        # 2. Paste prompt
        await self._safe_insert_multiline_prompt(page, prompt)

        # 3. Press Enter (ChatGPT sends automatically!)
        await page.keyboard.press("Enter")

        # Fast backup check: if editor still has text, click send button or press Enter again
        await asyncio.sleep(0.08)
        try:
            ed_has_text = await page.evaluate("""() => {
                const el = document.querySelector('div#prompt-textarea');
                return el && (el.innerText || el.textContent || '').trim().length > 0;
            }""")
            if ed_has_text:
                btn = page.locator('form button[data-testid="send-button"], form button#composer-submit-button, button[aria-label*="Send" i]:not([aria-label="Start Voice"])').first
                if await btn.is_visible(timeout=300):
                    await btn.click(force=True, timeout=500)
                else:
                    await page.keyboard.press("Enter")
        except Exception:
            pass

        # 4. Wait for response to finish
        start_time = asyncio.get_event_loop().time()
        stop_btn = page.locator('button[data-testid="stop-button"], button[aria-label*="Stop" i], button[aria-label*="توقف" i]').first
        prev_len = 0
        stable_count = 0
        extracted_html = None

        while (asyncio.get_event_loop().time() - start_time) < timeout_seconds:
            await asyncio.sleep(0.15)
            is_stopping = False
            try:
                is_stopping = await stop_btn.is_visible()
            except Exception:
                is_stopping = False

            check = await page.evaluate("""(base) => {
                const assts = document.querySelectorAll('div[data-message-author-role="assistant"]');
                if (assts.length === 0) return null;
                const last = assts[assts.length - 1];
                const curId = last.getAttribute('data-message-id') || (last.textContent || '').trim().substring(0, 50);

                if (base.lastId && curId === base.lastId) {
                    return null;
                }

                const mdBox = last.querySelector('.markdown, div.prose, div[class*="markdown"]') || last;
                return {
                    text: (mdBox.textContent || '').trim(),
                    html: mdBox.innerHTML
                };
            }""", baseline_info)

            if not check:
                continue

            cur_text = check["text"]

            if not is_stopping and len(cur_text) > 0:
                if len(cur_text) == prev_len:
                    stable_count += 1
                else:
                    prev_len = len(cur_text)
                    stable_count = 0

                if stable_count >= 1:
                    extracted_html = check["html"]
                    break

        if not extracted_html:
            extracted_html = await page.evaluate("""() => {
                const assts = document.querySelectorAll('div[data-message-author-role="assistant"]');
                if (assts.length === 0) return null;
                const last = assts[assts.length - 1];
                const mdBox = last.querySelector('.markdown, div.prose, div[class*="markdown"]') || last;
                return mdBox.innerHTML || last.innerHTML;
            }""")

        if not extracted_html:
            raise RuntimeError("پاسخ جدیدی از هوش مصنوعی دریافت نشد. لطفاً تب کروم را بررسی نمایید.")

        return convert_chat_html_to_markdown(extracted_html)
    async def translate_with_gemini(self, prompt: str, timeout_seconds: int = 360, session_tag: str = "default") -> str:
        """Automates translation silently in the background Google Gemini tab."""
        async with self._get_lock(session_tag):
            for attempt in range(2):
                try:
                    page = await self.get_or_create_page("gemini.google.com", "https://gemini.google.com/app", force_new_chat=False, session_tag=session_tag)
                    return await self._do_gemini_translation(page, prompt, timeout_seconds)
                except Exception as e:
                    err_msg = str(e).lower()
                    if ("crash" in err_msg or "closed" in err_msg or "destroyed" in err_msg or "session closed" in err_msg) and attempt == 0:
                        logger.warning("Gemini tab crashed or closed. Resetting connection and retrying...")
                        await self._clean_disconnect()
                        await asyncio.sleep(2.0)
                        continue
                    raise e
    async def _do_gemini_translation(self, page: PlaywrightPage, prompt: str, timeout_seconds: int = 360) -> str:
        turns_locator = page.locator("model-response, [class*='model-response'], div.model-response")
        baseline_turns_count = await turns_locator.count()
        input_box = page.locator(
            "rich-textarea div[contenteditable='true'], textarea, div.ql-editor, [contenteditable='true'][role='textbox']"
        ).first
        await input_box.wait_for(state="visible", timeout=30000)
        await input_box.click()

        # Clear existing text
        try:
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
        except Exception:
            pass

        await self._safe_insert_multiline_prompt(page, prompt)

        streaming_query = "button[aria-label*='Stop' i], button[aria-label*='توقف' i], button.stop-button"

        send_btn = page.locator(
            "button[aria-label='Send message'], button[aria-label*='Send' i], button.send-button, button[aria-label='Submit'], button[aria-label*='ارسال' i]"
        ).first
        if await send_btn.is_visible(timeout=500):
            await send_btn.click(force=True, timeout=1000)
        else:
            await page.keyboard.press("Enter")

        start_time = asyncio.get_event_loop().time()
        prev_len = 0
        stable_count = 0

        while (asyncio.get_event_loop().time() - start_time) < timeout_seconds:
            await asyncio.sleep(0.2)
            is_streaming_ui = False
            try:
                stop_locator = page.locator(streaming_query).first
                if await stop_locator.is_visible(timeout=50):
                    is_streaming_ui = True
            except Exception:
                pass

            turns_count = await turns_locator.count()
            if turns_count <= baseline_turns_count:
                continue

            latest_turn = turns_locator.nth(turns_count - 1)
            cur_text = ""
            try:
                cur_text = (await latest_turn.inner_text()).strip()
            except Exception:
                pass

            if not is_streaming_ui and len(cur_text) > 0:
                if len(cur_text) == prev_len:
                    stable_count += 1
                else:
                    prev_len = len(cur_text)
                    stable_count = 0

                if stable_count >= 1:
                    break
        turns_count = await turns_locator.count()
        if turns_count <= baseline_turns_count:
            raise RuntimeError("پاسخ جدیدی از Gemini دریافت نشد. لطفاً تب کروم را بررسی نمایید.")
        latest_turn = turns_locator.nth(turns_count - 1)

        extracted_html = ""
        if latest_turn:
            # Priority 1: .markdown-main-panel (cleanest markdown container inside Gemini)
            panels = latest_turn.locator(".markdown-main-panel")
            panel_count = await panels.count()
            if panel_count > 0:
                html_parts = []
                for i in range(panel_count):
                    p_html = await panels.nth(i).inner_html()
                    if p_html.strip():
                        html_parts.append(p_html)
                extracted_html = "\n\n".join(html_parts)

            # Priority 2: message-content elements inside latest turn
            if not extracted_html.strip():
                msg_contents = latest_turn.locator("message-content")
                mc_count = await msg_contents.count()
                if mc_count > 0:
                    html_parts = []
                    for i in range(mc_count):
                        m_html = await msg_contents.nth(i).inner_html()
                        if m_html.strip():
                            html_parts.append(m_html)
                    extracted_html = "\n\n".join(html_parts)

            # Priority 3: .model-response-text inside latest turn
            if not extracted_html.strip():
                mrt = latest_turn.locator(".model-response-text")
                if await mrt.count() > 0:
                    extracted_html = await mrt.first.inner_html()

            # Priority 4: full latest turn inner_html
            if not extracted_html.strip():
                extracted_html = await latest_turn.inner_html()
        # Global fallback if turns_locator didn't match anything
        if not extracted_html.strip():
            fallback_res = page.locator(".markdown-main-panel, message-content, .model-response-text")
            fb_count = await fallback_res.count()
            if fb_count == 0:
                raise RuntimeError("No response found from Gemini. Please verify you are logged into Google Gemini.")
            extracted_html = await fallback_res.nth(fb_count - 1).inner_html()

        return convert_chat_html_to_markdown(extracted_html)

    async def translate_with_claude(self, prompt: str, timeout_seconds: int = 360, session_tag: str = "default") -> str:
        """Automates translation silently in the background Claude tab."""
        async with self._get_lock(session_tag):
            for attempt in range(2):
                try:
                    page = await self.get_or_create_page("claude.ai", "https://claude.ai/new", force_new_chat=False, session_tag=session_tag)
                    return await self._do_claude_translation(page, prompt, timeout_seconds)
                except Exception as e:
                    err_msg = str(e).lower()
                    if ("crash" in err_msg or "closed" in err_msg or "destroyed" in err_msg or "session closed" in err_msg) and attempt == 0:
                        logger.warning("Claude tab crashed or closed. Resetting connection and retrying...")
                        await self._clean_disconnect()
                        await asyncio.sleep(2.0)
                        continue
                    raise e
    async def _do_claude_translation(self, page: PlaywrightPage, prompt: str, timeout_seconds: int = 360) -> str:
        responses = page.locator("div[data-is-streaming='false'], div.font-claude-message, div[data-test-render-count], div.prose")
        baseline_count = await responses.count()

        input_box = page.locator("div[contenteditable='true'], textarea, div.ProseMirror").first
        await input_box.wait_for(state="visible", timeout=15000)
        try:
            await input_box.click(force=True, timeout=1200)
        except Exception:
            pass

        # Clear editor first to ensure no leftover text
        try:
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
        except Exception:
            pass
        await self._safe_insert_multiline_prompt(page, prompt)

        stop_query = "button[aria-label*='Stop' i], button[aria-label*='توقف' i]"

        send_btn = page.locator("button[aria-label='Send Message'], button[aria-label='Send message'], button[aria-label*='Send' i]").first
        if await send_btn.is_visible(timeout=500):
            await send_btn.click(force=True, timeout=1000)
        else:
            await page.keyboard.press("Enter")

        start_time = asyncio.get_event_loop().time()
        stop_btn = page.locator("button[aria-label='Stop generating'], button[aria-label='Stop responding'], button[aria-label*='Stop' i]").first

        prev_len = 0
        stable_count = 0
        while (asyncio.get_event_loop().time() - start_time) < timeout_seconds:
            await asyncio.sleep(0.2)
            is_stopping = False
            try:
                is_stopping = await stop_btn.is_visible()
            except Exception:
                is_stopping = False

            if not is_stopping:
                finished = False
                try:
                    finished = await page.evaluate("""() => {
                        const latest = document.querySelector("div[data-is-streaming='false']")
                                    || document.querySelector("button[aria-label*='Copy']");
                        return !!latest;
                    }""")
                except Exception:
                    finished = False

                if finished:
                    break

            count = await responses.count()
            if count <= baseline_count:
                continue

            latest_res = responses.nth(count - 1)
            cur_text = ""
            try:
                cur_text = (await latest_res.inner_text()).strip()
            except Exception:
                pass

            if not is_stopping and len(cur_text) > 0:
                if len(cur_text) == prev_len:
                    stable_count += 1
                else:
                    prev_len = len(cur_text)
                    stable_count = 0

                if stable_count >= 1:
                    break

        count = await responses.count()
        if count == 0:
            raise RuntimeError("No response found from Claude. Please check the open browser window.")

        latest_res = responses.nth(count - 1)
        html = await latest_res.inner_html()
        return convert_chat_html_to_markdown(html)
