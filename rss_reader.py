import streamlit as st
import requests
import xml.etree.ElementTree as ET
import re
import os
import hashlib
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from collections import defaultdict

try:
    os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]
except Exception:
    os.environ.setdefault("GEMINI_API_KEY", "JOUW_KEY_HIER")

st.set_page_config(page_title="My News", layout="wide", page_icon="🗞️")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.main, div[data-testid="stAppViewContainer"], div[data-testid="stMain"] { background: #070c18; }

div[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #060b16 0%, #0a1220 100%);
    border-right: 1px solid #111e35;
}
div[data-testid="stSidebar"] .stButton button {
    background: transparent !important;
    border: none !important;
    border-radius: 8px !important;
    color: #4a6a8a !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    text-align: left !important;
    padding: 8px 12px !important;
    width: 100% !important;
}
div[data-testid="stSidebar"] .stButton button:hover {
    background: #0e1a2d !important;
    color: #c8e0ff !important;
}

/* Zoekbalk */
div[data-testid="stTextInput"] input {
    background: #0a1628 !important;
    border: 1px solid #162035 !important;
    border-radius: 10px !important;
    color: #c8d8f0 !important;
    font-size: 13px !important;
}

/* Tabs */
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
    border-bottom: 2px solid transparent !important;
}
.stTabs [aria-selected="true"] {
    color: #7aa8e0 !important;
    border-bottom: 2px solid #2563eb !important;
    background: transparent !important;
}

/* App header */
.app-title {
    font-size: 28px; font-weight: 800; color: #f0f6ff;
    letter-spacing: -1px; padding: 20px 0 4px 0;
}
.app-sub { font-size: 12px; color: #2a3d5a; margin-bottom: 16px; }

/* Topic header */
.topic-header {
    font-size: 12px; font-weight: 700; color: #2a3d5a;
    text-transform: uppercase; letter-spacing: 1.5px;
    margin: 20px 0 4px 0;
}

/* Google News artikel rij */
.art-row {
    display: flex;
    align-items: flex-start;
    gap: 14px;
    padding: 14px 0;
    border-bottom: 1px solid #0f1e35;
    cursor: pointer;
}
.art-row:hover .art-title { color: #7aa8e0 !important; }
.art-body { flex: 1; min-width: 0; }
.art-source {
    font-size: 11px; font-weight: 600; color: #2563eb;
    text-transform: uppercase; letter-spacing: 0.5px;
    margin-bottom: 4px;
}
.art-title {
    font-size: 15px; font-weight: 600; color: #dde8f8;
    line-height: 1.4; margin-bottom: 5px;
    text-decoration: none; display: block;
    transition: color 0.15s;
}
.art-title.dimmed { color: #2a3d5a !important; }
.art-summary {
    font-size: 12px; color: #4a6a8a; line-height: 1.55;
    margin-bottom: 5px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}
.art-meta { font-size: 11px; color: #1e3050; }
.art-thumb {
    width: 86px; height: 64px;
    object-fit: cover;
    border-radius: 8px;
    flex-shrink: 0;
}
.art-tag {
    display: inline-block; background: #0f2040; color: #4a7fc1;
    border-radius: 4px; padding: 1px 6px; font-size: 10px;
    font-weight: 700; margin-right: 4px;
}
.saved-tag {
    display: inline-block; background: #0f2a0f; color: #2e8b2e;
    border-radius: 4px; padding: 1px 6px; font-size: 10px; font-weight: 700;
}

/* Knoppen */
.stButton button {
    background: #0a1628 !important;
    border: 1px solid #162035 !important;
    color: #5a7a9a !important;
    border-radius: 6px !important;
    font-size: 11px !important;
    padding: 3px 10px !important;
}
.stButton button:hover {
    background: #0f2040 !important;
    border-color: #2563eb !important;
    color: #7aa8e0 !important;
}

.search-result-count { font-size: 12px; color: #2a3d5a; margin-bottom: 12px; }
</style>
""", unsafe_allow_html=True)

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

# Session state
for key, val in [("saved", {}), ("read", set()), ("active_category", list(TOPICS.keys())[0]),
                 ("active_topics", {t: True for t in TOPICS}), ("custom_name", ""),
                 ("custom_url", ""), ("max_items", 5), ("keywords", []), ("show_dupes", False)]:
    if key not in st.session_state:
        st.session_state[key] = val

def clean_xml(t): return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', t)

def strip_html(text):
    if not text: return ""
    text = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = text.replace('&amp;','&').replace('&lt;','<').replace('&gt;','>').replace('&quot;','"').replace('&#39;',"'").replace('&nbsp;',' ')
    return re.sub(r'\s+', ' ', text).strip()

def article_id(a): return hashlib.md5((a.get("link","") + a.get("title","")).encode()).hexdigest()[:10]

def relative_time(pub_raw):
    try:
        dt = parsedate_to_datetime(pub_raw)
        mins = int((datetime.now(timezone.utc) - dt).total_seconds() / 60)
        if mins < 1: return "zojuist"
        if mins < 60: return f"{mins} min geleden"
        h = mins // 60
        if h < 24: return f"{h} uur geleden"
        d = h // 24
        return "gisteren" if d == 1 else f"{d} dagen geleden"
    except: return ""

def read_time(text):
    return f"{max(1, round(len((text or '').split()) / 200))} min"

def sort_key(a):
    try: return parsedate_to_datetime(a["pub_raw"])
    except: return datetime.min.replace(tzinfo=timezone.utc)

def esc(t): return (t or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

def dedup(arts, thr=0.6):
    seen, unique = [], []
    for a in arts:
        words = set(a["title"].lower().split())
        if not any(len(words & s) / max(len(words), len(s), 1) > thr for s in seen):
            unique.append(a)
            seen.append(words)
    return unique

@st.cache_data(ttl=60, show_spinner=False)
def fetch(source, url):
    try:
        r = requests.get(url, timeout=8, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Cache-Control": "no-cache",
        })
        r.encoding = r.apparent_encoding
        root = ET.fromstring(clean_xml(r.text).encode("utf-8"))
        ns = {"atom": "http://www.w3.org/2005/Atom", "media": "http://search.yahoo.com/mrss/"}
        channel = root.find("channel") or root
        out = []
        for item in (channel.findall("item") or root.findall("atom:entry", ns))[:15]:
            link = item.findtext("link", "")
            if not link:
                el = item.find("atom:link", ns)
                link = el.get("href", "#") if el is not None else "#"
            pub = item.findtext("pubDate") or item.findtext("atom:published", "", ns) or ""
            desc_el = item.find("description") or item.find("atom:summary", ns)
            summary = strip_html(" ".join(desc_el.itertext()) if desc_el is not None else "")[:200]
            img = ""
            for tag, attr in [("media:thumbnail","url"),("media:content","url")]:
                el = item.find(tag, ns)
                if el is not None: img = el.get(attr,""); break
            if not img:
                enc = item.find("enclosure")
                if enc is not None and "image" in (enc.get("type") or ""): img = enc.get("url","")
            title = strip_html(item.findtext("title") or item.findtext("atom:title","",ns) or "")
            out.append({"source": source, "title": title, "link": link.strip(),
                        "date": relative_time(pub), "pub_raw": pub,
                        "summary": summary, "img": img,
                        "read_time": read_time(summary), "tags": [], "id": ""})
        return out
    except: return []

# Sidebar
with st.sidebar:
    st.markdown("<div style='padding:16px 0 8px 0;font-size:20px;font-weight:800;color:#f0f6ff'>🗞️ My News</div>", unsafe_allow_html=True)
    st.markdown("<hr style='border:none;border-top:1px solid #111e35;margin:0 0 12px 0'>", unsafe_allow_html=True)
    st.markdown("<div style='font-size:10px;font-weight:700;color:#1e3050;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px'>Categorieën</div>", unsafe_allow_html=True)
    for topic in TOPICS:
        if not st.session_state.active_topics.get(topic, True): continue
        is_sel = st.session_state.active_category == topic
        color = "#c8e0ff" if is_sel else "#4a6a8a"
        bg = "background:#0e1a2d !important;" if is_sel else ""
        st.markdown(f"<style>.btn_{topic.replace(' ','_').replace('&','').replace('/','_')} button{{color:{color} !important;{bg}}}</style>", unsafe_allow_html=True)
        if st.button(topic, key=f"nav_{topic}", use_container_width=True):
            st.session_state.active_category = topic
            st.rerun()
    st.markdown("<hr style='border:none;border-top:1px solid #111e35;margin:12px 0'>", unsafe_allow_html=True)
    if st.button("🔄 Vernieuwen", use_container_width=True, key="refresh"):
        st.cache_data.clear()
        st.rerun()

# Laden
all_articles, topic_articles, sources_to_load = [], defaultdict(list), []
for topic, feeds in TOPICS.items():
    if st.session_state.active_topics.get(topic, True):
        for src, url in feeds.items():
            sources_to_load.append((topic, src, url))
if st.session_state.custom_url and st.session_state.custom_name:
    sources_to_load.append(("➕ Eigen", st.session_state.custom_name, st.session_state.custom_url))

bar = st.progress(0, text="Laden…")
for i, (topic, src, url) in enumerate(sources_to_load):
    arts = fetch(src, url)[:st.session_state.max_items]
    for a in arts:
        a["tags"] = [kw for kw in st.session_state.keywords if kw.lower() in (a["title"]+a["summary"]).lower()]
        a["id"] = article_id(a)
    topic_articles[topic].extend(arts)
    all_articles.extend(arts)
    bar.progress((i+1)/len(sources_to_load), text=f"{src}…")
bar.empty()

if not st.session_state.show_dupes:
    all_articles = dedup(all_articles)
    for t in topic_articles: topic_articles[t] = dedup(topic_articles[t])

# Header
st.markdown(f'<div class="app-title">🗞️ My News</div><div class="app-sub">{len(all_articles)} artikelen · {datetime.now().strftime("%d %B %Y, %H:%M")}</div>', unsafe_allow_html=True)

search = st.text_input("", placeholder="🔍  Zoek in alle artikelen…")
if search:
    q = search.lower()
    all_articles = [a for a in all_articles if q in a["title"].lower() or q in a["summary"].lower()]
    for t in topic_articles: topic_articles[t] = [a for a in topic_articles[t] if q in a["title"].lower() or q in a["summary"].lower()]
    st.markdown(f'<div class="search-result-count">{len(all_articles)} resultaten voor "<b>{search}</b>"</div>', unsafe_allow_html=True)

def render_article(a, prefix="a"):
    aid = a.get("id", "")
    is_read = aid in st.session_state.read
    is_saved = aid in st.session_state.saved
    dim = " dimmed" if is_read else ""
    tags_html = "".join([f'<span class="art-tag">{esc(t)}</span>' for t in a.get("tags", [])])
    saved_html = ' <span class="saved-tag">🔖</span>' if is_saved else ""
    summary = esc(a["summary"][:130]) + ("…" if len(a["summary"]) > 130 else "") if a.get("summary") else ""
    thumb = ""
    if a.get("img"):
        thumb = '<img class="art-thumb" src="' + esc(a["img"]) + '" onerror="this.style.display=\'none\'">'

    html = f'''<div class="art-row">
        <div class="art-body">
            <div class="art-source">{esc(a["source"])} · {esc(a["date"])} · 📖 {a["read_time"]}{saved_html}</div>
            <a class="art-title{dim}" href="{esc(a["link"])}" target="_blank">{esc(a["title"])}</a>
            <div class="art-summary">{summary}</div>
            {('<div style="margin-top:3px">' + tags_html + '</div>') if tags_html else ""}
        </div>
        {thumb}
    </div>'''
    st.markdown(html, unsafe_allow_html=True)
    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("✅ Bewaard" if is_saved else "🔖 Bewaar", key=f"{prefix}_s_{aid}"):
            if is_saved: del st.session_state.saved[aid]
            else: st.session_state.saved[aid] = a
            st.rerun()
    with c2:
        if st.button("↩ Ongelezen" if is_read else "👁 Gelezen", key=f"{prefix}_r_{aid}"):
            if is_read: st.session_state.read.discard(aid)
            else: st.session_state.read.add(aid)
            st.rerun()

# Tabs
saved_count = len(st.session_state.saved)
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📂 Per categorie", "⏱️ Tijdlijn", "🏷️ Trefwoorden", f"🔖 Opgeslagen ({saved_count})", "⚙️ Instellingen"])

with tab1:
    active_cat = st.session_state.active_category
    arts = topic_articles.get(active_cat, [])
    st.markdown(f'<div class="topic-header">{active_cat}</div>', unsafe_allow_html=True)
    if not arts:
        st.info("Geen artikelen gevonden.")
    else:
        cat_key = f"show_count_{active_cat}"
        if cat_key not in st.session_state: st.session_state[cat_key] = 12
        show_n = st.session_state[cat_key]
        for j, a in enumerate(arts[:show_n]):
            render_article(a, prefix=f"t1_{j}")
        if show_n < len(arts):
            if st.button(f"Laad meer ({len(arts)-show_n} resterend)", use_container_width=True):
                st.session_state[cat_key] += 12
                st.rerun()

with tab2:
    for ti, a in enumerate(sorted(all_articles, key=sort_key, reverse=True)):
        render_article(a, prefix=f"t2_{ti}")

with tab3:
    if not st.session_state.keywords:
        st.info("Voeg trefwoorden toe in de instellingen.")
    else:
        for kw in st.session_state.keywords:
            matched = [a for a in all_articles if kw.lower() in (a["title"]+a["summary"]).lower()]
            if matched:
                st.markdown(f'<div class="topic-header">🏷️ {kw} ({len(matched)})</div>', unsafe_allow_html=True)
                for ki, a in enumerate(sorted(matched, key=sort_key, reverse=True)[:8]):
                    render_article(a, prefix=f"t3_{kw}_{ki}")

with tab4:
    if not st.session_state.saved:
        st.info("Nog niets opgeslagen. Klik op 🔖 Bewaar bij een artikel.")
    else:
        if st.button("🗑️ Alles verwijderen"):
            st.session_state.saved = {}
            st.rerun()
        for si, a in enumerate(st.session_state.saved.values()):
            render_article(a, prefix=f"t4_{si}")

with tab5:
    st.markdown("#### ⚙️ Instellingen")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**📡 Onderwerpen**")
        new_active = {}
        for topic, feeds in TOPICS.items():
            new_active[topic] = st.checkbox(topic, value=st.session_state.active_topics.get(topic, True), key=f"set_{topic}")
            if new_active[topic]:
                with st.expander("Bronnen"):
                    for src in feeds:
                        st.markdown(f"<span style='color:#4a6a8a;font-size:12px'>· {src}</span>", unsafe_allow_html=True)
        st.session_state.active_topics = new_active
        st.markdown("<br>", unsafe_allow_html=True)
        st.session_state.show_dupes = st.toggle("Duplicaten tonen", value=st.session_state.show_dupes)
        st.session_state.max_items = st.slider("Artikelen per bron", 3, 15, st.session_state.max_items)
    with col2:
        st.markdown("**🏷️ Trefwoorden**")
        kw_str = ", ".join(st.session_state.keywords)
        kw_input = st.text_input("Komma-gescheiden", value=kw_str, placeholder="bijv. AI, ECB, rente…")
        st.session_state.keywords = [k.strip() for k in kw_input.split(",") if k.strip()] if kw_input else []
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("**➕ Eigen bron**")
        st.session_state.custom_name = st.text_input("Naam", value=st.session_state.custom_name, placeholder="bijv. FD.nl")
        st.session_state.custom_url = st.text_input("RSS URL", value=st.session_state.custom_url, placeholder="https://...")
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Feeds vernieuwen", use_container_width=True, key="settings_refresh"):
            st.cache_data.clear()
            st.rerun()
