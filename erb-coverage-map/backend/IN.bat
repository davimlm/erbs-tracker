@echo off
:: Navega para a pasta raiz (erb-coverage-map) a partir da pasta backend
cd /d "%~dp0.."

:: Inicia o servidor Python
echo Iniciando servidor Uvicorn...
uvicorn backend.main:app --host 127.0.0.1 --port 8000
pause
