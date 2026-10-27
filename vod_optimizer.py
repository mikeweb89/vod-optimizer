import streamlit as st
import itertools
import random 
import copy
import requests # NOWE: Biblioteka do zapytań sieciowych
from datetime import datetime # Dodajemy obsługę czasu
import json # NOWE: Do zapisywania danych w pliku
import os # NOWE: Do sprawdzania czy plik istnieje

# --- KONFIGURACJA TMDB API (BEZPIECZNA) ---
# Program próbuje pobrać klucz z bezpiecznego pliku secrets.toml
# Jeśli go nie znajdzie, używa wartości domyślnej, która wywoła ostrzeżenie
TMDB_API_KEY = st.secrets.get("TMDB_API_KEY", "TWÓJ_KLUCZ_API_TUTAJ")

st.set_page_config(page_title="VOD Optimizer", layout="wide")

# --- PLIK Z LOKALNĄ BAZĄ DANYCH ---
DATA_FILE = "vod_data.json"

def load_data():
    """Wczytuje zapisany stan z pliku JSON (jeśli istnieje)."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"history": [], "waiting_room": [], "platform_prices": None}

def save_data():
    """Zapisuje bieżący stan aplikacji do pliku JSON."""
    data = {
        "history": st.session_state.get('history', []),
        "waiting_room": st.session_state.get('waiting_room', []),
        "platform_prices": st.session_state.get('platform_prices', {})
    }
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

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

# Inicjalizacja stanu aplikacji z lokalnego pliku JSON
loaded_data = load_data()

if 'platform_prices' not in st.session_state:
    st.session_state['platform_prices'] = loaded_data.get('platform_prices') or copy.deepcopy(PLATFORMS)
if 'history' not in st.session_state:
    st.session_state['history'] = loaded_data.get('history', [])
if 'waiting_room' not in st.session_state:
    st.session_state['waiting_room'] = loaded_data.get('waiting_room', [])
if 'current_availability' not in st.session_state:
    st.session_state['current_availability'] = None
if 'titles_to_check' not in st.session_state:
    st.session_state['titles_to_check'] = []

# --- PRAWDZIWA INTEGRACJA Z ZEWNĘTRZNYM API (TMDB) ---
def fetch_availability_tmdb(title):
    if TMDB_API_KEY == "TWÓJ_KLUCZ_API_TUTAJ":
        st.error("Wprowadź swój klucz TMDB API w kodzie (linijka z TMDB_API_KEY)!")
        return []

    # 1. Szukamy ID tytułu w bazie
    search_url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={title}&language=pl-PL"
    try:
        response = requests.get(search_url).json()
        if not response.get('results'):
            return [] # Nie znaleziono takiego tytułu
        
        # Bierzemy pierwszy (najbardziej trafny) wynik
        first_result = response['results'][0]
        media_type = first_result.get('media_type')
        item_id = first_result.get('id')
        
        if media_type not in ['movie', 'tv']:
            return []

        # 2. Sprawdzamy gdzie można to obejrzeć w Polsce
        providers_url = f"https://api.themoviedb.org/3/{media_type}/{item_id}/watch/providers?api_key={TMDB_API_KEY}"
        prov_response = requests.get(providers_url).json()
        
        pl_data = prov_response.get('results', {}).get('PL', {})
        flatrate_options = pl_data.get('flatrate', []) # Tylko w abonamencie, bez wypożyczeń!
        
        available_platforms = []
        if flatrate_options:
            provider_ids = [prov['provider_id'] for prov in flatrate_options]
            
            # Dopasowujemy ID z TMDB do naszych zdefiniowanych platform
            for p_name, p_data in st.session_state['platform_prices'].items():
                if p_data['jw_id'] in provider_ids:
                    available_platforms.append(p_name)
                    
        return available_platforms
        
    except Exception as e:
        print(f"Błąd API dla tytułu {title}: {e}")
        return []

# --- NOWE: FUNKCJA DO POBIERANIA TRENDÓW ---
@st.cache_data(ttl=3600) # Zapisujemy w pamięci podręcznej na godzinę, żeby oszczędzać zapytania do API
def get_trending_titles(api_key):
    if api_key == "TWÓJ_KLUCZ_API_TUTAJ":
        return []
    try:
        # Pobieramy top 5 filmów i top 5 seriali (trendy z tego tygodnia)
        movies = requests.get(f"https://api.themoviedb.org/3/trending/movie/week?api_key={api_key}&language=pl-PL").json().get('results', [])[:5]
        tv = requests.get(f"https://api.themoviedb.org/3/trending/tv/week?api_key={api_key}&language=pl-PL").json().get('results', [])[:5]
        
        # Łączymy wyniki i przygotowujemy linki do plakatów
        trending = []
        for item in movies + tv:
            if item.get('poster_path'):
                title = item.get('title') or item.get('name')
                img_url = f"https://image.tmdb.org/t/p/w200{item['poster_path']}"
                trending.append({"title": title, "img": img_url})
        
        random.shuffle(trending) # Mieszamy filmy z serialami
        return trending
    except Exception as e:
        print(f"Błąd API dla trendów: {e}")
        return []
        
def display_marquee(items):
    if not items:
        return
        
    # Tworzymy tagi <img> dla każdego plakatu (dodano tooltip po najechaniu myszką)
    images_html = "".join([f'<img src="{item["img"]}" title="{item["title"]}" style="height: 180px; margin: 0 10px; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.5);">' for item in items])
    # Duplikujemy listę, żeby pętla mogła kręcić się bez widocznego przeskoku
    images_html *= 2 

    # Kod CSS tworzący efekt przewijania i zatrzymania (hover)
    html_code = f"""
    <style>
    .marquee-container {{
        overflow: hidden;
        white-space: nowrap;
        width: 100%;
        padding: 10px 0 25px 0;
    }}
    .marquee-content {{
        display: inline-block;
        animation: marquee 30s linear infinite;
    }}
    .marquee-content:hover {{
        animation-play-state: paused;
        cursor: pointer;
    }}
    @keyframes marquee {{
        0% {{ transform: translateX(0); }}
        100% {{ transform: translateX(-50%); }}
    }}
    </style>
    <div class="marquee-container">
        <div class="marquee-content">
            {images_html}
        </div>
    </div>
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
        # Zapisujemy nową cenę, jeśli użytkownik ją zmienił
        if st.session_state['platform_prices'][p_name]['price'] != new_price:
            st.session_state['platform_prices'][p_name]['price'] = new_price
            save_data()
            
    st.write("---")
    st.header("🗑️ Reset aplikacji")
    st.write("Chcesz zacząć od zera (np. od Nowego Roku)?")
    if st.button("Wyczyść historię i poczekalnię", type="primary", help="Ta akcja jest nieodwracalna!"):
        # Czyścimy listy w pamięci programu
        st.session_state['history'] = []
        st.session_state['waiting_room'] = []
        if 'results' in st.session_state:
            del st.session_state['results']
        
        # Zapisujemy wyczyszczony stan do pliku .json na dysku
        save_data()
        st.rerun()

MAX_BUDGET = sum(p["price"] for p in st.session_state['platform_prices'].values())
CURRENT_MONTH_STR = get_current_month_name()

# --- NOWE: WYŚWIETLENIE KARUZELI TRENDÓW ---
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
                    # Zamiana z funkcji Mock na prawdziwe API TMDB
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
            
            # Sprawdzamy, czy w historii mamy już wpis dla obecnego miesiąca
            is_update = len(st.session_state['history']) > 0 and st.session_state['history'][-1].get('month') == CURRENT_MONTH_STR
            
            if is_update:
                # AKTUALIZACJA W POŁOWIE MIESIĄCA
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
                # NOWY MIESIĄC
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
            
            # TRWAŁY ZAPIS: Zapisujemy dane po zatwierdzeniu planu
            save_data()
            st.rerun()

with col2:
    st.subheader("Dashboard Finansowy 💰")
    
    # Zabezpieczamy pobieranie 'savings' z historii używając .get()
    total_savings = sum(h.get("savings", 0) for h in st.session_state['history'])
    if total_savings > 0:
        st.success(f"🎉 **Twoje łączne oszczędności od początku:** {total_savings:.2f} PLN")
    
    if 'results' in st.session_state:
        res = st.session_state['results']
        # Zabezpieczamy klucze za pomocą .get(), aby uniknąć KeyError ze starych sesji
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
        # Tworzymy kolumny dla każdego elementu, by przycisk usuwania był w tej samej linii
        for i, item in enumerate(list(st.session_state['waiting_room'])):
            col_text, col_btn = st.columns([4, 1])
            with col_text:
                st.markdown(f"- {item}")
            with col_btn:
                # Unikalny klucz dla każdego przycisku jest wymagany w Streamlit
                if st.button("❌", key=f"del_wait_{i}_{item}"):
                    st.session_state['waiting_room'].remove(item)
                    
                    # TRWAŁY ZAPIS: Zapisujemy dane po usunięciu z poczekalni
                    save_data()
                    st.rerun()
    else:
        st.write("*Pusto. Jesteś na bieżąco!*")

    if st.session_state['history']:
        st.write("---")
        with st.expander("📜 Historia Twoich miesięcy"):
            for h in st.session_state['history']:
                # Zabezpieczamy historię
                h_savings = h.get('savings', 0.0)
                st.markdown(f"**{h.get('month', 'Nieznany')}:** Wybrano {', '.join(h.get('combo', [])) if h.get('combo', []) else 'Nic'} (Zaoszczędzono: {h_savings:.2f} PLN)")