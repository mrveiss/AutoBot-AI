# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``SecretModel`` can express the ownership a caller sent (#13051).

``SecretCreateRequest`` has declared ``owner_id``/``org_id``/``team_ids``/
``shared_with`` since #685 while ``SecretModel`` declared none of the four and
``to_secret_model()`` copied none of them — so a caller set ownership, got 200
back, and the body said nothing about it.

**The second half matters more than the first.** These values are *self
asserted*: they arrive in the request body and are never resolved from the
authenticated principal. Persisting them is only safe while nothing authorizes
on them — the legacy file store gates on ``scope``/``chat_id`` alone. That is
not a property prose can hold, because the day someone writes
``if user_id in secret["shared_with"]`` the stored value becomes a privilege
claim its own subject wrote. So it is a test: ``TestNothingAuthorizesOnThem``
fails the moment a read path consults one of the four, which is the signal to
resolve them from the caller first (#16450, umbrella #10088).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from api.schemas_system import ChatSecretScope, SecretCreateRequest, SecretModel, StorableSecretType

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SECRETS_API = _REPO_ROOT / "autobot-backend" / "api" / "secrets.py"
_SCHEMAS = _REPO_ROOT / "autobot-backend" / "api" / "schemas_system.py"

#: The four fields, named here so every assertion below reports its selector.
OWNERSHIP_FIELDS = ("owner_id", "org_id", "team_ids", "shared_with")

#: The store whose access decision is `scope`/`chat_id`.
_STORE_CLASS = "SecretsManager"

#: Its read/mutate paths. Scoped to the class on purpose and the scoping is
#: load-bearing: `api/secrets.py` also defines module-level route handlers of
#: the same four names, and *those* legitimately bind `owner_id` — to the
#: **authenticated caller** (`str((_user or {}).get("user_id"))`), not to the
#: stored row\'s self-asserted field. A guard over the whole module reports
#: those and reads as a breach; a guard over the class answers the question
#: actually being asked. The exclusion is written here rather than left as the
#: absence of a line.
_ACCESS_CONTROLLED_METHODS = ("get_secret", "list_secrets", "update_secret", "delete_secret")


def _declared_fields(source: str, class_name: str) -> set[str]:
    """Annotated class-level field names of *class_name*, from the AST."""
    node = next(
        (n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.ClassDef) and n.name == class_name),
        None,
    )
    assert node is not None, f"{class_name} is gone — re-point this guard, do not delete it"
    return {
        statement.target.id
        for statement in node.body
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name)
    }


class TestTheModelCanExpressOwnership:
    def test_secret_model_declares_all_four(self):
        declared = _declared_fields(_SCHEMAS.read_text(encoding="utf-8"), "SecretModel")
        missing = [name for name in OWNERSHIP_FIELDS if name not in declared]
        assert missing == [], f"SecretModel still drops {missing}"

    def test_the_request_still_declares_them(self):
        """The positive control for the reader above: it finds a known case."""
        declared = _declared_fields(_SCHEMAS.read_text(encoding="utf-8"), "SecretCreateRequest")
        assert [name for name in OWNERSHIP_FIELDS if name not in declared] == []

    def test_what_a_caller_sent_survives_the_conversion(self):
        request = SecretCreateRequest(
            name="deploy-key",
            type=StorableSecretType.API_KEY,
            scope=ChatSecretScope.GENERAL,
            value="v",
            owner_id="u-1",
            org_id="org-9",
            team_ids=["t-1", "t-2"],
            shared_with=["u-2"],
        )
        secret = request.to_secret_model()
        assert secret.owner_id == "u-1"
        assert secret.org_id == "org-9"
        assert secret.team_ids == ["t-1", "t-2"]
        assert secret.shared_with == ["u-2"]

    def test_a_caller_who_sent_nothing_gets_empty_not_missing(self):
        secret = SecretCreateRequest(
            name="k", type=StorableSecretType.API_KEY, scope=ChatSecretScope.GENERAL, value="v"
        ).to_secret_model()
        assert secret.owner_id is None and secret.org_id is None
        assert secret.team_ids == [] and secret.shared_with == []

    def test_a_stored_row_without_the_fields_still_parses(self):
        """`update_secret` rebuilds a SecretModel from rows written before this."""
        assert SecretModel(name="k", type=StorableSecretType.API_KEY, scope=ChatSecretScope.GENERAL).shared_with == []


def _names_referenced_in(source: str, method_names: tuple[str, ...], class_name: str | None = None) -> set[str]:
    """Every identifier and string literal used inside the named methods.

    Strings count because the store is dict-backed: ``secret_data["owner_id"]``
    is an authorization read even though ``owner_id`` is never an attribute.
    Comments and docstrings do not count — that is the point of using the AST,
    and ``test_prose_naming_a_field_does_not_trip_the_guard`` proves it.
    """
    tree: ast.AST = ast.parse(source)
    if class_name is not None:
        tree = next(
            (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == class_name),
            None,
        )
        assert tree is not None, f"{class_name} is gone — re-point this guard, do not delete it"
    found: set[str] = set()
    _names_referenced_in.reached = set()  # type: ignore[attr-defined]
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name not in method_names:
            continue
        _names_referenced_in.reached.add(node.name)  # type: ignore[attr-defined]
        body = node.body[1:] if ast.get_docstring(node) else node.body
        for inner in [child for statement in body for child in ast.walk(statement)]:
            if isinstance(inner, ast.Name):
                found.add(inner.id)
            elif isinstance(inner, ast.Attribute):
                found.add(inner.attr)
            elif isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                found.add(inner.value)
    return found


_CONTRAST_FIXTURE = '''
class SecretsManager:
    def get_secret(self, secret_id, chat_id=None):
        """Get a secret with access control.

        Ownership (owner_id, org_id, team_ids, shared_with) is not consulted:
        see #13051. A future change could gate on shared_with here.
        """
        # shared_with / team_ids are stored but never read
        secret_data = self._load_secrets().get(secret_id)
        if secret_data["scope"] == "chat" and secret_data["chat_id"] != chat_id:
            raise PermissionError("denied")
        return secret_data
'''

_POSITIVE_FIXTURE = """
class SecretsManager:
    def get_secret(self, secret_id, chat_id=None, user_id=None):
        secret_data = self._load_secrets().get(secret_id)
        if user_id not in secret_data["shared_with"]:
            raise PermissionError("denied")
        return secret_data
"""


class TestNothingAuthorizesOnThem:
    def test_the_detector_finds_a_real_authorization_read(self):
        """Known positive: without this the empty result below means nothing."""
        found = _names_referenced_in(_POSITIVE_FIXTURE, ("get_secret",))
        assert "shared_with" in found

    def test_prose_naming_a_field_does_not_trip_the_guard(self):
        """All four names appear — in a docstring and a comment only."""
        for name in OWNERSHIP_FIELDS:
            assert name in _CONTRAST_FIXTURE
        assert _names_referenced_in(_CONTRAST_FIXTURE, ("get_secret",)) & set(OWNERSHIP_FIELDS) == set()

    def test_the_legacy_store_s_access_paths_consult_none_of_the_four(self):
        """If this fails, resolve the fields from the caller before gating on them.

        Self-asserted ownership that decides access is a privilege claim written
        by its own subject. Adding the gate is the right direction — it just
        needs #16450's server-side resolution landed first.
        """
        referenced = _names_referenced_in(
            _SECRETS_API.read_text(encoding="utf-8"), _ACCESS_CONTROLLED_METHODS, _STORE_CLASS
        )
        reached = _names_referenced_in.reached  # type: ignore[attr-defined]
        assert reached == set(_ACCESS_CONTROLLED_METHODS), (
            f"{_STORE_CLASS} no longer has {sorted(set(_ACCESS_CONTROLLED_METHODS) - reached)} — "
            "the selector has drifted and an empty result below would mean nothing"
        )
        offending = sorted(referenced & set(OWNERSHIP_FIELDS))
        assert offending == [], f"{offending} now gates access in {_ACCESS_CONTROLLED_METHODS}"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__]))
