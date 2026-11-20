@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Оқу — электронная библиотека

rem --- Поиск Python: сначала по реестру (официальные установщики и
rem --- менеджер Python), затем через команды py / python ------------------
set "PY="
for /f "tokens=2,*" %%A in ('reg query "HKCU\Software\Python\PythonCore" /s /v ExecutablePath 2^>nul ^| findstr /i "ExecutablePath"') do set "PY=%%B"
if not defined PY for /f "tokens=2,*" %%A in ('reg query "HKLM\Software\Python\PythonCore" /s /v ExecutablePath 2^>nul ^| findstr /i "ExecutablePath"') do set "PY=%%B"
if not defined PY (py --version >nul 2>nul && set "PY=py")
if not defined PY (python --version >nul 2>nul && set "PY=python")

if not defined PY (
  echo [ОШИБКА] Python не найден.
  echo Установите Python 3.11+ с https://www.python.org/downloads/
  echo и поставьте галочку "Add python.exe to PATH".
  pause
  exit /b 1
)

echo ===========================================================
echo        ОҚУ - ЭЛЕКТРОННАЯ БИБЛИОТЕКА - ЗАПУСК
echo ===========================================================
echo Python: %PY%
echo.
if not exist "instance\logs" mkdir "instance\logs"
echo [1/3] Проверка зависимостей (в первый раз - около минуты)...
"%PY%" -m pip install --quiet --disable-pip-version-check --no-warn-script-location -r requirements.txt > instance\logs\setup.log 2>&1
if not %errorlevel%==0 (
  echo [ОШИБКА] Не удалось установить зависимости. Подробности в instance\logs\setup.log
  pause
  exit /b 1
)

echo [2/3] Подготовка базы данных...
"%PY%" -m app.seed

echo [3/3] Запуск сервера...
echo ===========================================================
echo   Сайт:        http://127.0.0.1:8000
echo   Документы:   http://127.0.0.1:8000/docs
echo   Вход:        muhan / ChangeMe_2026
echo   Остановить:  закройте это окно
echo ===========================================================
start "" cmd /c "timeout /t 5 >nul & start http://127.0.0.1:8000"
"%PY%" -m uvicorn app.web:app
pause
