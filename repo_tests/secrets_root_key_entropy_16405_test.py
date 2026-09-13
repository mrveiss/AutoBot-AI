# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#16405 — every root-key generator must draw from a byte-level random source.

Before this issue, two of the three generators for ``AUTOBOT_SECRETS_ROOT_KEY``
picked 32 random **characters** from a fixed alphabet and then base64-encoded
that ASCII string:

* the Ansible ``slm_manager`` role used
  ``lookup('password', '/dev/null length=32 chars=ascii_letters,digits')``
  (62 characters, ~5.95 bits each — ~190 bits total), and
* ``docker/secrets-init.sh``'s ``gen_b64_32`` used
  ``tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32`` before piping to ``base64``
  (the same 62-character alphabet).

Both shapes decode back to exactly 32 bytes, so ``autobot_shared.secrets_envelope
.load_root_key`` — which only checks the decoded length — could not tell a weak
key from a strong one. ``docker/generate-secrets.sh`` was already correct
(``openssl rand -base64 32``, reading the 32 bytes directly off the OS CSPRNG),
which is why ``repo_tests/secrets_root_key_provisioned_test.py`` — which only
ever asked "is *a* value provisioned, of the right decoded length" — passed the
whole time the other two were weak.

This file pins the *source* of the randomness, not just its decoded length:
each generator's own text must show a byte-level source (``openssl rand`` or
``secrets.token_bytes``) and must not show a character-class source (an
Ansible ``password`` lookup, or a ``tr -dc`` filter applied before the random
bytes are consumed). The detector is exercised against both shapes directly
(the planted self-tests below), so a detector that stops matching either one
fails loudly here instead of the per-file tests reading clean by accident.

Existing keys are never rotated by this change (#16406 tracks fleet rotation
separately) — these tests only cover what a *new* key is generated from.
"""

from __future__ import annotations

import re

import pytest
from repo_tests._paths import repo_root

REPO_ROOT = repo_root()

# (file, anchor) for every known generator of AUTOBOT_SECRETS_ROOT_KEY. The
# anchor pins a window of the file to the generator expression itself, not
# just any mention of the key name — autobot_shared/secrets_envelope.py's
# docstring mentions the name without generating anything, and a window
# anchored there would test nothing.
GENERATOR_SITES = [
    (
        "autobot-slm-backend/ansible/roles/slm_manager/tasks/main.yml",
        "autobot_secrets_root_key:",
    ),
    (
        "autobot-slm-backend/ansible/roles/slm_manager/tasks/main.yml",
        "AUTOBOT_SECRETS_ROOT_KEY={{",
    ),
    ("docker/generate-secrets.sh", "b64_32)"),
    ("docker/secrets-init.sh", "gen_b64_32() {"),
]

# Wide enough to hold a full lookup()/openssl invocation after the anchor,
# narrow enough that an unrelated task/function below it cannot leak in.
_WINDOW = 320

# A byte-level random source: `secrets.token_bytes`, `openssl rand` reading
# straight off the OS CSPRNG, or a fixed byte count read directly off
# /dev/urandom with nothing narrowing it in between (docker/secrets-init.sh's
# `gen_b64_32` avoids an openssl dependency on purpose — see its own header).
# None of the three restricts the value range of a byte.
_BYTE_SOURCE = re.compile(r"secrets\.token_bytes\(|openssl rand\b|head -c \d+ /dev/urandom\b")

# A character-class source: an Ansible `password` lookup draws from a fixed
# alphabet (letters/digits), and a `tr -dc` filter applied ahead of the random
# bytes discards every byte outside its class before anything downstream ever
# sees it. Both under-fill the entropy a "32 bytes" claim implies.
_CHARACTER_CLASS_SOURCE = re.compile(r"lookup\(\s*['\"]password['\"]|tr\s+-dc\b")


def is_byte_random_source(snippet: str) -> bool:
    """Whether *snippet* reads like a byte-level random source (#16405).

    A character-class marker anywhere in the snippet disqualifies it outright
    — a generator that both filters to a character class AND happens to
    mention ``openssl rand`` nearby (in a comment, say) is not a fix, so this
    checks the disqualifier first rather than requiring its absence only when
    no byte marker is found.
    """
    if _CHARACTER_CLASS_SOURCE.search(snippet):
        return False
    return bool(_BYTE_SOURCE.search(snippet))


def _window(text: str, anchor: str) -> str:
    idx = text.find(anchor)
    assert idx != -1, f"anchor {anchor!r} not found — the generator moved or was renamed"
    return text[idx : idx + _WINDOW]


@pytest.mark.parametrize(
    "rel,anchor",
    GENERATOR_SITES,
    ids=[f"{rel}::{anchor}" for rel, anchor in GENERATOR_SITES],
)
def test_each_generator_uses_a_byte_level_random_source(rel: str, anchor: str) -> None:
    path = REPO_ROOT / rel
    assert path.is_file(), f"{rel} is missing — this guard would otherwise pass vacuously"
    text = path.read_text(encoding="utf-8")
    snippet = _window(text, anchor)
    assert is_byte_random_source(snippet), (
        f"{rel} ({anchor!r}) does not read as a byte-level random source (#16405) "
        f"— it must use openssl rand / secrets.token_bytes, not a character-class "
        f"password lookup or a tr -dc filter ahead of the random bytes:\n{snippet}"
    )


# Planted self-test: the two BAD snippets are the actual pre-fix generator text
# this issue replaced (quoted verbatim, not paraphrased), and the two GOOD
# snippets are the actual post-fix text. Without this, "the detector rejects
# character-class sources" is only ever exercised by files that already pass
# — which proves the files are fixed, not that the detector could still catch
# a regression.
_PLANTED_BAD_ANSIBLE = (
    "AUTOBOT_SECRETS_ROOT_KEY={{ (lookup('password', '/dev/null length=32 "
    "chars=ascii_letters,digits') | b64encode) | replace('+', '-') | replace('/', '_') }}"
)
_PLANTED_BAD_SHELL = "tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32 | base64 | tr '+/' '-_'"
_PLANTED_GOOD_ANSIBLE = (
    "AUTOBOT_SECRETS_ROOT_KEY={{ lookup('pipe', 'openssl rand -base64 32') | "
    "replace('+', '-') | replace('/', '_') }}"
)
_PLANTED_GOOD_SHELL = "head -c 32 /dev/urandom | base64 | tr '+/' '-_' | tr -d '\\n'"
_PLANTED_GOOD_PYTHON = "base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()"


@pytest.mark.parametrize(
    "snippet",
    [_PLANTED_BAD_ANSIBLE, _PLANTED_BAD_SHELL],
    ids=["pre-fix-ansible-password-lookup", "pre-fix-shell-tr-dc-filter"],
)
def test_the_detector_rejects_the_actual_pre_fix_generators(snippet: str) -> None:
    assert not is_byte_random_source(snippet)


@pytest.mark.parametrize(
    "snippet",
    [_PLANTED_GOOD_ANSIBLE, _PLANTED_GOOD_SHELL, _PLANTED_GOOD_PYTHON],
    ids=["post-fix-ansible-openssl-pipe", "post-fix-shell-urandom-base64", "byte-random-python-control"],
)
def test_the_detector_accepts_a_byte_level_source(snippet: str) -> None:
    assert is_byte_random_source(snippet)


def test_the_character_class_check_does_not_fire_on_unrelated_tr_usage() -> None:
    """The contrast for `tr -dc`: a plain alphabet *translation* is not a filter.

    `openssl rand -base64 32 | tr '+/' '-_'` (used by every fixed generator
    here) maps the base64 OUTPUT alphabet to url-safe — it does not delete any
    byte from a random stream, so it must not trip the same detector as
    `tr -dc ... </dev/urandom`.
    """
    assert is_byte_random_source("openssl rand -base64 32 | tr '+/' '-_'")
