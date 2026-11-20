"""Открыть сайт «Оқу» в интернет с этого компьютера (бесплатно).

Как это работает: сайт запускается здесь, как обычно, а программа
``cloudflared`` (бесплатный туннель Cloudflare) выдаёт ему публичную ссылку
вида ``https://что-то.trycloudflare.com`` с HTTPS. По ссылке сайт открывается
с любого телефона или компьютера, пока это окно открыто.

Запуск: двойной клик по ``start_public.bat`` (он сам найдёт Python,
поставит зависимости и подготовит базу) или ``python run_public.py``.

Что делает скрипт:

1. по желанию меняет пароль служебных демо-аккаунтов (владелец, редактор,
   модератор, авторы) — пароль из README знают все, а сайт будет открыт
   в интернет;
2. запускает сервер в публичном режиме: подсказка с демо-паролем скрыта,
   журнал пишет настоящие IP посетителей;
3. запускает туннель, показывает ссылку, копирует её в буфер обмена
   и сохраняет в ``instance/public_url.txt``.
"""

from __future__ import annotations

import getpass
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("OQU_PORT", "8000"))
LOCAL_URL = f"http://127.0.0.1:{PORT}"
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
STAFF = ("muhan", "khadizat", "moder01", "author01", "author02")


def find_cloudflared() -> str | None:
    """cloudflared.exe в папке tools/ проекта или в PATH."""
    local = os.path.join(BASE_DIR, "tools", "cloudflared.exe")
    if os.path.isfile(local):
        return local
    return shutil.which("cloudflared")


def change_staff_password() -> None:
    """Предложить новый пароль для служебных демо-аккаунтов."""
    print("Сайт будет открыт в интернет. Пароль демо-аккаунтов ChangeMe_2026")
    print("написан в README, поэтому для служебных аккаунтов")
    print("(" + ", ".join(STAFF) + ") лучше задать свой.")
    password = getpass.getpass("Новый пароль (Enter - оставить прежний): ")
    if not password:
        print("Пароль не изменён.\n")
        return
    if len(password) < 8:
        print("Слишком короткий (меньше 8 символов) - пароль не изменён.\n")
        return
    if getpass.getpass("Повторите пароль: ") != password:
        print("Пароли не совпали - пароль не изменён.\n")
        return
    sys.path.insert(0, BASE_DIR)
    from app import security, web  # noqa: E402  (нужен путь к проекту)
    from app.db import connect

    db = connect(web.DB_PATH)
    try:
        new_hash = security.hash_password(password)
        marks = ",".join("?" * len(STAFF))
        cur = db.execute(
            f"UPDATE users SET password_hash = ? WHERE username IN ({marks})",
            (new_hash, *STAFF))
        db.commit()
        print(f"Пароль изменён у {cur.rowcount} аккаунтов. Запомните его!\n")
    finally:
        db.close()


def wait_for_server(timeout: float = 30) -> bool:
    """Ждать, пока сервер ответит на /api/health."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(LOCAL_URL + "/api/health", timeout=2):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def announce(url: str) -> None:
    """Показать ссылку крупно, скопировать и сохранить."""
    line = "=" * 64
    print(f"\n{line}\n  САЙТ ОТКРЫТ В ИНТЕРНЕТ:\n\n    {url}\n")
    print(f"  Документация API:  {url}/docs")
    print("  Ссылка скопирована в буфер обмена (Ctrl+V).")
    print("  Остановить: закройте это окно или нажмите Ctrl+C.")
    print(f"{line}\n")
    try:
        subprocess.run("clip", input=url.encode("ascii"), check=False,
                       shell=True)
    except OSError:
        pass
    os.makedirs(os.path.join(BASE_DIR, "instance"), exist_ok=True)
    with open(os.path.join(BASE_DIR, "instance", "public_url.txt"), "w",
              encoding="utf-8") as fh:
        fh.write(url + "\n")
    webbrowser.open(url)


def watch_tunnel(proc: subprocess.Popen) -> None:
    """Читать вывод туннеля, найти ссылку; остальное — в лог-файл."""
    log_path = os.path.join(BASE_DIR, "instance", "logs", "tunnel.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    found = False
    with open(log_path, "w", encoding="utf-8") as log:
        for raw in proc.stdout:
            text = raw.decode("utf-8", "replace")
            log.write(text)
            log.flush()
            match = URL_RE.search(text)
            if match and not found:
                found = True
                announce(match.group(0))


def main() -> int:
    os.chdir(BASE_DIR)
    cloudflared = find_cloudflared()
    if not cloudflared:
        print("[ОШИБКА] Не найден cloudflared.exe.")
        print("Скачайте cloudflared-windows-amd64.exe со страницы")
        print("https://github.com/cloudflare/cloudflared/releases/latest")
        print("переименуйте в cloudflared.exe и положите в папку tools\\")
        return 1

    change_staff_password()

    env = dict(os.environ, OQU_PUBLIC="1", OQU_TRUST_PROXY="1")
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.web:app",
         "--host", "127.0.0.1", "--port", str(PORT)], env=env)
    tunnel = None
    try:
        print("Запускаю сервер...")
        if not wait_for_server():
            print("[ОШИБКА] Сервер не запустился. Смотрите сообщения выше.")
            return 1
        print("Сервер работает. Подключаю туннель (10-20 секунд)...")
        tunnel = subprocess.Popen(
            [cloudflared, "tunnel", "--no-autoupdate", "--url", LOCAL_URL],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        threading.Thread(target=watch_tunnel, args=(tunnel,),
                         daemon=True).start()
        while server.poll() is None and tunnel.poll() is None:
            time.sleep(1)
        if tunnel.poll() is not None:
            print("[ОШИБКА] Туннель остановился. Проверьте интернет;")
            print("подробности в instance\\logs\\tunnel.log")
        return 1
    except KeyboardInterrupt:
        print("\nОстанавливаю...")
        return 0
    finally:
        for proc in (tunnel, server):
            if proc and proc.poll() is None:
                proc.terminate()


if __name__ == "__main__":
    sys.exit(main())
