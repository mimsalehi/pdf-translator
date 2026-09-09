"""Unit tests for Translation Providers and Exporters."""
import pytest
from pathlib import Path
from pdf_translator.adapters.providers.base import build_translation_prompt
from pdf_translator.adapters.providers.mock_provider import MockTranslationProvider
from pdf_translator.adapters.export.markdown_exporter import MarkdownExporter
from pdf_translator.adapters.export.docx_exporter import DocxExporter
from pdf_translator.domain.entities import Project, Page, GlossaryItem
from pdf_translator.domain.enums import PageStatus

def test_prompt_builder_with_glossary():
    glossary = [
        GlossaryItem(source_term="Value Object", target_term="شیء مقدار", include_parenthesis_english=True),
        GlossaryItem(source_term="Aggregate", target_term="مجموعه", include_parenthesis_english=False),
    ]
    prompt = build_translation_prompt(
        source_text="An entity and a Value Object belong to an Aggregate.",
        source_language="English",
        target_language="Persian",
        system_prompt="Translate accurately.",
        glossary=glossary,
    )
    assert "Value Object" in prompt
    assert "شیء مقدار" in prompt
    assert "An entity and a Value Object" in prompt

@pytest.mark.asyncio
async def test_mock_provider_with_glossary():
    provider = MockTranslationProvider(delay_seconds=0)
    glossary = [
        GlossaryItem(source_term="Entity", target_term="موجودیت", include_parenthesis_english=True),
    ]
    result = await provider.translate(
        source_text="This is an Entity in DDD.",
        source_language="English",
        target_language="Persian",
        system_prompt="Test",
        glossary=glossary,
    )
    assert "موجودیت (Entity)" in result

def test_markdown_and_docx_exporters(tmp_path: Path):
    project = Project(
        id="proj-123",
        title="Sample Book",
        source_pdf_filename="sample.pdf",
        source_pdf_path="",
        storage_dir="",
        total_pages=2,
    )
    pages = [
        Page(project_id="proj-123", page_number=1, source_text="Eng 1", approved_text="فارسی ۱", status=PageStatus.APPROVED),
        Page(project_id="proj-123", page_number=2, source_text="Eng 2", approved_text="فارسی ۲", status=PageStatus.APPROVED),
    ]

    # Markdown Export
    md_exporter = MarkdownExporter()
    out_md = tmp_path / "book.md"
    md_exporter.assemble_book(project, pages, out_md)
    assert out_md.exists()
    md_text = out_md.read_text(encoding="utf-8")
    assert "Sample Book" in md_text
    assert "فارسی ۱" in md_text
    assert "فارسی ۲" in md_text

    # DOCX Export with Headings, Bullets, and Embedded Pictures
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    sample_png = img_dir / "page_1_img_1.png"
    # Create minimal 1x1 PNG file
    sample_png.write_bytes(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7VkX\x00\x00\x00\x00IEND\xaeB`\x82')
    
    project.storage_dir = str(tmp_path)
    pages[0].approved_text = "# فصل اول\n\nتوضیحات سرور تک نفره:\n\n![نمودار ۱-۱](/api/projects/proj-123/pages/1/images/1)\n\n- نکته اول\n- نکته دوم"

    docx_exporter = DocxExporter()
    out_docx = tmp_path / "book.docx"
    docx_exporter.assemble_book(project, pages, out_docx)
    assert out_docx.exists()
    assert out_docx.stat().st_size > 0

def test_detect_code_language_multi_lang():
    from pdf_translator.adapters.pdf.pymupdf_extractor import detect_code_language
    
    php_code = "$pdfGenerator = new \\Vendor\\Pdf\\Generator();\n$html = $invoice->renderAsHtml();"
    py_code = "def solve(x: int) -> int:\n    return x * 2"
    js_code = "const express = require('express');\napp.get('/', (req, res) => res.send('ok'));"
    sql_code = "SELECT id, name FROM users WHERE active = 1;"
    bash_code = "$ pip install -r req.txt\n$ pytest"

    assert detect_code_language(php_code) == "php"
    assert detect_code_language(py_code) == "python"
    assert detect_code_language(js_code) == "javascript"
    assert detect_code_language(sql_code) == "sql"
    assert detect_code_language(bash_code) == "bash"

def test_merge_split_heading_numbers():
    from pdf_translator.adapters.pdf.pymupdf_extractor import merge_split_heading_paragraphs
    
    sample_blocks = [
        "## 2.3",
        "## Understanding the Pattern",
        "This is paragraph text describing section 2.3.",
        "### 2.3.1",
        "### What It Is",
        "This is paragraph text describing section 2.3.1."
    ]
    
    merged = merge_split_heading_paragraphs(sample_blocks)
    assert "## 2.3 Understanding the Pattern" in merged
    assert "### 2.3.1 What It Is" in merged
    assert "## 2.3" not in merged
    assert "### 2.3.1" not in merged

def test_mask_and_unmask_code_blocks():
    from pdf_translator.application.translation_service import mask_code_blocks, unmask_code_blocks

    doc = (
        "## 2.5 Real-World Implementation\n\n"
        "Here is the code:\n\n"
        "```php\n"
        "namespace App\\Invoices;\n\n"
        "interface InvoiceGeneratorInterface\n"
        "{\n"
        "    public function generate(Invoice $invoice): string;\n"
        "}\n"
        "```\n\n"
        "This is the explanation."
    )

    masked, blocks = mask_code_blocks(doc)
    assert len(blocks) == 1
    assert "[[CODE_BLOCK_0]]" in masked
    assert "namespace App\\Invoices" not in masked

    simulated_translation = (
        "## ۲.۵ پیاده‌سازی در دنیای واقعی\n\n"
        "کد در زیر آورده شده است:\n\n"
        "[[CODE_BLOCK_0]]\n\n"
        "این توضیحات است."
    )

    unmasked = unmask_code_blocks(simulated_translation, blocks)
    assert "```php\nnamespace App\\Invoices;" in unmasked
    assert "public function generate(Invoice $invoice): string;" in unmasked
    assert "[[CODE_BLOCK_0]]" not in unmasked

def test_convert_chat_html_to_markdown():
    from pdf_translator.adapters.providers.browser_manager import convert_chat_html_to_markdown

    html = """
    <p>در اینجا ترجمه کد آورده شده است:</p>
    <pre><div class="flex items-center justify-between"><span>php</span><button>Copy code</button></div><div class="p-4 overflow-y-auto"><code class="!whitespace-pre hljs language-php"><span class="hljs-comment">// Value objects</span>
    <span class="hljs-keyword">final</span> <span class="hljs-class"><span class="hljs-keyword">class</span> <span class="hljs-title">PdfGenerationOptions</span>
    </span>{
        <span class="hljs-keyword">public</span> <span class="hljs-function"><span class="hljs-keyword">function</span> <span class="hljs-title">__construct</span>(
            <span class="hljs-keyword">public</span> <span class="hljs-keyword">readonly</span> <span class="hljs-keyword">string</span> $orientation = "portrait",
        ) </span>{}
    }
    </code></div></pre>
    <p>این کد اشیاء مقدار را می‌سازد.</p>
    """

    res = convert_chat_html_to_markdown(html)
    assert "Copy code" not in res
    assert "```php" in res
    assert "final class PdfGenerationOptions" in res
    assert '$orientation = "portrait"' in res

def test_is_pure_code_or_media_page():
    from pdf_translator.application.translation_service import is_pure_code_or_media_page

    pure_code = "```php\nnamespace App\\Invoices;\nclass Invoice {}\n```"
    pure_img = "![Figure 1-1](/api/projects/123/pages/4/images/1)"
    mixed = "## Section 2.4\nHere is code:\n```php\nclass A {}\n```"

    assert is_pure_code_or_media_page(pure_code) is True
    assert is_pure_code_or_media_page(pure_img) is True
    assert is_pure_code_or_media_page(mixed) is False


def test_mask_and_unmask_image_blocks():
    from pdf_translator.application.translation_service import mask_image_blocks, unmask_image_blocks

    src = (
        "![Figure/Diagram](/api/projects/bc771201/pages/32/images/1)\n\n"
        "### Figure 1-1. A simplified outline of ETL\n\n"
        "In some cases, the data sources of the ETL processes are external SaaS products."
    )

    masked, img_blocks = mask_image_blocks(src)
    assert "[[IMAGE_BLOCK_0]]" in masked
    assert len(img_blocks) == 1
    assert img_blocks[0] == "![Figure/Diagram](/api/projects/bc771201/pages/32/images/1)"

    # 1. AI preserved token
    ai_out_preserved = "[[IMAGE_BLOCK_0]]\n\n### شکل ۱-۱. طرح کلی\n\nدر برخی موارد..."
    unmasked_1 = unmask_image_blocks(ai_out_preserved, img_blocks, src)
    assert unmasked_1.startswith("![Figure/Diagram](/api/projects/bc771201/pages/32/images/1)")
    assert "[[IMAGE_BLOCK_0]]" not in unmasked_1

    # 2. AI completely dropped token
    ai_out_dropped = "### شکل ۱-۱. طرح کلی\n\nدر برخی موارد..."
    unmasked_2 = unmask_image_blocks(ai_out_dropped, img_blocks, src)
    assert unmasked_2.startswith("![Figure/Diagram](/api/projects/bc771201/pages/32/images/1)")

    # 3. AI with Persian digits
    ai_out_persian = "[[IMAGE_BLOCK_۰]]\n\n### شکل ۱-۱. طرح کلی..."
    unmasked_3 = unmask_image_blocks(ai_out_persian, img_blocks, src)
    assert unmasked_3.startswith("![Figure/Diagram](/api/projects/bc771201/pages/32/images/1)")

    # 4. AI literally outputs 'Figure/Diagram' instead of the token
    ai_out_literal = "### شکل ۱-۱. طرح کلی\n\nFigure/Diagram\n\nدر برخی موارد..."
    unmasked_4 = unmask_image_blocks(ai_out_literal, img_blocks, src)
    assert "![Figure/Diagram](/api/projects/bc771201/pages/32/images/1)" in unmasked_4
    assert "Figure/Diagram\n\n" not in unmasked_4

def test_gemini_html_multi_panel_extraction():
    from bs4 import BeautifulSoup
    from pdf_translator.adapters.providers.browser_manager import convert_chat_html_to_markdown

    html = """
    <model-response>
      <div class="container">
        <div class="markdown markdown-main-panel">
          <p>بخش اول ترجمه: این متن مقدمه است.</p>
        </div>
        <div class="markdown markdown-main-panel">
          <p>بخش دوم ترجمه: این پاراگراف دوم و ادامه‌ی ترجمه است.</p>
          <ul>
            <li>نکته اول</li>
            <li>نکته دوم</li>
          </ul>
        </div>
      </div>
    </model-response>
    """
    soup = BeautifulSoup(html, "html.parser")
    panels = soup.select(".markdown-main-panel")
    assert len(panels) == 2
    combined_html = "\n\n".join(str(p) for p in panels)
    res = convert_chat_html_to_markdown(combined_html)
    assert "بخش اول ترجمه: این متن مقدمه است." in res
    assert "بخش دوم ترجمه: این پاراگراف دوم و ادامه‌ی ترجمه است." in res
    assert "- نکته اول" in res
    assert "- نکته دوم" in res

@pytest.mark.asyncio
async def test_translate_with_gemini_waits_for_completion():
    from unittest.mock import AsyncMock, MagicMock
    from pdf_translator.adapters.providers.browser_manager import BrowserManager

    manager = BrowserManager.get_instance()
    mock_page = AsyncMock()
    manager.get_or_create_page = AsyncMock(return_value=mock_page)

    call_count = {"count": 0}
    async def get_turns_count():
        call_count["count"] += 1
        if call_count["count"] == 1:
            return 0
        return 1

    mock_turns = AsyncMock()
    mock_turns.count = AsyncMock(side_effect=get_turns_count)

    mock_turn_elem = AsyncMock()
    mock_turn_elem.inner_text = AsyncMock(return_value="ترجمه کامل متن.")

    mock_panel = AsyncMock()
    mock_panel.inner_html = AsyncMock(return_value="<p>ترجمه کامل متن.</p>")

    mock_panels = AsyncMock()
    mock_panels.count = AsyncMock(return_value=1)
    mock_panels.nth = MagicMock(return_value=mock_panel)

    mock_turn_elem.locator = MagicMock(return_value=mock_panels)
    mock_turns.nth = MagicMock(return_value=mock_turn_elem)

    mock_send_btn = AsyncMock()
    mock_send_btn.is_visible = AsyncMock(return_value=True)

    mock_stop_btn = AsyncMock()
    mock_stop_btn.is_visible = AsyncMock(return_value=False)

    def locator_router(selector):
        if "model-response" in selector:
            return mock_turns
        elif "contenteditable" in selector or "rich-textarea" in selector:
            first_mock = MagicMock()
            first_mock.wait_for = AsyncMock()
            first_mock.click = AsyncMock()
            return MagicMock(first=first_mock)
        elif "Send message" in selector or "send-button" in selector:
            return MagicMock(first=mock_send_btn)
        elif "Stop" in selector or "mat-icon" in selector or "processing-state" in selector:
            return MagicMock(first=mock_stop_btn)
        return MagicMock(first=AsyncMock(), count=AsyncMock(return_value=0))

    mock_page.locator = MagicMock(side_effect=locator_router)
    mock_page.keyboard = AsyncMock()

    res = await manager.translate_with_gemini("Test prompt", timeout_seconds=10)
    assert "ترجمه کامل متن." in res

