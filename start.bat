@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Электронная библиотека Коркыт ата

echo ===========================================================
echo        ЭЛЕКТРОННАЯ БИБЛИОТЕКА - ЗАПУСК
echo ===========================================================
echo.

rem --- Поиск Python -----------------------------------------------------
where py >nul 2>nul
if %errorlevel%==0 (set "PY=py") else (set "PY=python")

%PY% --version >nul 2>nul
if not %errorlevel%==0 (
  echo [ОШИБКА] Python не найден.
  echo Установите Python 3.11+ с https://www.python.org/downloads/
  echo и обязательно поставьте галочку "Add Python to PATH".
  echo.
  pause
  exit /b 1
)

echo [1/3] Установка зависимостей (только в первый раз, подождите)...
%PY% -m pip install --quiet --disable-pip-version-check -r requirements.txt
if not %errorlevel%==0 (
  echo [ОШИБКА] Не удалось установить зависимости. Проверьте интернет.
  pause
  exit /b 1
)

echo [2/3] Подготовка базы данных (демо-книги и пользователи)...
%PY% -m app.seed

echo [3/3] Запуск сервера...
echo.
echo ===========================================================
echo   Сайт открывается в браузере:  http://127.0.0.1:8000
echo   Документация API (OpenAPI):   http://127.0.0.1:8000/docs
echo.
echo   Вход главного разработчика:   muhan / ChangeMe_2026
echo.
echo   Чтобы ОСТАНОВИТЬ сервер - закройте это окно
echo   или нажмите Ctrl + C.
echo ===========================================================
echo.

rem Открыть браузер через 4 секунды (сервер успеет подняться)
start "" cmd /c "timeout /t 4 >nul & start http://127.0.0.1:8000"

%PY% -m uvicorn app.web:app
pause
