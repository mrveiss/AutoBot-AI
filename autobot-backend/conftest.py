"""
AutoBot User Backend - Test Configuration
Provides pytest fixtures for colocated tests.

Issue: #734 - Colocate tests with source files
AutoBot - AI-Powered Automation Platform
Copyright (c) 2025 mrveiss
Author: mrveiss
"""

import asyncio
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure autobot-backend and autobot_shared are importable
project_root = Path(__file__).parent.parent
backend_root = Path(__file__).parent
shared_root = project_root / "autobot_shared"
sys.path.insert(0, str(project_root))
# Insert shared_root before backend_root so that backend_root ends up at
# position 0 (highest priority).  This ensures bare `models.*` imports in
# autobot-backend code resolve to autobot-backend/models/, not the similarly-
# named package in autobot_shared/.
sys.path.insert(0, str(shared_root))
sys.path.insert(0, str(backend_root))


def _make_pkg_stub(name: str) -> types.ModuleType:
    """Create a minimal package stub that Python's import machinery accepts.

    A bare MagicMock() cannot serve as a package because the importer
    requires ``__path__`` to be set for submodule resolution (e.g. when the
    code does ``from sqlalchemy.dialects.postgresql import ARRAY``).  We
    create a real ModuleType with ``__path__ = []`` so the dotted import chain
    succeeds while leaving every attribute access as a MagicMock via
    ``__getattr__``.
    """
    mod = types.ModuleType(name)
    mod.__path__ = []  # marks this as a package to the import system
    mod.__package__ = name
    mock_attr = MagicMock()

    def _getattr(attr: str) -> MagicMock:  # noqa: ANN001
        return mock_attr

    mod.__getattr__ = _getattr  # type: ignore[attr-defined]
    sys.modules[name] = mod
    return mod


# Stub optional heavy dependencies that may not be installed in the dev venv.
# These are only needed at runtime on the target VM; tests use mocks.
# Simple (leaf) modules that don't need submodule resolution:
_SIMPLE_STUBS = [
    "prometheus_client",
    "xxhash",
    "torch",
    "torch.nn",
    "torch.cuda",
    "asyncpg",
    "psycopg2",
    "alembic",
]
for _mod in _SIMPLE_STUBS:
    if _mod not in sys.modules:
        try:
            import importlib

            importlib.import_module(_mod)
        except ImportError:
            sys.modules[_mod] = MagicMock()

# Celery stub — issue #4455. When celery isn't installed in the dev venv,
# provide a tiny shim so modules that do ``@celery_app.task`` import cleanly.
# The real package is used on production nodes; tests never rely on Beat.
try:
    import celery as _celery_real  # noqa: F401
except ImportError:
    _celery_stub = types.ModuleType("celery")

    class _StubCelery:
        def __init__(self, *args, **kwargs) -> None:
            self.conf = types.SimpleNamespace(
                update=lambda **_k: None,
                beat_schedule={},
            )

        def task(self, *_args, **_kwargs):
            def decorator(fn):
                fn.update_state = lambda *a, **k: None
                return fn

            return decorator

        def autodiscover_tasks(self, *_args, **_kwargs) -> None:
            return None

    _celery_stub.Celery = _StubCelery
    sys.modules["celery"] = _celery_stub

    _schedules_stub = types.ModuleType("celery.schedules")

    class _StubCrontab:
        def __init__(self, **fields) -> None:
            def _parse(v):
                try:
                    return {int(v)}
                except (TypeError, ValueError):
                    return set()

            self.minute = _parse(fields.get("minute", 0))
            self.hour = _parse(fields.get("hour", 0))

    _schedules_stub.crontab = _StubCrontab
    sys.modules["celery.schedules"] = _schedules_stub

# Package stubs for SQLAlchemy and alembic sub-packages (need __path__ so
# dotted sub-module imports like ``sqlalchemy.dialects.postgresql`` resolve).
_PKG_STUBS = [
    "sqlalchemy",
    "sqlalchemy.ext",
    "sqlalchemy.ext.asyncio",
    "sqlalchemy.orm",
    "sqlalchemy.orm.declarative",
    "sqlalchemy.dialects",
    "sqlalchemy.dialects.postgresql",
    "sqlalchemy.types",
    "sqlalchemy.engine",
    "sqlalchemy.pool",
    "sqlalchemy.sql",
    "sqlalchemy.sql.sqltypes",
    "alembic.op",
    "alembic.context",
]
for _pkg in _PKG_STUBS:
    try:
        import importlib as _il

        _il.import_module(_pkg)
    except ImportError:
        if _pkg not in sys.modules:
            _make_pkg_stub(_pkg)

# Fix metaclass conflict (#4300): when SQLAlchemy is not installed the stubs
# above make sqlalchemy.orm a MagicMock namespace module.  Every attribute
# access returns the same MagicMock instance, so ``DeclarativeBase`` becomes a
# MagicMock *instance*.  Inheriting from a MagicMock instance gives the
# subclass metaclass ``MagicMock`` (not ``type``).  Then any model that does
# ``class Foo(SomePlainMixin, DeclarativeBase)`` raises:
#   TypeError: metaclass conflict: the metaclass of a derived class must be a
#   (non-strict) subclass of the metaclasses of all its bases
# because ``MagicMock`` and ``type`` are incompatible metaclasses.
#
# Fix: patch the ORM stub so that ``DeclarativeBase`` and
# ``declarative_base`` are real Python classes/callables that produce
# ``type``-metaclassed base classes.  All other ORM attributes remain as
# MagicMock so the rest of the stub still works.
#
# Detection: real sqlalchemy.orm is a real ModuleType whose __dict__ contains
# the actual class objects; our stub's __dict__ only has __getattr__ and a few
# dunder attrs.  Check isinstance to distinguish a real module from the stub.
if "sqlalchemy.orm" in sys.modules:
    _orm_mod = sys.modules["sqlalchemy.orm"]
    # The stub module has __getattr__ set on the module object directly; real
    # sqlalchemy.orm does not.  Use that as the distinguishing signal.
    _is_stub = "__getattr__" in vars(_orm_mod)
    if _is_stub:

        class _DeclarativeBase:
            """Minimal SQLAlchemy DeclarativeBase stub with correct metaclass."""

            type_annotation_map: dict = {}

        def _declarative_base(**kwargs):
            """Minimal declarative_base() stub that returns a type-metaclassed class."""
            return _DeclarativeBase

        _orm_mod.DeclarativeBase = _DeclarativeBase  # type: ignore[attr-defined]
        _orm_mod.declarative_base = _declarative_base  # type: ignore[attr-defined]

# Pre-register models.infrastructure directly so that ``from models.infrastructure
# import ...`` succeeds without triggering models/__init__.py (which requires the
# full SQLAlchemy stack that is not installed in the dev/CI venv).
# This must run AFTER the sqlalchemy stubs above so that any subsequent import of
# models/__init__.py itself (if forced by other test files) has sqlalchemy stubs
# already in place.
if "models" not in sys.modules:
    import importlib.util as _ilu

    _infra_path = str(backend_root / "models" / "infrastructure.py")
    _spec = _ilu.spec_from_file_location("models.infrastructure", _infra_path)
    if _spec and _spec.loader:
        # Create a lightweight 'models' namespace package to hold the sub-module
        _models_pkg = _make_pkg_stub("models")
        _models_pkg.__path__ = [str(backend_root / "models")]
        _infra_mod = _ilu.module_from_spec(_spec)
        _infra_mod.__package__ = "models"
        sys.modules["models.infrastructure"] = _infra_mod
        _spec.loader.exec_module(_infra_mod)  # type: ignore[union-attr]
        setattr(_models_pkg, "infrastructure", _infra_mod)


# -- Requirements.txt enforcement (Issue #5032) ----------------------------
# Tests that use optional parsers like bs4 declare `pytest.importorskip(...)`
# so they skip gracefully. But a silent skip of ~10% of the suite looks like
# a passing run to an inattentive reviewer. This session hook reads
# requirements.txt and reports which declared deps are not importable, so the
# developer sees a clear "run pip install -r requirements.txt" hint at the
# top of every test run instead of silent skip messages buried further down.

# Map PyPI distribution names to their importable module name when they differ.
_DIST_TO_MODULE = {
    "beautifulsoup4": "bs4",
    "PyYAML": "yaml",
    "pyyaml": "yaml",
    "pillow": "PIL",
    "opencv-python": "cv2",
    "scikit-learn": "sklearn",
    "python-dotenv": "dotenv",
    "python-multipart": "multipart",
    "python-dateutil": "dateutil",
    "python-jose": "jose",
}


def _parse_requirements(path: Path) -> list[str]:
    """Return package names declared in a requirements.txt file."""
    names: list[str] = []
    if not path.exists():
        return names
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip().split("#", 1)[0].strip()
        if not line or line.startswith("-"):  # skip comments, blanks, -r/-e flags
            continue
        # Strip version specifiers and extras
        for sep in ("==", ">=", "<=", "~=", ">", "<", "!=", "["):
            if sep in line:
                line = line.split(sep, 1)[0].strip()
        if line:
            names.append(line)
    return names


def pytest_report_header(config) -> list[str]:
    """Report missing requirements.txt deps in the pytest session header.

    Does NOT fail the session — stubs in this conftest and `pytest.importorskip`
    calls in test files still handle graceful degradation. Purpose is to
    surface the root cause when tests silently skip due to missing deps.
    """
    import importlib.util

    req_file = backend_root / "requirements.txt"
    declared = _parse_requirements(req_file)
    if not declared:
        return []

    missing: list[str] = []
    for dist in declared:
        module = _DIST_TO_MODULE.get(dist.lower(), dist.replace("-", "_"))
        try:
            if importlib.util.find_spec(module) is None:
                missing.append(dist)
        except (ImportError, ValueError):
            missing.append(dist)

    if not missing:
        return [f"requirements.txt: all {len(declared)} deps importable"]

    preview = ", ".join(missing[:8]) + ("..." if len(missing) > 8 else "")
    return [
        f"requirements.txt: {len(missing)}/{len(declared)} deps NOT installed ({preview})",
        "    Run: pip install -r autobot-backend/requirements.txt",
        "    Tests using these deps will skip; see importorskip messages below.",
    ]


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_data_dir() -> Path:
    """Get test data directory."""
    return Path(__file__).parent / "tests" / "fixtures" / "data"


@pytest.fixture
def temp_dir(tmp_path) -> Path:
    """Provide temporary directory for test files."""
    return tmp_path


@pytest.fixture(autouse=True)
def set_test_environment():
    """
    Set TEST environment variables for all tests.
    Prevents tests from affecting production data.
    """
    original_env = dict(os.environ)

    os.environ["AUTOBOT_TEST_MODE"] = "true"
    os.environ["AUTOBOT_ENV"] = "test"

    yield

    os.environ.clear()
    os.environ.update(original_env)
