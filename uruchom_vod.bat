@echo off
title Optymalizator VOD - Serwer
echo Uruchamianie Optymalizatora VOD...
echo Prosze czekac, aplikacja otworzy sie w przegladarce.

:: Przejście do folderu, w którym znajduje się ten skrypt
cd /d "%~dp0"

:: Uruchomienie Streamlita
python -m streamlit run vod_optimizer.py

:: Zatrzymanie okna tylko w przypadku błędu
pause