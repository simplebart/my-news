"""
Aurora — a personal news hub
A Streamlit RSS reader art-directed like a magazine.

Run with:  streamlit run aurora_reader.py

SETUP (one-time):
  1. Create a GitHub Gist at https://gist.github.com
     - Filename: aurora_feeds.json
     - Content:  {}
     - Set to Secret
  2. Create a GitHub token at https://github.com/settings/tokens
     - Only needs the 'gist' scope
  3. Add to Streamlit Secrets (.streamlit/secrets.toml):
     GIST_ID    = "your_gist_id_here"
     GITHUB_TOKEN = "your_token_here"
  4. Push aurora_reader.py + requirements.txt to GitHub
  5. Deploy at share.streamlit.io
"""

import hashlib
import html
import json
import os
import re
import time
import urllib.request
import urllib.parse
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import feedparser
import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# Config — edit freely, these are your personal preferences
# ─────────────────────────────────────────────────────────────────────────────

MAX_PER_FEED      = 8    # articles fetched per feed (global default)
SECTION_SIZE      = 5    # articles shown per section
MAX_PER_SOURCE    = 2    # max from same source per section
DISPLAY_LIMIT     = 80
USER_NAME         = "Bart"

MAX_PER_FEED_OVERRIDES = {
    "The Verge": 4,
    "Wired":     4,
}

LOW_RES_SOURCES = {
    "BBC News", "BBC Europe", "BBC Sport Football",
    "The Guardian", "The Guardian Film",
}

NO_SCRAPE_SOURCES = {
    "FT", "FT Opinion", "FT Alphaville",
    "The Economist", "The Economist Leaders", "MarketWatch",
}

EXCLUDE_KEYWORDS = {
    "The Verge": [
        "prime day", "deal", "deals", "review", "hands-on", "hands on",
        "best", "discount", "sale", "unboxing", "how to", "versus", " vs ",
        "giveaway", "buy", "price", "cheap", "gift guide",
    ],
    "Wired": [
        "review", "best", "buying guide", "how to", "deal", "deals",
        "discount", "sale", "gear", "tested", "gift guide", "coupon", "promo",
    ],
}

DEFAULT_FEEDS = {
    "Daily news": [
        ("BBC News",        "https://feeds.bbci.co.uk/news/rss.xml"),
        ("BBC Europe",      "https://feeds.bbci.co.uk/news/world/europe/rss.xml"),
        ("The Guardian",    "https://www.theguardian.com/world/rss"),
        ("Politico Europe", "https://www.politico.eu/feed/"),
        ("NYT World",       "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"),
    ],
    "Finance": [
        ("FT",              "https://www.ft.com/rss/home"),
        ("FT Opinion",      "https://www.ft.com/rss/opinion"),
        ("FT Alphaville",   "https://www.ft.com/alphaville?format=rss"),
        ("The Economist",   "https://www.economist.com/finance-and-economics/rss.xml"),
        ("MarketWatch",     "https://feeds.marketwatch.com/marketwatch/topstories/"),
    ],
    "Tech": [
        ("The Verge",       "https://www.theverge.com/rss/index.xml"),
        ("Wired",           "https://www.wired.com/feed/rss"),
        ("Ars Technica",    "https://feeds.arstechnica.com/arstechnica/index"),
        ("MIT Tech Review", "https://www.technologyreview.com/feed/"),
    ],
    "Cultuur": [
        ("The Guardian Film", "https://www.theguardian.com/film/rss"),
        ("Pitchfork",         "https://pitchfork.com/rss/news/"),
        ("Dezeen",            "https://www.dezeen.com/feed/"),
        ("It's Nice That",    "https://www.itsnicethat.com/rss"),
        ("Bon Appétit",       "https://www.bonappetit.com/feed/rss"),
    ],
    "Long reads": [
        ("The Economist Leaders", "https://www.economist.com/leaders/rss.xml"),
        ("Aeon",                  "https://aeon.co/feed.rss"),
        ("The Atlantic",          "https://www.theatlantic.com/feed/all/"),
    ],
    "Sport": [
        ("BBC Sport Football", "https://feeds.bbci.co.uk/sport/football/rss.xml"),
        ("The Race F1",        "https://the-race.com/feed/"),
    ],
}

DEFAULT_CALM = ["Aeon", "The Atlantic", "The Economist Leaders", "FT Opinion"]

ACCENTS = {
    "BBC News":               "#B80000",
    "BBC Europe":             "#B80000",
    "BBC Sport Football":     "#D13900",
    "The Guardian":           "#0084C6",
    "The Guardian Film":      "#0084C6",
    "Politico Europe":        "#C8141A",
    "NYT World":              "#000000",
    "FT":                     "#0F5499",
    "FT Opinion":             "#0F5499",
    "FT Alphaville":          "#0F5499",
    "The Economist":          "#E3120B",
    "The Economist Leaders":  "#E3120B",
    "MarketWatch":            "#007F5F",
    "The Verge":              "#7C3AED",
    "Ars Technica":           "#FF4E00",
    "Wired":                  "#1A1A1A",
    "MIT Tech Review":        "#111111",
    "Pitchfork":              "#1A1A1A",
    "Dezeen":                 "#111111",
    "It's Nice That":         "#FF3B2F",
    "Bon Appétit":            "#C8322B",
    "Aeon":                   "#2E5FAB",
    "The Atlantic":           "#8B1A1A",
    "The Race F1":            "#E10600",
}

ALL, TODAY, CALM_VIEW, ALL_SOURCES = "All", "Today", "Calm", "All sources"
SMART = [TODAY, ALL, CALM_VIEW]


# ─────────────────────────────────────────────────────────────────────────────
# Gist persistence — feeds saved to a GitHub Gist so they survive restarts
# Falls back to local file if no Gist credentials are configured
# ─────────────────────────────────────────────────────────────────────────────
def _gist_headers():
    token = st.secrets.get("GITHUB_TOKEN", "")
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
        "User-Agent": "Aurora/1.0",
    }


def _gist_id():
    return st.secrets.get("GIST_ID", "")


def _has_gist():
    return bool(_gist_id() and st.secrets.get("GITHUB_TOKEN", ""))


def _gist_load():
    try:
        req = urllib.request.Request(
            f"https://api.github.com/gists/{_gist_id()}",
            headers=_gist_headers(),
        )
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read())
        content = data["files"]["aurora_feeds.json"]["content"]
        return json.loads(content)
    except Exception:
        return None


def _gist_save(payload):
    try:
        body = json.dumps({
            "files": {"aurora_feeds.json": {"content": json.dumps(payload, indent=2)}}
        }).encode()
        req = urllib.request.Request(
            f"https://api.github.com/gists/{_gist_id()}",
            data=body,
            headers=_gist_headers(),
            method="PATCH",
        )
        urllib.request.urlopen(req, timeout=6)
        return True
    except Exception:
        return False


HERE       = os.path.dirname(os.path.abspath(__file__))
FEEDS_PATH = os.path.join(HERE, "feeds.json")
STATE_PATH = os.path.join(HERE, "aurora_state.json")


def load_feeds():
    # Try Gist first
    if _has_gist():
        d = _gist_load()
        if d and d.get("feeds"):
            feeds = {fold: [tuple(p) for p in items] for fold, items in d["feeds"].items()}
            return feeds, d.get("calm", list(DEFAULT_CALM))
    # Fall back to local file
    try:
        with open(FEEDS_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        feeds = {fold: [tuple(p) for p in items] for fold, items in d.get("feeds", {}).items()}
        if feeds:
            return feeds, d.get("calm", list(DEFAULT_CALM))
    except Exception:
        pass
    return {k: list(v) for k, v in DEFAULT_FEEDS.items()}, list(DEFAULT_CALM)


def save_feeds(feeds, calm):
    payload = {
        "feeds": {k: [list(p) for p in v] for k, v in feeds.items()},
        "calm":  calm,
    }
    if _has_gist():
        _gist_save(payload)
    # Always save locally too as backup
    try:
        with open(FEEDS_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception:
        pass


def load_state():
    # Try Gist first
    if _has_gist():
        d = _gist_load()
        if d and "starred" in d:
            return set(d["starred"])
    # Fall back to local file
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return set(json.load(f).get("starred", []))
    except Exception:
        return set()


def save_state(starred):
    # Save to Gist alongside feeds
    if _has_gist():
        d = _gist_load() or {}
        d["starred"] = sorted(starred)
        _gist_save(d)
    # Always save locally too
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump({"starred": sorted(starred)}, f)
    except Exception:
        pass


def aid(link):
    return hashlib.md5((link or "").encode()).hexdigest()[:12]


def toggle_star(i):
    s = load_state()
    (s.discard if i in s else s.add)(i)
    save_state(s)


# ─────────────────────────────────────────────────────────────────────────────
# Source helpers
# ─────────────────────────────────────────────────────────────────────────────
def color_for(name):
    if name in ACCENTS:
        return ACCENTS[name]
    h = int(hashlib.md5(name.encode()).hexdigest(), 16)
    return f"hsl({h % 360},52%,46%)"


def initials(name):
    parts = [p for p in re.split(r"\s+", name) if p]
    if not parts:
        return "?"
    return parts[0][:2].upper() if len(parts) == 1 else (parts[0][0] + parts[-1][0]).upper()


def icon_html(name, size=17):
    return (f'<span class="ico" style="background:{color_for(name)};'
            f'width:{size}px;height:{size}px;border-radius:{max(3,size//4)}px">'
            f'{html.escape(initials(name))}</span>')


# ─────────────────────────────────────────────────────────────────────────────
# Image helpers
# ─────────────────────────────────────────────────────────────────────────────
TAG_RE    = re.compile(r"<[^>]+>")
IMG_RE    = re.compile(r'<img[^>]+src=["\']([^"\']+)', re.IGNORECASE)
BAD_IMG   = re.compile(r'(ichef\.bbci\.co\.uk/news/\d+/|i\.guim\.co\.uk/.*?w=\d{1,3}[^0-9])', re.IGNORECASE)
OG_RE     = re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', re.IGNORECASE)
OG_RE2    = re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image', re.IGNORECASE)


def clean_text(raw):
    return " ".join(html.unescape(TAG_RE.sub(" ", raw or "")).split())


def extract_image(entry, source=""):
    if source in LOW_RES_SOURCES:
        return None
    for key in ("media_thumbnail", "media_content"):
        media = entry.get(key)
        if media and media[0].get("url") and not BAD_IMG.search(media[0]["url"]):
            return media[0]["url"]
    for link in entry.get("links", []):
        if link.get("type", "").startswith("image") and not BAD_IMG.search(link.get("href", "")):
            return link["href"]
    blob = (entry["content"][0].get("value", "") if entry.get("content") else "") + entry.get("summary", "")
    m = IMG_RE.search(blob)
    if m and not BAD_IMG.search(m.group(1)):
        return m.group(1)
    return None


def scrape_og(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4) as r:
            chunk = r.read(12288).decode("utf-8", errors="ignore")
        m = OG_RE.search(chunk) or OG_RE2.search(chunk)
        return m.group(1) if m else None
    except Exception:
        return None


def entry_time(entry):
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            try:
                return datetime.fromtimestamp(time.mktime(t), tz=timezone.utc)
            except Exception:
                pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Fetch
# ─────────────────────────────────────────────────────────────────────────────
def _is_excluded(title, source):
    kws = EXCLUDE_KEYWORDS.get(source, [])
    t   = title.lower()
    return any(k in t for k in kws)


def _fetch_one(args):
    name, url, folder = args
    cap = MAX_PER_FEED_OVERRIDES.get(name, MAX_PER_FEED)
    out = []
    try:
        for e in feedparser.parse(url).entries:
            title = clean_text(e.get("title", "Untitled"))
            if _is_excluded(title, name):
                continue
            out.append({
                "source":  name,
                "folder":  folder,
                "title":   title,
                "link":    e.get("link", "#"),
                "summary": clean_text(e.get("summary", "")),
                "image":   extract_image(e, name),
                "time":    entry_time(e),
            })
    except Exception:
        pass
    out.sort(key=lambda a: a["time"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return out[:cap]


def _scrape_one(a):
    if a["image"] is None and a["source"] not in NO_SCRAPE_SOURCES:
        a["image"] = scrape_og(a["link"])
    return a


@st.cache_data(ttl=900, show_spinner=False)
def fetch(targets):
    items = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for chunk in pool.map(_fetch_one, list(targets)):
            items.extend(chunk)
    items.sort(key=lambda a: a["time"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    needs = [a for a in items if a["image"] is None and a["source"] not in NO_SCRAPE_SOURCES]
    if needs:
        with ThreadPoolExecutor(max_workers=12) as pool:
            list(pool.map(_scrape_one, needs[:15]))  # cap at 15 to keep load time reasonable
    return items


def relative(dt):
    if not dt:
        return ""
    d = (datetime.now(timezone.utc) - dt).total_seconds()
    if d < 60:        return "now"
    if d < 3600:      return f"{int(d//60)}m"
    if d < 86400:     return f"{int(d//3600)}h"
    if d < 7*86400:   return f"{int(d//86400)}d"
    return dt.strftime("%d %b")


def diverse_section(articles, n=SECTION_SIZE, max_per=MAX_PER_SOURCE):
    counts, picked, leftover = {}, [], []
    for a in articles:
        src = a["source"]
        if counts.get(src, 0) < max_per:
            counts[src] = counts.get(src, 0) + 1
            picked.append(a)
            if len(picked) == n:
                return picked
        else:
            leftover.append(a)
    seen = {id(a) for a in picked}
    for a in leftover:
        if len(picked) >= n:
            break
        if id(a) not in seen:
            picked.append(a)
    return picked


# ─────────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Aurora", page_icon="✦", layout="wide",
                   initial_sidebar_state="expanded")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&family=Inter:wght@400;500;600;700&display=swap');

:root {
  --bg:      #0c0f1a;
  --surface: rgba(255,255,255,.05);
  --card:    rgba(255,255,255,.065);
  --ink:     #eeeef3;
  --ink-2:   rgba(228,228,242,.60);
  --ink-3:   rgba(228,228,242,.32);
  --rule:    rgba(255,255,255,.10);
  --shadow:  0 8px 28px rgba(0,0,0,.36);
  --gold:    #f0c060;
  --serif:   'Libre Baskerville', Georgia, serif;
  --sans:    'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  --r:       14px;
  --r-lg:    20px;
}
@media (prefers-color-scheme: light) {
  :root {
    --bg:#f4f4f0; --surface:rgba(0,0,0,.04); --card:#fff;
    --ink:#111118; --ink-2:#5a5a6c; --ink-3:#98989e;
    --rule:#e0e0e8; --shadow:0 4px 16px rgba(0,0,0,.08); --gold:#9a7000;
  }
}

html,body,.stApp { background:var(--bg); font-family:var(--sans); color:var(--ink); }
header[data-testid="stHeader"] { background:transparent; }
#MainMenu,footer { display:none; }
[data-testid="stAppViewContainer"],[data-testid="stMain"],
[data-testid="stMainBlockContainer"] { background:transparent !important; }
[data-testid="stMainBlockContainer"] { padding-top:1.4rem; max-width:1100px; }

/* Ambient glow */
.stApp::before {
  content:""; position:fixed; inset:0; z-index:0; pointer-events:none;
  background:
    radial-gradient(ellipse 55vw 48vh at 8% 2%,   rgba(75,95,255,.16),  transparent 66%),
    radial-gradient(ellipse 48vw 44vh at 94% 6%,  rgba(195,75,155,.13), transparent 66%),
    radial-gradient(ellipse 50vw 46vh at 82% 97%, rgba(35,185,175,.11), transparent 66%);
  animation:glow 26s ease-in-out infinite alternate;
}
@media (prefers-color-scheme:light) { .stApp::before { display:none; } }
@keyframes glow {
  from { opacity:.7; transform:scale(1); }
  to   { opacity:1;  transform:scale(1.03) translate(-1%,1%); }
}
@media (prefers-reduced-motion:reduce) {
  .stApp::before,.feature .bg { animation:none !important; transition:none !important; }
}

/* Sidebar */
[data-testid="stSidebar"] {
  background:var(--surface) !important;
  border-right:1px solid var(--rule);
  backdrop-filter:blur(22px);
}
/* Hide sidebar on mobile screens */
@media (max-width: 768px) {
  [data-testid="stSidebar"] { display: none !important; }
  [data-testid="stMainBlockContainer"] { padding-left: 1rem !important; padding-right: 1rem !important; }
}
[data-testid="stSidebar"] * { color:var(--ink); }
.brand { display:flex; align-items:center; gap:.5rem; padding:.2rem 0 .55rem; }
.brand .mark {
  width:28px; height:28px; border-radius:8px; display:grid; place-items:center;
  font-size:13px; color:#fff;
  background:linear-gradient(135deg,#5b6fff,#c44eba 55%,#38d4be);
  box-shadow:0 3px 12px rgba(91,111,255,.5),inset 0 1px 0 rgba(255,255,255,.4);
}
.brand .name { font-family:var(--serif); font-weight:700; font-size:1.22rem; letter-spacing:-.01em; }
.sidebar-cap { font-size:.67rem; letter-spacing:.10em; text-transform:uppercase; color:var(--ink-3); font-weight:700; margin:.9rem 0 -.1rem; }

/* Bigger radio labels in sidebar */
[data-testid="stSidebar"] [data-testid="stRadio"] label p { font-size:.95rem !important; font-weight:500; }
[data-testid="stSidebar"] [data-testid="stRadio"] label { padding:.18rem 0; }

/* Widgets */
.stButton button {
  border-radius:8px; border:1px solid var(--rule);
  background:var(--card); color:var(--ink);
  font-weight:600; font-size:.76rem; padding:.28rem .55rem;
  transition:background .13s;
}
.stButton button:hover { background:var(--surface); }
[data-testid="stTextInput"] input {
  background:var(--card) !important; color:var(--ink) !important;
  border:1px solid var(--rule) !important; border-radius:10px !important;
}
[data-testid="stTextInput"] input::placeholder { color:var(--ink-3) !important; }
[data-baseweb="select"] > div {
  background:var(--card) !important; border-color:var(--rule) !important; border-radius:9px !important;
}

/* Masthead */
.greet { display:flex; align-items:baseline; gap:.45rem; margin-bottom:.2rem; }
.greet-pre  { font-family:var(--serif); font-style:italic; font-size:1.85rem; font-weight:400; color:var(--ink-2); }
.greet-name { font-family:var(--serif); font-size:1.85rem; font-weight:700; color:var(--ink); letter-spacing:-.02em; }
.masthead-meta { font-size:.71rem; letter-spacing:.08em; text-transform:uppercase; color:var(--ink-3); font-weight:600; margin-bottom:.65rem; }
.masthead-rule { height:1px; margin-bottom:1rem; background:linear-gradient(90deg,var(--rule),transparent); }

/* Source icon */
.ico {
  display:inline-grid; place-items:center; flex:none;
  color:#fff; font-size:.48rem; font-weight:800;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.22);
}
.kicker { display:flex; align-items:center; gap:.38rem; font-size:.66rem; font-weight:700; letter-spacing:.06em; text-transform:uppercase; margin-bottom:.38rem; }
.kicker .dot { opacity:.4; }
.kicker .ago { opacity:.72; }
.kicker .star { color:var(--gold); }
.chip { display:flex; align-items:center; gap:.36rem; font-size:.72rem; color:var(--ink-2); font-weight:600; margin-top:.42rem; }
.chip .ago  { color:var(--ink-3); font-weight:400; }
.chip .star { color:var(--gold); margin-left:.14rem; }

/* Section divider */
.section-rule { display:flex; align-items:center; gap:.65rem; margin:1.8rem 0 .85rem; }
.section-rule .label { font-size:.67rem; font-weight:800; letter-spacing:.12em; text-transform:uppercase; color:var(--ink-3); white-space:nowrap; }
.section-rule .line  { flex:1; height:1px; background:var(--rule); }

/* Feature tile (photo overlay) */
.feature { position:relative; display:block; border-radius:var(--r-lg); overflow:hidden; text-decoration:none; box-shadow:var(--shadow); isolation:isolate; }
.feature.cover { min-height:420px; }
.feature.mid   { min-height:260px; }
.feature.small { min-height:180px; }
.feature.read  { opacity:.48; }
.feature .bg   { position:absolute; inset:0; z-index:0; background-size:cover; background-position:center; transition:transform .7s cubic-bezier(.2,.7,.2,1); }
.feature:hover .bg { transform:scale(1.04); }
.feature::after {
  content:""; position:absolute; inset:0; z-index:3; pointer-events:none; border-radius:inherit;
  background:linear-gradient(115deg,transparent 38%,rgba(255,255,255,.12) 50%,transparent 62%);
  transform:translateX(-130%); transition:transform .9s ease;
}
.feature:hover::after { transform:translateX(130%); }
.feature .plate {
  position:absolute; left:14px; right:14px; bottom:14px; z-index:2; padding:.8rem 1rem;
  background:rgba(8,10,18,.40); backdrop-filter:blur(18px) saturate(155%);
  border:1px solid rgba(255,255,255,.17); border-radius:13px;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.30),0 6px 20px rgba(0,0,0,.26);
}
.feature.cover .plate { left:22px; right:22px; bottom:22px; padding:1rem 1.25rem; max-width:70%; }
.feature .kicker { color:rgba(255,255,255,.88); }
.feature .ft { font-family:var(--serif); font-weight:700; color:#fff; letter-spacing:-.018em; line-height:1.1; margin:0; display:-webkit-box; -webkit-box-orient:vertical; overflow:hidden; }
.feature.cover .ft { font-size:2.2rem; -webkit-line-clamp:4; }
.feature.mid .ft   { font-size:1.3rem; -webkit-line-clamp:3; }
.feature.small .ft { font-size:1.05rem; -webkit-line-clamp:3; }
.feature .fdek { color:rgba(255,255,255,.78); font-size:.9rem; line-height:1.5; margin:.45rem 0 0; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
.feature.cover .fdek::first-letter { font-family:var(--serif); font-size:2.4em; float:left; line-height:.72; padding:.05em .11em 0 0; font-weight:700; color:#fff; }

/* Panel (no photo) */
.panel { position:relative; display:block; overflow:hidden; text-decoration:none; color:var(--ink); border-radius:var(--r-lg); padding:1rem 1.2rem; border:1px solid var(--rule); box-shadow:inset 0 1px 0 rgba(255,255,255,.07),var(--shadow); background:linear-gradient(148deg,color-mix(in srgb,var(--c) 14%,transparent),transparent 58%),var(--card); }
.panel.cover { min-height:420px; }
.panel.mid   { min-height:260px; }
.panel.small { min-height:180px; }
.panel.read  { opacity:.48; }
.panel::after { content:""; position:absolute; inset:0; pointer-events:none; border-radius:inherit; background:linear-gradient(115deg,transparent 38%,color-mix(in srgb,var(--c) 16%,transparent) 50%,transparent 62%); transform:translateX(-130%); transition:transform .9s ease; }
.panel:hover::after { transform:translateX(130%); }
.panel .kicker { color:var(--c); }
.panel .pt { font-family:var(--serif); font-weight:700; letter-spacing:-.015em; line-height:1.13; margin:0; color:var(--ink); display:-webkit-box; -webkit-box-orient:vertical; overflow:hidden; }
.panel.cover .pt  { font-size:2rem;    -webkit-line-clamp:5; }
.panel.mid .pt    { font-size:1.35rem; -webkit-line-clamp:4; }
.panel.small .pt  { font-size:1.05rem; -webkit-line-clamp:4; }
.panel .pdek { color:var(--ink-2); font-size:.9rem; line-height:1.5; margin:.45rem 0 0; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }

/* Small card */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div .cardlink) {
  background:var(--card) !important; border:1px solid var(--rule) !important;
  border-radius:var(--r) !important;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.06),var(--shadow);
  transition:transform .15s ease,box-shadow .15s ease;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(> div .cardlink):hover { transform:translateY(-2px); box-shadow:0 14px 32px rgba(0,0,0,.18); }
.cardlink { display:block; text-decoration:none; color:inherit; }
.cardlink.read { opacity:.44; }

/* Image wrapper — stacks placeholder + real image */
.img-wrap { position:relative; width:100%; aspect-ratio:16/10; border-radius:9px; overflow:hidden; }
.img-wrap .ph  { position:absolute; inset:0; display:grid; place-items:center; color:#fff; font-weight:800; font-size:1.25rem; }
.img-wrap .over { position:absolute; inset:0; width:100%; height:100%; object-fit:cover; border-radius:9px; }
.img-wrap .over.broken { display:none; }

.thumb-wrap { position:relative; width:72px; height:72px; border-radius:10px; overflow:hidden; flex:none; }
.thumb-wrap .ph   { position:absolute; inset:0; display:grid; place-items:center; color:#fff; font-weight:800; font-size:1rem; }
.thumb-wrap .over { position:absolute; inset:0; width:100%; height:100%; object-fit:cover; }
.thumb-wrap .over.broken { display:none; }

.cardlink .accent { height:3px; width:32px; border-radius:3px; margin:.1rem 0 .42rem; }
.ctitle { font-family:var(--serif); font-weight:700; font-size:.97rem; line-height:1.3; letter-spacing:-.01em; color:var(--ink); margin:.52rem 0 0; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }

/* ── Mobile layout — Google News style ──────────────────────────── */

/* Section header */
.m-section-head {
  display: flex; align-items: center; gap: .6rem;
  padding: .9rem 0 .6rem; margin-top: .2rem;
  border-top: 1px solid var(--rule);
}
.m-section-label {
  font-family: var(--serif); font-size: 1.1rem; font-weight: 700;
  color: var(--ink); letter-spacing: -.01em;
}
.m-section-count {
  font-size: .68rem; color: var(--ink-3); font-weight: 500;
  margin-left: auto;
}

/* Hero card — full width, tall photo */
.m-hero {
  display: block; text-decoration: none; color: var(--ink);
  border-radius: 16px; overflow: hidden;
  background: var(--card); border: 1px solid var(--rule);
  box-shadow: 0 4px 20px rgba(0,0,0,.2);
  margin-bottom: .65rem;
  transition: transform .15s ease;
}
.m-hero:active { transform: scale(.985); }
.m-hero .m-hero-img {
  position: relative; width: 100%; height: 190px; overflow: hidden;
}
.m-hero .m-hero-img .ph {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  font-weight: 800; font-size: 2.2rem; color: rgba(255,255,255,.9);
}
.m-hero .m-hero-img .ph::after {
  content: ""; position: absolute; inset: 0;
  background: repeating-linear-gradient(-45deg,
    rgba(255,255,255,.04) 0,rgba(255,255,255,.04) 1px,
    transparent 1px,transparent 8px);
}
.m-hero .m-hero-img .over {
  position: absolute; inset: 0; width:100%; height:100%; object-fit:cover;
}
.m-hero .m-hero-img .over.broken { display:none; }
.m-hero .m-hero-img .scrim {
  position: absolute; bottom:0; left:0; right:0; height:80px;
  background: linear-gradient(transparent, rgba(0,0,0,.5)); z-index:1;
}
.m-hero .m-hero-body {
  padding: .75rem .9rem .8rem;
}
.m-hero .m-source-row {
  display: flex; align-items: center; gap: .35rem;
  margin-bottom: .35rem;
}
.m-hero .m-source-name { font-size:.68rem; font-weight:700; color:var(--ink-3); }
.m-hero .m-source-dot  { font-size:.68rem; color:var(--ink-3); opacity:.5; }
.m-hero .m-source-ago  { font-size:.68rem; color:var(--ink-3); }
.m-hero .m-hero-title {
  font-family: var(--serif); font-weight: 700;
  font-size: 1.1rem; line-height: 1.28; color: var(--ink);
  display: -webkit-box; -webkit-line-clamp: 3;
  -webkit-box-orient: vertical; overflow: hidden;
}

/* Pair row — two cards side by side */
.m-pair {
  display: grid; grid-template-columns: 1fr 1fr;
  gap: .55rem; margin-bottom: .65rem;
}
.m-pair-card {
  display: flex; flex-direction: column;
  text-decoration: none; color: var(--ink);
  background: var(--card); border: 1px solid var(--rule);
  border-radius: 13px; overflow: hidden;
  box-shadow: 0 3px 12px rgba(0,0,0,.16);
  transition: transform .15s ease;
}
.m-pair-card:active { transform: scale(.97); }
.m-pair-card .m-pair-img {
  position: relative; width: 100%; aspect-ratio: 16/10; overflow: hidden;
}
.m-pair-card .m-pair-img .ph {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  font-weight: 800; font-size: 1.3rem; color: rgba(255,255,255,.9);
}
.m-pair-card .m-pair-img .over {
  position: absolute; inset:0; width:100%; height:100%; object-fit:cover;
}
.m-pair-card .m-pair-img .over.broken { display:none; }
.m-pair-card .m-pair-body { padding: .5rem .6rem .55rem; flex:1; display:flex; flex-direction:column; }
.m-pair-card .m-pair-src  { font-size:.6rem; font-weight:700; color:var(--ink-3); margin-bottom:.25rem; }
.m-pair-card .m-pair-title {
  font-family: var(--serif); font-weight: 700;
  font-size: .82rem; line-height: 1.28; color: var(--ink);
  display: -webkit-box; -webkit-line-clamp: 3;
  -webkit-box-orient: vertical; overflow: hidden; flex:1;
}

/* Compact list row — thumbnail right, text left */
.m-list-card {
  display: flex; align-items: flex-start; gap: .65rem;
  text-decoration: none; color: var(--ink);
  background: var(--card); border: 1px solid var(--rule);
  border-radius: 13px; padding: .65rem .75rem;
  margin-bottom: .5rem;
  box-shadow: 0 2px 10px rgba(0,0,0,.13);
  transition: transform .15s ease;
}
.m-list-card:active { transform: scale(.988); }
.m-list-card .m-list-body { flex:1; min-width:0; }
.m-list-card .m-list-src  { font-size:.62rem; font-weight:700; color:var(--ink-3); margin-bottom:.22rem; }
.m-list-card .m-list-title {
  font-family: var(--serif); font-weight: 700;
  font-size: .88rem; line-height: 1.28; color: var(--ink);
  display: -webkit-box; -webkit-line-clamp: 3;
  -webkit-box-orient: vertical; overflow: hidden;
}
.m-list-card .m-list-ago { font-size:.6rem; color:var(--ink-3); margin-top:.22rem; }
.m-list-thumb {
  position: relative; width: 72px; height: 64px;
  border-radius: 9px; overflow: hidden; flex-shrink:0;
}
.m-list-thumb .ph {
  position:absolute; inset:0;
  display:grid; place-items:center;
  font-weight:800; font-size:.9rem; color:rgba(255,255,255,.9);
}
.m-list-thumb .over {
  position:absolute; inset:0; width:100%; height:100%; object-fit:cover;
}
.m-list-thumb .over.broken { display:none; }

/* Save button */
[data-testid="stMain"] .stButton { display:flex; justify-content:flex-end; margin-top:.32rem; }
[data-testid="stMain"] .stButton > button { width:auto; min-height:0; font-size:.71rem; font-weight:600; padding:.2rem .58rem; border-radius:999px; }

/* Empty / more */
.empty { text-align:center; color:var(--ink-2); padding:4rem 1rem; }
.empty .big { font-family:var(--serif); font-size:1.35rem; color:var(--ink); font-weight:700; margin-bottom:.4rem; }
.more { text-align:center; color:var(--ink-3); font-size:.77rem; padding:1.5rem 0 .5rem; }

/* Column height balance */
[data-testid="stColumn"] { display:flex; }
[data-testid="stColumn"] > [data-testid="stVerticalBlockBorderWrapper"] { width:100%; height:100%; }
[data-testid="stColumn"] > [data-testid="stVerticalBlockBorderWrapper"] > div,
[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] { height:100%; display:flex; flex-direction:column; }
[data-testid="stColumn"] [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:last-child,
[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:last-child { margin-top:auto; }
/* ── Scroll-to-top button (mobile) ── */
#scroll-top {
  position: fixed;
  top: 0; left: 0; right: 0;
  height: 44px;
  z-index: 9999;
  cursor: pointer;
  background: transparent;
  border: none;
  -webkit-tap-highlight-color: transparent;
  display: none;
}
#scroll-top.visible { display: block; }
/* Thin progress bar at very top as visual hint */
#scroll-top::after {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: linear-gradient(90deg, #5b6fff, #c44eba);
  opacity: 0;
  transition: opacity .2s;
}
#scroll-top:active::after { opacity: 1; }

/* ── Bottom nav bar (mobile) ───────────────────────────────────── */
#aurora-nav {
  display: none;
  position: fixed; bottom: 0; left: 0; right: 0;
  height: 62px;
  background: rgba(12,15,26,.92);
  backdrop-filter: blur(20px) saturate(160%);
  -webkit-backdrop-filter: blur(20px) saturate(160%);
  border-top: 1px solid rgba(255,255,255,.10);
  z-index: 9000;
  padding: 0 4px;
  padding-bottom: env(safe-area-inset-bottom);
  align-items: center; justify-content: space-around;
}
@media (prefers-color-scheme: light) {
  #aurora-nav { background: rgba(244,244,240,.94); border-top: 1px solid rgba(0,0,0,.09); }
}
#aurora-nav.visible { display: flex; }

.nav-btn {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 3px; flex: 1; height: 100%;
  background: none; border: none; cursor: pointer;
  color: rgba(180,180,200,.55);
  font-size: .56rem; font-weight: 600; letter-spacing: .04em; text-transform: uppercase;
  -webkit-tap-highlight-color: transparent;
  transition: color .12s;
}
.nav-btn svg { width: 22px; height: 22px; stroke-width: 1.7; fill: none; }
.nav-btn.active { color: #fff; }
@media (prefers-color-scheme: light) {
  .nav-btn { color: rgba(60,60,80,.45); }
  .nav-btn.active { color: #111; }
}

.nav-fab {
  width: 48px; height: 48px; border-radius: 50%; flex-shrink: 0;
  background: linear-gradient(135deg, #5b6fff, #c44eba);
  border: none; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 4px 18px rgba(91,111,255,.5);
  -webkit-tap-highlight-color: transparent;
  transition: transform .14s, box-shadow .14s;
}
.nav-fab:active { transform: scale(.91); box-shadow: 0 2px 8px rgba(91,111,255,.4); }
.nav-fab svg { width: 22px; height: 22px; stroke: #fff; stroke-width: 2.2; fill: none; }

body.has-nav [data-testid="stMainBlockContainer"] { padding-bottom: 84px !important; }
</style>
<script>
(function(){
  /* Scroll to top */
  var stBtn = document.createElement("button");
  stBtn.id = "scroll-top";
  stBtn.setAttribute("aria-label","Scroll to top");
  stBtn.onclick = function(){ window.scrollTo({top:0,behavior:"smooth"}); };
  document.body.appendChild(stBtn);
  window.addEventListener("scroll",function(){
    stBtn.classList.toggle("visible", window.scrollY > 200);
  },{passive:true});

  /* Bottom nav */
  var ITEMS = [
    {id:"today", label:"Today",
     icon:'<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><rect x="3" y="4" width="18" height="18" rx="2" stroke="currentColor"/><path d="M3 9h18M8 2v4M16 2v4" stroke="currentColor"/></svg>'},
    {id:"all",   label:"All",
     icon:'<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M4 6h16M4 12h16M4 18h10" stroke="currentColor"/></svg>'},
    {id:"fab",   label:"", fab:true,
     icon:'<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M12 5v14M5 12h14" stroke="currentColor"/></svg>'},
    {id:"calm",  label:"Calm",
     icon:'<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="12" r="9" stroke="currentColor"/><path d="M12 8v4l3 3" stroke="currentColor"/></svg>'},
    {id:"saved", label:"Saved",
     icon:'<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M5 3h14a1 1 0 011 1v17l-8-4-8 4V4a1 1 0 011-1z" stroke="currentColor"/></svg>'},
  ];
  var viewMap = {today:"Today",all:"All",calm:"Calm",saved:"Saved"};

  function buildNav(){
    var nav = document.createElement("div");
    nav.id = "aurora-nav";
    ITEMS.forEach(function(item){
      if(item.fab){
        var fab = document.createElement("button");
        fab.className = "nav-fab";
        fab.innerHTML = item.icon;
        fab.setAttribute("aria-label","Add feed");
        fab.onclick = function(){
          var url = new URL(window.location.href);
          url.searchParams.set('nav','add_feed');
          window.location.href = url.toString();
        };
        nav.appendChild(fab);
      } else {
        var btn = document.createElement("button");
        btn.className = "nav-btn";
        btn.dataset.view = item.id;
        btn.innerHTML = item.icon + "<span>" + item.label + "</span>";
        btn.onclick = function(){
          document.querySelectorAll(".nav-btn").forEach(function(b){ b.classList.remove("active"); });
          this.classList.add("active");
          var url = new URL(window.location.href);
          url.searchParams.set('nav', viewMap[this.dataset.view]);
          window.location.href = url.toString();
        };
        nav.appendChild(btn);
      }
    });
    document.body.appendChild(nav);
    nav.classList.add("visible");
    document.body.classList.add("has-nav");
    // Set Today as default active
    var first = nav.querySelector(".nav-btn");
    if(first) first.classList.add("active");
  }

  if(document.readyState === "loading"){
    document.addEventListener("DOMContentLoaded", buildNav);
  } else { buildNav(); }
})();
</script>
"""
st.html(CSS)


# ─────────────────────────────────────────────────────────────────────────────
# State
# ─────────────────────────────────────────────────────────────────────────────
feeds, calm = load_feeds()
starred_set = load_state()
all_sources = [s for items in feeds.values() for s, _ in items]

if "layout" not in st.session_state:
    st.session_state.layout = "mobile"
if "nav_to" not in st.session_state:
    st.session_state.nav_to = None
if "add_feed_open" not in st.session_state:
    st.session_state.add_feed_open = False

# Intercept nav bar messages from JS (via URL query params)
_qs = st.query_params.get("nav", None)
if _qs:
    _nav_map = {"Today": TODAY, "All": ALL, "Calm": CALM_VIEW,
                "Saved": None, "add_feed": None}
    if _qs == "add_feed":
        st.session_state.add_feed_open = True
    elif _qs in _nav_map and _nav_map[_qs]:
        st.session_state.nav_to = _nav_map[_qs]
    st.query_params.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.html('<div class="brand"><div class="mark">✦</div><div class="name">Aurora</div></div>')

    st.html('<div class="sidebar-cap">Library</div>')
    _nav = st.session_state.pop("nav_to", None)
    _opts = SMART + list(feeds.keys())
    _idx  = _opts.index(_nav) if _nav and _nav in _opts else 0
    view = st.radio("Library", _opts, index=_idx, label_visibility="collapsed")

    view_sources = (
        [s for s in calm if s in all_sources] if view == CALM_VIEW
        else all_sources if view in (TODAY, ALL)
        else [s for s, _ in feeds.get(view, [])]
    )

    st.html('<div class="sidebar-cap">Source</div>')
    source = st.selectbox("Source", [ALL_SOURCES, *view_sources], label_visibility="collapsed")

    # ── Feed manager ──
    with st.expander("⚙︎  Manage feeds"):
        tab_add, tab_remove, tab_calm = st.tabs(["Add", "Remove", "Calm"])

        with tab_add:
            nf_name = st.text_input("Name", placeholder="e.g. Tortoise", key="nf_name")
            nf_url  = st.text_input("RSS URL", placeholder="https://…/feed", key="nf_url")
            fold_opts  = list(feeds.keys()) + ["➕ New section…"]
            nf_fold    = st.selectbox("Section", fold_opts, key="nf_fold")
            nf_newfold = st.text_input("New section name", key="nf_newfold") if nf_fold == "➕ New section…" else ""
            if st.button("Add feed", use_container_width=True, key="add_feed"):
                folder = (nf_newfold or "").strip() if nf_fold == "➕ New section…" else nf_fold
                if nf_name.strip() and nf_url.strip() and folder:
                    feeds.setdefault(folder, [])
                    if not any(u == nf_url.strip() for _, u in feeds[folder]):
                        feeds[folder].append((nf_name.strip(), nf_url.strip()))
                        save_feeds(feeds, calm)
                        fetch.clear()
                        st.success(f"Added {nf_name.strip()}")
                        st.rerun()
                else:
                    st.warning("Name, URL and section are required.")

        with tab_remove:
            labels = [f"{fold} · {nm}" for fold, items in feeds.items() for nm, _ in items]
            if labels:
                rm = st.selectbox("Feed to remove", labels, label_visibility="collapsed", key="rm_pick")
                if st.button("Remove", use_container_width=True, key="rm_feed", type="primary"):
                    rfold, rname = [x.strip() for x in rm.split("·", 1)]
                    feeds[rfold] = [(n, u) for n, u in feeds[rfold] if n != rname]
                    if not feeds[rfold]:
                        del feeds[rfold]
                    calm = [c for c in calm if c in [n for it in feeds.values() for n, _ in it]]
                    save_feeds(feeds, calm)
                    fetch.clear()
                    st.rerun()
            else:
                st.caption("No feeds yet.")

        with tab_calm:
            st.caption("Calm feeds appear only in the Calm view, not in Today or All.")
            new_calm = st.multiselect(
                "Calm sources", all_sources,
                default=[c for c in calm if c in all_sources],
                key="calm_pick", label_visibility="collapsed",
            )
            if set(new_calm) != set(calm):
                calm = new_calm
                save_feeds(feeds, calm)
                st.rerun()

    if st.button("↻  Refresh feeds", use_container_width=True):
        fetch.clear(); st.rerun()

    # ── Layout toggle ──
    st.html('<div class="sidebar-cap">Layout</div>')
    is_desk = st.session_state.layout == "desktop"
    lc1, lc2 = st.columns(2, gap="small")
    with lc1:
        if st.button("🖥  Desktop", use_container_width=True,
                     type="primary" if is_desk else "secondary"):
            st.session_state.layout = "desktop"; st.rerun()
    with lc2:
        if st.button("📱  Mobile", use_container_width=True,
                     type="primary" if not is_desk else "secondary"):
            st.session_state.layout = "mobile"; st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Fetch + filter
# ─────────────────────────────────────────────────────────────────────────────
calm_set = set(calm)
if view == CALM_VIEW:
    targets = tuple((n, u, folder) for folder, items in feeds.items() for n, u in items if n in calm_set)
elif view in (TODAY, ALL):
    targets = tuple((n, u, folder) for folder, items in feeds.items() for n, u in items)
else:
    targets = tuple((n, u, view) for n, u in feeds.get(view, []))

with st.spinner("Fetching…"):
    articles = fetch(targets)

if view == TODAY:
    cutoff   = datetime.now(timezone.utc) - timedelta(hours=24)
    articles = [a for a in articles if a["time"] and a["time"] >= cutoff]

seen, deduped = set(), []
for a in articles:
    a["id"] = aid(a["link"])
    if a["id"] not in seen:
        seen.add(a["id"]); deduped.append(a)
articles = deduped

if source != ALL_SOURCES:
    articles = [a for a in articles if a["source"] == source]

saved_n = sum(1 for a in articles if a["id"] in starred_set)


# ─────────────────────────────────────────────────────────────────────────────
# Masthead
# ─────────────────────────────────────────────────────────────────────────────
_now = datetime.now()
_h   = _now.hour
_pre = ("Good morning," if 5 <= _h < 12 else "Good afternoon," if 12 <= _h < 18
        else "Good evening," if 18 <= _h < 23 else "Still up,")
title_txt = source if source != ALL_SOURCES else view

st.html(
    f'<div class="greet">'
    f'<span class="greet-pre">{_pre}</span> '
    f'<span class="greet-name">{html.escape(USER_NAME)}</span></div>'
    f'<div class="masthead-meta">'
    f'{html.escape(title_txt)} &nbsp;·&nbsp; {_now.strftime("%A %-d %B %Y")}'
    f' &nbsp;·&nbsp; {len(articles)} stories &nbsp;·&nbsp; {saved_n} saved</div>'
    f'<div class="masthead-rule"></div>'
)

col_show, col_search = st.columns([1, 3], gap="small")
with col_show:
    show = st.segmented_control("Show", ["All", "Saved"], default="All",
                                label_visibility="collapsed") or "All"
with col_search:
    query = st.text_input("Search", placeholder="Search headlines…", label_visibility="collapsed")

if show == "Saved":
    articles = [a for a in articles if a["id"] in starred_set]
if query:
    q = query.lower()
    articles = [a for a in articles if q in a["title"].lower() or q in a["summary"].lower()]


# ─────────────────────────────────────────────────────────────────────────────
# HTML builders
# ─────────────────────────────────────────────────────────────────────────────
def _kicker(a):
    star = ' <span class="star">★</span>' if a["id"] in starred_set else ""
    return (f'<div class="kicker">{icon_html(a["source"])}'
            f'<span>{html.escape(a["source"])}</span>'
            f'<span class="dot">·</span><span class="ago">{relative(a["time"])}</span>{star}</div>')


def _chip(a):
    star = '<span class="star">★</span>' if a["id"] in starred_set else ""
    return (f'<div class="chip">{icon_html(a["source"])}'
            f'<span>{html.escape(a["source"])}</span>'
            f'<span class="ago">· {relative(a["time"])}</span>{star}</div>')


def _img_wrap(img_url, color, inits, wrap="img-wrap"):
    on_err = "this.classList.add('broken')"
    img    = html.escape(img_url, quote=True)
    return (f'<div class="{wrap}">'
            f'<div class="ph" style="background:{color}">{inits}</div>'
            f'<img class="over" src="{img}" loading="lazy" onerror="{on_err}">'
            f'</div>')


def feature_html(a, size="mid"):
    img  = (a["image"] or "").replace("'", "%27")
    dek  = (f'<div class="fdek">{html.escape(a["summary"][:220])}</div>'
            if size == "cover" and a["summary"] else "")
    return (f'<a class="feature {size}" href="{html.escape(a["link"],quote=True)}"'
            f' target="_blank" rel="noopener noreferrer">'
            f'<div class="bg" style="background-color:{color_for(a["source"])};'
            f'background-image:url(\'{html.escape(img,quote=True)}\')"></div>'
            f'<div class="plate">{_kicker(a)}'
            f'<div class="ft">{html.escape(a["title"])}</div>{dek}</div></a>')


def panel_html(a, size="mid"):
    dek = f'<div class="pdek">{html.escape(a["summary"][:240])}</div>' if a["summary"] else ""
    return (f'<a class="panel {size}" href="{html.escape(a["link"],quote=True)}"'
            f' target="_blank" rel="noopener noreferrer" style="--c:{color_for(a["source"])}">'
            f'{_kicker(a)}<div class="pt">{html.escape(a["title"])}</div>{dek}</a>')


def card_html(a):
    link  = html.escape(a["link"], quote=True)
    title = html.escape(a["title"])
    color = color_for(a["source"])
    inits = html.escape(initials(a["source"]))
    if a["image"]:
        media = _img_wrap(a["image"], color, inits)
        return (f'<a class="cardlink" href="{link}" target="_blank" rel="noopener noreferrer">'
                f'{media}<div class="ctitle">{title}</div>{_chip(a)}</a>')
    accent = f'<div class="accent" style="background:{color}"></div>'
    return (f'<a class="cardlink text" href="{link}" target="_blank" rel="noopener noreferrer">'
            f'{accent}<div class="ctitle">{title}</div>{_chip(a)}</a>')


# ─────────────────────────────────────────────────────────────────────────────
# Mobile HTML builders
# ─────────────────────────────────────────────────────────────────────────────
def _m_img(img_url, color, inits, cls):
    on_err = "this.classList.add('broken')"
    img    = html.escape(img_url, quote=True) if img_url else ""
    ph     = f'<div class="ph" style="background:{color}">{inits}</div>'
    over   = f'<img class="over" src="{img}" loading="lazy" onerror="{on_err}">' if img_url else ""
    return f'<div class="{cls}">{ph}{over}</div>'


def _m_src_row(src_e, color, ago):
    return (f'<div class="m-source-row">'
            f'<span class="m-source-name" style="color:{color}">{src_e}</span>'
            f'<span class="m-source-dot">·</span>'
            f'<span class="m-source-ago">{ago}</span>'
            f'</div>')


def m_hero_html(a):
    """Full-width hero card — big photo, large title."""
    link  = html.escape(a["link"], quote=True)
    title = html.escape(a["title"])
    src   = a["source"]; color = color_for(src)
    inits = html.escape(initials(src)); src_e = html.escape(src)
    ago   = relative(a["time"])
    img   = _m_img(a["image"], color, inits, "m-hero-img")
    scrim = '<div class="scrim"></div>'
    img_w = img.replace("</div>", f"{scrim}</div>", 1)
    body  = (f'<div class="m-hero-body">'
             f'{_m_src_row(src_e, color, ago)}'
             f'<div class="m-hero-title">{title}</div>'
             f'</div>')
    return f'<a class="m-hero" href="{link}" target="_blank" rel="noopener noreferrer">{img_w}{body}</a>'


def m_pair_html(a):
    """Half-width card for the pair row."""
    link  = html.escape(a["link"], quote=True)
    title = html.escape(a["title"])
    src   = a["source"]; color = color_for(src)
    inits = html.escape(initials(src)); src_e = html.escape(src)
    img   = _m_img(a["image"], color, inits, "m-pair-img")
    return (f'<a class="m-pair-card" href="{link}" target="_blank" rel="noopener noreferrer">'
            f'{img}'
            f'<div class="m-pair-body">'
            f'<div class="m-pair-src" style="color:{color}">{src_e}</div>'
            f'<div class="m-pair-title">{title}</div>'
            f'</div></a>')


def m_list_html(a):
    """Compact list row — text left, small thumb right."""
    link  = html.escape(a["link"], quote=True)
    title = html.escape(a["title"])
    src   = a["source"]; color = color_for(src)
    inits = html.escape(initials(src)); src_e = html.escape(src)
    ago   = relative(a["time"])
    thumb = _m_img(a["image"], color, inits, "m-list-thumb")
    return (f'<a class="m-list-card" href="{link}" target="_blank" rel="noopener noreferrer">'
            f'<div class="m-list-body">'
            f'<div class="m-list-src" style="color:{color}">{src_e}</div>'
            f'<div class="m-list-title">{title}</div>'
            f'<div class="m-list-ago">{ago}</div>'
            f'</div>'
            f'{thumb}</a>')


def strip_card_html(a):
    """Kept for compatibility — routes to m_list_html."""
    return m_list_html(a)


def actions(a):
    is_star = a["id"] in starred_set
    st.button("★ Saved" if is_star else "☆ Save",
              key=f"s_{a['id']}", on_click=toggle_star, args=(a["id"],))


def section_header(label, desktop=True):
    """Clickable section header — tapping navigates to that folder view."""
    if desktop:
        col_lbl, col_line = st.columns([2, 8], gap="small")
        with col_lbl:
            if st.button(label, key=f"nav_{label}", use_container_width=True):
                st.session_state.nav_to = label
                st.rerun()
        with col_line:
            st.html('<div style="height:1px;background:var(--rule);margin-top:1.1rem"></div>')
    else:
        count = len(folder_items) if "folder_items" in dir() else ""
        st.html(
            f'<div class="m-section-head">'
            f'<span class="m-section-label">{html.escape(label)}</span>'
            f'</div>'
        )
        if st.button(f"{label} →", key=f"nav_{label}"):
            st.session_state.nav_to = label
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Desktop layout
# ─────────────────────────────────────────────────────────────────────────────
def render_big(a, size="mid"):
    with st.container(border=False):
        st.html(feature_html(a, size) if a["image"] else panel_html(a, size))
        actions(a)


def render_small(a):
    with st.container(border=True):
        st.html(card_html(a))
        actions(a)


def render_section_desktop(folder_items, is_first=False):
    items = diverse_section(folder_items)
    if not items:
        return
    render_big(items[0], size="cover" if is_first else "mid")
    st.write("")
    if len(items) >= 3:
        c1, c2 = st.columns(2, gap="medium")
        with c1: render_big(items[1], "mid")
        with c2: render_big(items[2], "mid")
        st.write("")
    tail = items[3:]
    if tail:
        cols = st.columns(len(tail), gap="medium")
        for col, a in zip(cols, tail):
            with col: render_small(a)
        st.write("")


# ─────────────────────────────────────────────────────────────────────────────
# Mobile layout — Google News style
# ─────────────────────────────────────────────────────────────────────────────
def render_section_mobile(folder_items):
    """
    Layout per section:
      [0]      — hero: full-width, big photo, large title
      [1] [2]  — pair: two half-width cards side by side
      [3] [4]  — list: compact rows with thumbnail right
    """
    items = diverse_section(folder_items)
    if not items:
        return

    # Hero
    st.html(m_hero_html(items[0]))

    # Pair
    if len(items) >= 3:
        pair = m_pair_html(items[1]) + m_pair_html(items[2])
        st.html(f'<div class="m-pair">{pair}</div>')
    elif len(items) == 2:
        st.html(m_list_html(items[1]))

    # List rows
    for a in items[3:]:
        st.html(m_list_html(a))


# ─────────────────────────────────────────────────────────────────────────────
# Render
# ─────────────────────────────────────────────────────────────────────────────
if not articles:
    msg = ("No saved stories yet — tap Save on anything you want to keep."
           if show == "Saved"
           else "Nothing here. Try a different view, clear the search, or refresh.")
    st.html(f'<div class="empty"><div class="big">Nothing here</div>{msg}</div>')

else:
    items       = articles[:DISPLAY_LIMIT]
    mobile_mode = st.session_state.layout == "mobile"
    use_grouped = view in (ALL, TODAY, CALM_VIEW) and source == ALL_SOURCES

    if use_grouped:
        grouped: dict = OrderedDict()
        for a in items:
            grouped.setdefault(a.get("folder", "Other"), []).append(a)

        for idx, (folder, folder_items) in enumerate(grouped.items()):
            if not folder_items:
                continue
            section_header(folder, desktop=not mobile_mode)
            if mobile_mode:
                render_section_mobile(folder_items)
            else:
                render_section_desktop(folder_items, is_first=(idx == 0))

    else:
        # Single folder / source view — magazine rhythm on both desktop and mobile
        # Back button to Today
        if st.button("← Today", key="back_to_today"):
            st.session_state.nav_to = TODAY
            st.rerun()
        st.write("")
        cover = next((a for a in items if a["image"]), items[0])
        rest  = [a for a in items if a is not cover]
        render_big(cover, size="cover")
        st.write("")
        pattern = ["trio", "trio", "band", "trio", "pair", "trio"]
        i, p, n = 0, 0, len(rest)
        while i < n:
            block = pattern[p % len(pattern)]; p += 1; left = n - i
            if left <= 2:
                if left == 1: render_big(rest[i])
                else:
                    c1, c2 = st.columns(2, gap="medium")
                    with c1: render_small(rest[i])
                    with c2: render_small(rest[i+1])
                break
            if block == "band":
                render_big(rest[i]); i += 1
            elif block == "pair":
                chunk = rest[i:i+2]; i += 2
                c1, c2 = st.columns(2, gap="medium")
                with c1: render_big(chunk[0])
                with c2: render_big(chunk[1])
            else:
                chunk = rest[i:i+3]; i += 3
                cols = st.columns(3, gap="medium")
                for k, a in enumerate(chunk):
                    with cols[k]: render_small(a)
            st.write("")

    if len(articles) > DISPLAY_LIMIT:
        st.html(f'<div class="more">Showing {DISPLAY_LIMIT} of {len(articles)} stories. '
                f'Pick a section or search to go deeper.</div>')
