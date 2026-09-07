"""Markdown exporter for pages and assembled books."""
from pathlib import Path
from typing import List
from pdf_translator.domain.entities import Project, Page

class MarkdownExporter:
    def export_page(self, page: Page, output_path: Path) -> Path:
        content = f"# Page {page.page_number}\n\n"
        content += (page.approved_text or page.latest_translation or page.source_text).strip()
        content += "\n"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        return output_path

    def assemble_book(self, project: Project, pages: List[Page], output_path: Path) -> Path:
        lines = [f"# {project.title}\n", f"_{project.source_language} → {project.target_language}_\n\n---\n"]
        for p in pages:
            text = (p.approved_text or p.latest_translation or p.source_text).strip()
            lines.append(f"\n<!-- Page {p.page_number} -->\n\n{text}\n\n---\n")
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("".join(lines), encoding="utf-8")
        return output_path
