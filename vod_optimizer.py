import streamlit as st
import requests
import copy
import itertools
from datetime import datetime
import urllib.parse
import hashlib
from supabase import create_client, Client
import pandas as pd


def hash_password(raw_password: str) -> str:
    return hashlib.sha256(raw_password.encode("utf-8")).hexdigest()

@st.dialog("⚠️ Usuwanie danych")
def confirm_hard_reset():
    st.write("Czy na pewno chcesz usunąć CAŁĄ historię, budżet i poczekalnię? Ta akcja jest nieodwracalna.")
    if st.button("Tak, usuń wszystko trwale", type="primary", use_container_width=True):
        st.session_state['history'] = []
        st.session_state['waiting_room'] = []
        st.session_state['target_budget'] = None
        st.session_state['current_spend'] = None
        save_data(st.session_state['logged_in_user'], {
            "poczekalnia": [],
            "historia_wydatkow": [],
            "target_budget": None,
            "current_spend": None
        })
        st.session_state['toast_msg'] = ("Konto zostało zresetowane", "🧹")
        st.rerun()

@st.dialog("🏁 Weryfikacja cyklu")
def confirm_cycle_closure(watched_titles, unwatched_titles):
    st.write("Zanim zamkniemy cykl, powiedz szczerze:")
    st.subheader("Czy w tym miesiącu faktycznie opłaciłeś te platformy?")
    
    if st.button("✅ Tak, kupiłem (Zapisz cykl i oszczędności)", type="primary", use_container_width=True):
        st.session_state['history'][-1]['covered'] = watched_titles
        st.session_state['history'][-1]['is_closed'] = True
        
        if unwatched_titles:
            st.session_state['waiting_room'].extend(unwatched_titles)
            st.session_state['waiting_room'] = list(set(st.session_state['waiting_room']))
            
        save_data(st.session_state['logged_in_user'], {
            "poczekalnia": st.session_state['waiting_room'],
            "historia_wydatkow": st.session_state['history'],
            "target_budget": st.session_state['target_budget'],
            "current_spend": st.session_state['current_spend']
        })
        st.session_state['toast_msg'] = ("Cykl zamknięty, oszczędności dodane!", "💰")
        st.rerun()
        
    if st.button("❌ Nie, zrezygnowałem (Anuluj ten plan)", type="secondary", use_container_width=True):
        # Usuwamy aktywny, niezamknięty plan z historii i zliczania oszczędności
        st.session_state['history'].pop()
        
        # Zwracamy wszystkie zaplanowane tytuły do poczekalni
        all_planned = watched_titles + unwatched_titles
        if all_planned:
            st.session_state['waiting_room'].extend(all_planned)
            st.session_state['waiting_room'] = list(set(st.session_state['waiting_room']))
            
        save_data(st.session_state['logged_in_user'], {
            "poczekalnia": st.session_state['waiting_room'],
            "historia_wydatkow": st.session_state['history'],
            "target_budget": st.session_state['target_budget'],
            "current_spend": st.session_state['current_spend']
        })
        st.session_state['toast_msg'] = ("Plan anulowany. Tytuły wracają do poczekalni, brak kosztów.", "↩️")
        st.rerun()

@st.dialog("🎬 Zwiastun produkcji", width="large")
def show_trailer_dialog(title, media_type, item_id):
    yt_url = fetch_trailer_tmdb(media_type, item_id) if media_type and item_id else None
    st.markdown(f"### 🍿 {title}")
    if yt_url:
        st.video(yt_url)
    else:
        query = urllib.parse.quote(f"{title} oficjalny zwiastun pl trailer")
        yt_search = f"https://www.youtube.com/results?search_query={query}"
        st.info("Brak bezpośredniego klipu w bazie TMDB dla tego tytułu.")
        st.markdown(
            f'<a href="{yt_search}" target="_blank" style="display:inline-block; background:#E50914; color:white; padding:10px 20px; border-radius:20px; text-decoration:none; font-weight:600;">▶️ Otwórz zwiastun na YouTube</a>',
            unsafe_allow_html=True,
        )

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="Optymalizator Subskrypcji VOD", page_icon="🍿", layout="wide", initial_sidebar_state="expanded")

# --- NOWOCZESNY DESIGN (CSS) ---
modern_ui = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@600;700;800&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

/* Ukrywamy śmieci, ale ZOSTAWIAMY górny pasek, żeby działało menu na telefonach */
#MainMenu {visibility: hidden;}
div[data-testid="stAppDeployButton"] {display: none;}
footer {visibility: hidden;}

/* Kinowe tło z delikatną poświatą i nowoczesna typografia */
.stApp {
    background: radial-gradient(circle at 50% 0%, rgba(229, 9, 20, 0.16) 0%, rgba(90, 46, 152, 0.09) 35%, #0b0d13 72%) !important;
    font-family: 'Plus Jakarta Sans', sans-serif !important;
}

h1, h2, h3 {
    font-family: 'Outfit', sans-serif !important;
    letter-spacing: -0.02em;
}

/* Baner Hero */
.hero-banner {
    background: linear-gradient(135deg, rgba(229, 9, 20, 0.16) 0%, rgba(20, 24, 36, 0.85) 55%, rgba(90, 46, 152, 0.18) 100%);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 22px;
    padding: 26px 32px;
    margin-bottom: 22px;
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.35);
    backdrop-filter: blur(12px);
}
.hero-badge {
    display: inline-block;
    background: rgba(229, 9, 20, 0.2);
    color: #ff6b72;
    border: 1px solid rgba(229, 9, 20, 0.4);
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 4px 12px;
    border-radius: 999px;
    margin-bottom: 10px;
}
.hero-title {
    font-family: 'Outfit', sans-serif;
    font-size: 2.4rem;
    font-weight: 800;
    margin: 0 0 6px 0;
    background: linear-gradient(90deg, #ffffff 0%, #f3f4f6 60%, #ff7b82 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}
.hero-subtitle {
    color: #9ca3af;
    font-size: 0.98rem;
    margin: 0;
}

/* Nowoczesne, zaokrąglone przyciski z animacją powiększenia */
.stButton > button, .stFormSubmitButton > button {
    border-radius: 24px !important;
    font-weight: 600 !important;
    transition: all 0.25s ease !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    box-shadow: 0 4px 10px rgba(0, 0, 0, 0.2) !important;
}
.stButton > button:hover, .stFormSubmitButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 16px rgba(229, 9, 20, 0.38) !important;
    border-color: rgba(229, 9, 20, 0.5) !important;
}

/* Karty KPI (st.metric) w stylu Glassmorphism */
div[data-testid="stMetric"] {
    background: linear-gradient(145deg, rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0.015));
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-left: 4px solid #E50914;
    border-radius: 16px;
    padding: 16px 20px;
    box-shadow: 0 8px 22px rgba(0, 0, 0, 0.28);
    backdrop-filter: blur(10px);
    transition: transform 0.25s ease, border-color 0.25s ease;
}
div[data-testid="stMetric"]:hover {
    transform: translateY(-3px);
    border-color: rgba(229, 9, 20, 0.6);
}

/* Delikatne podświetlenie kart (kontenerów) po najechaniu */
div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 16px !important;
    background: rgba(255, 255, 255, 0.018);
    transition: all 0.25s ease;
}
div[data-testid="stVerticalBlockBorderWrapper"]:hover {
    border-color: rgba(229, 9, 20, 0.45) !important;
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.3);
}

/* Plakaty w karuzeli z efektem powiększenia po najechaniu */
.marquee-poster {
    height: 168px;
    margin-right: 16px;
    border-radius: 12px;
    box-shadow: 0 6px 14px rgba(0,0,0,0.45);
    transition: transform 0.25s ease, box-shadow 0.25s ease;
}
.marquee-poster:hover {
    transform: scale(1.07);
    box-shadow: 0 10px 22px rgba(229, 9, 20, 0.5);
}
</style>
"""
st.markdown(modern_ui, unsafe_allow_html=True)

# --- SYSTEM POWIADOMIEŃ TOAST ---
if 'toast_msg' in st.session_state:
    msg, icon = st.session_state['toast_msg']
    st.toast(msg, icon=icon)
    del st.session_state['toast_msg']

# --- SEKRETY I API ---
TMDB_API_KEY = st.secrets.get("TMDB_API_KEY", "BŁĄD_KLUCZA")

@st.cache_resource
def init_supabase():
    url = st.secrets.get("SUPABASE_URL", "")
    key = st.secrets.get("SUPABASE_KEY", "")
    return create_client(url, key)

supabase: Client = init_supabase()

# --- FUNKCJE BAZY DANYCH (CHMURA) ---
def load_data(email):
    try:
        response = supabase.table("user_data").select("*").eq("user_email", email).execute()
        if len(response.data) > 0:
            data = response.data[0]
            return {
                "poczekalnia": data.get("poczekalnia", []), 
                "historia_wydatkow": data.get("historia_wydatkow", []),
                "target_budget": data.get("target_budget"),
                "current_spend": data.get("current_spend"),
                "platform_prices": data.get("platform_prices") # <--- NOWE
            }
        return {"poczekalnia": [], "historia_wydatkow": [], "target_budget": None, "current_spend": None, "platform_prices": None}
    except Exception as e:
        st.error(f"Błąd połączenia z bazą danych: {e}")
        return {"poczekalnia": [], "historia_wydatkow": [], "target_budget": None, "current_spend": None, "platform_prices": None}

def save_data(email, data):
    try:
        supabase.table("user_data").update({
            "poczekalnia": data.get("poczekalnia", []),
            "historia_wydatkow": data.get("historia_wydatkow", []),
            "target_budget": data.get("target_budget"),
            "current_spend": data.get("current_spend"),
            # Zaciągamy ceny wprost z sesji, żeby nie zmieniać każdego przycisku w kodzie
            "platform_prices": st.session_state.get('platform_prices', PLATFORMS)
        }).eq("user_email", email).execute()
    except Exception as e:
        st.error(f"Błąd zapisu do bazy danych: {e}")

# --- KONFIGURACJA DANYCH ---
PLATFORMS = {
    "Netflix": {"price": 75.00, "jw_id": 8, "url": "https://www.netflix.com/pl/"},
    "Disney+": {"price": 34.99, "jw_id": 337, "url": "https://www.disneyplus.com/pl-pl"},
    "Apple TV+": {"price": 34.99, "jw_id": 350, "url": "https://tv.apple.com/pl"},
    "Max": {"price": 29.99, "jw_id": 1899, "url": "https://www.max.com/pl/pl"}, 
    "Canal+": {"price": 29.00, "jw_id": 582, "url": "https://canalplus.com/pl/"},
    "SkyShowtime": {"price": 24.99, "jw_id": 1773, "url": "https://www.skyshowtime.com/pl"},
    "Amazon Prime": {"price": 10.99, "jw_id": 119, "url": "https://www.primevideo.com/pl/"}
}

# --- FUNKCJE POMOCNICZE UI ---
def platform_chip(name):
    # Kolory dopasowane do brandingu platform
    colors = {
        "Netflix": "#E50914",
        "Disney+": "#113CCF",
        "Max": "#5A2E98",
        "Apple TV+": "#1C1C1E",
        "Canal+": "#000000",
        "SkyShowtime": "#001D66",
        "Amazon Prime": "#00A8E1",
        "Amazon Prime Video": "#00A8E1"
    }
    bg_color = colors.get(name, "#555555") # Szary jako domyślny dla nierozpoznanych
    url = PLATFORMS.get(name, {}).get("url", "#")
    
    return f'<a href="{url}" target="_blank" style="text-decoration: none;"><span style="background-color: {bg_color}; color: white; padding: 3px 11px; border-radius: 12px; font-size: 0.75em; font-weight: 600; margin-right: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.25); display: inline-block; margin-bottom: 4px; border: 1px solid rgba(255,255,255,0.12);">{name}</span></a>'

def rating_badge(rating):
    if not rating: return ""
    try:
        r = float(rating)
        if r >= 7.5: bg = "#16a34a" # Zielony (hity)
        elif r >= 6.0: bg = "#ca8a04" # Żółty (średniaki)
        else: bg = "#4b5563" # Szary (słabe)
        return f'<span style="background-color: {bg}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.55em; vertical-align: middle; margin-left: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">⭐ {r:.1f}</span>'
    except:
        return ""

def meta_badge(meta):
    if not meta:
        return ""
    parts = []
    media_type = meta.get("media_type")
    if media_type == "movie":
        parts.append("🎬 Film")
    elif media_type == "tv":
        parts.append("📺 Serial")
    year = meta.get("year")
    if year:
        parts.append(str(year))
    if not parts:
        return ""
    label = " • ".join(parts)
    return f'<span style="background-color: rgba(255,255,255,0.08); color: #d1d5db; padding: 2px 8px; border-radius: 10px; font-size: 0.5em; font-weight: 500; vertical-align: middle; margin-left: 6px; border: 1px solid rgba(255,255,255,0.12);">{label}</span>'

def get_current_month_name():
    months_pl = ["Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec", "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień"]
    now = datetime.now()
    return f"{months_pl[now.month - 1]} {now.year}"

def get_watch_history(title, history):
    title_lower = title.strip().lower()
    for h in reversed(history):
        if h.get('is_closed', True):
            covered_lower = {t.strip().lower(): t for t in h.get('covered', [])}
            if title_lower in covered_lower:
                oryginalny_tytul = covered_lower[title_lower]
                plats = h.get('covered_details', {}).get(oryginalny_tytul, h.get('combo', []))
                plat_str = f" [{', '.join(plats)}]" if plats else ""
                return f"{h.get('month', 'Nieznany')}{plat_str}"
    return None

# --- TRENDY TYGODNIA I KARUZELA PLAKATÓW ---
@st.cache_data(ttl=3600)
def fetch_trending_tmdb():
    if TMDB_API_KEY == "BŁĄD_KLUCZA":
        return []
    url = f"https://api.themoviedb.org/3/trending/all/week?api_key={TMDB_API_KEY}&language=pl-PL"
    try:
        resp = requests.get(url, timeout=5).json()
        results = resp.get('results', [])
        trending = []
        for item in results[:15]:
            path = item.get('poster_path')
            title = item.get('title') or item.get('name')
            if path and title:
                vote = item.get('vote_average')
                rating_str = f"⭐ {vote:.1f}" if vote else ""
                media_type = item.get('media_type', 'movie')
                item_id = item.get('id')
                tmdb_link = f"https://www.themoviedb.org/{media_type}/{item_id}?language=pl-PL" if item_id and media_type in ['movie', 'tv'] else "#"
                trending.append({
                    "title": title,
                    "poster_url": f"https://image.tmdb.org/t/p/w154{path}",
                    "rating_str": rating_str,
                    "tmdb_link": tmdb_link
                })
        return trending
    except:
        return []

def display_marquee():
    trending = fetch_trending_tmdb()
    if not trending:
        return
    posters_html = ""
    for item in trending:
        safe_tooltip = f"{item['title']} ({item['rating_str']})".replace('"', '&quot;')
        posters_html += (
            f'<a href="{item["tmdb_link"]}" target="_blank" title="{safe_tooltip}" style="text-decoration: none;">'
            f'<img src="{item["poster_url"]}" class="marquee-poster" alt="{safe_tooltip}">'
            f'</a>'
        )

    marquee_html = f"""
    <div style="overflow: hidden; white-space: nowrap; margin-bottom: 24px; padding: 12px 0; 
                -webkit-mask-image: linear-gradient(to right, transparent, black 8%, black 92%, transparent); 
                mask-image: linear-gradient(to right, transparent, black 8%, black 92%, transparent);">
        <div style="display: inline-block; animation: scroll 38s linear infinite;" 
             onmouseover="this.style.animationPlayState='paused'" 
             onmouseout="this.style.animationPlayState='running'">
            {posters_html} {posters_html}
        </div>
    </div>
    <style>
    @keyframes scroll {{
        0% {{ transform: translateX(0); }}
        100% {{ transform: translateX(-50%); }}
    }}
    </style>
    """
    st.markdown(marquee_html, unsafe_allow_html=True)

# Inicjalizacja stanu aplikacji
if 'platform_prices' not in st.session_state:
    st.session_state['platform_prices'] = copy.deepcopy(PLATFORMS)
if 'history' not in st.session_state:
    st.session_state['history'] = []
if 'waiting_room' not in st.session_state:
    st.session_state['waiting_room'] = []
if 'target_budget' not in st.session_state:
    st.session_state['target_budget'] = None
if 'current_spend' not in st.session_state:
    st.session_state['current_spend'] = None
if 'current_availability' not in st.session_state:
    st.session_state['current_availability'] = None
if 'titles_to_check' not in st.session_state:
    st.session_state['titles_to_check'] = []
if 'logged_in_user' not in st.session_state:
    st.session_state['logged_in_user'] = None
if 'search_input' not in st.session_state:
    st.session_state['search_input'] = ""
if 'clear_flag' not in st.session_state:
    st.session_state['clear_flag'] = False
if 'pending_titles' not in st.session_state:
    st.session_state['pending_titles'] = []

@st.cache_data(ttl=3600)
def fetch_trailer_tmdb(media_type, item_id):
    if TMDB_API_KEY == "BŁĄD_KLUCZA" or not media_type or not item_id:
        return None
    for lang in ("pl-PL", "en-US"):
        url = f"https://api.themoviedb.org/3/{media_type}/{item_id}/videos?api_key={TMDB_API_KEY}&language={lang}"
        try:
            resp = requests.get(url, timeout=5).json()
            videos = resp.get("results", [])
            # Najpierw szukamy oficjalnego Trailera na YouTube, potem dowolnego Teaser/Clip na YouTube
            for v in videos:
                if v.get("site") == "YouTube" and v.get("type") == "Trailer" and v.get("key"):
                    return f"https://www.youtube.com/watch?v={v['key']}"
            for v in videos:
                if v.get("site") == "YouTube" and v.get("key"):
                    return f"https://www.youtube.com/watch?v={v['key']}"
        except Exception:
            pass
    return None

@st.cache_data(ttl=3600)
def fetch_tmdb_details(title):
    if TMDB_API_KEY == "BŁĄD_KLUCZA":
        return [], None, None, {}
    search_url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={urllib.parse.quote(title.strip())}&language=pl-PL"
    try:
        response = requests.get(search_url, timeout=5).json()
        results = [r for r in response.get('results', []) if r.get('media_type') in ('movie', 'tv')]
        if not results:
            return [], None, None, {}
        
        # --- INTELIGENTNE DOPASOWANIE TYTUŁU ---
        user_query = title.strip().lower()
        best_match = results[0] # Domyślnie bierzemy pierwszy wynik (najpopularniejszy)
        
        for item in results:
            item_title = (item.get('title') or item.get('name') or "").lower()
            item_original = (item.get('original_title') or item.get('original_name') or "").lower()
            
            if user_query == item_title or user_query == item_original:
                best_match = item
                break
        # ---------------------------------------

        media_type = best_match.get('media_type')
        item_id = best_match.get('id')
        poster_path = best_match.get('poster_path')
        vote_avg = best_match.get('vote_average')
        rating = round(vote_avg, 1) if vote_avg else None
        poster_url = f"https://image.tmdb.org/t/p/w154{poster_path}" if poster_path else None

        matched_title = best_match.get('title') or best_match.get('name') or title.title()
        original_title = best_match.get('original_title') or best_match.get('original_name') or ""
        raw_date = best_match.get('release_date') or best_match.get('first_air_date') or ""
        year = raw_date[:4] if len(raw_date) >= 4 else None
        overview = (best_match.get('overview') or "").strip()

        meta_info = {
            "item_id": item_id,
            "matched_title": matched_title,
            "original_title": original_title,
            "media_type": media_type,
            "year": year,
            "overview": overview,
            "tmdb_url": f"https://www.themoviedb.org/{media_type}/{item_id}?language=pl-PL" if item_id else None
        }
        
        if media_type not in ['movie', 'tv']:
            return [], poster_url, rating, meta_info
        providers_url = f"https://api.themoviedb.org/3/{media_type}/{item_id}/watch/providers?api_key={TMDB_API_KEY}"
        prov_response = requests.get(providers_url, timeout=5).json()
        pl_data = prov_response.get('results', {}).get('PL', {})
        flatrate_options = pl_data.get('flatrate', [])
        
        available_platforms = []
        if flatrate_options:
            provider_ids = [prov['provider_id'] for prov in flatrate_options]
            for p_name, p_data in PLATFORMS.items():
                if p_data['jw_id'] in provider_ids:
                    available_platforms.append(p_name)
        return available_platforms, poster_url, rating, meta_info
    except Exception:
        return [], None, None, {}

def fetch_availability_tmdb(title):
    avail, poster, rating, _ = fetch_tmdb_details(title)
    return avail, poster, rating

def optimize_subscriptions(titles_availability):
    platform_names = list(PLATFORMS.keys())
    combos_1 = list(itertools.combinations(platform_names, 1))
    combos_2 = list(itertools.combinations(platform_names, 2))
    all_combos = combos_1 + combos_2
    
    best_combo = []
    max_titles_covered = -1
    best_cost = float('inf')
    
    for combo in all_combos:
        current_covered_titles = [title for title, available_on in titles_availability.items() if any(p in combo for p in available_on)]
        coverage_count = len(current_covered_titles)
        combo_cost = sum(st.session_state['platform_prices'][p]["price"] for p in combo)
        
        if coverage_count > max_titles_covered or (coverage_count == max_titles_covered and combo_cost < best_cost):
            max_titles_covered = coverage_count
            best_cost = combo_cost
            best_combo = list(combo)
    return best_combo

def toggle_watched_status(title):
    has_active = len(st.session_state['history']) > 0 and not st.session_state['history'][-1].get('is_closed', True)
    if has_active:
        if 'watched_temp' not in st.session_state['history'][-1]:
            st.session_state['history'][-1]['watched_temp'] = []
            
        is_checked = st.session_state.get(f"chk_{title}", False)
        if is_checked and title not in st.session_state['history'][-1]['watched_temp']:
            st.session_state['history'][-1]['watched_temp'].append(title)
        elif not is_checked and title in st.session_state['history'][-1]['watched_temp']:
            st.session_state['history'][-1]['watched_temp'].remove(title)
            
        save_data(st.session_state['logged_in_user'], {
            "poczekalnia": st.session_state['waiting_room'],
            "historia_wydatkow": st.session_state['history'],
            "target_budget": st.session_state['target_budget'],
            "current_spend": st.session_state['current_spend']
        })

# --- SYSTEM LOGOWANIA Z HASŁEM ---
if not st.session_state['logged_in_user']:
    # Tworzymy 3 kolumny, żeby wyśrodkować środkową (2 razy szerszą)
    _, col_login, _ = st.columns([1, 2, 1])
    
    with col_login:
        st.write("") # Drobny odstęp z góry
        st.write("")
        with st.container(border=True):
            st.markdown("<h2 style='text-align: center;'>🎬 Optymalizator VOD</h2>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: gray;'>Zaloguj się lub zarejestruj, aby zarządzać subskrypcjami</p>", unsafe_allow_html=True)
            st.write("")
            
            # st.form pozwala na zatwierdzanie klawiszem Enter
            with st.form("login_form"):
                user_email = st.text_input("Adres e-mail", placeholder="przyklad@email.com")
                user_password = st.text_input("Hasło", type="password")
                submitted = st.form_submit_button("Zaloguj / Zarejestruj 🚀", use_container_width=True)
                
                if submitted:
                    if not user_email or not user_password:
                        st.error("Podaj e-mail oraz hasło.")
                    elif "@" not in user_email or "." not in user_email:
                        st.error("Wprowadź poprawny format e-mail.")
                    else:
                        clean_email = user_email.lower().strip()
                        hashed_pass = hash_password(user_password)
                        with st.spinner("Weryfikacja..."):
                            try:
                                response = supabase.table("user_data").select("password").eq("user_email", clean_email).execute()
                                if len(response.data) > 0:
                                    stored_pass = response.data[0].get("password")
                                    if stored_pass == hashed_pass or stored_pass == user_password:
                                        # Automatyczna migracja starszych haseł tekstowych do SHA-256
                                        if stored_pass == user_password and stored_pass != hashed_pass:
                                            supabase.table("user_data").update({"password": hashed_pass}).eq("user_email", clean_email).execute()
                                        st.session_state['logged_in_user'] = clean_email
                                        st.rerun()
                                    else:
                                        st.error("❌ Błędne hasło lub e-mail jest już zajęty!")
                                else:
                                    new_user = {
                                        "user_email": clean_email, 
                                        "password": hashed_pass,
                                        "poczekalnia": [], 
                                        "historia_wydatkow": []
                                    }
                                    supabase.table("user_data").insert(new_user).execute()
                                    st.session_state['logged_in_user'] = clean_email
                                    st.success("Utworzono nowe konto!")
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Błąd połączenia z bazą: {e}")
    st.stop()



if 'cloud_loaded' not in st.session_state or not st.session_state['cloud_loaded']:
    with st.spinner("☁️ Synchronizacja z chmurą..."):
        cloud_data = load_data(st.session_state['logged_in_user'])
        st.session_state['waiting_room'] = cloud_data.get("poczekalnia", [])
        st.session_state['history'] = cloud_data.get("historia_wydatkow", [])
        st.session_state['target_budget'] = cloud_data.get("target_budget")
        st.session_state['current_spend'] = cloud_data.get("current_spend")

        # --- NOWE: Nadpisywanie cen domyślnych tymi z chmury ---
        saved_prices = cloud_data.get("platform_prices")
        if saved_prices:
            st.session_state['platform_prices'] = saved_prices
            
        st.session_state['cloud_loaded'] = True

# ==========================================
# EKRAN ONBOARDINGU (WYWIAD FINANSOWY)
# ==========================================
if st.session_state['target_budget'] is None:
    # Wyśrodkowanie onboardingu
    col_empty1, col_center, col_empty2 = st.columns([1, 2, 1])
    
    with col_center:
        st.title("Witaj w Optymalizatorze VOD! 👋")
        st.markdown("Zanim zaczniemy optymalizować, sprawdźmy, jak wygląda Twoja obecna sytuacja.")
        
        with st.container(border=True):
            st.subheader("1. Za które platformy płacisz w tym momencie?")
            current_subs = st.multiselect("Wybierz swoje aktywne subskrypcje:", list(PLATFORMS.keys()))
            
            netflix_price = 75.0
            if "Netflix" in current_subs:
                netflix_plan = st.radio(
                    "Z jakiego planu Netflixa korzystasz?", 
                    ["Podstawowy (37 zł / 720p / 1 ekran)", 
                     "Standardowy (55 zł / 1080p / 2 ekrany)", 
                     "Premium (75 zł / 4K / 4 ekrany)"]
                )
                if "37" in netflix_plan: netflix_price = 37.0
                elif "55" in netflix_plan: netflix_price = 55.0
                else: netflix_price = 75.0

            prime_price = 10.99
            if "Amazon Prime" in current_subs:
                prime_plan = st.radio(
                    "Jak płacisz za Amazon Prime?", 
                    ["Miesięcznie (10,99 zł)", 
                     "Rocznie z góry (49 zł / rok -> ok. 4,08 zł miesięcznie)"]
                )
                if "Rocznie" in prime_plan: prime_price = 4.08
                else: prime_price = 10.99

            calculated_spend = 0.0
            for sub in current_subs:
                if sub == "Netflix":
                    calculated_spend += netflix_price
                elif sub == "Amazon Prime":
                    calculated_spend += prime_price
                else:
                    calculated_spend += PLATFORMS[sub]["price"]
                    
            st.info(f"Twoje obecne miesięczne wydatki na VOD wynoszą około: **{calculated_spend:.2f} PLN**")
            
        with st.container(border=True):
            st.subheader("2. Ile maksymalnie chciałbyś wydawać miesięcznie?")
            user_budget = st.number_input("Twój miesięczny limit (PLN):", min_value=0.0, value=60.0, step=10.0)
            
            st.write("")
            if st.button("Zapisz profil i przejdź do aplikacji 🚀", type="primary", use_container_width=True):
                st.session_state['target_budget'] = user_budget
                st.session_state['current_spend'] = calculated_spend
                
                st.session_state['platform_prices']["Netflix"]["price"] = netflix_price
                st.session_state['platform_prices']["Amazon Prime"]["price"] = prime_price
                
                save_data(st.session_state['logged_in_user'], {
                    "poczekalnia": st.session_state['waiting_room'],
                    "historia_wydatkow": st.session_state['history'],
                    "target_budget": st.session_state['target_budget'],
                    "current_spend": st.session_state['current_spend']
                })
                st.rerun()
    st.stop()

# ==========================================
# GŁÓWNY INTERFEJS
# ==========================================
# Menu profilu na samej górze po prawej stronie
c_empty, c_prof = st.columns([6, 1])
with c_prof:
    with st.popover("👤 Mój profil", use_container_width=True):
        st.markdown(f"<span style='font-size: 0.8em; color: gray;'>Zalogowano jako:</span><br><b>{st.session_state['logged_in_user']}</b>", unsafe_allow_html=True)
        st.write("---")
        if st.button("Wyloguj 🚪", use_container_width=True):
            st.session_state['logged_in_user'] = None
            st.session_state['cloud_loaded'] = False
            st.rerun()

# Karuzela i baner Hero ładują się pod profilem
display_marquee()

st.markdown(
    """
    <div class="hero-banner">
        <div class="hero-badge">✨ Inteligentny Asystent Streamingowy</div>
        <h1 class="hero-title">🎬 Optymalizator Subskrypcji VOD</h1>
        <p class="hero-subtitle">Wybieraj to, co chcesz obejrzeć — algorytm policzy, które platformy opłaca się włączyć w tym miesiącu, żeby nie przepłacać.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Szybkie zsumowanie oszczędności z zamkniętych cykli (spójne w całej aplikacji)
closed_cycles = [h for h in st.session_state['history'] if h.get('is_closed', False)]
total_saved = sum([h.get("savings", st.session_state['current_spend'] - h.get("cost", 0)) for h in closed_cycles])

kpi1, kpi2, kpi3 = st.columns(3)
with kpi1:
    st.metric("🎯 Docelowy limit", f"{st.session_state['target_budget']:.2f} zł")
with kpi2:
    st.metric("💳 Dawne wydatki", f"{st.session_state['current_spend']:.2f} zł")
with kpi3:
    # Delta (zielona strzałka) pokaże się, jeśli oszczędności są większe od zera
    st.metric("💰 Łączne oszczędności", f"{total_saved:.2f} zł", delta=f"{total_saved:.2f} zł ({len(closed_cycles)} cykli)" if total_saved > 0 else None)

st.write("---") # Oddzielenie headera od reszty apki linią

tab_calc, tab_settings = st.tabs(["🍿 Kalkulator VOD", "⚙️ Ustawienia Profilu"])

with tab_calc:
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Etap 1: Czego szukamy?")

        def add_to_pending(raw_text):
            if not raw_text:
                return
            # Obsługa wpisywania pojedynczego tytułu lub kilku po przecinku / średniku / nowej linii
            parts = [p.strip() for chunk in raw_text.replace(";", ",").split("\n") for p in chunk.split(",") if p.strip()]
            added_any = False
            existing_lower = [x.lower() for x in st.session_state['pending_titles']]
            for part in parts:
                if part.lower() not in existing_lower:
                    st.session_state['pending_titles'].append(part)
                    existing_lower.append(part.lower())
                    added_any = True
            if added_any and len(parts) == 1:
                st.session_state["toast_msg"] = (f"Dodano „{parts[0]}” do kolejki!", "🎬")
            elif added_any:
                st.session_state["toast_msg"] = (f"Dodano {len(parts)} tytułów do kolejki!", "🎬")

        with st.form("add_title_form", clear_on_submit=True, border=True):
            f_col1, f_col2 = st.columns([4, 1])
            with f_col1:
                new_title_input = st.text_input(
                    "Dodaj film lub serial (wciśnij Enter lub kliknij Dodaj):",
                    placeholder="np. Diuna, The Bear, Fallout (możesz wpisać kilka po przecinku)...",
                    label_visibility="collapsed",
                )
            with f_col2:
                submitted_title = st.form_submit_button("➕ Dodaj", use_container_width=True)
            if submitted_title and new_title_input.strip():
                add_to_pending(new_title_input)
                st.rerun()

        # Wyświetlanie kolejki dodanych tytułów jako klikalne pigułki
        if st.session_state['pending_titles']:
            st.caption(f"🎯 **Twoja kolejka do sprawdzenia ({len(st.session_state['pending_titles'])}):** *(kliknij tytuł, aby usunąć)*")
            pill_cols = st.columns(3)
            for p_idx, p_title in enumerate(list(st.session_state['pending_titles'])):
                with pill_cols[p_idx % 3]:
                    if st.button(f"✕ {p_title}", key=f"rm_pending_{p_idx}_{p_title}", use_container_width=True):
                        st.session_state['pending_titles'].remove(p_title)
                        st.rerun()
        else:
            st.caption("✨ *Kolejka jest pusta — wpisz tytuł powyżej lub wybierz coś z hitów tygodnia poniżej.*")

        trending_items = fetch_trending_tmdb()
        if trending_items:
            with st.expander("🔥 Zainspiruj się: Hity tygodnia (dodaj 1 kliknięciem)"):
                st.caption("Kliknij tytuł poniżej, aby dorzucić go od razu do swojej kolejki:")
                t_cols = st.columns(2)
                for idx, t_item in enumerate(trending_items[:8]):
                    t_title = t_item["title"]
                    t_rating = f" ({t_item['rating_str']})" if t_item.get("rating_str") else ""
                    with t_cols[idx % 2]:
                        if st.button(
                            f"➕ {t_title}{t_rating}",
                            key=f"trend_add_{idx}",
                            use_container_width=True,
                        ):
                            add_to_pending(t_title)
                            st.rerun()

        include_waiting_room = st.checkbox("➕ Uwzględnij tytuły z mojej Kupki wstydu", value=True)
        
        if st.button("Sprawdź dostępność i dobierz pakiet 🔍", type="primary", use_container_width=True):
            current_titles = list(st.session_state['pending_titles'])
            
            if include_waiting_room:
                all_titles = list(dict.fromkeys(current_titles + st.session_state['waiting_room']))
            else:
                all_titles = list(dict.fromkeys(current_titles))
            
            if not all_titles:
                st.warning("Dodaj przynajmniej jeden tytuł do kolejki (lub zaznacz Kupkę wstydu)!")
            else:
                with st.spinner("Pobieram oceny, plakaty, opisy i dostępność z bazy TMDB... 🎬"):
                    st.session_state['titles_to_check'] = all_titles
                    availability, posters, ratings, metas = {}, {}, {}, {}
                    for title in all_titles:
                        avail, poster, rating, meta_info = fetch_tmdb_details(title)
                        availability[title] = avail
                        posters[title] = poster
                        ratings[title] = rating
                        metas[title] = meta_info
                    st.session_state['current_availability'] = availability
                    st.session_state['current_posters'] = posters
                    st.session_state['current_ratings'] = ratings
                    st.session_state['current_metas'] = metas
                st.session_state['pending_titles'] = []
                st.rerun()

        if not st.session_state['current_availability']:
            st.info("💡 **Podpowiedź:** Dodaj powyżej tytuły, które chodzą Ci po głowie, a algorytm automatycznie przeszuka platformy i dobierze najtańszy pakiet.")

        if st.session_state['current_availability']:
            st.write("---")
            st.subheader("Etap 2: Twój wybór na aktualny cykl")
            
            availability = st.session_state['current_availability']
            posters = st.session_state.get('current_posters', {})
            ratings = st.session_state.get('current_ratings', {})
            metas = st.session_state.get('current_metas', {})
            
            titles_list = list(availability.keys())
            for title in titles_list:
                with st.container(border=True):
                    c_img, c_info, c_action = st.columns([1.1, 3.7, 1.2])
                    with c_img:
                        poster_url = posters.get(title)
                        if poster_url:
                            st.markdown(f'<img src="{poster_url}" style="width: 100%; aspect-ratio: 2/3; object-fit: cover; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.35);">', unsafe_allow_html=True)
                        else:
                            st.markdown('<div style="width: 100%; aspect-ratio: 2/3; background-color: #1e1e1e; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 2em; box-shadow: 0 4px 10px rgba(0,0,0,0.35);">🎬</div>', unsafe_allow_html=True)
                    
                    with c_info:
                        rating = ratings.get(title)
                        meta = metas.get(title, {})
                        display_title = meta.get("matched_title") or title.title()
                        st.markdown(f"### {display_title} {rating_badge(rating)}{meta_badge(meta)}", unsafe_allow_html=True)

                        orig_title = meta.get("original_title", "")
                        if orig_title and orig_title.lower() != display_title.lower():
                            st.caption(f"Tytuł oryginalny: *{orig_title}*")

                        overview = meta.get("overview", "")
                        if overview:
                            short_overview = overview[:155] + "…" if len(overview) > 155 else overview
                            st.caption(short_overview)
                        
                        history_match = get_watch_history(title, st.session_state['history'])
                        if history_match:
                            st.info(f"💡 Oglądałeś to już w: **{history_match}**!")
                            
                        platforms = availability.get(title, [])
                        if platforms:
                            platforms_links = "".join([platform_chip(p) for p in platforms])
                            st.markdown(platforms_links, unsafe_allow_html=True)
                        else:
                            st.markdown("*Brak w abonamentach (tylko wypożyczalnie/zakup).*")
                            
                    with c_action:
                        if st.button("▶️ Zwiastun", key=f"trailer_{title}", use_container_width=True):
                            show_trailer_dialog(display_title, meta.get("media_type"), meta.get("item_id"))
                        if st.button("🗑️ Odrzuć", key=f"discard_{title}", use_container_width=True):
                            if title in st.session_state['titles_to_check']:
                                st.session_state['titles_to_check'].remove(title)
                            if title in st.session_state['current_availability']:
                                del st.session_state['current_availability'][title]
                            st.rerun()

            if st.session_state['current_availability']:
                with st.container(border=True):
                    suggested_combo = optimize_subscriptions(st.session_state['current_availability'])
                    st.success(f"💡 **Sugestia algorytmu:** Najbardziej opłaca Ci się wziąć: **{', '.join(suggested_combo) if suggested_combo else 'Nic'}**")
                    
                    selected_platforms = st.multiselect(
                        "Wybierz platformy, które chcesz dodać do tego cyklu:", 
                        options=list(PLATFORMS.keys()), 
                        default=suggested_combo
                    )
                    
                    live_cost = sum(st.session_state['platform_prices'][p]["price"] for p in selected_platforms)
                    live_left = st.session_state['target_budget'] - live_cost
                    live_covered_count = sum(
                        1
                        for t in st.session_state['titles_to_check']
                        if any(p in selected_platforms for p in st.session_state['current_availability'].get(t, []))
                    )
                    total_checked_count = len(st.session_state['titles_to_check'])
                    if live_covered_count > 0:
                        cost_per_title = live_cost / live_covered_count
                        cinema_cmp = " — taniej niż bilet do kina! 🍿" if cost_per_title < 30 else ""
                        per_title_info = f" | 🎯 Pokrycie: **{live_covered_count}/{total_checked_count}** tyt. (**{cost_per_title:.2f} zł** / tytuł{cinema_cmp})"
                    else:
                        per_title_info = f" | 🎯 Pokrycie: **0/{total_checked_count}** tyt."
                    
                    if live_cost > st.session_state['target_budget']:
                        st.error(f"💸 Koszt wybranych: **{live_cost:.2f} PLN** (Przekraczasz budżet o {abs(live_left):.2f} PLN!){per_title_info}")
                    else:
                        st.info(f"💸 Koszt wybranych: **{live_cost:.2f} PLN** (Zostaje Ci: {live_left:.2f} PLN z budżetu){per_title_info}")
                    
                    if st.button("Zatwierdź plan i aktualizuj poczekalnię ✅", type="primary", use_container_width=True):
                        covered, uncovered = [], []
                        covered_details = {}
                        for title in st.session_state['titles_to_check']:
                            available_in_selected = [p for p in st.session_state['current_availability'].get(title, []) if p in selected_platforms]
                            if available_in_selected:
                                covered.append(title)
                                covered_details[title] = available_in_selected
                            else:
                                uncovered.append(title)
                        
                        has_active_plan = len(st.session_state['history']) > 0 and not st.session_state['history'][-1].get('is_closed', True)
                        
                        if has_active_plan:
                            existing_combo = set(st.session_state['history'][-1]['combo'])
                            merged_combo = list(existing_combo.union(set(selected_platforms)))
                            new_cost = sum(st.session_state['platform_prices'][p]["price"] for p in merged_combo)
                            
                            new_savings = st.session_state['current_spend'] - new_cost
                            merged_covered = list(set(st.session_state['history'][-1]['covered'] + covered))
                            
                            merged_covered_details = st.session_state['history'][-1].get('covered_details', {})
                            merged_covered_details.update(covered_details)
                            
                            st.session_state['history'][-1].update({
                                "combo": merged_combo,
                                "cost": new_cost,
                                "savings": new_savings,
                                "covered": merged_covered,
                                "covered_details": merged_covered_details
                            })
                        else:
                            cost = sum(st.session_state['platform_prices'][p]["price"] for p in selected_platforms)
                            savings = st.session_state['current_spend'] - cost
                            
                            current_month_result = {
                                "month": get_current_month_name(),
                                "combo": selected_platforms,
                                "cost": cost,
                                "covered": covered,
                                "covered_details": covered_details,
                                "watched_temp": [],
                                "savings": savings,
                                "is_closed": False 
                            }
                            st.session_state['history'].append(current_month_result)
                        
                        st.session_state['waiting_room'] = uncovered
                        st.session_state['current_availability'] = None
                        st.session_state['titles_to_check'] = []
                        
                        save_data(st.session_state['logged_in_user'], {
                            "poczekalnia": st.session_state['waiting_room'],
                            "historia_wydatkow": st.session_state['history'],
                            "target_budget": st.session_state['target_budget'],
                            "current_spend": st.session_state['current_spend']
                        })
                        st.session_state['toast_msg'] = ("Zaktualizowano plan na ten cykl!", "✅")
                        st.rerun()

    with col2:
        st.subheader("Dashboard Finansowy 💰")
                        
        has_active_plan = len(st.session_state['history']) > 0 and not st.session_state['history'][-1].get('is_closed', True)
        
        if has_active_plan:
            with st.container(border=True):
                res = st.session_state['history'][-1]
                current_cost = res.get('cost', 0.0)
                savings = st.session_state['current_spend'] - current_cost
                
                combo_html = "".join([platform_chip(p) for p in res.get('combo', [])]) if res.get('combo', []) else 'Nic!'
                st.markdown(f"**W bieżącym cyklu ({res.get('month')}) kupiłeś:** {combo_html}", unsafe_allow_html=True)
                
                m1, m2, m3 = st.columns(3)
                m1.metric("Twój Limit", f"{st.session_state['target_budget']:.2f} PLN")
                m2.metric("Ten cykl", f"{current_cost:.2f} PLN")
                m3.metric("Oszczędność", f"{savings:.2f} PLN", delta=f"{savings:.2f} PLN")
                
                if st.session_state['target_budget'] > 0:
                    percent_used = min(current_cost / st.session_state['target_budget'], 1.0)
                    st.progress(percent_used, text=f"💸 Wykorzystanie budżetu: {percent_used*100:.0f}%")
                    if current_cost > st.session_state['target_budget']:
                        st.warning("⚠️ Przekroczyłeś swój limit budżetowy na ten cykl!")
                
                st.write("---")
                st.markdown("**Do obejrzenia (Zaznacz to, co widziałeś):**")
                
                if res.get('covered'):
                    if 'watched_temp' not in res:
                        res['watched_temp'] = []

                    total_covered = len(res['covered'])
                    watched_count = len([t for t in res['covered'] if t in res.get('watched_temp', [])])
                    if total_covered > 0:
                        watch_ratio = min(watched_count / total_covered, 1.0)
                        st.progress(watch_ratio, text=f"🍿 Postęp oglądania: {watched_count} z {total_covered} tytułów ({watch_ratio*100:.0f}%)")
                        
                    if st.button("☑️ Zaznacz wszystkie jako obejrzane"):
                        for t in res['covered']:
                            st.session_state[f"chk_{t}"] = True
                            if t not in res['watched_temp']:
                                res['watched_temp'].append(t)
                        save_data(st.session_state['logged_in_user'], {
                            "poczekalnia": st.session_state['waiting_room'],
                            "historia_wydatkow": st.session_state['history'],
                            "target_budget": st.session_state['target_budget'],
                            "current_spend": st.session_state['current_spend']
                        })
                        st.rerun()
                            
                    for t in res['covered']:
                        safe_title = urllib.parse.quote(t)
                        link = f"https://www.themoviedb.org/search?query={safe_title}&language=pl-PL"
                        
                        plats = res.get('covered_details', {}).get(t, [])
                        plat_label = f" `[{', '.join(plats)}]`" if plats else ""
                        
                        chk_key = f"chk_{t}"
                        if chk_key not in st.session_state:
                            st.session_state[chk_key] = (t in res['watched_temp'])
                            
                        st.checkbox(f"[{t.title()}]({link}){plat_label}", key=chk_key, on_change=toggle_watched_status, args=(t,))
                    
                    st.write("")
                    if st.button("🏁 Zakończ ten plan rozliczeniowy", type="primary", use_container_width=True):
                        watched = res.get('watched_temp', [])
                        unwatched = [t for t in res.get('covered', []) if t not in watched]
                        confirm_cycle_closure(watched, unwatched)
                else:
                    st.write("*Brak tytułów do obejrzenia.*")
                    if st.button("🏁 Zakończ ten plan rozliczeniowy", type="primary", use_container_width=True):
                        confirm_cycle_closure([], [])
        else:
            st.info("Zatwierdź plan z lewej strony, aby rozpocząć nowy cykl rozliczeniowy.")
            
        st.write("---")
        st.subheader("Kupka wstydu na kolejny miesiąc ⏳")
        
        if 'wait_avail' not in st.session_state:
            st.session_state['wait_avail'] = {}
        if 'wait_details' not in st.session_state:
            st.session_state['wait_details'] = {}

        if st.session_state['waiting_room']:
            missing = [item for item in st.session_state['waiting_room'] if item not in st.session_state['wait_avail'] or item not in st.session_state['wait_details']]
            if missing:
                with st.spinner("Analizuję zasoby Twojej kupki wstydu..."):
                    for item in missing:
                        avail, poster, rating, meta_info = fetch_tmdb_details(item)
                        st.session_state['wait_avail'][item] = avail
                        st.session_state['wait_details'][item] = {
                            "poster": poster,
                            "rating": rating,
                            "meta": meta_info
                        }
            
            platform_counts = {p: 0 for p in PLATFORMS.keys()}
            for item in st.session_state['waiting_room']:
                for p in st.session_state['wait_avail'].get(item, []):
                    if p in platform_counts:
                        platform_counts[p] += 1
            
            active_counts = {p: c for p, c in platform_counts.items() if c > 0}
            if active_counts:
                counts_str = " | ".join([f"{p}: {c}" for p, c in active_counts.items()])
                st.caption(f"**Podsumowanie zaległości:** {counts_str}")
                
            recommended = [p for p, c in active_counts.items() if c >= 3]
            if recommended:
                st.info(f"💡 **Wskazówka na przyszłość:** W kolejnym miesiącu warto rozważyć wykupienie: **{', '.join(recommended)}**.")
                
            sorted_waiting_room = sorted(list(st.session_state['waiting_room']))
            for i, item in enumerate(sorted_waiting_room):
                with st.container(border=True):
                    col_thumb, col_text, col_btn = st.columns([1, 4.6, 1.4])
                    details = st.session_state['wait_details'].get(item, {})
                    w_poster = details.get("poster")
                    w_rating = details.get("rating")
                    w_meta = details.get("meta", {})
                    display_name = w_meta.get("matched_title") or item.title()

                    with col_thumb:
                        if w_poster:
                            st.markdown(f'<img src="{w_poster}" style="width: 52px; aspect-ratio: 2/3; object-fit: cover; border-radius: 6px; box-shadow: 0 2px 5px rgba(0,0,0,0.35);">', unsafe_allow_html=True)
                        else:
                            st.markdown('<div style="width: 52px; aspect-ratio: 2/3; background-color: #1e1e1e; border-radius: 6px; display: flex; align-items: center; justify-content: center; font-size: 1.2em;">🎬</div>', unsafe_allow_html=True)

                    with col_text:
                        safe_title = urllib.parse.quote(item)
                        link = w_meta.get("tmdb_url") or f"https://www.themoviedb.org/search?query={safe_title}&language=pl-PL"
                        platforms = st.session_state['wait_avail'].get(item, [])
                        plat_str = "".join([platform_chip(p) for p in platforms]) if platforms else '<span style="color: gray; font-size: 0.8em;">Brak w abonamentach</span>'
                        st.markdown(
                            f"**[{display_name}]({link})** {rating_badge(w_rating)}{meta_badge(w_meta)}<br>{plat_str}",
                            unsafe_allow_html=True
                        )
                    with col_btn:
                        b_tr, b_del = st.columns(2)
                        with b_tr:
                            if st.button("▶️", key=f"tr_wait_{i}_{item}", help="Obejrzyj zwiastun"):
                                show_trailer_dialog(display_name, w_meta.get("media_type"), w_meta.get("item_id"))
                        with b_del:
                            if st.button("❌", key=f"del_wait_{i}_{item}", help="Usuń z kupki wstydu"):
                                st.session_state['waiting_room'].remove(item)
                                save_data(st.session_state['logged_in_user'], {
                                    "poczekalnia": st.session_state['waiting_room'],
                                    "historia_wydatkow": st.session_state['history'],
                                    "target_budget": st.session_state['target_budget'],
                                    "current_spend": st.session_state['current_spend']
                                })
                                st.session_state['toast_msg'] = (f"Usunięto {item.title()} z kupki wstydu", "🗑️")
                                st.rerun()
        else:
            st.write("*Pusto. Jesteś na bieżąco!*")

        if st.session_state['history']:
            st.write("---")
            
            # 1. Wykres i kamienie milowe oszczędności
            with st.expander("📊 Trend Twoich oszczędności i nagrody (Wykres)", expanded=True):
                closed_history = [h for h in st.session_state.get('history', []) if h.get('is_closed', False)]
                
                if closed_history:
                    chart_history = closed_history[-12:] 
                    current_spend_base = st.session_state.get('current_spend', 0) or st.session_state.get('target_budget', 0)
                    
                    start_idx = len(closed_history) - len(chart_history)
                    chart_rows = []
                    for i, h in enumerate(chart_history):
                        val = round(float(h.get('savings', current_spend_base - h.get('cost', 0))), 2)
                        cost_val = round(float(h.get('cost', 0)), 2)
                        chart_rows.append({
                            "Cykl": f"#{start_idx + i + 1} ({h.get('month', '').split()[0]})",
                            "Kolejność": i,
                            "Oszczędność (PLN)": val,
                            "Wydano (PLN)": cost_val,
                            "Platformy": ", ".join(h.get('combo', [])) or "Brak"
                        })
                    
                    if total_saved > 0:
                        cinema_tickets = int(total_saved // 32)
                        pizzas = int(total_saved // 45)
                        free_months = round(total_saved / max(st.session_state.get('target_budget', 60.0), 1.0), 1)
                        st.markdown(
                            f"""
                            <div style="background: rgba(22, 163, 74, 0.12); border: 1px solid rgba(22, 163, 74, 0.35); border-radius: 12px; padding: 10px 14px; margin-bottom: 14px; font-size: 0.86rem;">
                                🏆 <b>Twoje oszczędności ({total_saved:.2f} zł) to równowartość:</b><br>
                                🎟️ <b>{cinema_tickets}</b> biletów do kina &nbsp;•&nbsp; 🍕 <b>{pizzas}</b> dużych pizz &nbsp;•&nbsp; 🍿 <b>{free_months}</b> mies. budżetu VOD gratis!
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                    st.caption("Ostatnie zamknięte cykle rozliczeniowe (najedź na słupek po szczegóły):")
                    st.vega_lite_chart(
                        chart_rows,
                        {
                            "height": 230,
                            "background": "transparent",
                            "mark": {
                                "type": "bar",
                                "cornerRadiusTopLeft": 8,
                                "cornerRadiusTopRight": 8,
                            },
                            "encoding": {
                                "x": {
                                    "field": "Cykl",
                                    "type": "ordinal",
                                    "sort": {"field": "Kolejność"},
                                    "axis": {"labelAngle": 0, "title": None, "labelColor": "#9ca3af"},
                                },
                                "y": {
                                    "field": "Oszczędność (PLN)",
                                    "type": "quantitative",
                                    "axis": {"title": "Zaoszczędzono (PLN)", "gridColor": "rgba(255,255,255,0.07)", "labelColor": "#9ca3af", "titleColor": "#9ca3af"},
                                },
                                "color": {
                                    "condition": {"test": "datum['Oszczędność (PLN)'] >= 0", "value": "#E50914"},
                                    "value": "#6b7280",
                                },
                                "tooltip": [
                                    {"field": "Cykl", "type": "ordinal", "title": "Cykl"},
                                    {"field": "Oszczędność (PLN)", "type": "quantitative", "title": "Zaoszczędzono (PLN)", "format": ".2f"},
                                    {"field": "Wydano (PLN)", "type": "quantitative", "title": "Koszt pakietu (PLN)", "format": ".2f"},
                                    {"field": "Platformy", "type": "ordinal", "title": "Wybrane platformy"},
                                ],
                            },
                        },
                        use_container_width=True,
                    )
                else:
                    st.info("Zamknij swój pierwszy cykl, aby zobaczyć wykres oszczędności i przelicznik nagród!")
            
            st.write("---")
            
            # 2. Główny ekspander na całą historię – domyślnie zwinięty
            with st.expander("📜 Historia cykli (szczegóły)"):
                history_list = st.session_state.get('history', [])
                
                if history_list:
                    # Wyciągamy unikalne lata i sortujemy malejąco
                    available_years = sorted(list(set([h.get('month', ' 2026').split()[-1] for h in history_list])), reverse=True)
                    
                    # Dla każdego roku tworzymy OSOBNY ROZWIJANY EKSPANDER (zamiast zakładek)
                    for year in available_years:
                        with st.expander(f"📅 Rok {year}"):
                            history_for_year = [h for h in history_list if h.get('month', '').endswith(year)]
                            
                            # Wewnątrz danego roku są zwinięte karty poszczególnych miesięcy
                            for h in reversed(history_for_year):
                                is_closed = h.get('is_closed', False)
                                status_icon = "✅" if is_closed else "⏳"
                                status_text = "Zamknięty" if is_closed else "Otwarty"
                                
                                with st.expander(f"{h.get('month', 'Nieznany')} ({status_icon} {status_text})"):
                                    cost = h.get('cost', 0)
                                    current_spend_base = st.session_state.get('current_spend', 0) or st.session_state.get('target_budget', 0)
                                    savings = h.get('savings', current_spend_base - cost)
                                    
                                    platforms = h.get('combo', [])
                                    plats_html = "".join([platform_chip(p) for p in platforms]) if platforms else "*Brak*"
                                    
                                    st.markdown(f"**Zakupiono:** {plats_html} *(Koszt: {cost:.2f} PLN | Zaoszczędzono: {savings:.2f} PLN)*", unsafe_allow_html=True)
                                    st.write("")
                                    
                                    watched = h.get('covered', [])
                                    if watched:
                                        st.write("**Obejrzano:**")
                                        for title in watched:
                                            st.write(f"- {title.title()}")
                                    else:
                                        st.write("*Brak odhaczonych tytułów w tym cyklu.*")
                else:
                    st.write("*Brak historii do wyświetlenia.*")

with tab_settings:
    st.header("⚙️ Ustawienia cen subskrypcji")
    st.write("Edytuj ceny, jeśli operator wprowadzi podwyżki. Zmiany wpłyną na Twoje przyszłe obliczenia.")
    
    c_set1, c_set2 = st.columns(2)
    platforms_list = list(st.session_state['platform_prices'].items())
    half = (len(platforms_list) + 1) // 2
    
    with c_set1:
        for p_name, p_data in platforms_list[:half]:
            new_price = st.number_input(f"{p_name} (PLN)", value=float(p_data['price']), step=1.0, min_value=0.0)
            if st.session_state['platform_prices'][p_name]['price'] != new_price:
                st.session_state['platform_prices'][p_name]['price'] = new_price
                
    with c_set2:
        for p_name, p_data in platforms_list[half:]:
            new_price = st.number_input(f"{p_name} (PLN)", value=float(p_data['price']), step=1.0, min_value=0.0)
            if st.session_state['platform_prices'][p_name]['price'] != new_price:
                st.session_state['platform_prices'][p_name]['price'] = new_price

    c_save_p1, c_save_p2 = st.columns(2)
    with c_save_p1:
        if st.button("💾 Zapisz nowe ceny w chmurze", type="primary", use_container_width=True):
            save_data(st.session_state['logged_in_user'], {
                "poczekalnia": st.session_state['waiting_room'],
                "historia_wydatkow": st.session_state['history'],
                "target_budget": st.session_state['target_budget'],
                "current_spend": st.session_state['current_spend']
            })
            st.session_state['toast_msg'] = ("Nowe ceny subskrypcji zostały zapisane!", "💾")
            st.rerun()
    with c_save_p2:
        if st.button("↺ Przywróć domyślne ceny rynkowe", type="secondary", use_container_width=True):
            st.session_state['platform_prices'] = copy.deepcopy(PLATFORMS)
            save_data(st.session_state['logged_in_user'], {
                "poczekalnia": st.session_state['waiting_room'],
                "historia_wydatkow": st.session_state['history'],
                "target_budget": st.session_state['target_budget'],
                "current_spend": st.session_state['current_spend']
            })
            st.session_state['toast_msg'] = ("Przywrócono domyślne ceny rynkowe", "↺")
            st.rerun()

    st.write("---")
    st.header("🗑️ Strefa niebezpieczna")
    st.caption("Poniższe akcje usuną część lub całość Twoich danych. Bądź ostrożny.")
    
    c_danger1, c_danger2 = st.columns(2)
    
    with c_danger1:
        if st.button("Resetuj ustawienia budżetu (powrót do ankiety)", type="secondary", use_container_width=True):
            st.session_state['target_budget'] = None
            st.session_state['current_spend'] = None
            save_data(st.session_state['logged_in_user'], {
                "poczekalnia": st.session_state['waiting_room'],
                "historia_wydatkow": st.session_state['history'],
                "target_budget": None,
                "current_spend": None
            })
            st.rerun()
            
    with c_danger2:
        if st.button("Wyczyść całe konto (Hard Reset)", type="primary", use_container_width=True):
            confirm_hard_reset()