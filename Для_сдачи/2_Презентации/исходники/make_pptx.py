"""Презентация предзащиты «Оқу» в PowerPoint: 12 слайдов, три версии.

Стиль «тетрадь в клетку и книжная полка»: фон в клетку, скриншоты-полароиды
со скотчем, пометки ручкой на полях, стикеры, внизу - полка с корешками
(маскот сайта). Кто говорит - ленточка-закладка сверху справа:
фиолетовая - Мұхан, жёлтая - Хадизат.

    python make_pptx.py

Нужны python-pptx и qrcode (pip install python-pptx qrcode).
"""

import io
import os
import random

import qrcode
from lxml import etree
from PIL import Image, ImageDraw
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

from notes import HADIZAT, MUHAN, THANKS
from slides_ky import KY

# Язык текста на слайдах: в кыргызской версии весь текст по-кыргызски,
# в остальных - по-русски (речь в заметках - на языке версии).
LANG = "ru"


def tr(s):
    """Перевести строку слайда на язык текущей версии."""
    return KY.get(s, s) if LANG == "ky" else s

HERE = os.path.dirname(os.path.abspath(__file__))
PRES_DIR = os.path.dirname(HERE)
PROJECT = os.path.dirname(os.path.dirname(PRES_DIR))
IMG = os.path.join(PROJECT, "docs", "img")
GRID = os.path.join(HERE, "img", "grid.png")
SITE = "https://130-17-21-59.sslip.io"

VERSIONS = {"рус-каз": "Оқу_предзащита_рус-каз.pptx",
            "рус-кыр": "Оқу_предзащита_рус-кыр.pptx",
            "рус": "Оқу_предзащита_рус.pptx"}

HEAD, BODY, MONO, HAND = "Cambria", "Calibri", "Consolas", "Segoe Print"
PAPER = "F8F7F1"
INK, SOFT, MUTED, LINE = "1F211D", "44483F", "7A7F73", "C9CCC2"
PEN = "1F4E9C"                      # «шариковая ручка» для пометок
GREEN = "0F6E5A"
YES, NO = "2E7D4F", "B23A3A"
MINT, PINK, CREAM = "D9F0E3", "F9DCE2", "FFF6D8"
SPK = {"m": {"main": "6A3FC8", "on": "FFFFFF", "hl": "B9A2F0"},
       "h": {"main": "F2B705", "on": "1F211D", "hl": "FFD54A"}}
SPINES = ["0F6E5A", "8C3B3B", "2E4A6B", "C8902E", "7A9A7E", "5B3F6B",
          "3B3D38", "A65E2E", "4F7C8A", "9C8A5A"]

L, W = 130, 1660


def px(v):
    return Emu(int(v * 6350))


def rgb(h):
    return RGBColor.from_string(h)


# --- Фон «тетрадь в клетку» --------------------------------------------------
def make_grid():
    if os.path.exists(GRID):
        return
    os.makedirs(os.path.dirname(GRID), exist_ok=True)
    img = Image.new("RGB", (1920, 1080), "#" + PAPER)
    d = ImageDraw.Draw(img)
    for x in range(0, 1920, 40):
        d.line([(x, 0), (x, 1080)], fill="#DCE6EE", width=1)
    for y in range(0, 1080, 40):
        d.line([(0, y), (1920, y)], fill="#DCE6EE", width=1)
    img.save(GRID)


# --- Примитивы ---------------------------------------------------------------
def _effects(shape):
    spPr = shape._element.spPr
    eff = spPr.find(qn("a:effectLst"))
    if eff is None:
        eff = etree.SubElement(spPr, qn("a:effectLst"))
    return eff


def shadow(shape, blur=16, dist=5, alpha=28):
    eff = _effects(shape)
    sh = etree.SubElement(eff, qn("a:outerShdw"), blurRad=str(blur * 12700),
                          dist=str(dist * 12700), dir="5400000", algn="t",
                          rotWithShape="0")
    clr = etree.SubElement(sh, qn("a:srgbClr"), val="000000")
    etree.SubElement(clr, qn("a:alpha"), val=str(alpha * 1000))


def alpha(shape, pct):
    clr = shape.fill._xPr.find(qn("a:solidFill"))[0]
    etree.SubElement(clr, qn("a:alpha"), val=str(int(pct * 1000)))


def box(slide, x, y, w, h, color, shape="rect", radius=14, line=None,
        rot=0, lw=1.5):
    kind = {"rect": MSO_SHAPE.RECTANGLE,
            "round": MSO_SHAPE.ROUNDED_RECTANGLE,
            "oval": MSO_SHAPE.OVAL,
            "tri": MSO_SHAPE.ISOSCELES_TRIANGLE}[shape]
    shp = slide.shapes.add_shape(kind, px(x), px(y), px(w), px(h))
    if color:
        shp.fill.solid()
        shp.fill.fore_color.rgb = rgb(color)
    else:
        shp.fill.background()
    if line:
        shp.line.color.rgb = rgb(line)
        shp.line.width = Pt(lw)
    else:
        shp.line.fill.background()
    _effects(shp)
    if shape == "round":
        shp.adjustments[0] = min(0.5, radius / min(w, h))
    shp.rotation = rot
    return shp


def fill_text(tf, paras, size, color, font, bold, align, spacing, gap):
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, para in enumerate([paras] if isinstance(paras, str) else paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = spacing
        if i:
            p.space_before = Pt(size * gap)
        for chunk, opt in (para if isinstance(para, list) else [(para, {})]):
            r = p.add_run()
            r.text = tr(chunk)
            f = r.font
            f.name = opt.get("font", font)
            f.size = Pt(opt.get("size", size) / 2)
            f.bold = opt.get("bold", bold)
            f.color.rgb = rgb(opt.get("color", color))


def text(slide, x, y, w, h, paras, size=28, color=SOFT, font=BODY,
         bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
         spacing=1.1, gap=0.3, rot=0):
    tb = slide.shapes.add_textbox(px(x), px(y), px(w), px(h))
    tb.text_frame.vertical_anchor = anchor
    fill_text(tb.text_frame, paras, size, color, font, bold, align, spacing,
              gap)
    tb.rotation = rot
    return tb


def hand(slide, x, y, w, h, paras, size=28, color=PEN, rot=0,
         align=PP_ALIGN.LEFT):
    """Пометка «ручкой» на полях."""
    return text(slide, x, y, w, h, paras, size=size, color=color, font=HAND,
                spacing=1.0, gap=0.1, rot=rot, align=align)


def sticky(slide, x, y, w, h, paras, color=MINT, rot=-2, size=26,
           font=HAND, tcolor=INK):
    shp = box(slide, x, y, w, h, color, rot=rot)
    shadow(shp, blur=12, dist=6, alpha=22)
    tf = shp.text_frame
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    fill_text(tf, paras, size, tcolor, font, False, PP_ALIGN.LEFT, 1.0, 0.15)
    for side in ("margin_left", "margin_right"):
        setattr(tf, side, px(26))
    return shp


def tape(slide, cx, cy, rot):
    t = box(slide, cx - 55, cy - 16, 110, 32, "EDE3C6", rot=rot)
    alpha(t, 70)


def polaroid(slide, name, x, y, w, h, rot=0, pad=14, tapes=True,
             data=None):
    """Скриншот в белой рамке с тенью; рамка и картинка вращаются вместе."""
    fr = box(slide, x - pad, y - pad, w + 2 * pad, h + 2 * pad, "FFFFFF",
             rot=rot)
    shadow(fr)
    if data is not None:
        pic = slide.shapes.add_picture(data, px(x), px(y), px(w), px(h))
    else:
        path = os.path.join(IMG, name)
        iw, ih = Image.open(path).size
        k = max(w / iw, h / ih)          # заполнить рамку, лишнее обрезать
        pic = slide.shapes.add_picture(path, px(x), px(y), px(w), px(h))
        cw, ch = w / (iw * k), h / (ih * k)
        pic.crop_left = pic.crop_right = (1 - cw) / 2
        pic.crop_top, pic.crop_bottom = 0, 1 - ch
    pic.rotation = rot
    if tapes:
        tape(slide, x + 40, y - pad, -8 + rot)
        tape(slide, x + w - 40, y - pad, 10 + rot)
    return fr


def hairline(slide, x, y, w, color=LINE):
    box(slide, x, y, w, 2, color)


def rows(slide, x, y, w, data, widths, row_h=60, size=25, head=True,
         mono_col=None, bold_col=0, colors=None):
    """Таблица «от руки»: только текст и тонкие линии."""
    for i, row in enumerate(data):
        yy = y + i * row_h
        cx = x
        for j, val in enumerate(row):
            cw = w * widths[j]
            col = INK
            if colors and i and colors(i, j, val):
                col = colors(i, j, val)
            font = MONO if (mono_col == j and i) else BODY
            bold = (head and i == 0) or (bold_col == j and i > 0)
            tsize = size - 1 if (head and i == 0) else size
            text(slide, cx + 8, yy, cw - 16, row_h, val, size=tsize,
                 color=MUTED if (head and i == 0) else col, font=font,
                 bold=bold, anchor=MSO_ANCHOR.MIDDLE, spacing=1.0)
            cx += cw
        hairline(slide, x, yy + row_h - 1, w,
                 color="9DA195" if (head and i == 0) else LINE)


def shelf(slide, seed):
    """Книжная полка внизу слайда: корешки разной высоты на доске."""
    rnd = random.Random(seed)
    box(slide, 0, 1062, 1920, 18, "8A6A4A")
    x = 40 + rnd.randint(0, 60)
    while x < 1880:
        if rnd.random() < 0.12:
            x += rnd.randint(30, 90)
            continue
        w = rnd.randint(16, 30)
        h = rnd.randint(38, 66)
        tilt = 0
        if rnd.random() < 0.06 and x < 1820:
            tilt = rnd.choice([-12, 12])
        b = box(slide, x, 1062 - h, w, h, rnd.choice(SPINES), rot=tilt)
        if rnd.random() < 0.5:
            band = box(slide, x, 1062 - h + 8, w, 4, "E8D9B5", rot=tilt)
            alpha(band, 70)
        x += w + rnd.randint(1, 4)
        del b


def ribbon(slide, spk, page):
    """Закладка-ленточка сверху справа: цвет докладчика и номер слайда."""
    c = SPK[spk]
    x = 1740
    r = box(slide, x, 0, 72, 150, c["main"])
    shadow(r, blur=8, dist=3, alpha=25)
    notch = box(slide, x, 124, 72, 27, PAPER, "tri")
    notch.line.fill.background()
    text(slide, x, 54, 72, 50, str(page), size=34, color=c["on"],
         font=HEAD, bold=True, align=PP_ALIGN.CENTER,
         anchor=MSO_ANCHOR.MIDDLE)


def page(prs, spk, num, kicker, title):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.shapes.add_picture(GRID, 0, 0, px(1920), px(1080))
    shelf(s, num * 7 + 3)
    ribbon(s, spk, num)
    hand(s, L, 58, 1400, 50, kicker, size=30)
    text(s, L, 108, 1560, 84, title, size=58, color=INK, font=HEAD,
         bold=True)
    return s


def highlight(slide, x, y, w, h, spk, rot=-1):
    hl = box(slide, x, y, w, h, SPK[spk]["hl"], rot=rot)
    alpha(hl, 55)


def circle_mark(slide, x, y, w, h, rot=-6, color=PEN):
    o = box(slide, x, y, w, h, None, "oval", line=color, rot=rot, lw=2.5)
    return o


# --- Слайды ------------------------------------------------------------------
def s_cover(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.shapes.add_picture(GRID, 0, 0, px(1920), px(1080))
    shelf(s, 11)
    ribbon(s, "h", 1)
    hand(s, L, 150, 900, 50, "курсовой проект · вариант 11", size=34)
    text(s, L - 8, 190, 900, 260, "Оқу", size=250, color=INK, font=HEAD,
         bold=True)
    if LANG == "ru":         # маркер под первой строкой русского текста
        highlight(s, L, 486, 820, 62, "h")
    text(s, L, 470, 840, 140, "Электронная библиотека с REST API "
         "и документацией OpenAPI", size=46, color=INK, spacing=1.05)
    text(s, L, 650, 900, 160, [
        [("Мұхан Надирхалиф", {"bold": True}), ("  ·  ", {}),
         ("Жоробекова Хадизат", {"bold": True})],
        "группа Сиб-24-1",
        "руководитель: Айтимов Мурат Жолдасбекович"], size=30, color=SOFT,
        gap=0.25)
    text(s, L, 860, 1000, 40, "Кызылординский университет имени Коркыт Ата "
         "· 2026", size=24, color=MUTED)
    polaroid(s, "01_home.png", 1010, 200, 640, 400, rot=3)
    polaroid(s, "17_mobile_home.jpg", 1560, 470, 190, 400, rot=-5,
             tapes=False)
    tape(s, 1650, 462, 4)
    sticky(s, 1060, 690, 400, 150, ["сайт уже работает!", "QR-код - "
           "в конце ;)"], color=MINT, rot=-4, size=28)
    return s


def s_problem(prs):
    s = page(prs, "h", 2, "с чего всё началось", "Студенту неудобно читать "
             "книги вуза онлайн")
    probs = [("Сложный доступ", "в МегаПро в основном сканы, до книги "
              "несколько шагов, с телефона читать тяжело"),
             ("Нет «продолжить»", "негде отметить, что читаешь, и вернуться "
              "на ту же страницу"),
             ("Платно и без казахского", "популярные сервисы платные и почти "
              "не знают казахского языка")]
    for i, (t, b) in enumerate(probs):
        y = 236 + i * 118
        hand(s, L, y - 6, 60, 70, f"{i + 1}.", size=48)
        text(s, L + 70, y, 860, 40, t, size=32, color=INK, font=HEAD,
             bold=True)
        text(s, L + 70, y + 44, 860, 64, b, size=26, spacing=1.0)
    sticky(s, 1110, 222, 620, 340, [
        [("Наше решение - «Оқу»:", {"font": HEAD, "bold": True,
                                    "size": 32})],
        "· книга открывается одной кнопкой",
        "· чтение с места остановки",
        "· 4 языка + телефон",
        "· новинки бесплатно студентам",
        "· открытый REST API"], color=PINK, rot=2.5, size=26)

    def yn(i, j, v):
        return {"да": YES, "нет": NO, "закрыт": NO}.get(v) if j else None
    rows(s, L, 606, 1480, [
        ["", "МегаПро", "MangaLib", "Goodreads", "ЛитРес", "Оқу"],
        ["Продолжить с места остановки", "нет", "да", "-", "да", "да"],
        ["Казахский интерфейс", "частично", "нет", "нет", "нет", "да"],
        ["Бесплатно для студентов", "да", "частично", "да", "нет", "да"],
        ["Открытый API", "нет", "нет", "закрыт", "нет", "да"]],
        [0.33, 0.134, 0.134, 0.134, 0.134, 0.134], row_h=60, size=25,
        colors=yn)
    circle_mark(s, L + 1480 * 0.866 - 24, 596, 130, 320, rot=-3,
                color=SPK["h"]["main"])
    hand(s, 1080, 920, 780, 40, "сравнивали по открытым страницам "
         "сервисов", size=22, color=MUTED, rot=-1, align=PP_ALIGN.RIGHT)
    return s


def s_task(prs):
    s = page(prs, "m", 3, "что нам задали", "Вариант 11: что требовалось "
             "и как сделано")
    rows(s, L, 222, W - 120, [
        ["Требование", "Как выполнено", "Где в коде"],
        ["REST API на FastAPI", "59 маршрутов в 10 группах: книги, полка, "
         "комментарии, модерация, журнал…", "app/web.py"],
        ["Документация OpenAPI", "Swagger на /docs и ReDoc на /redoc "
         "строятся сами по коду", "/openapi.json"],
        ["Аутентификация JWT", "HS256: access 30 мин + refresh 7 дней; "
         "пароли - хэш PBKDF2-SHA256", "app/security.py"],
        ["Постраничный вывод", "page, page_size (1-100, по умолчанию 20) "
         "→ items, total, pages", "service._paginate"],
        ["Журнал действий", "action_log: кто, что, когда (UTC), IP; "
         "фильтры, CSV, хранение 365 дней", "service.log_action"],
        ["Логика отдельно + тесты", "service.py не знает про HTTP; 155 "
         "тестов, покрытие 89,4%", "app/service.py"]],
        [0.25, 0.55, 0.2], row_h=78, size=25, mono_col=2,
        colors=lambda i, j, v: SPK["m"]["main"] if j == 2 else None)
    hand(s, 1440, 168, 420, 50, "всё по ТЗ ✓", size=34, rot=-4)
    sticky(s, L + 20, 796, 1260, 140, [
        [("+ сверх задания: ", {"bold": True, "font": BODY}),
         ("поверх этого же API - целый сайт для читателей (7 ролей, "
          "читалка, 4 языка, телефон), и он уже в интернете с HTTPS",
          {"font": BODY})]], color="E6DEFA", rot=-1, size=29)
    return s


CODE = """GET /api/books?page=2&page_size=10&sort=rating

200 OK
{
  "items": [
    {"id": 26, "title": "A Study in Scarlet",
     "author": "Arthur Conan Doyle", …},
    …
  ],
  "total": 88,
  "page": 2,
  "page_size": 10,
  "pages": 9
}"""


def s_backend(prs):
    s = page(prs, "m", 4, "так выглядит выполненное задание",
             "Бэкенд: REST API и его Swagger")
    polaroid(s, "22_swagger_top.png", L + 14, 250, 820, 519, rot=-2)
    hand(s, 520, 812, 440, 90, "↑ кнопка Authorize: войти и вызвать "
         "любой запрос прямо отсюда", size=24, rot=-2)
    term = box(s, 1010, 236, 770, 560, "1E1F24", "round", 16)
    shadow(term)
    for i, c in enumerate(["FF5F57", "FEBC2E", "28C840"]):
        box(s, 1034 + i * 28, 254, 16, 16, c, "oval")
    text(s, 1036, 290, 720, 500, CODE.split("\n"), size=22, color="E6E3F5",
         font=MONO, gap=0, spacing=1.04)
    highlight(s, 1052, 612, 200, 32, "m", rot=0)
    hand(s, 1300, 620, 480, 120, "← 88 книг = 9 страниц по 10. "
         "Это и есть постраничный вывод", size=24, color="F3EEDD")
    text(s, 1010, 832, 780, 120, [
        [("422", {"bold": True, "color": SPK["m"]["main"]}),
         (" - неверные данные: Pydantic сам скажет, какое поле не так", {})],
        [("401", {"bold": True, "color": SPK["m"]["main"]}),
         (" - нет токена или он истёк", {})]], size=25, gap=0.2)
    return s


def s_arch(prs):
    s = page(prs, "m", 5, "как это устроено внутри", "Архитектура: три "
             "слоя, как книги в стопке")
    books = [("Интерфейс: HTML + JS без сборки", "~2 700 строк · браузер "
              "и телефон", "DCEBE4", INK, 0, "7A9A7E"),
             ("web.py - REST API", "1 109 строк · маршруты, права, "
              "проверки", "6A3FC8", "FFFFFF", 30, "4B2A93"),
             ("service.py - бизнес-логика", "1 580 строк · не знает про "
              "HTTP", "7E58D4", "FFFFFF", 10, "4B2A93"),
             ("db.py - SQLite", "16 таблиц · WAL · миграции", "2A2C28",
              "F3F4EF", 40, "000000")]
    y = 240
    for i, (t, sub, fill, col, dx, spine) in enumerate(books):
        x = L + dx
        b = box(s, x, y, 860, 118, fill, "round", 10)
        shadow(b, blur=6, dist=3, alpha=20)
        box(s, x, y, 34, 118, spine, "rect")
        text(s, x + 60, y + 16, 780, 44, t, size=32, color=col, font=HEAD,
             bold=True)
        text(s, x + 60, y + 66, 780, 40, sub, size=24, color=col)
        y += 132
    hand(s, 1060, 336, 300, 40, "↕ HTTP + JSON + JWT", size=23)
    hand(s, 1060, 468, 300, 40, "↕ вызов функций", size=23)
    hand(s, 1060, 600, 300, 40, "↕ SQL с «?»", size=23)
    x = 1370
    hand(s, x, 236, 420, 50, "почему именно так?", size=28,
         color=SPK["m"]["main"])
    why = [("FastAPI", "OpenAPI и проверка данных из коробки"),
           ("SQLite", "один файл, ноль настройки"),
           ("JS без сборки", "открылся - и работает"),
           ("Вторая платформа", "приложение подключится к тому же API, "
            "сервер не меняется")]
    yy = 300
    for t, b in why:
        text(s, x, yy, 420, 130, [[(t + ": ", {"bold": True,
                                               "color": INK}), (b, {})]],
             size=25, spacing=1.0)
        yy += 116
    sticky(s, L + 40, 790, 860, 130, ["service.py можно проверить тестами "
           "без сервера и браузера - так и требует методичка"],
           color=CREAM, rot=-1.5, size=25)
    return s


def s_db(prs):
    s = page(prs, "m", 6, "где всё хранится", "База данных: 16 таблиц "
             "в пяти группах")
    groups = [("Люди", ["users", "bans", "unban_requests",
                        "student_requests"]),
              ("Книги", ["books", "tags", "book_tags", "book_images"]),
              ("Чтение", ["shelf", "reading_progress", "bookmarks"]),
              ("Отзывы", ["comments", "ratings", "purchases"]),
              ("Служебные", ["action_log", "game_saves"])]
    rots = [-2, 1.5, -1, 2, -1.5]
    gw = 300
    for i, (g, tabs) in enumerate(groups):
        x = L + i * (gw + 34)
        c = box(s, x, 236, gw, 300, "FFFFFF", rot=rots[i])
        shadow(c, blur=10, dist=4, alpha=22)
        tf = c.text_frame
        tf.vertical_anchor = MSO_ANCHOR.TOP
        fill_text(tf, [[(g, {"font": HEAD, "bold": True, "size": 32,
                             "color": SPK["m"]["main"]})]] + tabs, 24, INK,
                  MONO, False, PP_ALIGN.LEFT, 1.0, 0.35)
        tf.margin_left = tf.margin_top = px(24)
    rows(s, L, 586, W - 120, [
        ["Правило", "Что даёт"],
        ["CHECK", "роль из списка, год 0-2100, цена ≥ 0, оценка 1-5"],
        ["Внешние ключи", "удалили книгу - ушли её отзывы и закладки "
         "(CASCADE); в журнале SET NULL - история цела"],
        ["Уникальность", "логин и почта UNIQUE; одна оценка на книгу - "
         "ключ (user_id, book_id)"],
        ["Поиск", "индексы + свой LOWER() для казахских букв"]],
        [0.22, 0.78], row_h=64, size=25)
    hand(s, 1380, 540, 460, 40, "ER-диаграмма - в документе 3", size=22,
         color=MUTED, rot=-1)
    return s


def s_security(prs):
    s = page(prs, "m", 7, "как защищены данные", "Вход по JWT и защита "
             "от атак")
    steps = [("логин + пароль", "POST /api/auth/login"),
             ("сверка хэша", "PBKDF2-SHA256, соль, 600 000 итераций"),
             ("два токена", "access 30 мин, refresh 7 дней"),
             ("каждый запрос", "Bearer-токен; 401 → сайт сам обновит")]
    sw = 360
    for i, (t, b) in enumerate(steps):
        x = L + i * (sw + 54)
        circle = box(s, x, 232, 64, 64, SPK["m"]["main"], "oval")
        circle.rotation = 0
        text(s, x, 232, 64, 64, str(i + 1), size=32, color="FFFFFF",
             font=HEAD, bold=True, align=PP_ALIGN.CENTER,
             anchor=MSO_ANCHOR.MIDDLE)
        text(s, x + 80, 236, sw - 80, 56, t, size=30, color=INK, font=HEAD,
             bold=True, anchor=MSO_ANCHOR.MIDDLE)
        text(s, x, 310, sw, 90, b, size=25, spacing=1.0)
        if i < 3:
            hand(s, x + sw + 4, 238, 50, 60, "→", size=40)
    hand(s, 560, 400, 640, 44, "↑ пароль в базе не хранится вообще!",
         size=25, rot=-1.5)
    rows(s, L, 462, W - 120, [
        ["Атака", "Как защищено"],
        ["Подбор пароля", "5 ошибок подряд - блокировка; не больше 10 "
         "попыток в минуту с одного IP"],
        ["SQL-инъекция", "только запросы с параметрами «?»; сортировка - "
         "из белого списка"],
        ["Украли базу", "там только хэши с солью; ключ JWT - в переменной "
         "окружения, не в коде"],
        ["Подмена файла", "проверка первых байтов (%PDF-, PNG, JPEG), "
         "случайные имена, лимиты 40 и 5 МБ"],
        ["XSS", "экранирование вывода, заголовок CSP, HTTPS"],
        ["Перебор логинов", "фиктивный хэш: ответ одинаково долгий"]],
        [0.22, 0.78], row_h=64, size=25)
    return s


def s_log(prs):
    s = page(prs, "h", 8, "усложнение нашего варианта", "Журнал действий: "
             "кто, что и когда")
    polaroid(s, "15_admin_log.png", L + 14, 254, 860, 538, rot=1.5)
    x = 1100
    text(s, x, 222, 260, 200, "26", size=150, color=INK, font=HEAD,
         bold=True)
    circle_mark(s, x - 20, 236, 260, 170, rot=-8, color=SPK["h"]["main"])
    hand(s, x + 270, 270, 380, 120, "видов действий: вход, бан, "
         "покупка, смена роли…", size=26)
    items = [("В каждой записи:", "время, кто, что, подробности, IP"),
             ("Модератор может:", "выбрать действие и даты, листать, "
              "скачать CSV"),
             ("Время:", "показывается в часовом поясе читателя")]
    yy = 450
    for t, b in items:
        text(s, x, yy, 680, 100, [[(t + " ", {"bold": True, "color": INK}),
                                   (b, {})]], size=27, spacing=1.0)
        yy += 104
    sticky(s, x + 60, 770, 520, 120, ["старше года - удаляется само, "
           "база не пухнет"], color=MINT, rot=3, size=26)
    return s


def s_roles(prs):
    s = page(prs, "h", 9, "кто что может", "Семь ролей: каждому только "
             "нужные права")
    data = [("Гость", "ищет и читает бесплатные книги", 0.14),
            ("Читатель", "+ полки, закладки, оценки, комментарии", 0.3),
            ("Студент", "+ платные новинки бесплатно (после студбилета)",
             0.42),
            ("Автор", "+ добавляет книги, меняет только свои", 0.55),
            ("Редактор", "+ управляет всеми книгами", 0.68),
            ("Модератор", "баны, разбан, студбилеты, журнал", 0.82),
            ("Главный разработчик", "всё, и его нельзя забанить", 1.0)]
    for i, (r, d, k) in enumerate(data):
        y = 232 + i * 86
        text(s, L, y, 380, 70, r, size=30, color=INK, font=HEAD, bold=True,
             anchor=MSO_ANCHOR.MIDDLE)
        # «Шкала прав» из корешков: чем больше прав, тем больше книг.
        for j in range(7):
            filled = j <= i
            box(s, L + 390 + j * 26, y + 14 - (j % 2) * 4, 20,
                44 + (j % 2) * 4, SPK["h"]["main"] if filled else None,
                line=None if filled else "B9BCB2", lw=1)
        text(s, L + 600, y, 900, 70, d, size=27, color=INK,
             anchor=MSO_ANCHOR.MIDDLE)
    hand(s, L + 380, 838, 1100, 50, "↑ больше книжек на полке - больше "
         "прав у роли", size=24, color=MUTED)
    sticky(s, 1380, 196, 400, 150, ["права проверяет СЕРВЕР: скрытая "
           "кнопка не поможет (403)"], color=PINK, rot=3, size=24)
    return s


def s_ui(prs):
    s = page(prs, "h", 10, "что видит читатель", "Каталог, шкаф, читалка "
             "и телефон")
    shots = [("02_catalog.png", "каталог: поиск и фильтры", -3),
             ("04_bookcase.png", "шкаф - книги по жанрам", 2),
             ("06_reader.png", "читалка: текст, PDF, закладки", -1.5)]
    for i, (f, cap, r) in enumerate(shots):
        x = L + 14 + i * 470
        polaroid(s, f, x, 250 + (i % 2) * 30, 420, 262, rot=r,
                 tapes=(i != 1))
        hand(s, x, 560 + (i % 2) * 30, 440, 50, cap, size=25)
    polaroid(s, "17_mobile_home.jpg", 1580, 236, 190, 410, rot=3,
             tapes=False)
    tape(s, 1675, 230, -6)
    hand(s, 1540, 670, 300, 60, "← и на телефоне!", size=26, rot=-3)
    hand(s, L, 680, 400, 50, "а ещё:", size=30)
    feats = [("4 языка", MINT, -2), ("тёмная тема", PINK, 1.5),
             ("«продолжить чтение»", CREAM, -1),
             ("оценки и комментарии", MINT, 2),
             ("мини-игра «Парақ»", PINK, -2.5),
             ("цензура грубых слов", CREAM, 1)]
    x, y = L, 740
    for f, c, r in feats:
        w = len(tr(f)) * 15 + 60
        if x + w > 1500:
            x, y = L, y + 100
        sticky(s, x, y, w, 76, [f], color=c, rot=r, size=24, font=BODY)
        x += w + 26
    return s


def s_quality(prs):
    s = page(prs, "m", 11, "насколько это надёжно", "Тесты: что именно "
             "проверено")
    nums = [("155", "автотестов, все зелёные"),
            ("89,4%", "покрытие логики (надо ≥ 80%)"),
            ("0", "замечаний PEP 8"),
            ("66", "коммитов в Git (надо ≥ 10)")]
    for i, (n, lab) in enumerate(nums):
        x = L + i * 400
        text(s, x, 214, 380, 110, n, size=90, color=SPK["m"]["main"],
             font=HEAD, bold=True)
        hand(s, x, 324, 380, 50, lab, size=23, color=INK)
    circle_mark(s, L + 380, 204, 320, 114, rot=-4)
    rows(s, L, 400, W - 120, [
        ["Граничный случай", "Что будет", "Тест"],
        ["Год издания 2101", "ошибка проверки", "test_add_book_bad_year"],
        ["Страница за концом списка", "пустой список",
         "test_page_beyond_end_is_empty"],
        ["page_size = 10 000", "урежется до 100",
         "test_pagination_page_size_clamped"],
        ["5 неверных паролей подряд", "блокировка входа",
         "test_bruteforce_lockout"],
        ["Модератор банит главразраба", "запрещено",
         "test_cannot_ban_owner"],
        ["SQL в параметре сортировки", "игнорируется",
         "test_search_injection_in_sort_is_ignored"],
        ["Накрутка очков в игре", "отклонено",
         "test_game_too_fast_growth_rejected"]],
        [0.33, 0.2, 0.47], row_h=62, size=24, mono_col=2,
        colors=lambda i, j, v: SPK["m"]["main"] if j == 2 else None)
    return s


def qr_png():
    img = qrcode.make(SITE, border=2, box_size=12)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def s_finish(prs, thanks):
    s = page(prs, "h", 12, "итог", "Всё сделано - и даже больше")
    checks = [("Задание варианта 11", "FastAPI и OpenAPI, JWT, "
               "постраничный вывод, журнал действий, тесты"),
              ("Сверх задания", "сайт: 7 ролей, читалка, шкаф, 4 языка, "
               "телефон, сервер с HTTPS"),
              ("Документы", "все 14: ТЗ, архитектура, тесты, руководства, "
               "соглашение")]
    for i, (t, b) in enumerate(checks):
        y = 236 + i * 132
        box(s, L, y + 6, 56, 56, None, line=INK, lw=2.5)
        hand(s, L + 4, y - 14, 70, 80, "✓", size=60, color=PEN)
        text(s, L + 90, y, 900, 44, t, size=34, color=INK, font=HEAD,
             bold=True)
        text(s, L + 90, y + 50, 920, 60, b, size=26, spacing=1.0)
    highlight(s, L - 6, 680, 1000, 74, "h", rot=-0.8)
    text(s, L, 664, 1080, 100, thanks, size=54, color=INK, font=HEAD,
         bold=True)
    polaroid(s, None, 1290, 250, 380, 380, rot=3, data=qr_png())
    hand(s, 1250, 670, 480, 60, "наведите камеру ↑", size=30, rot=-2)
    text(s, 1250, 750, 480, 90, ["130-17-21-59.sslip.io",
         "github.com/Kioku-0/oqu"], size=24, color=SOFT, gap=0.1,
         align=PP_ALIGN.CENTER)
    return s


ORDER = ["cover", "problem", "task", "backend", "arch", "db", "security",
         "log", "roles", "ui", "quality", "finish"]


def build(version, filename):
    global LANG
    LANG = "ky" if version == "рус-кыр" else "ru"
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
            note = "[Мұхан - фиолетовая закладка]\n" + MUHAN[sid]
        else:
            note = "[Хадизат - жёлтая закладка]\n" + HADIZAT[lang][sid]
        slide.notes_slide.notes_text_frame.text = note
    out = os.path.join(PRES_DIR, filename)
    prs.save(out)
    print("Собран", out)


if __name__ == "__main__":
    make_grid()
    for ver, name in VERSIONS.items():
        build(ver, name)
