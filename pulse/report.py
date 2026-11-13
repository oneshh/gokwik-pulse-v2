"""Turn the article store + run log into site/data.json, the only file the dashboard reads."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from . import config

IST = timezone(timedelta(hours=config.IST_OFFSET_HOURS))


def ist_date(iso: str) -> date:
    return datetime.fromisoformat(iso).astimezone(IST).date()


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())  # Monday


def build(store: dict[str, dict], runs: list[dict], now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(IST).date()
    ids = [c["id"] for c in config.COMPANIES]
    articles = list(store.values())

    # ---- weekly counts by publish week (IST), last N weeks incl. the current one
    this_week = week_start(today)
    weeks = [this_week - timedelta(weeks=i) for i in range(config.WEEKS_ON_DASHBOARD - 1, -1, -1)]
    buckets = {w: {cid: 0 for cid in ids} for w in weeks}
    all_time = {cid: 0 for cid in ids}
    for a in articles:
        wk = week_start(ist_date(a["published"]))
        for cid in a["companies"]:
            if cid not in all_time:
                continue
            all_time[cid] += 1
            if wk in buckets:
                buckets[wk][cid] += 1

    def shares(counts: dict[str, int]) -> dict[str, float]:
        tot = sum(counts.values())
        return {k: (round(v * 100 / tot, 1) if tot else 0.0) for k, v in counts.items()}

    week_rows = []
    for w in weeks:
        c = buckets[w]
        week_rows.append({
            "week_start": w.isoformat(),
            "label": w.strftime("%d %b"),
            "counts": c,
            "shares": shares(c),
            "total": sum(c.values()),
            "is_current": w == this_week,
        })

    window = {cid: sum(r["counts"][cid] for r in week_rows) for cid in ids}

    # ---- daily article counts by publish date (IST), last 30 days, per company
    daily = {(today - timedelta(days=i)).isoformat(): {cid: 0 for cid in ids} for i in range(29, -1, -1)}
    added_today = 0
    for a in articles:
        d = ist_date(a["published"]).isoformat()
        if d in daily:
            for cid in a["companies"]:
                if cid in daily[d]:
                    daily[d][cid] += 1
        if a["first_seen"] == today.isoformat():
            added_today += 1

    latest = sorted(articles, key=lambda a: a["published"], reverse=True)[: config.LATEST_COUNT]

    last_run = runs[-1] if runs else None
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "today": today.isoformat(),
        "tracking_since": runs[0]["run_at"][:10] if runs else today.isoformat(),
        "companies": [
            {k: c[k] for k in ("id", "name", "color", "color_dark", "query")} for c in config.COMPANIES
        ],
        "totals": {
            "articles": len(articles),
            "by_company": all_time,
            "shares": shares(all_time),
            "added_today": added_today,
            "last_30_days": sum(sum(v.values()) for v in daily.values()),
        },
        "window": {
            "weeks": config.WEEKS_ON_DASHBOARD,
            "from": weeks[0].isoformat(),
            "counts": window,
            "shares": shares(window),
            "total": sum(window.values()),
        },
        "weeks": week_rows,
        "daily": [{"date": d, "counts": c, "total": sum(c.values())} for d, c in daily.items()],
        "latest": [
            {k: a[k] for k in ("title", "url", "publisher", "published", "first_seen", "companies", "outlets", "sources")}
            for a in latest
        ],
        "health": {
            "last_run": last_run,
            "recent_runs": runs[-30:],
        },
    }
