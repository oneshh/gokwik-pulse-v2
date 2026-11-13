# GoKwik Pulse V2

**A daily tracker of news coverage for India's four big checkout players, showing each company's share of the coverage.**

| | |
|---|---|
| **Companies** | GoKwik · Shopflo · Simpl · Razorpay Magic Checkout |
| **Live dashboard** | https://oneshh.github.io/gokwik-pulse-v2/ |
| **Runs** | Every day at 08:00 IST on GitHub Actions, plus a backup run at 20:00 IST. Free, runs in the cloud, no laptop needed. |
| **Alerts** | A GitHub issue (which also emails you) when a run fails or comes back empty. Healthy runs send nothing. |
| **Proof the alert fired** | See [Alert proof](#alert-proof) below |
| **Cost** | ₹0. No API keys, no servers, no database. |

---

## Part 3: Handover note

### How to run it, and what runs when

| When | What runs | Where |
|---|---|---|
| **Every day, 08:00 IST** | `Daily tracker` workflow: fetch 3 feeds × 4 companies → de-duplicate → `pulse.audit` → commit `data/` → publish the page → open an alert issue on failure, or close an open one after a healthy run | [`daily.yml`](.github/workflows/daily.yml) on GitHub Actions |
| **Every day, 20:00 IST** | The same run again, as a backup in case GitHub skips the morning slot. De-duplication makes a second run harmless. | same |
| **Every push** | The 43 tests (tracker + Part 2) | [`ci.yml`](.github/workflows/ci.yml) |
| **On demand** | Actions → Daily tracker → *Run workflow*: `none` = a normal run, `empty` / `failure` = fire a test alert (nothing is saved) | GitHub UI |
| **By hand** | Part 2: `pip install -r requirements-dev.txt && python analysis/cod_returns.py` (rewrites `analysis/output/`) | any laptop |

Nothing runs on a laptop and there are no secrets to rotate. To change companies or queries, edit [`pulse/config.py`](pulse/config.py). To exclude an off-topic article, add it to [`data/overrides.json`](data/overrides.json). Local commands are under [Run it locally](#run-it-locally).

### What will break first, and how I'd find out

| Likely to break | How I'd find out | Gap / mitigation |
|---|---|---|
| **1. A news feed changes or blocks GitHub's servers.** Google News RSS is unofficial and can throttle cloud IPs. | A company drops to 0 → **alert issue + email**. A drop below 40% of its usual level → amber warning on the page. One source down → amber. | Amber warnings don't email anyone. A slow decline could be missed if nobody looks at the page. |
| **2. GitHub retires the Node 20 actions** (`deploy-pages@v4`, and the upload step inside `upload-pages-artifact@v4`). The run logs already warn about it. | The run fails → alert issue. | It's a planned deprecation, so bump the versions before GitHub's cut-off rather than wait for the failure. |
| **3. Counts drift without anything "failing"**, e.g. a new company named Simpl, or listicles that mention everyone. | Nothing alerts. It shows up only as more "body mention" articles in each run's summary and in `pulse.audit`. | This is the riskiest failure because it's silent. It needs a person to skim the list weekly (see "next", item 2). |
| **4. GitHub Actions itself stops** (schedule disabled, account or billing issue). | The page turns amber after 36 h with no run. No email, because the alert runs on the same system that stopped. | An outside watchdog (see "next", item 1). |
| **5. Alert emails don't arrive** (GitHub notification settings, spam filter). | Only when an alert is missed. | Fire `simulate=empty` once a month and check the inbox. |

### What I'd build next with two more days

1. **Outside watchdog (½ day).** Ping a free healthchecks.io check at the end of each healthy run; it emails if no ping arrives within 26 h. That closes the "GitHub itself stopped" gap.
2. **Weekly digest issue (½ day).** Every Monday, one GitHub issue listing amber warnings, new body-mention articles to review, and the week's shares. That makes the silent failures (rows 1 and 3) visible without making the daily alert noisy.
3. **Read the article, not just the headline (1 day).** Resolve the Google redirect links, fetch the page text, and count how often and where the company is named. That replaces the headline-vs-body heuristic with a real "is this article about them" score, and lets near-identical syndicated stories be grouped as one *story* alongside the *article* count.
4. **Production-grade Part 2.** Turn [`cod_returns.py`](analysis/cod_returns.py)'s checks (duplicates, label variants, test merchants, missing days, stale statuses) into a scheduled data-quality gate that runs on each new orders export, and refuses to publish a return rate when a check fails.

---

## Part 2: COD return-rate analysis

The data-quality analysis of `orders.csv` lives in **[`analysis/`](analysis/README.md)**: the script, its outputs and a full write-up.

- **Weekly COD return rate (IST, Mon–Sun):** flat at about 28% (26.7% to 29.4%; the differences are within sampling noise). Whole period: **28.37%**.
- **Top 3 stores (≥ 200 final COD orders):** **M122 39.53%**, **M108 38.84%**, **M110 38.14%**. M112 (37.10%) is close enough to swap with #3.
- **12 data problems found and handled**, including:
  - two test merchants that would otherwise top the ranking;
  - COD and status labels written many different ways;
  - 1,439 duplicate rows;
  - UTC timestamps that have to become IST weeks;
  - two missing days (14–15 Sep);
  - orders stuck in "in transit" for months;
  - undated orders;
  - placeholder order values.

---

## What you see on the dashboard

1. **Key highlights.** A one-line summary in plain English (who leads, how this week compares with last week), plus four headline numbers.
2. **Company cards.** Each company's share of coverage over the last 12 weeks, its article counts and a mini weekly bar chart.
3. **Weekly share of articles.** A stacked bar chart for each week, with a *Share %* or *Article count* toggle and a *Table* view. Hover over a week to see exact numbers.
4. **20 latest articles.** Newest first, each linked to the original story, tagged by company and filterable.
5. **Tracker health.** Status of the last run, a strip of recent runs (green, amber or red), what was fetched, and how the pipeline works.

---

## Where the news comes from, and why

The tracker uses **three free RSS searches for each company**:

| Source | What it adds |
|---|---|
| **Google News RSS** (plain search) | The widest coverage of Indian business media (ET, Inc42, YourStory, Moneycontrol, Entrackr, Mint…). Results are ranked by relevance and go back years, so the first run fills in the history. |
| **Google News RSS, last 30 days** (`when:30d`) | The plain search ranks by relevance, so a brand-new story can miss its top results. This search only looks at recent news, so new stories are not missed. |
| **Bing News RSS** (sorted by date) | A second, independent index. It catches stories Google misses and keeps the tracker working if Google ever blocks or changes its feed. |

**Why this mix gives the most reliable count**

- **News only.** Social posts are noisy and are not "coverage". Twitter/X and LinkedIn APIs are no longer free. Profiles from Crunchbase, Instagram, LinkedIn and similar sites are filtered out.
- **No keys and no scraping.** RSS is a published, stable format. Nothing breaks when a website changes its layout, and no account or API key can expire.
- **Exact-phrase queries.** `"GoKwik"`, `"Shopflo"`, `"Magic Checkout" Razorpay`. Simpl is a common-sounding word, so its query is `"Simpl"` plus a payments term (BNPL, pay later, checkout, fintech or payments). Bing's search is looser, so a Bing result must also name the company in its headline or summary. Without that check Bing returns unrelated stories; see the RCA table below.
- **Two independent indexes.** If one source has an outage, the other keeps counting. The run is marked amber instead of silently undercounting.

Known limits (stated so the numbers are read correctly): RSS searches return about 100 results at most per query. Google matches the full article text, so a story that mentions *Magic Checkout* only in passing still counts. Paywalled-only outlets may be missing.

---

## Is an article actually about the company? (relevance)

Every (article, company) pair gets a **relevance label**, shown as a chip on each article:

| Label | Meaning | Example |
|---|---|---|
| **headline** (solid chip) | The headline names the company. High confidence. | "Pine Labs acquires Shopflo for Rs 88 crore" |
| **body mention** (dashed chip) | The company is named only in the article text, found by Google's full-text search. Usually real coverage (GoKwik data cited in a Diwali-sales story), sometimes a passing mention. | "Festive shopping: D2C sales jump 81%" (cites GoKwik data) |

The dashboard's **All coverage / Headline only** switch recalculates every share, chart and the latest-20 list on either basis, so you can judge how much the numbers depend on body mentions. On 14 Nov 2026, 136 of 151 company-article pairs were headline matches. In headline-only mode, Razorpay Magic Checkout has **no** articles in the last 12 weeks: all its recent coverage is Razorpay stories that mention Magic Checkout in passing.

**How to verify relevance yourself**

1. Each daily run's summary page (Actions → the run) lists **new body-mention articles** with their ids, ready for a quick look.
2. `python -m pulse.audit` prints every body-mention article in the whole history.
3. If an article isn't really about a company, add it to [`data/overrides.json`](data/overrides.json) with a reason. It disappears from that company's counts on the next run. History is never deleted, so removing the entry undoes it. Two articles are already excluded this way, with reasons.

---

## How counting works

```
 08:00 IST  ┌───────────┐   ┌───────────────┐   ┌──────────────┐   ┌──────────────┐
 every day  │  Collect  │──▶│  De-duplicate │──▶│   Publish    │──▶│ Alert if bad │
            │ 3 feeds × │   │ one record per│   │ dashboard on │   │ GitHub issue │
            │ 4 companies│  │ story, forever│   │ GitHub Pages │   │ (silent if ok)│
            └───────────┘   └───────────────┘   └──────────────┘   └──────────────┘
```

- **History is kept.** Every story is stored in [`data/articles.json`](data/articles.json), which is committed back to this repo after each run. The full history and the run log ([`data/runs.json`](data/runs.json)) can be audited in git.
- **Each article is counted once.** An article is one piece of writing by one outlet. The same article is recognised and merged when:
  - the **normalised headline** matches (case, punctuation, apostrophes and a trailing "| Outlet name" are ignored). This catches repeats across days and feeds, and word-for-word syndicated copies;
  - **or** it has the **same publisher URL**;
  - **or** it's the **same outlet** (`Moneycontrol.com` = `moneycontrol`) with a headline at least 85% similar within 3 days, as long as the headlines contain the **same numbers**. This catches edited headlines, without merging "Q1 results" with "Q2 results".
- **Same event, different outlets = separate articles, on purpose.** When Moneycontrol and Entrackr both report the Pine Labs–Shopflo deal, that's two pieces of coverage, and share of coverage should reflect it. The dashboard shows how many such pairs exist under *Data quality*.
- **Share of coverage** = a company's articles ÷ all company-articles in that week. An article that names two tracked companies counts once for each of them.
- **Weeks** start on Monday and are counted in IST, by publish date.

---

## Edge cases covered (RCA checklist)

| What could go wrong | What prevents it | Tested |
|---|---|---|
| Same article counted again on later days | Stable id from the normalised headline, stored permanently | ✅ |
| Same article returned by Google *and* Bing | Same id / same URL → merged, sources recorded | ✅ |
| Outlet edits its headline after publishing | Same-outlet fuzzy match (≥85%, ≤3 days) | ✅ |
| Two different stories with similar wording ("Q1" vs "Q2", "100 jobs" vs "150 jobs") | Fuzzy merge requires identical numbers; never merges different outlets | ✅ |
| "Moneycontrol.com" vs "moneycontrol" treated as two outlets | Publisher-name normalisation | ✅ |
| Hindi or other non-English headlines collapsing into one id | Unicode-aware normalisation (no ASCII stripping) | ✅ |
| "Simpl" matching "simple" | Exact-phrase query + payments keywords; Bing results must name the company | ✅ |
| Bing returning unrelated stories (**found and fixed 14 Nov**: its sort-by-date mode ignores the query) | Option removed; regression test; strict name check on Bing results | ✅ |
| Off-topic article that only mentions a company | Relevance label + headline-only view + human overrides file | ✅ |
| Company profiles / social posts counted as news | Blocklist (Crunchbase, LinkedIn, Instagram, YouTube…) | ✅ |
| Malformed feed items or `javascript:` links | Items without a title or http(s) link are dropped before counting | ✅ |
| Old articles (first run fills in years of history) inflating recent share | Weekly charts and shares use **publish date**; cards show the last 12 weeks; all-time shown separately | ✅ |
| Article published late Sunday night IST put in the wrong week | Weeks computed in IST, not UTC | ✅ |
| One company quietly returns nothing | Health check: 0 for any company → alert | ✅ |
| A query slowly degrades (returns far fewer than usual) | Warning when a company falls below 40% of its 7-run median | ✅ |
| GitHub skips a scheduled run | Second daily run at 20:00 IST; dashboard turns amber after 36 h without a run | — |
| Duplicate slips through anyway | `pulse.audit` runs every day and **fails the run (→ alert)** if it finds one; a test checks the saved history on every push | ✅ |

---

## Alerts: fires on trouble, silent otherwise

The workflow opens a GitHub issue labelled `pulse-alert` and assigned to the repo owner. GitHub then emails you. The alert fires when:

| Condition | Alert? |
|---|---|
| The code crashes, or the job or deploy fails | 🚨 Yes |
| **The run quietly returns nothing:** 0 articles in total, or 0 for any one company across every source. Each feed returns a rolling window of past stories, so zero means something broke, not that the news stopped. | 🚨 Yes |
| Every source request fails | 🚨 Yes |
| One source fails but the other works | 🟡 No alert. Shown as amber on the dashboard. |
| Zero *new* articles today (a slow news day) | ✅ No. This is normal. |
| Healthy run | ✅ Nothing is sent |

- If an alert is already open, a new failure **comments on it** instead of opening a duplicate.
- The next healthy run **closes the issue automatically**.
- If the schedule itself stops, the dashboard turns amber once the last run is more than 36 hours old.
- Optional: add a repo secret `ALERT_WEBHOOK_URL` (a Slack or Discord incoming webhook) and the same alert is also posted there.

### Test the alert yourself

Go to **Actions → Daily tracker → Run workflow** and pick `simulate = failure` (a crash) or `simulate = empty` (a run that returns nothing). Simulated runs never touch the saved data.

### Alert proof

The alert was tested end to end on 13 Nov 2026. Everything is recorded in **[issue #1](https://github.com/oneshh/gokwik-pulse-v2/issues/1)**:

| Step | Run | What happened |
|---|---|---|
| 1. Simulated **empty run** (`simulate=empty`) | [run 43437011991](https://github.com/oneshh/gokwik-pulse-v2/actions/runs/43437011991) ❌ | Issue #1 opened: *"The run returned nothing: 0 articles across all companies and sources."* |
| 2. Simulated **crash** (`simulate=failure`) | [run 43437101524](https://github.com/oneshh/gokwik-pulse-v2/actions/runs/43437101524) ❌ | Added a comment to the open issue instead of opening a duplicate |
| 3. Real **healthy run** | [run 43437162614](https://github.com/oneshh/gokwik-pulse-v2/actions/runs/43437162614) ✅ | Issue closed automatically: *"Recovered"* |
| Earlier healthy run | [run 43436821089](https://github.com/oneshh/gokwik-pulse-v2/actions/runs/43436821089) ✅ | Alert job skipped, nothing sent |

---

## Run it locally

```bash
python3 -m pulse.run                 # fetch, save, rebuild site/data.json
python3 -m pulse.run --simulate empty  # try the "returned nothing" check (exit code 2, nothing saved)
python3 -m http.server -d site 8000  # open http://localhost:8000
python3 -m pulse.audit               # data-quality report (duplicates, relevance, overrides)
pip install -r requirements-dev.txt && python3 -m pytest -q   # 43 offline tests
```

The tracker needs only the Python standard library.

## Project layout

```
pulse/config.py    companies, search queries, colours  ← edit here to add a company
pulse/sources.py   Google News + Bing News RSS fetch & parse
pulse/store.py     history file + de-duplication
pulse/health.py    the rules for when to alert
pulse/audit.py     data-quality audit (duplicates, relevance)
data/overrides.json  human review: articles excluded from a company's count, with reasons
pulse/report.py    builds site/data.json for the dashboard
pulse/run.py       daily entry point
site/index.html    the dashboard (one file, no build step, light & dark mode)
.github/workflows/daily.yml   schedule → track → publish → alert / auto-recover
.github/workflows/ci.yml      tests on every push
analysis/cod_returns.py       Part 2: COD return-rate analysis (outputs in analysis/output/)
```

## How it runs every day (everything is on GitHub)

| Job | GitHub service | Cost |
|---|---|---|
| Wake up at 08:00 IST (+ backup at 20:00 IST) | **GitHub Actions** `schedule` (cron) in [`daily.yml`](.github/workflows/daily.yml) | Free (public repo) |
| Run the Python code | GitHub Actions runner (a fresh Ubuntu machine) | Free |
| Store history | This **git repo**: the bot commits `data/` after each run | Free |
| Host the dashboard | **GitHub Pages** | Free |
| Alert | **GitHub Issues** → email from GitHub | Free |

The only things outside GitHub are the news feeds themselves (Google News and Bing News RSS, both public).

**Caveats:**
- GitHub's scheduler is best-effort. Runs often start 5–30 minutes late and can occasionally be skipped at busy times, which is why there's a backup run.
- GitHub pauses schedules in repos with no activity for 60 days. The daily data commit counts as activity, so the schedule keeps itself alive.
- For an outside watchdog that alerts even if GitHub Actions itself is down, a free healthchecks.io "dead man's switch" can be added later; it isn't needed for normal operation.
