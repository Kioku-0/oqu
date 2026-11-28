"""Демо-манга «Оқу»: «図書館の猫» (Кот из библиотеки) — своя история и
рисунки (Pillow). Японский оригинал, вертикальный текст в облачках.
Пишет PNG-страницы и manga.json с рамками реплик и переводами ru/kk/en.

Запуск (Windows, нужны Pillow и шрифт Yu Gothic):
    python tools/make_manga.py app/demo/manga
"""
import json
import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
W, H = 900, 1350
FONT_JP = "C:/Windows/Fonts/YuGothB.ttc"
FONT_SFX = "C:/Windows/Fonts/YuGothB.ttc"
random.seed(7)

INK = (20, 20, 20)
PAPER = (255, 255, 255)


def font(size):
    return ImageFont.truetype(FONT_JP, size)


# ---------- Фоны и приёмы манги ----------
def tone(img, box, step=7, r=1.3, fill=(150, 150, 150)):
    """Скринтон: сетка точек внутри прямоугольника."""
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    for y in range(int(y0), int(y1), step):
        off = (step // 2) if ((y - y0) // step) % 2 else 0
        for x in range(int(x0) + off, int(x1), step):
            d.ellipse((x - r, y - r, x + r, y + r), fill=fill)


def speed_lines(img, box, center, n=90, color=(60, 60, 60)):
    d = ImageDraw.Draw(img)
    cx, cy = center
    x0, y0, x1, y1 = box
    rad = math.hypot(x1 - x0, y1 - y0)
    for i in range(n):
        a = random.uniform(0, 2 * math.pi)
        r0 = random.uniform(0.35, 0.55) * rad / 2
        p0 = (cx + math.cos(a) * r0, cy + math.sin(a) * r0)
        p1 = (cx + math.cos(a) * rad, cy + math.sin(a) * rad)
        d.line([p0, p1], fill=color, width=random.choice((1, 2, 2, 3)))


def shelves(img, box):
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    y = y0 + 20
    while y < y1 - 30:
        x = x0 + 10
        while x < x1 - 20:
            w = random.randint(14, 30)
            h = random.randint(60, 95)
            shade = random.choice((90, 130, 170, 200, 230))
            d.rectangle((x, y + 100 - h, x + w, y + 100), fill=(shade,) * 3,
                        outline=INK, width=2)
            if random.random() < .5:
                d.line((x + 3, y + 100 - h + 12, x + w - 3, y + 100 - h + 12),
                       fill=INK, width=1)
            x += w + 2
        d.rectangle((x0, y + 100, x1, y + 110), fill=(80, 60, 40), outline=INK)
        y += 125


def steppe(img, box, sun=True):
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    horizon = y0 + (y1 - y0) * .55
    tone(img, (x0, y0, x1, horizon), step=9, r=1, fill=(185, 185, 185))
    if sun:
        d.ellipse((x1 - 170, y0 + 30, x1 - 90, y0 + 110), fill=PAPER,
                  outline=INK, width=3)
    for k in range(3):
        yy = horizon + k * 18
        pts = [(x, yy + 8 * math.sin(x / 60 + k)) for x in range(int(x0), int(x1) + 10, 10)]
        d.line(pts, fill=INK, width=2)
    for _ in range(60):
        gx = random.uniform(x0, x1)
        gy = random.uniform(horizon + 40, y1 - 5)
        d.line((gx, gy, gx + random.uniform(-6, 6), gy - random.uniform(8, 18)),
               fill=INK, width=2)
    return horizon


# ---------- Персонажи ----------
def girl(img, cx, cy, s=1.0, face="calm", arm_up=False):
    """Аяа: школьница с каре и заколкой-закладкой."""
    d = ImageDraw.Draw(img)
    def S(v): return v * s
    # тело (форма)
    d.polygon([(cx - S(70), cy + S(230)), (cx - S(50), cy + S(95)),
               (cx + S(50), cy + S(95)), (cx + S(70), cy + S(230))],
              fill=(40, 40, 40), outline=INK)
    d.polygon([(cx - S(30), cy + S(95)), (cx, cy + S(140)), (cx + S(30), cy + S(95))],
              fill=PAPER, outline=INK)
    d.line((cx, cy + S(110), cx, cy + S(150)), fill=(220, 220, 220), width=int(S(6)))
    if arm_up:
        d.line((cx + S(45), cy + S(110), cx + S(110), cy - S(60)), fill=(40, 40, 40), width=int(S(20)))
        d.ellipse((cx + S(98), cy - S(82), cx + S(124), cy - S(56)), fill=PAPER, outline=INK, width=2)
    # шея и голова
    d.rectangle((cx - S(12), cy + S(70), cx + S(12), cy + S(100)), fill=PAPER, outline=INK)
    d.ellipse((cx - S(62), cy - S(60), cx + S(62), cy + S(80)), fill=PAPER, outline=INK, width=3)
    # волосы-каре
    d.chord((cx - S(70), cy - S(72), cx + S(70), cy + S(60)), 180, 360, fill=INK)
    d.rectangle((cx - S(70), cy - S(6), cx - S(46), cy + S(70)), fill=INK)
    d.rectangle((cx + S(46), cy - S(6), cx + S(70), cy + S(70)), fill=INK)
    d.polygon([(cx - S(50), cy - S(8)), (cx - S(20), cy - S(30)), (cx + S(10), cy - S(8)),
               (cx + S(40), cy - S(32)), (cx + S(52), cy - S(4)), (cx + S(52), cy - S(40)),
               (cx - S(52), cy - S(40))], fill=INK)
    # заколка-закладка (золотая в бренде, тут светлая)
    d.polygon([(cx + S(30), cy - S(50)), (cx + S(48), cy - S(50)), (cx + S(48), cy - S(14)),
               (cx + S(39), cy - S(22)), (cx + S(30), cy - S(14))], fill=(230, 230, 230), outline=INK)
    # глаза
    ey = cy + S(18)
    for ex in (cx - S(24), cx + S(24)):
        if face == "shock":
            d.ellipse((ex - S(14), ey - S(16), ex + S(14), ey + S(16)), fill=PAPER, outline=INK, width=3)
            d.ellipse((ex - S(4), ey - S(4), ex + S(4), ey + S(4)), fill=INK)
        elif face == "happy":
            d.arc((ex - S(14), ey - S(8), ex + S(14), ey + S(14)), 200, 340, fill=INK, width=4)
        else:
            d.ellipse((ex - S(11), ey - S(15), ex + S(11), ey + S(13)), fill=INK)
            d.ellipse((ex - S(6), ey - S(10), ex + S(1), ey - S(3)), fill=PAPER)
    # рот
    my = cy + S(52)
    if face == "shock":
        d.ellipse((cx - S(10), my - S(8), cx + S(10), my + S(12)), fill=INK)
    elif face == "happy":
        d.chord((cx - S(14), my - S(10), cx + S(14), my + S(10)), 0, 180, fill=INK)
    else:
        d.arc((cx - S(10), my - S(6), cx + S(10), my + S(4)), 20, 160, fill=INK, width=3)
    if face == "shock":
        for k in range(3):
            d.line((cx - S(70) - k * S(10), cy - S(70) + k * S(14), cx - S(90) - k * S(10), cy - S(90) + k * S(14)),
                   fill=INK, width=3)


def cat(img, cx, cy, s=1.0, wink=False):
    """Кот-библиотекарь в очках."""
    d = ImageDraw.Draw(img)
    def S(v): return v * s
    d.ellipse((cx - S(60), cy + S(10), cx + S(60), cy + S(110)), fill=(70, 70, 70), outline=INK, width=3)
    d.arc((cx + S(30), cy + S(30), cx + S(120), cy + S(120)), 270, 80, fill=INK, width=int(S(12)))
    d.ellipse((cx - S(50), cy - S(50), cx + S(50), cy + S(40)), fill=(70, 70, 70), outline=INK, width=3)
    for sx in (-1, 1):
        d.polygon([(cx + sx * S(46), cy - S(20)), (cx + sx * S(40), cy - S(78)), (cx + sx * S(12), cy - S(44))],
                  fill=(70, 70, 70), outline=INK)
        d.polygon([(cx + sx * S(38), cy - S(28)), (cx + sx * S(36), cy - S(62)), (cx + sx * S(20), cy - S(42))],
                  fill=(200, 200, 200))
    # очки
    for ex in (cx - S(20), cx + S(20)):
        d.ellipse((ex - S(15), cy - S(18), ex + S(15), cy + S(12)), fill=PAPER, outline=INK, width=3)
    d.line((cx - S(5), cy - S(4), cx + S(5), cy - S(4)), fill=INK, width=3)
    d.ellipse((cx - S(26), cy - S(9), cx - S(14), cy + S(3)), fill=INK)
    if wink:
        d.arc((cx + S(10), cy - S(10), cx + S(30), cy + S(6)), 200, 340, fill=INK, width=3)
    else:
        d.ellipse((cx + S(14), cy - S(9), cx + S(26), cy + S(3)), fill=INK)
    d.polygon([(cx - S(5), cy + S(14)), (cx + S(5), cy + S(14)), (cx, cy + S(20))], fill=INK)
    for sx in (-1, 1):
        for k in (-1, 0, 1):
            d.line((cx + sx * S(14), cy + S(20) + k * S(4), cx + sx * S(56), cy + S(16) + k * S(9)), fill=PAPER, width=2)


def book(img, cx, cy, s=1.0, open_=False, glow=False):
    d = ImageDraw.Draw(img)
    def S(v): return v * s
    if glow:
        for r in range(160, 40, -20):
            g = 255
            d.ellipse((cx - S(r), cy - S(r * .7), cx + S(r), cy + S(r * .7)), outline=(200, 200, 200), width=2)
    if open_:
        d.polygon([(cx, cy - S(10)), (cx - S(120), cy - S(40)), (cx - S(120), cy + S(50)), (cx, cy + S(70))],
                  fill=PAPER, outline=INK, width=3)
        d.polygon([(cx, cy - S(10)), (cx + S(120), cy - S(40)), (cx + S(120), cy + S(50)), (cx, cy + S(70))],
                  fill=PAPER, outline=INK, width=3)
        for k in range(1, 5):
            d.line((cx - S(105), cy - S(25) + k * S(14), cx - S(15), cy - S(2) + k * S(14)), fill=(150, 150, 150), width=2)
            d.line((cx + S(15), cy - S(2) + k * S(14), cx + S(105), cy - S(25) + k * S(14)), fill=(150, 150, 150), width=2)
    else:
        d.rectangle((cx - S(45), cy - S(65), cx + S(45), cy + S(65)), fill=(60, 60, 60), outline=INK, width=3)
        d.rectangle((cx - S(35), cy - S(50), cx + S(35), cy - S(20)), outline=PAPER, width=2)
        d.ellipse((cx - S(16), cy + S(4), cx + S(16), cy + S(36)), outline=PAPER, width=3)


def rider(img, cx, cy, s=1.0):
    """Всадник на коне (силуэт), конь в галопе."""
    d = ImageDraw.Draw(img)
    def P(pts): return [(cx + x * s, cy + y * s) for x, y in pts]
    horse = P([(-120, -10), (-60, -40), (40, -45), (80, -90), (110, -100), (130, -80), (115, -70),
               (95, -60), (85, -20), (70, 10), (-90, 15), (-130, 0)])
    d.polygon(horse, fill=INK)
    for leg in ([(-90, 10), (-140, 60), (-130, 66), (-80, 20)], [(-70, 10), (-40, 75), (-30, 72), (-55, 12)],
                [(50, 5), (110, 45), (115, 37), (65, 0)], [(60, 8), (30, 80), (40, 82), (75, 12)]):
        d.polygon(P(leg), fill=INK)
    d.polygon(P([(-120, -10), (-175, -25), (-185, 5), (-125, 5)]), fill=INK)   # хвост
    d.polygon(P([(80, -90), (60, -60), (50, -45), (75, -55)]), fill=(90, 90, 90))  # грива
    # всадник
    d.polygon(P([(-10, -45), (-25, -110), (5, -125), (25, -100), (20, -45)]), fill=INK)
    d.ellipse(P([(-12, -160), (22, -126)])[0] + P([(-12, -160), (22, -126)])[1], fill=INK)
    d.polygon(P([(-14, -150), (8, -178), (26, -150)]), fill=INK)                # малахай
    d.line(P([(15, -110), (80, -85)]), fill=INK, width=int(6 * s))             # повод
    d.polygon(P([(-25, -105), (-75, -95), (-70, -80), (-22, -90)]), fill=(90, 90, 90))  # плащ


# ---------- Облачка и подписи ----------
def vtext_size(lines, size):
    cols = len(lines)
    rows = max(len(l) for l in lines)
    return cols * size * 1.25, rows * size * 1.08


def draw_vtext(d, x_right, y_top, lines, size, fnt):
    """Вертикальный японский текст: столбцы справа налево."""
    col_w = size * 1.25
    for ci, line in enumerate(lines):
        x = x_right - (ci + 1) * col_w + (col_w - size) / 2
        y = y_top
        for ch in line:
            if ch in "ー":
                img_ch = Image.new("L", (size, size), 0)
                ImageDraw.Draw(img_ch).text((0, 0), ch, font=fnt, fill=255)
                img_ch = img_ch.rotate(-90)
                d.bitmap((x, y), img_ch, fill=INK)
            elif ch in "、。":
                d.text((x + size * .55, y - size * .45), ch, font=fnt, fill=INK)
            elif ch in "…":
                d.text((x + size * .15, y), "︙", font=fnt, fill=INK)
            elif ch in "！？":
                d.text((x + size * .1, y), ch, font=fnt, fill=INK)
            else:
                d.text((x, y), ch, font=fnt, fill=INK)
            y += size * 1.08


BOXES = {}


def bubble(img, page, key, cx, cy, lines, size=30, tail=None, shout=False, think=False):
    d = ImageDraw.Draw(img)
    tw, th = vtext_size(lines, size)
    rx, ry = tw / 2 + 34, th / 2 + 34
    if tail:
        tx, ty = tail
        ang = math.atan2(ty - cy, tx - cx)
        base = [(cx + math.cos(ang + .35) * rx * .8, cy + math.sin(ang + .35) * ry * .8),
                (cx + math.cos(ang - .35) * rx * .8, cy + math.sin(ang - .35) * ry * .8)]
        d.polygon([base[0], (tx, ty), base[1]], fill=PAPER, outline=INK)
    if shout:
        pts = []
        n = 22
        for i in range(n):
            a = 2 * math.pi * i / n
            k = 1.18 if i % 2 else .95
            pts.append((cx + math.cos(a) * rx * k, cy + math.sin(a) * ry * k))
        d.polygon(pts, fill=PAPER, outline=INK, width=3)
    elif think:
        d.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=PAPER, outline=INK, width=3)
    else:
        d.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=PAPER, outline=INK, width=3)
    if tail:
        # закрыть шов хвоста
        d.polygon([(cx + math.cos(ang + .3) * rx * .76, cy + math.sin(ang + .3) * ry * .76),
                   (cx + math.cos(ang) * rx * 1.02, cy + math.sin(ang) * ry * 1.02),
                   (cx + math.cos(ang - .3) * rx * .76, cy + math.sin(ang - .3) * ry * .76),
                   (cx, cy)], fill=PAPER)
    draw_vtext(d, cx + tw / 2, cy - th / 2, lines, size, font(size))
    # рамка перевода — внутренность облачка
    bx0, by0 = cx - rx * .9, cy - ry * .88
    BOXES.setdefault(page, []).append({"key": key, "x": bx0, "y": by0, "w": rx * 1.8, "h": ry * 1.76})


def caption(img, page, key, x, y, lines, size=26):
    d = ImageDraw.Draw(img)
    tw, th = vtext_size(lines, size)
    d.rectangle((x, y, x + tw + 28, y + th + 28), fill=PAPER, outline=INK, width=3)
    draw_vtext(d, x + 14 + tw, y + 14, lines, size, font(size))
    BOXES.setdefault(page, []).append({"key": key, "x": x + 2, "y": y + 2, "w": tw + 24, "h": th + 24})


def sfx(img, page, key, x, y, text, size=70, angle=-12):
    layer = Image.new("RGBA", (size * len(text) + 40, size + 40), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    f = ImageFont.truetype(FONT_SFX, size)
    ld.text((20, 10), text, font=f, fill=PAPER, stroke_width=8, stroke_fill=INK)
    layer = layer.rotate(angle, expand=True)
    img.paste(layer, (int(x), int(y)), layer)
    BOXES.setdefault(page, []).append({"key": key, "x": x + 10, "y": y + 10,
                                       "w": layer.width - 20, "h": layer.height - 20, "sfx": True})


def panel_frame(img, box):
    ImageDraw.Draw(img).rectangle(box, outline=INK, width=5)


def new_page():
    return Image.new("RGB", (W, H), PAPER)


M = 36
G = 18


def clip(img, box, painter):
    """Нарисовать содержимое панели только внутри её рамки."""
    x0, y0, x1, y1 = [int(v) for v in box]
    sub = Image.new("RGB", (x1 - x0, y1 - y0), PAPER)
    painter(sub, x1 - x0, y1 - y0)
    img.paste(sub, (x0, y0))
    panel_frame(img, box)


# ===================== Страница 1 =====================
p = new_page()
A = (M, M, W - M, 470)
B = (M, 470 + G, 470, H - M)
C = (470 + G, 470 + G, W - M, H - M)
clip(p, A, lambda im, w, h: (shelves(im, (0, 0, w, h)),
                             tone(im, (0, h - 60, w, h), step=6, fill=(120, 120, 120))))
caption(p, 1, "c1", A[2] - 120, A[1] + 22, ["放課後の", "図書館。"], 30)
clip(p, B, lambda im, w, h: (shelves(im, (0, 0, w, h * .55)), girl(im, w * .5, h * .55, 1.25, "calm", arm_up=True)))
bubble(p, 1, "b1", B[0] + 110, B[1] + 150, ["あれ？", "この本、", "見たことない…"], 30, tail=(B[0] + 210, B[1] + 330))
clip(p, C, lambda im, w, h: (tone(im, (0, 0, w, h), step=8, fill=(205, 205, 205)),
                             shelves(im, (0, h * .45, w, h)), cat(im, w * .52, h * .30, 1.35)))
bubble(p, 1, "b2", C[0] + 105, C[3] - 210, ["やっと", "来たね、", "アヤ。"], 32, tail=(C[0] + 190, C[1] + 330))
sfx(p, 1, "s1", C[2] - 190, C[1] + 20, "ニャ", 64)
p.save(OUT / "p1.png", optimize=True)

# ===================== Страница 2 =====================
p = new_page()
A = (M, M, W - M, 560)
B = (M, 560 + G, W * .48, H - M)
C = (W * .48 + G, 560 + G, W - M, H - M)
def pA(im, w, h):
    speed_lines(im, (0, 0, w, h), (w * .5, h * .55))
    girl(im, w * .5, h * .38, 1.45, "shock")
clip(p, A, pA)
bubble(p, 2, "b1", A[0] + 140, A[1] + 200, ["ね、猫が", "しゃべった", "！？"], 40, shout=True)
clip(p, B, lambda im, w, h: (tone(im, (0, 0, w, h), step=7, fill=(170, 170, 170)), cat(im, w * .5, h * .55, 1.5, wink=True)))
bubble(p, 2, "b2", B[0] + 110, B[1] + 160, ["驚くのは", "まだ早い。"], 32, tail=(B[0] + 190, B[1] + 380))
def pC(im, w, h):
    shelves(im, (0, 0, w, h * .4))
    book(im, w * .45, h * .62, 1.5)
    cat(im, w * .78, h * .72, .8)
clip(p, C, pC)
bubble(p, 2, "b3", C[0] + 120, C[1] + 150, ["その本を", "開いて", "ごらん。"], 30, tail=(C[0] + 330, C[1] + 470))
p.save(OUT / "p2.png", optimize=True)

# ===================== Страница 3 =====================
p = new_page()
A = (M, M, W - M, 520)
B = (M, 520 + G, W - M, 1000)
C = (M, 1000 + G, W - M, H - M)
def pA3(im, w, h):
    speed_lines(im, (0, 0, w, h), (w * .5, h * .55), n=140, color=(110, 110, 110))
    book(im, w * .5, h * .6, 1.7, open_=True, glow=True)
clip(p, A, pA3)
caption(p, 3, "c1", A[2] - 125, A[1] + 22, ["ページから", "風が吹いた。"], 28)
sfx(p, 3, "s1", A[0] + 40, A[1] + 30, "パァッ", 74)
def pB3(im, w, h):
    hz = steppe(im, (0, 0, w, h))
    rider(im, w * .72, hz + 10, .55)
    girl(im, w * .2, h * .32, 1.05, "shock")
clip(p, B, pB3)
bubble(p, 3, "b1", B[0] + 330, B[1] + 140, ["ここは…", "草原？"], 34, tail=(B[0] + 210, B[1] + 220))
def pC3(im, w, h):
    steppe(im, (0, 0, w, h), sun=False)
    cat(im, w * .3, h * .45, 1.15)
clip(p, C, pC3)
bubble(p, 3, "b2", C[0] + 560, C[1] + 160, ["読んだ", "物語の", "中だよ。"], 32, tail=(C[0] + 380, C[1] + 170))
p.save(OUT / "p3.png", optimize=True)

# ===================== Страница 4 =====================
p = new_page()
A = (M, M, W - M, 600)
B = (M, 600 + G, W * .5, 1080)
C = (W * .5 + G, 600 + G, W - M, 1080)
D = (M, 1080 + G, W - M, H - M)
def pA4(im, w, h):
    hz = steppe(im, (0, 0, w, h))
    speed_lines(im, (0, 0, w, h), (w * .1, h * .6), n=50, color=(160, 160, 160))
    rider(im, w * .55, hz + 70, 1.5)
clip(p, A, pA4)
bubble(p, 4, "b1", A[0] + 130, A[1] + 180, ["旅人よ、", "道に", "迷ったか？"], 32, tail=(A[0] + 330, A[1] + 200))
clip(p, B, lambda im, w, h: (speed_lines(im, (0, 0, w, h), (w * .5, h * .5), n=60, color=(180, 180, 180)),
                             girl(im, w * .5, h * .35, 1.1, "happy")))
bubble(p, 4, "b2", B[0] + 110, B[1] + 140, ["わたし、", "続きが", "知りたい！"], 30, tail=(B[0] + 200, B[1] + 260))
clip(p, C, lambda im, w, h: (tone(im, (0, 0, w, h), step=7, fill=(190, 190, 190)), cat(im, w * .66, h * .66, 1.1, wink=True)))
bubble(p, 4, "b3", C[0] + 105, C[1] + 150, ["しっかり", "つかまって！"], 28, tail=(C[0] + 215, C[1] + 300))
def pD(im, w, h):
    tone(im, (0, 0, w, h), step=6, fill=(60, 60, 60))
    d = ImageDraw.Draw(im)
    d.rectangle((0, h * .7, w, h), fill=(30, 30, 30))
    book(im, w * .5, h * .55, 1.1, open_=True)
clip(p, D, pD)
caption(p, 4, "c1", D[2] - 150, D[1] + 20, ["物語は、", "読む人を", "待っている。"], 26)
caption(p, 4, "c2", D[0] + 30, D[1] + 50, ["つづく"], 30)
p.save(OUT / "p4.png", optimize=True)

# ---------- Тексты: оригинал и переводы ----------
TEXT = {
    1: {"c1": ("放課後の図書館。", "Библиотека после уроков.", "Сабақтан кейінгі кітапхана.", "The library, after school."),
        "b1": ("あれ？この本、見たことない…", "Хм? Эту книгу я раньше не видела…", "Ой? Бұл кітапты бұрын көрмеппін…", "Huh? I've never seen this book before…"),
        "b2": ("やっと来たね、アヤ。", "Наконец-то ты пришла, Ая.", "Ақыры келдің бе, Ая.", "You finally came, Aya."),
        "s1": ("ニャ", "Мяу", "Мияу", "Meow")},
    2: {"b1": ("ね、猫がしゃべった！？", "К-кот заговорил?!", "М-мысық сөйледі ме?!", "Th-the cat talked?!"),
        "b2": ("驚くのはまだ早い。", "Удивляться ещё рано.", "Таңғалуға әлі ерте.", "Too early to be surprised."),
        "b3": ("その本を開いてごらん。", "Открой-ка эту книгу.", "Сол кітапты ашып көрші.", "Go on, open that book.")},
    3: {"c1": ("ページから風が吹いた。", "Из страниц подул ветер.", "Беттерден жел соқты.", "Wind blew out of the pages."),
        "s1": ("パァッ", "Вжух!", "Жарқ!", "Fwoosh!"),
        "b1": ("ここは…草原？", "Где это мы… степь?", "Бұл қай жер… дала ма?", "Where… is this the steppe?"),
        "b2": ("読んだ物語の中だよ。", "Мы внутри истории, которую ты читаешь.", "Біз сен оқыған әңгіменің ішіндеміз.", "We're inside the story you read.")},
    4: {"b1": ("旅人よ、道に迷ったか？", "Путник, ты сбился с дороги?", "Жолаушы, адасып қалдың ба?", "Traveller, have you lost your way?"),
        "b2": ("わたし、続きが知りたい！", "Я хочу узнать, что дальше!", "Мен әрі қарай не болатынын білгім келеді!", "I want to know what happens next!"),
        "b3": ("しっかりつかまって！", "Держись крепче!", "Мықтап ұста!", "Hold on tight!"),
        "c1": ("物語は、読む人を待っている。", "Истории ждут своих читателей.", "Әңгімелер өз оқырманын күтеді.", "Stories wait for their readers."),
        "c2": ("つづく", "Продолжение следует", "Жалғасы бар", "To be continued")},
}

pages = []
for n in range(1, 5):
    boxes = []
    for b in BOXES[n]:
        src, ru, kk, en = TEXT[n][b["key"]]
        boxes.append({"x": round(b["x"] / W * 100, 2), "y": round(b["y"] / H * 100, 2),
                      "w": round(b["w"] / W * 100, 2), "h": round(b["h"] / H * 100, 2),
                      "shape": "oval" if b["key"].startswith("b") else "rect",
                      "src": src, "ru": ru, "kk": kk, "en": en})
    pages.append({"file": f"p{n}.png", "boxes": boxes})
(OUT / "manga.json").write_text(json.dumps({
    "title": "Кот из библиотеки", "original_title": "図書館の猫", "author": "Команда «Оқу»",
    "language": "ja", "pages": pages}, ensure_ascii=False, indent=1), encoding="utf-8")
print("ok", [len(p["boxes"]) for p in pages])
