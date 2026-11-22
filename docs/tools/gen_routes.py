"""Сгенерировать таблицу маршрутов API из схемы OpenAPI приложения.

Запуск из корня проекта::

    python docs/tools/gen_routes.py > docs/_routes_table.md

Таблица всегда совпадает с кодом: маршруты, методы и описания берутся
прямо из FastAPI, а права доступа — из словаря ACCESS ниже.
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
os.environ.setdefault("OQU_INSTANCE", tempfile.mkdtemp())

from app.web import app  # noqa: E402

# Кто может вызвать маршрут (по зависимостям require_user/require_perm).
ACCESS = {
    ("POST", "/api/auth/register"): "Все",
    ("POST", "/api/auth/login"): "Все (лимит 10/мин с IP)",
    ("POST", "/api/auth/refresh"): "Все (нужен refresh-токен)",
    ("POST", "/api/unban-request"): "Забаненный (логин+пароль)",
    ("GET", "/api/books"): "Все",
    ("GET", "/api/books/random"): "Все",
    ("GET", "/api/genres"): "Все",
    ("GET", "/api/tags"): "Все",
    ("GET", "/api/books/{book_id}"): "Все",
    ("GET", "/api/books/{book_id}/read"):
        "Все; платная — студент, покупатель, автор, редактор",
    ("GET", "/api/books/{book_id}/file"): "Как у чтения текста",
    ("POST", "/api/books"): "book.add: автор, редактор",
    ("PATCH", "/api/books/{book_id}"):
        "book.edit (редактор) или своя книга (автор)",
    ("DELETE", "/api/books/{book_id}"):
        "book.delete (редактор) или своя книга (автор)",
    ("POST", "/api/books/{book_id}/file"): "Как у изменения книги",
    ("DELETE", "/api/books/{book_id}/file"): "Как у изменения книги",
    ("POST", "/api/books/{book_id}/cover"): "Как у изменения книги",
    ("DELETE", "/api/books/{book_id}/cover"): "Как у изменения книги",
    ("POST", "/api/books/{book_id}/images"): "Как у изменения книги",
    ("GET", "/api/game/config"): "Все",
    ("GET", "/api/game/me"): "Вошедший",
    ("PUT", "/api/game/me"): "Вошедший (проверка на накрутку)",
    ("DELETE", "/api/game/me"): "Вошедший",
    ("GET", "/api/game/leaderboard"): "Все",
    ("POST", "/api/books/{book_id}/buy"): "book.buy: вошедший читатель",
    ("PUT", "/api/books/{book_id}/rating"): "rating.set: вошедший",
    ("GET", "/api/books/{book_id}/comments"): "Все",
    ("POST", "/api/books/{book_id}/comments"): "comment.write: вошедший",
    ("PATCH", "/api/comments/{comment_id}"): "Автор комментария",
    ("DELETE", "/api/comments/{comment_id}"):
        "Свой; любой — модератор, редактор",
    ("GET", "/api/me"): "Вошедший",
    ("PATCH", "/api/me"): "Вошедший",
    ("DELETE", "/api/me"):
        "Вошедший (кроме главного разработчика)",
    ("GET", "/api/me/summary"): "Вошедший",
    ("POST", "/api/me/password"): "Вошедший",
    ("PUT", "/api/me/language"): "Вошедший",
    ("POST", "/api/me/student-request"): "student.apply: читатель",
    ("GET", "/api/me/shelf"): "Вошедший",
    ("PUT", "/api/me/shelf/{book_id}"): "shelf.manage: вошедший",
    ("PUT", "/api/me/progress/{book_id}"): "progress.save: вошедший",
    ("GET", "/api/me/bookmarks"): "Вошедший",
    ("POST", "/api/me/bookmarks/{book_id}"): "progress.save: вошедший",
    ("DELETE", "/api/me/bookmarks/{bookmark_id}"): "Владелец закладки",
    ("GET", "/api/stats"): "Все",
    ("GET", "/api/admin/users"): "user.list: модератор",
    ("POST", "/api/admin/users/{user_id}/role"): "Только главный разработчик",
    ("POST", "/api/admin/users/{user_id}/ban"):
        "user.ban: модератор (не персонал)",
    ("POST", "/api/admin/users/{user_id}/unban"): "user.ban: модератор",
    ("POST", "/api/admin/users/{user_id}/verify-student"):
        "user.verify_student: модератор",
    ("DELETE", "/api/admin/users/{user_id}"): "Только главный разработчик",
    ("GET", "/api/admin/unban-requests"): "unban.manage: модератор",
    ("POST", "/api/admin/unban-requests/{request_id}/resolve"):
        "unban.manage: модератор",
    ("GET", "/api/admin/student-requests"): "user.verify_student: модератор",
    ("GET", "/api/admin/student-requests/{request_id}/image"):
        "user.verify_student: модератор",
    ("POST", "/api/admin/student-requests/{request_id}/resolve"):
        "user.verify_student: модератор",
    ("GET", "/api/admin/log"): "log.read: модератор",
    ("GET", "/api/admin/log.csv"): "log.read: модератор",
    ("GET", "/api/i18n/{lang}"): "Все",
    ("GET", "/api/health"): "Все",
}


def main() -> None:
    schema = app.openapi()
    rows = []
    for path, ops in schema["paths"].items():
        for method, op in ops.items():
            key = (method.upper(), path)
            codes = ", ".join(sorted(c for c in op.get("responses", {})))
            rows.append((op.get("tags", ["—"])[0], method.upper(), path,
                         op.get("summary", ""), ACCESS.get(key, "?"), codes))
    order = [t["name"] for t in schema.get("tags", [])]
    rows.sort(key=lambda r: (order.index(r[0]) if r[0] in order else 99))
    print("| № | Группа | Метод | Адрес | Назначение | Кто может вызвать |")
    print("|---|---|---|---|---|---|")
    for i, (tag, method, path, summary, access, _codes) in enumerate(rows,
                                                                     1):
        print(f"| {i} | {tag} | `{method}` | `{path}` | {summary} | "
              f"{access} |")
    missing = [r for r in rows if r[4] == "?"]
    print(f"\nВсего маршрутов: {len(rows)}", file=sys.stderr)
    if missing:
        print("Без описания прав:", missing, file=sys.stderr)


if __name__ == "__main__":
    main()
