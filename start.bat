@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

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

:: === Kiem tra Node.js ===
echo [*] Kiem tra Node.js...
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [LOI] Node.js khong duoc cai dat hoac khong co trong PATH!
    pause
    exit /b 1
)
echo [OK] Node.js da san sang.

:: === Cai dat Python dependencies (neu can) ===
cd /d "%~dp0backend"
if not exist "venv\" (
    echo [*] Tao virtual environment...
    python -m venv venv
)
call venv\Scripts\activate.bat
echo [*] Kiem tra Python packages...
pip install -r requirements.txt --quiet 2>nul
echo [OK] Python packages da san sang.

:: === Cai dat Node.js dependencies (neu can) ===
cd /d "%~dp0frontend"
if not exist "node_modules\" (
    echo [*] Dang cai dat npm packages... (lan dau chay se lau hon)
    call npm install
)
echo [OK] npm packages da san sang.

:: === Khoi dong Backend ===
cd /d "%~dp0backend"
echo.
echo [1/2] Khoi dong Backend (FastAPI)...
start "DeepSeek-Backend" cmd /k "cd /d %~dp0backend && venv\Scripts\activate.bat && python main.py"

:: === Khoi dong Frontend ===
cd /d "%~dp0frontend"
echo [2/2] Khoi dong Frontend (React + Vite)...
start "DeepSeek-Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

:: === Doi server khoi dong xong ===
echo.
echo [*] Dang doi server khoi dong...
echo     (Backend co the lau hon neu chua co file .env)

:: Doi backend (toi da 15 giay)
set /a count=0
:wait_backend
timeout /t 1 /nobreak >nul
set /a count+=1
curl -s http://localhost:8000/ >nul 2>&1
if !errorlevel! equ 0 goto backend_ready
if !count! lss 15 goto wait_backend
echo [CANH BAO] Backend chua san sang, nhung van tiep tuc...

:backend_ready
echo [OK] Backend da san sang!

:: Doi frontend (toi da 15 giay)
set /a count=0
:wait_frontend
timeout /t 1 /nobreak >nul
set /a count+=1
curl -s http://localhost:3000/ >nul 2>&1
if !errorlevel! equ 0 goto frontend_ready
if !count! lss 15 goto wait_frontend
echo [CANH BAO] Frontend chua san sang, nhung van tiep tuc...

:frontend_ready
echo [OK] Frontend da san sang!

:: === Mo trinh duyet ===
echo.
echo [*] Dang mo trinh duyet...
start "" http://localhost:3000

echo.
echo ========================================
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:3000
echo ========================================
echo.
echo Da mo trinh duyet tu dong!
echo Nhan phim bat ky de dong cua so nay...
echo (Backend va Frontend se tiep tuc chay)
pause >nul
