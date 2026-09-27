"""HTTP implementation of ArticleFetcherPort.

Downloads an article page, isolates its main content with readability, stores every
content image locally as PNG (so the PDF image route, reader and DOCX exporter work
unchanged), and converts the result into the same Markdown dialect the PDF extractor emits.
"""
import asyncio
import base64
import binascii
import io
import re
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Tuple
from urllib.parse import unquote_to_bytes, urljoin, urlparse

import httpx
import pymupdf as fitz
from bs4 import BeautifulSoup, Comment, NavigableString, Tag
from markdownify import MarkdownConverter
from PIL import Image, UnidentifiedImageError
from readability import Document

from pdf_translator.adapters.pdf.pymupdf_extractor import detect_code_language
from pdf_translator.domain.errors import ArticleFetchError
from pdf_translator.domain.ports import ArticleFetcherPort, FetchedArticle

ARTICLE_PAGE_NUMBER = 1
MAX_IMAGES = 80
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_WIDTH = 1600
MIN_IMAGE_SIDE = 48
MIN_CONTENT_CHARS = 400
MIN_ARTICLE_CHARS = 150
DOWNLOAD_CONCURRENCY = 8

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

LAZY_SRC_ATTRS = ("data-src", "data-original", "data-lazy-src", "data-hi-res-src", "data-url")
SRCSET_ATTRS = ("data-srcset", "data-lazy-srcset", "srcset")
STRIP_TAGS = ("script", "style", "noscript", "template", "iframe", "form", "button", "input", "select", "textarea", "svg", "nav", "map")


def best_srcset_candidate(srcset: str) -> Optional[str]:
    """Returns the highest-resolution URL of a srcset attribute."""
    best_url, best_score = None, -1.0
    for candidate in re.split(r"(?<=\d[wx]),\s*|,\s+", srcset.strip()):
        parts = candidate.strip().split()
        if not parts:
            continue
        score = 1.0
        if len(parts) > 1:
            descriptor = parts[-1]
            try:
                if descriptor.endswith("w"):
                    score = float(descriptor[:-1])
                elif descriptor.endswith("x"):
                    score = float(descriptor[:-1]) * 1000.0
            except ValueError:
                pass
        if score > best_score:
            best_url, best_score = parts[0], score
    return best_url


def resolve_image_source(img: Tag) -> Optional[str]:
    """Picks the real image URL of an <img>, seeing through lazy-loading placeholders and <picture>."""
    for attr in LAZY_SRC_ATTRS:
        value = (img.get(attr) or "").strip()
        if value and not value.startswith("data:"):
            return value
    for attr in SRCSET_ATTRS:
        value = (img.get(attr) or "").strip()
        if value:
            best = best_srcset_candidate(value)
            if best:
                return best
    picture = img.find_parent("picture")
    if picture:
        for source in picture.find_all("source"):
            value = (source.get("srcset") or source.get("data-srcset") or "").strip()
            if value:
                best = best_srcset_candidate(value)
                if best:
                    return best
    src = (img.get("src") or "").strip()
    return src or None


def image_to_png(data: bytes) -> Optional[Tuple[bytes, int, int]]:
    """Decodes raster or SVG image bytes into PNG. Returns (png, width, height), or None if undecodable."""
    head = data[:512].lstrip().lower()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in data[:2048].lower()):
        try:
            doc = fitz.open(stream=data, filetype="svg")
            try:
                pix = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                return pix.tobytes("png"), pix.width, pix.height
            finally:
                doc.close()
        except Exception:
            return None

    try:
        with Image.open(io.BytesIO(data)) as im:
            im.seek(0)
            has_alpha = im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info
            frame = im.convert("RGBA" if has_alpha else "RGB")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None

    if frame.width > MAX_IMAGE_WIDTH:
        frame.thumbnail((MAX_IMAGE_WIDTH, MAX_IMAGE_WIDTH * 20))
    out = io.BytesIO()
    frame.save(out, format="PNG")
    return out.getvalue(), frame.width, frame.height


def decode_data_uri(uri: str) -> Optional[bytes]:
    header, sep, payload = uri.partition(",")
    if not sep:
        return None
    try:
        if header.endswith(";base64"):
            return base64.b64decode(payload, validate=False)
        return unquote_to_bytes(payload)
    except (binascii.Error, ValueError):
        return None


def clean_alt_text(alt: str) -> str:
    """Alt text must not break the `![alt](url)` token that translation masking relies on."""
    cleaned = re.sub(r"[\[\]\(\)\n\r\t]+", " ", alt or "")
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned[:150] or "Figure/Diagram"


def code_language_of(pre: Tag) -> str:
    """Reads the language of a <pre> block from `language-xxx`/`lang-xxx` classes, or detects it."""
    classes: List[str] = list(pre.get("class") or [])
    code = pre.find("code")
    if code is not None:
        classes += list(code.get("class") or [])
    for cls in classes:
        match = re.match(r"^(?:lang(?:uage)?-)([A-Za-z0-9_-]+)$", cls)
        if match:
            return match.group(1).lower()
    declared = re.sub(r"[^A-Za-z0-9_-]", "", pre.get("data-lang") or pre.get("data-language") or "")
    return declared.lower() or detect_code_language(pre.get_text())


LAYOUT_CELL_TEXT_CHARS = 300


def is_layout_table(table: Tag) -> bool:
    """True for tables used for page layout (old-school sites) rather than tabular data."""
    if table.find("th") is not None:
        return False
    for cell in table.find_all("td"):
        if cell.find(["table", "p", "div", "pre", "ul", "ol", "img", "h1", "h2", "h3", "blockquote"]):
            return True
        if len(cell.get_text(" ", strip=True)) > LAYOUT_CELL_TEXT_CHARS:
            return True
    return False


MIN_MATCH_PARAGRAPH_CHARS = 40
LINK_DENSITY_LIMIT = 0.6
MAX_WRAPPER_LEVELS = 4
PAGE_ROOTS = ("body", "html", "[document]")
# Blocks that are never article content, wherever they appear.
NON_ARTICLE_BLOCK = re.compile(
    r"(?:^|[-_\s])(?:comments?|related|recommend(?:ed|ations)?|share|sharing|social|promo|"
    r"newsletter|subscribe|advert(?:isement)?|sponsor(?:ed)?|disqus)(?:[-_\s]|$)",
    re.IGNORECASE,
)
# Page chrome that must not pull the article boundary outwards (but may hold in-article asides).
PAGE_CHROME_BLOCK = re.compile(r"(?:^|[-_\s])(?:sidebar|secondary|footer|header|menu)(?:[-_\s]|$)", re.IGNORECASE)


def _normalized_text(el: Tag) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ")).strip()


def paragraph_texts(root: Tag) -> set:
    """Whitespace-normalized texts of the substantial paragraphs, list items and code blocks under `root`."""
    return {
        text
        for el in root.find_all(["p", "li", "pre"])
        if len(text := _normalized_text(el)) >= MIN_MATCH_PARAGRAPH_CHARS
    }


def _is_non_article_block(el: Tag) -> bool:
    if el.name in ("nav", "form"):
        return True
    return bool(NON_ARTICLE_BLOCK.search(_block_marker(el)))


def _is_page_chrome(el: Tag) -> bool:
    return el.name in ("aside", "footer", "header") or bool(PAGE_CHROME_BLOCK.search(_block_marker(el)))


def _block_marker(el: Tag) -> str:
    return " ".join(el.get("class") or []) + " " + (el.get("id") or "")


def _prose_chars(el: Tag) -> int:
    """Characters of real prose under `el`: substantial paragraphs/code that are not mostly link text."""
    if not isinstance(el, Tag):
        return 0
    total = 0
    for block in [el] if el.name in ("p", "pre") else el.find_all(["p", "pre"]):
        text_chars = len(block.get_text(" ", strip=True))
        link_chars = sum(len(a.get_text(" ", strip=True)) for a in block.find_all("a"))
        if text_chars >= MIN_MATCH_PARAGRAPH_CHARS and link_chars / text_chars < 0.5:
            total += text_chars
    return total


def enclosing_container(summary: Tag, soup: BeautifulSoup) -> Optional[Tag]:
    """
    Locates readability's pick in the original page (the deepest element containing every paragraph it
    kept), then grows it while neighbouring blocks carry more article prose. readability scores
    paragraphs by their direct parent, so articles split into nested <section>s often come back as a
    single section or just the intro.
    """
    kept = paragraph_texts(summary)
    matched = [el for el in soup.find_all(["p", "li", "pre"]) if _normalized_text(el) in kept]
    if not matched:
        return None
    common = {id(parent) for parent in matched[0].parents}
    for el in matched[1:]:
        common &= {id(parent) for parent in el.parents}
    node = next((parent for parent in matched[0].parents if id(parent) in common), None)
    if node is None or node.name in PAGE_ROOTS:
        return None

    candidate, wrapper_levels = node, 0
    while candidate.parent is not None and candidate.parent.name not in PAGE_ROOTS and wrapper_levels < MAX_WRAPPER_LEVELS:
        parent = candidate.parent
        sibling_prose = sum(
            _prose_chars(sibling)
            for sibling in parent.find_all(recursive=False)
            if sibling is not candidate and not _is_non_article_block(sibling) and not _is_page_chrome(sibling)
        )
        candidate = parent
        if sibling_prose >= MIN_MATCH_PARAGRAPH_CHARS:
            node, wrapper_levels = parent, 0
        else:
            wrapper_levels += 1  # pure wrapper: look further up, but only adopt it if prose is found there
    return node


def prune_non_article_blocks(content: Tag) -> None:
    """Drops comments/related/share sections and navigation-like, mostly-link blocks (e.g. tables of contents)."""
    for block in content.find_all(True):
        if block.decomposed:
            continue
        if _is_non_article_block(block):
            block.decompose()
            continue
        if block.name not in ("ul", "ol", "div") or block.find(["img", "pre", "table"]):
            continue
        text_chars = len(block.get_text(" ", strip=True))
        link_chars = sum(len(a.get_text(" ", strip=True)) for a in block.find_all("a"))
        if text_chars and link_chars / text_chars > LINK_DENSITY_LIMIT:
            block.decompose()


class _ArticleMarkdownConverter(MarkdownConverter):
    def convert_figcaption(self, el, text, parent_tags=None, **kwargs):
        text = text.strip()
        return f"\n\n*{text}*\n\n" if text else ""


class PageRenderer(Protocol):
    """A real browser able to render pages that plain HTTP cannot fetch (bot checks, client-side rendering)."""

    async def render_page_html(self, url: str) -> Tuple[str, str]: ...

    async def fetch_resource(self, url: str, referer: str, max_bytes: int) -> Optional[bytes]: ...


class _RetryWithBrowser(ArticleFetchError):
    """Plain HTTP failed in a way a real browser may get past."""


class HttpArticleFetcher(ArticleFetcherPort):
    """Fetches web articles over HTTP(S), falling back to a real browser, and converts them into one Markdown page."""

    def __init__(
        self,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        timeout: float = 30.0,
        page_renderer: Optional[PageRenderer] = None,
    ):
        self.transport = transport
        self.timeout = timeout
        self.page_renderer = page_renderer

    async def fetch_article(self, url: str, project_id: str, images_dir: Path) -> FetchedArticle:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ArticleFetchError(url, "Only http(s) URLs are supported.")

        async with httpx.AsyncClient(
            transport=self.transport,
            headers=BROWSER_HEADERS,
            follow_redirects=True,
            timeout=self.timeout,
        ) as client:
            rendered_by_browser = False
            try:
                html, final_url = await self._download_page(client, url)
                title, content = await asyncio.to_thread(self._prepare_content, html, final_url)
                if self.page_renderer is not None and len(content.get_text(" ", strip=True)) < MIN_ARTICLE_CHARS:
                    raise _RetryWithBrowser(url, "The static HTML contains almost no article text.")
            except _RetryWithBrowser as http_failure:
                if self.page_renderer is None:
                    raise ArticleFetchError(url, http_failure.details) from None
                try:
                    html, final_url = await self.page_renderer.render_page_html(url)
                except Exception as browser_err:
                    raise ArticleFetchError(
                        url, f"{http_failure.details} Browser fallback also failed: {browser_err}"
                    ) from browser_err
                title, content = await asyncio.to_thread(self._prepare_content, html, final_url)
                rendered_by_browser = True

            image_count = await self._localize_images(
                client, content, final_url, project_id, images_dir, use_browser=rendered_by_browser
            )

        markdown = await asyncio.to_thread(self._to_markdown, content, title)
        prose = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", markdown)
        if len(prose.strip()) < MIN_ARTICLE_CHARS:
            raise ArticleFetchError(
                url,
                "No readable article text was found. The page may require a login or a subscription.",
            )
        return FetchedArticle(title=title, markdown=markdown, final_url=final_url, image_count=image_count)

    # --- Page download -------------------------------------------------------------------

    async def _download_page(self, client: httpx.AsyncClient, url: str) -> Tuple[object, str]:
        try:
            response = await client.get(url)
        except httpx.HTTPError as err:
            raise _RetryWithBrowser(url, f"Network error: {str(err) or type(err).__name__}.") from err

        if response.status_code in (401, 403, 429) or response.status_code >= 500:
            raise _RetryWithBrowser(url, f"Server responded with HTTP {response.status_code}.")
        if response.status_code >= 400:
            raise ArticleFetchError(url, f"Server responded with HTTP {response.status_code}.")

        content_type = response.headers.get("content-type", "").lower()
        if "pdf" in content_type:
            raise ArticleFetchError(url, "The URL points to a PDF file. Download it and create a PDF project instead.")
        if content_type and "html" not in content_type and "xml" not in content_type:
            raise ArticleFetchError(url, f"Unsupported content type '{content_type}'. Expected an HTML page.")

        # Honour an explicit HTTP charset; otherwise let BeautifulSoup sniff <meta charset>.
        html: object = response.text if response.charset_encoding else response.content
        return html, str(response.url)

    def _prepare_content(self, html: object, final_url: str) -> Tuple[str, Tag]:
        """Parses the page and returns (title, cleaned main-content soup). CPU-bound; run off the event loop."""
        soup = BeautifulSoup(html, "lxml")
        title = self._extract_title(soup)
        self._normalize_media_and_links(soup, final_url)
        content = self._extract_main_content(soup)
        self._clean_content(content)
        return title, content

    # --- HTML preparation ----------------------------------------------------------------

    @staticmethod
    def _extract_title(soup: BeautifulSoup) -> str:
        for attrs in ({"property": "og:title"}, {"name": "twitter:title"}):
            meta = soup.find("meta", attrs=attrs)
            if meta and (meta.get("content") or "").strip():
                return meta["content"].strip()
        h1 = soup.find("h1")
        if h1 and h1.get_text(strip=True):
            return h1.get_text(" ", strip=True)
        if soup.title and soup.title.get_text(strip=True):
            return soup.title.get_text(" ", strip=True)
        return ""

    @staticmethod
    def _normalize_media_and_links(soup: BeautifulSoup, base_url: str) -> None:
        """Makes lazy-loaded and <picture> images plain `<img src=absolute>` so readability keeps them."""
        for noscript in soup.find_all("noscript"):
            if not noscript.find("img"):
                continue
            parent = noscript.parent
            has_sibling_img = parent is not None and any(
                img.find_parent("noscript") is None for img in parent.find_all("img")
            )
            if has_sibling_img:
                noscript.decompose()
            else:
                noscript.unwrap()

        for img in soup.find_all("img"):
            source = resolve_image_source(img)
            if not source:
                img.decompose()
                continue
            absolute = source if source.startswith("data:") else urljoin(base_url, source)
            alt = img.get("alt") or ""
            img.attrs = {"src": absolute, "alt": alt}
            picture = img.find_parent("picture")
            if picture is not None:
                picture.replace_with(img)

        # readability prunes wrapper <div>s that hold an image but little text, so strip figures down to
        # image + caption and turn text-less image wrappers into paragraphs, which it keeps.
        for figure in soup.find_all("figure"):
            images = [img.extract() for img in figure.find_all("img")]
            if not images:
                continue
            caption = figure.find("figcaption")
            caption = caption.extract() if caption is not None else None
            figure.clear()
            for img in images:
                figure.append(img)
            if caption is not None:
                figure.append(caption)
        for img in soup.find_all("img"):
            wrapper = img.parent
            while (
                wrapper is not None
                and wrapper.name in ("div", "span", "a")
                and not wrapper.get_text(strip=True)
                and len(wrapper.find_all("img")) == 1
            ):
                outer = wrapper.parent
                if outer is None or outer.name not in ("div", "span", "a") or outer.get_text(strip=True) or len(outer.find_all("img")) != 1:
                    wrapper.name = "p"
                    wrapper.attrs = {}
                    break
                wrapper = outer

        # readability drops headings whose text is mostly a link, which is how permalink anchors look.
        for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            for anchor in heading.find_all("a"):
                anchor.unwrap()

        for anchor in soup.find_all("a", href=True):
            anchor["href"] = urljoin(base_url, anchor["href"])

    @staticmethod
    def _extract_main_content(soup: BeautifulSoup) -> Tag:
        document = Document(str(soup))
        content = BeautifulSoup(document.summary(html_partial=True), "lxml")
        content_chars = len(content.get_text(" ", strip=True))

        # When the article body around readability's pick holds substantial prose it dropped
        # (typically whole <section>s), that body is the real article.
        container = enclosing_container(content, soup)
        if container is not None:
            recovered = BeautifulSoup(str(container), "lxml")
            prune_non_article_blocks(recovered)
            kept = paragraph_texts(content)
            dropped_prose = sum(len(text) for text in paragraph_texts(recovered) if text not in kept)
            if dropped_prose >= MIN_CONTENT_CHARS:
                return recovered

        if content_chars >= MIN_CONTENT_CHARS:
            return content

        # readability found too little: fall back to the most specific semantic container.
        for selector in ("article", "[role=main]", "main", "body"):
            node = soup.select_one(selector)
            if node is not None and len(node.get_text(" ", strip=True)) >= MIN_CONTENT_CHARS:
                return BeautifulSoup(str(node), "lxml")
        return content

    @staticmethod
    def _clean_content(content: Tag) -> None:
        for tag in content.find_all(STRIP_TAGS):
            tag.decompose()
        # A link wrapping an image would become `[![..](..)](..)` and break image masking.
        for anchor in content.find_all("a"):
            if anchor.find("img"):
                anchor.unwrap()
        for pre in content.find_all("pre"):
            pre["data-detected-lang"] = code_language_of(pre)
        # Innermost first, so nested layout tables are flattened before their parents are judged.
        for table in reversed(content.find_all("table")):
            if is_layout_table(table):
                for cell in table.find_all(["td", "th"]):
                    cell.name = "div"
                    table.insert_before(cell.extract())
                table.decompose()
        # readability sometimes drops the <table> but keeps its rows and cells.
        for part in content.find_all(["tr", "td", "th", "tbody", "thead", "tfoot"]):
            if part.find_parent("table") is None:
                part.name = "div"
        for comment in content.find_all(string=lambda s: isinstance(s, Comment)):
            comment.extract()
        # Source HTML wraps prose at arbitrary columns; outside <pre> those newlines are not content.
        for text_node in content.find_all(string=True):
            if text_node.find_parent("pre") is None and re.search(r"\s{2,}|\n", text_node):
                text_node.replace_with(NavigableString(re.sub(r"\s+", " ", text_node)))

    # --- Images --------------------------------------------------------------------------

    async def _localize_images(
        self,
        client: httpx.AsyncClient,
        content: Tag,
        referer: str,
        project_id: str,
        images_dir: Path,
        use_browser: bool,
    ) -> int:
        images_dir.mkdir(parents=True, exist_ok=True)
        for stale in images_dir.glob(f"page_{ARTICLE_PAGE_NUMBER}_img_*.png"):
            stale.unlink()

        imgs = content.find_all("img")
        unique_sources: List[str] = []
        for img in imgs:
            src = img.get("src", "")
            if src and src not in unique_sources:
                unique_sources.append(src)
        unique_sources = unique_sources[:MAX_IMAGES]

        limiter = asyncio.Semaphore(DOWNLOAD_CONCURRENCY)

        async def fetch(src: str) -> Optional[Tuple[bytes, int, int]]:
            async with limiter:
                data = await self._download_image(client, src, referer, use_browser)
            return await asyncio.to_thread(image_to_png, data) if data else None

        decoded = await asyncio.gather(*(fetch(src) for src in unique_sources))
        results: Dict[str, Optional[Tuple[bytes, int, int]]] = dict(zip(unique_sources, decoded))

        seen = set()
        next_index = 1
        for img in imgs:
            src = img.get("src", "")
            if src in seen:
                img.decompose()
                continue
            seen.add(src)

            result = results.get(src)
            if result is None:
                # Undownloadable or undecodable: keep the remote reference so nothing silently disappears.
                if src.startswith("data:"):
                    img.decompose()
                else:
                    img["alt"] = clean_alt_text(img.get("alt", ""))
                continue

            png, width, height = result
            if width < MIN_IMAGE_SIDE or height < MIN_IMAGE_SIDE:
                img.decompose()  # tracking pixels, avatars, icons
                continue

            (images_dir / f"page_{ARTICLE_PAGE_NUMBER}_img_{next_index}.png").write_bytes(png)
            img["src"] = f"/api/projects/{project_id}/pages/{ARTICLE_PAGE_NUMBER}/images/{next_index}"
            img["alt"] = clean_alt_text(img.get("alt", ""))
            next_index += 1

        return next_index - 1

    async def _download_image(
        self, client: httpx.AsyncClient, src: str, referer: str, use_browser: bool
    ) -> Optional[bytes]:
        if src.startswith("data:"):
            return decode_data_uri(src)
        data = None
        try:
            async with client.stream("GET", src, headers={"Referer": referer}) as response:
                if response.status_code < 400:
                    chunks = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_IMAGE_BYTES:
                            chunks = None
                            break
                        chunks.append(chunk)
                    data = b"".join(chunks) if chunks is not None else None
        except httpx.HTTPError:
            data = None
        if data is None and use_browser and self.page_renderer is not None:
            data = await self.page_renderer.fetch_resource(src, referer, MAX_IMAGE_BYTES)
        return data

    # --- Markdown ------------------------------------------------------------------------

    @staticmethod
    def _to_markdown(content: Tag, title: str) -> str:
        converter = _ArticleMarkdownConverter(
            heading_style="ATX",
            bullets="-",
            escape_underscores=False,
            code_language_callback=lambda el: el.get("data-detected-lang") or "",
        )
        markdown = converter.convert_soup(content)

        # Images always stand as their own paragraph, like PDF-extracted diagrams.
        markdown = re.sub(r"[ \t]*(!\[[^\]\n]*\]\([^)\s]+\))[ \t]*", r"\n\n\1\n\n", markdown)
        markdown = re.sub(r"[ \t]+\n", "\n", markdown)
        markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()

        first_heading = re.match(r"^#{1,2}\s+(.+)$", markdown, flags=re.MULTILINE)
        if title and not (first_heading and first_heading.group(1).strip().lower() == title.strip().lower()):
            markdown = f"# {title}\n\n{markdown}"
        return markdown
