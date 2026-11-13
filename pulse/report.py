"""Turn the article store + run log into site/data.json, the only file the dashboard reads.

Every count is produced twice:
  all       - every article that covers the company (headline or body mention)
  headline  - only articles whose headline names the company (strict, highest confidence)
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from . import config

IST = timezone(timedelta(hours=config.IST_OFFSET_HOURS))
MODES = ("all", "headline")


def ist_date(iso: str) -> date:
    return datetime.fromisoformat(iso).astimezone(IST).date()


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())  # Monday


def _counts_for(a: dict, mode: str, ids: list[str]) -> list[str]:
    """Companies this article counts for, under the given mode."""
    rel = a.get("relevance", {})
    return [c for c in a["companies"] if c in ids and (mode == "all" or rel.get(c) == "headline")]


def shares(counts: dict[str, int]) -> dict[str, float]:
    tot = sum(counts.values())
    return {k: (round(v * 100 / tot, 1) if tot else 0.0) for k, v in counts.items()}


def _block(counts: dict[str, int]) -> dict:
    return {"counts": counts, "shares": shares(counts), "total": sum(counts.values())}


def build(store: dict[str, dict], runs: list[dict], now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(IST).date()
    ids = [c["id"] for c in config.COMPANIES]
    articles = list(store.values())

    this_week = week_start(today)
    weeks = [this_week - timedelta(weeks=i) for i in range(config.WEEKS_ON_DASHBOARD - 1, -1, -1)]
    days = [today - timedelta(days=i) for i in range(29, -1, -1)]

    def zero():
        return {cid: 0 for cid in ids}

    wk = {m: {w: zero() for w in weeks} for m in MODES}
    dy = {m: {d: zero() for d in days} for m in MODES}
    all_time = {m: zero() for m in MODES}
    added_today = 0
    for a in articles:
        pd = ist_date(a["published"])
        ws = week_start(pd)
        for m in MODES:
            for cid in _counts_for(a, m, ids):
                all_time[m][cid] += 1
                if ws in wk[m]:
                    wk[m][ws][cid] += 1
                if pd in dy[m]:
                    dy[m][pd][cid] += 1
        if a["first_seen"] == today.isoformat():
            added_today += 1

    week_rows = []
    for w in weeks:
        row = {"week_start": w.isoformat(), "label": w.strftime("%d %b"), "is_current": w == this_week}
        row.update(_block(wk["all"][w]))
        row["headline"] = _block(wk["headline"][w])
        week_rows.append(row)

    def window(m):
        c = {cid: sum(wk[m][w][cid] for w in weeks) for cid in ids}
        return {"weeks": config.WEEKS_ON_DASHBOARD, "from": weeks[0].isoformat(), **_block(c)}

    newest = sorted(articles, key=lambda a: a["published"], reverse=True)
    latest = newest[: config.LATEST_COUNT]
    latest_headline = [a for a in newest if _counts_for(a, "headline", ids)][: config.LATEST_COUNT]

    def card(a):
        return {**{k: a[k] for k in ("id", "title", "url", "publisher", "published", "first_seen", "companies", "outlets", "sources")},
                "relevance": {c: a.get("relevance", {}).get(c, "mention") for c in a["companies"]}}
    pairs = sum(len(a["companies"]) for a in articles)
    mention_only = sum(1 for a in articles for c in a["companies"] if a.get("relevance", {}).get(c) != "headline")

    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "today": today.isoformat(),
        "tracking_since": runs[0]["run_at"][:10] if runs else today.isoformat(),
        "companies": [
            {k: c[k] for k in ("id", "name", "color", "color_dark", "query")} for c in config.COMPANIES
        ],
        "totals": {
            "articles": len(articles),
            "by_company": all_time["all"],
            "by_company_headline": all_time["headline"],
            "shares": shares(all_time["all"]),
            "added_today": added_today,
            "last_30_days": sum(sum(v.values()) for v in dy["all"].values()),
        },
        "window": window("all"),
        "window_headline": window("headline"),
        "weeks": week_rows,
        "daily": [{"date": d.isoformat(), "counts": dy["all"][d], "total": sum(dy["all"][d].values())} for d in days],
        "latest": [card(a) for a in latest],
        "latest_headline": [card(a) for a in latest_headline],
        "review": {
            "company_articles": pairs,
            "headline": pairs - mention_only,
            "mention_only": mention_only,
            "excluded": 0,  # filled in by run.py from data/overrides.json
        },
        "health": {
            "last_run": runs[-1] if runs else None,
            "recent_runs": runs[-30:],
        },
    }
