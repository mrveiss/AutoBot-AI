#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Generate frontend TypeScript types from canonical Python dataclasses.

#7122: minimal codegen pipeline. Walks the dataclass field types of
selected canonical classes (curated via MANIFEST below) and emits the
matching TypeScript interface declarations. The output file is checked
into the repo; a CI step re-runs this script and fails if the generated
output drifts from the committed file.

Why this matters
----------------
Without codegen, every backend dataclass change must be mirrored by hand
in the frontend type file. #7044 documented exactly this drift: the
frontend `TemplateStep` interface had only 2 of 7 fields actually
matching what `/api/templates` emits, and the gap survived 18 months
because v-if defaults masked the missing fields. Codegen makes drift
impossible to introduce silently.

Scope
-----
Initial: the canonical workflow shapes from `autobot_shared.workflow`:
  - PromptSpec
  - ExecutionStrategy (enum → string union)
  - WorkflowTask
  - WorkflowPlan

Future iterations can extend MANIFEST without changing the codegen logic.

Const maps (#16491)
-------------------
MANIFEST emits types; a type union cannot carry runtime values. CONST_MANIFEST
emits module-level *dicts* as typed TypeScript ``const`` maps -- the backend's
role -> permission grants and role priorities -- so the frontend's permission
sets and role ranking are generated from the backend instead of hand-copied.

Output
------
`autobot-frontend/src/types/_generated/workflow.ts` — committed to the
repo so consumers import a stable path. CI re-generates and diffs.

Usage
-----
  python3 autobot-infrastructure/shared/scripts/gen_frontend_types.py
  python3 autobot-infrastructure/shared/scripts/gen_frontend_types.py --check
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib.util
import sys
import types
import typing
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Set, Tuple, Union, get_args, get_origin

# PEP 604 `X | Y` unions have origin ``types.UnionType`` (py3.10+), which is a
# distinct object from ``typing.Union``. ``get_type_hints`` may return either
# form depending on the interpreter version, so both must be treated as unions
# for deterministic output across Python 3.10 … 3.14.
_UNION_ORIGINS = (Union, getattr(types, "UnionType", Union))


def _ts_array(inner: str) -> str:
    """Render ``inner[]`` but parenthesize a union member so ``X | null`` becomes
    ``(X | null)[]`` — otherwise TS parses ``X | null[]`` as ``X | (null[])`` (#11020)."""
    return f"({inner})[]" if "|" in inner else f"{inner}[]"


def _is_optional(annotation: object) -> bool:
    """True when *annotation* is a union that admits ``None`` (Optional[...])."""
    return get_origin(annotation) in _UNION_ORIGINS and type(None) in get_args(annotation)


REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
OUTPUT_PATH = REPO_ROOT / "autobot-frontend" / "src" / "types" / "_generated" / "workflow.ts"


# ---------------------------------------------------------------------------
# Manifest — extend this to add more dataclasses to the codegen
# ---------------------------------------------------------------------------

# Each entry: (module path, attr name)
#
# How to extend (#7226 cookbook):
#
#   1. Identify the canonical Python source. For dataclasses this is a
#      `@dataclass`; for enums this is a `class X(Enum):` or
#      `class X(str, Enum):`. Pydantic models are NOT supported — convert
#      to a dataclass first or wait for OpenAPI-based codegen (deferred).
#
#   2. Append `(module_path, ClassName)` to MANIFEST below. The module
#      must be importable from the repo root with `autobot_shared/` and
#      `autobot-backend/` on sys.path.
#
#   3. Re-run codegen and commit the regenerated TS:
#        python3 autobot-infrastructure/shared/scripts/gen_frontend_types.py
#
#   4. Update frontend imports to consume from `@/types/_generated/workflow`
#      (re-export from `@/types/workflowTemplates` if a stable public path
#      is preferred).
#
#   5. CI's `frontend-codegen-drift` job will fail if the committed file
#      drifts from the source.
# Each entry: (relative file path from repo root, class name).
# Using file paths (not module paths) lets us load source files directly
# via spec_from_file_location, bypassing package `__init__.py` chains
# that would pull in heavyweight runtime deps (aiohttp, pydantic, etc.).
# CI runs in a slim Python-only environment without those deps installed.
MANIFEST: List[Tuple[str, str]] = [
    ("autobot_shared/workflow/types.py", "PromptSpec"),
    ("autobot_shared/workflow/types.py", "ExecutionStrategy"),
    ("autobot_shared/workflow/types.py", "WorkflowTask"),
    ("autobot_shared/workflow/types.py", "WorkflowPlan"),
    # #7226: extend MANIFEST to cover hand-written types prone to drift
    ("autobot-backend/services/workflow_automation/models.py", "WorkflowStepStatus"),
    ("autobot_shared/status_enums.py", "Severity"),  # exported as RiskLevel via alias below
    # #14937: the canonical role vocabulary, so the frontend role unions derive
    # from it instead of three hand-maintained copies drifting apart.
    ("autobot_shared/auth/permissions.py", "Role"),
    # #16243: the canonical permission vocabulary. usePermissions.ts hand-rolled
    # its own `users:read`-style strings that shared nothing with these
    # `admin.users.read`-style ones -- a control could be shown to a role the
    # backend refuses, or hidden from one it would allow.
    ("autobot_shared/auth/permissions.py", "Permission"),
]


# Aliases emitted alongside their backing class — TypeScript can't have
# two type names point at the same union literal without a duplication,
# so we emit `export type RiskLevel = Severity;` after the source class.
# Map: source class name → list of alias names to emit.
ALIASES: Dict[str, List[str]] = {
    "Severity": ["RiskLevel"],
}


class ConstMap(NamedTuple):
    """A module-level dict emitted as a typed TypeScript ``const`` map (#16491).

    A NamedTuple, not a dataclass: ``repo_tests/gen_frontend_types_test.py``
    loads this file without registering it in ``sys.modules``, and a dataclass
    under ``from __future__ import annotations`` resolves its field types
    through ``sys.modules[cls.__module__]``.
    """

    source: str  # file path from the repo root
    attr: str  # the dict's name in that module
    ts_name: str  # the exported TS const
    key_type: str  # TS type of the keys (a generated union's name)
    value_type: str  # TS type of each value
    field: Optional[str] = None  # when set, emit each value's ``[field]`` rather than the value


# #16491: the runtime values a union cannot carry. usePermissions.ts and
# constants/roles.ts used to hand-copy both maps; generated, a grant or a
# priority changed on the backend reaches the frontend with the next run.
CONST_MANIFEST: List[ConstMap] = [
    ConstMap(
        "autobot_shared/auth/permissions.py", "ROLE_PERMISSIONS", "ROLE_PERMISSIONS", "Role", "readonly Permission[]"
    ),
    ConstMap("autobot_shared/auth/permissions.py", "_ROLE_META", "ROLE_PRIORITY", "Role", "number", "priority"),
]


def _load_module_from_path(file_path: Path, module_name: str) -> Any:
    """Load a Python source file as a standalone module by file path.

    Uses ``importlib.util.spec_from_file_location`` so the loader skips
    the parent-package import chain (e.g. ``services/__init__.py``
    pulling in ``aiohttp``). The module is registered under a synthetic
    ``codegen_<basename>`` name so subsequent imports referenced by the
    target file's own ``from ... import ...`` statements still resolve
    via the normal sys.path search.
    """
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Could not load source file: {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _ensure_autobot_shared_on_path() -> None:
    """Set up sys.path so target source files can resolve their internal
    imports.

    autobot_shared modules import each other via ``from autobot_shared.X``
    (parent dir must be on path). autobot-backend modules use bare imports
    like ``from type_defs.common import Metadata`` (autobot-backend itself
    must be on path). We add both. Crucially, neither addition triggers a
    package __init__.py — sys.path entries are only consulted when an
    import statement runs inside a target file."""
    shared = REPO_ROOT / "autobot_shared"
    if str(shared.parent) not in sys.path:
        sys.path.insert(0, str(shared.parent))
    backend = REPO_ROOT / "autobot-backend"
    if backend.is_dir() and str(backend) not in sys.path:
        sys.path.insert(0, str(backend))


def _load_source(rel_file_path: str, loaded_modules: Dict[str, Any]) -> Any:
    """Load *rel_file_path* once per run, so every manifest entry naming it
    shares one module load (and one execution of that module's side effects)."""
    if rel_file_path not in loaded_modules:
        abs_path = REPO_ROOT / rel_file_path
        if not abs_path.is_file():
            raise SystemExit(f"Source file not found: {rel_file_path}")
        # Synthetic module name avoids colliding with anything sys.path
        # might also surface as `autobot_shared.workflow.types` etc.
        synth_name = "codegen_" + rel_file_path.replace("/", "_").replace(".", "_")
        loaded_modules[rel_file_path] = _load_module_from_path(abs_path, synth_name)
    return loaded_modules[rel_file_path]


def _display_module(rel_file_path: str) -> str:
    """The dotted module path a generated comment shows for *rel_file_path*.

    autobot-backend/services/X/Y.py → services.X.Y;
    autobot_shared/workflow/types.py → autobot_shared.workflow.types.
    """
    return rel_file_path.removeprefix("autobot-backend/").removesuffix(".py").replace("/", ".")


# ---------------------------------------------------------------------------
# Type translation
# ---------------------------------------------------------------------------

PRIMITIVE_MAP: Dict[type, str] = {
    str: "string",
    int: "number",
    float: "number",
    bool: "boolean",
    type(None): "null",
}


def _ts_type(py_type: Any, known_names: Set[str]) -> str:
    """Translate a Python annotation to a TypeScript type expression."""
    if py_type is type(None):
        return "null"

    if py_type in PRIMITIVE_MAP:
        return PRIMITIVE_MAP[py_type]

    # Forward references emitted by `from __future__ import annotations`
    # arrive as strings.
    if isinstance(py_type, str):
        # If it's a known canonical name, use it; otherwise fall back to unknown.
        return py_type if py_type in known_names else "unknown"

    if isinstance(py_type, typing.ForwardRef):
        name = py_type.__forward_arg__
        return name if name in known_names else "unknown"

    if isinstance(py_type, type) and issubclass(py_type, Enum):
        # Enum → string union of its values
        return " | ".join(f"'{m.value}'" for m in py_type)

    if dataclasses.is_dataclass(py_type):
        return py_type.__name__

    origin = get_origin(py_type)
    args = get_args(py_type)

    if origin in _UNION_ORIGINS:
        # Handle Optional[X] = Union[X, None] and PEP 604 `X | None` specially
        non_none = [a for a in args if a is not type(None)]
        rendered = " | ".join(_ts_type(a, known_names) for a in non_none)
        if type(None) in args:
            rendered = f"{rendered} | null"
        return rendered

    if origin in (list, List):
        inner = _ts_type(args[0], known_names) if args else "unknown"
        return _ts_array(inner)

    if origin in (dict, Dict):
        if not args:
            return "Record<string, unknown>"
        # Always emit Record<string, V> — the key type is required
        # to be string-compatible for JSON serialization.
        v = _ts_type(args[1], known_names)
        return f"Record<string, {v}>"

    if origin in (set, Set, frozenset):
        inner = _ts_type(args[0], known_names) if args else "unknown"
        return _ts_array(inner)

    if origin is tuple:
        inner = ", ".join(_ts_type(a, known_names) for a in args) if args else "unknown"
        return f"[{inner}]"

    if py_type is Any:
        return "unknown"

    # Bare (unsubscripted) containers — no origin/args but a real type. Render the
    # collection shape rather than falling through to "unknown" (#11020), so
    # ``Optional[dict]`` becomes ``Record<string, unknown> | null`` etc.
    if py_type is dict:
        return "Record<string, unknown>"
    if py_type in (list, set, frozenset):
        return "unknown[]"
    if py_type is tuple:
        return "unknown[]"

    # Last resort — emit the type name and let TypeScript flag it
    name = getattr(py_type, "__name__", None) or repr(py_type)
    return name if name in known_names else "unknown"


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def _render_enum(cls: type, source: str) -> str:
    """Emit a TypeScript string union for a Python Enum."""
    members = [f"  | '{m.value}'" for m in cls]
    body = "\n".join(members)
    return f"/** Generated from `{source}.{cls.__name__}` */\n" f"export type {cls.__name__} =\n{body};\n"


def _render_alias(name: str, target: str, source_cls: str) -> str:
    """Emit a TypeScript type alias re-exporting an existing union."""
    return (
        f"/** Generated alias — same union as `{source_cls}` (#6689 / #7226) */\n" f"export type {name} = {target};\n"
    )


def _render_dataclass(cls: type, known_names: Set[str], source: str) -> str:
    """Emit a TypeScript interface for a Python dataclass."""
    type_hints = typing.get_type_hints(cls, include_extras=False)
    lines = [
        f"/** Generated from `{source}.{cls.__name__}` */",
        f"export interface {cls.__name__} {{",
    ]
    for f in dataclasses.fields(cls):
        annotation = type_hints.get(f.name, f.type)
        ts = _ts_type(annotation, known_names)
        # A field whose annotation admits ``None`` (``Optional[X]`` / ``X | None``)
        # is not required at construction and is serialized as ``null`` when
        # unset — emit ``field?: T`` so consumers need not supply it. Non-nullable
        # fields stay required so the wire schema remains exact.
        opt = "?" if _is_optional(annotation) else ""
        lines.append(f"  {f.name}{opt}: {ts};")
    lines.append("}\n")
    return "\n".join(lines)


def _render_class(cls: type, known_names: Set[str], display_module: str) -> List[str]:
    """The TS parts for one MANIFEST class: its union or interface, then any aliases."""
    if isinstance(cls, type) and issubclass(cls, Enum):
        parts = [_render_enum(cls, display_module)]
    elif dataclasses.is_dataclass(cls):
        parts = [_render_dataclass(cls, known_names, display_module)]
    else:
        raise SystemExit(f"Unsupported class kind: {cls!r}")
    parts.extend(_render_alias(alias, cls.__name__, cls.__name__) for alias in ALIASES.get(cls.__name__, []))
    return parts


def _unescaped(text: str) -> str:
    """*text*, unless it would need escaping inside a single-quoted TS string -- the renderer does not escape."""
    if "'" in text or "\\" in text:
        raise SystemExit(f"Const-map string needs escaping, which the renderer does not do: {text!r}")
    return text


def _ts_key(key: object) -> str:
    """A TS object key: an Enum member's value or a str, bare when an identifier, else single-quoted."""
    text = key.value if isinstance(key, Enum) else key
    if not isinstance(text, str):
        raise SystemExit(f"Unsupported const-map key: {key!r}")
    return text if text.isidentifier() else f"'{_unescaped(text)}'"


def _ts_literal(value: object) -> str:
    """A TS literal for one const-map value: a string (or a str Enum's value), a number or a boolean."""
    if isinstance(value, Enum):
        value = value.value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return f"'{_unescaped(value)}'"
    raise SystemExit(f"Unsupported const-map value: {value!r}")


def _project(value: object, spec: ConstMap) -> object:
    """*value* itself, or its ``spec.field`` entry when the manifest asks for one."""
    if spec.field is None:
        return value
    if not isinstance(value, dict) or spec.field not in value:
        raise SystemExit(f"{spec.source}::{spec.attr} value has no field {spec.field!r}: {value!r}")
    return value[spec.field]


def _render_const_entry(key: object, value: object) -> List[str]:
    """The lines for one ``key: value`` entry; a list renders one element per line, in its own order."""
    ts_key = _ts_key(key)
    if isinstance(value, (list, tuple)):
        if not value:
            return [f"  {ts_key}: [],"]
        return [f"  {ts_key}: [", *(f"    {_ts_literal(v)}," for v in value), "  ],"]
    return [f"  {ts_key}: {_ts_literal(value)},"]


def _render_const_map(spec: ConstMap, mapping: object, display_module: str) -> str:
    """Emit a typed TS ``const`` map for a module-level dict, entries in the dict's own order (#16491)."""
    if not isinstance(mapping, dict):
        raise SystemExit(f"{spec.source}::{spec.attr} is not a dict: {type(mapping).__name__}")
    field_note = f" (field `{spec.field}`)" if spec.field else ""
    lines = [
        f"/** Generated from `{display_module}.{spec.attr}`{field_note} */",
        f"export const {spec.ts_name}: Readonly<Record<{spec.key_type}, {spec.value_type}>> = {{",
    ]
    for key, value in mapping.items():
        lines.extend(_render_const_entry(key, _project(value, spec)))
    lines.append("};\n")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

HEADER = """// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// AUTO-GENERATED — DO NOT EDIT
//
// Source: autobot-infrastructure/shared/scripts/gen_frontend_types.py
// Run `python3 autobot-infrastructure/shared/scripts/gen_frontend_types.py`
// to regenerate. CI checks this file is in sync with the canonical
// Python dataclasses in `autobot_shared/workflow/types.py` (#7122).

/* eslint-disable */
"""


def generate() -> str:
    """Run both manifests and produce the full TS output as a string."""
    _ensure_autobot_shared_on_path()
    loaded_modules: Dict[str, Any] = {}
    entries: List[Tuple[str, type]] = []
    for rel_file_path, attr in MANIFEST:
        cls = getattr(_load_source(rel_file_path, loaded_modules), attr, None)
        if cls is None:
            raise SystemExit(f"{rel_file_path}::{attr} not found")
        entries.append((rel_file_path, cls))

    known_names = {c.__name__ for _, c in entries}
    # Aliases are also valid known names so dataclasses referencing them resolve.
    for alias_list in ALIASES.values():
        known_names.update(alias_list)

    parts: List[str] = [HEADER]
    for rel_file_path, cls in entries:
        parts.extend(_render_class(cls, known_names, _display_module(rel_file_path)))
    for spec in CONST_MANIFEST:
        mapping = getattr(_load_source(spec.source, loaded_modules), spec.attr, None)
        if mapping is None:
            raise SystemExit(f"{spec.source}::{spec.attr} not found")
        parts.append(_render_const_map(spec, mapping, _display_module(spec.source)))
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the generated output differs from the committed file.",
    )
    args = parser.parse_args()

    rendered = generate()

    if args.check:
        existing = OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else ""
        if rendered != existing:
            print(
                f"DRIFT: {OUTPUT_PATH.relative_to(REPO_ROOT)} is out of date.\n"
                f"Run: python3 {Path(__file__).relative_to(REPO_ROOT)}",
                file=sys.stderr,
            )
            return 1
        print("OK — generated TS matches committed file.")
        return 0

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(rendered, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
