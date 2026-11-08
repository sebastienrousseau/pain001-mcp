# Copyright (C) 2023-2026 Sebastien Rousseau.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Names an agent reads in a tool description must exist in the core.

An agent copies a scheme profile or a message type out of the tool
descriptions it is shown. A name the core does not know turns into an
"Unknown scheme profile" error on the first call, so every profile a
description or schema names has to resolve against
``pain001.validation.schemes.PROFILES``, and every message type the core
supports is named in ``list_message_types`` by the core's own
``TemplateMetadata.display_name``.
"""

import asyncio
import json
import re

import pytest
from pain001.constants import valid_xml_types
from pain001.templates import DEFAULT_TEMPLATE_REGISTRY
from pain001.validation.schemes import PROFILES

from pain001_mcp import _catalogue, server

# Parameters whose value is a scheme profile name (or a comma-separated
# list of them).
_PROFILE_PARAMETERS = ("scheme", "profile")

# A quoted token in a description: 'name' or ``name``.
_QUOTED = re.compile(r"'([^'\s]+)'|``([^`\s]+)``")

# A token shaped like a scheme profile: lower-case words joined by
# hyphens, as every profile name in PROFILES is.
_PROFILE_SHAPED = re.compile(r"^[a-z]+(?:-[a-z]+)+$")


def _tools() -> list:
    """Return every tool the server registers."""
    return list(asyncio.run(server.server.list_tools()))


def _schema(tool) -> dict:
    """Return a tool's input schema whatever the SDK calls the field."""
    return (
        getattr(tool, "inputSchema", None)
        or getattr(tool, "input_schema", None)
        or {}
    )


def _quoted(text: str) -> set[str]:
    """Return every quoted token in ``text``, splitting comma lists."""
    return {
        name for a, b in _QUOTED.findall(text) for name in (a or b).split(",")
    }


def _profile_parameter_texts() -> list[tuple[str, str, str]]:
    """Return (tool, parameter, schema JSON) for every profile parameter."""
    found = []
    for tool in _tools():
        props = _schema(tool).get("properties", {}) or {}
        for name in _PROFILE_PARAMETERS:
            if name in props:
                found.append((tool.name, name, json.dumps(props[name])))
    return found


def test_profile_parameters_exist():
    """The tools that take a scheme profile are the ones checked below."""
    tools = {tool for tool, _, _ in _profile_parameter_texts()}
    assert {
        "validate_payment_scheme",
        "simulate_payment_batch",
        "stage_payment_batch",
    } <= tools


@pytest.mark.parametrize(
    ("tool", "parameter", "text"),
    _profile_parameter_texts(),
    ids=[f"{tool}.{name}" for tool, name, _ in _profile_parameter_texts()],
)
def test_every_profile_a_parameter_names_exists(tool, parameter, text):
    """A profile parameter's schema names only profiles the core has."""
    named = _quoted(text)
    assert named, f"{tool}.{parameter} names no profile"
    unknown = sorted(named - set(PROFILES))
    assert not unknown, f"{tool}.{parameter} names {unknown}"


def test_validate_payment_scheme_lists_every_profile():
    """The profile parameter offers every profile the core ships."""
    (text,) = [
        text
        for tool, parameter, text in _profile_parameter_texts()
        if (tool, parameter) == ("validate_payment_scheme", "profile")
    ]
    assert set(PROFILES) <= _quoted(text)


def test_every_profile_shaped_name_in_a_description_exists():
    """No tool description or schema quotes a profile that is not real."""
    unknown = set()
    for tool in _tools():
        text = (tool.description or "") + json.dumps(_schema(tool))
        for token in _quoted(text):
            if _PROFILE_SHAPED.match(token) and token not in PROFILES:
                unknown.add((tool.name, token))
    assert not unknown, sorted(unknown)


def test_message_names_come_from_the_core_registry():
    """Each name is the core's ``TemplateMetadata.display_name``."""
    rows = server.list_message_types()
    for row in rows:
        metadata = DEFAULT_TEMPLATE_REGISTRY.get_template(row["message_type"])
        assert row["name"] == metadata.display_name, row


def test_no_hand_written_name_table_remains():
    """The names are not restated here, so they cannot drift."""
    assert not hasattr(_catalogue, "_HUMAN_NAMES")


def test_human_names_carry_the_message_version():
    """Each human name ends in the version its message type carries."""
    families = {
        "pain.001": "Customer Credit Transfer Initiation",
        "pain.008": "Customer Direct Debit Initiation",
    }
    for row in server.list_message_types():
        family, version = row["message_type"].rsplit(".", 1)
        family = family.rsplit(".", 1)[0]
        assert row["name"] == f"{families[family]} V{version}", row


def test_a_type_without_metadata_keeps_its_code(monkeypatch):
    """A type the registry does not describe is named by its code."""

    class _Empty:
        def get_template(self, message_type):
            raise KeyError(message_type)

    monkeypatch.setattr(_catalogue, "DEFAULT_TEMPLATE_REGISTRY", _Empty())
    rows = server.list_message_types()
    assert all(row["name"] == row["message_type"] for row in rows)


def test_list_message_types_never_falls_back_to_the_raw_type():
    """No row of ``list_message_types`` repeats the type as its name."""
    rows = server.list_message_types()
    assert {row["message_type"] for row in rows} == set(valid_xml_types)
    assert all(row["name"] != row["message_type"] for row in rows)
