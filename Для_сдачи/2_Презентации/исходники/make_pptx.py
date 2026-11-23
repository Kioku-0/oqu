"""Сборка презентации предзащиты «Оқу» в PowerPoint (три версии).

Слайды одинаковые во всех версиях; речь (заметки докладчика) берётся из
исходников слайдов: исходники/предзащита_12_<версия>/slides/<id>.html,
тег <aside>. Запуск из любой папки:

    python make_pptx.py

Нужна библиотека python-pptx (pip install python-pptx).
"""

import html
import os
import re

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Pt

HERE = os.path.dirname(os.path.abspath(__file__))
PRES_DIR = os.path.dirname(HERE)
PROJECT = os.path.dirname(os.path.dirname(PRES_DIR))
IMG = os.path.join(PROJECT, "docs", "img")

VERSIONS = {
    "рус-каз": "Оқу_предзащита_рус-каз.pptx",
    "рус-кыр": "Оқу_предзащита_рус-кыр.pptx",
    "рус": "Оқу_предзащита_рус.pptx",
}
ORDER = ["cover", "task", "backend", "more", "problem", "arch", "api", "log",
         "roles", "ui", "quality", "finish"]

HEAD = "Cambria"
BODY = "Calibri"
PAPER, PAPER2, CARD = "F3F4EF", "E7EAE2", "FBFBF8"
INK, SOFT, MUTED = "1B1D1A", "4A4F47", "7C8278"
GREEN, GREEN_SOFT = "0F6E5A", "DCEBE4"
ORANGE, ORANGE_SOFT = "B8561A", "F6E2D2"
LIGHT, DARK_SOFT = "F3F4EF", "C9CEC5"

L, TOP, W = 176, 112, 1616          # левое поле, верх, ширина в px (1920)


def px(v):
    """1 px холста 1920×1080 = 6350 EMU (слайд 13,33 × 7,5 дюйма)."""
    return Emu(int(v * 6350))


def rgb(h):
    return RGBColor.from_string(h)


# --- Примитивы ---------------------------------------------------------------
def background(slide, color):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = rgb(color)


def box(slide, x, y, w, h, color, rounded=False, radius=20):
    kind = MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE
    shp = slide.shapes.add_shape(kind, px(x), px(y), px(w), px(h))
    shp.fill.solid()
    shp.fill.fore_color.rgb = rgb(color)
    shp.line.fill.background()
    shp.shadow.inherit = False
    if rounded:
        shp.adjustments[0] = min(0.5, radius / min(w, h))
    return shp


def text(slide, x, y, w, h, paras, size=32, color=SOFT, font=BODY,
         bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
         spacing=1.15, caps=False):
    """paras: строка или список абзацев; абзац - строка или список
    кусков (текст, {опции})."""
    tb = slide.shapes.add_textbox(px(x), px(y), px(w), px(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for side in ("margin_left", "margin_right", "margin_top",
                 "margin_bottom"):
        setattr(tf, side, 0)
    if isinstance(paras, str):
        paras = [paras]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = spacing
        if i:
            p.space_before = Pt(size * 0.25)
        runs = para if isinstance(para, list) else [(para, {})]
        for chunk, opt in runs:
            r = p.add_run()
            r.text = chunk.upper() if caps else chunk
            f = r.font
            f.name = opt.get("font", font)
            f.size = Pt(opt.get("size", size) / 2)
            f.bold = opt.get("bold", bold)
            f.color.rgb = rgb(opt.get("color", color))
    return tb


def picture(slide, name, x, y, w, h, frame=True):
    """Скриншот целиком (contain) по центру рамки."""
    path = os.path.join(IMG, name)
    iw, ih = Image.open(path).size
    if frame:
        box(slide, x, y, w, h, "DDE1D8", rounded=True, radius=16)
    k = min(w / iw, h / ih)
    pw, ph = iw * k, ih * k
    slide.shapes.add_picture(path, px(x + (w - pw) / 2), px(y + (h - ph) / 2),
                             px(pw), px(ph))


def card(slide, x, y, w, h, title, body, fill=CARD, tsize=36, bsize=28):
    box(slide, x, y, w, h, fill, rounded=True)
    text(slide, x + 32, y + 26, w - 64, 50, title, size=tsize, color=INK,
         font=HEAD, bold=True)
    text(slide, x + 32, y + 26 + tsize * 1.45, w - 64, h - 60 - tsize,
         body, size=bsize, color=SOFT)


def frame(prs, speaker, eyebrow, title, page, foot, bg=PAPER, dark=False):
    """Обычный слайд: полоса докладчика, надзаголовок, заголовок, подвал."""
    s = prs.slides.add_slide(prs.slide_layouts[6])
    background(s, INK if dark else bg)
    accent = GREEN if speaker == "m" else ORANGE
    box(s, 0, 0, 32, 1080, accent)
    eb = "E59A62" if dark else accent
    text(s, L, TOP, W, 34, eyebrow, size=24, color=eb, bold=True, caps=True)
    if title:
        text(s, L, TOP + 46, W, 90, title, size=64, color=LIGHT if dark
             else INK, font=HEAD, bold=True)
    fc = "8D948A" if dark else MUTED
    text(s, L, 986, 1300, 30, foot, size=24, color=fc)
    text(s, L + W - 200, 986, 200, 30, str(page), size=24, color=fc,
         align=PP_ALIGN.RIGHT)
    return s


def table(slide, x, y, w, rows, widths, row_h=58, size=26):
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
            cell.fill.fore_color.rgb = rgb(GREEN_SOFT if i == 0 else
                                           (CARD if i % 2 else PAPER2))
            cell.margin_left = cell.margin_right = px(16)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = cell.text_frame
            tf.paragraphs[0].text = ""
            r = tf.paragraphs[0].add_run()
            r.text = val
            r.font.size = Pt(size / 2)
            r.font.name = BODY
            r.font.bold = i == 0
            r.font.color.rgb = rgb(INK)
    return tbl


# --- Слайды ------------------------------------------------------------------
def s_cover(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    background(s, INK)
    box(s, 0, 0, 32, 1080, ORANGE)
    text(s, L, 250, W, 34, "Курсовой проект · вариант 11 · предзащита",
         size=24, color="E59A62", bold=True, caps=True)
    text(s, L, 290, W, 230, "Оқу", size=200, color=LIGHT, font=HEAD,
         bold=True)
    text(s, L, 540, 1400, 60, "Электронная библиотека с REST API и "
         "документацией OpenAPI", size=44, color=LIGHT)
    for i, (lab, val) in enumerate([
            ("Выполнили", "Мұхан Надирхалиф, Жоробекова Хадизат"),
            ("Руководитель", "Айтимов Мурат Жолдасбекович")]):
        x = L + i * 760
        text(s, x, 690, 720, 30, lab, size=24, color="8D948A")
        text(s, x, 726, 720, 44, val, size=32, color=LIGHT)
    text(s, L, 986, 1300, 30, "Кызылординский университет имени Коркыт Ата"
         " · Сиб-24-1 · 2026", size=24, color="8D948A")
    text(s, L + W - 500, 986, 500, 30, "FastAPI · JWT · SQLite", size=24,
         color="8D948A", align=PP_ALIGN.RIGHT)
    return s


def s_task(prs):
    s = frame(prs, "m", "Что нам задали",
              "Вариант 11: серверная часть библиотеки", 2, "Оқу · задание")
    items = [("FastAPI", "REST API с документацией OpenAPI"),
             ("JWT", "вход по токенам, а не по сессиям"),
             ("Страницы", "постраничный вывод длинных списков"),
             ("Журнал", "действия пользователей с временем")]
    cw = (W - 3 * 24) / 4
    for i, (t, b) in enumerate(items):
        card(s, L + i * (cw + 24), 300, cw, 230, t, b)
    text(s, L, 590, 1500, 160, [[
        ("По заданию достаточно ", {}), ("бэкенда", {"bold": True,
                                                    "color": INK}),
        (": сервера, который принимает запросы и отдаёт данные в JSON. "
         "Интерфейса для людей в задании нет.", {})]], size=36)
    return s


def s_shot_cards(prs, speaker, eyebrow, title, page, foot, shot, cards):
    s = frame(prs, speaker, eyebrow, title, page, foot, bg=PAPER2)
    picture(s, shot, L, 290, 960, 600)
    y = 290
    for t, b in cards:
        card(s, L + 1016, y, W - 1016, 186, t, b, fill=PAPER)
        y += 207
    return s


def s_more(prs):
    s = frame(prs, "m", "Сверх задания",
              "Поверх API мы сделали полноценный сайт", 4, "Оқу · сверх "
              "задания")
    picture(s, "20_swagger.png", L, 300, 560, 350)
    text(s, L, 668, 560, 70, "Требовалось: API для программистов", size=24,
         color=MUTED)
    text(s, L + 580, 400, 80, 120, "+", size=96, color=GREEN, bold=True,
         align=PP_ALIGN.CENTER)
    picture(s, "01_home.png", L + 676, 300, 820, 512)
    text(s, L + 676, 830, 820, 40, "Сделали ещё: сайт для читателей на "
         "компьютере и телефоне", size=24, color=MUTED)
    return s


def s_problem(prs):
    s = frame(prs, "h", "Зачем", "Студенту нужна удобная библиотека", 5,
              "Оқу · зачем")
    items = [("Сейчас", "каталог вуза (МегаПро) неудобен с телефона, место "
              "чтения не запоминается"),
             ("Языки", "книги на казахском, русском и английском, интерфейс "
              "тоже нужен на родном языке"),
             ("Аналоги", "ЛитРес, MangaLib, Kitap.kz: у каждого чего-то не "
              "хватает для учёбы")]
    cw = (W - 2 * 28) / 3
    for i, (t, b) in enumerate(items):
        card(s, L + i * (cw + 28), 290, cw, 210, t, b, bsize=26)
    table(s, L, 540, W, [
        ["Что важно", "МегаПро", "ЛитРес", "MangaLib", "Оқу"],
        ["Продолжить с места остановки", "нет", "да", "да", "да"],
        ["Казахский и кыргызский интерфейс", "частично", "нет", "нет", "да"],
        ["Открытый API", "нет", "нет", "нет", "да"],
        ["Бесплатно для студентов", "да", "нет", "да", "да"]],
        [0.4, 0.15, 0.15, 0.15, 0.15], row_h=72)
    return s


def s_arch(prs):
    s = frame(prs, "m", "Архитектура", "Три слоя, каждый отвечает за своё",
              6, "Оқу · архитектура", bg=PAPER2)
    layers = [("Сайт: HTML, CSS, JS", "браузер, телефон", GREEN_SOFT, INK),
              ("web.py: REST API", "маршруты, права, проверки", GREEN, LIGHT),
              ("service.py: бизнес-логика", "правила, не знает про HTTP",
               GREEN, LIGHT),
              ("db.py: SQLite", "16 таблиц", INK, LIGHT)]
    arrows = ["↓ HTTP + JSON, токен JWT", "↓ вызовы функций",
              "↓ SQL с параметрами"]
    y, lw = 286, 1040
    for i, (t, sub, fill, col) in enumerate(layers):
        box(s, L, y, lw, 86, fill, rounded=True)
        text(s, L + 36, y, 620, 86, t, size=34, color=col, font=HEAD,
             bold=True, anchor=MSO_ANCHOR.MIDDLE)
        text(s, L + 640, y, lw - 676, 86, sub, size=26, color=col,
             align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)
        y += 86
        if i < 3:
            text(s, L, y + 4, lw, 40, arrows[i], size=28, color=GREEN,
                 align=PP_ALIGN.CENTER)
            y += 50
    x = L + lw + 56
    card(s, x, 286, W - lw - 56, 230, "Почему так", "логику можно проверить "
         "тестами без сервера и браузера", fill=PAPER)
    card(s, x, 540, W - lw - 56, 230, "Вторая платформа", "мобильное или "
         "настольное приложение подключится к тому же API", fill=PAPER)
    return s


def chip(slide, x, y, label):
    w = len(label) * 13 + 40
    box(slide, x, y, w, 46, GREEN_SOFT, rounded=True, radius=23)
    text(slide, x, y, w, 46, label, size=24, color=GREEN, bold=True,
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)


def s_api(prs):
    s = frame(prs, "m", "Обязательные функции", "JWT и постраничный вывод",
              7, "Оқу · API")
    cw = (W - 32) / 2
    data = [("Вход по JWT", "После входа сервер выдаёт два подписанных "
             "токена: доступ на 30 минут и обновление на 7 дней. Когда доступ "
             "истекает, сайт сам получает новый.",
             "POST /api/auth/login → access_token"),
            ("Списки страницами", "Книги, комментарии, пользователи и журнал "
             "отдаются частями. В ответе: элементы, всего, номер и число "
             "страниц. Больше 100 за раз нельзя.",
             "GET /api/books?page=2&page_size=10")]
    for i, (t, b, c) in enumerate(data):
        x = L + i * (cw + 32)
        box(s, x, 290, cw, 360, CARD, rounded=True)
        text(s, x + 32, 316, cw - 64, 50, t, size=36, color=INK, font=HEAD,
             bold=True)
        text(s, x + 32, 372, cw - 64, 190, b, size=28, color=SOFT)
        chip(s, x + 32, 570, c)
    text(s, L, 700, 1500, 110, "Пароли хранятся только как хэш PBKDF2 "
         "(600 000 итераций). После 5 неверных паролей вход блокируется.",
         size=36)
    return s


def s_roles(prs):
    s = frame(prs, "h", "Роли · принцип наименьших привилегий",
              "Каждому только нужные права", 9, "Оқу · роли")
    table(s, L, 280, W, [
        ["Роль", "Что может"],
        ["Гость", "каталог, поиск, бесплатные книги"],
        ["Читатель", "+ полки, закладки, оценки, комментарии, покупка "
         "новинки"],
        ["Студент", "+ платные новинки бесплатно после проверки студбилета"],
        ["Автор", "+ добавляет книги, меняет только свои"],
        ["Редактор", "+ любые книги"],
        ["Модератор", "баны с причиной и сроком, заявки на разбан, журнал; "
         "книги не трогает"],
        ["Главный разработчик", "всё, включая роли; его нельзя забанить"]],
        [0.26, 0.74], row_h=64)
    text(s, L, 830, W, 40, "Права проверяет сервер при каждом запросе, а не "
         "только интерфейс", size=24)
    return s


def s_ui(prs):
    s = frame(prs, "h", "Что видит читатель", "Каталог, шкаф, читалка, "
              "телефон", 10, "Оқу · интерфейс", bg=PAPER2)
    shots = [("02_catalog.png", "Каталог: поиск, фильтры, 3 вида"),
             ("04_bookcase.png", "Шкаф: книги по жанрам, анимации"),
             ("06_reader.png", "Читалка: текст и PDF, закладки")]
    for i, (f, cap) in enumerate(shots):
        x = L + i * 458
        picture(s, f, x, 290, 430, 269)
        text(s, x, 574, 430, 70, cap, size=24, color=MUTED)
    picture(s, "17_mobile_home.jpg", L + 1396, 290, 220, 476)
    text(s, L, 800, 1600, 60, "4 языка: русский, казахский, кыргызский, "
         "английский · светлая и тёмная тема", size=36)
    return s


def s_quality(prs):
    s = frame(prs, "m", "Качество", "Тесты, стиль, безопасность", 11,
              "Оқу · качество")
    nums = [("155", "тестов pytest, все проходят"),
            ("89%", "покрытие бизнес-логики (нужно 80%)"),
            ("0", "замечаний PEP 8 (ruff)"),
            ("61", "коммит в Git (нужно 10)")]
    cw = (W - 3 * 24) / 4
    for i, (n, lab) in enumerate(nums):
        x = L + i * (cw + 24)
        box(s, x, 290, cw, 230, CARD, rounded=True)
        text(s, x + 32, 312, cw - 64, 100, n, size=88, color=GREEN,
             font=HEAD, bold=True)
        text(s, x + 32, 420, cw - 64, 90, lab, size=26)
    cw = (W - 32) / 2
    card(s, L, 556, cw, 240, "Граничные случаи", "год 2101, цена больше "
         "миллиона, пустое название, бан главного разработчика, накрутка в "
         "игре, старая база")
    card(s, L + cw + 32, 556, cw, 240, "Защита данных", "хэш паролей, "
         "параметризованный SQL, ключ JWT вне кода, проверка файлов по "
         "сигнатуре, CSP, HTTPS")
    return s


def s_finish(prs, thanks):
    s = frame(prs, "h", "Итог", "Задание выполнено, и сверх него сделан сайт",
              12, "Оқу · спасибо за внимание", dark=True)
    cols = [("Бэкенд", "FastAPI, JWT, страницы, журнал, OpenAPI"),
            ("Сайт", "7 ролей, читалка, шкаф, 4 языка, телефон"),
            ("Документы", "ТЗ, архитектура, тесты, руководства, "
             "14 документов")]
    cw = (W - 56) / 3
    for i, (t, b) in enumerate(cols):
        x = L + i * (cw + 28)
        text(s, x, 300, cw, 44, t, size=32, color=LIGHT, bold=True)
        text(s, x, 350, cw, 100, b, size=32, color=DARK_SOFT)
    links = [("Сайт", "130-17-21-59.sslip.io"),
             ("API", "130-17-21-59.sslip.io/docs"),
             ("Код", "github.com/Kioku-0/oqu")]
    for i, (lab, val) in enumerate(links):
        x = L + i * (cw + 28)
        text(s, x, 520, cw, 30, lab, size=24, color="8D948A")
        text(s, x, 556, cw, 44, val, size=32, color=LIGHT)
    text(s, L, 700, W, 80, thanks, size=56, color=LIGHT, font=HEAD)
    return s


THANKS = {"рус-каз": "Рахмет! Сұрақтарыңызға дайынбыз.",
          "рус-кыр": "Рахмат! Суроолоруңузга даярбыз.",
          "рус": "Спасибо! Готовы ответить на вопросы."}


def notes_for(version):
    folder = os.path.join(HERE, f"предзащита_12_{version}", "slides")
    out = {}
    for sid in ORDER:
        with open(os.path.join(folder, sid + ".html"), encoding="utf-8") as f:
            m = re.search(r"<aside>(.*?)</aside>", f.read(), re.S)
        out[sid] = html.unescape(m.group(1).strip()) if m else ""
    return out


def build(version, filename):
    prs = Presentation()
    prs.slide_width, prs.slide_height = px(1920), px(1080)
    prs.core_properties.title = "Оқу - предзащита курсового проекта"
    prs.core_properties.author = "Мұхан Надирхалиф, Жоробекова Хадизат"
    slides = [
        s_cover(prs), s_task(prs),
        s_shot_cards(prs, "m", "Так выглядит выполненное задание",
                     "Бэкенд: REST API и Swagger на /docs", 3,
                     "Оқу · 130-17-21-59.sslip.io/docs", "20_swagger.png", [
                         ("59 маршрутов", "книги, полки, комментарии, "
                          "профиль, модерация, журнал"),
                         ("Документация сама", "FastAPI строит её по коду, "
                          "стандарт OpenAPI"),
                         ("Можно проверить", "вход, кнопка Authorize и "
                          "любой запрос прямо в браузере")]),
        s_more(prs), s_problem(prs), s_arch(prs), s_api(prs),
        s_shot_cards(prs, "h", "Усложнение варианта",
                     "Журнал действий с временными метками", 8,
                     "Оқу · журнал", "15_admin_log.png", [
                         ("Что пишется", "кто, что сделал, когда и с какого "
                          "IP: вход, бан, покупка, правка книги"),
                         ("Как смотреть", "фильтры, страницы, выгрузка "
                          "в CSV"),
                         ("Хранение", "записи старше года удаляются сами")]),
        s_roles(prs), s_ui(prs), s_quality(prs),
        s_finish(prs, THANKS[version]),
    ]
    notes = notes_for(version)
    for sid, slide in zip(ORDER, slides):
        slide.notes_slide.notes_text_frame.text = notes[sid]
    out = os.path.join(PRES_DIR, filename)
    prs.save(out)
    print("Собран", out)


if __name__ == "__main__":
    for ver, name in VERSIONS.items():
        build(ver, name)
