"""DOCX exporter for translated pages and full books with true RTL OOXML, Vazirmatn typography, and embedded picture support."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from pdf_translator.application.persian_cleanup import clean_markdown_persian, to_persian_digits
from pdf_translator.domain.entities import Page, Project

DEFAULT_FONT = "Vazirmatn"


def _set(elem, parent):
    parent.append(elem)
    return elem


def persianize_styles(doc: Document, font: str = DEFAULT_FONT, size: float = 11.0):
    """Configures the document-wide defaults python-docx inherits from its Latin template.
    
    Ensures:
    - Normal style uses Vazirmatn in the Complex Script (cs) slot with RTL flag.
    - Heading styles 1-4 use Vazirmatn, RTL, and neutral black color instead of Word's default blue.
    """
    normal_style = doc.styles["Normal"]
    normal_style.font.name = font
    normal_style.font.size = Pt(size)
    
    rPr = normal_style.element.get_or_add_rPr()
    rF = rPr.find(qn("w:rFonts"))
    if rF is None:
        rF = _set(OxmlElement("w:rFonts"), rPr)
    for a in ("w:ascii", "w:hAnsi", "w:cs"):
        rF.set(qn(a), font)
    
    _set(OxmlElement("w:rtl"), rPr)
    szCs = _set(OxmlElement("w:szCs"), rPr)
    szCs.set(qn("w:val"), str(int(size * 2)))
    _set(OxmlElement("w:bidi"), normal_style.element.get_or_add_pPr())

    # Heading styles 1-4: Vazirmatn, bidi, and neutral black color
    for i in range(1, 5):
        try:
            h = doc.styles[f"Heading {i}"]
        except KeyError:
            continue
        h.font.name = font
        h.font.color.rgb = RGBColor(0, 0, 0)
        hr = h.element.get_or_add_rPr()
        hf = hr.find(qn("w:rFonts"))
        if hf is None:
            hf = _set(OxmlElement("w:rFonts"), hr)
        for a in ("w:ascii", "w:hAnsi", "w:cs"):
            hf.set(qn(a), font)
        _set(OxmlElement("w:rtl"), hr)
        _set(OxmlElement("w:bidi"), h.element.get_or_add_pPr())


def rtl_section(section):
    """Enforces section-level bidirectional flow (<w:bidi/> as first child of <w:sectPr>)."""
    sectPr = section._sectPr
    if sectPr.find(qn("w:bidi")) is None:
        sectPr.insert(0, OxmlElement("w:bidi"))


def keep_with_next(p):
    """Prevents headings from being orphaned at the bottom of a page."""
    pPr = p._p.get_or_add_pPr()
    pPr.append(OxmlElement("w:keepNext"))
    pPr.append(OxmlElement("w:keepLines"))
def rtl_paragraph(p, align: str = "start"):
    """Applies bidi and start/both/center alignment to a paragraph.
    Note: In OOXML with bidi, 'start' is the visual right. Setting 'right' causes visual left!
    """
    pPr = p._p.get_or_add_pPr()
    if pPr.find(qn("w:bidi")) is None:
        pPr.append(OxmlElement("w:bidi"))
    
    # Map 'right' to 'start' to avoid the OOXML RTL inversion trap
    effective_align = "start" if align in {"right", "start"} else align
    
    jc = pPr.find(qn("w:jc"))
    if jc is None:
        jc = OxmlElement("w:jc")
        pPr.append(jc)
    jc.set(qn("w:val"), effective_align)
    return p

def fa_run(
    p,
    text: str,
    font: str = DEFAULT_FONT,
    size: float = 11.0,
    bold: bool = False,
    italic: bool = False,
    color: RGBColor | None = None,
):
    """Adds a run explicitly configured for Persian Complex Script (CS) shaping."""
    run = p.add_run(text)
    rPr = run._r.get_or_add_rPr()
    
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = _set(OxmlElement("w:rFonts"), rPr)
    for attr in ("w:ascii", "w:hAnsi", "w:cs"):
        rFonts.set(qn(attr), font)
        
    _set(OxmlElement("w:rtl"), rPr)
    szCs = _set(OxmlElement("w:szCs"), rPr)
    szCs.set(qn("w:val"), str(int(size * 2)))
    run.font.size = Pt(size)
    
    if bold:
        _set(OxmlElement("w:bCs"), rPr)
        run.bold = True
    if italic:
        _set(OxmlElement("w:iCs"), rPr)
        run.italic = True
    if color:
        run.font.color.rgb = color
        
    return run


def render_markdown_paragraph_to_docx(doc: Document, par_text: str, storage_dir: str | None = None):
    """Parses a markdown paragraph or image block and adds it with proper Persian RTL formatting to docx."""
    text = par_text.strip()
    if not text:
        return

    # Check for image tag: ![caption](/api/projects/.../pages/6/images/1)
    img_match = re.search(r"!\[(.*?)\]\((.*?)\)", text)
    if img_match:
        caption = img_match.group(1).strip()
        url = img_match.group(2).strip()
        
        found_img_file: Path | None = None
        match_params = re.search(r"/pages/(\d+)/images/(\d+)", url)
        if match_params and storage_dir:
            p_num = match_params.group(1)
            i_idx = match_params.group(2)
            cand = Path(storage_dir) / "images" / f"page_{p_num}_img_{i_idx}.png"
            if cand.exists():
                found_img_file = cand

        if found_img_file and found_img_file.exists():
            try:
                pic_p = doc.add_paragraph()
                pic_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = pic_p.add_run()
                run.add_picture(str(found_img_file), width=Inches(5.0))
                
                # Only add caption if it's a real specific title, not generic 'Figure/Diagram' or 'تصویر'
                is_generic = bool(re.match(r"^(?:Figure[\s\/_-]*Diagram|Image|تصویر(?:\s*[0-9۰-۹]+)?|نمودار(?:\s*[0-9۰-۹]+)?)$", caption, re.IGNORECASE))
                if caption and not is_generic:
                    cap_p = doc.add_paragraph()
                    rtl_paragraph(cap_p, align="center")
                    fa_run(
                        cap_p,
                        caption,
                        size=9.5,
                        italic=True,
                        color=RGBColor(100, 116, 139),
                    )
                return
            except Exception:
                pass
        else:
            # Image tag matched but file not on disk: consume to prevent leaking raw text into output
            return
    # Headings: H1, H2, H3
    if text.startswith("# "):
        title_text = text[2:].strip()
        h = doc.add_heading(level=1)
        rtl_paragraph(h, align="right")
        keep_with_next(h)
        fa_run(h, title_text, size=16.0, bold=True)
        return
    elif text.startswith("## "):
        title_text = text[3:].strip()
        h = doc.add_heading(level=2)
        rtl_paragraph(h, align="right")
        keep_with_next(h)
        fa_run(h, title_text, size=13.5, bold=True)
        return
    elif text.startswith("### "):
        title_text = text[4:].strip()
        h = doc.add_heading(level=3)
        rtl_paragraph(h, align="right")
        keep_with_next(h)
        fa_run(h, title_text, size=12.0, bold=True)
        return

    # Bullet / List: avoid 'List Bullet' because numbering.xml breaks RTL and uses OpenSymbol
    if text.startswith(("- ", "* ")):
        item_text = text[2:].strip()
        p = doc.add_paragraph()
        rtl_paragraph(p, align="right")
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.left_indent = Inches(0.25)
        fa_run(p, "•  ", bold=True)
        fa_run(p, item_text)
        return

    # Numbered List: avoid 'List Number' because numbering.xml renders Latin digits on visual left
    if re.match(r"^\d+\.\s+", text):
        num_match = re.match(r"^(\d+)\.\s+(.*)", text)
        if num_match:
            num_val = num_match.group(1)
            item_text = num_match.group(2)
        else:
            num_val = "1"
            item_text = text
        p = doc.add_paragraph()
        rtl_paragraph(p, align="right")
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.left_indent = Inches(0.25)
        fa_prefix = f"{to_persian_digits(num_val)}.  "
        fa_run(p, fa_prefix, bold=True)
        fa_run(p, item_text)
        return

    # Blockquote
    if text.startswith("> "):
        p = doc.add_paragraph()
        rtl_paragraph(p, align="right")
        p.paragraph_format.left_indent = Inches(0.4)
        p.paragraph_format.space_after = Pt(6)
        clean_quote = text[2:].strip().replace("**", "").replace("`", "")
        fa_run(p, f"«{clean_quote}»", italic=True, color=RGBColor(71, 85, 105))
        return

    # Standard body paragraph with bidi justification
    p = doc.add_paragraph()
    rtl_paragraph(p, align="both")
    p.paragraph_format.line_spacing = 1.4
    p.paragraph_format.space_after = Pt(8)
    clean_text = text.replace("**", "").replace("`", "")
    fa_run(p, clean_text)


class DocxExporter:
    def export_page(self, page: Page, output_path: Path, storage_dir: str | None = None) -> Path:
        doc = Document()
        persianize_styles(doc)
        rtl_section(doc.sections[0])
        
        # Add page heading with Persian digits
        fa_page_num = to_persian_digits(str(page.page_number))
        heading = doc.add_heading(level=1)
        rtl_paragraph(heading, align="right")
        keep_with_next(heading)
        fa_run(heading, f"صفحه {fa_page_num}", size=16.0, bold=True)
        
        # Content
        text = (page.approved_text or page.latest_translation or page.source_text).strip()
        text = clean_markdown_persian(text)
        
        if not storage_dir:
            storage_dir = getattr(page, "storage_dir", None)
            if not storage_dir and hasattr(page, "project") and page.project:
                storage_dir = page.project.storage_dir
            if not storage_dir:
                from pdf_translator.adapters.storage.file_storage import FileStorageManager
                storage_dir = str(FileStorageManager().get_project_dir(page.project_id))

        for paragraph_text in text.split("\n\n"):
            if paragraph_text.strip():
                render_markdown_paragraph_to_docx(doc, paragraph_text.strip(), storage_dir)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(output_path))
        return output_path

    def assemble_book(self, project: Project, pages: list[Page], output_path: Path) -> Path:
        doc = Document()
        persianize_styles(doc)
        rtl_section(doc.sections[0])
        
        # Title Page
        title_p = doc.add_heading(level=0)
        rtl_paragraph(title_p, align="center")
        fa_run(title_p, project.title, size=22.0, bold=True)
        
        sub = doc.add_paragraph()
        rtl_paragraph(sub, align="center")
        sub_text = f"ترجمه از {project.source_language} به {project.target_language}"
        fa_run(sub, sub_text, size=11.0, color=RGBColor(100, 116, 139))
        
        doc.add_page_break()

        for page in pages:
            text = (page.approved_text or page.latest_translation or page.source_text).strip()
            text = clean_markdown_persian(text)
            
            fa_page_num = to_persian_digits(str(page.page_number))
            p_head = doc.add_heading(level=2)
            rtl_paragraph(p_head, align="right")
            keep_with_next(p_head)
            fa_run(p_head, f"صفحه {fa_page_num}", size=14.0, bold=True)
            
            for par in text.split("\n\n"):
                if par.strip():
                    render_markdown_paragraph_to_docx(doc, par.strip(), project.storage_dir)
            doc.add_paragraph()  # spacing

        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(output_path))
        return output_path
