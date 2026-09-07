"""CLI and Server entrypoint for PDF Book Translator."""
import uvicorn

def main():
    print("🚀 Starting PDF Book Translator web server at http://127.0.0.1:8000 ...")
    uvicorn.run("pdf_translator.web.app:app", host="127.0.0.1", port=8000, reload=True)

if __name__ == "__main__":
    main()
