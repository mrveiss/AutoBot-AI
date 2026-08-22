# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss

"""#14758: every surface that provisions a deployment must provide the envelope root key.

`AUTOBOT_SECRETS_ROOT_KEY` is mandatory for the canonical envelope secret store —
`load_root_key` raises when it is unset — and nothing generated it, so the store
was unreachable on every provisioned deployment. Each consumer swallowed the
failure, which is why an entirely absent store was indistinguishable from "that
secret does not exist".

These assert the *provisioning* surfaces, not the consumers. A test that only
checked the consumers would have passed for the whole time the bug was live.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT_KEY = "AUTOBOT_SECRETS_ROOT_KEY"

# Each surface, and the sibling signing secret that proves the surface really is
# where secrets get provisioned. Pinning the sibling means a file that is
# reorganised out from under this test fails loudly instead of passing empty.
SURFACES = [
    ("docker/secrets-init.sh", "_GEN_SECRET_KEY", "_GEN_SECRETS_ROOT_KEY"),
    ("docker/with-secrets.sh", "SECRET_KEY", ROOT_KEY),
    ("docker/generate-secrets.sh", "AUTOBOT_JWT_SECRET", ROOT_KEY),
    (
        "autobot-slm-backend/ansible/roles/slm_manager/templates/slm-secrets.env.j2",
        "SLM_SECRET_KEY",
        ROOT_KEY,
    ),
    (
        "autobot-slm-backend/ansible/roles/backend/templates/backend.env.j2",
        "AUTOBOT_INTERNAL_API_KEY",
        ROOT_KEY,
    ),
]


@pytest.mark.parametrize("rel,sibling,needle", SURFACES, ids=[s[0] for s in SURFACES])
def test_every_provisioning_surface_provides_the_root_key(rel: str, sibling: str, needle: str) -> None:
    path = REPO_ROOT / rel
    assert path.is_file(), f"{rel} is missing — this guard would otherwise pass vacuously"
    text = path.read_text(encoding="utf-8")
    assert sibling in text, (
        f"{rel} no longer provisions {sibling}, so it may no longer be a secrets "
        "surface at all — re-point this guard rather than deleting it"
    )
    assert needle in text, f"{rel} provisions {sibling} but not {needle} (#14758)"


def test_the_generated_key_decodes_to_the_length_the_loader_demands() -> None:
    """The root key is base64-DECODED and must be exactly 32 bytes.

    This is why it cannot reuse the hex generator the signing secrets use:
    `openssl rand -hex 32` is 64 characters, which decodes to 48 bytes and is
    rejected. Encoding 32 characters yields exactly 32 bytes.
    """

    def decode(text: str) -> bytes:  # mirrors autobot_shared.secrets_envelope._b64d
        stripped = text.rstrip("=")
        return base64.urlsafe_b64decode(stripped + "=" * (-len(stripped) % 4))

    sample = base64.b64encode(b"a" * 32).decode().replace("+", "-").replace("/", "_")
    assert len(decode(sample)) == 32

    # The control: the generator used for the signing secrets must NOT satisfy it.
    hex_style = "0" * 64
    assert len(decode(hex_style)) != 32, "a 64-char hex value must not pass for a root key"


def test_the_ansible_generator_asks_for_the_right_length() -> None:
    """The password lookup must request 32 chars, since b64 of N chars decodes to N bytes."""
    tasks = (
        REPO_ROOT
        / "autobot-slm-backend/ansible/roles/slm_manager/tasks/main.yml"
    ).read_text(encoding="utf-8")
    assert ROOT_KEY in tasks or "autobot_secrets_root_key" in tasks

    # Every generator feeding the root key must be length=32 — a 48-char lookup
    # (the length the sibling secrets use) would decode to 48 bytes and be rejected.
    generators = re.findall(
        r"autobot_secrets_root_key.*?length=(\d+)", tasks, re.DOTALL
    ) + re.findall(r"AUTOBOT_SECRETS_ROOT_KEY=.*?length=(\d+)", tasks)
    assert generators, "found no generator for the root key to check"
    assert set(generators) == {"32"}, f"root key generated at wrong length(s): {set(generators)}"


def test_every_root_key_jinja_expression_compiles() -> None:
    """A nested `{{ }}` inside an open expression is a hard TemplateSyntaxError.

    YAML validity says nothing about Jinja validity, so a task file can parse
    cleanly and still abort at run time. That matters more than it sounds here:
    the generator lives in the same multi-key `set_fact` that produces the SLM's
    signing key, encryption key, admin password and auth token, so one bad
    expression fails all of them on every fresh install.
    """
    jinja2 = pytest.importorskip("jinja2")

    env = jinja2.Environment()  # nosec B701  # compiling only, never rendering untrusted input
    # Filters/lookups Ansible injects that core Jinja does not ship.
    env.filters["b64encode"] = lambda v: v
    env.globals["lookup"] = lambda *a, **k: "x"

    task_files = [
        REPO_ROOT / "autobot-slm-backend/ansible/roles/slm_manager/tasks/main.yml",
        REPO_ROOT / "autobot-slm-backend/ansible/roles/backend/tasks/main.yml",
    ]
    checked = 0
    for path in task_files:
        assert path.is_file(), f"{path} missing — this guard would pass vacuously"
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"\{\{.*?\}\}", text, re.DOTALL):
            expr = match.group(0)
            context = text[max(0, match.start() - 200) : match.end()]
            if ROOT_KEY not in context and "autobot_secrets_root_key" not in context:
                continue
            checked += 1
            try:
                env.compile(expr)
            except jinja2.TemplateSyntaxError as exc:  # pragma: no cover - failure path
                raise AssertionError(f"{path.name}: {exc}\n  {expr[:160]}") from exc

    assert checked >= 3, (
        f"only {checked} root-key expressions found — the extraction missed some, "
        "so a passing result would not mean they are all valid"
    )
