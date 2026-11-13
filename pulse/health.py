"""Decide whether a run is healthy. The alert fires ONLY when this says "fail".

A run fails when:
  * the code crashed (handled by the workflow: any non-zero exit), or
  * every source request errored, or
  * the run "quietly returned nothing": zero articles in total, or zero articles for any one
    company across all sources. Both sources return a rolling window of past articles, so a
    healthy run always sees *something* for every company even on a slow news day. Zero means
    a query, parser or source broke, not that the news stopped.

Zero NEW articles is normal (nothing published since yesterday) and is NOT an alert.
One source failing while the other works is a warning shown on the dashboard, not an alert.
"""

from __future__ import annotations


def evaluate(raw_counts: dict[str, dict[str, int]], errors: list[str], company_ids: list[str],
             sources: list[str]) -> dict:
    """raw_counts[company][source] = items fetched. errors = ["source/company: message", ...]."""
    total = sum(sum(v.values()) for v in raw_counts.values())
    problems: list[str] = []
    warnings: list[str] = []

    attempts = len(company_ids) * len(sources)
    if attempts and len(errors) >= attempts:
        problems.append("Every source request failed - no news could be fetched.")
    elif total == 0:
        problems.append("The run returned nothing: 0 articles across all companies and sources.")
    else:
        for cid in company_ids:
            if sum(raw_counts.get(cid, {}).values()) == 0:
                problems.append(f"The run returned nothing for '{cid}' (0 articles from every source).")

    for src in sources:
        failed = [e for e in errors if e.startswith(src + "/")]
        if failed and len(failed) == len(company_ids):
            warnings.append(f"Source '{src}' failed for every company; running on the other source.")
        elif failed and not problems:
            warnings.extend(failed)

    status = "fail" if problems else ("warn" if warnings else "ok")
    return {"status": status, "problems": problems, "warnings": warnings, "raw_total": total}
