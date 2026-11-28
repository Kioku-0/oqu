"""Наполнение базы демонстрационными данными.

Запуск::

    python -m app.seed           # наполнить, если база пустая
    python -m app.seed --reset   # удалить базу и создать заново
    python -m app.seed --staff-password  # свой пароль служебным аккаунтам

Создаются учётные записи всех ролей, книги, теги, полки, оценки, закладки,
комментарии, бан с заявкой на разбан — чтобы на защите можно было сразу
показать каждую функцию. Тексты классических произведений — короткие
начальные фрагменты книг, перешедших в общественное достояние (авторы умерли
более 70 лет назад). Учебник «Основы Python» и рассказ «Тихий робот»
написаны командой проекта специально для демонстрации.
"""

from __future__ import annotations

import json
import os
import random
import secrets
import shutil
import struct
import sys
import zlib
from datetime import timedelta
from typing import Optional

from app import service
from app.db import connect

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("LIBRARY_DB", os.path.join(
    os.environ.get("OQU_INSTANCE", os.path.join(BASE_DIR, "instance")),
    "library.sqlite"))
DEMO_PASSWORD = "ChangeMe_2026"


def _demo(name: str) -> str:
    """Прочитать демонстрационный текст из app/demo/<name>.txt."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo",
                        f"{name}.txt")
    with open(path, encoding="utf-8") as fh:
        return fh.read().strip()


PD_NOTE = ("Это начальный фрагмент произведения. Полный текст находится "
           "в общественном достоянии и может быть добавлен редактором через "
           "форму «Изменить книгу» — из файла .txt или как скан PDF.")
PD_NOTE_KK = ("Бұл — шығарманың бастапқы үзіндісі. Толық мәтін қоғам "
              "игілігінде және оны редактор «Кітапты өзгерту» арқылы "
              ".txt файлынан немесе PDF-скан ретінде қоса алады.")
PD_NOTE_EN = ("This is the opening excerpt. The full text is in the public "
              "domain and an editor can add it via “Edit book” — from a .txt "
              "file or as a PDF scan.")

def _demo_json(name: str):
    """Прочитать демонстрационные данные из app/demo/<name>."""
    path = os.path.join(DEMO_DIR, name)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


DEMO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo")
# Произведения, которые в базе лежат целиком (короткие стихи) — им не нужна
# пометка «это начальный фрагмент».
COMPLETE_WORKS = {"Ворона и Лисица", "Сказка о рыбаке и рыбке",
                  "Белая берёза", "Ночь, улица, фонарь, аптека", "Sonnet 18"}
COPYRIGHT_NOTE = ("## Об этой карточке\n\nЭто аннотация, которую редакция "
                  "«Оқу» написала сама по открытым сведениям о книге. Полный "
                  "текст защищён авторским правом ({holder}), поэтому здесь "
                  "его нет: книгу можно купить у официального издателя или "
                  "взять в библиотеке.")
MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря")

PYTHON_BOOK = _demo("python_book")

ROBOT_STORY = _demo("robot_story")

# (название, автор, год, жанр, язык, цвет, текст, теги, описание)
BOOKS = [
    ("Қара сөздер", "Абай Құнанбайұлы", 1898, "философия", "kk", "#0f4c81",
     "Бұл жасқа келгенше жақсы, жаман күн өткіздік. Алыстық, жұлыстық, "
     "айтыстық, тартыстық — әуре-сарсаңды көп көрдік. Енді жасымыз жетті, "
     "қажыдық, жалықтық; қылып жүрген ісіміздің баянсызын, байлаусызын "
     "көрдік, бәрі қоршылық екенін білдік. Ал, енді қалған өмірімізді "
     "қайтіп, не қылып өткіземіз? Соны таба алмай өзім де қайранмын.\n\n"
     + PD_NOTE_KK,
     ["классика", "қазақ әдебиеті"],
     "Абайдың қырық бес қара сөзі — қазақ ойының інжу-маржаны. Адам, "
     "білім, еңбек және ар туралы толғаныстар."),
    ("Евгений Онегин", "Александр Пушкин", 1833, "поэзия", "ru", "#7a2e2e",
     "Мой дядя самых честных правил,\nКогда не в шутку занемог,\n"
     "Он уважать себя заставил\nИ лучше выдумать не мог.\n"
     "Его пример другим наука;\nНо, боже мой, какая скука\n"
     "С больным сидеть и день и ночь,\nНе отходя ни шагу прочь!\n"
     "Какое низкое коварство\nПолуживого забавлять,\n"
     "Ему подушки поправлять,\nПечально подносить лекарство,\n"
     "Вздыхать и думать про себя:\nКогда же черт возьмет тебя!\n\n"
     + PD_NOTE,
     ["классика", "русская литература"],
     "Роман в стихах о молодом петербургском дворянине, скуке, любви и "
     "упущенном счастье. «Энциклопедия русской жизни»."),
    ("Анна Каренина", "Лев Толстой", 1877, "роман", "ru", "#1f5f4a",
     "Все счастливые семьи похожи друг на друга, каждая несчастливая семья "
     "несчастлива по-своему.\n\nВсё смешалось в доме Облонских. Жена "
     "узнала, что муж был в связи с бывшею в их доме француженкою-"
     "гувернанткой, и объявила мужу, что не может жить с ним в одном "
     "доме.\n\n" + PD_NOTE,
     ["классика", "русская литература"],
     "История любви, долга и общественного осуждения на фоне жизни "
     "русского дворянства второй половины XIX века."),
    ("Преступление и наказание", "Фёдор Достоевский", 1866, "роман", "ru",
     "#3d3d3d",
     "В начале июля, в чрезвычайно жаркое время, под вечер, один молодой "
     "человек вышел из своей каморки, которую нанимал от жильцов в С—м "
     "переулке, на улицу и медленно, как бы в нерешимости, отправился к "
     "К—ну мосту.\n\n" + PD_NOTE,
     ["классика", "русская литература"],
     "Бывший студент Раскольников решается на преступление, чтобы "
     "проверить свою теорию, — и сталкивается с собственной совестью."),
    ("Мёртвые души", "Николай Гоголь", 1842, "роман", "ru", "#a3782a",
     "В ворота гостиницы губернского города NN въехала довольно красивая "
     "рессорная небольшая бричка, в какой ездят холостяки: отставные "
     "подполковники, штабс-капитаны, помещики, имеющие около сотни душ "
     "крестьян, — словом, все те, которых называют господами средней "
     "руки.\n\n" + PD_NOTE,
     ["классика", "сатира"],
     "Чичиков скупает у помещиков умерших крестьян — и проезжает через "
     "галерею незабываемых характеров."),
    ("Герой нашего времени", "Михаил Лермонтов", 1840, "роман", "ru",
     "#2f7f8f",
     "Я ехал на перекладных из Тифлиса. Вся поклажа моей тележки состояла "
     "из одного небольшого чемодана, который до половины был набит путевыми "
     "записками о Грузии.\n\n" + PD_NOTE,
     ["классика", "русская литература"],
     "Первый русский психологический роман: пять историй о Печорине — "
     "человеке, которому скучно жить."),
    ("Дама с собачкой", "Антон Чехов", 1899, "рассказ", "ru", "#9b3b54",
     "Говорили, что на набережной появилось новое лицо: дама с собачкой. "
     "Дмитрий Дмитрич Гуров, проживший в Ялте уже две недели и привыкший "
     "тут, тоже стал интересоваться новыми лицами.\n\n" + PD_NOTE,
     ["классика", "короткая проза"],
     "Курортное знакомство в Ялте, которое оказывается важнее всей "
     "прежней жизни."),
    ("Pride and Prejudice", "Jane Austen", 1813, "роман", "en", "#6b3fa0",
     "It is a truth universally acknowledged, that a single man in "
     "possession of a good fortune, must be in want of a wife.\n\n"
     + PD_NOTE_EN,
     ["classic", "english literature"],
     "Elizabeth Bennet and Mr Darcy: first impressions, pride, prejudice "
     "and one of the best-loved novels in English."),
    ("Alice's Adventures in Wonderland", "Lewis Carroll", 1865, "сказка",
     "en", "#b0532c",
     "Alice was beginning to get very tired of sitting by her sister on the "
     "bank, and of having nothing to do: once or twice she had peeped into "
     "the book her sister was reading, but it had no pictures or "
     "conversations in it, “and what is the use of a book,” thought Alice, "
     "“without pictures or conversations?”\n\n" + PD_NOTE_EN,
     ["classic", "fairy tale"],
     "A girl follows a White Rabbit down a rabbit hole into a world where "
     "nothing is what it seems."),
    ("Hamlet", "William Shakespeare", 1603, "драма", "en", "#4f7a2e",
     "To be, or not to be, that is the question:\nWhether 'tis nobler in "
     "the mind to suffer\nThe slings and arrows of outrageous fortune,\n"
     "Or to take arms against a sea of troubles\nAnd by opposing end "
     "them.\n\n" + PD_NOTE_EN,
     ["classic", "theatre"],
     "The Prince of Denmark, a ghost, and the most famous question in "
     "world drama."),
]


def _reset() -> None:
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(DB_PATH + suffix)
        except OSError:
            pass
    # Загруженные файлы старой демо-базы больше ни к чему не привязаны.
    for sub in ("books", "students", "images"):
        folder = os.path.join(os.path.dirname(DB_PATH), "uploads", sub)
        if os.path.isdir(folder):
            for name in os.listdir(folder):
                try:
                    os.remove(os.path.join(folder, name))
                except OSError:
                    pass


def seed() -> None:
    """Наполнить базу демонстрационными данными (если она пустая)."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = connect(DB_PATH)
    if service.get_user_by_username(db, "muhan") is not None:
        print("База уже наполнена — пропускаю (для пересоздания: --reset).")
        db.close()
        return

    def user(name, email, role, display, lang="ru"):
        uid = service.register_user(db, name, email, DEMO_PASSWORD, role=role,
                                    display_name=display, language=lang)
        return service.get_user(db, uid)

    # Имена — одногруппники Мұхана (с их согласия, для живости демо).
    owner = user("muhan", "muhan@oqu.kz", "owner", "Мұхан Надирхалиф")
    editor = user("khadizat", "khadizat@oqu.kz", "editor",
                  "Жоробекова Хадизат", "kk")
    moder = user("moder01", "moder@oqu.kz", "moderator", "Алтынбек")
    author = user("author01", "author@oqu.kz", "author", "Команда «Оқу»")
    student = user("student01", "student@oqu.kz", "user", "Мұратхан", "kk")
    service.verify_student(db, "owner", student["id"])
    student = service.get_user(db, student["id"])
    reader = user("reader01", "reader@oqu.kz", "user", "Данияр")
    spammer = user("spammer01", "spam@oqu.kz", "user", "Едіге")
    applicant = user("applicant01", "applicant@oqu.kz", "user", "Сейілхан",
                     "kk")
    banned = user("banned01", "banned@oqu.kz", "user", "Забаненный навсегда")
    author2 = user("author02", "author2@oqu.kz", "author", "Темірлан", "kk")
    vladimir = user("vladimir_p", "vladimir@oqu.kz", "user", "Владимир П.")

    ext = _demo_json("texts_ext.json")   # продолжения текстов (1–4 стр.)

    def full_text(title, text, lang):
        """Текст книги: скачанное продолжение (если есть) + пометка."""
        note = {"kk": PD_NOTE_KK, "en": PD_NOTE_EN}.get(lang, PD_NOTE)
        base = text.split("\n\n" + note)[0]
        if title in COMPLETE_WORKS:
            return ext.get(title, base)
        return ext.get(title, base) + "\n\n" + note

    ids: dict[str, int] = {}
    for title, writer, year, genre, lang, color, text, tags, desc in BOOKS:
        ids[title] = service.add_book(
            db, "editor", title, writer, year=year, genre=genre,
            language=lang, description=desc,
            content=full_text(title, text, lang),
            cover_color=color, tags=tags, added_by=editor["id"])
    for item in _demo_json("books_extra.json"):
        ids[item["title"]] = service.add_book(
            db, "editor", item["title"], item["author"],
            year=item["year"], genre=item["genre"],
            language=item["language"], description=item["description"],
            content=full_text(item["title"], item["content"],
                              item["language"]),
            cover_color=item["color"], cover_pattern=item["pattern"],
            tags=item["tags"], added_by=editor["id"])

    ids["Основы Python"] = service.add_book(
        db, "author", "Основы Python: от переменной до REST API",
        "Команда «Оқу»", year=2026, genre="учебник", language="ru",
        description="Короткий учебник, написанный для демонстрации "
                    "платной новинки и режима чтения с закладками.",
        content=PYTHON_BOOK, cover_color="#0f6e5a", is_paid=True, price=990,
        paid_days=30, tags=["программирование", "python", "учебник"],
        added_by=author["id"])
    ids["Тихий робот"] = service.add_book(
        db, "author", "Тихий робот", "Команда «Оқу»", year=2026,
        genre="фантастика", language="ru",
        description="Короткий рассказ о роботе, который расставлял книги "
                    "по цвету корешков.",
        content=ROBOT_STORY, cover_color="#3b5ba5", is_paid=True, price=490,
        paid_days=14, tags=["фантастика", "библиотека"],
        added_by=author["id"])
    # Книга из электронной библиотеки университета (МегаПро): у нас —
    # карточка и ссылка, сам скан открывается на сайте вуза.
    ids["МегаПро"] = service.add_book(
        db, "editor", "Халық-сахналық би негіздері",
        "Автор не указан", genre="искусство", language="kk",
        description="Оқу құралы университеттің МегаПро электрондық "
                    "кітапханасында. Сканды ашу үшін «ЖОО кітапханасында "
                    "ашу» батырмасын басыңыз.",
        external_url="https://library.korkyt.kz/MegaPro/Download/MObject/"
                     "2262",
        cover_color="#8a5a35", tags=["хореография", "мегапро"],
        added_by=editor["id"])

    # Полки, прогресс, оценки, закладки.
    plan = [
        (reader, "Анна Каренина", "reading", 320, 5),
        (reader, "Қара сөздер", "read", None, 5),
        (reader, "Евгений Онегин", "read", None, 4),
        (reader, "Hamlet", "want", None, None),
        (student, "Основы Python", "reading", 450, 5),
        (student, "Қара сөздер", "read", None, 5),
        (student, "Pride and Prejudice", "read", None, 4),
        (student, "Мёртвые души", "dropped", None, 3),
        (editor, "Дама с собачкой", "read", None, 5),
        (editor, "Герой нашего времени", "read", None, 4),
        (moder, "Преступление и наказание", "read", None, 5),
        (moder, "Alice's Adventures in Wonderland", "reading", 600, 5),
    ]
    for who, title, status, position, rating in plan:
        service.set_shelf_status(db, who["id"], ids[title], status)
        if position is not None:
            service.save_progress(db, who["id"], ids[title], position)
        if rating:
            service.rate_book(db, who, ids[title], rating)
    service.add_bookmark(db, student["id"], ids["Основы Python"], 450,
                         "Про JWT — повторить к защите")
    service.add_bookmark(db, reader["id"], ids["Анна Каренина"], 120,
                         "Начало: знаменитая первая фраза")

    # Комментарии с приписками ролей.
    service.add_comment(db, owner, ids["Қара сөздер"],
                        "Добро пожаловать в «Оқу»! Начните с Абая.")
    service.add_comment(db, student, ids["Қара сөздер"],
                        "Бірінші сөзді әр жыл сайын қайта оқимын.")
    service.add_comment(db, author, ids["Основы Python"],
                        "Если что-то непонятно — пишите, дополним главу.")
    service.add_comment(db, reader, ids["Анна Каренина"],
                        "Первая фраза — лучшая в русской литературе.")
    service.add_comment(db, editor, ids["Евгений Онегин"],
                        "Полный текст добавим к следующему семестру.")

    # Второй автор (Темірлан): своя бесплатная книга и платный бестселлер.
    ids["Сөре"] = service.add_book(
        db, "author", "Сөредегі кітап", "Темірлан", year=2026,
        genre="рассказ", language="kk",
        description="Қысқа әңгіме: кітапханадағы ұмытылған кітап туралы.",
        content="Кітапхананың ең жоғарғы сөресінде бір кітап тұрды. Оны "
                "ешкім алмаған еді.\n\nБір күні бір студент баспалдаққа "
                "шығып, оны қолына алды. Кітап ақырын сыбырлады: "
                "«Ақыры келдің бе?»",
        cover_color="#9b3b54", cover_pattern="ornament",
        tags=["әңгіме", "кітапхана"], added_by=author2["id"])
    service.add_comment(db, author2, ids["Сөре"],
                        "Оқығандарыңызға рақмет! Пікір қалдырыңыз.")
    ids["Как стать амбассадором ИИ"] = service.add_book(
        db, "author", "Как стать амбассадором ИИ", "Темірлан", year=2026,
        genre="саморазвитие", language="ru",
        description="Вымышленная история о том, как школьник научился "
                    "разговаривать с нейросетями и к двадцати годам стал "
                    "миллиардером. С формулой успеха внутри.",
        content=_demo("ai_ambassador"), cover_color="#0f4c81",
        cover_pattern="sun", is_paid=True, price=4990, paid_days=30,
        tags=["искусственный интеллект", "саморазвитие", "бестселлер"],
        added_by=author2["id"])
    service.add_comment(db, author2, ids["Как стать амбассадором ИИ"],
                        "Первые десять читателей получат бесплатную "
                        "консультацию по промптам. Шучу. Или нет.")

    _add_easter_eggs(db, editor, ids)
    _add_pictures(db, ids)
    people = {"daniyar": reader, "murathan": student, "seyilkhan": applicant,
              "vladimir_p": vladimir, "altynbek": moder, "khadizat": editor,
              "edige": spammer}
    _add_comments(db, people, ids)
    _add_game_records(db, {"muhan": owner, "daniyar": reader,
                           "temirlan": author2, "altynbek": moder,
                           "murathan": student, "vladimir_p": vladimir,
                           "seyilkhan": applicant})
    for who, title in ((reader, "Капитанская дочка"),
                       (reader, "Moby-Dick"), (student, "Шинель"),
                       (student, "Отцы и дети"), (moder, "Каштанка"),
                       (editor, "Горе от ума"), (applicant, "Жаз")):
        service.set_shelf_status(db, who["id"], ids[title], "read")
        service.rate_book(db, who, ids[title], 4 + (len(title) % 2))

    # Бан с заявкой на разбан — для демонстрации модерации.
    service.ban_user(db, moder, spammer["id"], "Спам ссылками в комментариях",
                     seconds=7 * 24 * 3600)
    service.create_unban_request(db, spammer["id"],
                                 "Извините, больше не буду публиковать "
                                 "ссылки.")
    service.ban_user(db, owner, banned["id"], "Оскорбления и угрозы",
                     seconds=None)
    # Заявка на статус студента с картинкой «студбилета» — для модератора.
    service.submit_student_request(db, applicant, _demo_student_card())
    # Комментарии, добавленные выше напрямую, «состарим» на три недели,
    # чтобы на сайте не было «46 секунд назад» рядом с недельными отзывами.
    recent = (service._now() - timedelta(minutes=30)).strftime(
        service.DATETIME_FMT)
    for (cid,) in db.execute("SELECT id FROM comments WHERE created_at >= ?",
                             (recent,)).fetchall():
        when = service._now() - timedelta(days=22, minutes=-cid * 37)
        db.execute("UPDATE comments SET created_at = ? WHERE id = ?",
                   (when.strftime(service.DATETIME_FMT), cid))
    db.commit()
    add_demo_news(db, editor)
    service.log_action(db, owner["id"], "seed", "демо-данные созданы")

    count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    print(f"Готово: {len(ids)} книг, {count} пользователей. Вход: muhan / "
          f"{DEMO_PASSWORD}")
    db.close()


def _add_easter_eggs(db, editor, ids: dict) -> None:
    """Пасхалки: карточки «Гарри Поттера» и всех томов Re:Zero.

    Названия, авторы и годы — общеизвестные факты; аннотации написаны
    нами. Обложки рисуются сайтом (картинки издателей не используются).
    """
    for item in _demo_json("harry_potter.json"):
        ids[item["title"]] = service.add_book(
            db, "editor", item["title"], "Джоан Роулинг", year=item["year"],
            genre="фэнтези", language="ru", description=item["description"],
            content=item["content"] + "\n\n" + COPYRIGHT_NOTE.format(
                holder="© J. K. Rowling"),
            cover_color=item["color"], cover_pattern=item["pattern"],
            tags=["гарри поттер", "фэнтези", "пасхалка"],
            added_by=editor["id"])

    rz = _demo_json("rezero.json")
    for arc in rz.get("arcs", []):
        size = arc["to"] - arc["from"] + 1
        for number in range(arc["from"], arc["to"] + 1):
            date = rz["dates"][number - 1]
            year, month, day = (int(x) for x in date.split("-"))
            when = f"{day} {MONTHS[month - 1]} {year} года"
            k = number - arc["from"] + 1
            about = (f"Том {number} — {k}-й из {size} томов {arc['n']}-й "
                     f"арки.")
            if k == 1:
                about += " С него начинается новая арка."
            elif k == size and arc["n"] < len(rz["arcs"]):
                about += " Им эта арка завершается."
            # Номер тома — в начале, чтобы его было видно на обложке.
            title = f"Re:Zero. Том {number}. Жизнь с нуля в альтернативном " \
                    "мире"
            ids[title] = service.add_book(
                db, "editor", title, rz["author"], year=year,
                genre="ранобэ", language="ru",
                description=f"Арка {arc['n']} «{arc['name']}». Японское "
                            f"издание — {when}.",
                content=(f"## О серии\n\n{rz['about']}\n\n"
                         f"{rz['heroes']}\n\n"
                         f"## Арка {arc['n']}. «{arc['name']}»\n\n"
                         f"{arc['premise']}\n\n## Этот том\n\n{about} "
                         f"Японское издание вышло {when}. "
                         f"{rz['publisher']}\n\n"
                         + COPYRIGHT_NOTE.format(
                             holder="© Таппэй Нагацуки, Kadokawa")),
                cover_color=arc["color"], cover_pattern=arc["pattern"],
                tags=["re:zero", "ранобэ", "пасхалка"],
                added_by=editor["id"])


# Обложки-портреты авторов (общественное достояние, источники —
# app/demo/img/SOURCES.json) и иллюстрации Джона Тенниела к «Алисе».
COVER_IMAGES = {
    "Қара сөздер": "abai", "Ғылым таппай мақтанба": "abai",
    "Анна Каренина": "tolstoy", "Евгений Онегин": "pushkin",
    "Преступление и наказание": "dostoevsky", "Мёртвые души": "gogol",
    "Герой нашего времени": "lermontov", "Дама с собачкой": "chekhov",
    "Pride and Prejudice": "austen", "Hamlet": "shakespeare",
    "Отцы и дети": "turgenev",
}
ALICE_PICTURES = (
    ("alice_caterpillar", "The Caterpillar on the mushroom (chapter V)"),
    ("alice_cheshire", "The Cheshire Cat (chapter VI)"),
    ("alice_teaparty", "A Mad Tea-Party (chapter VII)"),
)


def _copy_picture(key: str) -> Optional[str]:
    """Скопировать картинку из app/demo/img в загрузки под случайным именем."""
    sources = _demo_json(os.path.join("img", "SOURCES.json"))
    info = sources.get(key)
    if not info:
        return None
    src = os.path.join(DEMO_DIR, "img", info["file"])
    if not os.path.exists(src):
        return None
    folder = os.path.join(os.path.dirname(DB_PATH), "uploads", "images")
    os.makedirs(folder, exist_ok=True)
    ext = os.path.splitext(info["file"])[1].lower().replace(".jpeg", ".jpg")
    name = secrets.token_hex(16) + ext
    shutil.copyfile(src, os.path.join(folder, name))
    return name


def _add_pictures(db, ids: dict) -> None:
    for title, key in COVER_IMAGES.items():
        name = _copy_picture(key)
        if name and title in ids:
            service.set_book_cover(db, ids[title], name)

    alice = ids.get("Alice's Adventures in Wonderland")
    if not alice:
        return
    credit = "Illustration by John Tenniel, 1865 (public domain)"
    content = service.get_book(db, alice)["content"]
    body = content.partition("\n\n" + PD_NOTE_EN)[0]
    blocks = body.split("\n\n")
    rabbit = _copy_picture("alice_rabbit")
    if rabbit:
        service.add_book_image(db, alice, rabbit)
        at = next((i for i, b in enumerate(blocks) if "Rabbit" in b), 0)
        blocks.insert(at + 1, f"![The White Rabbit. {credit}](img:{rabbit})")
    gallery = []
    for key, caption in ALICE_PICTURES:
        name = _copy_picture(key)
        if name:
            service.add_book_image(db, alice, name)
            gallery.append(f"![{caption}. {credit}](img:{name})")
    if gallery:
        blocks += ["## Pictures from the next chapters"] + gallery
    text = "\n\n".join(blocks) + "\n\n" + PD_NOTE_EN
    db.execute("UPDATE books SET content = ? WHERE id = ?", (text, alice))
    db.commit()


def _add_comments(db, people: dict, ids: dict) -> None:
    """Отзывы на каждой книге: хорошие, средние и плохие, разными людьми.

    Едіге (спамер) успевает оставить спам и пару грубых слов до бана —
    цензура заменяет мат звёздочками, это удобно показать на защите.
    Даты комментариев разнесены по последним трём неделям.
    """
    pools = _demo_json("comments.json")
    special = pools["special"]
    regular = ["daniyar", "vladimir_p", "murathan", "seyilkhan", "altynbek",
               "khadizat"]
    native = {"daniyar": "ru", "vladimir_p": "ru", "altynbek": "ru",
              "murathan": "kk", "khadizat": "kk"}
    mat = [line for line in pools["edige_spam"]
           if service.censor_profanity(line) != line]
    spam = [line for line in pools["edige_spam"] if line not in mat]
    now = service._now()

    for book_id in ids.values():
        book = service.get_book(db, book_id)
        title = book["title"]
        rng = random.Random("comments:" + title)
        entries: list[tuple[str, str, str]] = []
        if title in special:
            entries = [tuple(e) for e in special[title]]
        else:
            group = ("harry" if "Гарри Поттер" in title else
                     "rezero" if title.startswith("Re:Zero") else "")
            if group:
                entries = [tuple(e) for e in rng.sample(special[group], 2)]
            chosen = rng.sample(regular, rng.randint(2, 3) - bool(group))
            moods = ["good", "mid", "bad"]
            rng.shuffle(moods)
            for i, who in enumerate(chosen):
                mood = "good" if who == "altynbek" else (
                    moods[i] if i < 3 else rng.choice(["good", "mid"]))
                lang = native.get(who) or rng.choice(["ru", "kk"])
                if book["language"] == "en" and rng.random() < .5:
                    lang = "en"
                pool = pools[lang].get(mood) or pools["ru"][mood]
                used = {e[2] for e in entries}
                text = rng.choice([p for p in pool if p not in used] or pool)
                entries.append((who, mood, text))
        if rng.random() < .55:
            line = rng.choice(mat) if rng.random() < .7 else rng.choice(spam)
            entries.append(("edige", "spam", line))
        rng.shuffle(entries)

        for index, (who, mood, text) in enumerate(entries):
            user = people[who]
            cid = service.add_comment(db, user, book_id, text)
            when = now - timedelta(days=rng.uniform(.2, 21),
                                   minutes=index * 7)
            db.execute("UPDATE comments SET created_at = ? WHERE id = ?",
                       (when.strftime(service.DATETIME_FMT), cid))
            if mood == "spam":
                continue
            value = {"good": 5 if who == "altynbek" else rng.choice((4, 5)),
                     "mid": 3, "bad": rng.choice((1, 2))}[mood]
            service.rate_book(db, user, book_id, value)
            service.set_shelf_status(db, user["id"], book_id,
                                     "dropped" if mood == "bad" else "read")
        db.commit()


def _add_game_records(db, players: dict) -> None:
    """Рекорды мини-игры «Парақ» (главный разработчик — не первый)."""
    records = {"temirlan": (184000, 9100, {"bookmark": 12, "student": 15,
                                           "lamp": 10, "shelf": 6, "hall": 3,
                                           "edige": 1, "altynbek": 1,
                                           "temirlan": 1}),
               "daniyar": (52400, 4300, {"bookmark": 8, "student": 10,
                                         "lamp": 6, "shelf": 3,
                                         "edige": 1}),
               "muhan": (31700, 2950, {"bookmark": 6, "student": 8,
                                       "lamp": 5, "shelf": 2}),
               "altynbek": (12900, 2200, {"bookmark": 5, "student": 6,
                                          "lamp": 3, "altynbek": 1}),
               "murathan": (4100, 1500, {"bookmark": 4, "student": 4,
                                         "lamp": 1}),
               "vladimir_p": (880, 640, {"bookmark": 2, "student": 2}),
               "seyilkhan": (240, 240, {"bookmark": 1})}
    # В таблице рекордов остаются результаты, но улучшения у всех с нуля:
    # кто войдёт под демо-аккаунтом, начнёт игру заново (рекорд сохранится).
    stamp = service._now_str()
    for key, (total, clicks, _owned) in records.items():
        db.execute(
            "INSERT INTO game_saves(user_id, pages, pages_total, clicks, "
            "upgrades, updated_at) VALUES (?, 0, ?, ?, '{}', ?)",
            (players[key]["id"], float(total), clicks, stamp))
    db.commit()


def _demo_student_card() -> str:
    """Создать PNG-картинку «студенческий билет» для демо-заявки.

    Рисуем без сторонних библиотек: PNG = сигнатура + блоки IHDR/IDAT/IEND,
    где IDAT — сжатые zlib строки пикселей. Возвращает имя файла.
    """
    width, height = 320, 200
    rows = bytearray()
    for y in range(height):
        rows.append(0)  # фильтр строки: «без фильтра»
        for x in range(width):
            if y < 44:
                pixel = (15, 110, 90)               # зелёная шапка билета
            elif 64 <= y < 160 and 20 <= x < 100:
                pixel = (190, 180, 160)             # место для фото
            elif y in range(70, 150, 20) and 120 <= x < 290 - y // 3:
                pixel = (60, 60, 60)                # «строки текста»
            else:
                pixel = (246, 243, 236)             # фон
            rows.extend(pixel)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0,
                                        0, 0))
           + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
           + chunk(b"IEND", b""))
    folder = os.path.join(os.path.dirname(DB_PATH), "uploads", "students")
    os.makedirs(folder, exist_ok=True)
    name = secrets.token_hex(16) + ".png"
    with open(os.path.join(folder, name), "wb") as fh:
        fh.write(png)
    return name


def create_owner() -> None:
    """Создать главного разработчика на рабочем сервере (без демо-данных).

    Данные берутся из переменных окружения OQU_OWNER_USERNAME,
    OQU_OWNER_EMAIL и OQU_OWNER_PASSWORD, чтобы пароль не попал в историю
    команд оболочки.
    """
    username = os.environ.get("OQU_OWNER_USERNAME", "")
    email = os.environ.get("OQU_OWNER_EMAIL", "")
    password = os.environ.get("OQU_OWNER_PASSWORD", "")
    if not (username and email and password):
        print("Задайте OQU_OWNER_USERNAME, OQU_OWNER_EMAIL, "
              "OQU_OWNER_PASSWORD")
        raise SystemExit(1)
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = connect(DB_PATH)
    try:
        if db.execute("SELECT 1 FROM users WHERE role = 'owner'").fetchone():
            print("Главный разработчик уже есть — ничего не меняю.")
            return
        service.register_user(db, username, email, password, role="owner",
                              display_name=username)
        print(f"Создан главный разработчик «{username}».")
    finally:
        db.close()


STAFF_ACCOUNTS = ("muhan", "khadizat", "moder01", "author01", "author02")


def set_staff_password(ask_skip: bool = False) -> None:
    """Задать свой пароль служебным демо-аккаунтам (ввод с клавиатуры).

    Нужно, когда сайт открыт в интернет: демо-пароль опубликован в README,
    и любой мог бы войти как владелец. Пароль вводится скрыто (getpass)
    и в истории команд не остаётся.
    """
    import getpass

    from app import security

    print("Новый пароль для служебных аккаунтов: " + ", ".join(STAFF_ACCOUNTS))
    hint = " (Enter - оставить прежний)" if ask_skip else ""
    password = getpass.getpass(f"Пароль{hint}: ")
    if not password:
        print("Пароль не изменён.\n")
        return
    if len(password) < 8:
        print("Слишком короткий (меньше 8 символов) - пароль не изменён.\n")
        return
    if getpass.getpass("Повторите пароль: ") != password:
        print("Пароли не совпали - пароль не изменён.\n")
        return
    db = connect(DB_PATH)
    try:
        marks = ",".join("?" * len(STAFF_ACCOUNTS))
        cur = db.execute(
            "UPDATE users SET password_hash = ? "
            f"WHERE username IN ({marks})",
            (security.hash_password(password), *STAFF_ACCOUNTS))
        db.commit()
        print(f"Пароль изменён у {cur.rowcount} аккаунтов. Запомните его!\n")
    finally:
        db.close()


def add_demo_news(db, author) -> int:
    """Демо-новости для главной: марафон, конкурсы, событие, обновления.

    Добавляются, только если новостей ещё нет. ``author`` — редактор или
    владелец (у него есть право ``news.manage``). Возвращает число новостей.
    """
    if db.execute("SELECT COUNT(*) FROM news").fetchone()[0]:
        return 0

    def book_link(title: str) -> str:
        row = db.execute("SELECT id FROM books WHERE title = ?",
                         (title,)).fetchone()
        return f"#/book/{row['id']}" if row else "#/catalog"

    now = service._now()

    def ago(days: float) -> str:
        return (now - timedelta(days=days)).strftime(service.DATETIME_FMT)

    # (тип, заголовок, текст, ссылка, приз, срок, закреплено, дней назад)
    items = [
        ("update", "Кыргызский язык интерфейса",
         "Сайт теперь на четырёх языках: қазақша, русский, кыргызча и "
         "English. Язык переключается в шапке сайта.", "#/about", "", None,
         False, 5),
        ("event", "Защита проекта «Оқу» 8 декабря",
         "Окончательная защита в КУ им. Коркыт Ата: покажем марафоны "
         "чтения, план интеграции с Platonus и живую презентацию.",
         "#/about", "", "2026-12-08 12:00:00", False, 3),
        ("contest", "Турнир «Парақ» среди групп",
         "Соберите больше всех страниц в мини-игре до конца семестра. "
         "Рекорды видны в разделе «Статистика».", "#/game",
         "звание «Главный читатель группы»", "2026-12-31 18:59:59", False, 2),
        ("contest", "Конкурс отзывов «Абай и мы»",
         "Напишите отзыв на «Қара сөздер» от 300 слов своими словами, без "
         "копирования из интернета. Три лучших отзыва выберут модераторы.",
         book_link("Қара сөздер"), "книжный сертификат 10 000 ₸",
         "2026-12-20 18:59:59", False, 1),
        ("update", "Обновление 2.1: новости и конкурсы",
         "На главной появился раздел новостей. Редакторы публикуют "
         "конкурсы со сроком и призом, а сайт сам считает, сколько дней "
         "осталось.", "#/news", "", None, False, 0.5),
        ("marathon", "Зимний марафон «15 книг до весны»",
         "С 1 декабря по 1 марта. Книга: 250 баллов, отзыв: +50, книга за "
         "10–15 дней: +50. Книга засчитывается после мини-теста. Лучшие "
         "группы выходят в командный квиз.", "#/catalog",
         "сертификат каждому, призёрам книги", "2027-03-01 18:59:59", True,
         0.2),
    ]
    for kind, title, body, link, prize, ends, pinned, days in items:
        nid = service.add_news(db, author, kind=kind, title=title, body=body,
                               link=link, prize=prize, ends_at=ends,
                               pinned=pinned)
        db.execute("UPDATE news SET created_at = ? WHERE id = ?",
                   (ago(days), nid))
    db.commit()
    return len(items)


def seed_news() -> None:
    """Добавить демо-новости в уже наполненную базу (например, на сервере):
    ``python -m app.seed --news``."""
    db = connect(DB_PATH)
    try:
        author = db.execute("SELECT * FROM users WHERE role IN ('owner', "
                            "'editor') ORDER BY role = 'owner' DESC, id "
                            "LIMIT 1").fetchone()
        if author is None:
            print("Нет владельца или редактора — сначала создайте базу.")
            return
        added = add_demo_news(db, author)
        print(f"Добавлено новостей: {added}" if added
              else "Новости уже есть — ничего не добавлено.")
    finally:
        db.close()


if __name__ == "__main__":
    if "--news" in sys.argv:
        seed_news()
    elif "--create-owner" in sys.argv:
        create_owner()
    elif "--staff-password" in sys.argv:
        set_staff_password()
    else:
        if "--reset" in sys.argv:
            _reset()
        seed()
