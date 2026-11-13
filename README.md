# GoKwik Pulse V2

**A daily tracker of news coverage for India's four big checkout players, showing each company's share of the coverage.**

| | |
|---|---|
| **Companies** | GoKwik · Shopflo · Simpl · Razorpay Magic Checkout |
| **Live dashboard** | https://oneshh.github.io/gokwik-pulse-v2/ |
| **Runs** | Every day at 08:00 IST on GitHub Actions (free, runs in the cloud, no laptop needed) |
| **Alerts** | A GitHub issue (which also emails you) when a run fails or comes back empty. Healthy runs send nothing. |
| **Proof the alert fired** | See [Alert proof](#alert-proof) below |
| **Cost** | ₹0. No API keys, no servers, no database. |

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
- **Exact-phrase queries.** `"GoKwik"`, `"Shopflo"`, `"Magic Checkout" Razorpay`. Simpl is a common-sounding word, so its query is `"Simpl"` plus a payments term (BNPL, pay later, checkout, fintech or payments). Bing's search is looser, so a Bing result must also name the company in its headline or summary.
- **Two independent indexes.** If one source has an outage, the other keeps counting. The run is marked amber instead of silently undercounting.

Known limits (stated so the numbers are read correctly): RSS searches return about 100 results at most per query. Google matches the full article text, so a story that mentions *Magic Checkout* only in passing still counts. Paywalled-only outlets may be missing.

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
- **Each article is counted once.** A story's identity is its normalised headline (case, punctuation, apostrophes and a trailing "| Outlet name" are ignored). Seeing the same story again tomorrow, in another feed, or reprinted word-for-word by another outlet does **not** add to the count. Instead, the record remembers every outlet that ran it ("+2 more" on the dashboard).
- **Share of coverage** = a company's articles ÷ all company-articles in that week. An article that names two tracked companies counts once for each of them.
- **Weeks** start on Monday and are counted in IST, by publish date.

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

<!-- PROOF -->

---

## Run it locally

```bash
python3 -m pulse.run                 # fetch, save, rebuild site/data.json
python3 -m pulse.run --simulate empty  # try the "returned nothing" check (exit code 2, nothing saved)
python3 -m http.server -d site 8000  # open http://localhost:8000
pip install -r requirements-dev.txt && python3 -m pytest -q   # 19 offline tests
```

The tracker needs only the Python standard library.

## Project layout

```
pulse/config.py    companies, search queries, colours  ← edit here to add a company
pulse/sources.py   Google News + Bing News RSS fetch & parse
pulse/store.py     history file + de-duplication
pulse/health.py    the rules for when to alert
pulse/report.py    builds site/data.json for the dashboard
pulse/run.py       daily entry point
site/index.html    the dashboard (one file, no build step, light & dark mode)
.github/workflows/daily.yml   schedule → track → publish → alert / auto-recover
.github/workflows/ci.yml      tests on every push
```

## Keeping it running

GitHub pauses scheduled workflows in repos with no activity for 60 days. The daily data commit counts as activity, so the schedule keeps itself alive.
