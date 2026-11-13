"""What we track and where we look. Edit this file to add a company or tune a query."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SITE_DIR = ROOT / "site"
ARTICLES_FILE = DATA_DIR / "articles.json"
RUNS_FILE = DATA_DIR / "runs.json"
SITE_DATA_FILE = SITE_DIR / "data.json"

# Indian timezone offset: weeks and "today" are counted in IST, where these companies operate.
IST_OFFSET_HOURS = 5.5

# Each company has:
#   query    - the search string sent to the news sources
#   match    - regex an article's title/summary must contain to count (guards against
#              loose matches, e.g. "simple" for Simpl). Case-insensitive.
#   color    - categorical colour (validated colour-blind safe, fixed order)
COMPANIES = [
    {
        "id": "gokwik",
        "name": "GoKwik",
        "query": '"GoKwik"',
        "match": r"go\s?kwik",
        "color": "#2a78d6",
        "color_dark": "#3987e5",
    },
    {
        "id": "shopflo",
        "name": "Shopflo",
        "query": '"Shopflo"',
        "match": r"shop\s?flo",
        "color": "#eb6834",
        "color_dark": "#d95926",
    },
    {
        "id": "simpl",
        "name": "Simpl",
        "query": '"Simpl" (BNPL OR "pay later" OR checkout OR fintech OR payments)',
        "match": r"\bsimpl\b",
        "color": "#1baf7a",
        "color_dark": "#199e70",
    },
    {
        "id": "razorpay_magic",
        "name": "Razorpay Magic Checkout",
        "query": '"Magic Checkout" Razorpay',
        "match": r"magic\s?checkout",
        "color": "#eda100",
        "color_dark": "#c98500",
    },
]

# Sources that must apply the `match` regex. Google News matches against the full article
# text, so its titles often don't name the company; we trust its exact-phrase search.
# Bing's RSS search is looser, so its results must name the company in title/summary.
STRICT_MATCH_SOURCES = {"bing"}

# Results from these "publishers" are profiles or social posts, not news articles.
BLOCKED_PUBLISHERS = [
    "crunchbase", "instagram", "facebook", "linkedin", "youtube", "twitter", "x.com",
    "reddit", "tracxn", "pitchbook", "wikipedia", "glassdoor", "ambitionbox", "zaubacorp",
]

HTTP_TIMEOUT = 20
HTTP_RETRIES = 3
USER_AGENT = "Mozilla/5.0 (compatible; GoKwikPulse/2.0; +https://github.com)"

LATEST_COUNT = 20
WEEKS_ON_DASHBOARD = 12
