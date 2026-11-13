# Part 2: Can these numbers be trusted?

**COD return rate from `orders.csv` (97,378 rows, 26 merchant ids, 27 Jul to 25 Oct 2026).**

| | |
|---|---|
| **Script** | [`cod_returns.py`](cod_returns.py), which runs end to end: `python analysis/cod_returns.py` |
| **Outputs** | [`weekly_cod_return_rate.csv`](output/weekly_cod_return_rate.csv) · [`store_cod_return_rate.csv`](output/store_cod_return_rate.csv) · [`data_issues.csv`](output/data_issues.csv) · [`summary.json`](output/summary.json) |
| **Tests** | [`tests/test_cod_returns.py`](../tests/test_cod_returns.py) pins every fix, so editing the script can't quietly undo one |
| **Input** | [`data/orders.csv`](data/orders.csv), sha256 `45c37009…ace16` (recorded in `summary.json`, so a changed file is obvious) |

**Definitions used.**
- Return rate = COD orders with status `rto` (returned to origin, i.e. back to the store) ÷ COD orders that are `delivered` or `rto`.
- `cancelled`, `pending` and `in_transit` are not final delivery outcomes, so they appear in neither part of the fraction.
- Weeks run Monday 00:00 to Sunday 23:59 in IST.
- A store must have at least 200 COD orders with a final outcome to be ranked.

---

## Answer 1: COD return rate by week (IST, Mon–Sun)

| Week (Mon–Sun) | Final COD orders | Returned | **Return rate** | 95% range |
|---|---:|---:|---:|---|
| 27 Jul – 2 Aug | 3,710 | 1,083 | **29.19%** | 27.8–30.7 |
| 3 – 9 Aug | 3,686 | 991 | **26.89%** | 25.5–28.3 |
| 10 – 16 Aug | 3,665 | 1,070 | **29.20%** | 27.8–30.7 |
| 17 – 23 Aug | 3,802 | 1,081 | **28.43%** | 27.0–29.9 |
| 24 – 30 Aug | 3,505 | 980 | **27.96%** | 26.5–29.5 |
| 31 Aug – 6 Sep | 3,515 | 1,009 | **28.71%** | 27.2–30.2 |
| 7 – 13 Sep | 3,768 | 1,058 | **28.08%** | 26.7–29.5 |
| 14 – 20 Sep ⚠️ | 2,508 | 726 | **28.95%** | 27.2–30.8 |
| 21 – 27 Sep | 3,659 | 1,045 | **28.56%** | 27.1–30.1 |
| 28 Sep – 4 Oct | 3,607 | 1,007 | **27.92%** | 26.5–29.4 |
| 5 – 11 Oct | 3,689 | 984 | **26.67%** | 25.3–28.1 |
| 12 – 18 Oct | 3,539 | 1,028 | **29.05%** | 27.6–30.6 |
| 19 – 25 Oct | 3,558 | 1,046 | **29.40%** | 27.9–30.9 |
| **Whole period** | **46,211** | **13,108** | **28.37%** | |

⚠️ The week of 14–20 Sep has data for only 5 of 7 days, because 14 and 15 Sep are missing (problem 7). Its *rate* is still valid; its *volume* is not.

**How to read it:** the rate is **flat at about 28%**. The week-to-week swings (26.7% to 29.4%) are within sampling noise: a chi-square test across the 13 weeks gives 15.8, below the 21.0 needed to call any week different at p = 0.05. Nobody should act on a single week's movement.

## Answer 2: The 3 stores with the highest COD return rate (≥ 200 final COD orders)

| Rank | Store | Final COD orders | Returned | **Return rate** | 95% range |
|---|---|---:|---:|---:|---|
| 1 | **M122** | 1,968 | 778 | **39.53%** | 37.4–41.7 |
| 2 | **M108** | 2,495 | 969 | **38.84%** | 36.9–40.8 |
| 3 | **M110** | 2,601 | 992 | **38.14%** | 36.3–40.0 |
| *4* | *M112* | *957* | *355* | *37.10%* | *34.1–40.2* |

For comparison, the average across all 24 real stores is 28.37%, and the lowest-rate store, M101, is at 17.95%.

**How sure are we?** All three are clearly well above average. Their *order* among themselves is not certain, though: the 95% ranges of #1–#3 overlap, and #3 (M110) overlaps with #4 (M112). If the stale "in transit" orders (problem 8) all turned out to be returns, M112 would move into #3. So: **M122, M108 and M110 are the answer on the data as given, with M112 a close fourth.**

**Which "top 3" would a careless analysis produce?** On the raw file it would put **M_TEST_01 (88.8%) and M_TEST_02 (88.1%)** first and second (problem 4). If the minimum were ignored it would add **M117 (63.5% on only 145 orders)** (problem 10). Both are wrong.

---

## Answer 3: Every problem found, and what was done

Ranked by how much each one could change the answer. Every count below comes from the script's own output ([`output/data_issues.csv`](output/data_issues.csv)). Counts are for the 24 real stores unless marked "after de-duplication", which means all 26 ids before the test accounts are removed.

| # | Problem | Evidence | What I did | What it would have done to the answer |
|---|---|---|---|---|
| 1 | **Test merchants mixed in with real stores** | `M_TEST_01` and `M_TEST_02` (1,686 orders after de-duplication) are COD-only, with no card, UPI or netbanking, and return rates of 88–89%. The brief's "26 stores" is really 24 stores + 2 test accounts. | Excluded from every number. | They'd be **#1 and #2** in the ranking, and the overall rate would read 30.20% instead of 28.37%. |
| 2 | **Store below the minimum looks like the worst offender** | M117 has only 145 final COD orders (227 orders in total, about 18 a week); its 63.5% rate has a 95% range of 55–71%. | Kept out of the ranking by the ≥ 200 rule; still included in the weekly rates. | A naive "top 3 by rate" puts it **first among real stores**. |
| 3 | **COD written three ways** | `cod` (48,723), `Cash on Delivery` (3,398) and `COD` (3,342), counted after de-duplication across all 26 ids. Every store uses all three, at 11–14% of its COD orders. | Treated all three as COD, using an explicit allow-list after trimming and lower-casing. | Filtering on `cod` alone silently loses **6,740 COD orders** across every store. |
| 4 | **Status written 20 ways** | 5 real statuses spelled 20 ways: `delivered`, `DELIVERED`, `" Delivered"`, `rto`, `RTO`, `" Rto"` and so on. 7,446 values (after de-duplication) have stray spaces. | Trimmed and lower-cased, then asserted the result is exactly the 5 expected statuses. | Exact matching on `rto`/`delivered` drops **5,623 of 47,664 final COD orders (12%)** (after de-duplication, all ids). |
| 5 | **Duplicate rows** | 1,439 rows are exact copies of another row; 97,378 rows hold 95,939 unique order ids. No id has two *different* versions. | Dropped the copies (keeping one). Asserted that `order_id` is unique afterwards. | Duplicated orders count twice in both the top and bottom of the rate. |
| 6 | **UTC timestamps, IST weeks** | All timestamps end in `Z`. Converted to IST, the data spans exactly Mon 27 Jul 00:00 to Sun 25 Oct 23:59, which proves the `Z` is genuine. | Converted to `Asia/Kolkata` before assigning days and weeks. | Grouping on the UTC date invents a **14th week (20 Jul)** with 230 orders, and moves every order placed between 00:00 and 05:29 IST to the wrong day. |
| 7 | **Two whole days missing** | **Mon 14 and Tue 15 Sep have zero orders**, while every other day has 908–1,217. Order ids continue without a gap across those days, so the orders were never recorded rather than deleted later. | Nothing to recover. The week is reported but flagged "partial: 5 of 7 days". | The rate stays comparable (it's a ratio); the week's volume would wrongly look like a 30% demand drop. |
| 8 | **Stale "pending" / "in transit" orders** | 4,376 real-store COD orders never reached a final outcome. 3,175 were placed before 1 Oct; 128 from July are still "in transit". The share is a steady 7.5–8.8% every week, so these look like statuses that stopped updating. | Excluded from the denominator, as the definition requires, and their possible effect measured (worst-case check below). | If all were really returns, weekly rates would rise by up to **6.75 points**, and **M112 would replace M110 at #3**. |
| 9 | **Orders with no timestamp** | 283 real-store orders have an empty `created_at` (147 of them are final COD orders). The raw file has 287, but 4 are duplicates or test rows. | Placed each in the week of its neighbouring order ids. Order ids follow time (rank correlation 0.9999), and on 93,970 dated orders this method picks the right week 100% of the time when both neighbours agree, which they do for all 283. They need no date for the store ranking. | Dropping them instead changes no weekly rate by more than **0.11 points**. |
| 10 | **Cancelled COD orders** | 3,190 real-store COD orders are `cancelled`. | Excluded: a cancellation isn't a delivery outcome. | Counting them as "not returned" would wrongly lower the overall rate from 28.37% to 26.53%. |
| 11 | **Placeholder order values** | 3 orders have `order_value = 9,999,999` (ORD0030525, ORD0031256, ORD0039939); all others are between ₹121 and ₹13,421. | Orders kept (status and payment are fine); the value is flagged as unusable. | None on return rates (they count orders), but it would wreck any revenue or average-order-value figure. |
| 12 | **Checked and found clean** | CRLF line endings; every row has 6 fields; no non-numeric, zero or negative values; no store with a different currency or unit (every store's median order is ₹1,069–1,137); no double-submits (same store + value within 10 min); 1,073 prepaid orders were also returned (normal for undeliverable parcels, and outside a COD question). | Nothing to fix. | None. |

### Worst-case checks (`summary.json → sensitivity`)

| Check | Result |
|---|---|
| Drop the 283 undated orders instead of placing them | Largest weekly change: 0.11 points |
| Treat every stale pending / in-transit COD order as a return | Weekly rates rise by up to 6.75 points; top 3 becomes M122, M108, **M112** |
| Do the weeks differ beyond noise? | No (chi-square 15.8 < 21.0) |
| Top 3 from the raw, uncleaned file | M_TEST_01, M_TEST_02, M122 ❌ |

### What I'd ask the data owner

1. Are `M_TEST_*` the only test accounts, or are there others under normal-looking ids?
2. What happened on 14–15 Sep: a tracking outage, or an export problem? Can those days be re-exported?
3. Why do orders from July still say "in transit"? If the carrier status feed stopped updating, the true return rate is somewhere between 28.4% and 34.6%, which matters more than any single week's movement.
4. Where do the duplicate rows come from (a double load in the export job)? If the job is re-run, it could happen again.
