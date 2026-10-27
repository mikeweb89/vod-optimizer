🎬 Optymalizator Subskrypcji VOD

Aplikacja webowa stworzona w celu walki ze "zmęczeniem subskrypcjami" (subscription fatigue). Narzędzie pomaga użytkownikom zoptymalizować miesięczne koszty platform streamingowych (Netflix, Max, Disney+, Apple TV+, Canal+, SkyShowtime) na podstawie ich osobistej listy filmów i seriali do obejrzenia.

✨ Główne funkcje

Inteligentny algorytm: Dobiera maksymalnie 2 platformy w miesiącu, które pokryją najwięcej tytułów z Twojej listy, generując jak największe oszczędności.

Kupka wstydu (Poczekalnia): Tytuły, które nie załapały się w danym miesiącu, mogą zostać przeniesione do zintegrowanej poczekalni na kolejne miesiące.

Dashboard Finansowy: Śledzi Twoje rzeczywiste oszczędności i budżet miesiąc po miesiącu. Pozwala na ręczną modyfikację cen subskrypcji.

Aktualne dane z rynku: Integracja z darmowym API TMDB (wspieranym przez JustWatch) dla regionu PL dostarcza danych o dostępności produkcji na bieżąco, wliczając w to aktualne "Trendy" (najpopularniejsze produkcje tygodnia).

Pełna prywatność: Aplikacja działa lokalnie i zapisuje historię bezpośrednio na Twoim urządzeniu.

🛠 Technologie

Język: Python

Framework: Streamlit (błyskawiczne tworzenie interaktywnych interfejsów webowych)

API: The Movie Database (TMDB) API

🚀 Jak uruchomić aplikację lokalnie

Sklonuj to repozytorium na swój komputer (lub pobierz jako ZIP).

Otwórz terminal w folderze z projektem i zainstaluj wymagane biblioteki:
pip install streamlit requests

W głównym folderze projektu stwórz ukryty folder .streamlit, a w nim plik secrets.toml.

W pliku secrets.toml wklej swój klucz API z TMDB w następującym formacie:
TMDB_API_KEY = "TWÓJ_PRAWDZIWY_KLUCZ_API"

Uruchom aplikację komendą:
python -m streamlit run vod_optimizer.py