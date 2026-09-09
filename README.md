# PDF Book Translator

A **Local-first, Python-native Web Application** for translating PDF books page-by-page with **Human-in-the-Loop (HITL)** workflows and **Standard Persian Writing & Typography Engine**.

---

## 🌟 Architecture & Highlights

- **Domain-Driven Design (Hexagonal / Ports & Adapters Architecture)**:
  - `domain/`: Business entities (`Project`, `Page`, `TranslationProfile`, `TranslationAttempt`), state machine transitions (`PageStatus`), and ports.
  - `application/`: End-to-end use cases (`ProjectService`, `PageService`, `TranslationService`, `ChapterService`, `ExportService`) and Persian text normalizer.
  - `adapters/`: PyMuPDF PDF parser & renderer, SQLite persistence, AI providers (`OpenAI`, `Gemini`, `Claude`, `Mock`), and true RTL DOCX/Markdown exporters.
  - `web/`: FastAPI backend with responsive book reader and in-reading AI assistant.

- **Strict Human-in-the-Loop (HITL)**:
  1. *PDF Ingestion*: Auto-detects pages, extracts text, and renders PNG visuals.
  2. *Pre-Translation Inspection*: Operator inspects and edits extracted text before translation.
  3. *AI Translation Engine*: Translates via configured LLM profile with glossary support.
  4. *Human Review & Polish*: Operator reviews, edits draft, or retries.
  5. *Book Assembly & Export*: Single-click export of translated pages and complete book in Markdown & DOCX.

- **🇮🇷 Persian Writing, Typography & De-AI Engine**:
  - **De-AI Prompting (حذف لحن ماشینی و متکلف هوش مصنوعی)**:
    - Built-in strict prompt guidelines banning bureaucratic copula inflation (`می‌باشد`, `به شمار می‌رود`, `محسوب می‌شود`, `گردید`).
    - Eliminates ceremonial AI filler announcements (`لازم به ذکر است که`, `شایان ذکر است`, `باید خاطرنشان کرد`).
    - Eliminates significance inflation (`نقش بسزایی ایفا می‌کند`, `از اهمیت ویژه‌ای برخوردار است`, `در راستای`).
    - Eliminates translationese calques (`در پایان روز`, `نگاهی بیندازیم به`).
  - **Automated Editorial Normalization (ویراستاری خودکار)**:
    - Zero-dependency, Markdown-safe post-processing (`application/persian_cleanup.py`).
    - Maps Arabic characters to Persian (`ي`/`ك`/`ة` $\rightarrow$ `ی`/`ک`/`ه`).
    - Enforces standard ZWNJ (نیم‌فاصله) on verbs (`می‌شود`), prefixes (`به‌عنوان`), suffixes (`کتاب‌ها`, `بزرگ‌تر`), and possessives (`خانه‌ام`).
    - Converts English quotes to Persian guillemets (`«...»`) and strips invalid English em dashes (`—`).
    - Normalizes punctuation spacing and Persian digits in lists.
    - Preserves 100% of code blocks, inline code, LaTeX math formulas, system placeholders, and Markdown URLs untouched.
  - **True RTL DOCX Export with Vazirmatn**:
    - Generates OOXML-compliant Word documents with section-level `<w:bidi/>`.
    - Styles Word defaults (`persianize_styles`) so Normal and Heading styles use Vazirmatn in the Complex Script (`w:cs`) slot.
    - Prevents Word's default blue headings and DejaVu/OpenSymbol font fallbacks.
    - Fixes list numbering with native Persian numerals (`۱.  `, `•  `) avoiding corrupted `numbering.xml`.
  - **Bundled Fonts**:
    - Ships with official SIL OFL **Vazirmatn** and **Lalezar** fonts under `assets/fonts/`.
    - Includes `./scripts/install_fonts.sh` for one-command installation to `~/.fonts` on Linux/macOS.

---

## 🚀 Quickstart

### 1. Installation

```bash
# Create virtualenv and install dependencies
python3 -m virtualenv .venv
.venv/bin/pip install -e ".[dev]"
```

### 2. (Optional) Install Persian Fonts for System / LibreOffice

```bash
# Installs bundled Vazirmatn and Lalezar fonts to ~/.fonts
bash scripts/install_fonts.sh
```

### 3. Run Application

```bash
# Start the web server
.venv/bin/python -m pdf_translator.main
```

Open your browser at **`http://127.0.0.1:8000`**.

### 4. Run Tests

```bash
.venv/bin/pytest -v
```

---

## 📖 Ubiquitous Language

See [`CONTEXT.md`](file:///home/masoud.salehi@zoodfood.ir/Projects/pdf-translator/CONTEXT.md) and [`docs/01-adr.md`](file:///home/masoud.salehi@zoodfood.ir/Projects/pdf-translator/docs/01-adr.md) for architectural decisions and glossary definitions.
