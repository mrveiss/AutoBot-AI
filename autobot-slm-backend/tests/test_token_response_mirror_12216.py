# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#12216: the SLM login TokenResponse must expose the JWT under BOTH
`access_token` (its native field) and `token` (the core backend's field) so a
client written against either backend reads the token correctly.

The root conftest stubs ``models.schemas`` with a MagicMock and the module uses
package-relative imports, so the real class cannot be imported standalone here.
Assert structurally (via AST) that TokenResponse declares a ``token`` field and
a mirror validator. (Runtime mirror behaviour is covered for the equivalent
core LoginResponse in autobot-backend/api/login_response_mirror_12216_test.py,
which the core conftest does not stub.)"""

import ast
from pathlib import Path

_SCHEMAS = Path(__file__).resolve().parents[1] / "models" / "schemas.py"


def _token_response_class() -> ast.ClassDef:
    tree = ast.parse(_SCHEMAS.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "TokenResponse":
            return node
    raise AssertionError("TokenResponse class not found in models/schemas.py")


def test_token_response_declares_both_token_fields():
    cls = _token_response_class()
    fields = {n.target.id for n in cls.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)}
    assert "access_token" in fields
    assert "token" in fields, "#12216: TokenResponse must also expose `token`"


def test_token_response_has_mirror_validator():
    cls = _token_response_class()
    src = ast.get_source_segment(_SCHEMAS.read_text(encoding="utf-8"), cls) or ""
    assert "model_validator" in src
    assert "self.token = self.access_token" in src, "#12216: `token` must mirror `access_token`"
