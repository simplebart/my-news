"""
Aurora — a personal news hub
A Streamlit RSS reader art-directed like a magazine, with an Apple "Liquid Glass" feel.

Run with:  streamlit run aurora_reader.py

• Editorial layout: a cinematic cover story, then an alternating rhythm of wide
  feature tiles, stacked cards, and colour-washed text panels.
• All controls are native, so tabs/folders/sources/save/read update in place —
  no reload, no new tab, no flash. Only tapping a story opens your browser.
• Light / dark follows macOS automatically.
• Feeds live in feeds.json; read/saved state in aurora_state.json (beside this file).
"""

import hashlib
import html
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import feedparser
import streamlit as st

# ----------------------------------------------------------------------------
# Defaults (seed feeds.json on first run)
# ----------------------------------------------------------------------------
DEFAULT_FEEDS = {
    "Culture": [
        ("1843", "https://www.economist.com/1843/rss.xml"),
        ("Monocle", "https://monocle.com/feed/"),
        ("The New Yorker", "https://www.newyorker.com/feed/everything"),
    ],
    "Europe": [
        ("Euractiv", "https://www.euractiv.com/feed/"),
        ("Foreign Policy", "https://foreignpolicy.com/feed/"),
        ("POLITICO Europe", "https://www.politico.eu/feed/"),
    ],
    "Finances": [
        ("Financial Times", "https://www.ft.com/markets?format=rss"),
        ("The Economist", "https://www.economist.com/finance-and-economics/rss.xml"),
        ("Les Echos", "https://services.lesechos.fr/rss/les-echos-finance-marches.xml"),
    ],
    "Tech": [
        ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
        ("TechCrunch", "https://techcrunch.com/feed/"),
        ("The Verge", "https://www.theverge.com/rss/index.xml"),
    ],
    "Sport": [
        ("The Athletic", "https://theathletic.com/rss-feed/"),
        ("BBC Sport Football", "https://feeds.bbci.co.uk/sport/football/rss.xml"),
        ("NOS Sport", "https://feeds.nos.nl/nossportalgemeen"),
    ],
    "Food & Travel": [
        ("Condé Nast Traveller", "https://www.cntraveller.com/feed/rss"),
        ("Fool.nl", "https://www.fool.nl/feed/"),
        ("LOST iS FOUND", "https://lostisfound.com/feed/"),
    ],
    "Arts": [
        ("Dezeen", "https://www.dezeen.com/feed/"),
        ("It's Nice That", "https://www.itsnicethat.com/rss"),
        ("De Volkskrant Cultuur", "https://www.volkskrant.nl/cultuur-media/rss.xml"),
    ],
}
DEFAULT_CALM = ["1843", "Monocle", "The New Yorker", "Foreign Policy",
                "LOST iS FOUND", "It's Nice That"]

ACCENTS = {
    "1843": "#E3120B", "Monocle": "#C8A45C", "The New Yorker": "#2E6FB7",
    "Euractiv": "#E8B400", "Foreign Policy": "#8C1D40", "POLITICO Europe": "#D11B1F",
    "Financial Times": "#0F5499", "The Economist": "#E3120B", "Les Echos": "#00457C",
    "Ars Technica": "#FF4E00", "TechCrunch": "#00B84D", "The Verge": "#7C3AED",
    "The Athletic": "#000000", "BBC Sport Football": "#FF4B00", "NOS Sport": "#CC0000",
    "Condé Nast Traveller": "#C9A96E", "Fool.nl": "#E63B2E", "LOST iS FOUND": "#4A9B8E",
    "Dezeen": "#000000", "It's Nice That": "#FF3B2F", "De Volkskrant Cultuur": "#CC0000",
}

ALL, TODAY, CALM, ALL_SOURCES = "All Articles", "Today", "Calm Feeds", "All sources"
SMART = [TODAY, ALL, CALM]
DISPLAY_LIMIT = 60

# Shown in the greeting at the top — change to your name.
USER_NAME = "Bart"

HERE = os.path.dirname(os.path.abspath(__file__))
FEEDS_PATH = os.path.join(HERE, "feeds.json")
STATE_PATH = os.path.join(HERE, "aurora_state.json")


# ----------------------------------------------------------------------------
# Persistence
# ----------------------------------------------------------------------------
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
            json.dump({"feeds": {k: [list(p) for p in v] for k, v in feeds.items()}, "calm": calm}, f, indent=2)
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
    s = load_state(); (s.discard if i in s else s.add)(i); save_state(s)


# ----------------------------------------------------------------------------
# Source identity
# ----------------------------------------------------------------------------
def color_for(name):
    if name in ACCENTS:
        return ACCENTS[name]
    h = int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16)
    return f"hsl({h % 360},58%,52%)"


def initials(name):
    parts = [p for p in re.split(r"\s+", name) if p]
    if not parts:
        return "?"
    return parts[0][:2].upper() if len(parts) == 1 else (parts[0][0] + parts[1][0]).upper()


def icon_html(name):
    return f'<span class="ico" style="background:{color_for(name)}">{html.escape(initials(name))}</span>'


# ----------------------------------------------------------------------------
# Fetch + parse
# ----------------------------------------------------------------------------
TAG_RE = re.compile(r"<[^>]+>")
IMG_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)', re.IGNORECASE)


def clean_text(raw):
    return " ".join(html.unescape(TAG_RE.sub(" ", raw or "")).split())


def extract_image(entry):
    media = entry.get("media_thumbnail") or entry.get("media_content")
    if media and media[0].get("url"):
        return media[0]["url"]
    for link in entry.get("links", []):
        if link.get("type", "").startswith("image"):
            return link.get("href")
    blob = (entry["content"][0].get("value", "") if entry.get("content") else "") + entry.get("summary", "")
    m = IMG_RE.search(blob)
    return m.group(1) if m else None


def entry_time(entry):
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime.fromtimestamp(time.mktime(t), tz=timezone.utc)
    return None


def _fetch_one(name_url):
    name, url = name_url
    out = []
    try:
        for e in feedparser.parse(url).entries:
            out.append({
                "source": name,
                "title": clean_text(e.get("title", "Untitled")),
                "link": e.get("link", "#"),
                "summary": clean_text(e.get("summary", "")),
                "image": extract_image(e),
                "time": entry_time(e),
            })
    except Exception:
        pass
    return out


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
    if diff < 60:
        return "now"
    if diff < 3600:
        return f"{int(diff // 60)}m ago"
    if diff < 86400:
        return f"{int(diff // 3600)}h ago"
    if diff < 7 * 86400:
        return f"{int(diff // 86400)}d ago"
    return dt.strftime("%d %b")


# ----------------------------------------------------------------------------
# Page + style
# ----------------------------------------------------------------------------
st.set_page_config(page_title="Aurora", page_icon="✦", layout="wide", initial_sidebar_state="expanded")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&family=Inter:wght@400;500;600;700;800&display=swap');
:root{
  --bg:#080b13; --panel:rgba(255,255,255,.045); --card:rgba(255,255,255,.055);
  --ink:#f3f3f7; --ink-2:rgba(235,235,245,.62); --ink-3:rgba(235,235,245,.34);
  --hair:rgba(255,255,255,.12); --sel:rgba(255,255,255,.10);
  --shadow:0 14px 36px rgba(0,0,0,.34); --accent:#0a84ff; --gold:#F5C85C; --aurora:.55;
  --serif:'Fraunces',Georgia,'Times New Roman',serif;
  --sans:-apple-system,'SF Pro Text',BlinkMacSystemFont,'Inter','Segoe UI',Roboto,sans-serif;
}
@media (prefers-color-scheme: light){
  :root{
    --bg:#fbfbfd; --panel:#f4f4f7; --card:#ffffff; --ink:#1d1d1f; --ink-2:#6e6e73; --ink-3:#a1a1a8;
    --hair:#e6e6eb; --sel:#e7e7ee; --shadow:0 8px 24px rgba(0,0,0,.07); --accent:#007aff; --aurora:0;
  }
}
html, body, .stApp{ background:var(--bg); font-family:var(--sans); color:var(--ink); }
.stApp::before{
  content:""; position:fixed; inset:-30vmax; z-index:0; pointer-events:none; opacity:var(--aurora);
  background:
    radial-gradient(40vmax 40vmax at 14% 14%, rgba(95,92,255,.55), transparent 60%),
    radial-gradient(34vmax 34vmax at 88% 12%, rgba(232,92,180,.42), transparent 60%),
    radial-gradient(42vmax 42vmax at 78% 92%, rgba(58,214,196,.40), transparent 62%);
  filter: blur(42px) saturate(132%); animation: drift 30s ease-in-out infinite alternate;
}
@keyframes drift{ 0%{transform:translate3d(0,0,0) scale(1);} 100%{transform:translate3d(-2.5%,2.5%,0) scale(1.06);} }
@media (prefers-reduced-motion: reduce){ .stApp::before{animation:none;} }

header[data-testid="stHeader"]{ background:transparent; }
#MainMenu, footer{ display:none; }
[data-testid="stAppViewContainer"], [data-testid="stMain"], [data-testid="stMainBlockContainer"]{ background:transparent !important; }
[data-testid="stMainBlockContainer"]{ padding-top:1.8rem; max-width:1120px; z-index:1; }

/* sidebar */
[data-testid="stSidebar"]{ background:var(--panel) !important; border-right:1px solid var(--hair);
  backdrop-filter:blur(26px) saturate(150%); -webkit-backdrop-filter:blur(26px) saturate(150%); }
[data-testid="stSidebar"] *{ color:var(--ink); }
.brand{ display:flex; align-items:center; gap:.55rem; padding:.1rem 0 .3rem; }
.brand .mark{ width:30px;height:30px;border-radius:9px;display:grid;place-items:center;font-size:16px;color:#fff;
  background:linear-gradient(135deg,#6E7BFF,#E85CC8 55%,#3FD6C8);
  box-shadow:0 4px 14px rgba(120,90,255,.45), inset 0 1px 0 rgba(255,255,255,.5); }
.brand .name{ font-family:var(--serif); font-weight:600; font-size:1.3rem; letter-spacing:-.01em; }
.cap{ font-size:.7rem; letter-spacing:.10em; text-transform:uppercase; color:var(--ink-3); font-weight:700; margin:.9rem .1rem -.2rem; }

/* native widgets */
.stButton button, .stDownloadButton button{ border-radius:9px; border:1px solid var(--hair); background:var(--card);
  color:var(--ink); font-weight:600; font-size:.78rem; padding:.3rem .5rem; transition:all .14s ease; }
.stButton button:hover{ background:var(--sel); }
[data-testid="stTextInput"] input{ background:var(--card) !important; color:var(--ink) !important;
  border:1px solid var(--hair) !important; border-radius:12px !important; }
[data-testid="stTextInput"] input::placeholder{ color:var(--ink-3) !important; }
[data-baseweb="select"] > div{ background:var(--card) !important; border-color:var(--hair) !important; border-radius:10px !important; }
[data-testid="stRadio"] label{ font-size:.93rem; }

/* time-of-day greeting */
.greet{ display:flex; align-items:center; gap:.65rem; margin:.1rem 0 .55rem; }
.greet .gtext{ font-family:var(--serif); font-size:2.7rem; font-weight:600; letter-spacing:-.02em; line-height:1; }
.greet .gpre{ background:linear-gradient(120deg, var(--ga), var(--gb)); -webkit-background-clip:text;
  background-clip:text; -webkit-text-fill-color:transparent; }
.greet .gname{ color:var(--ink); }
.greet .orb{ width:20px; height:20px; border-radius:50%; flex:none; }
.greet.tod-morning{ --ga:#FFC76B; --gb:#FF8FA3; }
.greet.tod-afternoon{ --ga:#7CC7FF; --gb:#5B8CFF; }
.greet.tod-evening{ --ga:#FF9E5E; --gb:#B65CC8; }
.greet.tod-night{ --ga:#9A8CFF; --gb:#4FD6C8; }
.greet:not(.tod-night) .orb{ background:radial-gradient(circle at 34% 30%, var(--ga), var(--gb));
  box-shadow:0 0 18px color-mix(in srgb, var(--gb) 55%, transparent); }
.greet.tod-night .orb{ background:transparent;
  box-shadow:inset -6px -3px 0 0 var(--ga), 0 0 16px color-mix(in srgb, var(--ga) 50%, transparent); }

/* edition header */
.edhead .section{ font-family:var(--serif); font-size:2.7rem; font-weight:600; letter-spacing:-.015em; line-height:1; color:var(--ink); }
.edhead .dateline{ text-transform:uppercase; letter-spacing:.14em; font-size:.7rem; font-weight:700; color:var(--ink-3); margin-top:.1rem; }
.edhead .dateline b{ color:var(--ink-2); }
.edhead .rule{ height:1px; margin-top:.7rem; background:linear-gradient(90deg, var(--hair) 0%, var(--hair) 40%, transparent 100%); }

/* shared kicker + chip */
.kicker{ display:flex; align-items:center; gap:.45rem; text-transform:uppercase; letter-spacing:.08em;
  font-size:.68rem; font-weight:800; margin-bottom:.5rem; }
.kicker .dot{ opacity:.5; } .kicker .ago{ opacity:.8; font-weight:700; letter-spacing:.04em; }
.kicker .star{ color:var(--gold); }
.ico{ width:18px;height:18px;border-radius:5px;flex:none;display:inline-grid;place-items:center;
  color:#fff;font-size:.5rem;font-weight:800; box-shadow:inset 0 1px 0 rgba(255,255,255,.3); }
.chip{ display:flex; align-items:center; gap:.4rem; font-size:.75rem; color:var(--ink-2); font-weight:600; margin-top:.5rem; }
.chip .ago{ color:var(--ink-3); font-weight:500; } .chip .star{ color:var(--gold); margin-left:.2rem; }

/* ---- COVER / FEATURE: headline on a frosted glass plate over the photo ---- */
.feature{ position:relative; display:block; border-radius:18px; overflow:hidden; text-decoration:none;
  box-shadow:var(--shadow); min-height:240px; isolation:isolate; }
.feature.cover{ min-height:460px; }
.feature.read{ opacity:.55; }
.feature .bg{ position:absolute; inset:0; background-size:cover; background-position:center; z-index:0;
  transition:transform .7s cubic-bezier(.2,.7,.2,1); }
.feature:hover .bg{ transform:scale(1.06); }
.feature::after{ content:""; position:absolute; inset:0; z-index:3; pointer-events:none; border-radius:inherit;
  background:linear-gradient(115deg, transparent 36%, rgba(255,255,255,.16) 48%, transparent 62%);
  transform:translateX(-130%); transition:transform .85s ease; }
.feature:hover::after{ transform:translateX(130%); }
.feature .plate{ position:absolute; left:14px; right:14px; bottom:14px; z-index:2; padding:.85rem 1rem;
  background:rgba(14,14,20,.30); backdrop-filter:blur(22px) saturate(165%); -webkit-backdrop-filter:blur(22px) saturate(165%);
  border:1px solid rgba(255,255,255,.22); border-radius:15px;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.42), 0 10px 26px rgba(0,0,0,.30); }
.feature.cover .plate{ left:20px; right:20px; bottom:20px; padding:1.05rem 1.25rem; max-width:74%; }
.feature .kicker{ color:#fff; margin-bottom:.45rem; }
.feature .kicker .ico{ box-shadow:inset 0 1px 0 rgba(255,255,255,.4); }
.feature .ft{ font-family:var(--serif); font-weight:600; color:#fff; letter-spacing:-.01em; line-height:1.08; margin:0;
  display:-webkit-box; -webkit-box-orient:vertical; overflow:hidden; }
.feature .ft{ font-size:1.4rem; -webkit-line-clamp:3; }
.feature.cover .ft{ font-size:2.5rem; -webkit-line-clamp:4; }
.feature .fdek{ color:rgba(255,255,255,.86); font-size:.95rem; line-height:1.5; margin:.55rem 0 0;
  display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
.feature.cover .fdek::first-letter{ font-family:var(--serif); font-size:2.5em; float:left; line-height:.72;
  padding:.06em .12em 0 0; font-weight:600; color:#fff; }

/* ---- TEXT PANEL (no image, colour-washed glass) ---- */
.panel{ position:relative; display:block; overflow:hidden; text-decoration:none; color:var(--ink); border-radius:18px;
  padding:1.15rem 1.3rem; border:1px solid var(--hair); box-shadow:inset 0 1px 0 rgba(255,255,255,.10), var(--shadow); min-height:200px;
  background:linear-gradient(150deg, color-mix(in srgb, var(--c) 22%, transparent), transparent 64%), var(--card); }
.panel.read{ opacity:.55; }
.panel::after{ content:""; position:absolute; inset:0; pointer-events:none; border-radius:inherit;
  background:linear-gradient(115deg, transparent 36%, color-mix(in srgb, var(--c) 22%, transparent) 48%, transparent 62%);
  transform:translateX(-130%); transition:transform .85s ease; }
.panel:hover::after{ transform:translateX(130%); }
.panel .kicker{ color:var(--c); }
.panel .pt{ font-family:var(--serif); font-weight:600; letter-spacing:-.01em; line-height:1.12; margin:0; color:var(--ink);
  display:-webkit-box; -webkit-box-orient:vertical; overflow:hidden; -webkit-line-clamp:4; }
.panel .pt{ font-size:1.5rem; } .panel.cover .pt{ font-size:2.3rem; -webkit-line-clamp:4; }
.panel .pdek{ color:var(--ink-2); font-size:.95rem; line-height:1.5; margin:.55rem 0 0;
  display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }

/* ---- STANDARD / COMPACT cards (bordered container) ---- */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div .cardlink){
  background:var(--card); border:1px solid var(--hair) !important; border-radius:15px;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.10), var(--shadow);
  transition:transform .16s ease, box-shadow .16s ease; }
[data-testid="stVerticalBlockBorderWrapper"]:has(> div .cardlink):hover{ transform:translateY(-2px); box-shadow:0 18px 38px rgba(0,0,0,.16); }
.cardlink{ display:block; text-decoration:none; color:inherit; }
.cardlink.read{ opacity:.5; }
.cardlink .media{ width:100%; aspect-ratio:16/10; object-fit:cover; border-radius:10px; display:block; }
.cardlink.compact .media{ aspect-ratio:16/9; }
.cardlink .ph{ display:grid; place-items:center; color:#fff; font-weight:800; font-size:1.4rem; }
.cardlink .accent{ height:4px; width:40px; border-radius:3px; margin:.1rem 0 .5rem; }
.ctitle{ font-weight:750; font-size:1rem; line-height:1.27; letter-spacing:-.012em; color:var(--ink); margin:.6rem 0 0;
  display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }
.cardlink.compact .ctitle{ font-size:.93rem; -webkit-line-clamp:2; }
.cardlink.text .ctitle{ font-family:var(--serif); font-weight:600; font-size:1.22rem; -webkit-line-clamp:4; margin-top:.1rem; }
.cardlink.text.compact .ctitle{ font-size:1.05rem; -webkit-line-clamp:3; }

.empty{ text-align:center; color:var(--ink-2); padding:3.5rem 1rem; }
.empty .big{ font-family:var(--serif); font-size:1.4rem; color:var(--ink); font-weight:600; margin-bottom:.4rem; }
.more{ text-align:center; color:var(--ink-3); font-size:.8rem; padding:1.6rem 0 .6rem; }

/* balance columns: every card fills its row height; actions sit at the bottom */
[data-testid="stColumn"]{ display:flex; }
[data-testid="stColumn"] > [data-testid="stVerticalBlockBorderWrapper"]{ width:100%; height:100%; }
[data-testid="stColumn"] > [data-testid="stVerticalBlockBorderWrapper"] > div,
[data-testid="stColumn"] > div[data-testid="stVerticalBlock"]{ height:100%; display:flex; flex-direction:column; }
[data-testid="stColumn"] [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:last-child,
[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:last-child{ margin-top:auto; }
.cardlink .ctitle{ margin-bottom:.1rem; }

/* compact Save button, pinned bottom-right of each article (main area only) */
[data-testid="stMain"] .stButton{ display:flex; justify-content:flex-end; margin-top:.4rem; }
[data-testid="stMain"] .stButton > button{ width:auto; min-height:0; font-size:.74rem; font-weight:600;
  padding:.26rem .66rem; border-radius:999px; }
</style>
"""
st.html(CSS)

# ----------------------------------------------------------------------------
# Load config + state
# ----------------------------------------------------------------------------
feeds, calm = load_feeds()
starred_set = load_state()
all_sources = [s for items in feeds.values() for s, _ in items]

# ----------------------------------------------------------------------------
# Sidebar
# ----------------------------------------------------------------------------
with st.sidebar:
    st.html('<div class="brand"><div class="mark">✦</div><div class="name">Aurora</div></div>')

    st.html('<div class="cap">Library</div>')
    view = st.radio("Library", SMART + list(feeds.keys()), label_visibility="collapsed")

    if view == CALM:
        view_sources = [s for s in calm if s in all_sources]
    elif view in (TODAY, ALL):
        view_sources = all_sources
    else:
        view_sources = [s for s, _ in feeds.get(view, [])]

    st.html('<div class="cap">Source</div>')
    source = st.selectbox("Source", [ALL_SOURCES, *view_sources], label_visibility="collapsed")

    with st.expander("⚙︎  Manage feeds"):
        st.caption("Add a feed")
        nf_name = st.text_input("Name", key="nf_name", placeholder="e.g. Wired")
        nf_url = st.text_input("RSS URL", key="nf_url", placeholder="https://…/feed")
        fold_opts = list(feeds.keys()) + ["➕ New folder…"]
        nf_fold = st.selectbox("Folder", fold_opts, key="nf_fold")
        nf_newfold = st.text_input("New folder name", key="nf_newfold") if nf_fold == "➕ New folder…" else ""
        if st.button("Add feed", key="add_feed", use_container_width=True):
            folder = (nf_newfold or "").strip() if nf_fold == "➕ New folder…" else nf_fold
            if nf_name.strip() and nf_url.strip() and folder:
                feeds.setdefault(folder, [])
                if not any(u == nf_url.strip() for _, u in feeds[folder]):
                    feeds[folder].append((nf_name.strip(), nf_url.strip()))
                    save_feeds(feeds, calm); fetch.clear(); st.rerun()
            else:
                st.warning("Name, URL and folder are all required.")

        st.divider()
        st.caption("Remove a feed")
        labels = [f"{fold}  —  {nm}" for fold, items in feeds.items() for nm, _ in items]
        if labels:
            rm = st.selectbox("Feed", labels, key="rm_pick", label_visibility="collapsed")
            if st.button("Remove", key="rm_feed", use_container_width=True):
                rfold, rname = [x.strip() for x in rm.split("—")]
                feeds[rfold] = [(n, u) for n, u in feeds[rfold] if n != rname]
                if not feeds[rfold]:
                    del feeds[rfold]
                calm = [c for c in calm if c in [n for it in feeds.values() for n, _ in it]]
                save_feeds(feeds, calm); fetch.clear(); st.rerun()

        st.divider()
        st.caption("Calm Feeds (read-at-leisure lane)")
        new_calm = st.multiselect("Calm sources", all_sources, default=[c for c in calm if c in all_sources],
                                  key="calm_pick", label_visibility="collapsed")
        if set(new_calm) != set(calm):
            save_feeds(feeds, new_calm); st.rerun()

    if st.button("↻  Refresh feeds", use_container_width=True):
        fetch.clear(); st.rerun()

# ----------------------------------------------------------------------------
# Gather + filter
# ----------------------------------------------------------------------------
if view == CALM:
    targets = tuple((n, u) for items in feeds.values() for n, u in items if n in set(calm))
elif view in (TODAY, ALL):
    targets = tuple((n, u) for items in feeds.values() for n, u in items)
else:
    targets = tuple(feeds.get(view, []))

with st.spinner("Gathering the latest…"):
    articles = fetch(targets)

if view == TODAY:
    today = datetime.now().date()
    articles = [a for a in articles if a["time"] and a["time"].astimezone().date() == today]

for a in articles:
    a["id"] = aid(a["link"])

seen, deduped = set(), []
for a in articles:
    if a["id"] in seen:
        continue
    seen.add(a["id"]); deduped.append(a)
articles = deduped

if source != ALL_SOURCES:
    articles = [a for a in articles if a["source"] == source]

saved_n = sum(1 for a in articles if a["id"] in starred_set)

# ----------------------------------------------------------------------------
# Masthead + Show switch + search
# ----------------------------------------------------------------------------
title_txt = source if source != ALL_SOURCES else view
_now = datetime.now()
dateline = f"{_now:%A} {_now.day} {_now:%B %Y}"
_h = _now.hour
if 5 <= _h < 12:
    _pre, _suf, _tod = "Good morning,", "", "morning"
elif 12 <= _h < 18:
    _pre, _suf, _tod = "Good afternoon,", "", "afternoon"
elif 18 <= _h < 23:
    _pre, _suf, _tod = "Good evening,", "", "evening"
else:
    _pre, _suf, _tod = "Still up,", "?", "night"
st.html(
    f'<div class="greet tod-{_tod}"><span class="orb"></span>'
    f'<span class="gtext"><span class="gpre">{_pre}</span> '
    f'<span class="gname">{html.escape(USER_NAME)}</span>{_suf}</span></div>'
    f'<div class="edhead"><div class="dateline"><b>{html.escape(title_txt)}</b> &nbsp;·&nbsp; {dateline} '
    f'&nbsp;·&nbsp; <b>{len(articles)}</b> stories &nbsp;·&nbsp; <b>{saved_n}</b> saved</div>'
    f'<div class="rule"></div></div>')

show = st.segmented_control("Show", ["All", "Starred"], default="All", label_visibility="collapsed") or "All"
query = st.text_input("Search", placeholder="Search headlines and summaries…", label_visibility="collapsed")

if show == "Starred":
    articles = [a for a in articles if a["id"] in starred_set]
if query:
    q = query.lower()
    articles = [a for a in articles if q in a["title"].lower() or q in a["summary"].lower()]


# ----------------------------------------------------------------------------
# Visual builders
# ----------------------------------------------------------------------------
def _kicker(a):
    star = ' <span class="star">★</span>' if a["id"] in starred_set else ""
    return (f'<div class="kicker">{icon_html(a["source"])}<span>{html.escape(a["source"])}</span>'
            f'<span class="dot">·</span><span class="ago">{relative(a["time"])}</span>{star}</div>')


def _chip(a):
    star = '<span class="star">★</span>' if a["id"] in starred_set else ""
    return (f'<div class="chip">{icon_html(a["source"])}{html.escape(a["source"])}'
            f'<span class="ago">· {relative(a["time"])}</span>{star}</div>')


def feature_html(a, cover=False):
    img = (a["image"] or "").replace("'", "%27")
    cv = " cover" if cover else ""
    dek = f'<div class="fdek">{html.escape(a["summary"][:200])}</div>' if cover and a["summary"] else ""
    return (f'<a class="feature{cv}" href="{html.escape(a["link"], quote=True)}" target="_blank" rel="noopener noreferrer">'
            f'<div class="bg" style="background-color:{color_for(a["source"])};background-image:url(\'{html.escape(img, quote=True)}\')"></div>'
            f'<div class="plate">{_kicker(a)}'
            f'<div class="ft">{html.escape(a["title"])}</div>{dek}</div></a>')


def panel_html(a, cover=False):
    cv = " cover" if cover else ""
    dek = f'<div class="pdek">{html.escape(a["summary"][:240])}</div>'
    return (f'<a class="panel{cv}" href="{html.escape(a["link"], quote=True)}" target="_blank" rel="noopener noreferrer" '
            f'style="--c:{color_for(a["source"])}">{_kicker(a)}'
            f'<div class="pt">{html.escape(a["title"])}</div>{dek}</a>')


def small_html(a, compact=False):
    cp = " compact" if compact else ""
    link = html.escape(a["link"], quote=True)
    if a["image"]:
        img = html.escape(a["image"], quote=True)
        ph = f"<div class='media ph' style='background:{color_for(a['source'])}'>{html.escape(initials(a['source']))}</div>"
        media = f'<img class="media" src="{img}" loading="lazy" onerror="this.outerHTML=&quot;{ph}&quot;">'
        return (f'<a class="cardlink{cp}" href="{link}" target="_blank" rel="noopener noreferrer">'
                f'{media}<div class="ctitle">{html.escape(a["title"])}</div>{_chip(a)}</a>')
    accent = f'<div class="accent" style="background:{color_for(a["source"])}"></div>'
    return (f'<a class="cardlink text{cp}" href="{link}" target="_blank" rel="noopener noreferrer">'
            f'{accent}<div class="ctitle">{html.escape(a["title"])}</div>{_chip(a)}</a>')


def actions(a):
    is_star = a["id"] in starred_set
    st.button("★ Saved" if is_star else "☆ Save", key=f"s_{a['id']}", on_click=toggle_star, args=(a["id"],))


def big(a, cover=False):
    """A wide tile: photo-overlay feature, or colour-washed text panel."""
    with st.container(border=False):
        st.html(feature_html(a, cover) if a["image"] else panel_html(a, cover))
        actions(a)


def small(a, compact=False):
    with st.container(border=True):
        st.html(small_html(a, compact))
        actions(a)


# ----------------------------------------------------------------------------
# Render — editorial rhythm
# ----------------------------------------------------------------------------
if not articles:
    msg = {
        "Starred": "No saved stories yet. Tap Save on anything you want to keep.",
    }.get(show, "Nothing to show. Try another view, clear the search, or refresh.")
    st.html(f'<div class="empty"><div class="big">Nothing here</div>{msg}</div>')
else:
    items = articles[:DISPLAY_LIMIT]
    cover = next((a for a in items if a["image"]), items[0])  # cover prefers a photo
    rest = [a for a in items if a is not cover]

    st.write("")
    big(cover, cover=True)
    st.write("")

    # Even 3-up rows keep columns balanced; a full-width feature band adds rhythm
    # without leaving a gap (it has no neighbour). No more mismatched 2-1 splits.
    pattern = ["trio", "trio", "band", "trio", "pair", "trio"]
    i, p, n = 0, 0, len(rest)
    while i < n:
        block = pattern[p % len(pattern)]
        p += 1
        left = n - i

        if left <= 2:  # tidy finish: 1 band, or a balanced pair
            if left == 1:
                big(rest[i])
            else:
                c1, c2 = st.columns(2, gap="medium")
                with c1:
                    small(rest[i])
                with c2:
                    small(rest[i + 1])
            i += left
            break

        if block == "band":
            big(rest[i]); i += 1
        elif block == "pair":
            chunk = rest[i:i + 2]; i += 2
            c1, c2 = st.columns(2, gap="medium")
            with c1:
                big(chunk[0])
            with c2:
                big(chunk[1])
        else:  # trio
            chunk = rest[i:i + 3]; i += 3
            cols = st.columns(3, gap="medium")
            for k, a in enumerate(chunk):
                with cols[k]:
                    small(a)
        st.write("")

    if len(articles) > DISPLAY_LIMIT:
        st.html(f'<div class="more">Showing the {DISPLAY_LIMIT} most recent of {len(articles)}. '
                    f"Pick a source or search to see more.</div>")
