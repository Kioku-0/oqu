"""Презентация предзащиты «Оқу» в PowerPoint: 12 слайдов, три версии.

Слайды одинаковые; речь Мұхана всегда по-русски, речь Хадизат - на языке
версии (казахский, кыргызский или русский). Цвет докладчика: фиолетовый -
Мұхан, жёлтый - Хадизат. Запуск:

    python make_pptx.py

Нужны python-pptx и qrcode (pip install python-pptx qrcode).
"""

import io
import os

import qrcode
from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Pt

from notes import HADIZAT, MUHAN, THANKS

HERE = os.path.dirname(os.path.abspath(__file__))
PRES_DIR = os.path.dirname(HERE)
PROJECT = os.path.dirname(os.path.dirname(PRES_DIR))
IMG = os.path.join(PROJECT, "docs", "img")
SITE = "https://130-17-21-59.sslip.io"

VERSIONS = {"рус-каз": "Оқу_предзащита_рус-каз.pptx",
            "рус-кыр": "Оқу_предзащита_рус-кыр.pptx",
            "рус": "Оқу_предзащита_рус.pptx"}

HEAD, BODY, MONO = "Cambria", "Calibri", "Consolas"
PAPER, PAPER2, CARD = "F3F4EF", "E9EBE4", "FCFCFA"
INK, SOFT, MUTED, LINE = "1B1D1A", "45493F", "767B70", "D9DCD3"
LIGHT, DSOFT = "F3F4EF", "C3C8BE"
GREEN, GREEN_SOFT = "0F6E5A", "DCEBE4"
# Цвета докладчиков
SPK = {
    "m": {"main": "6A3FC8", "soft": "ECE6FA", "on": "FFFFFF",
          "text": "5A33B0"},
    "h": {"main": "F2B705", "soft": "FFF3C4", "on": "1B1D1A",
          "text": "8A6400"},
}

L, W = 120, 1680          # поля и ширина рабочей области (холст 1920×1080)


def px(v):
    return Emu(int(v * 6350))


def rgb(h):
    return RGBColor.from_string(h)


# --- Примитивы ---------------------------------------------------------------
def background(slide, color):
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = rgb(color)


def box(slide, x, y, w, h, color, shape="rect", radius=18, line=None):
    kind = {"rect": MSO_SHAPE.RECTANGLE,
            "round": MSO_SHAPE.ROUNDED_RECTANGLE,
            "oval": MSO_SHAPE.OVAL}[shape]
    shp = slide.shapes.add_shape(kind, px(x), px(y), px(w), px(h))
    shp.fill.solid()
    shp.fill.fore_color.rgb = rgb(color)
    if line:
        shp.line.color.rgb = rgb(line)
        shp.line.width = Pt(1)
    else:
        shp.line.fill.background()
    shp.shadow.inherit = False
    if shape == "round":
        shp.adjustments[0] = min(0.5, radius / min(w, h))
    return shp


def text(slide, x, y, w, h, paras, size=28, color=SOFT, font=BODY,
         bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
         spacing=1.12, gap=0.3):
    """paras: строка или список абзацев; абзац - строка или список кусков
    (текст, {опции: bold, color, font, size})."""
    tb = slide.shapes.add_textbox(px(x), px(y), px(w), px(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, para in enumerate([paras] if isinstance(paras, str) else paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = spacing
        if i:
            p.space_before = Pt(size * gap)
        for chunk, opt in (para if isinstance(para, list) else [(para, {})]):
            r = p.add_run()
            r.text = chunk
            f = r.font
            f.name = opt.get("font", font)
            f.size = Pt(opt.get("size", size) / 2)
            f.bold = opt.get("bold", bold)
            f.color.rgb = rgb(opt.get("color", color))
    return tb


def picture(slide, name, x, y, w, h, frame="DDE1D8"):
    path = os.path.join(IMG, name)
    iw, ih = Image.open(path).size
    if frame:
        box(slide, x, y, w, h, frame, "round", 16)
    k = min(w / iw, h / ih)
    pw, ph = iw * k, ih * k
    slide.shapes.add_picture(path, px(x + (w - pw) / 2),
                             px(y + (h - ph) / 2), px(pw), px(ph))


def pill(slide, x, y, label, spk, size=22):
    c = SPK[spk]
    w = len(label) * size * 0.62 + 44
    box(slide, x, y, w, 44, c["main"], "round", 22)
    text(slide, x, y, w, 44, label.upper(), size=size, color=c["on"],
         bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)


def num_dot(slide, x, y, d, label, spk, size=26):
    c = SPK[spk]
    box(slide, x, y, d, d, c["main"], "oval")
    text(slide, x, y, d, d, label, size=size, color=c["on"], bold=True,
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)


def card(slide, x, y, w, h, title, body, fill=CARD, tsize=32, bsize=26,
         tcolor=INK):
    box(slide, x, y, w, h, fill, "round", 18)
    text(slide, x + 28, y + 22, w - 56, tsize * 1.3, title, size=tsize,
         color=tcolor, font=HEAD, bold=True)
    text(slide, x + 28, y + 30 + tsize * 1.3, w - 56,
         h - 52 - tsize * 1.3, body, size=bsize)


def table(slide, x, y, w, rows, widths, row_h=54, size=24, head=None,
          bold_first=False, mono_col=None):
    shp = slide.shapes.add_table(len(rows), len(rows[0]), px(x), px(y),
                                 px(w), px(row_h * len(rows)))
    tbl = shp.table
    tbl.first_row = True
    tbl.horz_banding = False
    for j, frac in enumerate(widths):
        tbl.columns[j].width = px(w * frac)
    for i, row in enumerate(rows):
        tbl.rows[i].height = px(row_h)
        for j, val in enumerate(row):
            cell = tbl.cell(i, j)
            cell.fill.solid()
            cell.fill.fore_color.rgb = rgb(head or GREEN_SOFT) if i == 0 \
                else rgb(CARD if i % 2 else PAPER2)
            cell.margin_left = cell.margin_right = px(14)
            cell.margin_top = cell.margin_bottom = px(6)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = cell.text_frame
            tf.word_wrap = True
            tf.paragraphs[0].text = ""
            r = tf.paragraphs[0].add_run()
            r.text = val
            f = r.font
            f.size = Pt(size / 2)
            f.name = MONO if (mono_col == j and i) else BODY
            f.bold = i == 0 or (bold_first and j == 0)
            f.color.rgb = rgb(INK)
    return tbl


def frame(prs, spk, eyebrow, title, page, section, bg=PAPER):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    background(s, bg)
    pill(s, L, 72, eyebrow, spk)
    text(s, L, 132, W, 80, title, size=58, color=INK, font=HEAD, bold=True)
    text(s, L, 1006, 1300, 30, "Оқу · " + section, size=22, color=MUTED)
    num_dot(s, L + W - 48, 994, 48, str(page), spk, size=22)
    return s


# --- Слайды ------------------------------------------------------------------
def s_cover(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    background(s, INK)
    pill(s, L, 150, "Курсовой проект · вариант 11", "h")
    text(s, L, 215, 900, 250, "Оқу", size=230, color=LIGHT, font=HEAD,
         bold=True)
    text(s, L, 478, 880, 130, "Электронная библиотека с REST API "
         "и документацией OpenAPI", size=46, color=LIGHT, spacing=1.05)
    chips = ["FastAPI + JWT", "59 маршрутов API", "16 таблиц", "4 языка"]
    x = L
    for c in chips:
        w = len(c) * 15 + 40
        box(s, x, 640, w, 48, "2C2F2A", "round", 24)
        text(s, x, 640, w, 48, c, size=24, color="F2B705", bold=True,
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        x += w + 14
    for i, (lab, val) in enumerate([
            ("Выполнили", "Мұхан Надирхалиф, Жоробекова Хадизат · Сиб-24-1"),
            ("Руководитель", "Айтимов Мурат Жолдасбекович")]):
        text(s, L, 760 + i * 84, 900, 28, lab, size=22, color="8D948A")
        text(s, L, 790 + i * 84, 900, 40, val, size=30, color=LIGHT)
    picture(s, "01_home.png", 980, 200, 680, 425, frame="2C2F2A")
    box(s, 1574, 440, 226, 466, "3A3D37", "round", 22)
    picture(s, "17_mobile_home.jpg", 1584, 450, 206, 446, frame=None)
    text(s, L, 1006, 1300, 30, "Кызылординский университет имени Коркыт "
         "Ата · 2026", size=22, color="8D948A")
    return s


def s_problem(prs):
    s = frame(prs, "h", "Зачем это нужно", "Студенту неудобно читать "
              "книги вуза онлайн", 2, "проблема")
    probs = [("Сложный доступ", "В МегаПро в основном сканы, до книги "
              "несколько шагов, с телефона читать тяжело"),
             ("Нет «продолжить»", "Негде отметить, что читаешь, и вернуться "
              "на ту же страницу"),
             ("Платно и без казахского", "Популярные сервисы платные и "
              "почти не знают казахского языка")]
    for i, (t, b) in enumerate(probs):
        y = 256 + i * 116
        num_dot(s, L, y + 4, 56, str(i + 1), "h")
        text(s, L + 80, y, 780, 40, t, size=30, color=INK, font=HEAD,
             bold=True)
        text(s, L + 80, y + 42, 780, 64, b, size=25, spacing=1.0)
    x = L + 900
    box(s, x, 252, W - 900, 330, SPK["h"]["soft"], "round", 20)
    text(s, x + 32, 274, W - 964, 44, "Наше решение: «Оқу»", size=32,
         color=INK, font=HEAD, bold=True)
    text(s, x + 32, 328, W - 964, 250, [
        "книга открывается одной кнопкой «Читать»",
        "чтение продолжается с места остановки",
        "интерфейс на 4 языках, есть версия для телефона",
        "новинки бесплатны для студентов вуза",
        "открытый REST API для других программ"], size=26, color=INK,
        gap=0.18)
    table(s, L, 612, W, [
        ["Что важно", "МегаПро", "MangaLib", "Goodreads", "ЛитРес", "Оқу"],
        ["Продолжить с места остановки", "нет", "да", "-", "да", "да"],
        ["Казахский интерфейс", "частично", "нет", "нет", "нет", "да"],
        ["Бесплатно для студентов", "да", "частично", "да", "нет", "да"],
        ["Открытый API", "нет", "нет", "закрыт", "нет", "да"]],
        [0.32, 0.136, 0.136, 0.136, 0.136, 0.136], row_h=60, size=24,
        head=SPK["h"]["soft"])
    return s


def s_task(prs):
    s = frame(prs, "m", "Задание варианта 11", "Что требовалось и как мы "
              "это выполнили", 3, "задание")
    table(s, L, 248, W, [
        ["Требование", "Как выполнено", "Где в коде"],
        ["REST API на FastAPI", "59 маршрутов в 10 группах: книги, полка, "
         "комментарии, модерация, журнал…", "app/web.py"],
        ["Документация OpenAPI", "Swagger UI на /docs и ReDoc на /redoc "
         "строятся автоматически по коду", "/openapi.json"],
        ["Аутентификация JWT", "Подпись HS256: access на 30 мин + refresh "
         "на 7 дней; пароли PBKDF2-SHA256", "app/security.py"],
        ["Постраничный вывод", "page и page_size (1-100, по умолчанию 20) "
         "→ items, total, page, pages", "service._paginate"],
        ["Журнал действий (усложнение)", "action_log: кто, что, когда "
         "(UTC), IP; фильтры, CSV, хранение 365 дней", "service.log_action"],
        ["Логика отдельно + тесты", "service.py не знает про HTTP; "
         "155 тестов pytest, покрытие 89,4%", "app/service.py, tests/"]],
        [0.25, 0.57, 0.18], row_h=74, size=24, bold_first=True,
        mono_col=2, head=SPK["m"]["soft"])
    c = SPK["m"]
    box(s, L, 790, W, 150, c["main"], "round", 20)
    text(s, L + 36, 806, W - 72, 120, [
        [("Сверх задания: ", {"bold": True}),
         ("поверх этого же API сделан полноценный сайт для читателей "
          "(7 ролей, читалка, 4 языка, телефон), и он работает в интернете "
          "на сервере с HTTPS.", {})]], size=30, color=c["on"],
        anchor=MSO_ANCHOR.MIDDLE)
    return s


CODE = """GET /api/books?page=2&page_size=10&sort=rating
→ 200 OK
{
  "items": [
    {"id": 26, "title": "A Study in Scarlet",
     "author": "Arthur Conan Doyle", "year": 1887, …},
    …
  ],
  "total": 88,
  "page": 2,
  "page_size": 10,
  "pages": 9
}"""


def s_backend(prs):
    s = frame(prs, "m", "Так выглядит бэкенд", "REST API и его "
              "документация Swagger", 4, "бэкенд", bg=PAPER2)
    picture(s, "22_swagger_top.png", L, 248, 820, 512, frame="D2D6CC")
    text(s, L, 774, 820, 34, "130-17-21-59.sslip.io/docs: все маршруты, "
         "кнопка Authorize, запросы прямо из браузера", size=22,
         color=MUTED)
    x = L + 860
    box(s, x, 248, W - 860, 430, "1E1F24", "round", 18)
    text(s, x + 28, 266, W - 916, 400, CODE.split("\n"), size=21,
         color="E6E3F5", font=MONO, gap=0, spacing=1.05)
    facts = [("10 групп", "маршрутов в OpenAPI"),
             ("JSON", "ответы и ошибки с кодом"),
             ("422", "неверные данные: Pydantic")]
    fw = (W - 860 - 2 * 16) / 3
    for i, (n, lab) in enumerate(facts):
        fx = x + i * (fw + 16)
        box(s, fx, 700, fw, 150, CARD, "round", 18)
        text(s, fx + 22, 716, fw - 44, 56, n, size=42, color=SPK["m"]["text"],
             font=HEAD, bold=True)
        text(s, fx + 22, 776, fw - 44, 66, lab, size=22)
    return s


def s_arch(prs):
    s = frame(prs, "m", "Архитектура", "Три слоя и почему эти "
              "технологии", 5, "архитектура")
    layers = [("Интерфейс", "index.html + JS без сборки, ~2 700 строк",
               GREEN_SOFT, INK),
              ("web.py · REST API", "маршруты, права, проверки · 1 109 строк",
               SPK["m"]["main"], "FFFFFF"),
              ("service.py · бизнес-логика", "правила, не знает про HTTP "
               "· 1 580 строк", SPK["m"]["main"], "FFFFFF"),
              ("db.py · SQLite", "16 таблиц, WAL, миграции", INK, LIGHT)]
    arrows = ["HTTP + JSON + JWT", "вызов функций", "SQL с параметрами «?»"]
    y, lw = 252, 860
    for i, (t, sub, fill, col) in enumerate(layers):
        box(s, L, y, lw, 104, fill, "round", 18)
        text(s, L + 30, y + 14, lw - 60, 40, t, size=32, color=col,
             font=HEAD, bold=True)
        text(s, L + 30, y + 58, lw - 60, 34, sub, size=24, color=col)
        y += 104
        if i < 3:
            text(s, L, y + 6, lw, 36, "↓  " + arrows[i], size=24,
                 color=SPK["m"]["text"], align=PP_ALIGN.CENTER)
            y += 48
    x, cw = L + lw + 40, W - lw - 40
    why = [("FastAPI", "документация OpenAPI и проверка данных (Pydantic) "
            "из коробки, быстрый"),
           ("SQLite", "один файл, ноль настройки; WAL - чтение не ждёт "
            "запись"),
           ("JS без сборки", "сайт открывается сразу, нечего собирать и "
            "обновлять"),
           ("Вторая платформа", "мобильное или настольное приложение "
            "подключится к тому же API, сервер не меняется")]
    for i, (t, b) in enumerate(why):
        card(s, x, 252 + i * 172, cw, 156, t, b, tsize=28, bsize=24,
             tcolor=SPK["m"]["text"])
    return s


def s_db(prs):
    s = frame(prs, "m", "Модель данных", "База данных: 16 таблиц в "
              "5 группах", 6, "база данных", bg=PAPER2)
    groups = [("Люди", ["users", "bans", "unban_requests",
                        "student_requests"]),
              ("Книги", ["books", "tags", "book_tags", "book_images"]),
              ("Чтение", ["shelf", "reading_progress", "bookmarks"]),
              ("Отзывы и покупки", ["comments", "ratings", "purchases"]),
              ("Служебные", ["action_log", "game_saves"])]
    gw = (W - 4 * 20) / 5
    for i, (g, tabs) in enumerate(groups):
        x = L + i * (gw + 20)
        box(s, x, 252, gw, 270, CARD, "round", 18)
        text(s, x + 22, 270, gw - 44, 40, g, size=28, color=SPK["m"]["text"],
             font=HEAD, bold=True)
        text(s, x + 22, 320, gw - 44, 250, tabs, size=23, color=INK,
             font=MONO, gap=0.25)
    rules = [("CHECK", "роль, язык, год 0-2100, цена ≥ 0, оценка 1-5"),
             ("Внешние ключи", "ON DELETE CASCADE: удалили книгу - ушли её "
              "отзывы и закладки; в журнале SET NULL"),
             ("Уникальность", "логин и почта UNIQUE; одна оценка на книгу: "
              "ключ (user_id, book_id)"),
             ("Скорость", "индексы на частых запросах; поиск по-казахски: "
              "свой LOWER() для Unicode")]
    cw = (W - 20) / 2
    for i, (t, b) in enumerate(rules):
        x = L + (i % 2) * (cw + 20)
        y = 548 + (i // 2) * 196
        card(s, x, y, cw, 176, t, b, fill=PAPER, tsize=30, bsize=26)
    return s


def s_security(prs):
    s = frame(prs, "m", "Безопасность", "Вход по JWT и защита данных", 7,
              "безопасность")
    steps = [("Логин и пароль", "POST /api/auth/login"),
             ("Сверка хэша", "PBKDF2-SHA256, соль, 600 000 итераций"),
             ("Два токена", "access 30 мин + refresh 7 дней, HS256"),
             ("Каждый запрос", "Authorization: Bearer …; 401 → сайт сам "
              "обновит токен")]
    sw = (W - 3 * 24) / 4
    for i, (t, b) in enumerate(steps):
        x = L + i * (sw + 24)
        box(s, x, 252, sw, 196, SPK["m"]["soft"], "round", 18)
        num_dot(s, x + 22, 272, 48, str(i + 1), "m", size=24)
        text(s, x + 84, 276, sw - 100, 40, t, size=28, color=INK, font=HEAD,
             bold=True)
        text(s, x + 22, 336, sw - 44, 100, b, size=24, color=INK)
    table(s, L, 480, W, [
        ["Угроза", "Как защищено"],
        ["Подбор пароля", "5 ошибок подряд - блокировка входа; не больше "
         "10 попыток в минуту с одного IP"],
        ["SQL-инъекция", "только параметризованные запросы; сортировка - "
         "из белого списка"],
        ["Утечка базы", "пароли хранятся только как хэш с солью; секрет JWT "
         "в переменной окружения, не в коде"],
        ["Подмена файлов", "проверка по первым байтам (%PDF-, PNG, JPEG), "
         "случайные имена, лимиты 40 и 5 МБ"],
        ["XSS и чужие скрипты", "экранирование вывода, заголовок CSP, "
         "HTTPS на сервере"],
        ["Перебор логинов", "фиктивный хэш: ответ одинаково долгий для "
         "любого логина"]],
        [0.24, 0.76], row_h=64, size=24, bold_first=True,
        head=SPK["m"]["soft"])
    return s


def s_log(prs):
    s = frame(prs, "h", "Усложнение варианта", "Журнал действий: кто, что "
              "и когда", 8, "журнал", bg=PAPER2)
    picture(s, "15_admin_log.png", L, 252, 880, 550, frame="D2D6CC")
    x, cw = L + 920, W - 920
    box(s, x, 252, cw, 150, SPK["h"]["soft"], "round", 18)
    text(s, x + 28, 262, 160, 130, "26", size=100, color=SPK["h"]["text"],
         font=HEAD, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    text(s, x + 200, 262, cw - 228, 130, "видов действий: вход, бан, "
         "покупка, правка книги, смена роли…", size=26, color=INK,
         anchor=MSO_ANCHOR.MIDDLE)
    items = [("В каждой записи", "время, пользователь, действие, "
              "подробности, IP"),
             ("Модератор может", "выбрать действие и даты, листать "
              "страницы, скачать CSV"),
             ("Хранение", "старше года - удаляется само")]
    for i, (t, b) in enumerate(items):
        card(s, x, 420 + i * 132, cw, 120, t, b, tsize=26, bsize=24)
    text(s, L, 820, 880, 70, "Ещё есть файл-журнал сервера: все запросы, "
         "время ответа, ошибки (instance/logs/oqu.log)", size=22,
         color=MUTED)
    return s


def s_roles(prs):
    s = frame(prs, "h", "Роли", "Семь ролей: каждому только нужные права",
              9, "роли")
    rows = [("Гость", "ищет и читает бесплатные книги"),
            ("Читатель", "+ полки, закладки, оценки, комментарии"),
            ("Студент", "+ платные новинки бесплатно после проверки "
             "студбилета"),
            ("Автор", "+ добавляет книги, меняет только свои"),
            ("Редактор", "+ управляет всеми книгами"),
            ("Модератор", "баны с причиной и сроком, разбан, студбилеты, "
             "журнал"),
            ("Главный разработчик", "всё, включая роли; его нельзя "
             "забанить")]
    for i, (r, d) in enumerate(rows):
        y = 252 + i * 84
        box(s, L, y, W, 72, CARD if i % 2 == 0 else PAPER2, "round", 14)
        lvl = SPK["h"]["main"] if i < 5 else "E0A400"
        box(s, L + 20, y + 20, 32, 32, lvl, "oval")
        text(s, L + 72, y, 420, 72, r, size=28, color=INK, font=HEAD,
             bold=True, anchor=MSO_ANCHOR.MIDDLE)
        text(s, L + 500, y, W - 520, 72, d, size=26, color=INK,
             anchor=MSO_ANCHOR.MIDDLE)
    box(s, L, 852, W, 84, SPK["h"]["soft"], "round", 18)
    text(s, L + 30, 852, W - 60, 84, [[
        ("Важно: ", {"bold": True}),
        ("права проверяет сервер при каждом запросе. Даже если найти "
         "скрытую кнопку, сервер ответит «нет доступа» (403).", {})]],
        size=26, color=INK, anchor=MSO_ANCHOR.MIDDLE)
    return s


def s_ui(prs):
    s = frame(prs, "h", "Что видит читатель", "Каталог, шкаф, читалка и "
              "телефон", 10, "интерфейс", bg=PAPER2)
    shots = [("02_catalog.png", "Каталог: поиск, фильтры, 3 вида"),
             ("04_bookcase.png", "Шкаф: книги на полках по жанрам"),
             ("06_reader.png", "Читалка: текст и PDF, закладки")]
    for i, (f, cap) in enumerate(shots):
        x = L + i * 486
        picture(s, f, x, 252, 466, 291, frame="D2D6CC")
        text(s, x, 556, 466, 34, cap, size=23, color=INK, bold=True)
    picture(s, "17_mobile_home.jpg", L + 1462, 252, 218, 472, frame=None)
    feats = ["4 языка: рус · қаз · кыр · eng", "тёмная тема",
             "продолжить чтение", "оценки и комментарии",
             "мини-игра «Парақ»", "цензура грубых слов"]
    x, y = L, 640
    for f in feats:
        w = len(f) * 14 + 44
        if x + w > L + 1440:
            x, y = L, y + 70
        box(s, x, y, w, 54, SPK["h"]["soft"], "round", 27)
        text(s, x, y, w, 54, f, size=24, color=INK, bold=True,
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        x += w + 16
    text(s, L, 800, 1420, 100, "88 книг в демо-каталоге: классика на "
         "трёх языках, тексты с иллюстрациями и формулами, PDF-сканы", size=24, color=MUTED)
    return s


def s_quality(prs):
    s = frame(prs, "m", "Качество", "Тесты: что именно проверено", 11,
              "тесты")
    nums = [("155", "автотестов pytest, все проходят"),
            ("89,4%", "покрытие логики (нужно ≥ 80%)"),
            ("0", "замечаний PEP 8 (ruff)"),
            ("66", "коммитов в Git (нужно ≥ 10)")]
    nw = (W - 3 * 20) / 4
    for i, (n, lab) in enumerate(nums):
        x = L + i * (nw + 20)
        box(s, x, 248, nw, 150, SPK["m"]["soft"], "round", 18)
        text(s, x + 24, 258, nw - 48, 80, n, size=68,
             color=SPK["m"]["text"], font=HEAD, bold=True)
        text(s, x + 24, 342, nw - 48, 50, lab, size=22, color=INK)
    table(s, L, 424, W, [
        ["Граничный или ошибочный случай", "Результат", "Тест"],
        ["Год издания 2101", "ошибка проверки", "test_add_book_bad_year"],
        ["Страница за концом списка", "пустой список",
         "test_page_beyond_end_is_empty"],
        ["page_size = 10 000", "урезается до 100",
         "test_pagination_page_size_clamped"],
        ["5 неверных паролей подряд", "вход заблокирован",
         "test_bruteforce_lockout"],
        ["Модератор банит главного разработчика", "запрещено",
         "test_cannot_ban_owner"],
        ["SQL в параметре сортировки", "игнорируется",
         "test_search_injection_in_sort_is_ignored"],
        ["Накрутка очков в игре", "сохранение отклонено",
         "test_game_too_fast_growth_rejected"]],
        [0.38, 0.2, 0.42], row_h=62, size=23, mono_col=2,
        head=SPK["m"]["soft"])
    return s


def qr_png():
    img = qrcode.make(SITE, border=1, box_size=12)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def s_finish(prs, thanks):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    background(s, INK)
    pill(s, L, 72, "Итог", "h")
    text(s, L, 132, W, 80, "Задание выполнено, и даже больше", size=58,
         color=LIGHT, font=HEAD, bold=True)
    cols = [("Требования варианта 11", "FastAPI и OpenAPI, JWT, страницы, "
             "журнал действий, тесты"),
            ("Сверх задания", "сайт: 7 ролей, читалка, шкаф, 4 языка, "
             "телефон, сервер с HTTPS"),
            ("Документы", "14 документов: ТЗ, архитектура, тесты, "
             "руководства, соглашение")]
    for i, (t, b) in enumerate(cols):
        y = 262 + i * 150
        box(s, L, y, 1080, 132, "2A2C28", "round", 18)
        box(s, L + 24, y + 42, 48, 48, "F2B705", "oval")
        text(s, L + 24, y + 42, 48, 48, "✓", size=28, color=INK, bold=True,
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        text(s, L + 96, y + 18, 960, 44, t, size=32, color=LIGHT,
             font=HEAD, bold=True)
        text(s, L + 96, y + 66, 960, 50, b, size=26, color=DSOFT)
    qx = L + 1180
    box(s, qx, 262, 420, 420, "F3F4EF", "round", 24)
    s.shapes.add_picture(qr_png(), px(qx + 30), px(292), px(360), px(360))
    text(s, qx, 700, 420, 34, "Откройте сайт прямо сейчас", size=24,
         color="F2B705", bold=True, align=PP_ALIGN.CENTER)
    text(s, qx - 40, 740, 500, 120, ["130-17-21-59.sslip.io",
         "github.com/Kioku-0/oqu"], size=24, color=DSOFT,
         align=PP_ALIGN.CENTER, gap=0.1)
    text(s, L, 760, 1080, 80, thanks, size=54, color="F2B705", font=HEAD,
         bold=True)
    text(s, L, 1006, 1300, 30, "Оқу · спасибо за внимание", size=22,
         color="8D948A")
    num_dot(s, L + W - 48, 994, 48, "12", "h", size=22)
    return s


ORDER = ["cover", "problem", "task", "backend", "arch", "db", "security",
         "log", "roles", "ui", "quality", "finish"]


def build(version, filename):
    prs = Presentation()
    prs.slide_width, prs.slide_height = px(1920), px(1080)
    prs.core_properties.title = "Оқу - предзащита курсового проекта"
    prs.core_properties.author = "Мұхан Надирхалиф, Жоробекова Хадизат"
    slides = [s_cover(prs), s_problem(prs), s_task(prs), s_backend(prs),
              s_arch(prs), s_db(prs), s_security(prs), s_log(prs),
              s_roles(prs), s_ui(prs), s_quality(prs),
              s_finish(prs, THANKS[version])]
    lang = {"рус-каз": "kk", "рус-кыр": "ky", "рус": "ru"}[version]
    for sid, slide in zip(ORDER, slides):
        if sid in MUHAN:
            note = "[Мұхан - фиолетовый]\n" + MUHAN[sid]
        else:
            note = "[Хадизат - жёлтый]\n" + HADIZAT[lang][sid]
        slide.notes_slide.notes_text_frame.text = note
    out = os.path.join(PRES_DIR, filename)
    prs.save(out)
    print("Собран", out)


if __name__ == "__main__":
    for ver, name in VERSIONS.items():
        build(ver, name)
