# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Real-load the SLM ``models.*`` schema modules the root conftest must not stub.

Split out of ``conftest.py`` to keep it under the 600-line cap (#21026). Loaded
by path from the root conftest, which is where ``sys.modules["models"]`` stub
is installed first; ``load_real_model_schemas`` then binds the real modules.
"""

import sys
from pathlib import Path

_SLM_ROOT = Path(__file__).resolve().parents[1]


def load_real_model_schemas() -> None:
    """Bind the real schema modules onto the stubbed ``models`` package."""
    # #13139: models/schemas_secrets.py must be REAL, not stubbed. It carries
    # response_model classes, and FastAPI rejects a MagicMock as a response field
    # ("Invalid args for response field!") the moment a test builds the app. It
    # imports only pydantic, so loading it by path is safe -- this deliberately
    # bypasses models/__init__.py, which is what the stubs above exist to avoid.
    _schemas_secrets_path = _SLM_ROOT / "models" / "schemas_secrets.py"
    if not _schemas_secrets_path.is_file():
        raise RuntimeError("conftest: models/schemas_secrets.py is named here but does not exist")
    import importlib.util as _ss_importlib_util

    _ss_spec = _ss_importlib_util.spec_from_file_location("models.schemas_secrets", _schemas_secrets_path)
    _ss_mod = _ss_importlib_util.module_from_spec(_ss_spec)
    _ss_spec.loader.exec_module(_ss_mod)
    sys.modules["models.schemas_secrets"] = _ss_mod
    setattr(sys.modules["models"], "schemas_secrets", _ss_mod)

    # #16281: models/npu_schemas.py and models/gpu_schemas.py are REAL for the same
    # reason -- services/node_gpu.py builds pydantic responses from them, and a
    # MagicMock model validates nothing. Both import only pydantic; gpu_schemas also
    # imports npu_schemas, hence the order and the sys.modules entry before exec.
    for _schema in ("npu_schemas", "gpu_schemas", "post_sync_schemas", "rollback_schemas"):
        _schema_path = _SLM_ROOT / "models" / f"{_schema}.py"
        _schema_spec = _ss_importlib_util.spec_from_file_location(f"models.{_schema}", _schema_path)
        _schema_mod = _ss_importlib_util.module_from_spec(_schema_spec)
        sys.modules[f"models.{_schema}"] = _schema_mod
        _schema_spec.loader.exec_module(_schema_mod)
        setattr(sys.modules["models"], _schema, _schema_mod)

    # #15495: models/node_capability.py is REAL for a different reason than the
    # pair above -- it declares a SQLAlchemy Core Table, not a Pydantic model, and
    # services/node_capability.py needs its real columns (``.c.node_id`` etc.) to
    # build meaningful insert/update/select statements. It imports only
    # sqlalchemy, which is already stubbed harmlessly above (attribute access on
    # the stub auto-vivifies rather than raising).
    _ncap_path = _SLM_ROOT / "models" / "node_capability.py"
    _ncap_spec = _ss_importlib_util.spec_from_file_location("models.node_capability", _ncap_path)
    _ncap_mod = _ss_importlib_util.module_from_spec(_ncap_spec)
    sys.modules["models.node_capability"] = _ncap_mod
    _ncap_spec.loader.exec_module(_ncap_mod)
    setattr(sys.modules["models"], "node_capability", _ncap_mod)
