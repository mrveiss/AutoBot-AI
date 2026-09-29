# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One spelling for the TTS worker's address, per side of the boundary (#17782).

Three namings reached the same worker and the drift was invisible until something
failed to connect (#3464 was a port incident on it). The fix is not "one name" --
that would be wrong, and the reason is the useful part:

**A name on both sides of a boundary is not one knob.**

* ``TTS_HOST`` / ``TTS_PORT`` are what the worker **binds** to. They are its own
  interface, written into its env file by its own Ansible role
  (``roles/tts-worker/templates/tts-worker.env.j2``).
* ``AUTOBOT_TTS_WORKER_HOST`` / ``_PORT`` are how **clients find** it, written by
  ``roles/backend/templates/backend.env.j2`` and read by the client that talks to
  the worker.

Renaming the first pair to match the second would break the role's env contract
for no gain -- they look like duplicates in a grep and are not. So the frozen set
below records a **side** for every name, and a new name has to declare which side
it is on, which is the question that stops the next duplicate.

What actually duplicated, recorded here because the code cannot hold it:
``services/service_orchestrator.py`` declared ``AUTOBOT_TTS_HOST``/``_PORT``,
which **nothing in this repository writes** -- no template, env file, compose
file or inventory. So that registry entry always fell through to its own
``default_port=8083`` literal, and the literal became a second source of truth
for a port the canonical pair already carries. It now reads the canonical names,
and the note there is one line because that module sits at its frozen size
ceiling -- which is why the argument lives in this docstring.

The set only shrinks. A new entry means a fourth way to say the same thing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

#: Extensions that can carry an env-var reference. Kept narrow so the walk stays
#: fast; widening it can only find MORE names, which fails loudly rather than
#: silently passing.
#:
#: ``.env`` is NOT in this list, and the reason is the bug review found (#17782):
#: ``Path(".env").suffix`` is ``""`` and ``Path(".env.docker").suffix`` is
#: ``".docker"``, so a suffix entry for ``.env`` matched **no file in this
#: repository at all** -- zero of the nine env files, every one of which is
#: ``.env`` or ``.env.<something>``. The entry was decoration and the file type
#: most likely to hold a deployed override was the one type never scanned.
_SUFFIXES = (".py", ".yml", ".yaml", ".j2", ".ts", ".vue", ".sh", ".md", ".toml", ".cfg")

#: Env files are matched by NAME, because their shape defeats suffix matching.
#: Covers `.env`, `.env.docker`, `.env.example`, and `backend.env`.
_ENV_NAME_PREFIX = ".env"
_ENV_NAME_SUFFIX = ".env"


def _is_scannable(name: str) -> bool:
    """True when a file of this NAME can carry an env-var reference.

    Split out from the walk so the env-file case has a contrast pair: the bug it
    fixes was invisible precisely because nothing exercised the predicate.
    """
    if name == _ENV_NAME_PREFIX or name.startswith(_ENV_NAME_PREFIX + "."):
        return True
    if name.endswith(_ENV_NAME_SUFFIX):
        return True
    return Path(name).suffix in _SUFFIXES


#: An env-var-shaped token naming a TTS address. Broad on the prefix: a future
#: `AUTOBOT_SPEECH_TTS_PORT` is exactly the drift this exists to catch.
_ADDRESS_NAME = r"(?:[A-Z][A-Z0-9]*_)*TTS(?:_[A-Z0-9]+)*_(?:HOST|PORT|URL)"

#: ...but only where it is USED AS AN ENV VAR, which is the actual subject.
#:
#: The first version matched any UPPER_SNAKE token and reported four false
#: positives, every one instructive:
#:
#:   * `TTS_WORKER_HOST = config.tts_worker_host` in `services/tts_client.py` --
#:     a Python constant DERIVED from the SSOT is not a competing spelling of an
#:     env var; it is the canonical value under a local name.
#:   * `TTS_HEALTH_URL = os.getenv("SLM_AGENT_TTS_HEALTH_URL") or ...` -- the
#:     constant is not the name, the quoted argument is.
#:   * this file's own contrast fixture and its own explanatory comment, which is
#:     the "a text detector counts prose about itself" trap in the guard written
#:     to catch drift.
#:
#: So a name counts when it is quoted (`os.getenv("X")`, `alias="X"`,
#: `default_port_env="X"`) or assigned at the start of a line in an env-shaped
#: file (`X=...`). Both are how an env var is actually referenced.
_QUOTED = re.compile(rf"""['"]({_ADDRESS_NAME})(?:=[^'"]*)?['"]""")
_ASSIGNED = re.compile(rf"^\s*({_ADDRESS_NAME})=", re.MULTILINE)

#: Every TTS address env var, with the side of the boundary it belongs to.
#: ONLY SHRINKS.
_ALLOWED = {
    # --- find side: how a client reaches the worker -------------------------
    "AUTOBOT_TTS_WORKER_HOST": "find: canonical client-side host (ssot_config, backend.env.j2)",
    "AUTOBOT_TTS_WORKER_PORT": "find: canonical client-side port (ssot_config, backend.env.j2)",
    "AUTOBOT_TTS_WORKER_URL": "find: the URL projection in the _URL_REGISTRY, one of six siblings",
    # --- bind side: what the worker listens on ------------------------------
    "TTS_HOST": "bind: the worker's own interface, written by tts-worker.env.j2",
    "TTS_PORT": "bind: the worker's own interface, written by tts-worker.env.j2",
    # --- find side, health endpoint -----------------------------------------
    # `os.getenv("SLM_AGENT_TTS_HEALTH_URL") or f"...{get_config().port.tts}/health"`
    # -- an override whose fallback is the SSOT port, so it cannot drift from it.
    "SLM_AGENT_TTS_HEALTH_URL": "find: health-endpoint override, falls back to the SSOT port",
}


def _scanned_files(root: Path) -> list[Path]:
    """Every file this guard reads. The population, so the reach is checkable."""
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or not _is_scannable(path.name):
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith((".git/", "node_modules/")) or "/node_modules/" in rel:
            continue
        # This guard names every spelling it forbids, so scanning itself would
        # report its own record as drift -- and its contrast fixtures as new
        # names. `_ADDRESS_NAME` is exercised directly instead, below.
        if rel == "repo_tests/tts_address_env_names_17782_test.py":
            continue
        files.append(path)
    return files


#: The reach floor, declared as data rather than asserted inside one test
#: (#15826), so `reach_declarations_test.py` can run this discovery against an
#: empty directory and REQUIRE the failure. My first version hand-wrote a
#: non-vacuity check, which proves the population is non-empty today and cannot
#: prove the check would fire if it ever became empty -- that is the difference
#: the mechanism exists for, and the meta-guard caught me not using it.
#:
#: **10,267** files match today -- one fewer than a raw count, because the sweep
#: excludes this file. The floor sits just under that with a growth band rather
#: than far below it: `reach_declarations_test` refuses a floor more than
#: `skips + growth` under the live population, and it is right to. A floor at
#: 6000 (my first attempt) "passes while most of the tree stops being reached",
#: which is the failure a reach floor exists to prevent, dressed as a safety
#: margin. So the band is explicit: 10,000..10,400 needs no action, and beyond
#: that the floor is ratcheted deliberately.
REACH = declare(
    "tts-address-env-name-sweep",
    discover=_scanned_files,
    floor=10000,
    growth=400,
    skips=0,
    what="text files that can carry an env-var reference",
)


def _found_names() -> dict[str, set[str]]:
    """Every TTS address env name in the tree, mapped to the files naming it."""
    root = repo_root()
    found: dict[str, set[str]] = {}
    for path in _scanned_files(root):
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for name in _QUOTED.findall(text) + _ASSIGNED.findall(text):
            found.setdefault(name, set()).add(rel)
    return found


def test_the_walk_finds_the_names_we_know_are_there() -> None:
    """Non-vacuity: a walk that found nothing would make every name below look retired."""
    found = _found_names()
    assert "AUTOBOT_TTS_WORKER_PORT" in found, (
        "the canonical client-side port was not found anywhere, so this guard is scanning "
        f"the wrong tree or the wrong suffixes (found {sorted(found)})"
    )
    assert "TTS_PORT" in found, "the worker's own bind port was not found, same conclusion"


def test_no_fourth_spelling_of_the_tts_address() -> None:
    found = _found_names()
    unexpected = sorted(set(found) - set(_ALLOWED))
    assert not unexpected, (
        "new env-var spelling(s) for the TTS worker address:\n  "
        + "\n  ".join(f"{name} in {sorted(found[name])[:3]}" for name in unexpected)
        + "\n\nThree spellings already drifted apart once (#17782, port incident #3464). "
        "Use the canonical client-side pair, or -- if this really is the worker's own bind "
        "interface -- record it here on the bind side with that reason."
    )


def test_every_allowed_name_declares_which_side_it_is_on() -> None:
    """The record's whole value: a name without a side is the next duplicate."""
    unsided = sorted(name for name, reason in _ALLOWED.items() if not reason.startswith(("find:", "bind:")))
    assert not unsided, "these entries do not say which side of the boundary they serve: " + ", ".join(unsided)


def test_retired_names_are_removed_from_the_record() -> None:
    """Only shrinks, so a name nothing references must not sit here looking live."""
    found = _found_names()
    stale = sorted(set(_ALLOWED) - set(found))
    assert not stale, "recorded TTS address names that no longer appear anywhere -- delete them:\n  " + "\n  ".join(
        stale
    )


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (".env", True),
        (".env.docker", True),
        (".env.example", True),
        ("backend.env", True),
        ("tts-worker.env.j2", True),
        ("config.py", True),
        ("notes.txt", False),
        ("image.png", False),
        ("envelope.pdf", False),
    ],
    ids=[
        "bare-env",
        "env-docker",
        "env-example",
        "prefixed-env",
        "env-template",
        "python",
        "text",
        "binary",
        "endswith-env-but-not-env",
    ],
)
def test_env_files_are_scannable_despite_having_no_usable_suffix(name: str, expected: bool) -> None:
    """The contrast pair for review's finding (#17782).

    `Path(".env").suffix` is `""` and `Path(".env.docker").suffix` is
    `".docker"`, so the original suffix tuple's `".env"` entry matched **zero**
    of this repository's nine env files. The guard's population silently excluded
    the file type most likely to carry a deployed override, and nothing failed --
    because no test exercised the predicate, only the walk's result.

    `envelope.pdf` is the negative that stops `endswith(".env")` from being a
    substring test.
    """
    assert _is_scannable(name) is expected


def test_the_walk_actually_reaches_an_env_file() -> None:
    """The predicate being right is not the same as the walk using it."""
    root = repo_root()
    names = {p.name for p in _scanned_files(root)}
    env_files = {n for n in names if n == ".env" or n.startswith(".env.") or n.endswith(".env")}
    assert env_files, (
        "no env file was reached by the walk, though this repository tracks nine -- the "
        "predicate and the walk have come apart"
    )


def test_the_detector_would_catch_a_new_prefix() -> None:
    """Contrast pair: prove the pattern is not pinned to the spellings that exist."""
    assert _ASSIGNED.findall("AUTOBOT_SPEECH" + "_TTS_PORT=8083") == ["AUTOBOT_SPEECH_TTS_PORT"]
    assert _QUOTED.findall('os.getenv("AUTOBOT_NEW' + '_TTS_HOST")') == ["AUTOBOT_NEW_TTS_HOST"]
    assert _QUOTED.findall('x = "AUTOBOT_TTS' + '_MODELS_DIR"') == [], "only HOST/PORT/URL are addresses"
    # A Python constant is not an env name, which is the false positive that
    # made the first version of this detector unusable.
    assert _QUOTED.findall("TTS_WORKER" + "_PORT = config.tts_worker_port") == []
    assert _ASSIGNED.findall("TTS_WORKER" + "_PORT = config.tts_worker_port") == []
