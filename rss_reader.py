"""
Aurora — a personal news hub
A Streamlit RSS reader art-directed like a magazine.

Run with:  streamlit run aurora_reader.py

Deploy free at:  https://streamlit.io/cloud
  1. Push this file + requirements.txt to a GitHub repo
  2. Connect repo at share.streamlit.io
  3. Done — available on any device, 24/7

Feeds live in feeds.json (auto-created on first run).
Saved state lives in aurora_state.json.
Per-section volume cap + source diversity are enforced at render time.
"""

import hashlib
import html
import json
import os
import re
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import feedparser
import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

# How many articles to fetch per individual feed (global default)
MAX_PER_FEED = 8

# Per-source fetch cap overrides (lower = less noise from high-volume sources)
MAX_PER_FEED_OVERRIDES = {
    "The Verge": 4,
    "Wired":     4,
}

# How many articles to show per section in the grouped view
SECTION_SIZE = 5

# Max articles from the same source within one section (diversity cap)
MAX_PER_SOURCE_IN_SECTION = 2

DISPLAY_LIMIT = 80
USER_NAME     = "Bart"

# Sources whose images are frequently low-res thumbnails — skip their images
# and fall back to the colour-plate treatment instead.
LOW_RES_SOURCES = {"BBC News", "BBC Europe", "BBC Sport Football", "The Guardian", "The Guardian Film"}

# Keywords to filter out per source (case-insensitive, matched against title).
# Articles whose title contains any of these words are silently skipped.
EXCLUDE_KEYWORDS = {
    "The Verge": [
        "prime day", "deal", "deals", "review", "hands-on", "hands on",
        "best", "discount", "sale", "unboxing", "how to", "versus", " vs ",
        "giveaway", "buy", "price", "cheap", "gift guide",
    ],
    "Wired": [
        "review", "best", "buying guide", "how to", "deal", "deals",
        "discount", "sale", "gear", "tested", "gift guide",
    ],
}

DEFAULT_FEEDS = {
    "Daily news": [
        ("BBC News",        "https://feeds.bbci.co.uk/news/rss.xml"),
        ("BBC Europe",      "https://feeds.bbci.co.uk/news/world/europe/rss.xml"),
        ("The Guardian",    "https://www.theguardian.com/world/rss"),
        ("Politico Europe", "https://www.politico.eu/feed/"),
        ("DW",              "https://rss.dw.com/rdf/rss-en-top"),
        ("Euronews",        "https://www.euronews.com/rss?level=theme&name=news"),
    ],
    "Finance": [
        ("FT",              "https://www.ft.com/rss/home"),
        ("FT Opinion",      "https://www.ft.com/rss/opinion"),
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
        ("The Guardian Film",  "https://www.theguardian.com/film/rss"),
        ("Pitchfork",          "https://pitchfork.com/rss/news/"),
        ("Dezeen",             "https://www.dezeen.com/feed/"),
        ("It's Nice That",     "https://www.itsnicethat.com/rss"),
        ("Bon Appétit",        "https://www.bonappetit.com/feed/rss"),
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
    "DW":                     "#1A5EA8",
    "Euronews":               "#0050A0",
    "FT":                     "#0F5499",
    "FT Opinion":             "#0F5499",
    "The Economist":          "#E3120B",
    "The Economist Leaders":  "#E3120B",
    "MarketWatch":            "#007F5F",
    "The Verge":              "#7C3AED",
    "Ars Technica":           "#FF4E00",
    "Wired":                  "#000000",
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

HERE       = os.path.dirname(os.path.abspath(__file__))
FEEDS_PATH = os.path.join(HERE, "feeds.json")
STATE_PATH = os.path.join(HERE, "aurora_state.json")


# ─────────────────────────────────────────────────────────────────────────────
# Persistence
# ─────────────────────────────────────────────────────────────────────────────
def load_feeds():
    try:
        with open(FEEDS_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        feeds = {fold: [tuple(p) for p in items] for fold, items in d.get("feeds", {}).items()}
        if feeds:
            return feeds, d.get("calm", [])
    except Exception:
        pass
    save_feeds(DEFAULT_FEEDS, DEFAULT_CALM)
    return {k: list(v) for k, v in DEFAULT_FEEDS.items()}, list(DEFAULT_CALM)


def save_feeds(feeds, calm):
    try:
        with open(FEEDS_PATH, "w", encoding="utf-8") as f:
            json.dump({"feeds": {k: [list(p) for p in v] for k, v in feeds.items()},
                       "calm": calm}, f, indent=2)
    except Exception:
        pass


def load_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        return set(d.get("starred", []))
    except Exception:
        return set()


def save_state(starred):
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump({"starred": sorted(starred)}, f)
    except Exception:
        pass


def aid(link):
    return hashlib.md5((link or "").encode("utf-8")).hexdigest()[:12]


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
    h = int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16)
    return f"hsl({h % 360},52%,46%)"


def initials(name):
    parts = [p for p in re.split(r"\s+", name) if p]
    if not parts:
        return "?"
    return parts[0][:2].upper() if len(parts) == 1 else (parts[0][0] + parts[-1][0]).upper()


def icon_html(name):
    return (f'<span class="ico" style="background:{color_for(name)}">'
            f'{html.escape(initials(name))}</span>')


# ─────────────────────────────────────────────────────────────────────────────
# Fetch + parse
# ─────────────────────────────────────────────────────────────────────────────
TAG_RE = re.compile(r"<[^>]+>")
IMG_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)', re.IGNORECASE)

# Patterns that indicate a low-quality/thumbnail image URL
BAD_IMG_RE = re.compile(r'(ichef\.bbci\.co\.uk/news/\d+/|i\.guim\.co\.uk/.*?w=\d{1,3}[^0-9])', re.IGNORECASE)

def clean_text(raw):
    return " ".join(html.unescape(TAG_RE.sub(" ", raw or "")).split())


def extract_image(entry, source_name=""):
    # Skip images for sources that serve bad thumbnails
    if source_name in LOW_RES_SOURCES:
        return None

    for key in ("media_thumbnail", "media_content"):
        media = entry.get(key)
        if media and media[0].get("url"):
            url = media[0]["url"]
            if not BAD_IMG_RE.search(url):
                return url
    for link in entry.get("links", []):
        if link.get("type", "").startswith("image"):
            href = link.get("href", "")
            if href and not BAD_IMG_RE.search(href):
                return href
    blob = (entry["content"][0].get("value", "") if entry.get("content") else "") + entry.get("summary", "")
    m = IMG_RE.search(blob)
    if m:
        url = m.group(1)
        if not BAD_IMG_RE.search(url):
            return url
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


def _is_excluded(title, source):
    keywords = EXCLUDE_KEYWORDS.get(source, [])
    if not keywords:
        return False
    title_lower = title.lower()
    return any(kw in title_lower for kw in keywords)


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


@st.cache_data(ttl=900, show_spinner=False)
def fetch(targets):
    items = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for chunk in pool.map(_fetch_one, list(targets)):
            items.extend(chunk)
    items.sort(key=lambda a: a["time"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return items


def relative(dt):
    if not dt:
        return ""
    diff = (datetime.now(timezone.utc) - dt).total_seconds()
    if diff < 60:        return "now"
    if diff < 3600:      return f"{int(diff // 60)}m"
    if diff < 86400:     return f"{int(diff // 3600)}h"
    if diff < 7 * 86400: return f"{int(diff // 86400)}d"
    return dt.strftime("%d %b")


# ─────────────────────────────────────────────────────────────────────────────
# Diversity: pick SECTION_SIZE articles from a section, max 2 per source
# ─────────────────────────────────────────────────────────────────────────────
def diverse_section(articles, n=SECTION_SIZE, max_per_source=MAX_PER_SOURCE_IN_SECTION):
    """
    From a list sorted by recency, pick up to n articles ensuring no single
    source appears more than max_per_source times.
    """
    counts = {}
    picked = []
    for a in articles:
        src = a["source"]
        if counts.get(src, 0) < max_per_source:
            counts[src] = counts.get(src, 0) + 1
            picked.append(a)
            if len(picked) == n:
                break
    return picked


# ─────────────────────────────────────────────────────────────────────────────
# Page config + CSS
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Aurora",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&family=Inter:wght@400;500;600;700&display=swap');

/* ── Tokens ── */
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
    --bg:      #f4f4f0;
    --surface: rgba(0,0,0,.04);
    --card:    #ffffff;
    --ink:     #111118;
    --ink-2:   #5a5a6c;
    --ink-3:   #98989e;
    --rule:    #e0e0e8;
    --shadow:  0 4px 16px rgba(0,0,0,.08);
    --gold:    #9a7000;
  }
}

/* ── Base ── */
html, body, .stApp { background: var(--bg); font-family: var(--sans); color: var(--ink); }
header[data-testid="stHeader"]  { background: transparent; }
#MainMenu, footer               { display: none; }
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="stMainBlockContainer"] { background: transparent !important; }
[data-testid="stMainBlockContainer"] { padding-top: 1.6rem; max-width: 1100px; }

/* ── Ambient glow (dark only) ── */
.stApp::before {
  content:""; position:fixed; inset:0; z-index:0; pointer-events:none;
  background:
    radial-gradient(ellipse 55vw 48vh at 8%  2%,  rgba(75,95,255,.16), transparent 66%),
    radial-gradient(ellipse 48vw 44vh at 94% 6%,  rgba(195,75,155,.13), transparent 66%),
    radial-gradient(ellipse 50vw 46vh at 82% 97%, rgba(35,185,175,.11), transparent 66%);
  animation: glow 26s ease-in-out infinite alternate;
}
@media (prefers-color-scheme: light) { .stApp::before { display:none; } }
@keyframes glow {
  from { opacity:.7; transform:scale(1); }
  to   { opacity:1;  transform:scale(1.03) translate(-1%,1%); }
}
@media (prefers-reduced-motion:reduce) {
  .stApp::before, .feature .bg { animation:none !important; transition:none !important; }
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
  background: var(--surface) !important;
  border-right: 1px solid var(--rule);
  backdrop-filter: blur(22px);
}
[data-testid="stSidebar"] * { color: var(--ink); }

.brand {
  display:flex; align-items:center; gap:.5rem; padding:.2rem 0 .55rem;
}
.brand .mark {
  width:28px; height:28px; border-radius:8px; display:grid; place-items:center;
  font-size:13px; color:#fff;
  background: linear-gradient(135deg, #5b6fff, #c44eba 55%, #38d4be);
  box-shadow: 0 3px 12px rgba(91,111,255,.5), inset 0 1px 0 rgba(255,255,255,.4);
}
.brand .name {
  font-family:var(--serif); font-weight:700; font-size:1.22rem; letter-spacing:-.01em;
}
.sidebar-cap {
  font-size:.67rem; letter-spacing:.10em; text-transform:uppercase;
  color:var(--ink-3); font-weight:700; margin:.9rem 0 -.1rem;
}

/* Layout toggle buttons at sidebar bottom */
.layout-toggle {
  display:flex; gap:8px; padding: .6rem 0 .2rem;
}
.layout-toggle button {
  flex:1; border-radius:10px; border:1px solid var(--rule);
  background:var(--card); color:var(--ink);
  font-size:.78rem; font-weight:600; padding:.45rem .5rem;
  cursor:pointer; transition:background .13s, border-color .13s;
}
.layout-toggle button.active {
  background: rgba(91,111,255,.22);
  border-color: rgba(91,111,255,.55);
  color: var(--ink);
}
.layout-toggle button:hover:not(.active) { background:var(--surface); }

/* ── Widgets ── */
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

/* ── Masthead ── */
.greet { display:flex; align-items:baseline; gap:.45rem; margin-bottom:.2rem; }
.greet-pre  { font-family:var(--serif); font-style:italic; font-size:1.85rem; font-weight:400; color:var(--ink-2); }
.greet-name { font-family:var(--serif); font-size:1.85rem; font-weight:700; color:var(--ink); letter-spacing:-.02em; }
.masthead-meta {
  font-size:.71rem; letter-spacing:.08em; text-transform:uppercase;
  color:var(--ink-3); font-weight:600; margin-bottom:.65rem;
}
.masthead-rule { height:1px; margin-bottom:1rem; background:linear-gradient(90deg, var(--rule), transparent 100%); }

/* ── Source identity ── */
.ico {
  width:17px; height:17px; border-radius:4px; flex:none;
  display:inline-grid; place-items:center;
  color:#fff; font-size:.5rem; font-weight:800;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.22);
}
.kicker {
  display:flex; align-items:center; gap:.38rem;
  font-size:.66rem; font-weight:700; letter-spacing:.06em; text-transform:uppercase;
  margin-bottom:.38rem;
}
.kicker .dot  { opacity:.4; }
.kicker .ago  { opacity:.72; }
.kicker .star { color:var(--gold); }
.chip {
  display:flex; align-items:center; gap:.36rem;
  font-size:.72rem; color:var(--ink-2); font-weight:600; margin-top:.42rem;
}
.chip .ago  { color:var(--ink-3); font-weight:400; }
.chip .star { color:var(--gold); margin-left:.14rem; }

/* ── Section divider ── */
.section-rule {
  display:flex; align-items:center; gap:.65rem; margin:1.8rem 0 .85rem;
}
.section-rule .label {
  font-size:.67rem; font-weight:800; letter-spacing:.12em;
  text-transform:uppercase; color:var(--ink-3); white-space:nowrap;
}
.section-rule .line { flex:1; height:1px; background:var(--rule); }

/* ── Feature (photo overlay) ── */
.feature {
  position:relative; display:block; border-radius:var(--r-lg);
  overflow:hidden; text-decoration:none;
  box-shadow:var(--shadow); isolation:isolate;
}
.feature.cover { min-height:420px; }
.feature.mid   { min-height:260px; }
.feature.small { min-height:180px; }
.feature.read  { opacity:.48; }

.feature .bg {
  position:absolute; inset:0; z-index:0;
  background-size:cover; background-position:center;
  transition:transform .7s cubic-bezier(.2,.7,.2,1);
}
.feature:hover .bg { transform:scale(1.04); }

/* sheen sweep */
.feature::after {
  content:""; position:absolute; inset:0; z-index:3; pointer-events:none;
  border-radius:inherit;
  background:linear-gradient(115deg,transparent 38%,rgba(255,255,255,.12) 50%,transparent 62%);
  transform:translateX(-130%); transition:transform .9s ease;
}
.feature:hover::after { transform:translateX(130%); }

.feature .plate {
  position:absolute; left:14px; right:14px; bottom:14px; z-index:2;
  padding:.8rem 1rem;
  background:rgba(8,10,18,.40);
  backdrop-filter:blur(18px) saturate(155%);
  border:1px solid rgba(255,255,255,.17);
  border-radius:13px;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.30), 0 6px 20px rgba(0,0,0,.26);
}
.feature.cover .plate { left:22px; right:22px; bottom:22px; padding:1rem 1.25rem; max-width:70%; }

.feature .kicker  { color:rgba(255,255,255,.88); }
.feature .ft {
  font-family:var(--serif); font-weight:700; color:#fff;
  letter-spacing:-.018em; line-height:1.1; margin:0;
  display:-webkit-box; -webkit-box-orient:vertical; overflow:hidden;
}
.feature.cover .ft  { font-size:2.2rem; -webkit-line-clamp:4; }
.feature.mid .ft    { font-size:1.3rem; -webkit-line-clamp:3; }
.feature.small .ft  { font-size:1.05rem; -webkit-line-clamp:3; }

.feature .fdek {
  color:rgba(255,255,255,.78); font-size:.9rem; line-height:1.5; margin:.45rem 0 0;
  display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;
}
.feature.cover .fdek::first-letter {
  font-family:var(--serif); font-size:2.4em; float:left;
  line-height:.72; padding:.05em .11em 0 0; font-weight:700; color:#fff;
}

/* ── Panel (colour-plate, no photo) ── */
.panel {
  position:relative; display:block; overflow:hidden;
  text-decoration:none; color:var(--ink);
  border-radius:var(--r-lg);
  padding:1rem 1.2rem;
  border:1px solid var(--rule);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.07), var(--shadow);
  background:
    linear-gradient(148deg, color-mix(in srgb, var(--c) 14%, transparent), transparent 58%),
    var(--card);
}
.panel.cover { min-height:420px; }
.panel.mid   { min-height:260px; }
.panel.small { min-height:180px; }
.panel.read  { opacity:.48; }
.panel::after {
  content:""; position:absolute; inset:0; pointer-events:none; border-radius:inherit;
  background:linear-gradient(115deg,transparent 38%,
    color-mix(in srgb, var(--c) 16%, transparent) 50%,transparent 62%);
  transform:translateX(-130%); transition:transform .9s ease;
}
.panel:hover::after { transform:translateX(130%); }
.panel .kicker { color:var(--c); }
.panel .pt {
  font-family:var(--serif); font-weight:700;
  letter-spacing:-.015em; line-height:1.13; margin:0; color:var(--ink);
  display:-webkit-box; -webkit-box-orient:vertical; overflow:hidden;
}
.panel.cover .pt  { font-size:2rem;   -webkit-line-clamp:5; }
.panel.mid .pt    { font-size:1.35rem;-webkit-line-clamp:4; }
.panel.small .pt  { font-size:1.05rem;-webkit-line-clamp:4; }
.panel .pdek {
  color:var(--ink-2); font-size:.9rem; line-height:1.5; margin:.45rem 0 0;
  display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden;
}

/* ── Standard card (small, bordered) ── */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div .cardlink) {
  background:var(--card) !important;
  border:1px solid var(--rule) !important;
  border-radius:var(--r) !important;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.06), var(--shadow);
  transition:transform .15s ease, box-shadow .15s ease;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(> div .cardlink):hover {
  transform:translateY(-2px);
  box-shadow: 0 14px 32px rgba(0,0,0,.18);
}
.cardlink { display:block; text-decoration:none; color:inherit; }
.cardlink.read { opacity:.44; }

/* img-wrap: stacks placeholder and real image, shows placeholder if img errors */
.img-wrap {
  position:relative; width:100%; aspect-ratio:16/10;
  border-radius:9px; overflow:hidden;
}
.img-wrap .ph {
  position:absolute; inset:0;
  display:grid; place-items:center;
  color:#fff; font-weight:800; font-size:1.25rem;
}
.img-wrap .over {
  position:absolute; inset:0;
  width:100%; height:100%; object-fit:cover;
  border-radius:9px;
}
.img-wrap .over.broken { display:none; }

/* thumb variant for mobile lead cards */
.thumb-wrap {
  position:relative; width:78px; height:64px;
  border-radius:8px; overflow:hidden; flex:none;
}
.thumb-wrap .ph {
  position:absolute; inset:0;
  display:grid; place-items:center;
  color:#fff; font-weight:800; font-size:1.1rem;
}
.thumb-wrap .over {
  position:absolute; inset:0;
  width:100%; height:100%; object-fit:cover;
}
.thumb-wrap .over.broken { display:none; }

.cardlink .accent { height:3px; width:32px; border-radius:3px; margin:.1rem 0 .42rem; }
.ctitle {
  font-family:var(--serif); font-weight:700; font-size:.97rem;
  line-height:1.3; letter-spacing:-.01em; color:var(--ink); margin:.52rem 0 0;
  display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden;
}

/* ── Mobile strip (horizontal scroll per section) ── */
.strip-wrap {
  overflow-x: auto;
  overflow-y: visible;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
  margin: 0 -1rem;
  padding: 0 1rem .5rem;
}
.strip-wrap::-webkit-scrollbar { display: none; }

.strip {
  display: flex;
  gap: .75rem;
  width: max-content;
  padding-bottom: .25rem;
}

/* Strip card — tall portrait tile */
.scard {
  display: flex;
  flex-direction: column;
  width: 200px;
  flex-shrink: 0;
  border-radius: var(--r);
  overflow: hidden;
  text-decoration: none;
  color: var(--ink);
  background: var(--card);
  border: 1px solid var(--rule);
  box-shadow: var(--shadow);
  transition: transform .18s ease;
}
.scard:hover { transform: translateY(-3px); }
.scard.read  { opacity: .45; }

/* Image area — 16:10 top */
.scard .simg {
  position: relative;
  width: 200px;
  height: 125px;
  flex-shrink: 0;
  overflow: hidden;
}
.scard .simg .ph {
  position: absolute; inset: 0;
  display: grid; place-items: center;
  color: #fff; font-weight: 800; font-size: 1.4rem;
}
.scard .simg .over {
  position: absolute; inset: 0;
  width: 100%; height: 100%; object-fit: cover;
}
.scard .simg .over.broken { display: none; }

/* Text body */
.scard .sbody {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: .65rem .75rem .6rem;
}
.scard .skicker {
  display: flex; align-items: center; gap: .32rem;
  font-size: .6rem; font-weight: 800; letter-spacing: .06em;
  text-transform: uppercase; color: var(--ink-3);
  margin-bottom: .3rem;
}
.scard .skicker .sico {
  width: 13px; height: 13px; border-radius: 3px;
  display: inline-grid; place-items: center;
  color: #fff; font-size: .42rem; font-weight: 800; flex: none;
}
.scard .skicker .sago { color: var(--ink-3); }
.scard .st {
  font-family: var(--serif); font-weight: 700;
  font-size: .88rem; line-height: 1.28;
  color: var(--ink); flex: 1;
  display: -webkit-box; -webkit-line-clamp: 4;
  -webkit-box-orient: vertical; overflow: hidden;
}
.scard .ssave {
  align-self: flex-end;
  margin-top: .5rem;
  font-size: .65rem; font-weight: 600;
  color: var(--ink-3); background: none;
  border: none; cursor: pointer; padding: 0;
}
.scard .ssave.saved { color: var(--gold); }

/* ── Save button ── */
[data-testid="stMain"] .stButton { display:flex; justify-content:flex-end; margin-top:.32rem; }
[data-testid="stMain"] .stButton > button {
  width:auto; min-height:0; font-size:.71rem; font-weight:600;
  padding:.2rem .58rem; border-radius:999px;
}

/* ── Empty / more ── */
.empty { text-align:center; color:var(--ink-2); padding:4rem 1rem; }
.empty .big { font-family:var(--serif); font-size:1.35rem; color:var(--ink); font-weight:700; margin-bottom:.4rem; }
.more { text-align:center; color:var(--ink-3); font-size:.77rem; padding:1.5rem 0 .5rem; }

/* ── Column height balance ── */
[data-testid="stColumn"] { display:flex; }
[data-testid="stColumn"] > [data-testid="stVerticalBlockBorderWrapper"] { width:100%; height:100%; }
[data-testid="stColumn"] > [data-testid="stVerticalBlockBorderWrapper"] > div,
[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] { height:100%; display:flex; flex-direction:column; }
[data-testid="stColumn"] [data-testid="stVerticalBlockBorderWrapper"]
  [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:last-child,
[data-testid="stColumn"] > div[data-testid="stVerticalBlock"]
  > [data-testid="stElementContainer"]:last-child { margin-top:auto; }
</style>
"""
st.html(CSS)


# ─────────────────────────────────────────────────────────────────────────────
# Load config + state
# ─────────────────────────────────────────────────────────────────────────────
feeds, calm   = load_feeds()
starred_set   = load_state()
all_sources   = [s for items in feeds.values() for s, _ in items]

# ─────────────────────────────────────────────────────────────────────────────
# Layout mode (mobile / desktop) — stored in session state
# ─────────────────────────────────────────────────────────────────────────────
if "layout" not in st.session_state:
    st.session_state.layout = "desktop"

def set_layout(mode):
    st.session_state.layout = mode

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.html('<div class="brand"><div class="mark">✦</div><div class="name">Aurora</div></div>')

    st.html('<div class="sidebar-cap">Library</div>')
    view = st.radio("Library", SMART + list(feeds.keys()), label_visibility="collapsed")

    if view == CALM_VIEW:
        view_sources = [s for s in calm if s in all_sources]
    elif view in (TODAY, ALL):
        view_sources = all_sources
    else:
        view_sources = [s for s, _ in feeds.get(view, [])]

    st.html('<div class="sidebar-cap">Source</div>')
    source = st.selectbox("Source", [ALL_SOURCES, *view_sources], label_visibility="collapsed")

    with st.expander("⚙︎  Manage feeds"):
        st.caption("Add a feed")
        nf_name = st.text_input("Name",    key="nf_name", placeholder="e.g. Wired")
        nf_url  = st.text_input("RSS URL", key="nf_url",  placeholder="https://…/feed")
        fold_opts  = list(feeds.keys()) + ["➕ New folder…"]
        nf_fold    = st.selectbox("Folder", fold_opts, key="nf_fold")
        nf_newfold = st.text_input("New folder name", key="nf_newfold") if nf_fold == "➕ New folder…" else ""
        if st.button("Add feed", key="add_feed", use_container_width=True):
            folder = (nf_newfold or "").strip() if nf_fold == "➕ New folder…" else nf_fold
            if nf_name.strip() and nf_url.strip() and folder:
                feeds.setdefault(folder, [])
                if not any(u == nf_url.strip() for _, u in feeds[folder]):
                    feeds[folder].append((nf_name.strip(), nf_url.strip()))
                    save_feeds(feeds, calm); fetch.clear(); st.rerun()
            else:
                st.warning("Name, URL and folder are required.")

        st.divider()
        st.caption("Remove a feed")
        labels = [f"{fold}  —  {nm}" for fold, items in feeds.items() for nm, _ in items]
        if labels:
            rm = st.selectbox("Feed", labels, key="rm_pick", label_visibility="collapsed")
            if st.button("Remove", key="rm_feed", use_container_width=True):
                rfold, rname = [x.strip() for x in rm.split("—", 1)]
                feeds[rfold] = [(n, u) for n, u in feeds[rfold] if n != rname]
                if not feeds[rfold]:
                    del feeds[rfold]
                calm = [c for c in calm if c in [n for it in feeds.values() for n, _ in it]]
                save_feeds(feeds, calm); fetch.clear(); st.rerun()

        st.divider()
        st.caption("Calm feeds (read-at-leisure)")
        new_calm = st.multiselect(
            "Calm sources", all_sources,
            default=[c for c in calm if c in all_sources],
            key="calm_pick", label_visibility="collapsed",
        )
        if set(new_calm) != set(calm):
            save_feeds(feeds, new_calm); st.rerun()

    if st.button("↻  Refresh", use_container_width=True):
        fetch.clear(); st.rerun()

    # ── Layout toggle — pinned at the bottom ──
    st.html('<div class="sidebar-cap">Layout</div>')
    is_desktop = st.session_state.layout == "desktop"
    lc1, lc2 = st.columns(2, gap="small")
    with lc1:
        if st.button("🖥  Desktop", use_container_width=True,
                     type="primary" if is_desktop else "secondary"):
            set_layout("desktop"); st.rerun()
    with lc2:
        if st.button("📱  Mobile", use_container_width=True,
                     type="primary" if not is_desktop else "secondary"):
            set_layout("mobile"); st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Gather + filter articles
# ─────────────────────────────────────────────────────────────────────────────
calm_set = set(calm)
if view == CALM_VIEW:
    targets = tuple((n, u, folder) for folder, items in feeds.items()
                    for n, u in items if n in calm_set)
elif view in (TODAY, ALL):
    targets = tuple((n, u, folder) for folder, items in feeds.items() for n, u in items)
else:
    targets = tuple((n, u, view) for n, u in feeds.get(view, []))

with st.spinner("Fetching…"):
    articles = fetch(targets)

if view == TODAY:
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    articles = [a for a in articles if a["time"] and a["time"] >= cutoff]

# Deduplicate
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
if   5 <= _h < 12:  _pre = "Good morning,"
elif 12 <= _h < 18: _pre = "Good afternoon,"
elif 18 <= _h < 23: _pre = "Good evening,"
else:               _pre = "Still up,"

title_txt = source if source != ALL_SOURCES else view
dateline  = _now.strftime("%A %-d %B %Y")

st.html(
    f'<div class="greet">'
    f'<span class="greet-pre">{_pre}</span> '
    f'<span class="greet-name">{html.escape(USER_NAME)}</span>'
    f'</div>'
    f'<div class="masthead-meta">'
    f'{html.escape(title_txt)} &nbsp;·&nbsp; {dateline}'
    f' &nbsp;·&nbsp; {len(articles)} stories &nbsp;·&nbsp; {saved_n} saved'
    f'</div>'
    f'<div class="masthead-rule"></div>'
)

col_show, col_search = st.columns([1, 3], gap="small")
with col_show:
    show = st.segmented_control("Show", ["All", "Saved"], default="All",
                                label_visibility="collapsed") or "All"
with col_search:
    query = st.text_input("Search", placeholder="Search headlines…",
                          label_visibility="collapsed")

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
            f'<span class="dot">·</span>'
            f'<span class="ago">{relative(a["time"])}</span>{star}</div>')


def _chip(a):
    star = '<span class="star">★</span>' if a["id"] in starred_set else ""
    return (f'<div class="chip">{icon_html(a["source"])}'
            f'<span>{html.escape(a["source"])}</span>'
            f'<span class="ago">· {relative(a["time"])}</span>{star}</div>')


def feature_html(a, size="mid"):
    img = (a["image"] or "").replace("'", "%27")
    dek = ""
    if size == "cover" and a["summary"]:
        dek = f'<div class="fdek">{html.escape(a["summary"][:220])}</div>'
    return (
        f'<a class="feature {size}" href="{html.escape(a["link"], quote=True)}"'
        f' target="_blank" rel="noopener noreferrer">'
        f'<div class="bg" style="background-color:{color_for(a["source"])};'
        f'background-image:url(\'{html.escape(img, quote=True)}\')"></div>'
        f'<div class="plate">{_kicker(a)}'
        f'<div class="ft">{html.escape(a["title"])}</div>{dek}</div></a>'
    )


def panel_html(a, size="mid"):
    dek = f'<div class="pdek">{html.escape(a["summary"][:240])}</div>' if a["summary"] else ""
    return (
        f'<a class="panel {size}" href="{html.escape(a["link"], quote=True)}"'
        f' target="_blank" rel="noopener noreferrer"'
        f' style="--c:{color_for(a["source"])}">'
        f'{_kicker(a)}'
        f'<div class="pt">{html.escape(a["title"])}</div>{dek}</a>'
    )


def img_with_fallback(img_url, color, inits, css_class="media"):
    """
    Renders image with an always-in-DOM colour-plate fallback.
    The real img sits on top (position:absolute); when it errors,
    JS adds class 'broken' which hides it, revealing the plate below.
    """
    img      = html.escape(img_url, quote=True)
    wrap_cls = "thumb-wrap" if css_class == "thumb" else "img-wrap"
    on_err   = "this.classList.add('broken')"
    return (
        f'<div class="{wrap_cls}">'
        f'<div class="ph" style="background:{color}">{inits}</div>'
        f'<img class="over" src="{img}" loading="lazy" onerror="{on_err}">'
        f'</div>'
    )


def card_html(a):
    link  = html.escape(a["link"], quote=True)
    title = html.escape(a["title"])
    src   = a["source"]
    color = color_for(src)
    inits = html.escape(initials(src))
    if a["image"]:
        media = img_with_fallback(a["image"], color, inits, css_class="media")
        return (f'<a class="cardlink" href="{link}" target="_blank" rel="noopener noreferrer">'
                f'{media}<div class="ctitle">{title}</div>{_chip(a)}</a>')
    accent = f'<div class="accent" style="background:{color}"></div>'
    return (f'<a class="cardlink text" href="{link}" target="_blank" rel="noopener noreferrer">'
            f'{accent}<div class="ctitle">{title}</div>{_chip(a)}</a>')


def mobile_card_html(a, lead=False):
    link   = html.escape(a["link"], quote=True)
    title  = html.escape(a["title"])
    src    = a["source"]
    color  = color_for(src)
    inits  = html.escape(initials(src))
    src_e  = html.escape(src)
    star   = "<span class='star'>&#9733;</span>" if a["id"] in starred_set else ""
    kicker = (f'<div class="kicker" style="color:{color}">'
              f'{icon_html(src)}'
              f'<span>{src_e}</span>'
              f'<span class="dot">&middot;</span>'
              f'<span class="ago">{relative(a["time"])}</span>'
              f'{star}</div>')
    if lead and a["image"]:
        thumb = img_with_fallback(a["image"], color, inits, css_class="thumb")
        return (f'<a class="mcard-lead" href="{link}" target="_blank" rel="noopener noreferrer">'
                f'{thumb}'
                f'<div class="body">{kicker}'
                f'<div class="mt">{title}</div></div></a>')
    return (f'<a class="mcard" href="{link}" target="_blank" rel="noopener noreferrer">'
            f'{kicker}<div class="mt">{title}</div></a>')



def actions(a):
    is_star = a["id"] in starred_set
    st.button("★ Saved" if is_star else "☆ Save",
              key=f"s_{a['id']}", on_click=toggle_star, args=(a["id"],))


def section_header(label):
    st.html(f'<div class="section-rule">'
            f'<span class="label">{html.escape(label)}</span>'
            f'<span class="line"></span></div>')


# ─────────────────────────────────────────────────────────────────────────────
# Desktop layout helpers
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
    """
    Layout for one section (folder) in desktop view.
    5 diverse articles, variable card sizes:
      - Article 0: full-width cover (large)
      - Articles 1-2: side-by-side medium tiles
      - Articles 3-4: row of 2 small cards
    """
    items = diverse_section(folder_items)
    if not items:
        return

    # Card 0 — cover
    render_big(items[0], size="cover" if is_first else "mid")
    st.write("")

    # Cards 1-2 — medium pair (if we have them)
    if len(items) >= 3:
        c1, c2 = st.columns(2, gap="medium")
        with c1: render_big(items[1], size="mid")
        with c2: render_big(items[2], size="mid")
        st.write("")

    # Cards 3-4 — small trio or pair
    tail = items[3:]
    if tail:
        cols = st.columns(len(tail), gap="medium")
        for col, a in zip(cols, tail):
            with col: render_small(a)
        st.write("")


# ─────────────────────────────────────────────────────────────────────────────
# Mobile layout helpers — horizontal strip
# ─────────────────────────────────────────────────────────────────────────────
def strip_card_html(a):
    """Single card inside the horizontal strip."""
    link   = html.escape(a["link"], quote=True)
    title  = html.escape(a["title"])
    src    = a["source"]
    color  = color_for(src)
    inits  = html.escape(initials(src))
    src_e  = html.escape(src)
    ago    = relative(a["time"])
    on_err = "this.classList.add('broken')"

    # Image or colour plate
    if a["image"]:
        img_url = html.escape(a["image"], quote=True)
        img_block = (
            f'<div class="simg">'
            f'<div class="ph" style="background:{color}">{inits}</div>'
            f'<img class="over" src="{img_url}" loading="lazy" onerror="{on_err}">'
            f'</div>'
        )
    else:
        img_block = (
            f'<div class="simg">'
            f'<div class="ph" style="background:{color}">{inits}</div>'
            f'</div>'
        )

    return (
        f'<a class="scard" href="{link}" target="_blank" rel="noopener noreferrer">'
        f'{img_block}'
        f'<div class="sbody">'
        f'<div class="skicker">'
        f'<span class="sico" style="background:{color}">{inits}</span>'
        f'<span>{src_e}</span>'
        f'<span class="sago">&middot; {ago}</span>'
        f'</div>'
        f'<div class="st">{title}</div>'
        f'</div></a>'
    )


def render_section_mobile(folder_items):
    """Horizontal scrolling strip of cards per section."""
    items = diverse_section(folder_items)
    if not items:
        return

    cards_html = "".join(strip_card_html(a) for a in items)
    st.html(
        f'<div class="strip-wrap">'
        f'<div class="strip">{cards_html}</div>'
        f'</div>'
    )


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
            section_header(folder)
            if mobile_mode:
                render_section_mobile(folder_items)
            else:
                render_section_desktop(folder_items, is_first=(idx == 0))

    else:
        # Single-folder / single-source: classic magazine rhythm on desktop,
        # horizontal strip on mobile
        if mobile_mode:
            cards_html = "".join(strip_card_html(a) for a in items)
            st.html(
                '<div class="strip-wrap">'
                f'<div class="strip">{cards_html}</div>'
                '</div>'
            )
        else:
            cover = next((a for a in items if a["image"]), items[0])
            rest  = [a for a in items if a is not cover]

            render_big(cover, size="cover")
            st.write("")

            pattern = ["trio", "trio", "band", "trio", "pair", "trio"]
            i, p, n = 0, 0, len(rest)
            while i < n:
                block = pattern[p % len(pattern)]
                p += 1
                left  = n - i
                if left <= 2:
                    if left == 1:
                        render_big(rest[i])
                    else:
                        c1, c2 = st.columns(2, gap="medium")
                        with c1: render_small(rest[i])
                        with c2: render_small(rest[i + 1])
                    i += left
                    break
                if block == "band":
                    render_big(rest[i]); i += 1
                elif block == "pair":
                    chunk = rest[i:i + 2]; i += 2
                    c1, c2 = st.columns(2, gap="medium")
                    with c1: render_big(chunk[0])
                    with c2: render_big(chunk[1])
                else:
                    chunk = rest[i:i + 3]; i += 3
                    cols  = st.columns(3, gap="medium")
                    for k, a in enumerate(chunk):
                        with cols[k]: render_small(a)
                st.write("")

    if len(articles) > DISPLAY_LIMIT:
        st.html(
            f'<div class="more">Showing {DISPLAY_LIMIT} of {len(articles)} stories. '
            f'Pick a folder or search to go deeper.</div>'
        )
