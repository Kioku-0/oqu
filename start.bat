@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Электронная библиотека Коркыт ата

rem --- Поиск Python -----------------------------------------------------
where py >nul 2>nul
if %errorlevel%==0 (set "PY=py") else (set "PY=python")

echo === SETUP START === > setup.log
%PY% --version >> setup.log 2>&1
if not %errorlevel%==0 (
  echo PYTHON_NOT_FOUND >> setup.log
  echo [ОШИБКА] Python не найден. Установите Python 3.11+ с python.org
  echo и поставьте галочку "Add Python to PATH".
  pause
  exit /b 1
)

echo ===========================================================
echo        ЭЛЕКТРОННАЯ БИБЛИОТЕКА - ЗАПУСК
echo ===========================================================
echo.
echo [1/3] Установка зависимостей (только в первый раз, подождите)...
echo [pip install] >> setup.log
%PY% -m pip install --disable-pip-version-check -r requirements.txt >> setup.log 2>&1

echo [2/3] Подготовка базы данных...
echo [seed] >> setup.log
%PY% -m app.seed >> setup.log 2>&1

echo === SETUP DONE === >> setup.log
echo.
echo [3/3] Запуск сервера...
echo ===========================================================
echo   Сайт:        http://127.0.0.1:8000
echo   Документы:   http://127.0.0.1:8000/docs
echo   Вход:        muhan / ChangeMe_2026
echo   Остановить:  закройте это окно
echo ===========================================================

rem Открыть сайт в браузере через 5 секунд (сервер успеет подняться)
start "" cmd /c "timeout /t 5 >nul & start msedge http://127.0.0.1:8000"

echo === SERVER START === >> setup.log
%PY% -m uvicorn app.web:app >> setup.log 2>&1
pause
