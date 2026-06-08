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
    background: transparent !important; border: none !important;
    color: #4a6a8a !important; font-size: 13px !important;
    font-weight: 500 !important; text-align: left !important;
    padding: 8px 12px !important; width: 100% !important;
}
div[data-testid="stSidebar"] .stButton button:hover { background: #0e1a2d !important; color: #c8e0ff !important; }

div[data-testid="stTextInput"] input {
    background: #0a1628 !important; border: 1px solid #162035 !important;
    border-radius: 10px !important; color: #c8d8f0 !important; font-size: 13px !important;
}

/* ── Breaking News ── */
.breaking-wrap {
    background: linear-gradient(135deg, #0f1e38, #0a1628);
    border: 1px solid #1e3a6b;
    border-radius: 14px;
    padding: 20px 24px;
    margin-bottom: 32px;
}
.breaking-label {
    font-size: 10px; font-weight: 800; color: #ef4444;
    text-transform: uppercase; letter-spacing: 2px;
    margin-bottom: 12px; display: flex; align-items: center; gap: 6px;
}
.breaking-dot {
    width: 7px; height: 7px; background: #ef4444;
    border-radius: 50%; display: inline-block;
    animation: pulse 1.5s infinite;
}
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
.breaking-item {
    display: flex; align-items: center; gap: 10px;
    padding: 8px 0; border-bottom: 1px solid #111e35;
}
.breaking-item:last-child { border-bottom: none; }
.breaking-source { font-size: 10px; font-weight: 700; color: #2563eb; text-transform: uppercase; white-space: nowrap; }
.breaking-title { font-size: 14px; font-weight: 600; color: #dde8f8; flex: 1; }
.breaking-title:hover { color: #7aa8e0; }
.breaking-time { font-size: 11px; color: #1e3050; white-space: nowrap; }

/* ── Sectie headers ── */
.section-title {
    font-size: 18px; font-weight: 800; color: #f0f6ff;
    letter-spacing: -0.3px; margin: 28px 0 16px 0;
    padding-bottom: 10px; border-bottom: 2px solid #111e35;
}

/* ── Meer Nieuws artikel ── */
.news-card {
    display: flex; gap: 14px; align-items: flex-start;
    padding: 14px 0; border-bottom: 1px solid #0f1e35;
}
.news-card:hover .news-title { color: #7aa8e0 !important; }
.news-card-body { flex: 1; min-width: 0; }
.news-source { font-size: 10px; font-weight: 700; color: #2563eb; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
.news-title { font-size: 14px; font-weight: 600; color: #dde8f8; line-height: 1.4; margin-bottom: 4px; text-decoration: none; display: block; transition: color 0.15s; }
.news-title.dimmed { color: #2a3d5a !important; }
.news-summary { font-size: 12px; color: #4a6a8a; line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.news-meta { font-size: 11px; color: #1e3050; margin-top: 4px; }
.news-thumb { width: 86px; height: 64px; object-fit: cover; border-radius: 8px; flex-shrink: 0; }

/* ── Topic kolom ── */
.topic-col-header {
    font-size: 12px; font-weight: 700; color: #5a7a9a;
    text-transform: uppercase; letter-spacing: 1px;
    margin-bottom: 12px; padding-bottom: 6px;
    border-bottom: 2px solid #2563eb;
    cursor: pointer; display: flex; justify-content: space-between; align-items: center;
}
.topic-col-header:hover { color: #7aa8e0; }
.topic-arrow { font-size: 14px; color: #2563eb; }
.mini-card { padding: 10px 0; border-bottom: 1px solid #0f1e35; display: flex; gap: 10px; align-items: flex-start; }
.mini-card:last-child { border-bottom: none; }
.mini-card-body { flex: 1; min-width: 0; }
.mini-source { font-size: 10px; font-weight: 700; color: #1e3a5f; text-transform: uppercase; letter-spacing: 0.3px; margin-bottom: 3px; }
.mini-title { font-size: 13px; font-weight: 600; color: #c8d8f0; line-height: 1.35; text-decoration: none; display: block; }
.mini-title:hover { color: #7aa8e0; }
.mini-time { font-size: 10px; color: #1e3050; margin-top: 3px; }
.mini-thumb { width: 54px; height: 40px; object-fit: cover; border-radius: 6px; flex-shrink: 0; }

/* Knoppen */
.stButton button {
    background: #0a1628 !important; border: 1px solid #162035 !important;
    color: #5a7a9a !important; border-radius: 6px !important;
    font-size: 11px !important; padding: 3px 10px !important;
}
.stButton button:hover { background: #0f2040 !important; border-color: #2563eb !important; color: #7aa8e0 !important; }

/* Categorie pagina */
.stTabs [data-baseweb="tab-list"] { background: transparent !important; border-bottom: 1px solid #111e35 !important; }
.stTabs [data-baseweb="tab"] { background: transparent !important; color: #2a3d5a !important; font-size: 12px !important; font-weight: 600 !important; padding: 8px 16px !important; border-bottom: 2px solid transparent !important; }
.stTabs [aria-selected="true"] { color: #7aa8e0 !important; border-bottom: 2px solid #2563eb !important; background: transparent !important; }
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

for key, val in [("saved", {}), ("read", set()), ("page", "home"), ("active_category", ""),
                 ("active_topics", {t: True for t in TOPICS}), ("custom_name", ""),
                 ("custom_url", ""), ("max_items", 8), ("keywords", []), ("show_dupes", False)]:
    if key not in st.session_state: st.session_state[key] = val

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
        mins = int((datetime.now(timezone.utc) - parsedate_to_datetime(pub_raw)).total_seconds() / 60)
        if mins < 1: return "zojuist"
        if mins < 60: return f"{mins} min"
        h = mins // 60
        if h < 24: return f"{h} uur"
        d = h // 24
        return "gisteren" if d == 1 else f"{d} dagen"
    except: return ""
def sort_key(a):
    try: return parsedate_to_datetime(a["pub_raw"])
    except: return datetime.min.replace(tzinfo=timezone.utc)
def esc(t): return (t or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")
def dedup(arts, thr=0.6):
    seen, unique = [], []
    for a in arts:
        words = set(a["title"].lower().split())
        if not any(len(words & s) / max(len(words), len(s), 1) > thr for s in seen):
            unique.append(a); seen.append(words)
    return unique
def thumb_html(url, cls="news-thumb"):
    if not url: return ""
    return '<img class="' + cls + '" src="' + esc(url) + '" onerror="this.style.display=\'none\'">'

@st.cache_data(ttl=60, show_spinner=False)
def fetch(source, url):
    try:
        r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0 Chrome/120.0.0.0 Safari/537.36", "Cache-Control": "no-cache"})
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
            if title:
                out.append({"source": source, "title": title, "link": link.strip(),
                            "date": relative_time(pub), "pub_raw": pub,
                            "summary": summary, "img": img, "id": ""})
        return out
    except: return []

# Sidebar
with st.sidebar:
    st.markdown("<div style='padding:16px 0 8px 0;font-size:20px;font-weight:800;color:#f0f6ff'>🗞️ My News</div>", unsafe_allow_html=True)
    st.markdown("<hr style='border:none;border-top:1px solid #111e35;margin:0 0 12px 0'>", unsafe_allow_html=True)
    if st.button("🏠 Home", use_container_width=True, key="nav_home"):
        st.session_state.page = "home"
        st.rerun()
    st.markdown("<div style='font-size:10px;font-weight:700;color:#1e3050;text-transform:uppercase;letter-spacing:1px;margin:12px 0 8px 0'>Categorieën</div>", unsafe_allow_html=True)
    for topic in TOPICS:
        if not st.session_state.active_topics.get(topic, True): continue
        is_sel = st.session_state.page == "category" and st.session_state.active_category == topic
        if st.button(topic, key=f"nav_{topic}", use_container_width=True):
            st.session_state.page = "category"
            st.session_state.active_category = topic
            st.rerun()
    st.markdown("<hr style='border:none;border-top:1px solid #111e35;margin:12px 0'>", unsafe_allow_html=True)
    if st.button("⚙️ Instellingen", use_container_width=True, key="nav_settings"):
        st.session_state.page = "settings"
        st.rerun()
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
    for a in arts: a["id"] = article_id(a)
    topic_articles[topic].extend(arts)
    all_articles.extend(arts)
    bar.progress((i+1)/len(sources_to_load), text=f"{src}…")
bar.empty()

if not st.session_state.show_dupes:
    all_articles = dedup(all_articles)
    for t in topic_articles: topic_articles[t] = dedup(topic_articles[t])

sorted_all = sorted(all_articles, key=sort_key, reverse=True)

def render_news_card(a, prefix="n"):
    aid = a["id"]
    is_read = aid in st.session_state.read
    is_saved = aid in st.session_state.saved
    dim = " dimmed" if is_read else ""
    saved_html = ' <span style="color:#2e8b2e;font-size:10px">🔖</span>' if is_saved else ""
    summary = esc(a["summary"][:130]) + ("…" if len(a["summary"]) > 130 else "") if a.get("summary") else ""
    th = thumb_html(a.get("img",""), "news-thumb")
    html = f'''<div class="news-card">
        <div class="news-card-body">
            <div class="news-source">{esc(a["source"])} · {esc(a["date"])}{saved_html}</div>
            <a class="news-title{dim}" href="{esc(a["link"])}" target="_blank">{esc(a["title"])}</a>
            <div class="news-summary">{summary}</div>
        </div>{th}</div>'''
    st.markdown(html, unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("✅" if is_saved else "🔖", key=f"{prefix}_s_{aid}"):
            if is_saved: del st.session_state.saved[aid]
            else: st.session_state.saved[aid] = a
            st.rerun()
    with c2:
        if st.button("↩" if is_read else "👁", key=f"{prefix}_r_{aid}"):
            if is_read: st.session_state.read.discard(aid)
            else: st.session_state.read.add(aid)
            st.rerun()

def render_mini_card(a):
    th = thumb_html(a.get("img",""), "mini-thumb")
    summary = esc(a["summary"][:80]) + "…" if a.get("summary") else ""
    html = f'''<div class="mini-card">
        <div class="mini-card-body">
            <div class="mini-source">{esc(a["source"])}</div>
            <a class="mini-title" href="{esc(a["link"])}" target="_blank">{esc(a["title"])}</a>
            <div class="mini-time">{esc(a["date"])}</div>
        </div>{th}</div>'''
    st.markdown(html, unsafe_allow_html=True)

# ── PAGINA'S ──────────────────────────────────────────────────────────────────
if st.session_state.page == "home":
    st.markdown(f'<div style="font-size:26px;font-weight:800;color:#f0f6ff;padding:16px 0 4px 0;letter-spacing:-0.5px">🗞️ My News</div>', unsafe_allow_html=True)
    st.markdown(f'<div style="font-size:12px;color:#2a3d5a;margin-bottom:20px">{datetime.now().strftime("%A %d %B %Y, %H:%M")}</div>', unsafe_allow_html=True)

    # ── Breaking News ──
    breaking = sorted_all[:6]
    if breaking:
        items_html = ""
        for a in breaking:
            items_html += f'''<div class="breaking-item">
                <span class="breaking-source">{esc(a["source"])}</span>
                <a class="breaking-title" href="{esc(a["link"])}" target="_blank">{esc(a["title"])}</a>
                <span class="breaking-time">{esc(a["date"])}</span>
            </div>'''
        st.markdown(f'''<div class="breaking-wrap">
            <div class="breaking-label"><span class="breaking-dot"></span> Breaking News</div>
            {items_html}
        </div>''', unsafe_allow_html=True)

    # ── Meer Nieuws ──
    st.markdown('<div class="section-title">Meer nieuws</div>', unsafe_allow_html=True)
    meer_nieuws = sorted_all[6:14]
    cols = st.columns(2)
    for j, a in enumerate(meer_nieuws):
        with cols[j % 2]:
            render_news_card(a, prefix=f"mn_{j}")

    # ── Jouw onderwerpen ──
    st.markdown('<div class="section-title">Jouw onderwerpen</div>', unsafe_allow_html=True)
    topic_cols = st.columns(len(TOPICS))
    for col, (topic, _) in zip(topic_cols, TOPICS.items()):
        with col:
            topic_arts = topic_articles.get(topic, [])[:3]
            emoji = topic.split()[0]
            name = " ".join(topic.split()[1:])
            if st.button(f"{name} →", key=f"topic_nav_{topic}", use_container_width=True):
                st.session_state.page = "category"
                st.session_state.active_category = topic
                st.rerun()
            for a in topic_arts:
                render_mini_card(a)

elif st.session_state.page == "category":
    cat = st.session_state.active_category
    arts = topic_articles.get(cat, [])
    st.markdown(f'<div style="font-size:24px;font-weight:800;color:#f0f6ff;padding:16px 0 4px 0">{cat}</div>', unsafe_allow_html=True)
    st.markdown(f'<div style="font-size:12px;color:#2a3d5a;margin-bottom:20px">{len(arts)} artikelen</div>', unsafe_allow_html=True)

    search = st.text_input("", placeholder="🔍 Zoek in deze categorie…", key="cat_search")
    if search:
        q = search.lower()
        arts = [a for a in arts if q in a["title"].lower() or q in a["summary"].lower()]

    cat_key = f"show_count_{cat}"
    if cat_key not in st.session_state: st.session_state[cat_key] = 12
    show_n = st.session_state[cat_key]
    for j, a in enumerate(arts[:show_n]):
        render_news_card(a, prefix=f"cat_{j}")
    if show_n < len(arts):
        if st.button(f"Laad meer ({len(arts)-show_n} resterend)", use_container_width=True):
            st.session_state[cat_key] += 12
            st.rerun()

elif st.session_state.page == "settings":
    st.markdown('<div style="font-size:24px;font-weight:800;color:#f0f6ff;padding:16px 0 16px 0">⚙️ Instellingen</div>', unsafe_allow_html=True)
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
        if st.button("🔄 Feeds vernieuwen", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
