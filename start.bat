@echo off
chcp 65001 >nul
title DeepSeek Chat App - Backend & Discord Bot

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

echo [*] Khoi dong Backend + Discord Bot trong cua so rieng...
echo.

:: Start backend trong cua so rieng (non-blocking)
start "Backend Server" cmd /k python backend\main.py

:: Doi backend khoi dong xong
timeout /t 3 /nobreak
echo [OK] Backend da khoi dong. Truy cap http://localhost:8000

pause
