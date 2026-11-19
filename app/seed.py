"""Наполнение базы демонстрационными данными.

Запуск::  python -m app.seed

Создаёт учётные записи (включая главного разработчика), несколько книг,
теги и комментарии, чтобы интерфейс и API можно было сразу показать на защите.
Тексты книг — короткие демонстрационные фрагменты (не защищённые авторским
правом полнотексты).
"""

from __future__ import annotations

import os

from app import service
from app.db import connect

DB_PATH = os.environ.get("LIBRARY_DB",
                         os.path.join(os.path.dirname(os.path.dirname(
                             os.path.abspath(__file__))), "instance",
                             "library.sqlite"))

DEMO_TEXT = (
    "Это демонстрационный фрагмент текста книги для показа режима чтения. "
    "Здесь хранится полный текст произведения, и пользователь может "
    "продолжить чтение с того места, где остановился в прошлый раз.\n\n"
) * 8

BOOKS = [
    # (title, author, year, genre, language, is_paid, paid_days, color)
    ("Абай жолы", "Мұхтар Әуезов", 1942, "роман", "kk", False, None, "#b45309"),
    ("Қан мен тер", "Әбдіжәміл Нұрпейісов", 1961, "роман", "kk", False, None,
     "#7c3aed"),
    ("Евгений Онегин", "Александр Пушкин", 1833, "поэзия", "ru", False, None,
     "#2563eb"),
    ("Война и мир", "Лев Толстой", 1869, "роман", "ru", False, None, "#dc2626"),
    ("Преступление и наказание", "Фёдор Достоевский", 1866, "роман", "ru",
     False, None, "#059669"),
    ("Pride and Prejudice", "Jane Austen", 1813, "novel", "en", False, None,
     "#db2777"),
    ("Новинка: Основы Python", "Айтимов М.Ж.", 2026, "учебник", "ru", True, 30,
     "#0891b2"),
    ("Робот и будущее", "Айдос Серіков", 2025, "фантастика", "ru", True, 14,
     "#4f46e5"),
]

TAGS = {
    "Абай жолы": ["классика", "казахская литература"],
    "Война и мир": ["классика", "русская литература"],
    "Pride and Prejudice": ["classic", "romance"],
    "Новинка: Основы Python": ["учебник", "программирование"],
}


def seed() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = connect(DB_PATH)

    if service.get_user_by_username(db, "muhan") is not None:
        print("База уже наполнена — пропускаю.")
        db.close()
        return

    # Главный разработчик (пункт 24 ТЗ: «поставь меня как главного разработчика»)
    owner_id = service.register_user(
        db, "muhan", "muhan@ex.kz", "ChangeMe_2026", role="owner",
        display_name="Мұхан Надирхалиф")
    # Напарница и демонстрационные роли.
    service.register_user(db, "khadizat", "khadizat@ex.kz", "ChangeMe_2026",
                          role="editor", display_name="Хадизат")
    service.register_user(db, "moder01", "moder@ex.kz", "ChangeMe_2026",
                          role="moderator", display_name="Модератор")
    service.register_user(db, "author01", "author@ex.kz", "ChangeMe_2026",
                          role="author", display_name="Автор книги")
    student_id = service.register_user(db, "student01", "student@ex.kz",
                                       "ChangeMe_2026", role="student",
                                       display_name="Студент")
    service.verify_student(db, "owner", student_id)
    reader_id = service.register_user(db, "reader01", "reader@ex.kz",
                                      "ChangeMe_2026", role="user",
                                      display_name="Читатель")

    title_to_id: dict[str, int] = {}
    for title, author, year, genre, lang, is_paid, paid_days, color in BOOKS:
        bid = service.add_book(
            db, "owner", title, author, year=year, genre=genre, language=lang,
            description=f"{title} — {author}. Демонстрационное описание книги.",
            content=DEMO_TEXT, cover_color=color, is_paid=is_paid,
            paid_days=paid_days, added_by=owner_id)
        title_to_id[title] = bid
        for tag in TAGS.get(title, []):
            service.tag_book(db, bid, tag)

    # Полка и прогресс для читателя.
    service.set_shelf_status(db, reader_id, title_to_id["Война и мир"],
                             "reading")
    service.save_progress(db, reader_id, title_to_id["Война и мир"], 320)
    service.set_shelf_status(db, reader_id, title_to_id["Абай жолы"], "read")
    service.set_shelf_status(db, student_id, title_to_id["Евгений Онегин"],
                             "want")

    # Комментарии (с разными приписками по ролям).
    owner = service.get_user(db, owner_id)
    reader = service.get_user(db, reader_id)
    service.add_comment(db, owner, title_to_id["Абай жолы"],
                        "Добро пожаловать в нашу библиотеку!")
    service.add_comment(db, reader, title_to_id["Война и мир"],
                        "Великий роман, читаю с удовольствием.")

    print(f"Готово. Создан главный разработчик 'muhan' (пароль ChangeMe_2026), "
          f"{len(BOOKS)} книг, демо-полки и комментарии.")
    db.close()


if __name__ == "__main__":
    seed()
