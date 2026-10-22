# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Run the Atheris harness on fixed inputs, where Atheris cannot run.

Atheris ships Linux x86_64 wheels only, so the fuzz workflow is the only
place the harness runs coverage-guided. This drives the same
``test_one_input`` with seeded inputs through a minimal stand-in for
``atheris.FuzzedDataProvider``, so a harness that no longer matches the
tool signatures fails here, on every platform, rather than first in the
fuzz job.
"""

from __future__ import annotations

import contextlib
import importlib.util
import random
import sys
import types
from collections.abc import Iterator
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[1] / "fuzz" / "fuzz_tools.py"


class _Provider:
    """The subset of FuzzedDataProvider the harness uses, seeded by data."""

    def __init__(self, data: bytes) -> None:
        self._rng = random.Random(data)

    def ConsumeIntInRange(self, low: int, high: int) -> int:
        return self._rng.randint(low, high)

    def ConsumeInt(self, size: int) -> int:
        bound = 2 ** (8 * size - 1)
        return self._rng.randint(-bound, bound - 1)

    def ConsumeBool(self) -> bool:
        return self._rng.random() < 0.5

    def ConsumeUnicodeNoSurrogates(self, count: int) -> str:
        length = self._rng.randint(0, count)
        points = [self._rng.choice((0x20, 0x7E, 0xE9, 0x2603, 0x0))]
        points += [self._rng.randint(0x20, 0x2FFF) for _ in range(length)]
        return "".join(chr(p) for p in points if not 0xD800 <= p <= 0xDFFF)

    def PickValueInList(self, values: list[object]) -> object:
        return self._rng.choice(values)


@contextlib.contextmanager
def _instrument_imports() -> Iterator[None]:
    yield


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    """The harness module, with the stand-in when Atheris is absent."""
    if importlib.util.find_spec("atheris") is None:
        stub = types.ModuleType("atheris")
        stub.FuzzedDataProvider = _Provider
        stub.instrument_imports = _instrument_imports
        monkeypatch.setitem(sys.modules, "atheris", stub)
    spec = importlib.util.spec_from_file_location("fuzz_tools", HARNESS)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("seed", range(40))
def test_harness_accepts_seeded_inputs(
    harness: types.ModuleType, seed: int
) -> None:
    """No tool raises or returns a non-container on a seeded input."""
    harness.test_one_input(seed.to_bytes(4, "little") * 8)
