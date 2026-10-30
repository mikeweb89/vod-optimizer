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
                "current_spend": data.get("current_spend")
            }
        return {"poczekalnia": [], "historia_wydatkow": [], "target_budget": None, "current_spend": None}
    except Exception as e:
        st.error(f"Błąd połączenia z bazą danych: {e}")
        return {"poczekalnia": [], "historia_wydatkow": [], "target_budget": None, "current_spend": None}

def save_data(email, data):
    try:
        supabase.table("user_data").update({
            "poczekalnia": data.get("poczekalnia", []),
            "historia_wydatkow": data.get("historia_wydatkow", []),
            "target_budget": data.get("target_budget"),
            "current_spend": data.get("current_spend")
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

def fetch_availability_tmdb(title):
    if TMDB_API_KEY == "TWÓJ_KLUCZ_API_TUTAJ": return [], None, None
    search_url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={title}&language=pl-PL"
    try:
        response = requests.get(search_url).json()
        if not response.get('results'): return [], None, None
        first_result = response['results'][0]
        media_type = first_result.get('media_type')
        item_id = first_result.get('id')
        poster_path = first_result.get('poster_path')
        vote_avg = first_result.get('vote_average')
        rating = round(vote_avg, 1) if vote_avg else None
        poster_url = f"https://image.tmdb.org/t/p/w154{poster_path}" if poster_path else None
        
        if media_type not in ['movie', 'tv']: return [], poster_url, rating
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
        return [], None, None

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

# --- SYSTEM LOGOWANIA Z HASŁEM ---
st.sidebar.title("🔐 Twoje Konto")
if not st.session_state['logged_in_user']:
    st.sidebar.info("Wpisz adres e-mail i hasło. Jeśli konto nie istnieje, zostanie automatycznie utworzone!")
    user_email = st.sidebar.text_input("Adres e-mail", placeholder="przyklad@email.com")
    user_password = st.sidebar.text_input("Hasło", type="password")
    
    if st.sidebar.button("Zaloguj / Zarejestruj 🚀"):
        if not user_email or not user_password:
            st.sidebar.error("Podaj e-mail oraz hasło.")
        elif "@" not in user_email or "." not in user_email:
            st.sidebar.error("Wprowadź poprawny format e-mail.")
        else:
            clean_email = user_email.lower().strip()
            with st.spinner("Weryfikacja..."):
                try:
                    response = supabase.table("user_data").select("password").eq("user_email", clean_email).execute()
                    if len(response.data) > 0:
                        # Użytkownik istnieje, sprawdzamy hasło
                        stored_pass = response.data[0].get("password")
                        if stored_pass == user_password:
                            st.session_state['logged_in_user'] = clean_email
                            st.rerun()
                        else:
                            st.sidebar.error("❌ Błędne hasło lub e-mail jest już zajęty!")
                    else:
                        # Nowy użytkownik, tworzymy konto
                        new_user = {
                            "user_email": clean_email, 
                            "password": user_password,
                            "poczekalnia": [], 
                            "historia_wydatkow": []
                        }
                        supabase.table("user_data").insert(new_user).execute()
                        st.session_state['logged_in_user'] = clean_email
                        st.sidebar.success("Utworzono nowe konto!")
                        st.rerun()
                except Exception as e:
                    st.sidebar.error(f"Błąd połączenia z bazą: {e}")
    st.stop()

st.sidebar.success(f"Zalogowano:\n**{st.session_state['logged_in_user']}**")
if st.sidebar.button("Wyloguj 🚪"):
    st.session_state['logged_in_user'] = None
    st.session_state['cloud_loaded'] = False
    st.rerun()

if 'cloud_loaded' not in st.session_state or not st.session_state['cloud_loaded']:
    with st.spinner("☁️ Synchronizacja z chmurą..."):
        cloud_data = load_data(st.session_state['logged_in_user'])
        st.session_state['waiting_room'] = cloud_data.get("poczekalnia", [])
        st.session_state['history'] = cloud_data.get("historia_wydatkow", [])
        st.session_state['target_budget'] = cloud_data.get("target_budget")
        st.session_state['current_spend'] = cloud_data.get("current_spend")
        st.session_state['cloud_loaded'] = True

# ==========================================
# EKRAN ONBOARDINGU (WYWIAD FINANSOWY)
# ==========================================
if st.session_state['target_budget'] is None:
    st.title("Witaj w Optymalizatorze VOD! 👋")
    st.markdown("Zanim zaczniemy optymalizować, sprawdźmy, jak wygląda Twoja obecna sytuacja.")
    
    st.subheader("1. Za które platformy płacisz w tym momencie?")
    current_subs = st.multiselect("Wybierz swoje aktywne subskrypcje:", list(PLATFORMS.keys()))
    
    netflix_price = 0
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

    calculated_spend = 0.0
    for sub in current_subs:
        if sub == "Netflix":
            calculated_spend += netflix_price
        else:
            calculated_spend += PLATFORMS[sub]["price"]
            
    st.info(f"Twoje obecne miesięczne wydatki na VOD wynoszą około: **{calculated_spend:.2f} PLN**")
    
    st.subheader("2. Ile maksymalnie chciałbyś wydawać miesięcznie?")
    user_budget = st.number_input("Twój miesięczny limit (PLN):", min_value=0.0, value=60.0, step=10.0)
    
    if st.button("Zapisz profil i przejdź do aplikacji 🚀", type="primary"):
        st.session_state['target_budget'] = user_budget
        st.session_state['current_spend'] = calculated_spend
        
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
st.title("🎬 Optymalizator Subskrypcji VOD")
st.markdown(f"**Twój docelowy limit:** `{st.session_state['target_budget']:.2f} PLN` | **Stare nawyki:** `{st.session_state['current_spend']:.2f} PLN/mc`")

tab_calc, tab_settings = st.tabs(["🍿 Kalkulator VOD", "⚙️ Ustawienia Profilu"])

with tab_calc:
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
                    availability, posters, ratings = {}, {}, {}
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

        if not st.session_state['current_availability']:
            st.info("💡 **Podpowiedź:** Wpisz powyżej tytuły, które chodzą Ci po głowie, a algorytm automatycznie przeszuka platformy i dobierze najtańszy pakiet.")

        if st.session_state['current_availability']:
            st.write("---")
            st.subheader("Etap 2: Twój wybór na aktualny cykl")
            availability = st.session_state['current_availability']
            posters = st.session_state.get('current_posters', {})
            ratings = st.session_state.get('current_ratings', {})
            
            for title, platforms in availability.items():
                c_img, c_info = st.columns([1, 4])
                with c_img:
                    poster_url = posters.get(title)
                    if poster_url: st.image(poster_url, use_container_width=True)
                    else: st.markdown("🎥 *Brak plakatu*")
                
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
                "Wybierz platformy, które chcesz dodać do tego cyklu:", 
                options=list(PLATFORMS.keys()), 
                default=suggested_combo
            )
            
            if st.button("Zatwierdź plan i aktualizuj poczekalnię ✅", type="primary"):
                covered, uncovered = [], []
                for title in st.session_state['titles_to_check']:
                    if any(p in selected_platforms for p in availability.get(title, [])):
                        covered.append(title)
                    else:
                        uncovered.append(title)
                
                has_active_plan = len(st.session_state['history']) > 0 and not st.session_state['history'][-1].get('is_closed', True)
                
                if has_active_plan:
                    existing_combo = set(st.session_state['history'][-1]['combo'])
                    merged_combo = list(existing_combo.union(set(selected_platforms)))
                    new_cost = sum(st.session_state['platform_prices'][p]["price"] for p in merged_combo)
                    
                    new_savings = st.session_state['current_spend'] - new_cost
                    merged_covered = list(set(st.session_state['history'][-1]['covered'] + covered))
                    
                    st.session_state['history'][-1].update({
                        "combo": merged_combo,
                        "cost": new_cost,
                        "savings": new_savings,
                        "covered": merged_covered
                    })
                else:
                    cost = sum(st.session_state['platform_prices'][p]["price"] for p in selected_platforms)
                    savings = st.session_state['current_spend'] - cost
                    
                    current_month_result = {
                        "month": get_current_month_name(),
                        "combo": selected_platforms,
                        "cost": cost,
                        "covered": covered,
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
        
        total_savings = sum(h.get("savings", 0) for h in st.session_state['history'])
        if total_savings > 0:
            st.success(f"🎉 **Zaoszczędziłeś łącznie od początku:** {total_savings:.2f} PLN (względem Twoich starych nawyków!)")
        
        has_active_plan = len(st.session_state['history']) > 0 and not st.session_state['history'][-1].get('is_closed', True)
        
        if has_active_plan:
            res = st.session_state['history'][-1]
            current_cost = res.get('cost', 0.0)
            savings = st.session_state['current_spend'] - current_cost
            
            st.write(f"**W bieżącym cyklu ({res.get('month')}) kupiłeś:** {', '.join(res.get('combo', [])) if res.get('combo', []) else 'Nic!'}")
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Twój Limit", f"{st.session_state['target_budget']:.2f} PLN")
            m2.metric("Ten cykl", f"{current_cost:.2f} PLN")
            m3.metric("Oszczędność", f"{savings:.2f} PLN", delta=f"{savings:.2f} PLN")
            
            if st.session_state['target_budget'] > 0:
                percent_used = min(current_cost / st.session_state['target_budget'], 1.0)
                st.progress(percent_used, text=f"Wykorzystanie Twojego budżetu: {percent_used*100:.0f}%")
                if current_cost > st.session_state['target_budget']:
                    st.warning("⚠️ Przekroczyłeś swój ustalony limit budżetowy na ten cykl!")
            
            st.write("---")
            st.markdown("**Do obejrzenia (Zaznacz to, co widziałeś):**")
            
            if res.get('covered'):
                if st.button("☑️ Zaznacz wszystkie jako obejrzane"):
                    for t in res['covered']:
                        st.session_state[f"chk_{t}"] = True
                        
                for t in res['covered']:
                    safe_title = urllib.parse.quote(t)
                    link = f"https://www.themoviedb.org/search?query={safe_title}&language=pl-PL"
                    st.checkbox(f"[{t.title()}]({link})", key=f"chk_{t}")
                
                st.write("")
                if st.button("🏁 Zakończ ten plan rozliczeniowy", type="primary"):
                    watched, unwatched = [], []
                    for t in res['covered']:
                        if st.session_state.get(f"chk_{t}", False): watched.append(t)
                        else: unwatched.append(t)
                            
                    st.session_state['history'][-1]['covered'] = watched
                    st.session_state['history'][-1]['is_closed'] = True
                    
                    st.session_state['waiting_room'].extend(unwatched)
                    st.session_state['waiting_room'] = list(set(st.session_state['waiting_room']))
                    
                    save_data(st.session_state['logged_in_user'], {
                        "poczekalnia": st.session_state['waiting_room'],
                        "historia_wydatkow": st.session_state['history'],
                        "target_budget": st.session_state['target_budget'],
                        "current_spend": st.session_state['current_spend']
                    })
                    st.session_state['toast_msg'] = ("Cykl zamknięty! Nieobejrzane tytuły wróciły do poczekalni.", "🔄")
                    st.rerun()
            else:
                st.write("*Brak tytułów do obejrzenia.*")
                if st.button("🏁 Zakończ ten plan rozliczeniowy", type="primary"):
                    st.session_state['history'][-1]['is_closed'] = True
                    save_data(st.session_state['logged_in_user'], {
                        "poczekalnia": st.session_state['waiting_room'],
                        "historia_wydatkow": st.session_state['history'],
                        "target_budget": st.session_state['target_budget'],
                        "current_spend": st.session_state['current_spend']
                    })
                    st.session_state['toast_msg'] = ("Cykl zamknięty!", "🔄")
                    st.rerun()
        else:
            st.info("Zatwierdź plan z lewej strony, aby rozpocząć nowy cykl rozliczeniowy.")
            
        st.write("---")
        st.subheader("Kupka wstydu na kolejny miesiąc ⏳")
        
        if 'wait_avail' not in st.session_state:
            st.session_state['wait_avail'] = {}

        if st.session_state['waiting_room']:
            missing = [item for item in st.session_state['waiting_room'] if item not in st.session_state['wait_avail']]
            if missing:
                with st.spinner("Analizuję zasoby Twojej kupki wstydu..."):
                    for item in missing:
                        avail, _, _ = fetch_availability_tmdb(item)
                        st.session_state['wait_avail'][item] = avail
            
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
                
            st.write("---")

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
            with st.expander("📜 Historia Twoich miesięcy (najnowsze na górze)"):
                for h in reversed(st.session_state['history']):
                    h_savings = h.get('savings', 0.0)
                    status = "✅ Zamknięty" if h.get('is_closed', True) else "⏳ Otwarty"
                    st.markdown(f"### {h.get('month', 'Nieznany')} ({status})")
                    st.markdown(f"**Zakupiono:** {', '.join(h.get('combo', [])) if h.get('combo', []) else 'Nic'} *(Zaoszczędzono: {h_savings:.2f} PLN)*")
                    if h.get('covered'):
                        st.markdown("**Obejrzano:**")
                        for t in h['covered']:
                            safe_title = urllib.parse.quote(t)
                            link = f"https://www.themoviedb.org/search?query={safe_title}&language=pl-PL"
                            st.markdown(f"- [{t.title()}]({link})")
                    st.write("---")

with tab_settings:
    st.header("⚙️ Ustawienia cen subskrypcji")
    st.write("Edytuj ceny, jeśli operator wprowadzi podwyżki. Zmiany wpłyną na Twoje przyszłe obliczenia.")
    
    c_set1, c_set2 = st.columns(2)
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
    st.header("🗑️ Ustawienia Profilu")
    if st.button("Resetuj ustawienia budżetu (powrót do ankiety)", type="secondary"):
        st.session_state['target_budget'] = None
        st.session_state['current_spend'] = None
        save_data(st.session_state['logged_in_user'], {
            "poczekalnia": st.session_state['waiting_room'],
            "historia_wydatkow": st.session_state['history'],
            "target_budget": None,
            "current_spend": None
        })
        st.rerun()
        
    st.warning("Ta akcja jest nieodwracalna. Usunie Twoją historię wydatków, budżet oraz poczekalnię.")
    if st.button("Wyczyść całe konto (Hard Reset)", type="primary"):
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