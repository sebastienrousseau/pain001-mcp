#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Fail when a function or file exceeds the complexity limits.

Per function: cyclomatic complexity at most 10, Halstead difficulty at most
30, at most 60 lines. Per file: at most 500 lines. Cognitive complexity (at
most 15) is checked by ``complexipy`` against ``complexipy-snapshot.json``
in the same CI job.

Offenders that predate the gate are recorded in
``scripts/complexity_baseline.json``. The baseline may only shrink: a new
offender fails, a recorded one that grows fails, and a recorded one that
improved fails until the baseline is rewritten to the lower number
(``--update``), so every gain is locked in.

Run::

    python scripts/check_complexity.py            # check
    python scripts/check_complexity.py --update   # rewrite the baseline
"""

from __future__ import annotations

import argparse
import ast
import json
from collections.abc import Iterator
from pathlib import Path

from radon.complexity import cc_visit
from radon.metrics import h_visit

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "scripts" / "complexity_baseline.json"
DEFAULT_PATHS = ("pain001_mcp", "scripts", "benches", "examples", "fuzz")
LIMITS = {
    "cyclomatic": 10,
    "halstead_difficulty": 30.0,
    "lines": 60,
    "file_lines": 500,
}

#: ``{"<file>": {"<function or *file*>": {"<metric>": value}}}``
Measures = dict[str, dict[str, dict[str, float]]]


def python_files() -> Iterator[Path]:
    """Every ``.py`` file under the checked paths, in a stable order."""
    for raw in DEFAULT_PATHS:
        path = ROOT / raw
        if path.is_dir():
            yield from sorted(path.rglob("*.py"))


def _function_lines(source: str) -> Iterator[tuple[str, float]]:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = node.end_lineno or node.lineno
            yield node.name, end - node.lineno + 1


def measure(path: Path) -> dict[str, dict[str, float]]:
    """Every metric of ``path`` that is over its limit."""
    source = path.read_text(encoding="utf-8")
    raw: list[tuple[str, str, float]] = [
        ("*file*", "file_lines", len(source.splitlines()))
    ]
    raw += [(b.name, "cyclomatic", b.complexity) for b in cc_visit(source)]
    raw += [
        (name, "halstead_difficulty", round(report.difficulty, 1))
        for name, report in h_visit(source).functions
    ]
    raw += [(name, "lines", n) for name, n in _function_lines(source)]
    over: dict[str, dict[str, float]] = {}
    for name, metric, value in raw:
        if value > LIMITS[metric]:
            entry = over.setdefault(name, {})
            entry[metric] = max(value, entry.get(metric, 0))
    return over


def measure_all() -> Measures:
    """Offenders across every checked file, keyed by relative path."""
    found: Measures = {}
    for path in python_files():
        over = measure(path)
        if over:
            found[path.relative_to(ROOT).as_posix()] = over
    return found


def compare(current: Measures, baseline: Measures) -> list[str]:
    """Every way ``current`` differs from what the baseline allows."""
    problems = []
    keys = {
        (f, n, m)
        for side in (current, baseline)
        for f, names in side.items()
        for n, metrics in names.items()
        for m in metrics
    }
    for file, name, metric in sorted(keys):
        now = current.get(file, {}).get(name, {}).get(metric)
        was = baseline.get(file, {}).get(name, {}).get(metric)
        where = f"{file} {name} {metric}"
        if was is None:
            problems.append(f"{where}: {now} (max {LIMITS[metric]}), new")
        elif now is None or now < was:
            problems.append(f"{where}: improved from {was}; run --update")
        elif now > was:
            problems.append(f"{where}: {now}, worse than baseline {was}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true")
    args = parser.parse_args(argv)
    current = measure_all()
    if args.update:
        BASELINE.write_text(json.dumps(current, indent=2) + "\n")
        print(f"wrote {BASELINE.relative_to(ROOT)}")
        return 0
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    problems = compare(current, baseline)
    for problem in problems:
        print(f"ERROR: {problem}")
    if problems:
        return 1
    print("OK: no new offender, and no baselined offender grew")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
