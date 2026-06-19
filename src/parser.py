"""Convert messy newsletter HTML into clean, readable text."""

import logging
import re
import unicodedata

import html2text
from bs4 import BeautifulSoup
from readability import Document

logger = logging.getLogger(__name__)

MAX_WORDS = 3000


def _strip_noise(soup: BeautifulSoup) -> None:
    """Remove tracking pixels, social buttons, unsubscribe footers, ad blocks."""
    # Tracking pixels: 1x1 images, hidden images
    for img in soup.find_all("img"):
        src = img.get("src", "")
        width = img.get("width", "")
        height = img.get("height", "")
        if width in ("1", "0") or height in ("1", "0"):
            img.decompose()
            continue
        # Common tracking domains
        if any(t in src for t in ["open.substack.com", "tracking", "pixel", "beacon"]):
            img.decompose()
            continue
        # Replace remaining images with alt text
        alt = img.get("alt", "").strip()
        if alt:
            img.replace_with(f"[Image: {alt}]")
        else:
            img.decompose()

    # Unsubscribe / footer sections
    for el in soup.find_all(string=re.compile(r"unsubscribe|manage\s+preferences|email\s+preferences|opt.out", re.I)):
        parent = el.find_parent(["div", "table", "tr", "td", "p", "section"])
        if parent:
            parent.decompose()

    # Social media buttons (common class/id patterns)
    for el in soup.find_all(class_=re.compile(r"social|share|footer|ad-block|advert", re.I)):
        el.decompose()
    for el in soup.find_all(id=re.compile(r"social|share|footer|ad-block|advert", re.I)):
        el.decompose()


def _normalize_text(text: str) -> str:
    """Clean up whitespace and normalize unicode."""
    text = unicodedata.normalize("NFKC", text)
    # Collapse runs of blank lines to max 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Collapse runs of spaces/tabs on a single line
    text = re.sub(r"[^\S\n]+", " ", text)
    return text.strip()


def _extract_links(soup: BeautifulSoup) -> list[dict]:
    """Extract meaningful links from the HTML."""
    links = []
    seen_urls = set()
    for a in soup.find_all("a", href=True):
        url = a["href"].strip()
        text = a.get_text(strip=True)
        # Skip empty, anchor-only, mailto, and tracking links
        if not url or url.startswith("#") or url.startswith("mailto:"):
            continue
        if any(t in url for t in [
            "unsubscribe", "tracking", "click.mailchimp", "list-manage",
            "substack.com/redirect", "substack.com/app-link",
            "/redirect/", "utm_source", "utm_medium", "utm_campaign",
            "click.convertkit", "sendgrid.net/ls", "mailchmp.com",
        ]):
            continue
        if url not in seen_urls and text:
            links.append({"text": text, "url": url})
            seen_urls.add(url)
    return links


def _truncate_words(text: str, max_words: int) -> str:
    """Truncate text to approximately max_words."""
    words = text.split()
    if len(words) <= max_words:
        return text
    truncated = " ".join(words[:max_words])
    return truncated + "\n\n[... truncated]"


def parse_email(email: dict) -> dict:
    """
    Parse a raw email dict into clean text.

    Args:
        email: dict with keys subject, from, date, html_body, text_body

    Returns:
        dict with keys: subject, from, date, clean_text, word_count, links
    """
    subject = email["subject"]
    sender = email["from"]
    html_body = email.get("html_body", "")
    text_body = email.get("text_body", "")

    clean_text = ""
    links = []

    if html_body:
        try:
            # Primary: readability extracts main content, then html2text converts
            doc = Document(html_body)
            readable_html = doc.summary()

            soup = BeautifulSoup(readable_html, "html.parser")
            _strip_noise(soup)
            links = _extract_links(soup)

            converter = html2text.HTML2Text()
            converter.ignore_images = True
            converter.ignore_emphasis = False
            converter.body_width = 0  # No wrapping
            converter.protect_links = True
            converter.wrap_links = False

            clean_text = converter.handle(str(soup))
        except Exception as e:
            logger.warning("Readability failed for '%s', using fallback: %s", subject, e)
            clean_text = ""

    # Fallback: plain BeautifulSoup stripping or raw text body
    if not clean_text.strip():
        if html_body:
            try:
                soup = BeautifulSoup(html_body, "html.parser")
                _strip_noise(soup)
                links = _extract_links(soup)
                clean_text = soup.get_text(separator="\n")
            except Exception as e:
                logger.warning("BeautifulSoup fallback failed for '%s': %s", subject, e)

    if not clean_text.strip() and text_body:
        clean_text = text_body

    clean_text = _normalize_text(clean_text)
    clean_text = _truncate_words(clean_text, MAX_WORDS)
    word_count = len(clean_text.split())

    logger.info("Parsed '%s': %d words, %d links", subject, word_count, len(links))

    return {
        "subject": subject,
        "from": sender,
        "date": str(email["date"]),
        "clean_text": clean_text,
        "word_count": word_count,
        "links": links,
    }
