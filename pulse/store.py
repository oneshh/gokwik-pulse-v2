"""Article history. One JSON file, one record per unique story, so history survives every run.

Dedup rule: a story's identity is its normalised headline. The same story seen again tomorrow,
seen in both sources, or syndicated word-for-word across outlets is ONE article. Each record
remembers every company it mentions, every source that returned it and every outlet that ran it.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from . import config
from .sources import RawItem

# Same outlet + headline at least this similar + published within MAX_DAYS -> same article
# (catches an outlet editing its headline, or Google and Bing showing slightly different titles).
FUZZY_RATIO = 0.85
FUZZY_MAX_DAYS = 3

_MATCHERS = {c["id"]: re.compile(c["match"], re.I) for c in config.COMPANIES}


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


def publisher_key(name: str) -> str:
    """'Moneycontrol.com', 'moneycontrol' and 'https://www.moneycontrol.com/' -> 'moneycontrol'."""
    k = name.casefold()
    k = re.sub(r"^https?://", "", k)
    k = re.sub(r"^www\.", "", k)
    k = re.sub(r"\.(com|in|co|org|net|news)(\.[a-z]{2})?/?$", "", k)
    k = re.sub(r"^the\s+", "", k)
    return re.sub(r"[^\w]+", "", k)


def relevance(company: str, title: str) -> str:
    """'headline' when the headline names the company, else 'mention' (named only in the body)."""
    m = _MATCHERS.get(company)
    return "headline" if m and m.search(title) else "mention"


def same_numbers(a: str, b: str) -> bool:
    """Headlines that cite different numbers ('Q1' vs 'Q2', '100 jobs' vs '150 jobs') are
    different stories, however similar the wording."""
    nums = lambda t: set(re.findall(r"\d+(?:\.\d+)?", normalise_title(t)))
    return nums(a) == nums(b)


def _days_apart(a: str, b: str) -> float:
    return abs((datetime.fromisoformat(a) - datetime.fromisoformat(b)).total_seconds()) / 86400


def find_existing(store: dict[str, dict], it: RawItem) -> str | None:
    """Return the id of the stored record this item duplicates, or None if it's a new article."""
    aid = article_id(it.title)
    if aid in store:
        return aid
    if _is_direct(it.url):
        for rid, rec in store.items():
            if rec["url"] == it.url:
                return rid
    pk = publisher_key(it.publisher)
    if not pk:
        return None
    norm = normalise_title(it.title)
    for rid, rec in store.items():
        if pk not in {publisher_key(o) for o in rec["outlets"] + [rec["publisher"]]}:
            continue
        if _days_apart(rec["published"], it.published) > FUZZY_MAX_DAYS:
            continue
        if same_numbers(it.title, rec["title"]) and \
                difflib.SequenceMatcher(None, norm, normalise_title(rec["title"])).ratio() >= FUZZY_RATIO:
            return rid
    return None


def _is_direct(url: str) -> bool:
    return bool(url) and "news.google.com" not in url


def load(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text() or "{}")
    for rec in data.values():  # back-fill fields added after a record was first saved
        rel = rec.setdefault("relevance", {})
        for cid in rec["companies"]:
            rel.setdefault(cid, relevance(cid, rec["title"]))
    return data


def load_overrides(path: Path) -> dict[tuple[str, str], str]:
    """Human review decisions: {(article_id, company_id): reason} to exclude from all counts."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text() or "{}")
    return {(e["id"], e["company"]): e.get("reason", "") for e in data.get("exclude", [])}


def apply_overrides(store: dict[str, dict], overrides: dict[tuple[str, str], str]) -> dict[str, dict]:
    """Copy of the store with excluded (article, company) pairs removed. Articles left with no
    company are dropped. The saved history itself is never edited, so a decision can be undone."""
    out = {}
    for aid, rec in store.items():
        comps = [c for c in rec["companies"] if (aid, c) not in overrides]
        if comps:
            out[aid] = {**rec, "companies": comps}
    return out


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
        aid = find_existing(store, it) or article_id(it.title)
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
                "relevance": {},
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
        # Relevance per company: upgrade to 'headline' if any version of the headline names it.
        rel = rec.setdefault("relevance", {})
        if rel.get(it.company) != "headline":
            rel[it.company] = relevance(it.company, it.title)
        if it.company not in rec["companies"]:
            rec["companies"].append(it.company)
            new_by_company.setdefault(it.company, []).append(aid)
    return new_by_company
