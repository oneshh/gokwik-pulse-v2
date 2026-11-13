"""Guards for the Part 2 analysis: each data problem stays fixed if the script is edited."""

import json
import sys
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import cod_returns  # noqa: E402

OUT = cod_returns.OUT


@pytest.fixture(scope="module")
def result():
    return cod_returns.main()


def test_dedup_and_test_merchants_removed(result):
    assert result["rows_raw"] == 97378
    assert result["rows_after_dedup"] == 95939           # 1,439 exact copies dropped
    assert result["real_stores"] == 24                   # 26 ids minus M_TEST_01 / M_TEST_02
    stores = pd.read_csv(OUT / "store_cod_return_rate.csv")
    assert not stores.merchant_id.str.startswith("M_TEST").any()


def test_thirteen_ist_weeks_monday_start(result):
    w = pd.read_csv(OUT / "weekly_cod_return_rate.csv", parse_dates=["week_start_mon"])
    assert len(w) == 13
    assert (w.week_start_mon.dt.day_of_week == 0).all()
    assert w.week_start_mon.min() == pd.Timestamp("2026-07-27")   # no fake 20-Jul week from UTC dates
    assert w.week_start_mon.max() == pd.Timestamp("2026-10-19")


def test_partial_week_flagged():
    w = pd.read_csv(OUT / "weekly_cod_return_rate.csv")
    flagged = w[w.days_with_data < 7]
    assert flagged.week_start_mon.tolist() == ["2026-09-14"]


def test_rate_definition_excludes_non_final():
    w = pd.read_csv(OUT / "weekly_cod_return_rate.csv")
    assert (w.return_rate_pct.round(2) == (w.returned / w.final_cod * 100).round(2)).all()


def test_top3_and_threshold(result):
    assert [t["store"] for t in result["top3"]] == ["M122", "M108", "M110"]
    assert all(t["final_cod"] >= 200 for t in result["top3"])
    stores = pd.read_csv(OUT / "store_cod_return_rate.csv").set_index("merchant_id")
    assert not stores.loc["M117", "eligible"]            # highest real rate, but < 200 orders


def test_naive_pipeline_would_be_wrong(result):
    assert result["sensitivity"]["naive_top3_raw_file"][:2] == ["M_TEST_01", "M_TEST_02"]


def test_every_issue_has_an_action():
    issues = pd.read_csv(OUT / "data_issues.csv")
    assert len(issues) >= 11
    assert issues.what_we_did.str.len().min() > 5
    assert not issues.effect_on_answer.str.contains("{EFFECT").any()   # placeholders all filled
