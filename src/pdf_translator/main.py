"""CLI and Server entrypoint for PDF Book Translator."""
import sys
import asyncio
import uvicorn

if sys.platform == "win32":
    # Playwright on Windows requires WindowsProactorEventLoopPolicy for subprocess transport.
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass
    try:
        import uvicorn.loops.asyncio
        uvicorn.loops.asyncio.asyncio_loop_factory = lambda use_subprocess=False: asyncio.ProactorEventLoop
    except Exception:
        pass

def main():
    is_windows = sys.platform == "win32"
    print("🚀 Starting PDF Book Translator web server at http://127.0.0.1:8000 ...")
    # On Windows, Uvicorn's reload=True supervisor forces SelectorEventLoop which breaks Playwright's subprocess transport.
    # Therefore, reload is disabled on Windows by default.
    uvicorn.run(
        "pdf_translator.web.app:app",
        host="127.0.0.1",
        port=8000,
        reload=False if is_windows else True,
        loop="asyncio" if is_windows else "auto"
    )

if __name__ == "__main__":
    main()
