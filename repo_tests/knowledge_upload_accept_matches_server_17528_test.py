# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The upload picker offers exactly what the endpoint accepts (#17528).

`KnowledgeUpload.vue` carried its own copy of the allow-list, and the copy had
drifted from the server's in **both** directions at once:

* offered and refused -- ``.doc``, ``.yaml``, ``.yml``, ``.xml``. The picker
  invited a file, the user waited for the upload, and the endpoint answered 400.
* accepted and hidden -- all five office types. #16775 added ``.xlsx``,
  ``.pptx``, ``.odt``, ``.ods`` and ``.odp`` server-side and the picker never
  learned, so a supported format looked unsupported.

Neither direction announces itself, which is why a guard and not a comment: the
two lists live in different languages in different trees, and every previous
attempt to keep them in step was a person remembering to.

Both sides are read as **text**, never imported. Importing the backend module
would execute the application, and `check_python_file_size.py`'s lesson applies
here too -- a check that needs the app running is a check that quietly stops
running.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

_BACKEND = Path("autobot-backend/api/knowledge.py")
_OFFICE = Path("autobot-backend/api/knowledge_office_upload.py")
_CONSTANTS = Path("autobot-frontend/src/constants/knowledgeUpload.ts")
_COMPONENT = Path("autobot-frontend/src/components/knowledge/KnowledgeUpload.vue")


def _read(relative: Path) -> str:
    path = repo_root() / relative
    assert path.is_file(), f"{relative} has moved; this guard reads it by path"
    return path.read_text(encoding="utf-8")


def _python_set_literal(source: str, name: str) -> set[str]:
    """The string members of a module-level ``name = {...}`` assignment.

    Parsed rather than regexed so a reformat, a line wrap or a trailing comment
    cannot make a populated set read as an empty one -- an empty set here would
    make every comparison below pass vacuously.
    """
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id != name:
            continue
        # `ALLOWED_EXTENSIONS = {...} | OFFICE_EXTENSIONS` is a BinOp whose left
        # side is the literal; the right side is resolved by the caller.
        value = node.value.left if isinstance(node.value, ast.BinOp) else node.value
        members = ast.literal_eval(value)
        assert isinstance(members, (set, frozenset)), f"{name} is no longer a set literal"
        return {str(m) for m in members}
    raise AssertionError(f"{name} not found as a module-level assignment")


def _ts_string_array(source: str, name: str) -> list[str]:
    """The string members of an exported ``const name ... = [...]`` array."""
    match = re.search(rf"export const {re.escape(name)}\b[^=]*=\s*(\[.*?\])", source, re.DOTALL)
    assert match, f"{name} not found as an exported array in {_CONSTANTS}"
    # The array is a list of single-quoted literals; JSON wants double quotes,
    # and trailing commas are not valid JSON.
    body = re.sub(r",(\s*\])", r"\1", match.group(1).replace("'", '"'))
    members = json.loads(body)
    assert members, f"{name} parsed as empty, which would pass every check below"
    return [str(m) for m in members]


def _ts_int(source: str, name: str) -> int:
    match = re.search(rf"export const {re.escape(name)}\b[^=]*=\s*(\d+)", source)
    assert match, f"{name} not found as an exported number in {_CONSTANTS}"
    return int(match.group(1))


def _python_int(source: str, name: str) -> int:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id == name:
                return int(ast.literal_eval(node.value))
    raise AssertionError(f"{name} not found as a module-level assignment")


@pytest.fixture(scope="module")
def server_extensions() -> set[str]:
    allowed = _python_set_literal(_read(_BACKEND), "ALLOWED_EXTENSIONS")
    office = _python_set_literal(_read(_OFFICE), "OFFICE_EXTENSIONS")
    return allowed | office


@pytest.fixture(scope="module")
def client_extensions() -> list[str]:
    return _ts_string_array(_read(_CONSTANTS), "KNOWLEDGE_UPLOAD_EXTENSIONS")


class TestTheTwoListsAgree:
    def test_the_client_offers_nothing_the_server_refuses(self, server_extensions, client_extensions):
        offered_and_refused = sorted(set(client_extensions) - server_extensions)
        assert not offered_and_refused, (
            "the picker offers extensions the endpoint rejects with 400 after the upload: " f"{offered_and_refused}"
        )

    def test_the_client_hides_nothing_the_server_accepts(self, server_extensions, client_extensions):
        accepted_and_hidden = sorted(server_extensions - set(client_extensions))
        assert not accepted_and_hidden, (
            "the endpoint accepts extensions the picker does not offer, so a supported "
            f"format looks unsupported: {accepted_and_hidden}"
        )

    def test_the_size_limits_agree(self):
        server_mb = _python_int(_read(_BACKEND), "MAX_FILE_SIZE_MB")
        client_mb = _ts_int(_read(_CONSTANTS), "KNOWLEDGE_UPLOAD_MAX_MB")
        assert client_mb == server_mb, (
            f"the client rejects at {client_mb}MB and the server at {server_mb}MB; "
            "whichever is larger sends a file that cannot succeed"
        )


class TestTheGuardIsMeasuringSomething:
    """A comparison of two empty sets passes. These pin the populations."""

    def test_the_server_list_is_populated(self, server_extensions):
        assert len(server_extensions) >= 12, f"read only {len(server_extensions)} server extensions"
        # Named so a parse that silently returns a different set still fails.
        assert {".pdf", ".docx", ".xlsx", ".odp"} <= server_extensions

    def test_the_client_list_is_populated(self, client_extensions):
        assert len(client_extensions) >= 12, f"read only {len(client_extensions)} client extensions"

    def test_every_entry_is_a_lowercase_dotted_suffix(self, client_extensions):
        # The server compares against os.path.splitext(filename.lower())[1], so an
        # entry without a dot or with a capital can never match and is dead weight.
        bad = [e for e in client_extensions if not e.startswith(".") or e != e.lower()]
        assert not bad, f"entries the server can never match: {bad}"


class TestTheComponentActuallyUsesThem:
    """The lists can agree perfectly while the component consults neither."""

    def test_the_component_imports_the_shared_constants(self):
        source = _read(_COMPONENT)
        assert "@/constants/knowledgeUpload" in source, (
            "KnowledgeUpload.vue no longer imports the shared list, so this guard "
            "is comparing the server against a file nothing reads"
        )

    def test_the_component_holds_no_second_copy_of_the_list(self):
        source = _read(_COMPONENT)
        # A re-introduced local array is how this drifted the first time.
        for name in ("SUPPORTED_EXTENSIONS", "MAX_FILE_SIZE"):
            assert (
                f"const {name}" not in source
            ), f"{name} is defined locally again; the shared constant is the one the guard checks"

    def test_the_accept_attribute_is_bound_not_hardcoded(self):
        source = _read(_COMPONENT)
        assert 'accept=".' not in source, (
            "the file input hardcodes an accept list again; bind KNOWLEDGE_UPLOAD_ACCEPT "
            "so it cannot drift from the server"
        )
