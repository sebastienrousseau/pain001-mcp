# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Tests for ``list_scheme_profiles``.

The tool lists the scheme profiles the core ships, so an agent can pick
one before it calls ``validate_payment_scheme``. Every field comes from
the core: the names from ``PROFILES``, the descriptions from the scheme
plugin registry, and the rule prefix and sources from the rail or
purpose mandate behind a profile. Nothing is restated here.
"""

from __future__ import annotations

import asyncio

from pain001.plugins import registry
from pain001.validation.rails import PurposeMandate, rail
from pain001.validation.schemes import PROFILES

import pain001_mcp.server as server
from pain001_mcp import _schemes


def _by_name() -> dict[str, dict]:
    """Return the listed profiles keyed by name."""
    return {p["name"]: p for p in server.list_scheme_profiles()["profiles"]}


def test_lists_every_core_profile_in_order() -> None:
    """One entry per profile in ``PROFILES``, sorted, with the count."""
    result = server.list_scheme_profiles()
    names = [p["name"] for p in result["profiles"]]
    assert names == sorted(PROFILES)
    assert result["count"] == len(PROFILES)


def test_every_entry_has_exactly_the_documented_keys() -> None:
    """name, description, rule_prefix and sources; nothing else."""
    for entry in server.list_scheme_profiles()["profiles"]:
        assert set(entry) == {"name", "description", "rule_prefix", "sources"}


def test_descriptions_come_from_the_plugin_registry() -> None:
    """The description is the one ``pain001 plugins list`` shows."""
    for name, entry in _by_name().items():
        expected = registry.get_scheme(name).meta.description
        assert entry["description"] == expected
        assert entry["description"], name


def test_a_rail_profile_names_its_rule_prefix_and_sources() -> None:
    """A rail reports the prefix of its rule ids and its documents."""
    entry = _by_name()["uk-fps"]
    assert entry["rule_prefix"] == rail("uk-fps").prefix == "UK-FPS"
    assert entry["sources"] == list(rail("uk-fps").sources)
    assert entry["sources"]


def test_a_purpose_mandate_names_its_sources() -> None:
    """A purpose mandate has no rail prefix, but cites its documents."""
    name = next(
        n for n, p in PROFILES.items() if isinstance(p, PurposeMandate)
    )
    entry = _by_name()[name]
    assert entry["rule_prefix"] is None
    assert entry["sources"] == list(PROFILES[name].sources)
    assert entry["sources"]


def test_a_built_in_rulebook_has_no_prefix_or_sources() -> None:
    """The SEPA rulebooks share rule ids, so no prefix is claimed."""
    entry = _by_name()["sepa-sct"]
    assert entry["rule_prefix"] is None
    assert entry["sources"] == []


def test_a_profile_without_a_registered_plugin_has_no_description(
    monkeypatch,
) -> None:
    """A profile the registry does not list (disabled) is still named."""
    monkeypatch.setattr(_schemes.scheme_registry, "get_scheme", lambda n: None)
    entries = server.list_scheme_profiles()["profiles"]
    assert {e["description"] for e in entries} == {""}


def test_the_tool_is_registered_read_only() -> None:
    """It is listed with the pure-read annotations."""
    tools = {t.name: t for t in asyncio.run(server.server.list_tools())}
    # by_alias reads the camelCase names on both SDK majors.
    hints = tools["list_scheme_profiles"].annotations.model_dump(by_alias=True)
    assert hints["readOnlyHint"] is True
    assert hints["openWorldHint"] is False
