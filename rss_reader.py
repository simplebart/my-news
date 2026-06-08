import streamlit as st
import requests
import xml.etree.ElementTree as ET
import re
import os
import hashlib
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

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

/* Sidebar */
div[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #060b16 0%, #0a1220 100%);
    border-right: 1px solid #111e35;
}
div[data-testid="stSidebar"] .stButton button {
    background: transparent !important; border: none !important;
    color: #4a6a8a !important; font-size: 13px !important;
    font-weight: 500 !important; padding: 8px 12px !important;
}
div[data-testid="stSidebar"] .stButton button:hover { background: #0e1a2d !important; color: #c8e0ff !important; }

/* Input */
div[data-testid="stTextInput"] input {
    background: #0a1628 !important; border: 1px solid #162035 !important;
    border-radius: 10px !important; color: #c8d8f0 !important; font-size: 13px !important;
}

/* Breaking News */
.breaking-wrap {
    background: linear-gradient(135deg, #0f1e38, #0a1628);
    border: 1px solid #1e3a6b; border-radius: 14px;
    padding: 20px 24px; margin-bottom: 32px;
}
.breaking-label {
    font-size: 10px; font-weight: 800; color: #ef4444;
    text-transform: uppercase; letter-spacing: 2px;
    margin-bottom: 12px; display: flex; align-items: center; gap: 6px;
}
.breaking-dot { width: 7px; height: 7px; background: #ef4444; border-radius: 50%; display: inline-block; animation: pulse 1.5s infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
.breaking-img { width: 260px; height: 160px; object-fit: cover; border-radius: 10px; flex-shrink: 0; }
.breaking-wrap a { color: #ffffff !important; text-decoration: none !important; }

/* Section headers */
.section-title {
    font-size: 18px; font-weight: 800; color: #ffffff;
    margin: 28px 0 16px 0; padding-bottom: 10px; border-bottom: 2px solid #111e35;
}

/* News card */
.news-card { display: flex; gap: 14px; align-items: flex-start; padding: 14px 0; border-bottom: 1px solid #0f1e35; }
.news-card:hover .news-title { color: #c8e0ff !important; }
.news-card-body { flex: 1; min-width: 0; }
.news-source { font-size: 10px; font-weight: 700; color: #888ea8; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
.news-title { font-size: 15px; font-weight: 700; color: #ffffff !important; line-height: 1.4; margin-bottom: 4px; text-decoration: none !important; display: block; transition: color 0.15s; }
.news-summary { font-size: 12px; color: #a0b0c0; line-height: 1.55; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.news-thumb { width: 86px; height: 64px; object-fit: cover; border-radius: 8px; flex-shrink: 0; }
a.news-title { color: #ffffff !important; text-decoration: none !important; }

/* Mini card */
.mini-card { padding: 10px 0; border-bottom: 1px solid #0a1628; display: flex; gap: 10px; align-items: flex-start; }
.mini-card:last-child { border-bottom: none; }
.mini-card-body { flex: 1; min-width: 0; }
.mini-source { font-size: 10px; font-weight: 700; color: #707888; text-transform: uppercase; margin-bottom: 3px; }
.mini-title { font-size: 13px; font-weight: 600; color: #e8eaf0 !important; line-height: 1.35; text-decoration: none !important; display: block; }
.mini-title:hover { color: #ffffff !important; }
.mini-time { font-size: 10px; color: #606878; margin-top: 3px; }
.mini-thumb { width: 54px; height: 40px; object-fit: cover; border-radius: 6px; flex-shrink: 0; }
a.mini-title { color: #e8eaf0 !important; text-decoration: none !important; }

/* Topic buttons */
.stButton button {
    background: #0e1a2d !important; border: 1px solid #1a2e4a !important;
    color: #c0c8d8 !important; border-radius: 8px !important;
    font-size: 12px !important; font-weight: 600 !important; padding: 6px 12px !important;
}
.stButton button:hover { background: #1a2e4a !important; border-color: #2563eb !important; color: #ffffff !important; }

/* Back button */
.back-btn button { background: transparent !important; border: none !important; color: #4a6a8a !important; font-size: 12px !important; padding: 4px 0 !important; }
.back-btn button:hover { color: #c8e0ff !important; background: transparent !important; }

/* Error notice */
.feed-error { font-size: 11px; color: #ef444466; padding: 4px 0; }

/* Tabs */
.stTabs [data-baseweb="tab-list"] { background: transparent !important; border-bottom: 1px solid #111e35 !important; }
.stTabs [data-baseweb="tab"] { background: transparent !important; color: #2a3d5a !important; font-size: 12px !important; font-weight: 600 !important; padding: 8px 16px !important; border-bottom: 2px solid transparent !important; }
.stTabs [aria-selected="true"] { color: #7aa8e0 !important; border-bottom: 2px solid #2563eb !important; background: transparent !important; }
</style>
""", unsafe_allow_html=True)

TOPICS = {
    "💹 Financiën & Markten": {
        "FT Markets":      "https://www.ft.com/markets?format=rss",
        "FT":              "https://www.ft.com/rss/home",
        "Yahoo Finance":   "https://finance.yahoo.com/news/rss",
        "Business Insider":"https://feeds.businessinsider.com/custom/all",
        "Investing.com":   "https://investing.com/rss/news.rss",
    },
    "🌐 Geopolitiek": {
        "BBC World":       "http://feeds.bbci.co.uk/news/world/rss.xml",
        "Politico Europe": "https://www.politico.eu/feed/",
        "AP News World":   "https://apnews.com/rss/apf-topnews",
    },
    "💻 Tech & AI": {
        "The Verge":       "https://www.theverge.com/rss/index.xml",
        "Ars Technica":    "http://feeds.arstechnica.com/arstechnica/index",
        "FT Tech":         "https://www.ft.com/technology?format=rss",
    },
    "📊 Economics": {
        "BBC Business":     "http://feeds.bbci.co.uk/news/business/rss.xml",
        "Euronews Business":"https://www.euronews.com/rss?format=mrss&level=vertical&name=business",
        "IMF News":         "https://www.imf.org/en/News/rss?language=eng",
    },
}

for key, val in [("page","home"), ("active_category",""), ("active_source",""),
                 ("active_topics",{t:True for t in TOPICS}),
                 ("custom_name",""), ("custom_url",""),
                 ("max_items",8), ("keywords",[]), ("show_dupes",False),
                 ("feed_errors",{})]:
    if key not in st.session_state: st.session_state[key] = val

def clean_xml(t): return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]','',t)

def strip_html(text):
    if not text: return ""
    text = re.sub(r'<!\[CDATA\[(.*?)\]\]>',r'\1',text,flags=re.DOTALL)
    text = re.sub(r'<[^>]+>',' ',text)
    text = text.replace('&amp;','&').replace('&lt;','<').replace('&gt;','>').replace('&quot;','"').replace('&#39;',"'").replace('&nbsp;',' ')
    return re.sub(r'\s+', ' ', text).strip()

def article_id(a): return hashlib.md5((a.get("link","")+a.get("title","")).encode()).hexdigest()[:10]

def parse_date(pub_raw):
    if not pub_raw: return None
    # Try RFC 2822 (standard RSS)
    try: return parsedate_to_datetime(pub_raw)
    except: pass
    # Try ISO 8601 with timezone offset e.g. 2026-06-08T13:14:34-04:00
    try:
        from datetime import timezone as tz
        # Python 3.7+ handles %z with colon offset
        dt = datetime.fromisoformat(pub_raw.strip())
        return dt.astimezone(timezone.utc)
    except: pass
    for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"]:
        try:
            dt = datetime.strptime(pub_raw[:19], fmt[:19])
            return dt.replace(tzinfo=timezone.utc)
        except: pass
    # Try US format: MM/DD/YYYY, HH:MM AM/PM
    for fmt in ["%m/%d/%Y, %I:%M %p", "%m/%d/%Y %I:%M %p", "%m/%d/%Y, %H:%M", "%B %d, %Y, %I:%M %p"]:
        try:
            dt = datetime.strptime(pub_raw.strip(), fmt)
            return dt.replace(tzinfo=timezone.utc)
        except: pass
    # Business Insider: "Jun 8, 2026, 5:41 PM CEST"
    # The Verge: "Jun 8, 2026 at 7:07 PM GMT+2"
    try:
        clean = pub_raw.strip()
        clean = re.sub(r'\s+GMT[+-]\d+$', '', clean)       # strip GMT+2
        clean = re.sub(r'\s+[A-Z]{2,5}$', '', clean)       # strip CEST/CET/EST
        clean = re.sub(r'\s+at\s+', ', ', clean)            # "at" -> ","
        clean = re.sub(r',\s*,', ',', clean)                # double comma fix
        for fmt in ["%b %d, %Y, %I:%M %p", "%b %d, %Y %I:%M %p",
                    "%B %d, %Y, %I:%M %p", "%B %d, %Y %I:%M %p"]:
            try:
                dt = datetime.strptime(clean.strip(), fmt)
                return dt.replace(tzinfo=timezone.utc)
            except: pass
    except: pass
    # Yahoo Finance: "Mon, June 8, 2026 at 6:30 PM GMT+2"
    try:
        clean = re.sub(r'\s+at\s+', ' ', pub_raw.strip())  # remove "at"
        clean = re.sub(r'\s+GMT[+-]\d+$', '', clean)        # strip GMT offset
        clean = re.sub(r'^[A-Za-z]+,\s+', '', clean)        # strip weekday
        dt = datetime.strptime(clean, "%B %d, %Y %I:%M %p")
        return dt.replace(tzinfo=timezone.utc)
    except: pass
    return None

def relative_time(pub_raw):
    try:
        dt = parse_date(pub_raw)
        if not dt: return ""
        mins = int((datetime.now(timezone.utc)-dt).total_seconds()/60)
        if mins < 1: return "zojuist"
        if mins < 60: return f"{mins} min"
        h = mins//60
        if h < 24: return f"{h} uur"
        d = h//24
        return "gisteren" if d==1 else f"{d} dagen"
    except: return ""

def is_recent(pub_raw, hours=2):
    try:
        dt = parse_date(pub_raw)
        if not dt: return False
        return (datetime.now(timezone.utc) - dt) < timedelta(hours=hours)
    except: return False

def sort_key(a):
    dt = parse_date(a.get("pub_raw",""))
    return dt if dt else datetime.min.replace(tzinfo=timezone.utc)

def esc(t): return (t or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

def dedup(arts, thr=0.6):
    seen, unique = [], []
    for a in arts:
        words = set(a["title"].lower().split())
        if not any(len(words&s)/max(len(words),len(s),1)>thr for s in seen):
            unique.append(a); seen.append(words)
    return unique

def thumb_html(url, cls="news-thumb"):
    w = "86px" if cls=="news-thumb" else ("260px" if cls=="breaking-img" else "54px")
    h = "64px" if cls=="news-thumb" else ("160px" if cls=="breaking-img" else "40px")
    r = "8px" if cls!="breaking-img" else "10px"
    ph = f'<div style="width:{w};height:{h};background:#111e35;border-radius:{r};flex-shrink:0;border:1px solid #1a2744"></div>'
    if not url: return ph
    return f'<img class="{cls}" src="{esc(url)}" style="width:{w};height:{h};object-fit:cover;border-radius:{r};flex-shrink:0" onerror="this.outerHTML=\'{ph}\'">'

@st.cache_data(ttl=3600, show_spinner=False)
def get_og_image(url):
    try:
        r = requests.get(url, timeout=5, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html",
        })
        for pattern in [
            r'<meta\s+property=["\']og:image["\']\s+content=["\'](https?://[^"\']+)["\']',
            r'<meta\s+content=["\'](https?://[^"\']+)["\']\s+property=["\']og:image["\']',
            r'<meta\s+name=["\']twitter:image["\']\s+content=["\'](https?://[^"\']+)["\']',
        ]:
            m = re.search(pattern, r.text, re.IGNORECASE)
            if m: return m.group(1)
        return ""
    except: return ""

@st.cache_data(ttl=120, show_spinner=False)
def fetch(source, url):
    try:
        r = requests.get(url, timeout=8, headers={
            "User-Agent": "Mozilla/5.0 Chrome/124.0.0.0 Safari/537.36",
            "Cache-Control": "no-cache"
        })
        r.encoding = r.apparent_encoding
        root = ET.fromstring(clean_xml(r.text).encode("utf-8"))
        ns = {"atom":"http://www.w3.org/2005/Atom","media":"http://search.yahoo.com/mrss/"}
        channel = root.find("channel") or root
        out = []
        for item in (channel.findall("item") or root.findall("atom:entry",ns))[:15]:
            link = item.findtext("link","")
            if not link:
                el = item.find("atom:link",ns)
                link = el.get("href","#") if el is not None else "#"
            pub = item.findtext("pubDate") or item.findtext("atom:published","",ns) or ""
            desc_el = item.find("description") or item.find("atom:summary",ns)
            summary = strip_html(" ".join(desc_el.itertext()) if desc_el is not None else "")[:200]
            img = ""
            for tag,attr in [("media:thumbnail","url"),("media:content","url")]:
                el = item.find(tag,ns)
                if el is not None: img=el.get(attr,""); break
            if not img:
                enc = item.find("enclosure")
                if enc is not None and "image" in (enc.get("type") or ""): img=enc.get("url","")
            title = strip_html(item.findtext("title") or item.findtext("atom:title","",ns) or "")
            if title:
                out.append({"source":source,"title":title,"link":link.strip(),
                            "date":relative_time(pub),"pub_raw":pub,
                            "summary":summary,"img":img,"id":""})
        return out, None
    except Exception as e:
        return [], str(e)

# Sidebar
with st.sidebar:
    st.markdown("<div style='padding:16px 0 8px 0;font-size:20px;font-weight:800;color:#f0f6ff'>🗞️ My News</div>", unsafe_allow_html=True)
    st.markdown("<hr style='border:none;border-top:1px solid #111e35;margin:0 0 12px 0'>", unsafe_allow_html=True)
    if st.button("🏠 Home", use_container_width=True, key="nav_home"):
        st.session_state.page = "home"; st.rerun()
    st.markdown("<div style='font-size:10px;font-weight:700;color:#1e3050;text-transform:uppercase;letter-spacing:1px;margin:12px 0 8px 0'>Categorieën</div>", unsafe_allow_html=True)
    for topic in TOPICS:
        if not st.session_state.active_topics.get(topic,True): continue
        if st.button(topic, key=f"nav_{topic}", use_container_width=True):
            st.session_state.page="category"; st.session_state.active_category=topic; st.rerun()
    st.markdown("<hr style='border:none;border-top:1px solid #111e35;margin:12px 0'>", unsafe_allow_html=True)
    st.markdown("<hr style='border:none;border-top:1px solid #111e35;margin:12px 0'>", unsafe_allow_html=True)
    if st.button("⚙️ Instellingen", use_container_width=True, key="nav_settings"):
        st.session_state.page="settings"; st.rerun()
    if st.button("🔄 Vernieuwen", use_container_width=True, key="refresh"):
        st.cache_data.clear(); st.rerun()

# Parallel laden
all_articles, topic_articles, feed_errors = [], defaultdict(list), {}
sources_to_load = []
for topic, feeds in TOPICS.items():
    if st.session_state.active_topics.get(topic,True):
        for src, url in feeds.items():
            sources_to_load.append((topic, src, url))
if st.session_state.custom_url and st.session_state.custom_name:
    sources_to_load.append(("➕ Eigen", st.session_state.custom_name, st.session_state.custom_url))

bar = st.progress(0, text="Nieuws laden…")
results = {}
with ThreadPoolExecutor(max_workers=6) as executor:
    futures = {executor.submit(fetch, src, url): (topic, src) for topic, src, url in sources_to_load}
    done = 0
    for future in as_completed(futures):
        topic, src = futures[future]
        arts, err = future.result()
        done += 1
        bar.progress(done/len(sources_to_load), text=f"{src}…")
        if err:
            feed_errors[src] = err
        arts = arts[:st.session_state.max_items]
        for a in arts: a["id"] = article_id(a)
        topic_articles[topic].extend(arts)
        all_articles.extend(arts)
bar.empty()

if not st.session_state.show_dupes:
    all_articles = dedup(all_articles)
    for t in topic_articles: topic_articles[t] = dedup(topic_articles[t])

sorted_all = sorted(all_articles, key=sort_key, reverse=True)

# Bronnen sidebar - na laden
with st.sidebar:
    with st.expander("📰 Bronnen", expanded=False):
        for src in sorted(set(a["source"] for a in all_articles)):
            if st.button(src, key=f"src_nav_{src}", use_container_width=True):
                st.session_state.page = "source"
                st.session_state.active_source = src
                st.rerun()

# Pre-fetch OG images for articles without one
def prefetch_images(articles):
    urls_needed = [(i, a) for i, a in enumerate(articles) if not a.get("img") and a.get("link")]
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(get_og_image, a["link"]): i for i, a in urls_needed}
        for future in as_completed(futures):
            idx = futures[future]
            articles[idx]["img"] = future.result()
    return articles

all_articles = prefetch_images(all_articles)
sorted_all = sorted(all_articles, key=sort_key, reverse=True)
for t in topic_articles:
    topic_articles[t] = prefetch_images(topic_articles[t])
    topic_articles[t] = sorted(topic_articles[t], key=sort_key, reverse=True)

def get_img(a, cls="news-thumb"):
    return thumb_html(a.get("img",""), cls)

def render_news_card(a, prefix="n", show_source_btn=True):
    summary = esc(a["summary"][:130])+"…" if len(a.get("summary",""))>130 else esc(a.get("summary",""))
    th = get_img(a, "news-thumb")
    st.markdown(f'''<div class="news-card">
        <div class="news-card-body">
            <div class="news-source">{esc(a["source"])} · {esc(a["date"])}</div>
            <a class="news-title" href="{esc(a["link"])}" target="_blank">{esc(a["title"])}</a>
            <div class="news-summary">{summary}</div>
        </div>{th}</div>''', unsafe_allow_html=True)
    if show_source_btn:
        if st.button(f"📰 Meer van {esc(a['source'])}", key=f"{prefix}_src_{a['id']}"):
            st.session_state.page = "source"
            st.session_state.active_source = a["source"]
            st.rerun()

def render_mini_card(a):
    th = get_img(a, "mini-thumb")
    st.markdown(f'''<div class="mini-card">
        <div class="mini-card-body">
            <div class="mini-source">{esc(a["source"])}</div>
            <a class="mini-title" href="{esc(a["link"])}" target="_blank">{esc(a["title"])}</a>
            <div class="mini-time">{esc(a["date"])}</div>
        </div>{th}</div>''', unsafe_allow_html=True)

# ── PAGINA'S ──────────────────────────────────────────────────────────────────
if st.session_state.page == "home":
    st.markdown(f'<div style="font-size:26px;font-weight:800;color:#f0f6ff;padding:16px 0 4px 0;letter-spacing:-0.5px">🗞️ My News</div>', unsafe_allow_html=True)
    st.markdown(f'<div style="font-size:12px;color:#2a3d5a;margin-bottom:20px">{datetime.now().strftime("%A %d %B %Y, %H:%M")}</div>', unsafe_allow_html=True)

    filtered_articles = sorted_all

    # Breaking News — alleen BBC, FT en AP, laatste 2 uur anders meest recent
    BREAKING_SOURCES = ["BBC World", "BBC Business", "FT", "FT Markets", "FT Tech", "AP News World"]
    trusted = [a for a in filtered_articles if a["source"] in BREAKING_SOURCES]
    recent = [a for a in trusted if is_recent(a["pub_raw"], hours=2)]
    breaking_art = recent[0] if recent else (trusted[0] if trusted else (sorted_all[0] if sorted_all else None))

    if breaking_art:
        a = breaking_art
        img_url = a.get("img","")
        if not img_url and a.get("link"): img_url = get_og_image(a["link"])
        img_html = thumb_html(img_url, "breaking-img")
        summary = esc(a["summary"][:200])+"…" if len(a.get("summary",""))>200 else esc(a.get("summary",""))
        st.markdown(f'''<div class="breaking-wrap">
            <div class="breaking-label"><span class="breaking-dot"></span> Breaking News</div>
            <div style="display:flex;gap:20px;align-items:flex-start">
                <div style="flex:1;min-width:0">
                    <div style="font-size:11px;font-weight:700;color:#888ea8;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px">{esc(a["source"])} · {esc(a["date"])}</div>
                    <a href="{esc(a["link"])}" target="_blank" style="font-size:20px;font-weight:800;color:#ffffff;line-height:1.35;text-decoration:none;display:block;margin-bottom:8px">{esc(a["title"])}</a>
                    <div style="font-size:13px;color:#a0b0c0;line-height:1.6">{summary}</div>
                </div>
                {img_html}
            </div>
        </div>''', unsafe_allow_html=True)

    # Meer Nieuws - max 2 per bron
    st.markdown('<div class="section-title">Meer nieuws</div>', unsafe_allow_html=True)
    breaking_id = breaking_art["id"] if breaking_art else ""
    meer_nieuws, source_count = [], {}
    for a in filtered_articles:
        if a["id"] == breaking_id: continue
        if source_count.get(a["source"], 0) >= 2: continue
        meer_nieuws.append(a)
        source_count[a["source"]] = source_count.get(a["source"], 0) + 1
        if len(meer_nieuws) >= 8: break
    cols = st.columns(2)
    for j, a in enumerate(meer_nieuws):
        with cols[j%2]: render_news_card(a)

    # Jouw onderwerpen
    st.markdown('<div class="section-title">Jouw onderwerpen</div>', unsafe_allow_html=True)
    topic_cols = st.columns(len(TOPICS))
    for col, (topic, _) in zip(topic_cols, TOPICS.items()):
        with col:
            name = " ".join(topic.split()[1:])
            if st.button(f"{topic.split()[0]} {name} →", key=f"topic_nav_{topic}", use_container_width=True):
                st.session_state.page="category"; st.session_state.active_category=topic; st.rerun()
            seen_sources = set()
            count = 0
            for a in topic_articles.get(topic, []):
                if a["source"] in seen_sources: continue
                seen_sources.add(a["source"])
                render_mini_card(a)
                count += 1
                if count >= 3: break

elif st.session_state.page == "category":
    cat = st.session_state.active_category
    arts = topic_articles.get(cat, [])

    # Terug knop
    st.markdown('<div class="back-btn">', unsafe_allow_html=True)
    if st.button("← Terug naar home", key="back_home"):
        st.session_state.page="home"; st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(f'<div style="font-size:24px;font-weight:800;color:#f0f6ff;padding:8px 0 4px 0">{cat}</div>', unsafe_allow_html=True)
    st.markdown(f'<div style="font-size:12px;color:#2a3d5a;margin-bottom:16px">{len(arts)} artikelen</div>', unsafe_allow_html=True)

    search = st.text_input("", placeholder="🔍 Zoek in deze categorie…", key="cat_search")
    if search:
        q = search.lower()
        arts = [a for a in arts if q in a["title"].lower() or q in a["summary"].lower()]

    cat_key = f"show_count_{cat}"
    if cat_key not in st.session_state: st.session_state[cat_key] = 12
    show_n = st.session_state[cat_key]
    for j, a in enumerate(arts[:show_n]):
        render_news_card(a)
    if show_n < len(arts):
        if st.button(f"Laad meer ({len(arts)-show_n} resterend)", use_container_width=True):
            st.session_state[cat_key]+=12; st.rerun()

elif st.session_state.page == "source":
    src = st.session_state.active_source
    arts = sorted([a for a in all_articles if a["source"] == src], key=sort_key, reverse=True)
    if st.button("← Terug naar home", key="back_source"):
        st.session_state.page = "home"; st.rerun()
    st.markdown(f'<div style="font-size:24px;font-weight:800;color:#f0f6ff;padding:8px 0 4px 0">{esc(src)}</div>', unsafe_allow_html=True)
    st.markdown(f'<div style="font-size:12px;color:#2a3d5a;margin-bottom:16px">{len(arts)} artikelen</div>', unsafe_allow_html=True)
    for j, a in enumerate(arts):
        render_news_card(a, prefix=f"src_{j}", show_source_btn=False)

elif st.session_state.page == "settings":
    if st.button("← Terug naar home", key="back_settings"):
        st.session_state.page="home"; st.rerun()
    st.markdown('<div style="font-size:24px;font-weight:800;color:#f0f6ff;padding:8px 0 16px 0">⚙️ Instellingen</div>', unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**📡 Onderwerpen**")
        new_active = {}
        for topic, feeds in TOPICS.items():
            new_active[topic] = st.checkbox(topic, value=st.session_state.active_topics.get(topic,True), key=f"set_{topic}")
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
            st.cache_data.clear(); st.rerun()
        if feed_errors:
            st.markdown("**⚠️ Feed fouten**")
            for src, err in feed_errors.items():
                st.markdown(f"<div class='feed-error'>· {src}: verbinding mislukt</div>", unsafe_allow_html=True)
