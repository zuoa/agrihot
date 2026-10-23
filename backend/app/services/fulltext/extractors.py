"""Extract article text from HTML, JATS XML, and text PDFs."""
from __future__ import annotations

import io
import re

from lxml import etree, html
from pypdf import PdfReader
from trafilatura import extract

from .base import FulltextFetchError


def extract_html(content: bytes, url: str) -> str:
    text = extract(content, url=url, output_format="markdown", include_comments=False,
                   include_tables=True, include_links=True, favor_recall=True)
    return text or ""


def article_links(content: bytes, url: str) -> dict[str, str]:
    from urllib.parse import urljoin

    try:
        root = html.fromstring(content)
    except (etree.ParserError, ValueError):
        return {}
    return {kind: urljoin(url, values[0].strip()) for kind in ("xml", "pdf")
            if (values := root.xpath(f'//meta[translate(@name, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")="citation_{kind}_url"]/@content'))
            and values[0].strip()}


def extract_jats(content: bytes) -> str:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False)
    try:
        root = etree.fromstring(content, parser=parser)
    except (etree.XMLSyntaxError, ValueError):
        raise FulltextFetchError("unsupported_content") from None
    articles = root.xpath('self::*[local-name()="article"] | .//*[local-name()="article"]')
    if not articles:
        raise FulltextFetchError("unsupported_content")
    root = articles[0]
    bodies = root.xpath('./*[local-name()="body"]')
    if not bodies or sum(len("".join(body.itertext()).strip()) for body in bodies) < 200:
        raise FulltextFetchError("unsupported_content")

    def words(node):
        return re.sub(r"\s+", " ", "".join(node.itertext())).strip()

    def render(node, level=2):
        tag = etree.QName(node).localname if isinstance(node.tag, str) else ""
        if tag in {"title", "article-title"}:
            return "#" * min(level, 6) + " " + words(node) + "\n\n"
        if tag in {"p", "ref", "caption", "disp-formula"}:
            return words(node) + "\n\n"
        if tag == "table-wrap":
            return "".join(render(child, level) for child in node)
        if tag == "table":
            rows = node.xpath('.//*[local-name()="tr"]')
            if rows:
                return "\n".join(" | ".join(words(cell) for cell in row) for row in rows) + "\n\n"
        if tag in {"sec", "abstract", "ref-list", "body", "fig", "list", "list-item"}:
            return "".join(render(child, level + (tag == "sec" and isinstance(child.tag, str)
                                                 and etree.QName(child).localname == "sec")) for child in node)
        if tag in {"label", "graphic", "supplementary-material"}:
            return ""
        return "".join(render(child, level) for child in node)

    titles = root.xpath('//*[local-name()="article-meta"]/*[local-name()="title-group"]/*[local-name()="article-title"]')
    parts = ["# " + words(titles[0]) + "\n\n"] if titles else []
    for abstract in root.xpath('//*[local-name()="article-meta"]/*[local-name()="abstract"]'):
        parts.append("## Abstract\n\n" + render(abstract))
    for body in bodies:
        parts.append(render(body))
    for refs in root.xpath('//*[local-name()="back"]/*[local-name()="ref-list"]'):
        parts.append("## References\n\n" + render(refs))
    return "".join(parts).strip()


def extract_pdf(content: bytes) -> str:
    if not content.lstrip().startswith(b"%PDF"):
        raise FulltextFetchError("unsupported_content")
    try:
        reader = PdfReader(io.BytesIO(content), strict=False)
        if reader.is_encrypted and not reader.decrypt(""):
            raise FulltextFetchError("content_access_denied")
        if len(reader.pages) > 100:
            raise FulltextFetchError("content_too_large")
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except FulltextFetchError:
        raise
    except Exception:
        raise FulltextFetchError("unsupported_content") from None
    if len(text) < 200:
        raise FulltextFetchError("pdf_no_text")
    return text
