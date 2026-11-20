"""Собрать версии документов для печати (.docx) из Markdown.

Запуск из корня проекта::

    python docs/tools/build_docx.py

Для каждого файла ``docs/NN_*.md`` создаётся ``docs/docx/NN_*.docx``:
титульный лист, поля по ГОСТ 7.32 (левое 30 мм, правое 15 мм, верх и низ
20 мм), шрифт Times New Roman, нумерация страниц. Поддерживаются заголовки,
абзацы с **жирным**, *курсивом*, `кодом`, списки, таблицы, блоки кода,
цитаты и картинки. Диаграммы Mermaid (их GitHub показывает картинками)
превращаются в таблицы связей, чтобы схема читалась и на бумаге.
"""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

DOCS = Path(__file__).resolve().parents[1]
OUT = DOCS / "docx"
FONT = "Times New Roman"
MONO = "Consolas"
ACCENT = RGBColor(0x0F, 0x6E, 0x5A)
INLINE = re.compile(r"(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`"
                    r"|\[[^\]]+\]\([^)]+\)|<[^>\s]+>)")


# --------------------------------------------------------------------------
# Оформление
# --------------------------------------------------------------------------
def setup(doc: Document) -> None:
    """Поля, шрифты и стили заголовков."""
    for section in doc.sections:
        section.page_height, section.page_width = Cm(29.7), Cm(21.0)
        section.left_margin, section.right_margin = Cm(3.0), Cm(1.5)
        section.top_margin = section.bottom_margin = Cm(2.0)
    normal = doc.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(14)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    fmt = normal.paragraph_format
    fmt.space_after = Pt(4)
    fmt.line_spacing = 1.15
    sizes = {1: 16, 2: 15, 3: 14, 4: 14}
    for level, size in sizes.items():
        style = doc.styles[f"Heading {level}"]
        style.font.name = FONT
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor(0x1C, 0x1B, 0x18)
        style.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
        style.paragraph_format.space_before = Pt(12 if level > 1 else 0)
        style.paragraph_format.space_after = Pt(6)
        style.paragraph_format.keep_with_next = True


def page_number_footer(section) -> None:
    """Номер страницы по центру нижнего колонтитула."""
    paragraph = section.footer.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    for kind, text in (("begin", None), (None, "PAGE"), ("end", None)):
        if kind:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), kind)
        else:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = text
        run._r.append(el)
    run.font.size = Pt(11)


def shade(cell_or_par, color: str) -> None:
    """Заливка ячейки таблицы или абзаца."""
    target = cell_or_par._tc if hasattr(cell_or_par, "_tc") \
        else cell_or_par._p
    props = target.get_or_add_tcPr() if hasattr(cell_or_par, "_tc") \
        else target.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color)
    props.append(shd)


def title_page(doc: Document, title: str) -> None:
    """Титульный лист в принятом в вузе виде."""
    def line(text, size=14, bold=False, space=0, align="center"):
        p = doc.add_paragraph()
        p.alignment = {"center": WD_ALIGN_PARAGRAPH.CENTER,
                       "right": WD_ALIGN_PARAGRAPH.RIGHT}[align]
        p.paragraph_format.space_before = Pt(space)
        run = p.add_run(text)
        run.font.size = Pt(size)
        run.bold = bold
        return p

    line("Министерство науки и высшего образования Республики Казахстан")
    line("Кызылординский университет имени Коркыт Ата", bold=True)
    line("Дисциплина «Разработка кроссплатформенных веб-, мобильных и "
         "настольных приложений с помощью Python»", size=13, space=6)
    line("КУРСОВОЙ ПРОЕКТ", size=16, bold=True, space=120)
    line("Тема: «Библиотека REST API с документацией OpenAPI» (вариант 11)",
         space=6)
    line("Проект «Оқу» — электронная библиотека", bold=True, space=6)
    line(title, size=18, bold=True, space=36).runs[0].font.color.rgb = ACCENT
    line("Выполнили: Мұхан Надирхалиф, Хадизат", space=150, align="right")
    line("Проверил: Айтимов Мурат Жолдасбекович", align="right")
    line("Кызылорда, 2026", space=110)
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


# --------------------------------------------------------------------------
# Текст
# --------------------------------------------------------------------------
def add_inline(paragraph, text: str, size: float | None = None) -> None:
    """Добавить текст с **жирным**, *курсивом*, `кодом` и ссылками."""
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            run = paragraph.add_run(part[2:-2])
            run.bold = True
        elif part.startswith("`") and part.endswith("`"):
            run = paragraph.add_run(part[1:-1])
            run.font.name = MONO
            run.font.size = Pt((size or 14) - 2)
        elif part.startswith("[") and "](" in part:
            label, url = re.match(r"\[([^\]]+)\]\(([^)]+)\)", part).groups()
            run = paragraph.add_run(label)
            if url.startswith("http"):
                run.font.color.rgb = ACCENT
        elif part.startswith("<") and part.endswith(">") and \
                part[1:5] == "http":
            run = paragraph.add_run(part[1:-1])
            run.font.color.rgb = ACCENT
        elif len(part) > 2 and part.startswith("*") and part.endswith("*"):
            run = paragraph.add_run(part[1:-1])
            run.italic = True
        else:
            run = paragraph.add_run(part)
        if size:
            run.font.size = Pt(size)


def add_table(doc: Document, rows: list[list[str]]) -> None:
    """Таблица Markdown -> таблица Word с выделенной шапкой."""
    width = max(len(r) for r in rows)
    table = doc.add_table(rows=len(rows), cols=width)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    size = 10 if width >= 5 else 11
    for i, row in enumerate(rows):
        for j in range(width):
            cell = table.cell(i, j)
            cell.paragraphs[0].paragraph_format.space_after = Pt(0)
            cell.paragraphs[0].paragraph_format.line_spacing = 1.0
            add_inline(cell.paragraphs[0], row[j] if j < len(row) else "",
                       size)
            if i == 0:
                shade(cell, "E2EFE9")
                for run in cell.paragraphs[0].runs:
                    run.bold = True
    doc.add_paragraph()


def add_code(doc: Document, lines: list[str]) -> None:
    """Блок кода моноширинным шрифтом на сером фоне."""
    for line in lines or [""]:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.0
        p.paragraph_format.left_indent = Cm(0.3)
        run = p.add_run(line if line else " ")
        run.font.name = MONO
        run.font.size = Pt(9.5)
        shade(p, "F2EFE8")
    doc.add_paragraph()


def add_image(doc: Document, alt: str, src: str) -> None:
    """Картинка шириной 15 см с подписью; если файла нет — заметка."""
    path = (DOCS / src).resolve()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if path.is_file():
        # Скриншоты телефона узкие — делаем их уже, чтобы влезли на страницу.
        narrow = "mobile" in path.name
        p.add_run().add_picture(str(path), width=Cm(6.5 if narrow else 15))
    else:
        run = p.add_run(f"[Скриншот: {alt}]")
        run.italic = True
    caption = doc.add_paragraph()
    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = caption.add_run(f"Рисунок — {alt}")
    run.italic = True
    run.font.size = Pt(11)


# --------------------------------------------------------------------------
# Диаграммы Mermaid -> таблицы
# --------------------------------------------------------------------------
NODE = re.compile(r"(\w+)\s*(?:\[\(?|\(\(|\{)([^\]\)}]*)(?:\)?\]|\)\)|\})")
ER_KIND = {"||--o{": "один ко многим", "|o--o{": "ноль/один ко многим",
           "||--||": "один к одному", "}o--o{": "многие ко многим"}


def mermaid_rows(lines: list[str]) -> tuple[str, list[list[str]]]:
    """Разобрать flowchart / erDiagram / sequenceDiagram в строки таблицы."""
    kind = lines[0].split()[0] if lines else ""
    clean = lambda s: re.sub(r"<br\s*/?>", " ", s).strip(' "')  # noqa: E731
    if kind == "erDiagram":
        rows = [["Таблица", "Связь", "Таблица", "Смысл"]]
        for line in lines[1:]:
            m = re.match(r"\s*(\w+)\s+(\S+)\s+(\w+)\s*:\s*(.*)", line)
            if m:
                rows.append([m[1], ER_KIND.get(m[2], m[2]), m[3],
                             clean(m[4]) or "—"])
        return "Схема связей таблиц базы данных", rows
    if kind == "sequenceDiagram":
        rows, names = [["№", "От кого", "Кому", "Действие"]], {}
        for line in lines[1:]:
            part = re.match(r"\s*participant\s+(\S+)\s+as\s+(.+)", line)
            if part:
                names[part[1]] = part[2]
                continue
            msg = re.match(r"\s*(\S+?)-+>>(\S+?):\s*(.*)", line)
            note = re.match(r"\s*Note over [^:]+:\s*(.*)", line)
            if msg:
                rows.append([str(len(rows)), names.get(msg[1], msg[1]),
                             names.get(msg[2], msg[2]), clean(msg[3])])
            elif note:
                rows.append(["—", "", "", "Примечание: " + clean(note[1])])
        return "Последовательность действий", rows
    labels: dict[str, str] = {}
    for line in lines[1:]:
        for node_id, label in NODE.findall(line):
            labels[node_id] = clean(label)
    rows = [["Элемент", "Связь", "Элемент"]]
    for line in lines[1:]:
        if line.strip().startswith(("subgraph", "end")):
            continue
        body = NODE.sub(lambda m: m[1], line)
        m = re.match(r"\s*(\w+)\s*(?:--\s*(.*?)\s*-->|-->)\s*(\w+)"
                     r"(?:\s*-->\s*(\w+))?", body)
        if m:
            rows.append([labels.get(m[1], m[1]), m[2] or "→",
                         labels.get(m[3], m[3])])
            if m[4]:
                rows.append([labels.get(m[3], m[3]), "→",
                             labels.get(m[4], m[4])])
    title = "Схема компонентов и связей"
    if len(rows) == 1:
        rows = [["Элемент"]] + [[v] for v in labels.values()]
    return title, rows


# --------------------------------------------------------------------------
# Разбор Markdown
# --------------------------------------------------------------------------
def build(md_path: Path) -> Path:
    """Собрать один документ .docx."""
    lines = md_path.read_text(encoding="utf-8-sig").split("\n")
    title = lines[0].lstrip("# ").strip()
    doc = Document()
    setup(doc)
    title_page(doc, title)
    body = doc.add_section(WD_SECTION.CONTINUOUS)
    page_number_footer(body)

    i = 1
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            block = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i])
                i += 1
            if lang == "mermaid":
                caption, rows = mermaid_rows([b for b in block if b.strip()])
                p = doc.add_paragraph()
                run = p.add_run(caption)
                run.bold = True
                run.font.size = Pt(12)
                add_table(doc, rows)
            else:
                add_code(doc, block)
        elif stripped.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in
                         lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            add_table(doc, rows)
            continue
        elif stripped.startswith("#"):
            level = min(len(stripped) - len(stripped.lstrip("#")), 4)
            doc.add_heading(stripped.lstrip("# ").strip(), level=level)
        elif re.match(r"!\[[^\]]*\]\([^)]+\)", stripped):
            alt, src = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", stripped).groups()
            add_image(doc, alt, src)
        elif re.match(r"(\d+\.|[-*])\s", stripped):
            numbered = stripped[0].isdigit()
            p = doc.add_paragraph(style="List Number" if numbered
                                  else "List Bullet")
            p.paragraph_format.left_indent = Cm(1.0 + (len(line) -
                                                       len(line.lstrip()))
                                                * 0.25)
            add_inline(p, re.sub(r"^(\d+\.|[-*])\s", "", stripped))
        elif stripped.startswith(">"):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.6)
            shade(p, "E2EFE9")
            add_inline(p, stripped.lstrip("> "))
        elif stripped:
            p = doc.add_paragraph()
            p.paragraph_format.first_line_indent = Cm(1.25)
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            add_inline(p, stripped)
        i += 1

    OUT.mkdir(exist_ok=True)
    target = OUT / (md_path.stem + ".docx")
    doc.save(target)
    return target


def main() -> None:
    for md in sorted(DOCS.glob("[0-9][0-9]_*.md")):
        print("Собран", build(md).name)


if __name__ == "__main__":
    main()
