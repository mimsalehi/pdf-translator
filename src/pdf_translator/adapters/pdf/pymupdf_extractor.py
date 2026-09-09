"""PyMuPDF implementation of PDFExtractorPort with typographical heading detection, in-text image interleaving, automatic code block detection, and exact paragraph preservation."""
from pathlib import Path
import re
from typing import List, Optional
from collections import Counter
import pymupdf as fitz
from pdf_translator.domain.ports import PDFExtractorPort

def is_running_header_footer(text: str, bbox, page_height: float, is_code: bool = False) -> bool:
    """Detects and filters out running headers, running footers, and standalone page numbers."""
    if is_code:
        return False

    cleaned = text.strip()
    if not cleaned:
        return True

    y0, y1 = bbox[1], bbox[3]

    # Check bottom margin (y0 > 92% of page height)
    if y0 > (page_height * 0.92):
        if re.match(r'^(page\s+)?\d{1,4}$', cleaned, re.IGNORECASE) or re.match(r'^[ivxlcdm]{1,6}$', cleaned, re.IGNORECASE):
            return True
        if '|' in cleaned or 'all rights reserved' in cleaned.lower() or 'isbn' in cleaned.lower():
            return True

    # Check top margin (y1 < 8% of page height)
    if y1 < (page_height * 0.08):
        if re.match(r'^(page\s+)?\d{1,4}$', cleaned, re.IGNORECASE) or re.match(r'^[ivxlcdm]{1,6}$', cleaned, re.IGNORECASE):
            return True
        if '|' in cleaned or re.match(r'^(chapter|section|part)\s+\d+', cleaned, re.IGNORECASE):
            return True

    return False

def is_monospace_span(span: dict) -> bool:
    """Detects if a span is formatted in a monospace/code font."""
    font = span.get("font", "").lower()
    return any(k in font for k in [
        "mono", "courier", "consolas", "code", "typewriter", "inconsolata",
        "menlo", "fira", "thesansmono", "sourcecode", "jetbrains", "dejavu", "ubuntu"
    ])

def detect_code_language(code: str) -> str:
    """Accurately detects programming language (PHP, Python, JavaScript, SQL, JSON, HTML, Bash, Go, Rust, Java, C++, etc.)."""
    cleaned = code.strip()
    if not cleaned:
        return ""

    # PHP Detection (tags, $variables, -> methods, new \Namespace)
    if re.search(r'<\?php|\$[a-zA-Z_\x7f-\xff][a-zA-Z0-9_\x7f-\xff]*|->[a-zA-Z_]|new\s+\\[A-Z]|namespace\s+[A-Z]|use\s+[A-Z]', cleaned):
        return "php"

    # Python Detection
    if re.search(r'^\s*(def\s+\w+\s*\(|class\s+\w+(\(.*\))?\s*:|import\s+\w+|from\s+\w+\s+import|@\w+|if\s+__name__\s*==|elif\s+|self\.\w+)', cleaned, re.MULTILINE):
        return "python"

    # JSON
    if (cleaned.startswith("{") and cleaned.endswith("}")) or (cleaned.startswith("[") and cleaned.endswith("]")):
        if '"' in cleaned and ":" in cleaned:
            return "json"

    # HTML / XML
    if re.search(r'<!DOCTYPE|<html|<div|<span|<p\b|<table|<script|<\/[a-zA-Z]+>', cleaned, re.IGNORECASE):
        return "html"

    # SQL
    if re.search(r'\b(SELECT\s+.*FROM|INSERT\s+INTO|UPDATE\s+.*SET|DELETE\s+FROM|CREATE\s+TABLE|ALTER\s+TABLE)\b', cleaned, re.IGNORECASE):
        return "sql"

    # JavaScript / TypeScript
    if re.search(r'\b(const\s+\w+\s*=|let\s+\w+\s*=|var\s+\w+\s*=|function\s*\w*\s*\(|console\.log|export\s+(default\s+)?|import\s+.*\s+from\s+[\'\"]|=>|\binterface\s+[A-Z]|\btype\s+[A-Z]\w*\s*=)', cleaned):
        return "javascript"

    # Bash / Shell / Terminal
    if re.search(r'^\s*([\$]|npm\b|pip\b|docker\b|curl\b|git\b|sudo\b|cd\b|chmod\b)', cleaned, re.MULTILINE):
        return "bash"

    # Rust
    if re.search(r'\b(fn\s+\w+\s*\(|let\s+mut\s+|impl\s+|pub\s+fn|println!\s*\()', cleaned):
        return "rust"

    # Go
    if re.search(r'\b(package\s+\w+|func\s+(\(\w+\s+\*?\w+\)\s+)?\w+\s*\(|fmt\.Println|type\s+\w+\s+struct)', cleaned):
        return "go"

    # Java / C#
    if re.search(r'\b(public\s+class|public\s+static\s+void|System\.out\.print|namespace\s+\w+\s*\{|using\s+System;)', cleaned):
        return "java"

    # C / C++
    if re.search(r'(#include\s+<[a-z.]+>|std::cout|int\s+main\s*\()', cleaned):
        return "cpp"

    return ""

def format_geometric_code_block(code_meta_list: List[dict]) -> str:
    """
    Reconstructs exact indentation and vertical empty lines of code blocks
    from PDF geometric coordinates (x0, y0, char_w, size).
    """
    if not code_meta_list:
        return ""
    non_empty = [l for l in code_meta_list if l["text"].strip()]
    if not non_empty:
        return "\n".join(l["text"] for l in code_meta_list)

    min_x0 = min(l["x0"] for l in non_empty)
    char_widths = [l["char_w"] for l in non_empty if l["char_w"] > 0]
    avg_char_w = sum(char_widths) / len(char_widths) if char_widths else 5.12

    sizes = [l.get("size", 10.0) for l in non_empty]
    avg_size = sum(sizes) / len(sizes) if sizes else 10.0
    line_height_threshold = avg_size * 1.65

    formatted = []
    prev_y0 = None

    for l in code_meta_list:
        raw_text = l["text"]
        if not raw_text.strip():
            formatted.append("")
            prev_y0 = l["y0"]
            continue

        if prev_y0 is not None:
            y_diff = l["y0"] - prev_y0
            if y_diff >= line_height_threshold:
                # Add an empty line for vertical method/block separation
                formatted.append("")

        num_spaces = int(round((l["x0"] - min_x0) / avg_char_w))
        indent = " " * num_spaces if num_spaces > 0 else ""
        formatted.append(indent + raw_text.rstrip())
        prev_y0 = l["y0"]

    return "\n".join(formatted).rstrip()

def merge_split_heading_paragraphs(paras: List[str]) -> List[str]:
    """
    Merges orphaned section/chapter numbers (e.g. '## 2.3', '### 2.3.1', '# Chapter 1')
    with their immediately subsequent heading title paragraph.
    """
    merged = []
    i = 0
    while i < len(paras):
        curr = paras[i].strip()
        match = re.match(r"^(#+)\s+((?:(?:Chapter|Section|Part|Appendix)\s+)?\d+(?:\.\d+)*\.?)$", curr, re.IGNORECASE)
        if match and i + 1 < len(paras):
            hashes = match.group(1)
            num_part = match.group(2)
            nxt = paras[i + 1].strip()

            nxt_match = re.match(r"^(#+)\s+(.*)", nxt)
            if nxt_match:
                title_part = nxt_match.group(2).strip()
                merged.append(f"{hashes} {num_part} {title_part}")
                i += 2
                continue
            elif not nxt.startswith(("#", "- ", "* ", "`", "!", "```")) and len(nxt) < 100 and not nxt.endswith((".", ":", ";", "!", "?")):
                merged.append(f"{hashes} {num_part} {nxt}")
                i += 2
                continue

        merged.append(curr)
        i += 1

    # Merge multiline headings of the same level (e.g. # Chapter 1 Introduction... followed by # Design Patterns)
    final_merged = []
    i = 0
    while i < len(merged):
        curr = merged[i].strip()
        if i + 1 < len(merged):
            nxt = merged[i + 1].strip()
            m1 = re.match(r"^(#{1,3})\s+(.*)", curr)
            m2 = re.match(r"^(#{1,3})\s+(.*)", nxt)
            if m1 and m2 and m1.group(1) == m2.group(1):
                t1 = m1.group(2).strip()
                t2 = m2.group(2).strip()
                if len(t1) < 60 and not t1.endswith((".", ":", ";", "!", "?")) and not t2.endswith((".", ";", "!")) and not re.match(r"^\d+", t2):
                    final_merged.append(f"{m1.group(1)} {t1} {t2}")
                    i += 2
                    continue
        final_merged.append(curr)
        i += 1

    return final_merged

merge_split_heading_numbers = merge_split_heading_paragraphs

def stitch_broken_paragraphs(paras: List[str]) -> List[str]:
    """
    Stitches distinct PDF blocks that were split across a line break without sentence-ending punctuation.
    """
    stitched = []
    i = 0
    while i < len(paras):
        curr = paras[i].strip()
        if i + 1 < len(paras):
            nxt = paras[i + 1].strip()
            # Never stitch into or from headings, bullet lists, code blocks, or images
            if not curr.startswith(("#", "- ", "* ", "```", "![")) and not nxt.startswith(("#", "- ", "* ", "```", "![")) and not re.match(r"^\d+[\.\)]\s+", nxt):
                last_char = curr[-1]
                if last_char not in {".", "!", "?", ":", "\"", "'", "”", "’", "`"} and not curr.endswith(("...", ".\"", "!\"", "?\"")):
                    stitched.append(curr + " " + nxt)
                    i += 2
                    continue
        stitched.append(curr)
        i += 1
    return stitched

def extract_semantic_markdown_from_page(
    doc,
    page_number: int,
    project_id: Optional[str] = None,
    images_dir: Optional[Path] = None
) -> str:
    """
    Extracts text using PDF font-size and weight dictionary analysis.
    Preserves exact paragraph boundaries, identifies headings (#, ##, ###),
    merges section numbers with titles, formats code blocks (```lang ... ```),
    inline code (`...`), bullet lists, and interleaves embedded diagrams/images.
    """
    page = doc[page_number - 1]
    page_rect = page.rect
    data = page.get_text("dict")

    # 1. Determine body font size (most common non-code font size)
    sizes = []
    for b in data.get("blocks", []):
        if "lines" in b:
            for l in b["lines"]:
                for s in l["spans"]:
                    if s["text"].strip() and not is_monospace_span(s):
                        sizes.append(round(s["size"], 1))

    body_size = Counter(sizes).most_common(1)[0][0] if sizes else 10.0

    # 2. Extract and save embedded images
    image_items = []
    img_infos = page.get_image_info(xrefs=True)
    valid_img_idx = 1
    for info in img_infos:
        w = info.get("width", 0)
        h = info.get("height", 0)
        bbox = info.get("bbox", (0, 0, 0, 0))
        # Filter out tiny icon decorations or full-page background covers
        if w > 40 and h > 40 and (bbox[3] - bbox[1]) > 30 and (bbox[2] - bbox[0]) > 30:
            xref = info.get("xref", 0)
            if images_dir:
                images_dir.mkdir(parents=True, exist_ok=True)
                img_file = images_dir / f"page_{page_number}_img_{valid_img_idx}.png"
                if not img_file.exists():
                    saved = False
                    if xref > 0:
                        try:
                            pix = fitz.Pixmap(doc, xref)
                            if pix.colorspace and pix.colorspace != fitz.csRGB:
                                pix = fitz.Pixmap(fitz.csRGB, pix)
                            pix.save(str(img_file))
                            saved = True
                        except Exception:
                            saved = False
                    if not saved:
                        try:
                            rect = fitz.Rect(bbox)
                            if not rect.is_empty and not rect.is_infinite:
                                pix = page.get_pixmap(clip=rect, dpi=150)
                                pix.save(str(img_file))
                                saved = True
                        except Exception:
                            pass

            proj_part = f"/api/projects/{project_id}" if project_id else "/api/projects/default"
            img_url = f"{proj_part}/pages/{page_number}/images/{valid_img_idx}"
            image_items.append({
                "type": "image",
                "y0": bbox[1],
                "markdown": f"![Figure/Diagram]({img_url})"
            })
            valid_img_idx += 1

    # 3. Process text and code blocks with typography analysis
    extracted_blocks = []
    current_code_meta = []
    current_code_y0 = 0.0

    for b in data.get("blocks", []):
        if "lines" not in b:
            continue
        bbox = b["bbox"]
        block_text = "".join(s["text"] for l in b["lines"] for s in l["spans"]).strip()

        # Check if block is a code block (predominantly monospace spans)
        mono_chars = sum(len(s["text"]) for l in b["lines"] for s in l["spans"] if is_monospace_span(s))
        total_chars = sum(len(s["text"]) for l in b["lines"] for s in l["spans"])
        is_code_block = (total_chars > 0) and (mono_chars / total_chars > 0.50)

        if is_running_header_footer(block_text, bbox, page_rect.height, is_code=is_code_block):
            continue

        if is_code_block:
            # Accumulate code lines with coordinates for exact indentation & spacing reconstruction
            if not current_code_meta:
                current_code_y0 = bbox[1]
            for l in b["lines"]:
                line_text = "".join(s["text"] for s in l["spans"])
                char_w = 0.0
                sz = 10.0
                for s in l["spans"]:
                    if len(s["text"].strip()) > 0:
                        char_w = (s["bbox"][2] - s["bbox"][0]) / len(s["text"])
                        sz = s["size"]
                        break
                current_code_meta.append({
                    "x0": l["bbox"][0],
                    "y0": l["bbox"][1],
                    "text": line_text,
                    "char_w": char_w or 5.12,
                    "size": sz
                })
            continue
        else:
            # If we were previously accumulating code lines, flush them as a fenced code block
            if current_code_meta:
                code_body = format_geometric_code_block(current_code_meta)
                lang = detect_code_language(code_body)
                fence = f"```{lang}\n{code_body}\n```" if lang else f"```\n{code_body}\n```"
                extracted_blocks.append({"type": "code", "y0": current_code_y0, "markdown": fence})
                current_code_meta = []

        # Process lines within this block
        block_paras = []
        current_bullet_text = None
        current_p_lines = []

        for l in b["lines"]:
            line_parts = []
            line_max_size = 0.0
            line_is_bold = False

            for s in l["spans"]:
                stxt = s["text"]
                sz = round(s["size"], 1)
                font = s.get("font", "").lower()
                flags = s.get("flags", 0)
                bold = bool(flags & 2) or "bold" in font or "black" in font or "heavy" in font or "semi" in font

                if sz > line_max_size:
                    line_max_size = sz
                if bold:
                    line_is_bold = True

                # Inline code detection
                if is_monospace_span(s) and stxt.strip() and not stxt.strip().startswith("`"):
                    prefix = " " if stxt.startswith(" ") else ""
                    suffix = " " if stxt.endswith(" ") else ""
                    line_parts.append(f"{prefix}`{stxt.strip()}`{suffix}")
                else:
                    line_parts.append(stxt)

            line_str = "".join(line_parts).strip()
            if not line_str:
                continue

            # Merge adjacent backticks within line
            line_str = re.sub(r'`\s+`', ' ', line_str)

            # Check if line starts a new bullet item or contains bullet symbols
            if re.search(r'^[•⁃‣]', line_str) or re.match(r'^[\*\-]\s+', line_str):
                if current_bullet_text:
                    block_paras.append(f"- {current_bullet_text}")
                    current_bullet_text = None
                if current_p_lines:
                    block_paras.append(" ".join(current_p_lines))
                    current_p_lines = []

                # Check for multiple bullets in one line
                bullet_parts = [p.strip() for p in re.split(r'\s*[•⁃‣]\s*', line_str) if p.strip()]
                if len(bullet_parts) > 1:
                    for bp in bullet_parts:
                        clean_bp = re.sub(r'^[\*\-]\s*', '', bp).strip()
                        if clean_bp:
                            block_paras.append(f"- {clean_bp}")
                else:
                    clean_b = re.sub(r'^[•⁃‣\*\-]\s*', '', line_str).strip()
                    current_bullet_text = clean_b
            elif line_max_size >= body_size * 1.45:
                if current_bullet_text:
                    block_paras.append(f"- {current_bullet_text}")
                    current_bullet_text = None
                if current_p_lines:
                    block_paras.append(" ".join(current_p_lines))
                    current_p_lines = []
                block_paras.append(f"# {line_str}")
            elif line_max_size >= body_size * 1.18:
                if current_bullet_text:
                    block_paras.append(f"- {current_bullet_text}")
                    current_bullet_text = None
                if current_p_lines:
                    block_paras.append(" ".join(current_p_lines))
                    current_p_lines = []
                block_paras.append(f"## {line_str}")
            elif line_is_bold and len(line_str) < 70 and not line_str.endswith((".", ":", ";", ",", "?", "!")) and not line_str.startswith("`"):
                if current_bullet_text:
                    block_paras.append(f"- {current_bullet_text}")
                    current_bullet_text = None
                if current_p_lines:
                    block_paras.append(" ".join(current_p_lines))
                    current_p_lines = []
                block_paras.append(f"### {line_str}")
            elif re.match(r'^\d+[\.\)]\s+', line_str):
                if current_bullet_text:
                    block_paras.append(f"- {current_bullet_text}")
                    current_bullet_text = None
                if current_p_lines:
                    block_paras.append(" ".join(current_p_lines))
                    current_p_lines = []
                block_paras.append(line_str)
            elif current_bullet_text:
                # Multi-line bullet text continuation!
                current_bullet_text += " " + line_str
            else:
                current_p_lines.append(line_str)

        if current_bullet_text:
            block_paras.append(f"- {current_bullet_text}")
        if current_p_lines:
            block_paras.append(" ".join(current_p_lines))

        for p in block_paras:
            extracted_blocks.append({"type": "text", "y0": bbox[1], "markdown": p})

    # Flush any remaining code block at end of page
    if current_code_meta:
        code_body = format_geometric_code_block(current_code_meta)
        lang = detect_code_language(code_body)
        fence = f"```{lang}\n{code_body}\n```" if lang else f"```\n{code_body}\n```"
        extracted_blocks.append({"type": "code", "y0": current_code_y0, "markdown": fence})

    # 4. Interleave text items, code blocks, and image items sorted by vertical coordinate y0
    all_items = extracted_blocks + image_items
    all_items.sort(key=lambda x: x["y0"])

    raw_paras = [item["markdown"] for item in all_items]
    merged_headings = merge_split_heading_paragraphs(raw_paras)
    stitched_paras = stitch_broken_paragraphs(merged_headings)

    # Normalize whitespace ONLY on non-code paragraphs to preserve 100% code indentation
    cleaned_paras = []
    for p in stitched_paras:
        if p.startswith("```"):
            cleaned_paras.append(p)
        else:
            p_clean = re.sub(r'[\u2010\u2011\u2012\u2013\u2014\u00ad]\s*\n\s*', '-\n', p)
            p_clean = re.sub(r'(\b[A-Za-z]+)-\s*\n\s*([a-z]+)\b', r'\1\2', p_clean)
            p_clean = re.sub(r'[ \t]{2,}', ' ', p_clean)
            cleaned_paras.append(p_clean)

    return "\n\n".join(cleaned_paras).strip()


def stitch_page_boundaries(pages_text: List[str]) -> List[str]:
    """
    Stitches incomplete trailing sentences from Page N into Page N+1's leading sentence ONLY if Page N does not end in a complete sentence.
    Strips the fragment from Page N+1 to guarantee zero duplicated content.
    """
    stitched = list(pages_text)
    for i in range(len(stitched) - 1):
        curr = stitched[i].strip()
        nxt = stitched[i+1].strip()

        if not curr or not nxt:
            continue

        # If nxt starts with a bullet, numbered list, heading, or code block: NEVER stitch across pages!
        if nxt.startswith(("#", "- ", "* ", "```", "![")) or re.match(r"^\d+[\.\)]\s+", nxt):
            continue

        last_line = curr.split('\n')[-1].strip()
        # If curr ends with a bullet, heading, or code block: NEVER stitch across pages!
        if last_line.startswith(("#", "- ", "* ", "![", "```")) or re.match(r"^(CHAPTER|SECTION|PART|\d+[\.\)])\s+", last_line, re.IGNORECASE):
            continue

        last_char = curr[-1]
        is_complete = (
            last_char in {'.', '!', '?', ':', '`', '"', "'", '”', '’', ')', ']', '>', '}'}
            or curr.endswith(('."', '!"', '?"', ".'", "!'", '.)', '!)', '?)', '```'))
        )

        if not is_complete:
            match = re.search(r'^(.*?[.!?])(\s+|$)', nxt, re.DOTALL)
            if match:
                fragment = match.group(1).strip()
                if not fragment.startswith(('#', '- ', '* ', '```', '![')) and not re.match(r'^(CHAPTER|SECTION)\b', fragment, re.IGNORECASE):
                    curr = curr + " " + fragment
                    nxt = nxt[len(match.group(0)):].strip()

                    stitched[i] = curr
                    stitched[i+1] = nxt

    return stitched


class PyMuPDFExtractor(PDFExtractorPort):
    """Adapter for PDF text, code, and image extraction and visual page rendering using PyMuPDF."""

    def get_page_count(self, pdf_path: Path) -> int:
        doc = fitz.open(str(pdf_path))
        try:
            return len(doc)
        finally:
            doc.close()

    def extract_page_content(
        self,
        pdf_path: Path,
        page_number: int,
        project_id: Optional[str] = None,
        images_dir: Optional[Path] = None
    ) -> str:
        """Extracts single page text, code blocks, and diagrams interleaved by vertical coordinate Y0."""
        doc = fitz.open(str(pdf_path))
        try:
            if page_number < 1 or page_number > len(doc):
                raise ValueError(f"Page number {page_number} is out of bounds (1..{len(doc)})")
            return extract_semantic_markdown_from_page(doc, page_number, project_id, images_dir)
        finally:
            doc.close()

    def extract_and_stitch_all_pages(self, pdf_path: Path, project_id: Optional[str] = None, images_dir: Optional[Path] = None) -> List[str]:
        """Extracts all pages with interleaved code blocks, images, and stitches cross-page sentence boundaries."""
        doc = fitz.open(str(pdf_path))
        try:
            total_pages = len(doc)
            raw_pages = []
            for num in range(1, total_pages + 1):
                raw_pages.append(self.extract_page_content(pdf_path, num, project_id, images_dir))
            return stitch_page_boundaries(raw_pages)
        finally:
            doc.close()

    def render_page_image(self, pdf_path: Path, page_number: int, output_image_path: Path, dpi: int = 150) -> Path:
        """Renders page at specified DPI to PNG."""
        doc = fitz.open(str(pdf_path))
        try:
            if page_number < 1 or page_number > len(doc):
                raise ValueError(f"Page number {page_number} is out of bounds (1..{len(doc)})")
            page = doc[page_number - 1]
            zoom = dpi / 72.0
            matrix = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            output_image_path.parent.mkdir(parents=True, exist_ok=True)
            pix.save(str(output_image_path))
            return output_image_path
        finally:
            doc.close()

    def render_thumbnail(self, pdf_path: Path, page_number: int, output_image_path: Path, max_width: int = 300) -> Path:
        """Renders small thumbnail for grid views."""
        doc = fitz.open(str(pdf_path))
        try:
            if page_number < 1 or page_number > len(doc):
                raise ValueError(f"Page number {page_number} is out of bounds (1..{len(doc)})")
            page = doc[page_number - 1]
            rect = page.rect
            scale = max_width / rect.width if rect.width > 0 else 1.0
            matrix = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            output_image_path.parent.mkdir(parents=True, exist_ok=True)
            pix.save(str(output_image_path))
            return output_image_path
        finally:
            doc.close()
