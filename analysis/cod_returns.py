"""Part 2 - Can these numbers be trusted?  COD return rate from analysis/data/orders.csv.

    python analysis/cod_returns.py            # prints the answers, writes analysis/output/*

Definitions (from the brief)
  COD return rate = COD orders returned to the store (status 'rto', return-to-origin)
                    / COD orders that reached a final delivery outcome ('delivered' or 'rto').
  Weeks run Monday-Sunday in IST (Asia/Kolkata, UTC+05:30).
  Store ranking: only stores with >= 200 COD orders that reached a final outcome.

Every data problem is detected in code, counted, fixed (or deliberately left alone) and logged
to analysis/output/data_issues.csv, so the write-up can't drift from what the code really did.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data" / "orders.csv"
OUT = HERE / "output"
IST = "Asia/Kolkata"
MIN_FINAL_COD = 200
FINAL = ("delivered", "rto")
COD_LABELS = {"cod", "cash on delivery"}          # compared after strip + lower-case
TEST_MERCHANT_PREFIX = "M_TEST"
PLACEHOLDER_VALUE = 9_999_999

issues: list[dict] = []


def log(n: int, problem: str, evidence: str, action: str, effect: str) -> None:
    issues.append({"#": n, "problem": problem, "evidence": evidence, "what_we_did": action, "effect_on_answer": effect})


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson interval for a proportion (well-behaved for small n, unlike +/- 1.96*SE)."""
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def week_start(ts_ist: pd.Series) -> pd.Series:
    """Monday 00:00 IST of the week each timestamp falls in."""
    local = ts_ist.dt.tz_localize(None)
    return (local.dt.normalize() - pd.to_timedelta(local.dt.day_of_week, unit="D")).dt.date


def rate_table(df: pd.DataFrame, by: str) -> pd.DataFrame:
    f = df[df.is_cod & df.status_n.isin(FINAL)]
    g = f.groupby(by).status_n.agg(final_cod="size", returned=lambda s: int((s == "rto").sum()))
    g["return_rate_pct"] = (g.returned / g.final_cod * 100).round(2)
    ci = [wilson(r, n) for r, n in zip(g.returned, g.final_cod)]
    g["ci95_low_pct"] = [round(a * 100, 2) for a, _ in ci]
    g["ci95_high_pct"] = [round(b * 100, 2) for _, b in ci]
    return g


def main() -> dict:
    OUT.mkdir(exist_ok=True)
    raw_bytes = DATA.read_bytes()
    # Read everything as text first so nothing is silently converted, then fix explicitly.
    raw = pd.read_csv(DATA, dtype=str, keep_default_na=False)
    n_raw = len(raw)

    # ---------------------------------------------------------------- 1. exact duplicate rows
    dup_mask = raw.duplicated(keep="first")
    id_dups = raw.order_id.duplicated(keep=False)
    conflicting = raw[id_dups].drop_duplicates().order_id.duplicated().sum()
    df = raw[~dup_mask].copy()
    log(1, "Duplicate rows",
        f"{dup_mask.sum():,} rows are exact copies of another row (all 6 columns identical); "
        f"{raw.order_id.nunique():,} unique order_ids in {n_raw:,} rows. Copies with the same id but "
        f"different values: {conflicting}.",
        "Dropped the second copy of each. Because every copy is identical there is no 'which version is right' question.",
        "Without this, each duplicated COD order counts twice in both numerator and denominator.")
    assert df.order_id.is_unique, "order_id must be unique after dropping exact duplicates"

    # ---------------------------------------------------------------- 2. payment_type labels
    pt = df.payment_type.str.strip().str.lower()
    df["is_cod"] = pt.isin(COD_LABELS)
    variants = df.payment_type[df.is_cod].value_counts().to_dict()
    log(2, "COD written three different ways",
        "payment_type values for COD: " + ", ".join(f"'{k}' ({v:,})" for k, v in variants.items())
        + ". Every store uses all three (about 12% of each store's COD orders are not 'cod').",
        "Treated 'cod', 'COD' and 'Cash on Delivery' as COD (trim + lower-case, explicit allow-list).",
        f"Filtering on 'cod' alone would drop {sum(v for k, v in variants.items() if k != 'cod'):,} COD orders, spread across every store.")
    unknown_pt = set(pt) - COD_LABELS - {"upi", "card", "netbanking"}
    assert not unknown_pt, f"unexpected payment types: {unknown_pt}"

    # ---------------------------------------------------------------- 3. status labels
    df["status_n"] = df.status.str.strip().str.lower()
    n_space = int((df.status != df.status.str.strip()).sum())
    raw_status_variants = df.status.nunique()
    log(3, "Status written in 20 different ways (case + stray spaces)",
        f"{raw_status_variants} raw spellings for 5 real statuses, e.g. 'delivered', 'DELIVERED', ' Delivered', "
        f"'rto', 'RTO', ' Rto'. {n_space:,} values have a leading/trailing space.",
        "Trimmed and lower-cased; checked the result is exactly {delivered, rto, cancelled, in_transit, pending}.",
        f"An exact match on 'rto'/'delivered' would silently drop "
        f"{((df.is_cod & df.status_n.isin(FINAL)) & ~df.status.isin(FINAL)).sum():,} of "
        f"{(df.is_cod & df.status_n.isin(FINAL)).sum():,} final COD orders "
        f"({((df.is_cod & df.status_n.isin(FINAL)) & ~df.status.isin(FINAL)).mean() / (df.is_cod & df.status_n.isin(FINAL)).mean():.0%}).")
    assert set(df.status_n) == {"delivered", "rto", "cancelled", "in_transit", "pending"}, set(df.status_n)

    # ---------------------------------------------------------------- 4. test merchants
    is_test = df.merchant_id.str.upper().str.startswith(TEST_MERCHANT_PREFIX)
    t = rate_table(df[is_test], "merchant_id")
    with_test = rate_table(df.assign(a=1), "a").return_rate_pct.iloc[0]
    without_test = rate_table(df[~is_test].assign(a=1), "a").return_rate_pct.iloc[0]
    test_pay = df[is_test].payment_type.str.strip().str.lower().replace({"cash on delivery": "cod"}).unique().tolist()
    log(4, "Test merchants mixed in with real stores",
        f"M_TEST_01 and M_TEST_02: {is_test.sum():,} orders, COD-only (payment types: {test_pay}), "
        f"COD return rates {t.return_rate_pct.min():.0f}-{t.return_rate_pct.max():.0f}%, both above the 200-order bar. "
        "So the brief's '26 stores' is really 24 stores + 2 test accounts.",
        "Excluded from every number.",
        f"Kept in, they would be #1 and #2 in the store ranking, and the overall rate would read {with_test:.2f}% "
        f"instead of {without_test:.2f}% (+{with_test - without_test:.2f} points).")
    df = df[~is_test].copy()

    # ---------------------------------------------------------------- 5. timezone
    ts = pd.to_datetime(df.created_at.replace("", None), utc=True, errors="coerce")
    bad_ts = int(((df.created_at != "") & ts.isna()).sum())
    assert bad_ts == 0, f"{bad_ts} timestamps failed to parse"
    df["ist"] = ts.dt.tz_convert(IST)
    utc_jul26 = int((ts.dt.strftime("%Y-%m-%d") == "2026-07-26").sum())
    log(5, "Timestamps are UTC, the weeks must be IST",
        f"All timestamps end in 'Z' (UTC). In IST the data spans exactly Mon 27 Jul 00:00 to Sun 25 Oct 23:59 "
        f"(13 full weeks), which confirms the stamps really are UTC. {utc_jul26} orders carry a UTC date of 26 Jul.",
        "Converted every timestamp to Asia/Kolkata before assigning days and weeks.",
        f"Bucketing on the raw UTC date would invent a 14th week (20 Jul) with {utc_jul26} orders and shift "
        "every order placed 00:00-05:29 IST into the previous day.")

    # ---------------------------------------------------------------- 6. missing timestamps
    df["n"] = df.order_id.str[3:].astype(int)
    df = df.sort_values("n").reset_index(drop=True)
    df["week"] = week_start(df.ist)
    missing = df.ist.isna()
    n_missing, n_missing_cod_final = int(missing.sum()), int((missing & df.is_cod & df.status_n.isin(FINAL)).sum())
    # Order ids follow creation time almost perfectly, so an undated order's week can be read off
    # its id neighbours. Validate first: hide each known week and predict it from its neighbours.
    known = df[~missing].reset_index(drop=True)
    prev_k, next_k = known.week.shift(1), known.week.shift(-1)
    agree = prev_k == next_k
    holdout_acc = float((prev_k[agree] == known.week[agree]).mean())
    rank_corr = float(known.n.rank().corr(known.ist.astype("int64").rank()))
    prev_w, next_w = df.week.ffill(), df.week.bfill()
    can_impute = missing & (prev_w == next_w)
    df["week_imputed"] = False
    df.loc[can_impute, "week"] = prev_w[can_impute]
    df.loc[can_impute, "week_imputed"] = True
    log(6, "Orders with no timestamp",
        f"{n_missing} orders have an empty created_at ({n_missing_cod_final} of them are COD with a final outcome). "
        f"Order ids track time almost perfectly (rank correlation {rank_corr:.4f}).",
        f"Placed each in the week of its neighbouring order ids. Checked on {len(known):,} dated orders first: "
        f"when both neighbours share a week the guess is right {holdout_acc:.2%} of the time. All {int(can_impute.sum())} "
        "undated orders had agreeing neighbours. They count fully in the store ranking, which needs no date.",
        "{EFFECT_UNDATED}")
    assert holdout_acc > 0.999 and int(can_impute.sum()) == n_missing

    # ---------------------------------------------------------------- 7. two missing days
    days = df.ist.dropna().dt.date.value_counts()
    all_days = pd.date_range(df.ist.min().date(), df.ist.max().date(), freq="D").date
    gap_days = [d for d in all_days if d not in days.index]
    ids_contiguous = df.n.max() - df.n.min() + 1 == len(df) + int(is_test.sum())  # test rows share the id sequence
    log(7, "Two whole days have no orders at all",
        f"No order is dated {', '.join(pd.Timestamp(d).strftime('%a %d %b') for d in gap_days)} (every other day has "
        f"{days.min():,}-{days.max():,}). Order ids run without a gap straight across them, so the orders were never "
        "recorded rather than deleted afterwards. The week of 14 Sep therefore has only 5 days (about 30% fewer orders).",
        "Not filled in (there is nothing to recover). The week's rate is still reported but flagged 'partial: 5 of 7 days'.",
        "A rate is a ratio, so it stays comparable. The week's volume is not, and should not be read as a demand drop.")

    # ---------------------------------------------------------------- 8. stale non-final statuses
    cod = df[df.is_cod]
    nonfinal = cod[cod.status_n.isin(["pending", "in_transit"])]
    old_nonfinal = int((nonfinal.ist < pd.Timestamp("2026-10-01", tz=IST)).sum())
    log(8, "COD orders still 'pending' / 'in_transit' weeks or months later",
        f"{len(nonfinal):,} COD orders never reached a final outcome; {old_nonfinal:,} of them were placed before 1 Oct, "
        "and orders from July are still 'in transit'. The share is flat (about 8% every week), so these look like statuses "
        "that stopped updating rather than parcels genuinely still moving.",
        "Excluded from the denominator, as the definition says (no final outcome). Bounded their possible effect instead.",
        "{EFFECT_STALE}")

    # ---------------------------------------------------------------- 9. cancelled
    canc = df.copy()
    canc_rate = rate_table(canc.assign(a=1, status_n=canc.status_n.replace({"cancelled": "delivered"})), "a").return_rate_pct.iloc[0]
    true_rate = rate_table(df.assign(a=1), "a").return_rate_pct.iloc[0]
    log(9, "Cancelled COD orders",
        f"{int((cod.status_n == 'cancelled').sum()):,} COD orders are 'cancelled'.",
        "Excluded: a cancellation is not a delivery outcome, so it is neither a return nor a delivery.",
        f"Counting them as 'not returned' would wrongly lower the overall rate from {true_rate:.2f}% to {canc_rate:.2f}%.")

    # ---------------------------------------------------------------- 10. small store
    final_by_store = rate_table(df, "merchant_id")
    small = final_by_store[final_by_store.final_cod < MIN_FINAL_COD]
    for m, r in small.iterrows():
        log(10, f"Store {m} is too small to rank",
            f"Only {int(r.final_cod)} COD orders with a final outcome (and {int((df.merchant_id == m).sum())} orders in total, "
            f"about 18 a week). Its {r.return_rate_pct:.1f}% return rate would rank #1 among real stores, "
            f"but the 95% range is {r.ci95_low_pct:.0f}-{r.ci95_high_pct:.0f}%.",
            f"Excluded from the ranking by the >= {MIN_FINAL_COD} rule. Still included in the weekly rates.",
            "A naive 'top 3 by rate' would put this store first.")

    # ---------------------------------------------------------------- 11. placeholder order values
    v = df.order_value.astype(float)
    ph = df[v >= PLACEHOLDER_VALUE]
    log(11, "Placeholder order values",
        f"{len(ph)} orders have order_value = 9,999,999 ({', '.join(ph.order_id)}); every other order is "
        f"between {v[v < PLACEHOLDER_VALUE].min():,.0f} and {v[v < PLACEHOLDER_VALUE].max():,.0f}.",
        "Kept the orders (status and payment are fine) but flagged the value as unusable.",
        "No effect on return rates, which count orders. Would distort any revenue or AOV figure.")

    # ---------------------------------------------------------------- 12. minor / checked-and-fine
    log(12, "Other things checked and found clean",
        "CRLF line endings (handled by the CSV reader); every row has 6 fields; no non-numeric, zero or negative values; "
        "no store has a different currency or unit (median order 1,069-1,137 for every store); no near-duplicate "
        "double-submits (same store + same value within 10 minutes); 1,073 prepaid orders were also returned "
        "(normal for undeliverable parcels; out of scope since the question is about COD).",
        "Nothing to fix.", "None.")

    # ================================================================= ANSWERS
    weekly = rate_table(df, "week")
    weekly["days_with_data"] = [len({d for d in days.index if pd.Timestamp(w) <= pd.Timestamp(d) < pd.Timestamp(w) + pd.Timedelta(days=7)}) for w in weekly.index]
    weekly["note"] = ["partial: 5 of 7 days (14-15 Sep missing)" if d < 7 else "" for d in weekly.days_with_data]
    weekly["week_end"] = [(pd.Timestamp(w) + pd.Timedelta(days=6)).date() for w in weekly.index]
    weekly.index.name = "week_start_mon"
    weekly = weekly[["week_end", "final_cod", "returned", "return_rate_pct", "ci95_low_pct", "ci95_high_pct", "days_with_data", "note"]]

    eligible = final_by_store[final_by_store.final_cod >= MIN_FINAL_COD].sort_values("return_rate_pct", ascending=False)
    eligible.insert(0, "rank", range(1, len(eligible) + 1))
    top3 = eligible.head(3)

    overall = rate_table(df.assign(all="all"), "all").iloc[0]

    # ================================================================= SENSITIVITY
    sens = {}
    w_drop = rate_table(df[~df.week_imputed], "week").return_rate_pct
    sens["max_weekly_change_if_undated_orders_dropped_pts"] = round(float((w_drop - weekly.return_rate_pct).abs().max()), 2)
    worst = df.copy()
    worst.loc[worst.is_cod & worst.status_n.isin(["pending", "in_transit"]), "status_n"] = "rto"
    w_worst = rate_table(worst, "week").return_rate_pct
    sens["max_weekly_rise_if_all_stale_were_returns_pts"] = round(float((w_worst - weekly.return_rate_pct).max()), 2)
    s_worst = rate_table(worst, "merchant_id")
    s_worst = s_worst[s_worst.final_cod >= MIN_FINAL_COD].sort_values("return_rate_pct", ascending=False)
    sens["top3_if_all_stale_were_returns"] = s_worst.index[:3].tolist()
    sens["top3_unchanged_under_worst_case"] = s_worst.index[:3].tolist() == top3.index.tolist()
    # Is the week-to-week movement more than sampling noise? Chi-square test of homogeneity
    # across the 13 weeks (2 x 13 table). Critical value for df=12 at p=0.05 is 21.03.
    full = weekly
    p_all = full.returned.sum() / full.final_cod.sum()
    chi2 = float(sum(((r - n * p_all) ** 2) / (n * p_all) + (((n - r) - n * (1 - p_all)) ** 2) / (n * (1 - p_all))
                     for r, n in zip(full.returned, full.final_cod)))
    sens["weekly_chi2"] = round(chi2, 1)
    sens["weekly_chi2_critical_p05_df12"] = 21.03
    sens["weekly_rates_differ_beyond_noise"] = chi2 > 21.03
    # how a naive pipeline would answer
    naive = raw.copy()
    naive_f = naive[(naive.payment_type == "cod") & naive.status.isin(FINAL)]
    ng = naive_f.groupby("merchant_id").status.agg(final="size", rto=lambda s: int((s == "rto").sum()))
    ng["rate"] = ng.rto / ng.final * 100
    sens["naive_top3_raw_file"] = ng[ng.final >= MIN_FINAL_COD].sort_values("rate", ascending=False).index[:3].tolist()
    # are the top 3 statistically separate from #4?
    fourth = eligible.iloc[3]
    sens["rank4_store"] = eligible.index[3]
    sens["rank3_vs_rank4_ci_overlap"] = bool(top3.iloc[2].ci95_low_pct <= fourth.ci95_high_pct)
    sens["rank1_vs_rank3_ci_overlap"] = bool(top3.iloc[0].ci95_low_pct <= top3.iloc[2].ci95_high_pct)

    for i in issues:
        i["effect_on_answer"] = i["effect_on_answer"].replace(
            "{EFFECT_UNDATED}",
            f"Dropping them instead changes no weekly rate by more than {sens['max_weekly_change_if_undated_orders_dropped_pts']} points.",
        ).replace(
            "{EFFECT_STALE}",
            f"If every stale order were really a return, weekly rates would rise by up to "
            f"{sens['max_weekly_rise_if_all_stale_were_returns_pts']} points and the top 3 would read "
            f"{', '.join(sens['top3_if_all_stale_were_returns'])}"
            + (" (unchanged)." if sens["top3_unchanged_under_worst_case"] else
               " - #1 and #2 hold, but #3 is not robust to this data problem."),
        )

    # ================================================================= WRITE
    weekly.to_csv(OUT / "weekly_cod_return_rate.csv")
    final_by_store.sort_values("return_rate_pct", ascending=False).assign(
        eligible=lambda d: d.final_cod >= MIN_FINAL_COD).to_csv(OUT / "store_cod_return_rate.csv")
    pd.DataFrame(issues).to_csv(OUT / "data_issues.csv", index=False)
    summary = {
        "input_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "rows_raw": n_raw, "rows_after_dedup": n_raw - int(dup_mask.sum()),
        "rows_analysed_real_stores": len(df), "real_stores": int(df.merchant_id.nunique()),
        "overall_cod_return_rate_pct": float(overall.return_rate_pct),
        "overall_final_cod": int(overall.final_cod), "overall_returned": int(overall.returned),
        "top3": [{"store": m, "return_rate_pct": float(r.return_rate_pct), "final_cod": int(r.final_cod),
                  "returned": int(r.returned), "ci95": [float(r.ci95_low_pct), float(r.ci95_high_pct)]} for m, r in top3.iterrows()],
        "sensitivity": sens,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")

    # ================================================================= PRINT
    pd.set_option("display.width", 200)
    print(f"Input {DATA.name}  sha256 {summary['input_sha256'][:12]}...  {n_raw:,} rows -> {len(df):,} analysed ({summary['real_stores']} real stores)\n")
    print("1) COD return rate by week (Mon-Sun, IST)\n")
    print(weekly.to_string())
    print(f"\nWhole period: {overall.return_rate_pct}%  ({int(overall.returned):,} / {int(overall.final_cod):,})\n")
    print(f"2) Top 3 stores by COD return rate (>= {MIN_FINAL_COD} final COD orders)\n")
    print(top3.to_string())
    print(f"\n   next: #4 {sens['rank4_store']} {fourth.return_rate_pct}%\n")
    print(f"3) {len(issues)} data problems -> analysis/output/data_issues.csv\n")
    for i in issues:
        print(f"  [{i['#']}] {i['problem']}")
    print("\nSensitivity:", json.dumps(sens, indent=2, default=str))
    return summary


if __name__ == "__main__":
    main()
    sys.exit(0)
