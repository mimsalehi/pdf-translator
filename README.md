# PDF Book Translator

A **Local-first, Python-native Web Application** for translating PDF books page-by-page with **Human-in-the-Loop (HITL)** workflows.

---

## 🌟 Architecture & Highlights

- **Domain-Driven Design (Hexagonal / Ports & Adapters Architecture)**:
  - `domain/`: Business entities (`Project`, `Page`, `TranslationProfile`, `TranslationAttempt`), state machine transitions (`PageStatus`), and ports.
  - `application/`: End-to-end use cases (`ProjectService`, `PageService`, `TranslationService`, `ExportService`).
  - `adapters/`: PyMuPDF PDF parser & renderer, SQLite persistence, AI providers (`OpenAI`, `Gemini`, `Claude`, `Mock`), and DOCX/Markdown exporters.
  - `web/`: FastAPI backend with clean responsive UI.
- **Strict Human-in-the-Loop (HITL)**:
  1. *PDF Ingestion*: Auto-detects pages, extracts text, and renders PNG visuals.
  2. *Pre-Translation Inspection*: Operator inspects and edits extracted text before translation.
  3. *AI Translation Engine*: Translates via configured LLM profile with glossary support.
  4. *Human Review & Polish*: Operator reviews, edits draft, or retries.
  5. *Book Assembly & Export*: Single-click export of translated pages and complete book in Markdown & DOCX.

---

## 🚀 Quickstart

### 1. Installation

```bash
# Create virtualenv and install dependencies
python3 -m virtualenv .venv
.venv/bin/pip install -e ".[dev]"
```

### 2. Run Application

```bash
# Start the web server
.venv/bin/python -m pdf_translator.main
```

Open your browser at **`http://127.0.0.1:8000`**.

### 3. Run Tests

```bash
.venv/bin/pytest -v
```

---

## 📖 Ubiquitous Language

See [`CONTEXT.md`](file:///home/masoud.salehi@zoodfood.ir/Projects/pdf-translator/CONTEXT.md) and [`docs/01-adr.md`](file:///home/masoud.salehi@zoodfood.ir/Projects/pdf-translator/docs/01-adr.md) for architectural decisions and glossary definitions.
