"""Наполнение базы демонстрационными данными.

Запуск::

    python -m app.seed           # наполнить, если база пустая
    python -m app.seed --reset   # удалить базу и создать заново

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
import secrets
import struct
import sys
import zlib

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
    for sub in ("books", "students"):
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

    owner = user("muhan", "muhan@oqu.kz", "owner", "Мұхан Надирхалиф")
    editor = user("khadizat", "khadizat@oqu.kz", "editor", "Жоробекова Хадизат", "kk")
    moder = user("moder01", "moder@oqu.kz", "moderator", "Модератор Айгерім")
    author = user("author01", "author@oqu.kz", "author", "Команда «Оқу»")
    student = user("student01", "student@oqu.kz", "user", "Студент Нұрлан",
                   "kk")
    service.verify_student(db, "owner", student["id"])
    student = service.get_user(db, student["id"])
    reader = user("reader01", "reader@oqu.kz", "user", "Читатель Дана")
    spammer = user("spammer01", "spam@oqu.kz", "user", "Нарушитель")
    applicant = user("applicant01", "applicant@oqu.kz", "user",
                     "Абитуриент Ерлан", "kk")
    banned = user("banned01", "banned@oqu.kz", "user", "Забаненный навсегда")
    author2 = user("author02", "author2@oqu.kz", "author", "Автор Айсұлу",
                   "kk")

    ids: dict[str, int] = {}
    for title, writer, year, genre, lang, color, text, tags, desc in BOOKS:
        ids[title] = service.add_book(
            db, "editor", title, writer, year=year, genre=genre,
            language=lang, description=desc, content=text,
            cover_color=color, tags=tags, added_by=editor["id"])
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "demo", "books_extra.json"),
              encoding="utf-8") as fh:
        for item in json.load(fh):
            ids[item["title"]] = service.add_book(
                db, "editor", item["title"], item["author"],
                year=item["year"], genre=item["genre"],
                language=item["language"], description=item["description"],
                content=item["content"] + "\n\n" + {
                    "kk": PD_NOTE_KK, "en": PD_NOTE_EN}.get(
                        item["language"], PD_NOTE),
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
        (moder, "Alice's Adventures in Wonderland", "reading", 600, 4),
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

    # Второй автор: своя бесплатная книга и комментарий с припиской.
    ids["Сөре"] = service.add_book(
        db, "author", "Сөредегі кітап", "Автор Айсұлу", year=2026,
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
    service.log_action(db, owner["id"], "seed", "демо-данные созданы")

    count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    print(f"Готово: {len(ids)} книг, {count} пользователей. Вход: muhan / "
          f"{DEMO_PASSWORD}")
    db.close()


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


if __name__ == "__main__":
    if "--create-owner" in sys.argv:
        create_owner()
    else:
        if "--reset" in sys.argv:
            _reset()
        seed()
