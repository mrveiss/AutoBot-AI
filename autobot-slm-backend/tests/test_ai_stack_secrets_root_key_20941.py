# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20941: every service env that opens the secrets store gets the ONE root key, the same way.

The ai-stack imports the envelope store but its env template carried no root key, so every
System-vault read in that process was refused. Templates are parsed (Jinja AST), never grepped
for a value: the key must come from the canonical variable, and only when it is set.
"""

from pathlib import Path

import pytest
import yaml
from jinja2 import ChainableUndefined, Environment, meta

_ANSIBLE = Path(__file__).resolve().parents[1] / "ansible"
_ROLES = _ANSIBLE / "roles"
_VAR = "AUTOBOT_SECRETS_ROOT_KEY"
_CANONICAL = "autobot_secrets_root_key"
#: Services whose process opens the envelope store (autobot_shared.secrets_envelope).
_STORE_TEMPLATES = ("backend/templates/backend.env.j2", "ai-stack/templates/ai-stack.env.j2")
_ENV = Environment(undefined=ChainableUndefined)
_ENV.filters["dirname"] = lambda value: str(value).rsplit("/", 1)[0]


def _root_key_lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip().startswith(f"{_VAR}=")]


def _rendered_lines(rel: str, **context) -> list[str]:
    template = _ENV.from_string((_ROLES / rel).read_text(encoding="utf-8"))
    return _root_key_lines(template.render(**context))


def _value_variables(line: str) -> set[str]:
    return meta.find_undeclared_variables(_ENV.parse(line.split("=", 1)[1]))


@pytest.mark.parametrize("rel", _STORE_TEMPLATES)
def test_store_template_renders_the_canonical_variable(rel: str) -> None:
    source = (_ROLES / rel).read_text(encoding="utf-8")
    lines = _root_key_lines(source)
    assert len(lines) == 1, f"{rel} must render {_VAR} exactly once"
    assert _value_variables(lines[0]) == {_CANONICAL}, f"{rel} takes the key from another source"
    assert "{{" in lines[0], f"{rel} hardcodes the key"


def test_every_template_that_renders_the_key_is_a_known_store_consumer() -> None:
    found = {
        str(p.relative_to(_ROLES))
        for p in _ROLES.glob("*/templates/*.j2")
        if _root_key_lines(p.read_text(encoding="utf-8"))
    }
    allowed = set(_STORE_TEMPLATES) | {"slm_manager/templates/slm-secrets.env.j2"}
    assert found <= allowed, f"unregistered root-key render: {sorted(found - allowed)}"


def test_the_rendered_ai_stack_env_carries_the_key_when_set() -> None:
    rel = "ai-stack/templates/ai-stack.env.j2"
    assert _rendered_lines(rel, **{_CANONICAL: "k-test"}) == [f"{_VAR}=k-test"]


def test_ai_stack_omits_the_key_when_unset() -> None:
    """Contrast: with no key the line is absent, never an empty `AUTOBOT_SECRETS_ROOT_KEY=`."""
    rel = "ai-stack/templates/ai-stack.env.j2"
    assert _rendered_lines(rel, **{_CANONICAL: ""}) == []
    assert _rendered_lines(rel) == []


def test_detector_flags_a_template_with_a_second_source() -> None:
    """Contrast: the variable check fails on a key read from anywhere but the canonical variable."""
    assert _value_variables(f"{_VAR}={{{{ some_other_key }}}}") != {_CANONICAL}
    assert _value_variables(f"{_VAR}=abc123") != {_CANONICAL}


def test_ai_stack_reads_the_key_from_the_slm_file_before_rendering() -> None:
    tasks = yaml.safe_load((_ROLES / "ai-stack/tasks/env_files.yml").read_text(encoding="utf-8"))
    order = [
        str(t.get("ansible.builtin.include_tasks") or t.get("ansible.builtin.template") or t.get("name")) for t in tasks
    ]  # an include with `apply:` is a dict whose repr still names the file
    read = next(i for i, v in enumerate(order) if "read_slm_secrets_root_key.yml" in v)
    rendered = next(
        i for i, t in enumerate(tasks) if t.get("ansible.builtin.template", {}).get("src") == "ai-stack.env.j2"
    )
    assert read < rendered
    shared = yaml.safe_load((_ANSIBLE / "_shared/tasks/read_slm_secrets_root_key.yml").read_text(encoding="utf-8"))
    assert all(t.get("no_log") is True for t in shared if "command" in str(t) or "set_fact" in str(t))
    assert (
        next(t for t in shared if "ansible.builtin.stat" in t).get("delegate_to") == "localhost"
    ), "the SLM's file is read on the SLM host"
