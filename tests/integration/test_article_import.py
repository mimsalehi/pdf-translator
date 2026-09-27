"""End-to-end tests for importing a web article by URL and translating it as a single page."""
import io
import re

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from pdf_translator.adapters.article.http_article_fetcher import HttpArticleFetcher
from pdf_translator.web.routes.project_routes import get_article_fetcher

ARTICLE_URL = "https://blog.example.com/posts/ddd-intro"

PARAGRAPH = (
    "Domain-driven design centres the software on a rich model of the business domain, "
    "built together with domain experts through a shared ubiquitous language. "
)


def _image_bytes(fmt: str, size) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buf, format=fmt)
    return buf.getvalue()


SVG_DIAGRAM = b'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="120"><rect width="200" height="120" fill="#36c"/></svg>'


def _article_html() -> str:
    body_paragraphs = "\n".join(f"<p>{PARAGRAPH * 3} Section note {i}.</p>" for i in range(40))
    return f"""<!doctype html>
<html><head><title>DDD Intro | Example Blog</title>
<meta property="og:title" content="An Introduction to Domain-Driven Design"></head>
<body>
  <nav><a href="/">Home</a> <a href="/about">NAVIGATION-JUNK</a></nav>
  <article>
    <h1>An Introduction to Domain-Driven Design</h1>
    <p>{PARAGRAPH}
       This paragraph is wrapped
       across several source lines.</p>
    <figure>
      <img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" data-src="/img/context-map.webp" alt="Context [map]">
      <figcaption>Figure 1: A context map</figcaption>
    </figure>
    <p>{PARAGRAPH * 2}</p>
    <picture>
      <source srcset="https://cdn.example.com/aggregate-small.png 400w, https://cdn.example.com/aggregate-large.png 1200w">
      <img alt="Aggregate">
    </picture>
    <img src="https://tracker.example.com/pixel.gif" alt="">
    <pre><code class="language-python">class Order:
    def __init__(self, order_id):
        self.order_id = order_id</code></pre>
    <p><img src="/img/layers.svg" alt="Layers"></p>
    {body_paragraphs}
  </article>
  <footer>FOOTER-JUNK</footer>
</body></html>"""


SECTIONED_URL = "https://blog.example.com/articles/extract-service.html"


def _sectioned_article_html() -> str:
    """Shaped like martinfowler.com: intro paragraphs followed by deeply nested <section>s, permalink headings."""
    def step(n: int) -> str:
        return (
            f'<section id="step{n}"><h3><a href="#step{n}">Step {n}. Do thing {n}</a></h3>'
            f"<p>{PARAGRAPH * 2} Step body {n}.</p><p>{PARAGRAPH} Step detail {n}.</p></section>"
        )
    steps = "".join(step(n) for n in range(1, 10))
    return f"""<!doctype html>
<html><head><title>Extract a service</title></head>
<body>
  <nav class="navmenu"><a href="/">Home</a><a href="/tags">Tags</a></nav>
  <main>
    <section class="frontMatter">
      <h1>How to extract a service</h1>
      <p class="abstract"><i>{PARAGRAPH}</i></p>
      <div class="contents"><h2>Contents</h2><ul>
        {"".join(f'<li><a href="#step{n}">Step {n}. Do thing {n}</a></li>' for n in range(1, 10))}
      </ul></div>
    </section>
    <div class="paperBody deep">
      <p>{PARAGRAPH} Intro one.</p>
      <p>{PARAGRAPH} Intro two.</p>
      <p>{PARAGRAPH} Intro three.</p>
      <section id="principles"><h2><a href="#principles">Guiding principles</a></h2>
        <p>{PARAGRAPH} Principles body.</p>
        <section id="single-write"><h3><a href="#single-write">Have a single write copy</a></h3>
          <p>{PARAGRAPH * 2} Single write body.</p></section>
      </section>
      <section id="steps"><h2><a href="#steps">Service extraction steps</a></h2>
        <p>{PARAGRAPH} Steps intro.</p>
        <pre>class Product: pass</pre>
        {steps}
      </section>
    </div>
    <div class="appendix"><section id="ack"><h2>Acknowledgements</h2><p>{PARAGRAPH} Thanks to reviewers.</p></section></div>
  </main>
</body></html>"""


def _handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if url == ARTICLE_URL:
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text=_article_html())
    if url == SECTIONED_URL:
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text=_sectioned_article_html())
    if url == "https://blog.example.com/img/context-map.webp":
        return httpx.Response(200, content=_image_bytes("WEBP", (640, 360)))
    if url == "https://cdn.example.com/aggregate-large.png":
        return httpx.Response(200, content=_image_bytes("PNG", (1200, 700)))
    if url == "https://tracker.example.com/pixel.gif":
        return httpx.Response(200, content=_image_bytes("GIF", (1, 1)))
    if url == "https://blog.example.com/img/layers.svg":
        return httpx.Response(200, headers={"content-type": "image/svg+xml"}, content=SVG_DIAGRAM)
    return httpx.Response(404, text="not found")


@pytest.fixture
def article_client(client: TestClient) -> TestClient:
    fetcher = HttpArticleFetcher(transport=httpx.MockTransport(_handler))
    client.app.dependency_overrides[get_article_fetcher] = lambda: fetcher
    return client


def test_article_url_becomes_single_translated_page_with_local_images(article_client: TestClient):
    create = article_client.post("/api/projects/article", json={"url": ARTICLE_URL})
    assert create.status_code == 201, create.text
    project_id = create.json()["project_id"]
    assert create.json()["total_pages"] == 1

    page = article_client.get(f"/api/projects/{project_id}/pages/1").json()
    assert page["project_title"] == "An Introduction to Domain-Driven Design"
    assert page["source_type"] == "ARTICLE"
    source = page["source_text"]

    # Main content only, prose unwrapped, code fenced with its language.
    assert "NAVIGATION-JUNK" not in source and "FOOTER-JUNK" not in source
    assert "This paragraph is wrapped across several source lines." in source
    assert "```python\nclass Order:\n    def __init__(self, order_id):" in source
    assert "*Figure 1: A context map*" in source

    # Lazy, <picture>/srcset and SVG images are stored locally in document order; the tracking pixel is dropped.
    image_refs = re.findall(r"!\[([^\]]*)\]\(([^)]*)\)", source)
    assert [url for _, url in image_refs] == [
        f"/api/projects/{project_id}/pages/1/images/{i}" for i in (1, 2, 3)
    ]
    assert image_refs[0][0] == "Context map"
    for i in (1, 2, 3):
        img = article_client.get(f"/api/projects/{project_id}/pages/1/images/{i}")
        assert img.status_code == 200
        assert img.content.startswith(b"\x89PNG")
    with Image.open(io.BytesIO(article_client.get(f"/api/projects/{project_id}/pages/1/images/2").content)) as im:
        assert im.width == 1200  # largest srcset candidate was chosen

    assert article_client.get(f"/api/projects/{project_id}/pages/1/thumbnail").status_code == 200
    workspace = article_client.get(f"/projects/{project_id}/pages/1")
    assert workspace.status_code == 200
    assert "Original Article" in workspace.text

    # The article is longer than one provider request, so it is translated in chunks and reassembled.
    assert len(source) > 12000
    assert article_client.post(f"/api/projects/{project_id}/pages/1/approve-for-translation").status_code == 200
    translated = article_client.post(f"/api/projects/{project_id}/pages/1/translate", json={}).json()["translated_text"]
    for i in range(40):
        assert f"Section note {i}." in translated
    for i in (1, 2, 3):
        assert f"(/api/projects/{project_id}/pages/1/images/{i})" in translated
    assert "class Order:" in translated

    reader = article_client.get(f"/projects/{project_id}/reader")
    assert reader.status_code == 200
    assert "Section note 39." in reader.text


def test_unreachable_article_reports_error_and_creates_no_project(article_client: TestClient):
    resp = article_client.post("/api/projects/article", json={"url": "https://blog.example.com/missing"})
    assert resp.status_code == 422
    assert "HTTP 404" in resp.json()["detail"]
    assert "blog.example.com/missing" not in article_client.get("/").text


def test_article_split_into_nested_sections_is_imported_completely(article_client: TestClient):
    project_id = article_client.post("/api/projects/article", json={"url": SECTIONED_URL}).json()["project_id"]
    source = article_client.get(f"/api/projects/{project_id}/pages/1").json()["source_text"]

    for marker in ("Intro one.", "Principles body.", "Single write body.", "Steps intro.", "Thanks to reviewers."):
        assert marker in source
    for n in range(1, 10):
        assert f"### Step {n}. Do thing {n}\n" in source  # permalink headings survive as plain headings
        assert f"Step body {n}." in source and f"Step detail {n}." in source
    assert "## Guiding principles" in source
    assert "```python\nclass Product: pass\n```" in source
    # The table of contents and site navigation are not article content.
    assert "](https://blog.example.com/articles/extract-service.html#step1)" not in source
    assert "Tags" not in source


def test_browser_provider_receives_whole_article_in_one_message(article_client: TestClient, monkeypatch):
    from pdf_translator.application import translation_service

    sent = []

    class RecordingBrowserProvider:
        def __init__(self, provider_type):
            pass

        async def translate(self, source_text, **kwargs):
            sent.append((source_text, kwargs["context_notes"]))
            return source_text

    monkeypatch.setattr(translation_service, "BrowserTranslationProvider", RecordingBrowserProvider)
    article_client.post(
        "/settings",
        data={"name": "Browser", "provider_type": "browser_chatgpt", "model_name": "chatgpt",
              "api_key": "", "system_prompt": "Translate", "temperature": 0.3},
    )
    project_id = article_client.post("/api/projects/article", json={"url": ARTICLE_URL}).json()["project_id"]
    article_client.post(f"/api/projects/{project_id}/pages/1/approve-for-translation")
    assert article_client.post(f"/api/projects/{project_id}/pages/1/translate", json={}).status_code == 200

    assert len(sent) == 1
    text, notes = sent[0]
    assert "Section note 0." in text and "Section note 39." in text
    assert "part 1 of" not in notes
