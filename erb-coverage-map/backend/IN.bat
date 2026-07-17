@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0.."

echo ==============================================
echo        INICIANDO AMBIENTE DE MAPA ERB
echo ==============================================
echo.

echo [1/3] Verificando pgAdmin 4...
tasklist /FI "IMAGENAME eq pgadmin4.exe" 2>NUL | find /I /N "pgadmin4.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo        - pgAdmin 4 ja esta em execucao.
) else (
    echo        - pgAdmin 4 nao esta rodando. Tentando iniciar...
    if exist "C:\Program Files\pgAdmin 4\v8\runtime\pgAdmin4.exe" (
        start "" "C:\Program Files\pgAdmin 4\v8\runtime\pgAdmin4.exe"
    ) else if exist "C:\Program Files\pgAdmin 4\v7\runtime\pgAdmin4.exe" (
        start "" "C:\Program Files\pgAdmin 4\v7\runtime\pgAdmin4.exe"
    ) else if exist "C:\Program Files\pgAdmin 4\v6\runtime\pgAdmin4.exe" (
        start "" "C:\Program Files\pgAdmin 4\v6\runtime\pgAdmin4.exe"
    ) else if exist "C:\Program Files\PostgreSQL\15\pgAdmin 4\bin\pgAdmin4.exe" (
        start "" "C:\Program Files\PostgreSQL\15\pgAdmin 4\bin\pgAdmin4.exe"
    ) else if exist "C:\Program Files\PostgreSQL\16\pgAdmin 4\bin\pgAdmin4.exe" (
        start "" "C:\Program Files\PostgreSQL\16\pgAdmin 4\bin\pgAdmin4.exe"
    ) else (
        echo        - [Aviso] pgAdmin4.exe nao encontrado nos caminhos padroes. Abra-o manualmente.
    )
)
echo.

echo [2/3] Escolha o modo de execucao da API:
echo    [1] Rodar Localmente (Somente nesta maquina)
echo    [2] Rodar via Cloudflare Tunnel (Sem limite HTTP/1.1)
echo.
set /p MODO="Digite 1 ou 2: "

echo.
echo [3/3] Iniciando Servicos...

if "%MODO%"=="1" goto start_api

echo Verificando Cloudflare Tunnel...
set "CLOUDFLARED_CMD="
if exist "%~dp0cloudflared.exe" set "CLOUDFLARED_CMD=%~dp0cloudflared.exe"
if "%CLOUDFLARED_CMD%"=="" if exist "backend\cloudflared.exe" set "CLOUDFLARED_CMD=%cd%\backend\cloudflared.exe"
if "%CLOUDFLARED_CMD%"=="" where cloudflared >nul 2>nul && set "CLOUDFLARED_CMD=cloudflared"

if "%CLOUDFLARED_CMD%"=="" (
    echo [AVISO] cloudflared.exe nao encontrado. Continuando sem tunel...
    goto start_api
)

echo Abrindo janela do Cloudflare Tunnel...
start "Cloudflare Tunnel" powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0start_tunnel.ps1" -CloudflaredPath "%CLOUDFLARED_CMD%"

:start_api
echo Iniciando servidor Uvicorn...
uvicorn backend.main:app --host 127.0.0.1 --port 8000
pause