@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Оқу — сайт в интернете

rem --- Тот же поиск Python, что и в start.bat ---------------------------
set "PY="
for /f "tokens=2,*" %%A in ('reg query "HKCU\Software\Python\PythonCore" /s /v ExecutablePath 2^>nul ^| findstr /i "ExecutablePath"') do set "PY=%%B"
if not defined PY for /f "tokens=2,*" %%A in ('reg query "HKLM\Software\Python\PythonCore" /s /v ExecutablePath 2^>nul ^| findstr /i "ExecutablePath"') do set "PY=%%B"
if not defined PY (py --version >nul 2>nul && set "PY=py")
if not defined PY (python --version >nul 2>nul && set "PY=python")

if not defined PY (
  echo [ОШИБКА] Python не найден. Установите Python 3.11+ с python.org
  pause
  exit /b 1
)

echo ===========================================================
echo     ОҚУ - ЗАПУСК С ПУБЛИЧНОЙ ССЫЛКОЙ (через Cloudflare)
echo ===========================================================
echo [1/3] Проверка зависимостей...
"%PY%" -m pip install --quiet --disable-pip-version-check --no-warn-script-location -r requirements.txt > setup.log 2>&1
if not %errorlevel%==0 (
  echo [ОШИБКА] Не удалось установить зависимости. Подробности в setup.log
  pause
  exit /b 1
)
echo [2/3] Подготовка базы данных...
"%PY%" -m app.seed
echo [3/3] Запуск сервера и туннеля...
echo.
"%PY%" run_public.py
pause
