"""Сделать документы 14 и 15 (Markdown) из юридических страниц сайта.

Источник один — ``static/legal/*.ru.html``, поэтому тексты на сайте и в
документах всегда совпадают. Запуск из корня проекта::

    python docs/tools/gen_legal_md.py
"""

from __future__ import annotations

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = {
    "terms": ("14_Пользовательское_соглашение.md", "Документ 14"),
    "privacy": ("15_Политика_конфиденциальности.md", "Документ 15"),
}


def to_markdown(src: str) -> str:
    """Перевести простой HTML (h1, h2, p, ol, ul, li, b, a, div) в Markdown."""
    text = src.replace("\r", "")
    text = re.sub(r'<a href="#/(\w+)">(.*?)</a>', r"\2", text)
    text = re.sub(r"</?b>", "**", text)
    text = re.sub(r"<h1>(.*?)</h1>", r"# \1\n", text)
    text = re.sub(r"<h2>(.*?)</h2>", r"\n## \1\n", text)
    text = re.sub(r'<div class="toc">(.*?)</div>', r"> \1\n", text, flags=re.S)
    out, counter = [], 0
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("<ol>"):
            counter = 1
            continue
        if stripped.startswith("</ol>") or stripped in ("<ul>", "</ul>"):
            counter = 0
            out.append("")
            continue
        item = re.match(r"<li>(.*)</li>", stripped)
        if item:
            prefix = f"{counter}." if counter else "-"
            counter = counter + 1 if counter else 0
            out.append(f"{prefix} {item.group(1)}")
            continue
        out.append(stripped)
    md = "\n".join(out)
    md = re.sub(r'<p class="[^"]*">(.*?)</p>', r"*\1*", md)
    md = re.sub(r"<p>(.*?)</p>", r"\1\n", md, flags=re.S)
    md = re.sub(r"<[^>]+>", "", md)
    md = html.unescape(md)
    return re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"


def main() -> None:
    for name, (filename, label) in DOCS.items():
        src = (ROOT / "static" / "legal" / f"{name}.ru.html").read_text(
            encoding="utf-8")
        body = to_markdown(src)
        title, rest = body.split("\n", 1)
        header = (f"{title.replace('# ', f'# {label}. ', 1)}\n\n"
                  "*Текст совпадает с разделом сайта; редакции на казахском "
                  "и английском — `static/legal/*.kk.html`, `*.en.html`.*\n")
        (ROOT / "docs" / filename).write_text(header + rest,
                                              encoding="utf-8")
        print("Создан", filename)


if __name__ == "__main__":
    main()
