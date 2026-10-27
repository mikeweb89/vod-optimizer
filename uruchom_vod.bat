@echo off
title Optymalizator VOD - Serwer
echo Uruchamianie Optymalizatora VOD...
echo Prosze czekac, aplikacja otworzy sie w przegladarce.

:: Przejście do folderu z aplikacją (zgodnie z Twoją ścieżką)
cd /d C:\Gemini_CLI\VOD_Optimizer

:: Uruchomienie Streamlita
python -m streamlit run vod_optimizer.py

:: Zatrzymanie okna tylko w przypadku błędu
pause