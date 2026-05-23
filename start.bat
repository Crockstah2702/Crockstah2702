@echo off
title Copy-Trading Web-Terminal
color 0a
echo ================================================
echo    COPY-TRADING WEB-TERMINAL
echo ================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [FEHLER] Python ist nicht installiert!
    echo Lade Python herunter: https://www.python.org/downloads/
    echo WICHTIG: Beim Installieren "Add Python to PATH" anhaken.
    echo.
    pause
    exit /b 1
)

echo [1/2] Installiere Abhaengigkeiten ^(einmalig, kann dauern^)...
pip install -r requirements.txt -q

echo.
echo [2/2] Starte Web-Terminal...
echo Browser oeffnet sich automatisch: http://localhost:8080
echo.
echo Zum Beenden dieses Fenster schliessen oder STRG+C druecken.
echo ================================================
echo.

python main.py
pause
