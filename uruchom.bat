@echo off
chcp 65001 >nul
title FocusIt
echo === FocusIt ===
python --version >nul 2>&1
if errorlevel 1 (
    echo Nie znaleziono Pythona! Zainstaluj go z https://www.python.org/downloads/
    echo Podczas instalacji zaznacz opcje "Add python.exe to PATH".
    pause
    exit /b 1
)
python -c "import psutil" >nul 2>&1
if errorlevel 1 (
    echo Instaluje wymagane biblioteki (tylko za pierwszym razem)...
    python -m pip install -r requirements.txt
)
python FocusIt.py
if errorlevel 1 pause
