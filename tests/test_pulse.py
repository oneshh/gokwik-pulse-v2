"""Offline tests: parsing, de-duplication, health rules and the dashboard data. No network."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pulse import config, health, report, sources, store

FIX = Path(__file__).parent / "fixtures"
IDS = [c["id"] for c in config.COMPANIES]
SRCS = list(sources.SOURCES)


def item(title, company="gokwik", source="google", url="https://news.google.com/x", pub="2026-11-10T05:00:00+00:00", publisher="Inc42"):
    return sources.RawItem(source=source, company=company, title=title, url=url, publisher=publisher, published=pub)


# ------------------------------------------------------------------ parsing

def test_parse_google_strips_publisher_suffix():
    items = sources.parse_google((FIX / "google.xml").read_bytes(), "gokwik")
    assert len(items) == 2
    assert items[0].title == "GoKwik raises $13 million in Series B"
    assert items[0].publisher == "Inc42"
    assert items[0].published == "2026-11-12T06:30:00+00:00"


def test_parse_bing_unwraps_tracker_link():
    items = sources.parse_bing((FIX / "bing.xml").read_bytes(), "shopflo")
    assert items[0].url == "https://www.cnbctv18.com/market/pine-labs-acquires-shopflo.htm"
    assert items[0].publisher == "cnbctv18"


def test_blocked_publishers_dropped():
    assert sources.is_blocked("Crunchbase")
    assert sources.is_blocked("Instagram")
    assert not sources.is_blocked("Economic Times")


# ------------------------------------------------------------------ dedup

def test_same_article_on_two_days_counted_once():
    db = {}
    new1 = store.merge(db, [item("GoKwik raises $13 million")], "2026-11-12")
    new2 = store.merge(db, [item("GoKwik raises $13 million")], "2026-11-13")
    assert len(db) == 1
    assert new1 == {"gokwik": [store.article_id("GoKwik raises $13 million")]}
    assert new2 == {}
    rec = next(iter(db.values()))
    assert rec["first_seen"] == "2026-11-12" and rec["last_seen"] == "2026-11-13"


def test_same_article_from_two_sources_merges_and_prefers_direct_link():
    db = {}
    store.merge(db, [
        item("Pine Labs acquires Shopflo", company="shopflo"),
        item("Pine Labs Acquires Shopflo!", company="shopflo", source="bing",
             url="https://cnbctv18.com/a", publisher="cnbctv18"),
    ], "2026-11-13")
    assert len(db) == 1
    rec = next(iter(db.values()))
    assert rec["url"] == "https://cnbctv18.com/a"
    assert sorted(rec["sources"]) == ["bing", "google"]
    assert set(rec["outlets"]) == {"Inc42", "cnbctv18"}


@pytest.mark.parametrize("a,b", [
    ("Razorpay's Magic Checkout grows", "Razorpays Magic Checkout grows"),
    ("Simpl app shut | The Lallantop", "Simpl app shut | Lallantop"),
    ("GoKwik — new CEO", "gokwik new ceo"),
])
def test_title_normalisation_variants_match(a, b):
    assert store.article_id(a) == store.article_id(b)


def test_hindi_titles_do_not_collapse():
    assert store.article_id("'Simpl' ऐप अब नहीं चलेगी") != store.article_id("'Simpl' ऐप फिर चलेगी")


def test_article_mentioning_two_companies_counts_for_each():
    db = {}
    new = store.merge(db, [item("GoKwik vs Shopflo", "gokwik"), item("GoKwik vs Shopflo", "shopflo")], "2026-11-13")
    assert set(new) == {"gokwik", "shopflo"}
    assert len(db) == 1


def test_store_roundtrip(tmp_path):
    db = {}
    store.merge(db, [item("A story about GoKwik")], "2026-11-13")
    p = tmp_path / "a.json"
    store.save(p, db)
    assert store.load(p) == db


# ------------------------------------------------------------------ health / alert rules

def counts(**over):
    c = {cid: {s: 5 for s in SRCS} for cid in IDS}
    for cid, n in over.items():
        c[cid] = {s: 0 for s in SRCS}
        c[cid][SRCS[0]] = n
    return c


def test_healthy_run_is_silent():
    assert health.evaluate(counts(), [], IDS, SRCS)["status"] == "ok"


def test_zero_new_articles_is_still_healthy():
    # health only looks at what was fetched, not what was new
    assert health.evaluate(counts(), [], IDS, SRCS)["problems"] == []


def test_empty_run_fails():
    zero = {cid: {s: 0 for s in SRCS} for cid in IDS}
    v = health.evaluate(zero, [], IDS, SRCS)
    assert v["status"] == "fail" and "returned nothing" in v["problems"][0]


def test_one_company_empty_fails():
    v = health.evaluate(counts(simpl=0), [], IDS, SRCS)
    assert v["status"] == "fail" and "simpl" in v["problems"][0]


def test_all_sources_down_fails():
    errs = [f"{s}/{c}: timeout" for s in SRCS for c in IDS]
    zero = {cid: {s: 0 for s in SRCS} for cid in IDS}
    v = health.evaluate(zero, errs, IDS, SRCS)
    assert v["status"] == "fail" and "Every source" in v["problems"][0]


def test_one_source_down_is_only_a_warning():
    errs = [f"bing/{c}: HTTP 429" for c in IDS]
    v = health.evaluate(counts(), errs, IDS, SRCS)
    assert v["status"] == "warn" and v["problems"] == []


# ------------------------------------------------------------------ report

def test_report_weekly_shares_and_latest():
    db = {}
    store.merge(db, [
        item("GoKwik one", pub="2026-11-10T05:00:00+00:00"),
        item("GoKwik two", pub="2026-11-11T05:00:00+00:00"),
        item("Shopflo one", company="shopflo", pub="2026-11-11T06:00:00+00:00"),
        item("Old Simpl story", company="simpl", pub="2019-01-01T00:00:00+00:00"),
    ], "2026-11-13")
    now = datetime(2026, 11, 13, 6, 0, tzinfo=timezone.utc)
    d = report.build(db, [{"run_at": now.isoformat(), "status": "ok"}], now)
    cur = d["weeks"][-1]
    assert cur["week_start"] == "2026-11-09" and cur["is_current"]
    assert cur["counts"]["gokwik"] == 2 and cur["counts"]["shopflo"] == 1
    assert cur["shares"]["gokwik"] == pytest.approx(66.7)
    assert d["totals"]["by_company"]["simpl"] == 1      # all-time keeps old stories
    assert d["window"]["counts"]["simpl"] == 0          # 12-week window does not
    assert d["latest"][0]["title"] == "Shopflo one"
    assert len(d["weeks"]) == config.WEEKS_ON_DASHBOARD
    json.dumps(d)  # serialisable


def test_ist_week_boundary():
    # Sunday 20:00 UTC = Monday 01:30 IST -> belongs to the new week
    assert report.week_start(report.ist_date("2026-11-08T20:00:00+00:00")).isoformat() == "2026-11-09"
