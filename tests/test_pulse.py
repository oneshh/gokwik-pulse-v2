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


# ------------------------------------------------------------------ RCA edge cases

def test_outlet_edits_headline_is_same_article():
    db = {}
    store.merge(db, [item("GoKwik raises $13 million in Series B led by RTP Global", publisher="Inc42")], "2026-11-12")
    new = store.merge(db, [item("GoKwik raises $13 million in Series B, led by RTP Global Ventures", publisher="Inc42")], "2026-11-13")
    assert len(db) == 1 and new == {}


def test_publisher_name_variants_match_for_fuzzy_dedup():
    assert store.publisher_key("Moneycontrol.com") == store.publisher_key("moneycontrol") == store.publisher_key("https://www.moneycontrol.com/")
    db = {}
    store.merge(db, [item("Pine Labs acquires D2C checkout startup Shopflo in Rs 88 crore deal", "shopflo", publisher="Moneycontrol.com")], "2026-11-12")
    store.merge(db, [item("Pine Labs acquires D2C checkout startup Shopflo in ₹88 crore deal", "shopflo", source="bing",
                          url="https://moneycontrol.com/x", publisher="moneycontrol")], "2026-11-13")
    assert len(db) == 1


def test_different_outlets_same_story_are_separate_articles():
    db = {}
    store.merge(db, [item("GoKwik secures $13 M in round led by RTP Global", publisher="YourStory.com"),
                     item("GoKwik raises $13 million round led by RTP Global", publisher="Moneycontrol.com")], "2026-11-13")
    assert len(db) == 2


def test_similar_headline_months_apart_is_not_merged():
    db = {}
    store.merge(db, [item("GoKwik appoints new CFO", pub="2025-01-10T00:00:00+00:00")], "2025-01-10")
    store.merge(db, [item("GoKwik appoints new CTO", pub="2026-06-10T00:00:00+00:00")], "2026-06-10")
    assert len(db) == 2


def test_same_direct_url_with_different_title_is_one_article():
    db = {}
    store.merge(db, [item("Shopflo bought", "shopflo", source="bing", url="https://et.com/a", publisher="ET")], "2026-11-13")
    store.merge(db, [item("Pine Labs buys checkout startup Shopflo", "shopflo", source="bing", url="https://et.com/a", publisher="ET")], "2026-11-13")
    assert len(db) == 1


def test_relevance_headline_vs_body_mention():
    db = {}
    store.merge(db, [item("Diwali D2C sales jump 81%"), item("GoKwik launches AI checkout")], "2026-11-13")
    rel = {r["title"]: r["relevance"]["gokwik"] for r in db.values()}
    assert rel == {"Diwali D2C sales jump 81%": "mention", "GoKwik launches AI checkout": "headline"}


def test_relevance_upgrades_when_another_feed_names_company_in_headline():
    db = {}
    store.merge(db, [item("Checkout startup bought by Pine Labs", "shopflo", url="https://x.com/a", source="bing", publisher="X")], "2026-11-13")
    store.merge(db, [item("Shopflo bought by Pine Labs", "shopflo", url="https://x.com/a", source="bing", publisher="X")], "2026-11-13")
    assert next(iter(db.values()))["relevance"]["shopflo"] == "headline"


def test_overrides_exclude_per_company_without_deleting_history(tmp_path):
    db = {}
    store.merge(db, [item("GoKwik vs Shopflo", "gokwik"), item("GoKwik vs Shopflo", "shopflo")], "2026-11-13")
    aid = next(iter(db))
    p = tmp_path / "o.json"
    p.write_text(json.dumps({"exclude": [{"id": aid, "company": "shopflo", "reason": "test"}]}))
    view = store.apply_overrides(db, store.load_overrides(p))
    assert view[aid]["companies"] == ["gokwik"]
    assert db[aid]["companies"] == ["gokwik", "shopflo"]   # history untouched


def test_malformed_items_are_not_counted():
    assert not sources.is_valid(item("", url="https://a"))
    assert not sources.is_valid(item("GoKwik", url="javascript:alert(1)"))
    assert sources.is_valid(item("GoKwik", url="https://a.com"))


def test_sudden_drop_is_a_warning_not_an_alert():
    past = [{"status": "ok", "per_company": {c: {"fetched": 50} for c in IDS}} for _ in range(5)]
    low = counts(gokwik=5)
    v = health.evaluate(low, [], IDS, SRCS, recent_runs=past)
    assert v["status"] == "warn" and "far below" in v["warnings"][0]


def test_report_headline_only_mode():
    db = {}
    store.merge(db, [item("Diwali D2C sales jump", pub="2026-11-10T05:00:00+00:00"),
                     item("GoKwik launches AI", pub="2026-11-11T05:00:00+00:00")], "2026-11-13")
    now = datetime(2026, 11, 13, 6, 0, tzinfo=timezone.utc)
    d = report.build(db, [], now)
    assert d["weeks"][-1]["counts"]["gokwik"] == 2
    assert d["weeks"][-1]["headline"]["counts"]["gokwik"] == 1
    assert d["review"]["mention_only"] == 1


def test_audit_flags_same_outlet_duplicates_only():
    from pulse import audit
    db = {
        "a": {"id": "a", "title": "GoKwik raises $13 million in Series B", "url": "https://x/1", "publisher": "Inc42",
              "outlets": ["Inc42"], "published": "2026-11-10T00:00:00+00:00", "companies": ["gokwik"], "relevance": {"gokwik": "headline"}},
        "b": {"id": "b", "title": "GoKwik raises $13 million in Series B round", "url": "https://x/2", "publisher": "Inc42",
              "outlets": ["Inc42"], "published": "2026-11-11T00:00:00+00:00", "companies": ["gokwik"], "relevance": {"gokwik": "headline"}},
    }
    assert len(audit.run(db, {})["same_outlet"]) == 1
    db["b"]["publisher"] = db["b"]["outlets"][0] = "Mint"
    assert audit.run(db, {})["same_outlet"] == []


def test_committed_history_has_no_duplicates():
    from pulse import audit
    r = audit.run(store.load(config.ARTICLES_FILE), store.load_overrides(config.OVERRIDES_FILE))
    assert r["exact"] == [] and r["same_outlet"] == []
    assert r["missing_overrides"] == []


def test_bing_url_has_no_sortbydate():
    # regression: sortbydate makes Bing RSS ignore the query
    assert "sortbydate" not in sources.bing_url('"Shopflo"')


def test_strict_source_drops_results_that_do_not_name_the_company(monkeypatch):
    xml = (FIX / "bing.xml").read_bytes().replace(b"Shopflo", b"Somebody")
    monkeypatch.setattr(sources, "_http_get", lambda url: xml)
    comp = next(c for c in config.COMPANIES if c["id"] == "shopflo")
    assert sources.fetch("bing", comp) == []


def test_headline_mode_still_lists_twenty_latest():
    db = {}
    store.merge(db, [item(f"GoKwik story {i}", pub=f"2026-10-{i+1:02d}T00:00:00+00:00") for i in range(25)]
                + [item(f"Body mention {i}", pub=f"2026-11-{i+1:02d}T00:00:00+00:00") for i in range(10)], "2026-11-13")
    d = report.build(db, [], datetime(2026, 11, 13, tzinfo=timezone.utc))
    assert len(d["latest_headline"]) == config.LATEST_COUNT
    assert all(a["relevance"]["gokwik"] == "headline" for a in d["latest_headline"])


def test_headlines_with_different_numbers_are_not_merged():
    db = {}
    store.merge(db, [item("GoKwik posts Q1 results, revenue up"), item("GoKwik posts Q2 results, revenue up"),
                     item("Simpl lays off 100 employees", "simpl"), item("Simpl lays off 150 employees", "simpl")], "2026-11-13")
    assert len(db) == 4
