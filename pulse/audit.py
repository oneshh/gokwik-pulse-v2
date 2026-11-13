"""Data-quality audit:  python -m pulse.audit

Checks the saved history the way an RCA reviewer would:
  1. exact duplicates          - same id or same direct URL twice            (must be 0, exit 1 otherwise)
  2. same-outlet near-dupes    - one outlet, near-identical headline, <=3 d  (must be 0, exit 1 otherwise)
  3. cross-outlet same story   - different outlets covering one event        (expected; listed for info)
  4. relevance                 - articles that only mention a company in the body
  5. overrides                 - human exclusions, and whether each id still exists
"""

from __future__ import annotations

import collections
import difflib
import sys

from . import config, store

STORY_RATIO = 0.75


def run(articles: dict[str, dict], overrides: dict) -> dict:
    A = list(articles.values())
    norm = {a["id"]: store.normalise_title(a["title"]) for a in A}
    urls = collections.Counter(a["url"] for a in A if "news.google.com" not in a["url"])
    exact = [u for u, n in urls.items() if n > 1]

    same_outlet, cross_outlet = [], []
    for i in range(len(A)):
        for j in range(i + 1, len(A)):
            a, b = A[i], A[j]
            if store._days_apart(a["published"], b["published"]) > store.FUZZY_MAX_DAYS:
                continue
            r = difflib.SequenceMatcher(None, norm[a["id"]], norm[b["id"]]).ratio()
            pa = {store.publisher_key(o) for o in a["outlets"] + [a["publisher"]]} - {""}
            pb = {store.publisher_key(o) for o in b["outlets"] + [b["publisher"]]} - {""}
            if pa & pb and r >= store.FUZZY_RATIO and store.same_numbers(a["title"], b["title"]):
                same_outlet.append((r, a, b))
            elif r >= STORY_RATIO:
                cross_outlet.append((r, a, b))

    mentions = [(a, c) for a in A for c in a["companies"]
                if a.get("relevance", {}).get(c) != "headline" and (a["id"], c) not in overrides]
    missing = [k for k in overrides if k[0] not in articles]
    return {"exact": exact, "same_outlet": same_outlet, "cross_outlet": cross_outlet,
            "mentions": mentions, "overrides": overrides, "missing_overrides": missing, "total": len(A)}


def main() -> int:
    articles = store.load(config.ARTICLES_FILE)
    overrides = store.load_overrides(config.OVERRIDES_FILE)
    r = run(articles, overrides)
    names = {c["id"]: c["name"] for c in config.COMPANIES}
    out = [f"## Data audit - {r['total']} articles\n"]
    out.append(f"- Exact duplicates (same URL): **{len(r['exact'])}**")
    out.append(f"- Same outlet, near-identical headline: **{len(r['same_outlet'])}**")
    out.append(f"- Same story told by different outlets (counted separately, by design): {len(r['cross_outlet'])}")
    out.append(f"- Company named only in article body (counted in 'All', not in 'Headline only'): {len(r['mentions'])}")
    out.append(f"- Human exclusions in data/overrides.json: {len(r['overrides'])}"
               + (f" ({len(r['missing_overrides'])} point at unknown ids)" if r["missing_overrides"] else ""))
    for _, a, b in r["same_outlet"]:
        out.append(f"  - DUPLICATE? `{a['id']}` {a['title']}  <->  `{b['id']}` {b['title']}")
    if r["mentions"]:
        out.append("\n<details><summary>Body-mention articles to spot-check</summary>\n")
        out += [f"- `{a['id']}` [{names.get(c, c)}] {a['title']} ({a['publisher']}, {a['published'][:10]})" for a, c in r["mentions"]]
        out.append("\n</details>")
    print("\n".join(out))
    return 1 if (r["exact"] or r["same_outlet"]) else 0


if __name__ == "__main__":
    sys.exit(main())
