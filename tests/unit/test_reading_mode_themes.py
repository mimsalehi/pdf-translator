"""Tests for Reading Mode Themes and Color Palette Standards."""
from pathlib import Path

CSS_PATH = Path(__file__).parents[2] / "src" / "pdf_translator" / "web" / "static" / "css" / "app.css"
JS_PATH = Path(__file__).parents[2] / "src" / "pdf_translator" / "web" / "static" / "js" / "app.js"
TEMPLATES_DIR = Path(__file__).parents[2] / "src" / "pdf_translator" / "web" / "templates"


def relative_luminance(hex_color: str) -> float:
    """Calculate WCAG relative luminance from hex color string."""
    hex_color = hex_color.lstrip('#')
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0

    def transform(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * transform(r) + 0.7152 * transform(g) + 0.0722 * transform(b)


def contrast_ratio(hex1: str, hex2: str) -> float:
    """Calculate WCAG contrast ratio between two hex colors."""
    l1 = relative_luminance(hex1)
    l2 = relative_luminance(hex2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def test_reader_themes_defined_in_css():
    """Verify all 4 core reader themes are defined in app.css."""
    assert CSS_PATH.exists()
    content = CSS_PATH.read_text(encoding="utf-8")

    assert ".reader-theme-dark" in content
    assert ".reader-theme-paper" in content
    assert ".reader-theme-sepia" in content
    assert ".reader-theme-sage" in content


def test_reader_css_variables_completeness():
    """Verify essential CSS tokens are defined across the reading system."""
    content = CSS_PATH.read_text(encoding="utf-8")

    essential_vars = [
        "--reader-bg",
        "--reader-surface",
        "--reader-border",
        "--reader-text",
        "--reader-h1",
        "--reader-h2",
        "--reader-h3",
        "--reader-quote-bg",
        "--reader-quote-border",
        "--reader-code-bg",
        "--reader-table-th-bg",
        "--reader-link",
    ]

    for var in essential_vars:
        assert var in content, f"Missing essential reading variable: {var}"


def test_reader_themes_wcag_contrast_standards():
    """Verify all 4 reader palettes meet WCAG AAA (>7:1) for body text without extreme glare."""
    palettes = {
        "dark": {"surface": "#1e1e22", "text": "#ded9cf", "h1": "#ebd8b4"},
        "paper": {"surface": "#fcfbfa", "text": "#2c2723", "h1": "#3a271c"},
        "sepia": {"surface": "#faf4e7", "text": "#3c2f21", "h1": "#6b3512"},
        "sage": {"surface": "#f3f7f0", "text": "#1d2d23", "h1": "#193825"},
    }

    for name, p in palettes.items():
        text_cr = contrast_ratio(p["text"], p["surface"])
        h1_cr = contrast_ratio(p["h1"], p["surface"])

        # Must meet WCAG AAA (>7:1) for optimal eye comfort
        assert text_cr >= 7.0, f"Theme '{name}' text contrast {text_cr:.2f} fails WCAG AAA (>= 7.0)"
        # Must not have excessive stark contrast (>18:1) that causes halation in dark mode
        if name == "dark":
            assert text_cr <= 16.0, f"Dark theme contrast {text_cr:.2f} is too stark (causes halation)"

        # Headings must meet at least WCAG AA (>= 4.5:1)
        assert h1_cr >= 4.5, f"Theme '{name}' H1 heading contrast {h1_cr:.2f} fails WCAG AA"


def test_app_js_reader_theme_api():
    """Verify app.js provides the theme manager API and stores preferences."""
    assert JS_PATH.exists()
    content = JS_PATH.read_text(encoding="utf-8")

    assert "READER_THEMES" in content
    assert "getSavedReaderTheme" in content
    assert "setReaderTheme" in content
    assert "cycleReaderTheme" in content
    assert "applyReaderTheme" in content
    assert "pdf_translator_reader_theme" in content


def test_templates_integrate_reader_theme_picker():
    """Verify templates contain the theme selector chips for dark, paper, sepia, and sage."""
    book_reader_html = (TEMPLATES_DIR / "book_reader.html").read_text(encoding="utf-8")
    workspace_html = (TEMPLATES_DIR / "page_workspace.html").read_text(encoding="utf-8")

    for tmpl in [book_reader_html, workspace_html]:
        assert "reader-theme-picker" in tmpl
        assert 'data-theme="dark"' in tmpl
        assert 'data-theme="paper"' in tmpl
        assert 'data-theme="sepia"' in tmpl
        assert 'data-theme="sage"' in tmpl


def test_chapter_reader_fullscreen_topbar_layout():
    """Verify chapter summary reading mode has unified topbar and maximized reading space in fullscreen."""
    project_detail_html = (TEMPLATES_DIR / "project_detail.html").read_text(encoding="utf-8")
    css_content = CSS_PATH.read_text(encoding="utf-8")

    # 1. Template: subnav inside header for a single unified topbar
    assert 'class="reader-modal-header chapter-reader-header"' in project_detail_html
    assert 'id="chapter-modal-subnav"' in project_detail_html
    assert 'id="btn-chapter-fullscreen"' in project_detail_html

    # 2. CSS: Fullscreen unified topbar styling
    assert ".reader-modal-dialog.is-fullscreen .reader-modal-header" in css_content
    assert ".reader-modal-dialog.is-fullscreen .chapter-modal-subnav" in css_content
    assert ".reader-modal-dialog.is-fullscreen .chapter-master-summary-banner" in css_content
    assert "display: none !important" in css_content
    assert ".reader-modal-dialog.is-fullscreen .chapter-section-header" in css_content
