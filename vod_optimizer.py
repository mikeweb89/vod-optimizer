import streamlit as st
import requests
import copy
import itertools
from datetime import datetime, timedelta
import urllib.parse
import hashlib
import os
import base64
from supabase import create_client, Client
import pandas as pd


@st.cache_data
def get_logo_base64() -> str:
    for fname in ("logo_icon.png", "logo.png", "logo.jpg"):
        fpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)
        if os.path.exists(fpath):
            with open(fpath, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            mime = "image/png" if fname.endswith(".png") else "image/jpeg"
            return f"data:{mime};base64,{b64}"
    return ""


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
_icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo_icon.png")
st.set_page_config(
    page_title="Optymalizator Subskrypcji VOD",
    page_icon=_icon_path if os.path.exists(_icon_path) else "🍿",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --- NOWOCZESNY DESIGN (CSS) ---
modern_ui = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@600;700;800&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

/* Ukrywamy śmieci, pusty pasek boczny i czarny pasek nagłówka Streamlita */
#MainMenu {visibility: hidden;}
div[data-testid="stAppDeployButton"] {display: none;}
footer {visibility: hidden;}
header[data-testid="stHeader"] {
    display: none !important;
}
section[data-testid="stSidebar"], div[data-testid="collapsedControl"] {
    display: none !important;
}
/* Ukrywamy osierocony dymek wykresu Vega-Lite (#vg-tooltip-element) po wyjściu z zakładki Statystyki */
#vg-tooltip-element {
    display: none !important;
}
body:has([data-testid="stVegaLiteChart"]:hover) #vg-tooltip-element.visible {
    display: block !important;
}

/* Kinowe tło z delikatną poświatą i nowoczesna typografia */
.stApp {
    background: radial-gradient(circle at 50% 0%, rgba(229, 9, 20, 0.15) 0%, rgba(90, 46, 152, 0.08) 35%, #0b0d13 70%) !important;
    font-family: 'Plus Jakarta Sans', sans-serif !important;
}

/* Wyśrodkowanie i optymalna szerokość na dużych monitorach */
.block-container {
    max-width: 1560px !important;
    padding-top: 1.1rem !important;
    padding-bottom: 3rem !important;
    margin: 0 auto !important;
}

h1, h2, h3 {
    font-family: 'Outfit', sans-serif !important;
    letter-spacing: -0.02em;
}

/* Pasek nawigacyjny spójny kolorystycznie z ciemnym kinowym motywem (Glassmorphism) */
div[data-testid="stHorizontalBlock"]:has(.tmdb-navbar-brand) {
    background: linear-gradient(135deg, rgba(255, 255, 255, 0.055) 0%, rgba(229, 9, 20, 0.08) 50%, rgba(255, 255, 255, 0.02) 100%) !important;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
    border-radius: 18px !important;
    padding: 10px 24px !important;
    margin-bottom: 16px !important;
    align-items: center !important;
    backdrop-filter: blur(14px) !important;
    box-shadow: 0 10px 28px rgba(0, 0, 0, 0.35) !important;
}
/* Idealne wyśrodkowanie w pionie wszystkich elementów w pasku */
div[data-testid="stHorizontalBlock"]:has(.tmdb-navbar-brand) > div[data-testid="stColumn"] {
    display: flex !important;
    flex-direction: column !important;
    justify-content: center !important;
}
div[data-testid="stHorizontalBlock"]:has(.tmdb-navbar-brand) div[data-testid="stMarkdownContainer"],
div[data-testid="stHorizontalBlock"]:has(.tmdb-navbar-brand) div[data-testid="stElementContainer"] {
    margin: 0 !important;
    padding: 0 !important;
}
.tmdb-navbar-brand {
    display: flex;
    align-items: center;
    gap: 14px;
    user-select: none;
    margin: 0;
    padding: 0;
}
.tmdb-navbar-logo {
    height: 46px;
    width: auto;
    object-fit: contain;
    display: block;
    filter: drop-shadow(0 4px 10px rgba(229, 9, 20, 0.35));
}
.tmdb-brand-text {
    display: flex;
    flex-direction: column;
    justify-content: center;
    line-height: 1.08;
}
.tmdb-brand-top {
    font-family: 'Outfit', sans-serif;
    font-weight: 800;
    font-size: 1.18rem;
    color: #f8fafc;
    letter-spacing: -0.01em;
    margin: 0;
}
.tmdb-brand-sub {
    font-family: 'Outfit', sans-serif;
    font-weight: 800;
    font-size: 0.78rem;
    letter-spacing: 0.13em;
    background: linear-gradient(90deg, #ff4b72 0%, #E50914 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin: 0;
}
/* Przyciski nawigacji wewnątrz górnego paska */
div[data-testid="stHorizontalBlock"]:has(.tmdb-navbar-brand) .stButton > button[kind="secondary"] {
    background: transparent !important;
    border: 1px solid transparent !important;
    box-shadow: none !important;
    color: #d1d5db !important;
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    border-radius: 12px !important;
    padding: 7px 14px !important;
}
div[data-testid="stHorizontalBlock"]:has(.tmdb-navbar-brand) .stButton > button[kind="secondary"]:hover {
    background: rgba(255, 255, 255, 0.06) !important;
    border-color: rgba(255, 255, 255, 0.12) !important;
    color: #ffffff !important;
    transform: none !important;
    box-shadow: none !important;
}
div[data-testid="stHorizontalBlock"]:has(.tmdb-navbar-brand) .stButton > button[kind="primary"] {
    background: linear-gradient(135deg, rgba(229, 9, 20, 0.24), rgba(168, 28, 81, 0.22)) !important;
    border: 1px solid rgba(229, 9, 20, 0.55) !important;
    color: #ffffff !important;
    font-weight: 700 !important;
    font-size: 0.95rem !important;
    border-radius: 12px !important;
    padding: 7px 14px !important;
    box-shadow: 0 4px 14px rgba(229, 9, 20, 0.22) !important;
}
/* Okrągły przycisk avatara (P) otwierający menu po kliknięciu */
div[data-testid="stHorizontalBlock"]:has(.tmdb-navbar-brand) div[data-testid="stPopover"] {
    display: flex !important;
    justify-content: flex-end !important;
}
div[data-testid="stHorizontalBlock"]:has(.tmdb-navbar-brand) div[data-testid="stPopover"] button {
    width: 40px !important;
    height: 40px !important;
    min-height: 40px !important;
    padding: 0 !important;
    border-radius: 50% !important;
    background: linear-gradient(135deg, #E50914 0%, #9b1c48 100%) !important;
    border: 1.5px solid rgba(255, 255, 255, 0.25) !important;
    color: #ffffff !important;
    font-family: 'Outfit', sans-serif !important;
    font-weight: 700 !important;
    font-size: 1rem !important;
    box-shadow: 0 4px 12px rgba(229, 9, 20, 0.35) !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    transition: transform 0.2s ease, box-shadow 0.2s ease !important;
}
div[data-testid="stHorizontalBlock"]:has(.tmdb-navbar-brand) div[data-testid="stPopover"] button:hover {
    transform: scale(1.06) !important;
    box-shadow: 0 6px 16px rgba(229, 9, 20, 0.55) !important;
    border-color: rgba(255, 255, 255, 0.5) !important;
}
div[data-testid="stHorizontalBlock"]:has(.tmdb-navbar-brand) div[data-testid="stPopover"] button svg,
div[data-testid="stHorizontalBlock"]:has(.tmdb-navbar-brand) div[data-testid="stPopover"] button span[data-testid="stIconMaterial"],
div[data-testid="stHorizontalBlock"]:has(.tmdb-navbar-brand) div[data-testid="stPopover"] button > div > span:not(:first-child) {
    display: none !important;
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

/* Karty KPI (st.metric) w stylu Glassmorphism — sztywna, identyczna wysokość jak karta z plakietką cykli */
div[data-testid="stMetric"] {
    background: linear-gradient(145deg, rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0.015));
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-left: 4px solid #E50914;
    border-radius: 16px;
    padding: 14px 18px !important;
    height: 142px !important;
    min-height: 142px !important;
    box-sizing: border-box !important;
    display: flex !important;
    flex-direction: column !important;
    justify-content: center !important;
    box-shadow: 0 8px 22px rgba(0, 0, 0, 0.28);
    backdrop-filter: blur(10px);
    transition: transform 0.25s ease, border-color 0.25s ease;
}
div[data-testid="stMetric"]:hover {
    transform: translateY(-3px);
    border-color: rgba(229, 9, 20, 0.6);
}
/* Mniejsza czcionka w metrykach wewnątrz kart (np. Aktywny cykl), żeby kwoty z „zł” nigdy się nie ucinały */
div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stMetric"] {
    padding: 10px 12px !important;
    height: 92px !important;
    min-height: 92px !important;
}
div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stMetricValue"],
div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stMetricValue"] * {
    font-size: 1.38rem !important;
    overflow: visible !important;
    text-overflow: unset !important;
    white-space: nowrap !important;
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
    del st.session_state['toast_msg']
    try:
        st.toast(msg, icon=icon)
    except Exception:
        st.toast(msg, icon="✅")

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
        return f'<span style="background-color: {bg}; color: white; padding: 2px 9px; border-radius: 999px; font-size: 0.78rem; font-weight: 700; display: inline-block; white-space: nowrap; vertical-align: middle; margin-left: 6px; box-shadow: 0 2px 4px rgba(0,0,0,0.25);">⭐ {r:.1f}</span>'
    except:
        return ""

def priority_badge():
    return '<span style="background: linear-gradient(90deg, #dc2626, #ea580c); color: white; padding: 2px 9px; border-radius: 999px; font-size: 0.72rem; font-weight: 700; display: inline-block; white-space: nowrap; vertical-align: middle; margin-left: 6px; letter-spacing: 0.04em; box-shadow: 0 2px 6px rgba(220,38,38,0.4);">🔥 PRIORYTET</span>'

def tvod_chip(name, link=None):
    target_url = link or "#"
    return (
        f'<a href="{target_url}" target="_blank" style="text-decoration: none;">'
        f'<span style="background-color: rgba(234, 179, 8, 0.14); color: #fde047; padding: 3px 10px; border-radius: 10px; font-size: 0.76rem; font-weight: 600; margin-right: 5px; display: inline-block; white-space: nowrap; margin-bottom: 4px; border: 1px solid rgba(234, 179, 8, 0.35);">🎟️ {name}</span>'
        f'</a>'
    )

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
    duration_label = meta.get("duration_label")
    if duration_label:
        parts.append(f"⏱️ {duration_label}")
    if not parts:
        return ""
    label = " &nbsp;•&nbsp; ".join(parts)
    return f'<div style="color: #9ca3af; font-size: 0.82rem; font-weight: 500; margin: 3px 0 6px 0;">{label}</div>'

def build_cancellation_calendar(platforms):
    plat_list = ", ".join(platforms) if platforms else "Subskrypcje VOD"
    remind_dt = datetime.now() + timedelta(days=27)
    start_str = remind_dt.strftime("%Y%m%d")
    end_str = (remind_dt + timedelta(days=1)).strftime("%Y%m%d")
    title = f"Anuluj subskrypcje VOD: {plat_list}"
    details = (
        f"Przypomnienie z aplikacji Optymalizator VOD! Za 3 dni mija miesiąc rozliczeniowy. "
        f"Sprawdź i wyłącz odnawianie dla platform: {plat_list}, jeśli nie planujesz ich na kolejny miesiąc."
    )
    gcal_url = (
        "https://calendar.google.com/calendar/render?action=TEMPLATE"
        f"&text={urllib.parse.quote(title)}"
        f"&dates={start_str}/{end_str}"
        f"&details={urllib.parse.quote(details)}"
    )
    ics_content = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//Optymalizator VOD//PL\r\n"
        "BEGIN:VEVENT\r\n"
        f"DTSTART;VALUE=DATE:{start_str}\r\n"
        f"DTEND;VALUE=DATE:{end_str}\r\n"
        f"SUMMARY:{title}\r\n"
        f"DESCRIPTION:{details}\r\n"
        "BEGIN:VALARM\r\n"
        "TRIGGER:-PT9H\r\n"
        "ACTION:DISPLAY\r\n"
        "DESCRIPTION:Przypomnienie o anulowaniu subskrypcji VOD\r\n"
        "END:VALARM\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    return gcal_url, ics_content, remind_dt.strftime("%d.%m.%Y")

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
if 'priority_titles' not in st.session_state:
    st.session_state['priority_titles'] = []
if 'title_overrides' not in st.session_state:
    st.session_state['title_overrides'] = {}

@st.cache_data(ttl=3600)
def fetch_trailer_tmdb(media_type, item_id):
    if TMDB_API_KEY == "BŁĄD_KLUCZA" or not media_type or not item_id:
        return None
    for lang in ("pl-PL", "en-US"):
        url = f"https://api.themoviedb.org/3/{media_type}/{item_id}/videos?api_key={TMDB_API_KEY}&language={lang}"
        try:
            resp = requests.get(url, timeout=5).json()
            videos = resp.get("results", [])
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
def search_candidates_tmdb(title):
    if TMDB_API_KEY == "BŁĄD_KLUCZA":
        return []
    search_url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={urllib.parse.quote(title.strip())}&language=pl-PL"
    try:
        response = requests.get(search_url, timeout=5).json()
        results = [r for r in response.get('results', []) if r.get('media_type') in ('movie', 'tv')]
        if not results:
            return []

        user_query = title.strip().lower()
        exact_idx = None
        for idx, item in enumerate(results):
            item_title = (item.get('title') or item.get('name') or "").lower()
            item_original = (item.get('original_title') or item.get('original_name') or "").lower()
            if user_query == item_title or user_query == item_original:
                exact_idx = idx
                break
        if exact_idx is not None and exact_idx > 0:
            exact_item = results.pop(exact_idx)
            results.insert(0, exact_item)

        candidates = []
        for item in results[:5]:
            m_type = item.get('media_type')
            m_id = item.get('id')
            m_title = item.get('title') or item.get('name') or title.title()
            raw_date = item.get('release_date') or item.get('first_air_date') or ""
            year = raw_date[:4] if len(raw_date) >= 4 else "brak roku"
            type_pl = "Film" if m_type == "movie" else "Serial"
            candidates.append({
                "key": f"{m_type}:{m_id}",
                "label": f"{m_title} ({year}) • {type_pl}",
                "media_type": m_type,
                "id": m_id,
                "raw": item
            })
        return candidates
    except Exception:
        return []

@st.cache_data(ttl=3600)
def fetch_item_by_id_tmdb(media_type, item_id, fallback_title=""):
    if TMDB_API_KEY == "BŁĄD_KLUCZA" or not media_type or not item_id:
        return [], None, None, {}
    try:
        detail_url = f"https://api.themoviedb.org/3/{media_type}/{item_id}?api_key={TMDB_API_KEY}&language=pl-PL"
        details = requests.get(detail_url, timeout=5).json()

        poster_path = details.get('poster_path')
        vote_avg = details.get('vote_average')
        rating = round(vote_avg, 1) if vote_avg else None
        poster_url = f"https://image.tmdb.org/t/p/w154{poster_path}" if poster_path else None

        matched_title = details.get('title') or details.get('name') or fallback_title.title()
        original_title = details.get('original_title') or details.get('original_name') or ""
        raw_date = details.get('release_date') or details.get('first_air_date') or ""
        year = raw_date[:4] if len(raw_date) >= 4 else None
        overview = (details.get('overview') or "").strip()

        # Obliczanie czasu oglądania
        watch_hours = 2.0
        duration_label = None
        if media_type == "movie":
            runtime = details.get("runtime") or 0
            if runtime > 0:
                h, m = divmod(int(runtime), 60)
                duration_label = f"{h}h {m:02d}m" if h > 0 else f"{m}m"
                watch_hours = round(runtime / 60.0, 1)
            else:
                duration_label = "~2h"
                watch_hours = 2.0
        elif media_type == "tv":
            seasons = details.get("number_of_seasons") or 1
            episodes = details.get("number_of_episodes") or 8
            ep_runtimes = details.get("episode_run_time") or []
            avg_ep = ep_runtimes[0] if ep_runtimes else 45
            eps_per_season = max(1, round(episodes / max(seasons, 1)))
            season_hours = round((eps_per_season * avg_ep) / 60.0, 1)
            watch_hours = season_hours
            sez_word = "sez."
            duration_label = f"{seasons} {sez_word} (~{season_hours:.0f}h / sez.)"

        providers_url = f"https://api.themoviedb.org/3/{media_type}/{item_id}/watch/providers?api_key={TMDB_API_KEY}"
        prov_response = requests.get(providers_url, timeout=5).json()
        pl_data = prov_response.get('results', {}).get('PL', {})
        jw_link = pl_data.get('link', f"https://www.themoviedb.org/{media_type}/{item_id}/watch?locale=PL")

        flatrate_options = pl_data.get('flatrate', [])
        available_platforms = []
        if flatrate_options:
            provider_ids = [prov['provider_id'] for prov in flatrate_options]
            for p_name, p_data in PLATFORMS.items():
                if p_data['jw_id'] in provider_ids:
                    available_platforms.append(p_name)

        # Wypożyczenia / zakup (TVOD)
        rent_buy_raw = (pl_data.get('rent') or []) + (pl_data.get('buy') or [])
        rent_providers = []
        for r_prov in rent_buy_raw:
            r_name = r_prov.get('provider_name', '')
            # Skracamy popularne nazwy dla czytelności pigułek
            clean_r = (
                r_name.replace("Apple TV", "Apple TV")
                .replace("Amazon Video", "Prime Video (Wypożycz)")
                .replace("Google Play Movies", "Google TV")
                .replace("Rakuten TV", "Rakuten TV")
                .replace("Premiery Canal+", "Premiery Canal+")
            )
            if clean_r and clean_r not in rent_providers:
                rent_providers.append(clean_r)

        meta_info = {
            "item_id": item_id,
            "matched_title": matched_title,
            "original_title": original_title,
            "media_type": media_type,
            "year": year,
            "overview": overview,
            "duration_label": duration_label,
            "watch_hours": watch_hours,
            "rent_providers": rent_providers[:4],
            "jw_link": jw_link,
            "tmdb_url": f"https://www.themoviedb.org/{media_type}/{item_id}?language=pl-PL" if item_id else None,
        }
        return available_platforms, poster_url, rating, meta_info
    except Exception:
        return [], None, None, {}

def fetch_tmdb_details(title, forced_key=None):
    candidates = search_candidates_tmdb(title)
    if not candidates:
        return [], None, None, {}
    chosen = candidates[0]
    if forced_key:
        for c in candidates:
            if c["key"] == forced_key:
                chosen = c
                break
    avail, poster, rating, meta_info = fetch_item_by_id_tmdb(chosen["media_type"], chosen["id"], title)
    meta_info["candidates"] = [{"key": c["key"], "label": c["label"]} for c in candidates]
    meta_info["selected_key"] = chosen["key"]
    return avail, poster, rating, meta_info

def fetch_availability_tmdb(title):
    avail, poster, rating, _ = fetch_tmdb_details(title)
    return avail, poster, rating

def optimize_subscriptions_smart(titles_availability, budget=None, priorities=None):
    platform_names = list(PLATFORMS.keys())
    priorities_set = set(priorities or [])
    combos_1 = list(itertools.combinations(platform_names, 1))
    combos_2 = list(itertools.combinations(platform_names, 2))
    all_combos = combos_1 + combos_2

    best_overall = {"combo": [], "score": -1, "covered_count": -1, "cost": float("inf")}
    best_in_budget = {"combo": [], "score": -1, "covered_count": -1, "cost": float("inf")}

    for combo in all_combos:
        covered_titles = [
            title for title, available_on in titles_availability.items()
            if any(p in combo for p in available_on)
        ]
        coverage_count = len(covered_titles)
        if coverage_count == 0:
            continue
        # Tytuły z priorytetem liczą się podwójnie (waga 2x)
        weighted_score = sum(2 if t in priorities_set else 1 for t in covered_titles)
        combo_cost = sum(st.session_state['platform_prices'][p]["price"] for p in combo)

        # Najlepsza opcja ogółem
        if (
            weighted_score > best_overall["score"]
            or (weighted_score == best_overall["score"] and coverage_count > best_overall["covered_count"])
            or (weighted_score == best_overall["score"] and coverage_count == best_overall["covered_count"] and combo_cost < best_overall["cost"])
        ):
            best_overall = {
                "combo": list(combo),
                "score": weighted_score,
                "covered_count": coverage_count,
                "cost": combo_cost,
            }

        # Najlepsza opcja mieszcząca się w budżecie
        if budget is not None and budget > 0 and combo_cost <= budget:
            if (
                weighted_score > best_in_budget["score"]
                or (weighted_score == best_in_budget["score"] and coverage_count > best_in_budget["covered_count"])
                or (weighted_score == best_in_budget["score"] and coverage_count == best_in_budget["covered_count"] and combo_cost < best_in_budget["cost"])
            ):
                best_in_budget = {
                    "combo": list(combo),
                    "score": weighted_score,
                    "covered_count": coverage_count,
                    "cost": combo_cost,
                }

    # Jeśli mamy sensowny pakiet w budżecie, rekomendujemy go jako główny!
    if best_in_budget["covered_count"] > 0:
        alt_above = None
        if best_overall["covered_count"] > best_in_budget["covered_count"]:
            alt_above = best_overall
        return best_in_budget["combo"], alt_above, True

    return best_overall["combo"], None, False

def optimize_subscriptions(titles_availability):
    combo, _, _ = optimize_subscriptions_smart(
        titles_availability,
        budget=st.session_state.get('target_budget'),
        priorities=st.session_state.get('priority_titles', []),
    )
    return combo

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
    _, col_login, _ = st.columns([1, 2, 1])
    
    with col_login:
        st.write("")
        st.write("")
        with st.container(border=True):
            logo_b64 = get_logo_base64()
            logo_img_html = f'<img src="{logo_b64}" style="height: 86px; margin-bottom: 8px; filter: drop-shadow(0 6px 14px rgba(229,9,20,0.35));" />' if logo_b64 else "🎬"
            st.markdown(
                f"""
                <div style="text-align: center; padding-top: 6px;">
                    {logo_img_html}
                    <div style="font-family: 'Outfit', sans-serif; font-weight: 800; font-size: 1.65rem; color: #f8fafc; line-height: 1.1;">Optymalizator</div>
                    <div style="font-family: 'Outfit', sans-serif; font-weight: 800; font-size: 1.05rem; letter-spacing: 0.14em; background: linear-gradient(90deg, #ff4b72, #c81e5b); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 6px;">SUBSKRYPCJI</div>
                    <p style="color: #9ca3af; font-size: 0.9rem; margin-bottom: 4px;">Zaloguj się lub zarejestruj, aby zarządzać subskrypcjami</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
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
# GŁÓWNY INTERFEJS — GÓRNY PASEK NAWIGACYJNY (STYL TMDB)
# ==========================================
if "active_nav" not in st.session_state:
    st.session_state["active_nav"] = "planer"

logo_b64 = get_logo_base64()
logo_html = f'<img src="{logo_b64}" class="tmdb-navbar-logo" alt="Logo" />' if logo_b64 else '<span style="font-size:1.8rem;">🍿</span>'
user_email_str = st.session_state.get("logged_in_user") or "U"
user_initial = user_email_str[0].upper()
wait_count = len(st.session_state.get("waiting_room", []))
wait_label = f"Kupka wstydu ({wait_count})" if wait_count > 0 else "Kupka wstydu"

nav_brand, nav_b1, nav_b2, nav_b3, nav_b4, nav_spacer, nav_prof = st.columns(
    [2.6, 1.0, 1.4, 1.1, 1.1, 1.2, 0.6], vertical_alignment="center"
)

with nav_brand:
    st.markdown(
        f"""
        <div class="tmdb-navbar-brand">
            {logo_html}
            <div class="tmdb-brand-text">
                <div class="tmdb-brand-top">Optymalizator</div>
                <div class="tmdb-brand-sub">SUBSKRYPCJI</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with nav_b1:
    if st.button("Planer", key="nav_planer", type="primary" if st.session_state["active_nav"] == "planer" else "secondary", use_container_width=True):
        st.session_state["active_nav"] = "planer"
        st.rerun()

with nav_b2:
    if st.button(wait_label, key="nav_waiting", type="primary" if st.session_state["active_nav"] == "waiting" else "secondary", use_container_width=True):
        st.session_state["active_nav"] = "waiting"
        st.rerun()

with nav_b3:
    if st.button("Statystyki", key="nav_stats", type="primary" if st.session_state["active_nav"] == "stats" else "secondary", use_container_width=True):
        st.session_state["active_nav"] = "stats"
        st.rerun()

with nav_b4:
    if st.button("Ustawienia", key="nav_settings", type="primary" if st.session_state["active_nav"] == "settings" else "secondary", use_container_width=True):
        st.session_state["active_nav"] = "settings"
        st.rerun()

with nav_spacer:
    st.write("")

with nav_prof:
    with st.popover(user_initial):
        st.markdown(f"<span style='font-size: 0.8em; color: gray;'>Zalogowano jako:</span><br><b>{user_email_str}</b>", unsafe_allow_html=True)
        st.write("---")
        if st.button("Wyloguj 🚪", use_container_width=True):
            st.session_state['logged_in_user'] = None
            st.session_state['cloud_loaded'] = False
            st.rerun()

# Karuzela plakatów ładuje się pod paskiem nawigacyjnym
display_marquee()

# Szybkie zsumowanie oszczędności z zamkniętych cykli (spójne w całej aplikacji)
closed_cycles = [h for h in st.session_state['history'] if h.get('is_closed', False)]
total_saved = sum([h.get("savings", st.session_state['current_spend'] - h.get("cost", 0)) for h in closed_cycles])

kpi1, kpi2, kpi3 = st.columns(3)
with kpi1:
    st.metric("🎯 Twój limit", f"{st.session_state['target_budget']:.2f} zł")
with kpi2:
    st.metric("💳 Dawne wydatki", f"{st.session_state['current_spend']:.2f} zł")
with kpi3:
    st.metric("💰 Zaoszczędzono", f"{total_saved:.2f} zł", delta=f"{len(closed_cycles)} cykli" if total_saved > 0 else None)

st.write("")

if st.session_state["active_nav"] == "planer":
    col1, col2 = st.columns([1.0, 1.0], gap="large")

    with col1:
        st.subheader("1. Co chcesz obejrzeć?")

        def add_to_pending(raw_text):
            if not raw_text:
                return
            parts = [p.strip() for chunk in raw_text.replace(";", ",").split("\n") for p in chunk.split(",") if p.strip()]
            added_any = False
            existing_lower = [x.lower() for x in st.session_state['pending_titles']]
            for part in parts:
                if part.lower() not in existing_lower:
                    st.session_state['pending_titles'].append(part)
                    existing_lower.append(part.lower())
                    added_any = True
            if added_any and len(parts) == 1:
                st.session_state["toast_msg"] = (f"Dodano „{parts[0]}”", "🎬")
            elif added_any:
                st.session_state["toast_msg"] = (f"Dodano {len(parts)} tytułów", "🎬")

        with st.form("add_title_form", clear_on_submit=True, border=False):
            f_col1, f_col2 = st.columns([4, 1])
            with f_col1:
                new_title_input = st.text_input(
                    "Dodaj film lub serial:",
                    placeholder="Wpisz tytuł (lub kilka po przecinku) i wciśnij Enter...",
                    label_visibility="collapsed",
                )
            with f_col2:
                submitted_title = st.form_submit_button("➕ Dodaj", use_container_width=True)
            if submitted_title and new_title_input.strip():
                add_to_pending(new_title_input)
                st.rerun()

        if st.session_state['pending_titles']:
            pill_cols = st.columns(3)
            for p_idx, p_title in enumerate(list(st.session_state['pending_titles'])):
                with pill_cols[p_idx % 3]:
                    if st.button(f"✕ {p_title}", key=f"rm_pending_{p_idx}_{p_title}", use_container_width=True):
                        st.session_state['pending_titles'].remove(p_title)
                        st.rerun()

        trending_items = fetch_trending_tmdb()
        if trending_items:
            with st.expander("🔥 Hity tygodnia (dodaj 1 kliknięciem)"):
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

        include_waiting_room = st.checkbox("Uwzględnij moją Kupkę wstydu", value=True)
        
        if st.button("Sprawdź dostępność i dobierz pakiet 🔍", type="primary", use_container_width=True):
            current_titles = list(st.session_state['pending_titles'])
            
            if include_waiting_room:
                all_titles = list(dict.fromkeys(current_titles + st.session_state['waiting_room']))
            else:
                all_titles = list(dict.fromkeys(current_titles))
            
            if not all_titles:
                st.warning("Dodaj przynajmniej jeden tytuł!")
            else:
                with st.spinner("Sprawdzam dostępność w TMDB... 🎬"):
                    st.session_state['titles_to_check'] = all_titles
                    availability, posters, ratings, metas = {}, {}, {}, {}
                    for title in all_titles:
                        forced_k = st.session_state['title_overrides'].get(title)
                        avail, poster, rating, meta_info = fetch_tmdb_details(title, forced_key=forced_k)
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

        if st.session_state['current_availability']:
            st.write("---")
            st.subheader("2. Dopasowane tytuły i pakiet")
            
            availability = st.session_state['current_availability']
            posters = st.session_state.get('current_posters', {})
            ratings = st.session_state.get('current_ratings', {})
            metas = st.session_state.get('current_metas', {})
            
            titles_list = list(availability.keys())
            for title in titles_list:
                is_prio = title in st.session_state['priority_titles']
                with st.container(border=True):
                    c_img, c_info, c_action = st.columns([0.9, 3.8, 1.1])
                    with c_img:
                        poster_url = posters.get(title)
                        if poster_url:
                            st.markdown(f'<img src="{poster_url}" style="width: 82px; aspect-ratio: 2/3; object-fit: cover; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.4);">', unsafe_allow_html=True)
                        else:
                            st.markdown('<div style="width: 82px; aspect-ratio: 2/3; background-color: #1e1e1e; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 1.5em;">🎬</div>', unsafe_allow_html=True)
                    
                    with c_info:
                        rating = ratings.get(title)
                        meta = metas.get(title, {})
                        display_title = meta.get("matched_title") or title.title()
                        prio_html = priority_badge() if is_prio else ""
                        overview = meta.get("overview", "")
                        short_overview = (overview[:175] + "...") if len(overview) > 178 else overview
                        overview_html = f'<div style="color: #9ca3af; font-size: 0.84rem; line-height: 1.4; margin-bottom: 8px;">{short_overview}</div>' if short_overview else ""

                        st.markdown(
                            f"<div style='font-size: 1.12rem; font-weight: 700; color: #f8fafc;'>{display_title} {rating_badge(rating)}{prio_html}</div>"
                            f"{meta_badge(meta)}"
                            f"{overview_html}",
                            unsafe_allow_html=True,
                        )
                        
                        platforms = availability.get(title, [])
                        rent_providers = meta.get("rent_providers", [])
                        jw_link = meta.get("jw_link") or meta.get("tmdb_url")
                        if platforms:
                            platforms_links = "".join([platform_chip(p) for p in platforms])
                            st.markdown(platforms_links, unsafe_allow_html=True)
                        elif rent_providers:
                            tvod_html = "".join([tvod_chip(r, jw_link) for r in rent_providers[:3]])
                            st.markdown(tvod_html, unsafe_allow_html=True)
                        else:
                            st.caption("Brak w abonamentach i wypożyczalniach VOD.")

                        history_match = get_watch_history(title, st.session_state['history'])
                        if history_match:
                            st.caption(f"💡 *Oglądano już w: {history_match}*")
                            
                    with c_action:
                        if st.button("🔥 Priorytet" if is_prio else "⭐ Priorytet", key=f"prio_{title}", use_container_width=True, help="Nadaj wagę 2x przy doborze platform"):
                            if is_prio:
                                st.session_state['priority_titles'].remove(title)
                            else:
                                st.session_state['priority_titles'].append(title)
                            st.rerun()
                        b_tr, b_del = st.columns(2)
                        with b_tr:
                            if st.button("▶️", key=f"trailer_{title}", use_container_width=True, help="Obejrzyj zwiastun"):
                                show_trailer_dialog(display_title, meta.get("media_type"), meta.get("item_id"))
                        with b_del:
                            if st.button("🗑️", key=f"discard_{title}", use_container_width=True, help="Odrzuć tytuł"):
                                if title in st.session_state['titles_to_check']:
                                    st.session_state['titles_to_check'].remove(title)
                                if title in st.session_state['current_availability']:
                                    del st.session_state['current_availability'][title]
                                if title in st.session_state['priority_titles']:
                                    st.session_state['priority_titles'].remove(title)
                                st.rerun()

                    candidates = meta.get("candidates", [])
                    if len(candidates) > 1:
                        with st.expander("🔄 Chodziło o inną wersję tego tytułu?"):
                            options_keys = [c["key"] for c in candidates]
                            options_labels = {c["key"]: c["label"] for c in candidates}
                            current_k = meta.get("selected_key", options_keys[0])
                            cur_idx = options_keys.index(current_k) if current_k in options_keys else 0
                            new_k = st.selectbox(
                                "Wybierz dopasowanie z bazy TMDB:",
                                options=options_keys,
                                index=cur_idx,
                                format_func=lambda k: options_labels.get(k, k),
                                key=f"cand_sel_{title}",
                            )
                            if new_k != current_k:
                                st.session_state['title_overrides'][title] = new_k
                                avail_n, poster_n, rating_n, meta_n = fetch_tmdb_details(title, forced_key=new_k)
                                st.session_state['current_availability'][title] = avail_n
                                st.session_state['current_posters'][title] = poster_n
                                st.session_state['current_ratings'][title] = rating_n
                                st.session_state['current_metas'][title] = meta_n
                                st.rerun()

            if st.session_state['current_availability']:
                with st.container(border=True):
                    suggested_combo, alt_above, fits_in_budget = optimize_subscriptions_smart(
                        st.session_state['current_availability'],
                        budget=st.session_state['target_budget'],
                        priorities=st.session_state['priority_titles'],
                    )
                    if suggested_combo:
                        badge_txt = "w budżecie" if fits_in_budget else "ponad limit"
                        rec_chips = "".join([platform_chip(p) for p in suggested_combo])
                        st.markdown(f"💡 **Rekomendacja ({badge_txt}):** {rec_chips}", unsafe_allow_html=True)
                        if fits_in_budget and alt_above and alt_above.get("combo"):
                            alt_chips = "".join([platform_chip(p) for p in alt_above["combo"]])
                            st.markdown(
                                f"<div style='font-size: 0.84rem; color: #9ca3af; margin-bottom: 8px;'>💎 <i>Pełniejsze pokrycie ponad budżet ({alt_above['cost']:.2f} zł — {alt_above['covered_count']}/{len(st.session_state['titles_to_check'])} tyt.):</i> {alt_chips}</div>",
                                unsafe_allow_html=True,
                            )
                    
                    selected_platforms = st.multiselect(
                        "Wybrane platformy na ten cykl:", 
                        options=list(PLATFORMS.keys()), 
                        default=suggested_combo
                    )
                    
                    live_cost = sum(st.session_state['platform_prices'][p]["price"] for p in selected_platforms)
                    live_left = st.session_state['target_budget'] - live_cost
                    covered_now = [
                        t for t in st.session_state['titles_to_check']
                        if any(p in selected_platforms for p in st.session_state['current_availability'].get(t, []))
                    ]
                    uncovered_now = [t for t in st.session_state['titles_to_check'] if t not in covered_now]
                    live_covered_count = len(covered_now)
                    total_checked_count = len(st.session_state['titles_to_check'])
                    cost_per_title = (live_cost / live_covered_count) if live_covered_count > 0 else 0.0
                    total_hours = sum(metas.get(t, {}).get("watch_hours", 2.0) for t in covered_now)

                    budget_color = "#ef4444" if live_cost > st.session_state['target_budget'] else "#22c55e"
                    budget_note = f"przekroczono o {abs(live_left):.0f} zł" if live_cost > st.session_state['target_budget'] else f"zostaje {live_left:.0f} zł"

                    st.markdown(
                        f"""
                        <div style="display:flex; justify-content:space-between; background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); border-radius:12px; padding:10px 14px; margin:8px 0 12px 0; font-size:0.86rem;">
                            <div>💸 <b>{live_cost:.2f} zł</b> <span style="color:{budget_color};">({budget_note})</span></div>
                            <div>🎯 <b>{live_covered_count}/{total_checked_count} tyt.</b> <span style="color:#9ca3af;">({cost_per_title:.1f} zł/tyt.)</span></div>
                            <div>⏱️ <b>~{total_hours:.0f}h</b> <span style="color:#9ca3af;">(~{total_hours/30.0:.1f}h/dz.)</span></div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    rentable_uncovered = [
                        (metas.get(u_t, {}).get("matched_title") or u_t.title())
                        for u_t in uncovered_now
                        if metas.get(u_t, {}).get("rent_providers")
                    ]
                    if rentable_uncovered:
                        st.caption(f"🎟️ *Pozostałe dostępne na pojedyncze wypożyczenie (TVOD): {', '.join(rentable_uncovered[:3])}*")
                    
                    if st.button("Zatwierdź plan na ten miesiąc ✅", type="primary", use_container_width=True):
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
                        st.session_state['priority_titles'] = []
                        
                        save_data(st.session_state['logged_in_user'], {
                            "poczekalnia": st.session_state['waiting_room'],
                            "historia_wydatkow": st.session_state['history'],
                            "target_budget": st.session_state['target_budget'],
                            "current_spend": st.session_state['current_spend']
                        })
                        st.session_state['toast_msg'] = ("Zaktualizowano plan na ten cykl!", "✅")
                        st.rerun()

    with col2:
        st.subheader("Aktywny cykl 💰")
                        
        has_active_plan = len(st.session_state['history']) > 0 and not st.session_state['history'][-1].get('is_closed', True)
        
        if has_active_plan:
            with st.container(border=True):
                res = st.session_state['history'][-1]
                current_cost = res.get('cost', 0.0)
                savings = st.session_state['current_spend'] - current_cost
                active_combos = res.get('combo', [])
                
                combo_html = "".join([platform_chip(p) for p in active_combos]) if active_combos else 'Nic!'
                st.markdown(f"**{res.get('month')}:** {combo_html}", unsafe_allow_html=True)
                
                m1, m2, m3 = st.columns(3)
                m1.metric("Limit", f"{st.session_state['target_budget']:.0f} zł")
                m2.metric("Koszt", f"{current_cost:.2f} zł")
                m3.metric("Oszczędność", f"{savings:.2f} zł")
                
                if st.session_state['target_budget'] > 0:
                    percent_used = min(current_cost / st.session_state['target_budget'], 1.0)
                    st.progress(percent_used, text=f"💸 Budżet: {percent_used*100:.0f}%")
                
                st.write("---")
                
                if res.get('covered'):
                    if 'watched_temp' not in res:
                        res['watched_temp'] = []

                    total_covered = len(res['covered'])
                    watched_count = len([t for t in res['covered'] if t in res.get('watched_temp', [])])
                    if total_covered > 0:
                        watch_ratio = min(watched_count / total_covered, 1.0)
                        st.progress(watch_ratio, text=f"🍿 Obejrzano: {watched_count}/{total_covered} ({watch_ratio*100:.0f}%)")
                        
                    act_b1, act_b2 = st.columns(2)
                    with act_b1:
                        if st.button("☑️ Zaznacz wszystkie", use_container_width=True):
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
                    with act_b2:
                        if active_combos:
                            gcal_url, ics_data, remind_date_str = build_cancellation_calendar(active_combos)
                            with st.popover("🔔 Przypomnienie", use_container_width=True):
                                st.caption(f"Alarm o anulowaniu subskrypcji ({remind_date_str}):")
                                st.link_button("📅 Google Calendar", gcal_url, use_container_width=True)
                                st.download_button(
                                    "📥 Pobierz plik .ics",
                                    data=ics_data,
                                    file_name="anuluj_subskrypcje_vod.ics",
                                    mime="text/calendar",
                                    use_container_width=True,
                                )
                            
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
                    if st.button("🏁 Zakończ i rozlicz miesiąc", type="primary", use_container_width=True):
                        watched = res.get('watched_temp', [])
                        unwatched = [t for t in res.get('covered', []) if t not in watched]
                        confirm_cycle_closure(watched, unwatched)
                else:
                    st.write("*Brak tytułów w tym cyklu.*")
                    if st.button("🏁 Zakończ i rozlicz miesiąc", type="primary", use_container_width=True):
                        confirm_cycle_closure([], [])
        else:
            st.caption("Brak aktywnego cyklu — wybierz tytuły po lewej stronie, aby rozpocząć.")

        if st.session_state.get("waiting_room"):
            st.write("")
            if st.button(f"🛋️ Kupka wstydu ({len(st.session_state['waiting_room'])} poz.) — zarządzaj zaległościami →", use_container_width=True):
                st.session_state["active_nav"] = "waiting"
                st.rerun()

elif st.session_state["active_nav"] == "waiting":
    st.subheader("🛋️ Kupka wstydu (Poczekalnia na kolejne miesiące)")
    st.caption("Tytuły odłożone na później. Możesz jednym kliknięciem przerzucić je do bieżącego Planera lub obejrzeć zwiastun.")

    with st.form("add_wait_form", clear_on_submit=True, border=False):
        wf1, wf2 = st.columns([4, 1])
        with wf1:
            new_wait_item = st.text_input("Dodaj tytuł bezpośrednio do Kupki wstydu:", placeholder="Wpisz tytuł, który chcesz odłożyć na później...", label_visibility="collapsed")
        with wf2:
            add_wait_btn = st.form_submit_button("➕ Odłóż na kupkę", use_container_width=True)
        if add_wait_btn and new_wait_item.strip():
            clean_w = new_wait_item.strip().lower()
            if clean_w not in [x.lower() for x in st.session_state['waiting_room']]:
                st.session_state['waiting_room'].append(clean_w)
                save_data(st.session_state['logged_in_user'], {
                    "poczekalnia": st.session_state['waiting_room'],
                    "historia_wydatkow": st.session_state['history'],
                    "target_budget": st.session_state['target_budget'],
                    "current_spend": st.session_state['current_spend']
                })
                st.session_state['toast_msg'] = (f"Odłożono „{new_wait_item.strip()}” na Kupkę wstydu", "🛋️")
                st.rerun()

    if 'wait_avail' not in st.session_state:
        st.session_state['wait_avail'] = {}
    if 'wait_details' not in st.session_state:
        st.session_state['wait_details'] = {}

    if st.session_state['waiting_room']:
        missing = [item for item in st.session_state['waiting_room'] if item not in st.session_state['wait_avail'] or item not in st.session_state['wait_details']]
        if missing:
            with st.spinner("Aktualizuję kupkę wstydu..."):
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
            counts_str = " • ".join([f"{p}: {c}" for p, c in active_counts.items()])
            st.caption(f"Dostępność zaległości w abonamentach: {counts_str}")
            
        sorted_waiting_room = sorted(list(st.session_state['waiting_room']))
        w_cols = st.columns(2)
        for i, item in enumerate(sorted_waiting_room):
            with w_cols[i % 2]:
                with st.container(border=True):
                    col_thumb, col_text, col_btn = st.columns([0.75, 3.8, 1.85])
                    details = st.session_state['wait_details'].get(item, {})
                    w_poster = details.get("poster")
                    w_rating = details.get("rating")
                    w_meta = details.get("meta", {})
                    display_name = w_meta.get("matched_title") or item.title()

                    with col_thumb:
                        if w_poster:
                            st.markdown(f'<img src="{w_poster}" style="width: 48px; aspect-ratio: 2/3; object-fit: cover; border-radius: 6px;">', unsafe_allow_html=True)
                        else:
                            st.markdown('<div style="width: 48px; aspect-ratio: 2/3; background-color: #1e1e1e; border-radius: 6px; display: flex; align-items: center; justify-content: center;">🎬</div>', unsafe_allow_html=True)

                    with col_text:
                        safe_title = urllib.parse.quote(item)
                        link = w_meta.get("tmdb_url") or f"https://www.themoviedb.org/search?query={safe_title}&language=pl-PL"
                        platforms = st.session_state['wait_avail'].get(item, [])
                        plat_str = "".join([platform_chip(p) for p in platforms]) if platforms else '<span style="color: gray; font-size: 0.78em;">Brak w abonamentach</span>'
                        st.markdown(
                            f"**[{display_name}]({link})** {rating_badge(w_rating)}<br>{plat_str}",
                            unsafe_allow_html=True
                        )
                    with col_btn:
                        b_plan, b_tr, b_del = st.columns(3)
                        with b_plan:
                            if st.button("🍿", key=f"to_plan_{i}_{item}", help="Przenieś do Planera"):
                                if item.lower() not in [x.lower() for x in st.session_state['pending_titles']]:
                                    st.session_state['pending_titles'].append(item)
                                st.session_state["active_nav"] = "planer"
                                st.session_state['toast_msg'] = (f"Dodano „{display_name}” do Planera", "🍿")
                                st.rerun()
                        with b_tr:
                            if st.button("▶️", key=f"tr_wait_{i}_{item}", help="Zwiastun"):
                                show_trailer_dialog(display_name, w_meta.get("media_type"), w_meta.get("item_id"))
                        with b_del:
                            if st.button("❌", key=f"del_wait_{i}_{item}", help="Usuń"):
                                st.session_state['waiting_room'].remove(item)
                                save_data(st.session_state['logged_in_user'], {
                                    "poczekalnia": st.session_state['waiting_room'],
                                    "historia_wydatkow": st.session_state['history'],
                                    "target_budget": st.session_state['target_budget'],
                                    "current_spend": st.session_state['current_spend']
                                })
                                st.session_state['toast_msg'] = (f"Usunięto {item.title()}", "🗑️")
                                st.rerun()
    else:
        st.info("Twoja Kupka wstydu jest pusta! Nieobejrzane tytuły z zamkniętych cykli trafią tutaj automatycznie.")

elif st.session_state["active_nav"] == "stats":
    st.subheader("📊 Trend oszczędności i historia cykli")
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
                <div style="background: rgba(22, 163, 74, 0.12); border: 1px solid rgba(22, 163, 74, 0.35); border-radius: 12px; padding: 12px 16px; margin-bottom: 18px; font-size: 0.9rem;">
                    🏆 <b>Twoje oszczędności ({total_saved:.2f} zł) to równowartość:</b> &nbsp;
                    🎟️ <b>{cinema_tickets}</b> biletów do kina &nbsp;•&nbsp; 🍕 <b>{pizzas}</b> dużych pizz &nbsp;•&nbsp; 🍿 <b>{free_months}</b> mies. budżetu VOD gratis!
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.vega_lite_chart(
            chart_rows,
            {
                "height": 260,
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
        st.info("Zamknij swój pierwszy cykl rozliczeniowy, aby zobaczyć wykres oszczędności.")

    st.write("---")
    st.subheader("📜 Archiwum cykli")
    history_list = st.session_state.get('history', [])
    if history_list:
        available_years = sorted(list(set([h.get('month', ' 2026').split()[-1] for h in history_list])), reverse=True)
        for year in available_years:
            with st.expander(f"📅 Rok {year}", expanded=(year == available_years[0])):
                history_for_year = [h for h in history_list if h.get('month', '').endswith(year)]
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
                        watched = h.get('covered', [])
                        if watched:
                            st.write("**Obejrzano:** " + ", ".join([t.title() for t in watched]))
                        else:
                            st.caption("Brak odhaczonych tytułów w tym cyklu.")
    else:
        st.caption("Brak historii do wyświetlenia.")

elif st.session_state["active_nav"] == "settings":
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
        if st.button("🔄 Przywróć domyślne ceny rynkowe", type="secondary", use_container_width=True):
            st.session_state['platform_prices'] = copy.deepcopy(PLATFORMS)
            save_data(st.session_state['logged_in_user'], {
                "poczekalnia": st.session_state['waiting_room'],
                "historia_wydatkow": st.session_state['history'],
                "target_budget": st.session_state['target_budget'],
                "current_spend": st.session_state['current_spend']
            })
            st.session_state['toast_msg'] = ("Przywrócono domyślne ceny rynkowe", "🔄")
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