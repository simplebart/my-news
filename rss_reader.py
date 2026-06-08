import streamlit as st
import requests
import xml.etree.ElementTree as ET
import re
import os
import hashlib
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone, timedelta
from collections import defaultdict

try:
    os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]
except Exception:
    os.environ.setdefault("GEMINI_API_KEY", "JOUW_KEY_HIER")

st.set_page_config(page_title="My News", layout="wide", page_icon="🗞️")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:ital,opsz,wght@0,14..32,300;0,14..32,400;0,14..32,500;0,14..32,600;0,14..32,700;0,14..32,800&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

/* ── Achtergrond ── */
.main, div[data-testid="stAppViewContainer"] { background: #070c18; }
div[data-testid="stMain"] { background: #070c18; }

/* ── Sidebar ── */
div[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #060b16 0%, #0a1220 100%);
    border-right: 1px solid #111e35;
}
div[data-testid="stSidebar"] .stCheckbox label { color: #8899b4 !important; font-size: 12px !important; font-weight: 500 !important; }
div[data-testid="stSidebar"] .stTextInput input { background: #0a1628 !important; border: 1px solid #162035 !important; border-radius: 8px !important; color: #c8d8f0 !important; font-size: 12px !important; }
div[data-testid="stSidebar"] .stTextInput label, div[data-testid="stSidebar"] .stSlider label { color: #2a3d5a !important; font-size: 10px !important; font-weight: 700 !important; text-transform: uppercase !important; letter-spacing: 1px !important; }
div[data-testid="stSidebar"] hr { border-color: #111e35 !important; margin: 10px 0 !important; }

/* Sidebar vernieuwen knop */
div[data-testid="stSidebar"] .stButton button {
    background: linear-gradient(135deg, #1a3a6b, #0f2448) !important;
    border: 1px solid #1e3a6b !important;
    color: #7aa8e0 !important;
    border-radius: 8px !important;
    font-size: 12px !important;
    font-weight: 600 !important;
    padding: 6px 12px !important;
}
div[data-testid="stSidebar"] .stButton button:hover {
    background: linear-gradient(135deg, #1e4080, #1a3060) !important;
    color: #a0c4f8 !important;
}

/* ── Header ── */
.app-header {
    padding: 24px 0 20px 0;
    border-bottom: 1px solid #111e35;
    margin-bottom: 20px;
}
.app-title {
    font-size: 32px; font-weight: 800; color: #f0f6ff;
    letter-spacing: -1px; line-height: 1;
    background: linear-gradient(135deg, #e2eaf6, #7aa8e0);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.app-sub { font-size: 12px; color: #4a6a8a; margin-top: 4px; font-weight: 500; letter-spacing: 0.3px; }

/* ── Zoekbalk ── */
div[data-testid="stTextInput"] input {
    background: #0a1628 !important;
    border: 1px solid #162035 !important;
    border-radius: 10px !important;
    color: #c8d8f0 !important;
    font-size: 13px !important;
    padding: 10px 14px !important;
}
div[data-testid="stTextInput"] input:focus {
    border-color: #2563eb !important;
    box-shadow: 0 0 0 3px #2563eb15 !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 1px solid #111e35 !important;
    gap: 0 !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: #2a3d5a !important;
    font-size: 12px !important;
    font-weight: 600 !important;
    padding: 8px 16px !important;
    border-radius: 0 !important;
    border-bottom: 2px solid transparent !important;
}
.stTabs [aria-selected="true"] {
    color: #7aa8e0 !important;
    border-bottom: 2px solid #2563eb !important;
    background: transparent !important;
}

/* ── Topic headers ── */
.topic-header {
    font-size: 13px; font-weight: 700; color: #5a7a9a;
    text-transform: uppercase; letter-spacing: 1.5px;
    margin: 32px 0 16px 0;
    display: flex; align-items: center; gap: 8px;
}
.topic-header::after {
    content: ''; flex: 1; height: 1px;
    background: linear-gradient(90deg, #111e35, transparent);
}

/* ── Artikel kaart ── */
.card-wrap {
    background: #0e1a2d;
    border: 1px solid #111e35;
    border-radius: 14px;
    overflow: hidden;
    margin-bottom: 14px;
    transition: border-color 0.15s, box-shadow 0.15s;
    display: flex;
    flex-direction: column;
    height: 100%;
}
.card-wrap:hover {
    border-color: #1e3a6b;
    box-shadow: 0 4px 24px #0008;
}
.card-body {
    padding: 14px 16px 10px 16px;
    display: flex;
    flex-direction: column;
    flex: 1;
}
.card-summary {
    flex: 1;
}
.card-footer-row {
    margin-top: auto;
}

/* Gelijke kolomhoogte */
div[data-testid="stHorizontalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"],
div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
    height: 100% !important;
}
div[data-testid="stHorizontalBlock"] > div[data-testid="column"] > div {
    height: 100% !important;
    display: flex;
    flex-direction: column;
}
.card-source {
    font-size: 10px; font-weight: 700; color: #4a90d9;
    text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px;
}
.card-title {
    font-size: 15px; font-weight: 600; color: #f0f6ff;
    line-height: 1.45; margin-bottom: 8px;
}
.card-title.dimmed { color: #3a5070 !important; }
.card-summary { font-size: 12px; color: #7a9cc0; line-height: 1.65; margin-bottom: 10px; }
.card-footer-row {
    display: flex; align-items: center; gap: 8px;
    border-top: 1px solid #1a2e45; padding-top: 8px; margin-top: 4px;
}
.card-date { font-size: 11px; color: #4a6a8a; }
.card-link { font-size: 11px; color: #5a9fd8; text-decoration: none; font-weight: 600; letter-spacing: 0.2px; }
.card-link:hover { color: #7aa8e0; }
.read-time { font-size: 10px; color: #4a6a8a; background: #0f1e35; border-radius: 4px; padding: 2px 6px; }

/* ── Tags ── */
.tag { display: inline-block; background: #0f2040; color: #6a9fd8; border-radius: 5px; padding: 2px 7px; font-size: 10px; font-weight: 700; margin-right: 4px; margin-bottom: 4px; letter-spacing: 0.3px; }
.saved-tag { display: inline-block; background: #0f2a0f; color: #2e8b2e; border-radius: 5px; padding: 2px 7px; font-size: 10px; font-weight: 700; }

/* ── Tijdlijn kaart ── */
.tl-wrap {
    background: #0e1a2d;
    border: 1px solid #111e35;
    border-radius: 12px;
    padding: 12px 16px;
    margin-bottom: 8px;
    transition: border-color 0.15s;
}
.tl-wrap:hover { border-color: #1e3a6b; }
.tl-title { font-size: 14px; font-weight: 600; color: #f0f6ff; line-height: 1.4; margin-bottom: 5px; }
.tl-title.dimmed { color: #3a5070 !important; }
.tl-meta { font-size: 11px; color: #5a7a9a; line-height: 1.6; }
.tl-badge { background: #0f2040; color: #6a9fd8; border-radius: 5px; padding: 2px 7px; font-size: 10px; font-weight: 700; }

/* ── Inline knoppen ── */
.stButton button {
    background: #0f2040 !important;
    border: 1px solid #1e3a6b !important;
    color: #7aa8e0 !important;
    border-radius: 6px !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    padding: 4px 10px !important;
    min-height: 0 !important;
    line-height: 1.4 !important;
}
.stButton button:hover {
    background: #1a3a6b !important;
    border-color: #2563eb !important;
    color: #c8e0ff !important;
}

.search-result-count { font-size: 12px; color: #2a3d5a; margin-bottom: 16px; }

/* ── Lijstweergave ── */
.list-row {
    padding: 14px 0;
    border-bottom: 1px solid #111e35;
}
.list-meta {
    font-size: 11px; color: #2a3d5a; margin-bottom: 5px;
    font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;
}
.list-title {
    font-size: 16px; font-weight: 600; line-height: 1.45;
    text-decoration: none; display: block; margin-bottom: 5px;
}
.list-title:hover { color: #7aa8e0 !important; }
.list-summary {
    font-size: 13px; color: #5a7a9a; line-height: 1.6;
}
</style>
""", unsafe_allow_html=True)

# ── Feeds ─────────────────────────────────────────────────────────────────────
TOPICS = {
    "💹 Financiën & Markten": {
        "CNBC Finance":    "https://www.cnbc.com/id/10000664/device/rss/rss.html",
        "Reuters Business":"https://feeds.reuters.com/reuters/businessNews",
        "Investing.com":   "https://investing.com/rss/news.rss",
        "Yahoo Finance":   "https://finance.yahoo.com/news/rss",
        "Business Insider":"https://feeds.businessinsider.com/custom/all",
        "FT":              "https://www.ft.com/rss/home",
    },
    "🌐 Geopolitiek": {
        "Reuters World":   "https://feeds.reuters.com/reuters/worldNews",
        "BBC World":       "http://feeds.bbci.co.uk/news/world/rss.xml",
        "Politico Europe": "https://www.politico.eu/feed/",
        "Foreign Affairs": "https://www.foreignaffairs.com/rss.xml",
    },
    "💻 Tech & AI": {
        "The Verge": "https://www.theverge.com/rss/index.xml",
        "FT Tech":   "https://www.ft.com/technology?format=rss",
    },
    "📊 Economics": {
        "The Economist":    "https://www.economist.com/rss.xml",
        "BBC Business":     "http://feeds.bbci.co.uk/news/business/rss.xml",
        "Euronews Business":"https://www.euronews.com/rss?format=mrss&level=vertical&name=business",
    },
}

# ── Session state ─────────────────────────────────────────────────────────────
if "saved" not in st.session_state:
    st.session_state.saved = {}   # {article_id: article_dict}
if "read" not in st.session_state:
    st.session_state.read = set()  # set of article_ids

# ── Helpers ───────────────────────────────────────────────────────────────────
def clean_xml(text):
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

def strip_html(text):
    if not text:
        return ""
    text = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>') \
               .replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')
    return re.sub(r'\s+', ' ', text).strip()

def article_id(a):
    return hashlib.md5((a.get("link","") + a.get("title","")).encode()).hexdigest()[:10]

def relative_time(pub_raw):
    try:
        dt = parsedate_to_datetime(pub_raw)
        now = datetime.now(timezone.utc)
        diff = now - dt
        mins = int(diff.total_seconds() / 60)
        if mins < 1:   return "zojuist"
        if mins < 60:  return f"{mins} min geleden"
        hours = mins // 60
        if hours < 24: return f"{hours} uur geleden"
        days = hours // 24
        if days == 1:  return "gisteren"
        return f"{days} dagen geleden"
    except Exception:
        return ""

def read_time(text):
    words = len((text or "").split())
    mins = max(1, round(words / 200))
    return f"{mins} min"

def fmt_date(raw):
    try:
        return parsedate_to_datetime(raw).strftime("%d %b, %H:%M")
    except Exception:
        return raw[:16] if raw else ""

def sort_key(a):
    try:
        return parsedate_to_datetime(a["pub_raw"])
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)

def get_tags(title, summary, keywords):
    text = (title + " " + summary).lower()
    return [kw for kw in keywords if kw.lower() in text]

def esc(text):
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def dedup(articles, threshold=0.6):
    """Remove near-duplicate articles based on title similarity."""
    seen_titles = []
    unique = []
    for a in articles:
        title_words = set(a["title"].lower().split())
        is_dup = False
        for seen in seen_titles:
            if len(title_words) == 0 or len(seen) == 0:
                continue
            overlap = len(title_words & seen) / max(len(title_words), len(seen))
            if overlap > threshold:
                is_dup = True
                break
        if not is_dup:
            unique.append(a)
            seen_titles.append(title_words)
    return unique

@st.cache_data(ttl=60, show_spinner=False)
def fetch(source, url):
    try:
        r = requests.get(url, timeout=8, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Cache-Control": "no-cache", "Pragma": "no-cache",
        })
        r.encoding = r.apparent_encoding
        root = ET.fromstring(clean_xml(r.text).encode("utf-8"))
        ns = {"atom": "http://www.w3.org/2005/Atom", "media": "http://search.yahoo.com/mrss/"}
        channel = root.find("channel") or root
        out = []
        for item in (channel.findall("item") or root.findall("atom:entry", ns))[:12]:
            link = item.findtext("link", "")
            if not link:
                el = item.find("atom:link", ns)
                link = el.get("href", "#") if el is not None else "#"
            pub = item.findtext("pubDate") or item.findtext("atom:published", "", ns) or ""
            desc_el = item.find("description") or item.find("atom:summary", ns)
            summary = " ".join(desc_el.itertext()) if desc_el is not None else ""
            img = ""
            for tag, attr in [("media:thumbnail", "url"), ("media:content", "url")]:
                el = item.find(tag, ns)
                if el is not None:
                    img = el.get(attr, "")
                    break
            if not img:
                enc = item.find("enclosure")
                if enc is not None and "image" in (enc.get("type") or ""):
                    img = enc.get("url", "")
            title = strip_html(item.findtext("title") or item.findtext("atom:title", "", ns) or "")
            summary_clean = strip_html(summary)[:240]
            out.append({
                "source": source, "title": title, "link": link.strip(),
                "date": relative_time(pub), "date_full": fmt_date(pub),
                "pub_raw": pub, "summary": summary_clean,
                "img": img, "tags": [],
                "read_time": read_time(summary_clean),
            })
        return out
    except Exception:
        return []

# ── Settings via session state ───────────────────────────────────────────────
if "active_topics" not in st.session_state:
    st.session_state.active_topics = {t: True for t in TOPICS}
if "custom_name" not in st.session_state:
    st.session_state.custom_name = ""
if "custom_url" not in st.session_state:
    st.session_state.custom_url = ""
if "max_items" not in st.session_state:
    st.session_state.max_items = 5
if "keywords" not in st.session_state:
    st.session_state.keywords = []
if "show_dupes" not in st.session_state:
    st.session_state.show_dupes = False
if "active_category" not in st.session_state:
    st.session_state.active_category = list(TOPICS.keys())[0]

active_topics = st.session_state.active_topics
custom_name   = st.session_state.custom_name
custom_url    = st.session_state.custom_url
max_items     = st.session_state.max_items
keywords      = st.session_state.keywords
show_dupes    = st.session_state.show_dupes

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style='padding:16px 0 12px 0'>
        <div style='font-size:20px;font-weight:800;color:#f0f6ff;letter-spacing:-0.5px'>🗞️ My News</div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("<hr style='border:none;border-top:1px solid #1a2744;margin:0 0 16px 0'>", unsafe_allow_html=True)
    st.markdown("<div style='font-size:10px;font-weight:700;color:#2a3d5a;text-transform:uppercase;letter-spacing:1px;margin-bottom:10px'>Categorieën</div>", unsafe_allow_html=True)

    for topic in TOPICS:
        if not st.session_state.active_topics.get(topic, True):
            continue
        is_active = st.session_state.active_category == topic
        bg = "#1a3a6b" if is_active else "#0e1a2d"
        border = "#2563eb" if is_active else "#111e35"
        color = "#c8e0ff" if is_active else "#5a7a9a"
        if st.button(topic, key=f"nav_{topic}", use_container_width=True):
            st.session_state.active_category = topic
            st.rerun()
        # Style the last button
        st.markdown(f"""<style>
        div[data-testid="stSidebar"] div[data-testid="stButton"]:has(button[kind="secondary"]) button {{
            text-align: left !important;
        }}
        </style>""", unsafe_allow_html=True)

    st.markdown("<hr style='border:none;border-top:1px solid #1a2744;margin:16px 0 12px 0'>", unsafe_allow_html=True)
    if st.button("🔄 Vernieuwen", use_container_width=True, key="refresh_btn"):
        st.cache_data.clear()
        st.rerun()

# ── Data laden ────────────────────────────────────────────────────────────────
all_articles = []
topic_articles = defaultdict(list)
sources_to_load = []

for topic, feeds in TOPICS.items():
    if active_topics.get(topic):
        for src, url in feeds.items():
            sources_to_load.append((topic, src, url))
if custom_url and custom_name:
    sources_to_load.append(("➕ Eigen", custom_name, custom_url))

bar = st.progress(0, text="Nieuws ophalen…")
for i, (topic, src, url) in enumerate(sources_to_load):
    arts = fetch(src, url)[:max_items]
    for a in arts:
        a["tags"] = get_tags(a["title"], a["summary"], keywords)
        a["id"] = article_id(a)
    topic_articles[topic].extend(arts)
    all_articles.extend(arts)
    bar.progress((i+1)/len(sources_to_load), text=f"{src}…")
bar.empty()

# Duplicaten verwijderen
if not show_dupes:
    all_articles = dedup(all_articles)
    for t in topic_articles:
        topic_articles[t] = dedup(topic_articles[t])

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(f'<div class="app-header"><div class="app-title">My News</div><div class="app-sub">{len(all_articles)} artikelen &nbsp;·&nbsp; {len(sources_to_load)} bronnen &nbsp;·&nbsp; {datetime.now().strftime("%d %B %Y, %H:%M")}</div></div>', unsafe_allow_html=True)

# ── Zoekbalk ──────────────────────────────────────────────────────────────────
search = st.text_input("", placeholder="🔍  Zoek in alle artikelen…")
if search:
    q = search.lower()
    all_articles = [a for a in all_articles if q in a["title"].lower() or q in a["summary"].lower()]
    for t in topic_articles:
        topic_articles[t] = [a for a in topic_articles[t] if q in a["title"].lower() or q in a["summary"].lower()]
    st.markdown(f'<div class="search-result-count">{len(all_articles)} resultaten voor "<b>{search}</b>"</div>', unsafe_allow_html=True)
# ── Kaart renderers ───────────────────────────────────────────────────────────
def _img_tag(url, h=175):
    if not url:
        return ""
    return '<img src="' + esc(url) + f'" style="width:100%;height:{h}px;object-fit:cover;display:block" onerror="this.parentElement.style.display=\'none\'">'

def _tl_img_tag(url):
    if not url:
        return ""
    return '<img src="' + esc(url) + '" style="width:90px;height:68px;object-fit:cover;border-radius:8px;flex-shrink:0" onerror="this.style.display=\'none\'">'

def _save_read_buttons(aid, is_saved, is_read, prefix):
    c1, c2 = st.columns([1, 1])
    with c1:
        lbl = "✅ Bewaard" if is_saved else "🔖 Bewaar"
        if st.button(lbl, key=f"{prefix}_save_{aid}"):
            if is_saved: del st.session_state.saved[aid]
            else: st.session_state.saved[aid] = a
            st.rerun()
    with c2:
        lbl2 = "↩ Ongelezen" if is_read else "👁 Gelezen"
        if st.button(lbl2, key=f"{prefix}_read_{aid}"):
            if is_read: st.session_state.read.discard(aid)
            else: st.session_state.read.add(aid)
            st.rerun()

def render_card(a, prefix="c"):
    aid = a.get("id", "")
    is_read = aid in st.session_state.read
    is_saved = aid in st.session_state.saved
    dim = " dimmed" if is_read else ""
    tags_html = "".join([f'<span class="tag">{esc(t)}</span>' for t in a.get("tags", [])])
    saved_html = ' <span class="saved-tag">🔖</span>' if is_saved else ""
    meta_line = f'{esc(a["source"])} · {esc(a["date"])} · <span class="read-time">📖 {a["read_time"]}</span>{saved_html}'
    parts = [
        f'<div class="card-wrap">',
        _img_tag(a.get("img", "")),
        f'<div class="card-body">',
        f'<div class="card-source">{meta_line}</div>',
        f'<div class="card-title{dim}">{esc(a["title"])}</div>',
        f'<div style="margin-bottom:8px">{tags_html}</div>' if tags_html else "",
        f'<div class="card-summary">{esc(a["summary"])}</div>' if a.get("summary") else "",
        f'<div class="card-footer-row"><a class="card-link" href="{esc(a["link"])}" target="_blank">Lees meer →</a></div>',
        '</div></div>',
    ]
    st.markdown("".join(parts), unsafe_allow_html=True)
    _save_read_buttons(aid, is_saved, is_read, prefix)

def render_tl_card(a, prefix="t"):
    aid = a.get("id", "")
    is_read = aid in st.session_state.read
    is_saved = aid in st.session_state.saved
    dim = " dimmed" if is_read else ""
    tags_html = "".join([f'<span class="tag">{esc(t)}</span>' for t in a.get("tags", [])])
    saved_html = ' <span class="saved-tag">🔖</span>' if is_saved else ""
    summary_short = esc(a["summary"][:140]) + ("…" if len(a["summary"]) > 140 else "")
    tags_block = f'<div style="margin-bottom:4px">{tags_html}{saved_html}</div>' if (tags_html or is_saved) else ""
    meta = f'<span class="tl-badge">{esc(a["source"])}</span> · {esc(a["date"])} · <span class="read-time">📖 {a["read_time"]}</span>'
    img_part = _tl_img_tag(a.get("img", ""))
    parts = [
        f'<div class="tl-wrap" style="display:flex;gap:12px;align-items:flex-start">',
        img_part,
        f'<div style="flex:1;min-width:0">',
        f'<a class="card-link" href="{esc(a["link"])}" target="_blank" style="text-decoration:none"><div class="tl-title{dim}">{esc(a["title"])}</div></a>',
        tags_block,
        f'<div class="tl-meta">{summary_short}<br>{meta}</div>',
        '</div></div>',
    ]
    st.markdown("".join(parts), unsafe_allow_html=True)
    _save_read_buttons(aid, is_saved, is_read, prefix)

# ── Tabs ──────────────────────────────────────────────────────────────────────
saved_count = len(st.session_state.saved)
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📂 Per onderwerp", "⏱️ Tijdlijn", "🏷️ Trefwoorden", f"🔖 Opgeslagen ({saved_count})", "⚙️ Instellingen"])

with tab1:
    active_cat = st.session_state.active_category
    arts = topic_articles.get(active_cat, [])
    st.markdown(f'<div class="topic-header">{active_cat}</div>', unsafe_allow_html=True)
    if not arts:
        st.info("Geen artikelen gevonden voor deze categorie.")
    else:
        for j, a in enumerate(arts):
            render_card(a, prefix=f"tab1_{j}")

with tab2:
    st.markdown("<br>", unsafe_allow_html=True)
    for ti, a in enumerate(sorted(all_articles, key=sort_key, reverse=True)):
        render_tl_card(a, prefix=f"tab2_{ti}")

with tab3:
    if not keywords:
        st.info("Voeg trefwoorden toe in de sidebar.")
    else:
        for kw in keywords:
            matched = [a for a in all_articles if kw.lower() in (a["title"] + a["summary"]).lower()]
            if not matched:
                continue
            st.markdown(f'<div class="topic-header">🏷️ {kw} <span style="font-size:13px;color:#475569;">({len(matched)})</span></div><div class="topic-divider"></div>', unsafe_allow_html=True)
            for ki, a in enumerate(sorted(matched, key=sort_key, reverse=True)[:6]):
                render_tl_card(a, prefix=f"tab3_{ki}")

with tab4:
    if not st.session_state.saved:
        st.info("Nog niets opgeslagen. Klik op 🔖 bij een artikel om het te bewaren.")
    else:
        if st.button("🗑️ Alles verwijderen", key="clear_saved"):
            st.session_state.saved = {}
            st.rerun()
        for si, a in enumerate(st.session_state.saved.values()):
            render_tl_card(a, prefix=f"tab4_{si}")

with tab5:
    st.markdown("<br>", unsafe_allow_html=True)

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown("#### 📡 Onderwerpen")
        new_active = {}
        for topic, feeds in TOPICS.items():
            checked = st.checkbox(topic, value=st.session_state.active_topics.get(topic, True), key=f"set_{topic}")
            new_active[topic] = checked
            if checked:
                with st.expander("Bronnen", expanded=False):
                    for src in feeds:
                        st.markdown(f"<span style='color:#5a7a9a;font-size:12px'>· {src}</span>", unsafe_allow_html=True)
        st.session_state.active_topics = new_active

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### 🔁 Overig")
        st.session_state.show_dupes = st.toggle("Duplicaten tonen", value=st.session_state.show_dupes, key="set_dupes")
        st.session_state.max_items = st.slider("Artikelen per bron", 3, 10, st.session_state.max_items, key="set_max")

    with col2:
        st.markdown("#### 🏷️ Trefwoorden volgen")
        kw_str = ", ".join(st.session_state.keywords)
        kw_input = st.text_input("Komma-gescheiden", value=kw_str, placeholder="bijv. AI, ECB, rente…", key="set_kw")
        st.session_state.keywords = [k.strip() for k in kw_input.split(",") if k.strip()] if kw_input else []

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### ➕ Eigen bron toevoegen")
        st.session_state.custom_name = st.text_input("Naam", value=st.session_state.custom_name, placeholder="bijv. FD.nl", key="set_cname")
        st.session_state.custom_url  = st.text_input("RSS URL", value=st.session_state.custom_url, placeholder="https://...", key="set_curl")

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Feeds vernieuwen", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
