#!/usr/bin/env python3
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
import typing
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union, get_args, get_origin

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
MANIFEST: List[Tuple[str, str]] = [
    ("autobot_shared.workflow.types", "PromptSpec"),
    ("autobot_shared.workflow.types", "ExecutionStrategy"),
    ("autobot_shared.workflow.types", "WorkflowTask"),
    ("autobot_shared.workflow.types", "WorkflowPlan"),
    # #7226: extend MANIFEST to cover hand-written types prone to drift
    ("services.workflow_automation.models", "WorkflowStepStatus"),
    ("autobot_shared.status_enums", "Severity"),  # exported as RiskLevel via alias below
]


# Aliases emitted alongside their backing class — TypeScript can't have
# two type names point at the same union literal without a duplication,
# so we emit `export type RiskLevel = Severity;` after the source class.
# Map: source class name → list of alias names to emit.
ALIASES: Dict[str, List[str]] = {
    "Severity": ["RiskLevel"],
}


def _ensure_autobot_shared_on_path() -> None:
    """Add ``autobot_shared`` and ``autobot-backend`` to sys.path so the script
    can import canonical and (#7226) backend modules standalone."""
    shared = REPO_ROOT / "autobot_shared"
    if str(shared.parent) not in sys.path:
        sys.path.insert(0, str(shared.parent))
    backend = REPO_ROOT / "autobot-backend"
    if backend.is_dir() and str(backend) not in sys.path:
        sys.path.insert(0, str(backend))


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

    if origin is Union:
        # Handle Optional[X] = Union[X, None] specially
        non_none = [a for a in args if a is not type(None)]
        rendered = " | ".join(_ts_type(a, known_names) for a in non_none)
        if type(None) in args:
            rendered = f"{rendered} | null"
        return rendered

    if origin in (list, List):
        inner = _ts_type(args[0], known_names) if args else "unknown"
        return f"{inner}[]"

    if origin in (dict, Dict):
        if not args:
            return "Record<string, unknown>"
        # Always emit Record<string, V> — the key type is required
        # to be string-compatible for JSON serialization.
        v = _ts_type(args[1], known_names)
        return f"Record<string, {v}>"

    if origin in (set, Set, frozenset):
        inner = _ts_type(args[0], known_names) if args else "unknown"
        return f"{inner}[]"

    if origin is tuple:
        inner = ", ".join(_ts_type(a, known_names) for a in args) if args else "unknown"
        return f"[{inner}]"

    if py_type is Any:
        return "unknown"

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
    return (
        f"/** Generated from `{source}.{cls.__name__}` */\n"
        f"export type {cls.__name__} =\n{body};\n"
    )


def _render_alias(name: str, target: str, source_cls: str) -> str:
    """Emit a TypeScript type alias re-exporting an existing union."""
    return (
        f"/** Generated alias — same union as `{source_cls}` (#6689 / #7226) */\n"
        f"export type {name} = {target};\n"
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
        # Optional in TS is best signalled via `field?: T` when default is
        # None or default_factory is callable returning a "missing" stand-in.
        # Keep it simple here: emit `field: T` always so the schema is exact.
        lines.append(f"  {f.name}: {ts};")
    lines.append("}\n")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

HEADER = """// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
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
    """Run the manifest and produce the full TS output as a string."""
    _ensure_autobot_shared_on_path()
    entries: List[Tuple[str, type]] = []
    for module_path, attr in MANIFEST:
        spec = importlib.util.find_spec(module_path)
        if spec is None:
            raise SystemExit(f"Module not found: {module_path}")
        module = importlib.import_module(module_path)
        cls = getattr(module, attr, None)
        if cls is None:
            raise SystemExit(f"{module_path}.{attr} not found")
        entries.append((module_path, cls))

    known_names = {c.__name__ for _, c in entries}
    # Aliases are also valid known names so dataclasses referencing them resolve.
    for source, alias_list in ALIASES.items():
        known_names.update(alias_list)

    parts: List[str] = [HEADER]
    for module_path, cls in entries:
        if isinstance(cls, type) and issubclass(cls, Enum):
            parts.append(_render_enum(cls, module_path))
        elif dataclasses.is_dataclass(cls):
            parts.append(_render_dataclass(cls, known_names, module_path))
        else:
            raise SystemExit(f"Unsupported class kind: {cls!r}")
        # Emit any aliases declared for this class
        for alias_name in ALIASES.get(cls.__name__, []):
            parts.append(_render_alias(alias_name, cls.__name__, cls.__name__))
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
