"""Article history. One JSON file, one record per unique story, so history survives every run.

Dedup rule: a story's identity is its normalised headline. The same story seen again tomorrow,
seen in both sources, or syndicated word-for-word across outlets is ONE article. Each record
remembers every company it mentions, every source that returned it and every outlet that ran it.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path

from .sources import RawItem


def normalise_title(title: str) -> str:
    # Keep non-Latin scripts (Hindi headlines exist); just fold case and compatibility forms.
    t = unicodedata.normalize("NFKC", title).casefold()
    # Apostrophes vanish entirely so "Razorpay's" and "Razorpays" match.
    t = re.sub(r"['\u2019\u2018`]", "", t)
    # Some outlets repeat their own name after a pipe ("... | The Lallantop"); drop it so
    # the same headline from two feeds dedups.
    t = re.sub(r"\s+[|]\s+[^|]{1,40}$", "", t)
    t = re.sub(r"[^\w ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def article_id(title: str) -> str:
    return hashlib.sha1(normalise_title(title).encode()).hexdigest()[:16]


def _is_direct(url: str) -> bool:
    return bool(url) and "news.google.com" not in url


def load(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return json.loads(path.read_text() or "{}")


def save(path: Path, store: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = dict(sorted(store.items(), key=lambda kv: kv[1]["published"], reverse=True))
    path.write_text(json.dumps(ordered, indent=1, ensure_ascii=False) + "\n")


def merge(store: dict[str, dict], items: list[RawItem], today: str) -> dict[str, list[str]]:
    """Fold fetched items into the store in place.

    Returns {company_id: [ids of articles NEW for that company this run]}.
    An article already known for a company is never counted again.
    """
    new_by_company: dict[str, list[str]] = {}
    for it in items:
        if not it.title:
            continue
        aid = article_id(it.title)
        rec = store.get(aid)
        if rec is None:
            rec = store[aid] = {
                "id": aid,
                "title": it.title,
                "url": it.url,
                "publisher": it.publisher,
                "published": it.published,
                "first_seen": today,
                "last_seen": today,
                "companies": [],
                "sources": [],
                "outlets": [],
            }
        rec["last_seen"] = max(rec["last_seen"], today)
        # Prefer a direct publisher link over a news.google.com redirect.
        if _is_direct(it.url) and not _is_direct(rec["url"]):
            rec["url"] = it.url
        # Keep the earliest publish time we've seen.
        rec["published"] = min(rec["published"], it.published)
        if it.source not in rec["sources"]:
            rec["sources"].append(it.source)
        if it.publisher and it.publisher.lower() not in {o.lower() for o in rec["outlets"]}:
            rec["outlets"].append(it.publisher)
        if not rec["publisher"] and it.publisher:
            rec["publisher"] = it.publisher
        if it.company not in rec["companies"]:
            rec["companies"].append(it.company)
            new_by_company.setdefault(it.company, []).append(aid)
    return new_by_company
