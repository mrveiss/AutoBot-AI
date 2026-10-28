# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A type the backend generates is never hand-declared again in a GUI (#19334).

``autobot-infrastructure/shared/scripts/gen_frontend_types.py`` writes the backend enums into
``autobot-frontend/src/types/_generated/workflow.ts``; consumers import them from there. Four
composables had hand-copied unions instead, each missing a member the backend emits
(``service_failed``, ``telegram``, ``awaiting_approval``, ``waiting_explanation``).

The guard reads every ``export type <Name>`` from the generated file and flags a ``type``,
``enum`` or ``interface`` of the same name in the main GUI's non-test source. One shape is
allowed, because the compiler checks it: ``type X = (typeof C)[number]`` where ``C`` is declared
``satisfies readonly ...`` -- a narrowed subset that cannot carry a value the backend lacks.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

_GENERATED = "autobot-frontend/src/types/_generated/workflow.ts"
#: The main GUI only: the generated file is its own, and the SLM GUI cannot import it (its ``Role``
#: is a fleet node role, a homonym of the auth ``Role``).
_APPS = ("autobot-frontend/src",)
_EXCLUDED = re.compile(r"(/_generated/|\.test\.|\.spec\.|\.stories\.|/__tests__/|/e2e/)")
_GENERATED_NAME = re.compile(r"^export (?:type|interface|enum) (\w+)\b", re.MULTILINE)
_SATISFIED_CONST = re.compile(r"const (\w+)\s*=\s*\[[^\]]*\]\s*as const satisfies readonly", re.DOTALL)


def generated_names(root: Path) -> set[str]:
    return set(_GENERATED_NAME.findall((root / _GENERATED).read_text(encoding="utf-8")))


def _sources(root: Path) -> list[Path]:
    found = []
    for app in _APPS:
        base = root / app
        if base.is_dir():
            found += [
                p
                for p in sorted(base.rglob("*"))
                if p.suffix in (".ts", ".vue") and not _EXCLUDED.search("/" + p.relative_to(root).as_posix())
            ]
    return found


REACH = declare(
    "generated-type-redeclarations",
    discover=_sources,
    floor=850,
    growth=100,  # ~9%: ordinary GUI growth between repins must not turn an unrelated PR red
    what="non-test .ts/.vue files",
    roots=_APPS,
)


def redeclarations(text: str, names: set[str], rel: str) -> list[str]:
    """Hand declarations of a generated name in *text*, minus compiler-checked subsets."""
    checked = set(_SATISFIED_CONST.findall(text))
    alternatives = "|".join(sorted(names))
    pattern = re.compile(
        rf"^[ \t]*(?:export[ \t]+)?(?:declare[ \t]+)?(?:const[ \t]+)?(?:type|enum|interface)[ \t]+({alternatives})\b"
        r"\s*(?:<.*?>\s*)?(?:extends[^{=]*)?(=\s*([^\n;]*)|\{)",
        re.MULTILINE,
    )
    found = []
    for m in pattern.finditer(text):
        subset = re.fullmatch(r"\(typeof (\w+)\)\[number\]", (m.group(3) or "").strip())
        if subset and subset.group(1) in checked:
            continue
        line = text.count("\n", 0, m.start()) + 1
        found.append(f"{rel}:{line}: {m.group(1)}")
    return found


def test_no_gui_redeclares_a_generated_type() -> None:
    root = repo_root()
    names = generated_names(root)
    assert len(names) >= 10, f"read only {sorted(names)} from {_GENERATED}; the parse lost its source"
    files = REACH.examined(root)
    found = [
        h for p in files for h in redeclarations(p.read_text(encoding="utf-8"), names, p.relative_to(root).as_posix())
    ]
    REACH.completed(files)
    assert not found, f"import these from '@/types/_generated/workflow' (#19334): {found}"


@pytest.mark.parametrize(
    "source",
    [
        "export type NotificationChannel = 'email' | 'slack';\n",
        "type WorkflowPhase =\n  | 'planning'\n  | 'failed';\n",
        "export enum OverseerStepStatus { PENDING = 'pending' }\n",
        "export interface WorkflowPhase extends Base {\n  x: string\n}\n",
        "type ExecutionStrategy<T = Array<string>> = T;\n",
        "const XS = ['a'] as const;\nexport type Severity = (typeof XS)[number];\n",
    ],
)
def test_each_redeclaration_shape_is_flagged(source: str) -> None:
    assert redeclarations(
        source, {"NotificationChannel", "WorkflowPhase", "OverseerStepStatus", "Severity", "ExecutionStrategy"}, "x.ts"
    )


def test_an_import_a_reexport_and_a_checked_subset_are_allowed() -> None:
    clean = (
        "import type { WorkflowPhase } from '@/types/_generated/workflow'\n"
        "import {\n  useX,\n  type Role,\n  type Permission,\n} from '@/composables/usePermissions'\n"
        "export type { WorkflowPhase }\n"
        "const SEV = ['info', 'low'] as const satisfies readonly CanonicalSeverity[]\n"
        "export type Severity = (typeof SEV)[number]\n"
    )
    assert not redeclarations(clean, {"WorkflowPhase", "Severity", "Role", "Permission"}, "x.ts")
