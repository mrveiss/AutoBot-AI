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
MANIFEST: List[Tuple[str, str]] = [
    ("autobot_shared.workflow.types", "PromptSpec"),
    ("autobot_shared.workflow.types", "ExecutionStrategy"),
    ("autobot_shared.workflow.types", "WorkflowTask"),
    ("autobot_shared.workflow.types", "WorkflowPlan"),
]


def _ensure_autobot_shared_on_path() -> None:
    """Add ``autobot_shared`` to sys.path so the script can import it standalone."""
    shared = REPO_ROOT / "autobot_shared"
    if str(shared.parent) not in sys.path:
        sys.path.insert(0, str(shared.parent))


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


def _render_enum(cls: type) -> str:
    """Emit a TypeScript string union for a Python Enum."""
    members = [f"  | '{m.value}'" for m in cls]
    body = "\n".join(members)
    return (
        f"/** Generated from `autobot_shared.workflow.types.{cls.__name__}` */\n"
        f"export type {cls.__name__} =\n{body};\n"
    )


def _render_dataclass(cls: type, known_names: Set[str]) -> str:
    """Emit a TypeScript interface for a Python dataclass."""
    type_hints = typing.get_type_hints(cls, include_extras=False)
    lines = [
        f"/** Generated from `autobot_shared.workflow.types.{cls.__name__}` */",
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
    classes: List[type] = []
    for module_path, attr in MANIFEST:
        spec = importlib.util.find_spec(module_path)
        if spec is None:
            raise SystemExit(f"Module not found: {module_path}")
        module = importlib.import_module(module_path)
        cls = getattr(module, attr, None)
        if cls is None:
            raise SystemExit(f"{module_path}.{attr} not found")
        classes.append(cls)

    known_names = {c.__name__ for c in classes}

    parts: List[str] = [HEADER]
    for cls in classes:
        if isinstance(cls, type) and issubclass(cls, Enum):
            parts.append(_render_enum(cls))
        elif dataclasses.is_dataclass(cls):
            parts.append(_render_dataclass(cls, known_names))
        else:
            raise SystemExit(f"Unsupported class kind: {cls!r}")
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
