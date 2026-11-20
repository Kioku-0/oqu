"""Измерение покрытия тестами без внешней библиотеки coverage.

Считает долю исполняемых строк модулей бизнес-логики, которые были выполнены
во время прогона pytest. Исполняемые строки определяются разбором байт-кода
(``code.co_lines``), выполненные — через ``sys.settrace``.

Запуск::  python run_coverage.py
"""

import os
import sys

TARGETS = [
    os.path.abspath("app/service.py"),
    os.path.abspath("app/profanity.py"),
    os.path.abspath("app/security.py"),
    os.path.abspath("app/db.py"),
]


def executable_lines(path: str) -> set[int]:
    """Вернуть номера исполняемых строк файла (через байт-код)."""
    with open(path, encoding="utf-8") as fh:
        code = compile(fh.read(), path, "exec")
    lines: set[int] = set()
    stack = [code]
    while stack:
        obj = stack.pop()
        for _start, _end, lineno in obj.co_lines():
            if lineno:
                lines.add(lineno)
        for const in obj.co_consts:
            if hasattr(const, "co_lines"):
                stack.append(const)
    return lines


def main() -> int:
    executed: dict[str, set[int]] = {t: set() for t in TARGETS}
    targets = set(TARGETS)

    def tracer(frame, event, arg):
        if event in ("line", "call"):
            fn = frame.f_code.co_filename
            if fn in targets:
                executed[fn].add(frame.f_lineno)
        return tracer

    import pytest

    sys.settrace(tracer)
    try:
        pytest.main(["-q", "-W", "ignore::UserWarning", "tests"])
    finally:
        sys.settrace(None)

    print("\n================ ПОКРЫТИЕ ТЕСТАМИ ================")
    total_exec, total_cov = 0, 0
    for path in TARGETS:
        execut = executable_lines(path)
        covered = executed[path] & execut
        total_exec += len(execut)
        total_cov += len(covered)
        pct = 100.0 * len(covered) / len(execut) if execut else 100.0
        print(f"{os.path.basename(path):14} "
              f"строк: {len(execut):3d}  покрыто: {len(covered):3d}  "
              f"{pct:5.1f}%")
    overall = 100.0 * total_cov / total_exec if total_exec else 100.0
    print("-" * 49)
    print(f"{'ИТОГО':14} строк: {total_exec:3d}  покрыто: {total_cov:3d}  "
          f"{overall:5.1f}%")
    print("=" * 49)
    return 0 if overall >= 80.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
