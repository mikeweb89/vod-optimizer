import streamlit as st
import requests
import urllib.parse
from datetime import datetime
import random
import copy
import itertools
from supabase import create_client, Client

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="Optymalizator Subskrypcji VOD", page_icon="🍿", layout="wide")

# --- SEKRETY I API ---
TMDB_API_KEY = st.secrets.get("TMDB_API_KEY", "BŁĄD_KLUCZA")

# --- INICJALIZACJA BAZY DANYCH (SUPABASE) ---
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
            return {"poczekalnia": data.get("poczekalnia", []), "historia_wydatkow": data.get("historia_wydatkow", [])}
        else:
            new_user = {"user_email": email, "poczekalnia": [], "historia_wydatkow": []}
            supabase.table("user_data").insert(new_user).execute()
            return {"poczekalnia": [], "historia_wydatkow": []}
    except Exception as e:
        st.error(f"Błąd połączenia z bazą danych: {e}")
        return {"poczekalnia": [], "historia_wydatkow": []}

def save_data(email, data):
    try:
        supabase.table("user_data").update({
            "poczekalnia": data["poczekalnia"],
            "historia_wydatkow": data["historia_wydatkow"]
        }).eq("user_email", email).execute()
    except Exception as e:
        st.error(f"Błąd zapisu do bazy danych: {e}")

# --- KONFIGURACJA DANYCH ---
PLATFORMS = {
    "Netflix": {"price": 75.00, "jw_id": 8},
    "Disney+": {"price": 34.99, "jw_id": 337},
    "Apple TV+": {"price": 34.99, "jw_id": 350},
    "Max": {"price": 29.99, "jw_id": 1899}, 
    "Canal+": {"price": 29.00, "jw_id": 582},
    "SkyShowtime": {"price": 24.99, "jw_id": 1773}
}

# --- FUNKCJE POMOCNICZE (CZAS) ---
def get_current_month_name():
    months_pl = ["Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec", "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień"]
    now = datetime.now()
    return f"{months_pl[now.month - 1]} {now.year}"

# =====================================================================
# --- SYSTEM LOGOWANIA (MVP) - MUSI BYĆ PRZED WYŚWIETLENIEM APLIKACJI ---
# =====================================================================
st.sidebar.title("🔐 Twoje Konto")
st.sidebar.markdown("Zaloguj się, aby zapisać swoją prywatną *Kupkę Wstydu* w chmurze.")
user_email = st.sidebar.text_input("Adres e-mail", placeholder="jan@kowalski.pl")

if not user_email:
    st.info("👈 Wpisz swój adres e-mail w panelu bocznym, aby rozpocząć korzystanie z aplikacji!")
    st.stop() # Zatrzymuje rysowanie reszty strony

# Jeśli dotarliśmy tutaj, to znaczy że mamy email. Czyścimy go i ładujemy dane.
clean_email = user_email.lower().strip()
cloud_data = load_data(clean_email)

# --- INICJALIZACJA STANU APLIKACJI ---
if 'platform_prices' not in st.session_state:
    st.session_state['platform_prices'] = copy.deepcopy(PLATFORMS)
if 'history' not in st.session_state:
    st.session_state['history'] = cloud_data.get("historia_wydatkow", [])
if 'waiting_room' not in st.session_state:
    st.session_state['waiting_room'] = cloud_data.get("poczekalnia", [])
if 'current_availability' not in st.session_state:
    st.session_state['current_availability'] = None
if 'titles_to_check' not in st.session_state:
    st.session_state['titles_to_check'] = []

# ODTWARZANIE WIDOKU BIEŻĄCEGO MIESIĄCA PO ODŚWIEŻENIU STRONY
if 'results' not in st.session_state and len(st.session_state['history']) > 0:
    last_month_data = st.session_state['history'][-1]
    if last_month_data.get('month') == get_current_month_name():
        st.session_state['results'] = last_month_data

# --- PRAWDZIWA INTEGRACJA Z ZEWNĘTRZNYM API (TMDB) ---
def fetch_availability_tmdb(title):
    if TMDB_API_KEY == "TWÓJ_KLUCZ_API_TUTAJ":
        st.error("Wprowadź swój klucz TMDB API w kodzie!")
        return []

    search_url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={title}&language=pl-PL"
    try:
        response = requests.get(search_url).json()
        if not response.get('results'):
            return []
        
        first_result = response['results'][0]
        media_type = first_result.get('media_type')
        item_id = first_result.get('id')
        
        if media_type not in ['movie', 'tv']:
            return []

        providers_url = f"https://api.themoviedb.org/3/{media_type}/{item_id}/watch/providers?api_key={TMDB_API_KEY}"
        prov_response = requests.get(providers_url).json()
        
        pl_data = prov_response.get('results', {}).get('PL', {})
        flatrate_options = pl_data.get('flatrate', [])
        
        available_platforms = []
        if flatrate_options:
            provider_ids = [prov['provider_id'] for prov in flatrate_options]
            for p_name, p_data in st.session_state['platform_prices'].items():
                if p_data['jw_id'] in provider_ids:
                    available_platforms.append(p_name)
                    
        return available_platforms
        
    except Exception as e:
        print(f"Błąd API dla tytułu {title}: {e}")
        return []

# --- FUNKCJA DO POBIERANIA TRENDÓW ---
@st.cache_data(ttl=3600)
def get_trending_titles(api_key):
    if api_key == "TWÓJ_KLUCZ_API_TUTAJ":
        return []
    try:
        movies = requests.get(f"https://api.themoviedb.org/3/trending/movie/week?api_key={api_key}&language=pl-PL").json().get('results', [])[:10]
        tv = requests.get(f"https://api.themoviedb.org/3/trending/tv/week?api_key={api_key}&language=pl-PL").json().get('results', [])[:10]
        
        trending = []
        for item in movies + tv:
            if item.get('poster_path'):
                title = item.get('title') or item.get('name')
                img_url = f"https://image.tmdb.org/t/p/w200{item['poster_path']}"
                trending.append({"title": title, "img": img_url})
        
        random.shuffle(trending)
        return trending
    except Exception as e:
        print(f"Błąd API dla trendów: {e}")
        return []
        
def display_marquee(items):
    if not items:
        return
        
    images_html = "".join([f'<img src="{item["img"]}" title="{item["title"]}" style="height: 180px; margin: 0 10px; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.5);">' for item in items])
    images_html *= 2 

    html_code = f"""
    <style>
    .marquee-container {{ overflow: hidden; white-space: nowrap; width: 100%; padding: 10px 0 25px 0; }}
    .marquee-content {{ display: inline-block; animation: marquee 30s linear infinite; }}
    .marquee-content:hover {{ animation-play-state: paused; cursor: pointer; }}
    @keyframes marquee {{ 0% {{ transform: translateX(0); }} 100% {{ transform: translateX(-50%); }} }}
    </style>
    <div class="marquee-container"><div class="marquee-content">{images_html}</div></div>
    """
    st.markdown(html_code, unsafe_allow_html=True)

# --- ALGORYTM OPTYMALIZACYJNY ---
def optimize_subscriptions(titles_availability):
    platform_names = list(st.session_state['platform_prices'].keys())
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

# --- INTERFEJS UŻYTKOWNIKA ---
with st.sidebar:
    st.header("⚙️ Ustawienia cen")
    st.write("Edytuj ceny, jeśli operator wprowadzi podwyżki:")
    for p_name, p_data in st.session_state['platform_prices'].items():
        new_price = st.number_input(f"{p_name} (PLN)", value=float(p_data['price']), step=1.0, min_value=0.0)
        if st.session_state['platform_prices'][p_name]['price'] != new_price:
            st.session_state['platform_prices'][p_name]['price'] = new_price
            # ZAPIS DANYCH
            save_data(clean_email, {"poczekalnia": st.session_state['waiting_room'], "historia_wydatkow": st.session_state.get('history', [])})
            
    st.write("---")
    st.header("🗑️ Reset aplikacji")
    st.write("Chcesz zacząć od zera (np. od Nowego Roku)?")
    if st.button("Wyczyść historię i poczekalnię", type="primary", help="Ta akcja jest nieodwracalna!"):
        st.session_state['history'] = []
        st.session_state['waiting_room'] = []
        if 'results' in st.session_state:
            del st.session_state['results']
        
        # ZAPIS DANYCH
        save_data(clean_email, {"poczekalnia": [], "historia_wydatkow": []})
        st.rerun()

MAX_BUDGET = sum(p["price"] for p in st.session_state['platform_prices'].values())
CURRENT_MONTH_STR = get_current_month_name()

# --- WYŚWIETLENIE KARUZELI TRENDÓW ---
trending_items = get_trending_titles(TMDB_API_KEY)
display_marquee(trending_items)

st.title("🎬 Optymalizator Subskrypcji VOD")
st.markdown(f"**Twój pełny miesięczny budżet:** `{MAX_BUDGET:.2f} PLN` | **Bieżący miesiąc:** `{CURRENT_MONTH_STR}`")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Etap 1: Czego szukamy?")
    titles_input = st.text_area("Wpisz filmy/seriale (każdy w nowej linii):", height=120)
    
    if st.button("Sprawdź dostępność 🔍"):
        current_titles = [t.strip() for t in titles_input.split('\n') if t.strip()]
        all_titles = list(set(current_titles + st.session_state['waiting_room']))
        
        if not all_titles:
            st.warning("Brak tytułów do sprawdzenia!")
        else:
            with st.spinner("Szukam w API TMDB..."):
                st.session_state['titles_to_check'] = all_titles
                availability = {}
                for title in all_titles:
                    availability[title] = fetch_availability_tmdb(title)
                st.session_state['current_availability'] = availability
            st.rerun()

    if st.session_state['current_availability']:
        st.write("---")
        st.subheader(f"Etap 2: Twój wybór na {CURRENT_MONTH_STR}")
        availability = st.session_state['current_availability']
        
        for title, platforms in availability.items():
            st.caption(f"**{title}** -> {', '.join(platforms) if platforms else 'Brak w abonamentach!'}")
            
        suggested_combo = optimize_subscriptions(availability)
        st.info(f"💡 **Sugestia algorytmu:** Najbardziej opłaca Ci się wziąć: {', '.join(suggested_combo)}")
        
        selected_platforms = st.multiselect(
            "Wybierz platformy, które chcesz dodać do tego miesiąca:", 
            options=list(PLATFORMS.keys()), 
            default=suggested_combo
        )
        
        if st.button("Zatwierdź plan i aktualizuj poczekalnię ✅", type="primary"):
            covered = []
            uncovered = []
            
            for title in st.session_state['titles_to_check']:
                if any(p in selected_platforms for p in availability.get(title, [])):
                    covered.append(title)
                else:
                    uncovered.append(title)
            
            is_update = len(st.session_state['history']) > 0 and st.session_state['history'][-1].get('month') == CURRENT_MONTH_STR
            
            if is_update:
                existing_combo = set(st.session_state['history'][-1]['combo'])
                merged_combo = list(existing_combo.union(set(selected_platforms)))
                
                new_cost = sum(st.session_state['platform_prices'][p]["price"] for p in merged_combo)
                new_savings = MAX_BUDGET - new_cost
                merged_covered = list(set(st.session_state['history'][-1]['covered'] + covered))
                
                st.session_state['history'][-1].update({
                    "combo": merged_combo,
                    "cost": new_cost,
                    "savings": new_savings,
                    "covered": merged_covered
                })
                st.session_state['results'] = st.session_state['history'][-1]
            else:
                cost = sum(st.session_state['platform_prices'][p]["price"] for p in selected_platforms)
                savings = MAX_BUDGET - cost
                
                current_month_result = {
                    "month": CURRENT_MONTH_STR,
                    "combo": selected_platforms,
                    "cost": cost,
                    "covered": covered,
                    "max_budget": MAX_BUDGET,
                    "savings": savings
                }
                st.session_state['results'] = current_month_result
                st.session_state['history'].append(current_month_result)
            
            st.session_state['waiting_room'] = uncovered
            st.session_state['current_availability'] = None
            st.session_state['titles_to_check'] = []
            
            # ZAPIS DANYCH
            save_data(clean_email, {"poczekalnia": st.session_state['waiting_room'], "historia_wydatkow": st.session_state.get('history', [])})
            st.rerun()

with col2:
    st.subheader("Dashboard Finansowy 💰")
    
    total_savings = sum(h.get("savings", 0) for h in st.session_state['history'])
    if total_savings > 0:
        st.success(f"🎉 **Twoje łączne oszczędności od początku:** {total_savings:.2f} PLN")
    
    if 'results' in st.session_state:
        res = st.session_state['results']
        savings = res.get('savings', 0.0)
        max_b = res.get('max_budget', MAX_BUDGET)
        current_cost = res.get('cost', 0.0)
        
        st.write(f"**W miesiącu {res.get('month', CURRENT_MONTH_STR)} kupiłeś:** {', '.join(res.get('combo', [])) if res.get('combo', []) else 'Nic!'}")
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Pełny koszt", f"{max_b:.2f} PLN")
        m2.metric("Twój koszt", f"{current_cost:.2f} PLN")
        m3.metric("Zaoszczędzono", f"{savings:.2f} PLN", delta=f"{savings:.2f} PLN")
        
        st.write("---")
        st.markdown("**Obejrzysz w tym miesiącu:**")
        if res.get('covered'):
            for t in res['covered']:
                st.write(f"✅ {t}")
        else:
            st.write("*Brak tytułów do obejrzenia.*")
            
    else:
        st.info("Zatwierdź plan z lewej strony, aby zobaczyć podsumowanie.")
        
    st.write("---")
    st.subheader("Kupka wstydu na kolejny miesiąc ⏳")
    if st.session_state['waiting_room']:
        for i, item in enumerate(list(st.session_state['waiting_room'])):
            col_text, col_btn = st.columns([4, 1])
            with col_text:
                st.markdown(f"- {item}")
            with col_btn:
                if st.button("❌", key=f"del_wait_{i}_{item}"):
                    st.session_state['waiting_room'].remove(item)
                    
                    # ZAPIS DANYCH
                    save_data(clean_email, {"poczekalnia": st.session_state['waiting_room'], "historia_wydatkow": st.session_state.get('history', [])})
                    st.rerun()
    else:
        st.write("*Pusto. Jesteś na bieżąco!*")

    if st.session_state['history']:
        st.write("---")
        with st.expander("📜 Szczegółowa historia Twoich miesięcy"):
            # Odwracamy historię, żeby najnowsze miesiące były na górze (reversed)
            for h in reversed(st.session_state['history']):
                h_savings = h.get('savings', 0.0)
                h_month = h.get('month', 'Nieznany')
                h_combo = ', '.join(h.get('combo', [])) if h.get('combo', []) else 'Brak abonamentów'
                h_covered = h.get('covered', [])
                
                st.markdown(f"### {h_month}")
                st.markdown(f"**Platformy:** {h_combo} | **Oszczędności:** `{h_savings:.2f} PLN`")
                
                if h_covered:
                    st.markdown("**Obejrzane produkcje:**")
                    for t in h_covered:
                        st.caption(f"✔️ {t}")
                else:
                    st.caption("*Brak przypisanych produkcji w tym miesiącu.*")
                st.write("---")