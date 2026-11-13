"""Daily entry point:  python -m pulse.run [--simulate failure|empty] [--offline]

Exit codes: 0 healthy (or warning), 1 crashed, 2 health check failed. Any non-zero exit makes
the GitHub Actions job fail, which opens the alert issue.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import config, health, report, sources, store

MAX_RUNS_KEPT = 400


def _gh_output(**kv: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a") as fh:
        for k, v in kv.items():
            fh.write(f"{k}<<__EOF__\n{v}\n__EOF__\n")


def _summary(md: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a") as fh:
            fh.write(md + "\n")
    print(md)


def fetch_all(simulate: str | None) -> tuple[list[sources.RawItem], dict, list[str]]:
    if simulate == "failure":
        raise RuntimeError("Simulated failure (manual alert test via workflow_dispatch).")
    company_ids = [c["id"] for c in config.COMPANIES]
    raw_counts = {cid: {s: 0 for s in sources.SOURCES} for cid in company_ids}
    if simulate == "empty":
        return [], raw_counts, []

    jobs = [(s, c) for c in config.COMPANIES for s in sources.SOURCES]
    items: list[sources.RawItem] = []
    errors: list[str] = []

    def one(job):
        src, comp = job
        try:
            return src, comp["id"], sources.fetch(src, comp), None
        except Exception as exc:
            return src, comp["id"], [], f"{src}/{comp['id']}: {exc}"

    with ThreadPoolExecutor(max_workers=4) as pool:
        for src, cid, got, err in pool.map(one, jobs):
            raw_counts[cid][src] = len(got)
            items.extend(got)
            if err:
                errors.append(err)
    return items, raw_counts, errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--simulate", choices=["none", "failure", "empty"], default="none")
    ap.add_argument("--rebuild-only", action="store_true", help="regenerate site/data.json without fetching")
    args = ap.parse_args(argv)
    simulate = None if args.simulate == "none" else args.simulate

    now = datetime.now(timezone.utc)
    today = now.astimezone(report.IST).date().isoformat()
    articles = store.load(config.ARTICLES_FILE)
    runs = json.loads(config.RUNS_FILE.read_text()) if config.RUNS_FILE.exists() else []

    if args.rebuild_only:
        config.SITE_DATA_FILE.write_text(json.dumps(report.build(articles, runs, now), indent=1))
        return 0

    items, raw_counts, errors = fetch_all(simulate)
    verdict = health.evaluate(raw_counts, errors, [c["id"] for c in config.COMPANIES], list(sources.SOURCES))

    new_by_company = store.merge(articles, items, today)
    run = {
        "run_at": now.isoformat(timespec="seconds"),
        "status": verdict["status"],
        "fetched": verdict["raw_total"],
        "new": len({a for ids in new_by_company.values() for a in ids}),
        "per_company": {
            cid: {"fetched": sum(raw_counts[cid].values()), "new": len(new_by_company.get(cid, []))}
            for cid in raw_counts
        },
        "problems": verdict["problems"],
        "warnings": verdict["warnings"],
    }

    names = {c["id"]: c["name"] for c in config.COMPANIES}
    srcs = list(sources.SOURCES)
    rows = "\n".join(
        f"| {names[cid]} | " + " | ".join(str(raw_counts[cid].get(s, 0)) for s in srcs)
        + f" | {run['per_company'][cid]['new']} |"
        for cid in raw_counts
    )
    head = " | ".join(sources.SOURCE_LABELS[s] for s in srcs)
    _summary(
        f"## GoKwik Pulse run - {verdict['status'].upper()}\n\n"
        f"| Company | {head} | New articles |\n|---|" + "---:|" * (len(srcs) + 1) + f"\n{rows}\n\n"
        f"**Fetched:** {run['fetched']}  ·  **New unique articles:** {run['new']}  ·  "
        f"**Total in history:** {len(articles)}\n"
        + "".join(f"\n- :x: {p}" for p in verdict["problems"])
        + "".join(f"\n- :warning: {w}" for w in verdict["warnings"])
    )

    if simulate:
        print("Simulation run: nothing written to disk.")
    else:
        # Save what we got even on a failed health check, so partial data is never lost.
        store.save(config.ARTICLES_FILE, articles)
        runs = (runs + [run])[-MAX_RUNS_KEPT:]
        config.RUNS_FILE.write_text(json.dumps(runs, indent=1) + "\n")
        config.SITE_DATA_FILE.write_text(json.dumps(report.build(articles, runs, now), indent=1))

    _gh_output(status=verdict["status"], reason="\n".join(verdict["problems"]) or "none")
    return 2 if verdict["status"] == "fail" else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # crash -> exit 1 and leave a reason for the alert issue
        _gh_output(status="fail", reason=f"Run crashed: {type(exc).__name__}: {exc}")
        print(f"CRASH: {exc}", file=sys.stderr)
        raise
