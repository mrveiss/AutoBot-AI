# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""`_resolve_env_path` must resolve to a FILE, never a directory (#12782).

The fallback branch used to return the base directory, because the `/ ".env"`
join had been absorbed into a trailing comment:

    fallback = Path(
        os.environ.get("AUTOBOT_BASE_DIR", "/opt/autobot")
    )  # ssot-config-exempt: bootstrap before config available / ".env"
    return fallback

`_parse_env_file` then hit `IsADirectoryError`, swallowed it into an empty dict
(its `except OSError` path), and every SSOT key was reported missing. A live
host showed "194 drifted, (194 SSOT keys, 0 .env keys)" while its `.env` held
93 keys — the drift report was an artefact, not a measurement.
"""

import pathlib

from autobot_shared import env_drift_detector as det


def test_explicit_path_is_used_verbatim(tmp_path):
    target = tmp_path / ".env"
    target.write_text("A=1\n", encoding="utf-8")

    assert det._resolve_env_path(str(target)) == target.resolve()


def test_resolved_path_is_always_an_env_file(monkeypatch, tmp_path):
    """The invariant that actually matters: never hand a directory to the parser."""
    monkeypatch.setenv("AUTOBOT_BASE_DIR", str(tmp_path))
    monkeypatch.setattr(pathlib.Path, "exists", lambda self: False)

    resolved = det._resolve_env_path(None)

    assert resolved.name == ".env", f"resolved to {resolved}, which is not a .env file"


def test_fallback_appends_env_to_the_base_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTOBOT_BASE_DIR", str(tmp_path))
    monkeypatch.setattr(pathlib.Path, "exists", lambda self: False)

    assert det._resolve_env_path(None) == tmp_path / ".env"


def test_parser_on_a_directory_yields_nothing(tmp_path):
    """Guards the swallow: a directory must not silently parse as zero keys.

    This is the behaviour that turned a path bug into a plausible-looking
    "194 keys drifted" report, so it is pinned deliberately.
    """
    assert det._parse_env_file(tmp_path) == {}


def test_parser_reads_a_real_env_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text('# c\nA=1\nB="two"\nC=3 # trailing\n\n', encoding="utf-8")

    assert det._parse_env_file(env) == {"A": "1", "B": "two", "C": "3"}
