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
    
    code_blocks = []
    
    # 1. Find all pre blocks, extract pristine code text and replace with token
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
        self._lock = asyncio.Lock()
        self._reset_thread_flags: Dict[str, bool] = {}

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
            "--no-first-run",
            "--no-default-browser-check",
            "--start-maximized",
            start_url,
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

    async def get_or_create_page(self, domain_keyword: str, default_url: str, force_new_chat: bool = False) -> PlaywrightPage:
        """Connects over CDP and retrieves the active tab without stealing focus with auto-reconnect."""
        async with self._lock:
            should_new_chat = force_new_chat or self._reset_thread_flags.pop(domain_keyword, False) or self._reset_thread_flags.pop("all", False)

            for attempt in range(2):
                try:
                    await self._ensure_cdp_connected(default_url)
                    context = self._browser.contexts[0] if self._browser.contexts else await self._browser.new_context()

                    # 1. Search for existing tab on this domain
                    matching_pages = [p for p in context.pages if domain_keyword in p.url]
                    if matching_pages:
                        target_page = matching_pages[0]
                        if should_new_chat:
                            # Navigate or click new chat button
                            try:
                                new_chat_btn = target_page.locator('a[href="/"], button[aria-label="New chat"], button[data-testid="create-new-chat-button"], button[aria-label="New Chat"]').first
                                if await new_chat_btn.is_visible(timeout=1000):
                                    await new_chat_btn.click()
                                    await asyncio.sleep(0.8)
                                else:
                                    await target_page.goto(default_url, wait_until="domcontentloaded", timeout=15000)
                            except Exception:
                                await target_page.goto(default_url, wait_until="domcontentloaded", timeout=15000)
                            await asyncio.sleep(0.5)
                        return target_page

                    # 2. If no tab found, open a new tab
                    page = await context.new_page()
                    await page.goto(default_url, wait_until="domcontentloaded", timeout=20000)
                    await asyncio.sleep(0.5)
                    return page

                except Exception as e:
                    if attempt == 0:
                        # Transport broke or browser restarted; cleanly reset and retry once
                        await self._clean_disconnect()
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

    async def translate_with_chatgpt(self, prompt: str, timeout_seconds: int = 150) -> str:
        """Automates translation silently in the background ChatGPT tab without tab switching."""
        page = await self.get_or_create_page("chatgpt.com", "https://chatgpt.com", force_new_chat=False)

        # Locate ProseMirror editor with multi-selector fallback
        editor_selectors = [
            "div#prompt-textarea",
            "div[contenteditable='true']",
            "textarea#prompt-textarea",
            "div.ProseMirror",
            "textarea[placeholder*='Ask']",
            "textarea[placeholder*='Message']",
            "#prompt-textarea"
        ]
        
        editor = None
        for sel in editor_selectors:
            try:
                loc = page.locator(sel).first
                if await loc.is_visible(timeout=2000):
                    editor = loc
                    break
            except Exception:
                pass

        if not editor:
            editor = page.locator("div#prompt-textarea, div[contenteditable='true'], textarea").first
            await editor.wait_for(state="visible", timeout=30000)

        await editor.click()
        await asyncio.sleep(0.3)

        # Focus inner paragraph via JS
        await page.evaluate("""() => {
            const el = document.querySelector('#prompt-textarea p') 
                    || document.querySelector('#prompt-textarea')
                    || document.querySelector('div[contenteditable="true"]')
                    || document.querySelector('textarea');
            if (el) el.focus();
        }""")

        # Insert prompt
        await page.keyboard.insert_text(prompt)
        await asyncio.sleep(0.6)

        # Send
        send_selectors = [
            'button[data-testid="send-button"]',
            'button[data-testid="composer-send-button"]',
            'button[data-testid="fruitjuice-send-button"]',
            'button[aria-label="Send prompt"]',
            'button[aria-label="Send message"]',
        ]
        sent = False
        for s_sel in send_selectors:
            try:
                s_btn = page.locator(s_sel).first
                if await s_btn.is_visible(timeout=800):
                    await s_btn.click()
                    sent = True
                    break
            except Exception:
                pass

        if not sent:
            await page.keyboard.press("Enter")

        # Wait for response in background
        await asyncio.sleep(3.0)
        stop_btn = page.locator('button[data-testid="stop-button"], button[aria-label="Stop streaming"], button[aria-label="Stop generating"]').first
        for _ in range(int(timeout_seconds * 2)):
            try:
                if not await stop_btn.is_visible():
                    await asyncio.sleep(1.0)
                    if not await stop_btn.is_visible():
                        break
            except Exception:
                break
            await asyncio.sleep(0.5)

        await asyncio.sleep(1.5)

        # Extract latest assistant message preserving Markdown structure (headings, lists, code)
        msgs = page.locator('div[data-message-author-role="assistant"]')
        count = await msgs.count()
        if count == 0:
            articles = page.locator('article')
            art_count = await articles.count()
            if art_count > 0:
                html = await articles.nth(art_count - 1).inner_html()
                return convert_chat_html_to_markdown(html)
            raise RuntimeError("No response found from ChatGPT. Please verify you are logged into ChatGPT.")

        latest_msg = msgs.nth(count - 1)
        html = await latest_msg.inner_html()
        return convert_chat_html_to_markdown(html)

    async def translate_with_gemini(self, prompt: str, timeout_seconds: int = 150) -> str:
        """Automates translation silently in the background Google Gemini tab."""
        page = await self.get_or_create_page("gemini.google.com", "https://gemini.google.com/app", force_new_chat=False)

        # Record baseline model responses count before submitting the prompt
        turns_locator = page.locator("model-response, [class*='model-response'], div.model-response")
        baseline_turns_count = await turns_locator.count()

        input_box = page.locator(
            "rich-textarea div[contenteditable='true'], textarea, div.ql-editor, [contenteditable='true'][role='textbox']"
        ).first
        await input_box.wait_for(state="visible", timeout=30000)
        await input_box.click()
        await asyncio.sleep(0.2)

        # Clear existing text completely before typing new prompt
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await asyncio.sleep(0.2)

        await page.keyboard.insert_text(prompt)
        await asyncio.sleep(0.5)

        send_btn = page.locator(
            "button[aria-label='Send message'], button[aria-label*='Send' i], button.send-button, button[aria-label='Submit'], button[aria-label*='ارسال' i]"
        ).first
        if await send_btn.is_visible():
            await send_btn.click()
        else:
            await page.keyboard.press("Enter")

        # Allow Gemini a short window to accept the prompt and begin generating
        await asyncio.sleep(2.0)

        # Streaming stop/busy indicators across locales and UI variants
        streaming_selectors = [
            "button[aria-label*='Stop' i]",
            "button[aria-label*='توقف' i]",
            "button:has(mat-icon[data-mat-icon-name='stop'])",
            "button:has(mat-icon[fonticon='stop'])",
            "mat-icon[data-mat-icon-name='stop']",
            "mat-icon[fonticon='stop']",
            "[aria-busy='true']",
        ]
        streaming_query = ", ".join(streaming_selectors)

        start_time = asyncio.get_event_loop().time()
        last_text = ""
        stable_since = None
        STABLE_REQUIRED_SECONDS = 2.5  # Content must remain unchanged for at least 2.5 seconds
        MIN_WAIT_SECONDS = 3.0        # Never finish before minimum reasonable response time

        while (asyncio.get_event_loop().time() - start_time) < timeout_seconds:
            turns_count = await turns_locator.count()

            # Check if stop / busy streaming UI is currently visible
            is_streaming_ui = False
            try:
                stop_locator = page.locator(streaming_query).first
                if await stop_locator.is_visible(timeout=100):
                    is_streaming_ui = True
            except Exception:
                pass

            # Read current text of the latest response to check generation progress
            current_text = ""
            if turns_count > baseline_turns_count:
                latest_turn = turns_locator.nth(turns_count - 1)
                try:
                    current_text = (await latest_turn.inner_text()).strip()
                except Exception:
                    pass
            else:
                try:
                    fallback_res = page.locator(".markdown-main-panel, message-content, .model-response-text")
                    fb_count = await fallback_res.count()
                    if fb_count > 0:
                        current_text = (await fallback_res.nth(fb_count - 1).inner_text()).strip()
                except Exception:
                    pass

            elapsed = asyncio.get_event_loop().time() - start_time

            # If text has changed or is still growing, reset the stability timer
            if current_text != last_text:
                last_text = current_text
                stable_since = asyncio.get_event_loop().time()

            # Check if copy-button or send-button has surfaced on the latest turn (strong completion indicator)
            has_completion_button = False
            try:
                copy_btn = page.locator("copy-button, button[data-test-id='copy-button'], button[aria-label*='Copy' i], button[aria-label*='کپی' i]").last
                if await copy_btn.count() > 0 and await copy_btn.is_visible():
                    has_completion_button = True
            except Exception:
                pass

            # Generation is complete when:
            # 1. Text is non-empty and has actually generated
            # 2. Stop/streaming UI is no longer visible
            # 3. Text has remained completely stable for STABLE_REQUIRED_SECONDS (or completion button is visible + 1.2s stability)
            # 4. Minimum wait threshold has passed
            is_stable = stable_since is not None and (asyncio.get_event_loop().time() - stable_since) >= STABLE_REQUIRED_SECONDS
            is_quick_stable = has_completion_button and stable_since is not None and (asyncio.get_event_loop().time() - stable_since) >= 1.2

            if (
                current_text
                and not is_streaming_ui
                and elapsed >= MIN_WAIT_SECONDS
                and (is_stable or is_quick_stable)
            ):
                break

            await asyncio.sleep(0.6)

        # Additional settle delay to ensure final DOM rendering is complete
        await asyncio.sleep(0.5)

        # Extract complete response HTML from the latest model response turn
        turns_count = await turns_locator.count()
        latest_turn = turns_locator.nth(turns_count - 1) if turns_count > 0 else None

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

    async def translate_with_claude(self, prompt: str, timeout_seconds: int = 150) -> str:
        """Automates translation silently in the background Claude tab."""
        page = await self.get_or_create_page("claude.ai", "https://claude.ai/new", force_new_chat=False)

        input_box = page.locator("div[contenteditable='true'], textarea, div.ProseMirror").first
        await input_box.wait_for(state="visible", timeout=30000)
        await input_box.click()
        await asyncio.sleep(0.3)

        await page.keyboard.insert_text(prompt)
        await asyncio.sleep(0.6)

        send_btn = page.locator("button[aria-label='Send Message'], button[aria-label='Send message']").first
        if await send_btn.is_visible():
            await send_btn.click()
        else:
            await page.keyboard.press("Enter")

        await asyncio.sleep(3.5)
        stop_btn = page.locator("button[aria-label='Stop generating'], button[aria-label='Stop responding']").first
        for _ in range(int(timeout_seconds * 2)):
            try:
                if not await stop_btn.is_visible():
                    await asyncio.sleep(1.0)
                    if not await stop_btn.is_visible():
                        break
            except Exception:
                break
            await asyncio.sleep(0.5)

        await asyncio.sleep(1.5)

        responses = page.locator("div.font-claude-message, div[data-is-streaming='false']")
        count = await responses.count()
        if count == 0:
            raise RuntimeError("No response found from Claude. Please check the open browser window.")

        latest_res = responses.nth(count - 1)
        html = await latest_res.inner_html()
        return convert_chat_html_to_markdown(html)
