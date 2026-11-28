# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A snapshot made by the SLM's own snapshot script restores on a fixture store (#18281).

The script text is read out of ``autobot-slm-backend/services/secrets_store_snapshot.py`` and run exactly
as the SLM sends it, so this tests the code path the backup uses, not a copy of it. The artifact
is ciphertext only: it opens and decrypts with the SAME key, and does not with a different one.
"""

from __future__ import annotations

import ast
import base64
import os
import subprocess
import sys
from pathlib import Path

import pytest

from services.secrets_service import SecretsService

SLM_MODULE = Path(__file__).resolve().parents[2] / "autobot-slm-backend" / "services" / "secrets_store_snapshot.py"
PLAINTEXT = "hunter2-fixture-value"


def _snapshot_script() -> str:
    tree = ast.parse(SLM_MODULE.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "_SNAPSHOT_SCRIPT" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("_SNAPSHOT_SCRIPT is gone from the SLM secrets backup module")


def _key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


@pytest.fixture
def snapshot(tmp_path):
    key = _key()
    live = tmp_path / "secrets.db"
    store = SecretsService(db_path=str(live), encryption_key=key)
    created = store.create_secret("api-token", "api_key", PLAINTEXT)
    copy = tmp_path / "snapshot.db"
    done = subprocess.run([sys.executable, "-c", _snapshot_script(), str(live)], capture_output=True, check=False)
    assert done.returncode == 0, done.stderr
    copy.write_bytes(done.stdout)
    return key, created["id"], copy, live


def test_the_snapshot_restores_and_decrypts_with_the_same_key(snapshot):
    key, secret_id, copy, _ = snapshot
    restored = SecretsService(db_path=str(copy), encryption_key=key)
    assert restored.get_secret(secret_id=secret_id, include_value=True)["value"] == PLAINTEXT


def test_a_different_key_does_not_decrypt_it(snapshot):
    _, secret_id, copy, _ = snapshot
    other = SecretsService(db_path=str(copy), encryption_key=_key())
    with pytest.raises(Exception):
        other.get_secret(secret_id=secret_id, include_value=True)


def test_the_artifact_holds_no_plaintext_and_no_key(snapshot):
    key, _, copy, _ = snapshot
    raw = copy.read_bytes()
    assert PLAINTEXT.encode() not in raw and key.encode() not in raw


def test_a_missing_source_fails_instead_of_minting_an_empty_store(tmp_path):
    done = subprocess.run(
        [sys.executable, "-c", _snapshot_script(), str(tmp_path / "absent.db")],
        capture_output=True,
        check=False,
    )
    assert done.returncode != 0 and not done.stdout and not (tmp_path / "absent.db").exists()
