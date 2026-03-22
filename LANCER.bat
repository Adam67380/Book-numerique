@echo off
title Vinted Flip Ultimate
color 0C

echo.
echo  ╔═══════════════════════════════════════════════╗
echo  ║       VINTED FLIP ULTIMATE v4.0               ║
echo  ╚═══════════════════════════════════════════════╝
echo.
echo [1/3] Python...
python --version >nul 2>&1
if errorlevel 1 (echo X Python manquant! & pause & exit /b)
echo OK

echo [2/3] Dependances...
pip install -r requirements.txt --quiet
echo OK

echo [3/3] Lancement...
echo.
echo  Dashboard: http://localhost:8081
echo.

start "Scraper" cmd /k "python scraper.py"
timeout /t 2 /nobreak >nul
start "Dashboard" cmd /k "python dashboard.py"

echo Tout est lance!
pause >nul
