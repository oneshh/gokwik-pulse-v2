"""News sources: Google News RSS and Bing News RSS. Standard library only, no API keys."""

from __future__ import annotations

import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from . import config


@dataclass
class RawItem:
    source: str          # "google" | "bing"
    company: str         # company id
    title: str
    url: str
    publisher: str
    published: str       # ISO 8601 UTC
    summary: str = ""


class SourceError(Exception):
    pass


def _http_get(url: str) -> bytes:
    last = None
    for attempt in range(config.HTTP_RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
            with urllib.request.urlopen(req, timeout=config.HTTP_TIMEOUT) as resp:
                if resp.status != 200:
                    raise SourceError(f"HTTP {resp.status}")
                return resp.read()
        except Exception as exc:  # network errors, timeouts, bad status
            last = exc
            time.sleep(2 ** attempt)
    raise SourceError(f"GET failed after {config.HTTP_RETRIES} tries: {last}")


def _iso(pubdate: str | None) -> str:
    if not pubdate:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        dt = parsedate_to_datetime(pubdate)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError):
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", text or "")).strip()


# ---------------------------------------------------------------- Google News

def google_url(query: str) -> str:
    q = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"


def parse_google(xml_bytes: bytes, company: str) -> list[RawItem]:
    root = ET.fromstring(xml_bytes)
    items = []
    for it in root.iter("item"):
        title = _clean(it.findtext("title"))
        src = it.find("source")
        publisher = _clean(src.text if src is not None else "")
        # Google appends " - Publisher" to every title; strip it.
        if publisher and title.endswith(" - " + publisher):
            title = title[: -len(publisher) - 3].strip()
        items.append(RawItem(
            source="google", company=company, title=title,
            url=(it.findtext("link") or "").strip(),
            publisher=publisher,
            published=_iso(it.findtext("pubDate")),
        ))
    return items


# ---------------------------------------------------------------- Bing News

def bing_url(query: str) -> str:
    q = urllib.parse.quote(query)
    # NOTE: do not add Bing's "sortbydate" option - in RSS mode it ignores the query and returns
    # unrelated stories (seen 2026-11-14: a "Shopflo" search returned GoKwik articles).
    return f"https://www.bing.com/news/search?q={q}&format=rss&mkt=en-IN"


def _bing_real_url(link: str) -> str:
    """Bing wraps links in a click tracker; the publisher URL is in the `url` param."""
    try:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
        return qs.get("url", [link])[0]
    except ValueError:
        return link


def parse_bing(xml_bytes: bytes, company: str) -> list[RawItem]:
    root = ET.fromstring(xml_bytes)
    items = []
    for it in root.iter("item"):
        publisher = ""
        for child in it:
            if child.tag.lower().endswith("source"):
                publisher = _clean(child.text)
        items.append(RawItem(
            source="bing", company=company,
            title=_clean(it.findtext("title")),
            url=_bing_real_url((it.findtext("link") or "").strip()),
            publisher=publisher,
            published=_iso(it.findtext("pubDate")),
            summary=_clean(it.findtext("description")),
        ))
    return items


def google_recent_url(query: str) -> str:
    # Same search limited to the last 30 days. Google's plain search is sorted by relevance and
    # reaches back years (great for backfill); this one guarantees fresh stories aren't missed.
    return google_url(f"{query} when:30d")


SOURCES = {
    "google": (google_url, parse_google),
    "google_recent": (google_recent_url, parse_google),
    "bing": (bing_url, parse_bing),
}

SOURCE_LABELS = {"google": "Google News", "google_recent": "Google News (30d)", "bing": "Bing News"}


def fetch(source: str, company: dict) -> list[RawItem]:
    """Fetch one company from one source. Raises SourceError on network/parse failure."""
    build_url, parse = SOURCES[source]
    body = _http_get(build_url(company["query"]))
    try:
        items = parse(body, company["id"])
    except ET.ParseError as exc:
        raise SourceError(f"bad XML from {source}: {exc}") from exc
    if source in config.STRICT_MATCH_SOURCES:
        pat = re.compile(company["match"], re.I)
        items = [i for i in items if pat.search(i.title + " " + i.summary)]
    return [i for i in items if is_valid(i) and not is_blocked(i.publisher)]


def is_valid(item: RawItem) -> bool:
    """Drop malformed entries so a half-broken parser can't look like a healthy run.
    Only http(s) links are kept (no javascript: or data: URLs reach the page)."""
    return bool(item.title.strip()) and item.url.lower().startswith(("https://", "http://"))


def is_blocked(publisher: str) -> bool:
    """Social posts and company databases are not news coverage."""
    p = publisher.lower()
    return any(b in p for b in config.BLOCKED_PUBLISHERS)
