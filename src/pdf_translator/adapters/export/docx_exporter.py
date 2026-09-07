"""DOCX exporter for translated pages and full books with rich markdown and embedded picture support."""
from pathlib import Path
import re
from typing import List, Optional
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from pdf_translator.domain.entities import Project, Page

def render_markdown_paragraph_to_docx(doc: Document, par_text: str, storage_dir: Optional[str] = None):
    """Parses a markdown paragraph or image block and adds it with proper formatting to the docx document."""
    text = par_text.strip()
    if not text:
        return

    # Check for image tag: ![caption](/api/projects/.../pages/6/images/1)
    img_match = re.match(r'^!\[(.*?)\]\((.*?)\)$', text)
    if img_match:
        caption = img_match.group(1).strip()
        url = img_match.group(2).strip()
        
        # Extract page_num and img_idx from url
        found_img_file: Optional[Path] = None
        match_params = re.search(r'/pages/(\d+)/images/(\d+)', url)
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
                
                if caption and caption not in {"Figure/Diagram", "Image", "تصویر", "نمودار"}:
                    cap_p = doc.add_paragraph()
                    cap_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    cap_run = cap_p.add_run(caption)
                    cap_run.font.italic = True
                    cap_run.font.size = Pt(9.5)
                    cap_run.font.color.rgb = RGBColor(100, 116, 139)
                return
            except Exception:
                pass

    # Headings
    if text.startswith("# "):
        h = doc.add_heading(text[2:].strip(), level=1)
        h.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        return
    elif text.startswith("## "):
        h = doc.add_heading(text[3:].strip(), level=2)
        h.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        return
    elif text.startswith("### "):
        h = doc.add_heading(text[4:].strip(), level=3)
        h.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        return

    # Bullet / List
    if text.startswith(("- ", "* ")):
        p = doc.add_paragraph(text[2:].strip(), style='List Bullet')
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        return
    elif re.match(r'^\d+\.\s+', text):
        num_match = re.match(r'^\d+\.\s+(.*)', text)
        clean_item = num_match.group(1) if num_match else text
        p = doc.add_paragraph(clean_item, style='List Number')
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        return

    # Blockquote
    if text.startswith("> "):
        p = doc.add_paragraph(text[2:].strip(), style='Intense Quote')
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        return

    # Standard body paragraph
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p.paragraph_format.line_spacing = 1.35
    p.paragraph_format.space_after = Pt(8)
    
    # Process inline bold / code
    # Clean standard markdown bold **bold**
    clean_text = text.replace("**", "").replace("`", "")
    p.add_run(clean_text)


class DocxExporter:
    def export_page(self, page: Page, output_path: Path) -> Path:
        doc = Document()
        
        # Add heading
        heading = doc.add_heading(f"صفحه {page.page_number}", level=1)
        heading.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        
        # Content
        text = (page.approved_text or page.latest_translation or page.source_text).strip()
        storage_dir = getattr(page, "storage_dir", None)
        if not storage_dir and hasattr(page, "project") and page.project:
            storage_dir = page.project.storage_dir

        for paragraph_text in text.split("\n\n"):
            if paragraph_text.strip():
                render_markdown_paragraph_to_docx(doc, paragraph_text.strip(), storage_dir)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(output_path))
        return output_path

    def assemble_book(self, project: Project, pages: List[Page], output_path: Path) -> Path:
        doc = Document()
        
        # Title Page
        title_p = doc.add_heading(project.title, level=0)
        title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        sub = doc.add_paragraph(f"ترجمه از {project.source_language} به {project.target_language}")
        sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        doc.add_page_break()

        for page in pages:
            text = (page.approved_text or page.latest_translation or page.source_text).strip()
            p_head = doc.add_heading(f"صفحه {page.page_number}", level=2)
            p_head.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            
            for par in text.split("\n\n"):
                if par.strip():
                    render_markdown_paragraph_to_docx(doc, par.strip(), project.storage_dir)
            doc.add_paragraph()  # spacing

        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(output_path))
        return output_path
