import streamlit as st
import requests
import copy
import itertools
from datetime import datetime
import random
import urllib.parse
from supabase import create_client, Client

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="Optymalizator Subskrypcji VOD", page_icon="🍿", layout="wide")

# --- SYSTEM POWIADOMIEŃ TOAST ---
if 'toast_msg' in st.session_state:
    msg, icon = st.session_state['toast_msg']
    st.toast(msg, icon=icon)
    del st.session_state['toast_msg']

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
    "Netflix": {"price": 75.00, "jw_id": 8, "url": "https://www.netflix.com/pl/"},
    "Disney+": {"price": 34.99, "jw_id": 337, "url": "https://www.disneyplus.com/pl-pl"},
    "Apple TV+": {"price": 34.99, "jw_id": 350, "url": "https://tv.apple.com/pl"},
    "Max": {"price": 29.99, "jw_id": 1899, "url": "https://www.max.com/pl/pl"}, 
    "Canal+": {"price": 29.00, "jw_id": 582, "url": "https://canalplus.com/pl/"},
    "SkyShowtime": {"price": 24.99, "jw_id": 1773, "url": "https://www.skyshowtime.com/pl"}
}

# --- FUNKCJE POMOCNICZE (CZAS) ---
def get_current_month_name():
    months_pl = ["Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec", "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień"]
    now = datetime.now()
    return f"{months_pl[now.month - 1]} {now.year}"

# Inicjalizacja stanu aplikacji
if 'platform_prices' not in st.session_state:
    st.session_state['platform_prices'] = copy.deepcopy(PLATFORMS)
if 'history' not in st.session_state:
    st.session_state['history'] = []
if 'waiting_room' not in st.session_state:
    st.session_state['waiting_room'] = []
if 'current_availability' not in st.session_state:
    st.session_state['current_availability'] = None
if 'current_posters' not in st.session_state:
    st.session_state['current_posters'] = {}
if 'current_ratings' not in st.session_state:
    st.session_state['current_ratings'] = {}
if 'titles_to_check' not in st.session_state:
    st.session_state['titles_to_check'] = []
if 'logged_in_user' not in st.session_state:
    st.session_state['logged_in_user'] = None
if 'search_input' not in st.session_state:
    st.session_state['search_input'] = ""
if 'clear_flag' not in st.session_state:
    st.session_state['clear_flag'] = False

# --- PRAWDZIWA INTEGRACJA Z ZEWNĘTRZNYM API (TMDB) ---
def fetch_availability_tmdb(title):
    if TMDB_API_KEY == "TWÓJ_KLUCZ_API_TUTAJ":
        return [], None, None

    search_url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={title}&language=pl-PL"
    try:
        response = requests.get(search_url).json()
        if not response.get('results'):
            return [], None, None
        
        first_result = response['results'][0]
        media_type = first_result.get('media_type')
        item_id = first_result.get('id')
        poster_path = first_result.get('poster_path')
        
        vote_avg = first_result.get('vote_average')
        rating = round(vote_avg, 1) if vote_avg else None
        
        poster_url = f"https://image.tmdb.org/t/p/w154{poster_path}" if poster_path else None
        
        if media_type not in ['movie', 'tv']:
            return [], poster_url, rating

        providers_url = f"https://api.themoviedb.org/3/{media_type}/{item_id}/watch/providers?api_key={TMDB_API_KEY}"
        prov_response = requests.get(providers_url).json()
        
        pl_data = prov_response.get('results', {}).get('PL', {})
        flatrate_options = pl_data.get('flatrate', [])
        
        available_platforms = []
        if flatrate_options:
            provider_ids = [prov['provider_id'] for prov in flatrate_options]
            for p_name, p_data in PLATFORMS.items():
                if p_data['jw_id'] in provider_ids:
                    available_platforms.append(p_name)
                    
        return available_platforms, poster_url, rating
        
    except Exception as e:
        print(f"Błąd API dla tytułu {title}: {e}")
        return [], None, None

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

# --- SYSTEM LOGOWANIA (MVP) ---
st.sidebar.title("🔐 Twoje Konto")

if not st.session_state['logged_in_user']:
    user_email = st.sidebar.text_input("Adres e-mail", placeholder="przyklad@email.com")
    
    if not user_email:
        st.info("👈 Wpisz swój adres e-mail w panelu bocznym, aby rozpocząć korzystanie z aplikacji!")
        st.stop()
    elif "@" not in user_email or "." not in user_email:
        st.sidebar.error("Wprowadź poprawny format e-mail (z symbolem '@' i kropką).")
        st.stop()
    else:
        clean_email = user_email.lower().strip()
        st.session_state['logged_in_user'] = clean_email
        st.rerun()

st.sidebar.success(f"Zalogowano jako:\n**{st.session_state['logged_in_user']}**")
if st.sidebar.button("Wyloguj 🚪"):
    st.session_state['logged_in_user'] = None
    st.rerun()

# Ładowanie z chmury z własnym ekranem ładowania (spinner)
if 'cloud_loaded' not in st.session_state:
    with st.spinner("☁️ Synchronizacja z chmurą..."):
        cloud_data = load_data(st.session_state['logged_in_user'])
        st.session_state['waiting_room'] = cloud_data.get("poczekalnia", [])
        st.session_state['history'] = cloud_data.get("historia_wydatkow", [])
        st.session_state['cloud_loaded'] = True

# --- GŁÓWNY INTERFEJS ---
MAX_BUDGET = sum(p["price"] for p in st.session_state['platform_prices'].values())
CURRENT_MONTH_STR = get_current_month_name()

st.title("🎬 Optymalizator Subskrypcji VOD")
st.markdown(f"**Twój pełny miesięczny budżet:** `{MAX_BUDGET:.2f} PLN` | **Bieżący miesiąc:** `{CURRENT_MONTH_STR}`")

# WYŚWIETLENIE KARUZELI TRENDÓW
trending_items = get_trending_titles(TMDB_API_KEY)
display_marquee(trending_items)

# ROZBICIE NA ZAKŁADKI (TABS)
tab_calc, tab_settings = st.tabs(["🍿 Kalkulator VOD", "⚙️ Ustawienia Profilu"])

# ==========================================
# ZAKŁADKA 1: KALKULATOR I DASHBOARD
# ==========================================
with tab_calc:
    if len(st.session_state['history']) > 0 and st.session_state['history'][-1].get('month') == CURRENT_MONTH_STR:
        st.session_state['results'] = st.session_state['history'][-1]

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Etap 1: Czego szukamy?")
        
        if st.session_state['clear_flag']:
            st.session_state['search_input'] = ""
            st.session_state['clear_flag'] = False
            
        titles_input = st.text_area("Wpisz filmy/seriale (każdy w nowej linii):", height=120, key="search_input")
        
        if st.button("Sprawdź dostępność 🔍"):
            current_titles = [t.strip() for t in titles_input.split('\n') if t.strip()]
            all_titles = list(set(current_titles + st.session_state['waiting_room']))
            
            if not all_titles:
                st.warning("Brak tytułów do sprawdzenia!")
            else:
                with st.spinner("Pobieram oceny, plakaty i dostępność z bazy TMDB... 🎬"):
                    st.session_state['titles_to_check'] = all_titles
                    availability = {}
                    posters = {}
                    ratings = {}
                    for title in all_titles:
                        avail, poster, rating = fetch_availability_tmdb(title)
                        availability[title] = avail
                        posters[title] = poster
                        ratings[title] = rating
                    st.session_state['current_availability'] = availability
                    st.session_state['current_posters'] = posters
                    st.session_state['current_ratings'] = ratings
                
                st.session_state['clear_flag'] = True
                st.rerun()

        # STAN PUSTY (Empty State)
        if not st.session_state['current_availability']:
            st.info("💡 **Podpowiedź:** Wpisz powyżej tytuły, które chodzą Ci po głowie, a algorytm automatycznie przeszuka platformy i dobierze najtańszy pakiet.")

        if st.session_state['current_availability']:
            st.write("---")
            st.subheader(f"Etap 2: Twój wybór na {CURRENT_MONTH_STR}")
            availability = st.session_state['current_availability']
            posters = st.session_state.get('current_posters', {})
            ratings = st.session_state.get('current_ratings', {})
            
            for title, platforms in availability.items():
                c_img, c_info = st.columns([1, 4])
                with c_img:
                    poster_url = posters.get(title)
                    if poster_url:
                        st.image(poster_url, use_container_width=True)
                    else:
                        st.markdown("🎥 *Brak plakatu*")
                
                with c_info:
                    rating = ratings.get(title)
                    rating_str = f" ⭐ {rating}/10" if rating else ""
                    st.markdown(f"### {title.title()}{rating_str}")
                    
                    if platforms:
                        platforms_links = " ".join([f"[`{p}`]({PLATFORMS[p]['url']})" for p in platforms])
                        st.markdown(platforms_links)
                    else:
                        st.markdown("*Brak w abonamentach (tylko wypożyczalnie/zakup).*")
                st.write("---")

            suggested_combo = optimize_subscriptions(availability)
            st.success(f"💡 **Sugestia algorytmu:** Najbardziej opłaca Ci się wziąć: **{', '.join(suggested_combo) if suggested_combo else 'Nic'}**")
            
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
                st.session_state['current_posters'] = {}
                st.session_state['current_ratings'] = {}
                st.session_state['titles_to_check'] = []
                
                save_data(st.session_state['logged_in_user'], {
                    "poczekalnia": st.session_state['waiting_room'],
                    "historia_wydatkow": st.session_state['history']
                })
                # Uruchomienie Toasta przed restartem
                st.session_state['toast_msg'] = ("Zaktualizowano plan na ten miesiąc!", "✅")
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
            
            # WIZUALIZACJA BUDŻETU (PASEK POSTĘPU)
            if max_b > 0:
                percent_used = min(current_cost / max_b, 1.0)
                st.progress(percent_used, text=f"Wykorzystanie pełnego budżetu VOD: {percent_used*100:.0f}%")
            
            st.write("---")
            st.markdown("**Obejrzysz w tym miesiącu:**")
            if res.get('covered'):
                for t in res['covered']:
                    safe_title = urllib.parse.quote(t)
                    link = f"https://www.themoviedb.org/search?query={safe_title}&language=pl-PL"
                    st.write(f"✅ **[{t.title()}]({link})**")
            else:
                st.write("*Brak tytułów do obejrzenia.*")
        else:
            st.info("Zatwierdź plan z lewej strony, aby zobaczyć podsumowanie.")
            
        st.write("---")
        st.subheader("Kupka wstydu na kolejny miesiąc ⏳")
        
        # Inicjalizacja pamięci dla poczekalni, by nie odpytywać API TMDB przy każdym kliknięciu
        if 'wait_avail' not in st.session_state:
            st.session_state['wait_avail'] = {}

        if st.session_state['waiting_room']:
            # Pobieranie danych dla nowych tytułów w tle
            missing = [item for item in st.session_state['waiting_room'] if item not in st.session_state['wait_avail']]
            if missing:
                with st.spinner("Analizuję zasoby Twojej kupki wstydu..."):
                    for item in missing:
                        avail, _, _ = fetch_availability_tmdb(item)
                        st.session_state['wait_avail'][item] = avail
            
            # Zliczanie wystąpień na platformach
            platform_counts = {p: 0 for p in PLATFORMS.keys()}
            for item in st.session_state['waiting_room']:
                for p in st.session_state['wait_avail'].get(item, []):
                    if p in platform_counts:
                        platform_counts[p] += 1
            
            # Wyświetlanie liczników (tylko dla platform, które mają > 0 filmów)
            active_counts = {p: c for p, c in platform_counts.items() if c > 0}
            if active_counts:
                counts_str = " | ".join([f"{p}: {c}" for p, c in active_counts.items()])
                st.caption(f"**Podsumowanie zaległości:** {counts_str}")
                
            # Logika rekomendacji - jeśli >= 3 zaległości
            recommended = [p for p, c in active_counts.items() if c >= 3]
            if recommended:
                st.info(f"💡 **Wskazówka na przyszłość:** W kolejnym miesiącu z pewnością warto rozważyć wykupienie: **{', '.join(recommended)}**. Masz tam sporo do nadrobienia!")
                
            st.write("---")

            # Wyświetlanie listy z tagami platform
            sorted_waiting_room = sorted(list(st.session_state['waiting_room']))
            for i, item in enumerate(sorted_waiting_room):
                col_text, col_btn = st.columns([4, 1])
                with col_text:
                    safe_title = urllib.parse.quote(item)
                    link = f"https://www.themoviedb.org/search?query={safe_title}&language=pl-PL"
                    
                    platforms = st.session_state['wait_avail'].get(item, [])
                    plat_str = f" `({', '.join(platforms)})`" if platforms else ""
                    
                    st.markdown(f"- **[{item.title()}]({link})**{plat_str}")
                with col_btn:
                    if st.button("❌", key=f"del_wait_{i}_{item}"):
                        st.session_state['waiting_room'].remove(item)
                        save_data(st.session_state['logged_in_user'], {
                            "poczekalnia": st.session_state['waiting_room'],
                            "historia_wydatkow": st.session_state['history']
                        })
                        st.session_state['toast_msg'] = (f"Usunięto {item.title()} z kupki wstydu", "🗑️")
                        st.rerun()
        else:
            st.write("*Pusto. Jesteś na bieżąco!*")

        if st.session_state['history']:
            st.write("---")
            with st.expander("📜 Historia Twoich miesięcy (najnowsze na górze)"):
                for h in reversed(st.session_state['history']):
                    h_savings = h.get('savings', 0.0)
                    st.markdown(f"### {h.get('month', 'Nieznany')}")
                    st.markdown(f"**Zakupiono:** {', '.join(h.get('combo', [])) if h.get('combo', []) else 'Nic'} *(Zaoszczędzono: {h_savings:.2f} PLN)*")
                    if h.get('covered'):
                        st.markdown("**Obejrzano:**")
                        for t in h['covered']:
                            safe_title = urllib.parse.quote(t)
                            link = f"https://www.themoviedb.org/search?query={safe_title}&language=pl-PL"
                            st.markdown(f"- [{t.title()}]({link})")
                    st.write("---")


# ==========================================
# ZAKŁADKA 2: USTAWIENIA PROFILU
# ==========================================
with tab_settings:
    st.header("⚙️ Ustawienia cen subskrypcji")
    st.write("Edytuj ceny, jeśli operator wprowadzi podwyżki. Zmiany wpłyną na Twoje przyszłe obliczenia.")
    
    c_set1, c_set2 = st.columns(2)
    
    # Dzielimy platformy na dwie kolumny dla lepszego wyglądu
    platforms_list = list(st.session_state['platform_prices'].items())
    half = len(platforms_list) // 2
    
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

    st.write("---")
    st.header("🗑️ Resetowanie Konta")
    st.warning("Ta akcja jest nieodwracalna. Usunie Twoją historię wydatków oraz poczekalnię.")
    if st.button("Wyczyść całą historię i poczekalnię", type="primary"):
        st.session_state['history'] = []
        st.session_state['waiting_room'] = []
        if 'results' in st.session_state:
            del st.session_state['results']
        save_data(st.session_state['logged_in_user'], {"poczekalnia": [], "historia_wydatkow": []})
        st.session_state['toast_msg'] = ("Konto zostało zresetowane", "🧹")
        st.rerun()