@echo off
chcp 65001 >nul
title DeepSeek Chat App

echo ========================================
echo   DeepSeek Chat App - Khoi Dong
echo ========================================
echo.

:: === Kiem tra Python ===
echo [*] Kiem tra Python...
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [LOI] Python khong duoc cai dat hoac khong co trong PATH!
    pause
    exit /b 1
)
echo [OK] Python da san sang.

:: === Activate .venv + Khoi dong Backend ===
cd /d "%~dp0"
echo [*] Kich hoat moi truong ao...
call .venv\Scripts\activate.bat

echo [*] Khoi dong Backend + Discord Bot...
echo.
start "" http://localhost:8000
python backend\main.py

pause
