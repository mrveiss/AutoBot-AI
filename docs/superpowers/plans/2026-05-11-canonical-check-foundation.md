# Canonical-Check Foundation (Wave 0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the empty-but-working three-runner canonical-check pipeline (Python + Frontend + Infra), plus one trivial smoke-test rule per layer, plus the Makefile/pre-commit/CI/slash-command wiring — so that Waves 1–5 can each add a rule module to a registry that already runs.

**Architecture:** Three independent runners (Python AST, Vue/TS, infrastructure YAML/shell) each consume a shared rule contract: `RULE_ID`, `ISSUE`, `SEVERITY`, `TARGETS`, `DESCRIPTION`, `FIX_HINT`, `check()`. A pluggable registry per layer auto-discovers rule modules. Reporter emits pretty stderr (pre-commit), markdown report (audit), and JSON sidecar (CI artifact). Audit mode runs from a weekly GitHub Actions cron and uploads results as a 365-day-retention artifact — no committed reports.

**Tech Stack:** Python 3.11 (`ast`, `pathlib`, `argparse`, `dataclasses`), Node ≥20 (`@vue/compiler-sfc`, `ts-morph` deferred to Wave 3 — Wave 0 frontend uses plain regex over text), pre-commit (`local` hooks), GitHub Actions, Make.

**Spec:** `docs/superpowers/specs/2026-05-10-canonical-check-workflow-design.md`

**Tracking:** Sub-umbrella #7458; this plan covers Wave 0 only (foundation skeleton + smoke-test rules).

---

## File Structure

### Created files (Python runner)
```
tools/lint/canonical_check.py                          # CLI entry (Python runner)
tools/lint/canonical/__init__.py                       # Package marker (empty)
tools/lint/canonical/diagnostic.py                     # Diagnostic dataclass
tools/lint/canonical/context.py                        # AST cache + file iterator
tools/lint/canonical/registry.py                       # Rule discovery + execution
tools/lint/canonical/reporter.py                       # Pretty / markdown / json output
tools/lint/canonical/rules/__init__.py                 # Package marker (empty)
tools/lint/canonical/rules/py_print_smoke.py           # Smoke-test rule
```

### Created files (Infra runner — same package as Python)
```
tools/lint/canonical_check_infra.py                    # CLI entry (Infra runner)
tools/lint/canonical/infra_rules/__init__.py           # Package marker (empty)
tools/lint/canonical/infra_rules/sh_echo_debug_smoke.py # Smoke-test infra rule
```

### Created files (Frontend runner — separate Node process)
```
autobot-frontend/scripts/canonical_check.mjs           # CLI entry (Frontend runner)
autobot-frontend/scripts/canonical/registry.mjs        # Rule discovery
autobot-frontend/scripts/canonical/diagnostic.mjs      # Diagnostic shape (mirrors Python)
autobot-frontend/scripts/canonical/reporter.mjs        # Output formatting
autobot-frontend/scripts/canonical/rules/fe_console_log_smoke.mjs  # Smoke-test rule
```

### Created files (tests)
```
tests/lint/canonical/__init__.py
tests/lint/canonical/test_diagnostic.py
tests/lint/canonical/test_context.py
tests/lint/canonical/test_registry.py
tests/lint/canonical/test_reporter.py
tests/lint/canonical/test_runner_cli.py
tests/lint/canonical/test_runner_infra_cli.py
tests/lint/canonical/rules/__init__.py
tests/lint/canonical/rules/test_py_print_smoke.py
tests/lint/canonical/rules/test_sh_echo_debug_smoke.py
tests/lint/canonical/fixtures/py_print_smoke/positive.py
tests/lint/canonical/fixtures/py_print_smoke/negative.py
tests/lint/canonical/fixtures/py_print_smoke/waiver.py
tests/lint/canonical/fixtures/sh_echo_debug_smoke/positive.sh
tests/lint/canonical/fixtures/sh_echo_debug_smoke/negative.sh
autobot-frontend/scripts/canonical/__tests__/registry.test.mjs
autobot-frontend/scripts/canonical/__tests__/runner.test.mjs
autobot-frontend/scripts/canonical/__tests__/fixtures/positive.ts
autobot-frontend/scripts/canonical/__tests__/fixtures/negative.ts
```

### Created files (wiring)
```
Makefile                                               # MODIFY: add canonical-check targets
.pre-commit-config.yaml                                # MODIFY: add 3 hook entries
.gitignore                                             # MODIFY: add .canonical-audit/
.github/workflows/canonical-audit.yml                  # CREATE: weekly cron
.claude/skills/canonical-audit/SKILL.md                # CREATE: slash command
docs/developer/CANONICAL_RULES.md                      # CREATE: rule catalog skeleton
```

### File responsibilities

- `diagnostic.py` — frozen dataclass; one job: structured violation records.
- `context.py` — file iteration, AST parsing, parse-error caching. No rule logic.
- `registry.py` — auto-discovers rule modules via `pkgutil.iter_modules`; runs them; aggregates diagnostics. Independent of rule content.
- `reporter.py` — three pure functions (`to_pretty`, `to_markdown`, `to_json`). No I/O.
- `canonical_check.py` — argparse, exit codes, glue between context/registry/reporter. Thin.
- `canonical_check_infra.py` — same shape, but iterates `*.sh`/`*.yml`/`Dockerfile` files; rules receive raw text + filename, not AST.
- Each `rules/*.py` — exactly one rule. Module-level constants + a single `check()` function.

---

## Task 1: Project skeleton + .gitignore

**Files:**
- Create: `tools/lint/canonical/__init__.py` (empty)
- Create: `tools/lint/canonical/rules/__init__.py` (empty)
- Create: `tools/lint/canonical/infra_rules/__init__.py` (empty)
- Create: `tests/lint/canonical/__init__.py` (empty)
- Create: `tests/lint/canonical/rules/__init__.py` (empty)
- Modify: `.gitignore`

- [ ] **Step 1: Create empty package markers**

```bash
touch tools/lint/canonical/__init__.py
touch tools/lint/canonical/rules/__init__.py
touch tools/lint/canonical/infra_rules/__init__.py
touch tests/lint/canonical/__init__.py
touch tests/lint/canonical/rules/__init__.py
```

- [ ] **Step 2: Append to `.gitignore`**

Add at end of file:

```gitignore

# Canonical-check local audit reports
.canonical-audit/
```

- [ ] **Step 3: Verify imports work**

Run: `python -c 'import tools.lint.canonical; import tools.lint.canonical.rules; import tools.lint.canonical.infra_rules; print("ok")'`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add tools/lint/canonical/ tests/lint/canonical/ .gitignore
git commit -m "feat(canonical-check): scaffold package directories and .gitignore (#7458)"
```

---

## Task 2: Diagnostic dataclass

**Files:**
- Create: `tools/lint/canonical/diagnostic.py`
- Test: `tests/lint/canonical/test_diagnostic.py`

- [ ] **Step 1: Write the failing test**

Create `tests/lint/canonical/test_diagnostic.py`:

```python
"""Tests for the Diagnostic dataclass — the shared violation record."""
from pathlib import Path

import pytest

from tools.lint.canonical.diagnostic import Diagnostic


def test_diagnostic_required_fields():
    d = Diagnostic(
        rule_id="py-print-smoke",
        issue="#7458",
        severity="warn",
        file=Path("autobot-backend/foo.py"),
        line=1,
        col=0,
        message="print() in production",
        snippet="print('hi')",
    )
    assert d.rule_id == "py-print-smoke"
    assert d.fix_hint == ""
    assert d.auto_fixable is False


def test_diagnostic_is_frozen():
    d = Diagnostic(
        rule_id="r", issue="#1", severity="warn",
        file=Path("a.py"), line=1, col=0, message="m", snippet="s",
    )
    with pytest.raises(AttributeError):
        d.line = 2  # type: ignore[misc]


def test_diagnostic_to_dict_round_trip():
    d = Diagnostic(
        rule_id="r", issue="#1", severity="warn",
        file=Path("a.py"), line=1, col=0, message="m", snippet="s",
        fix_hint="use foo()", auto_fixable=True,
    )
    payload = d.to_dict()
    assert payload["file"] == "a.py"  # Path serialized to str
    assert payload["auto_fixable"] is True


def test_diagnostic_severity_validated():
    with pytest.raises(ValueError, match="severity"):
        Diagnostic(
            rule_id="r", issue="#1", severity="catastrophic",  # type: ignore[arg-type]
            file=Path("a.py"), line=1, col=0, message="m", snippet="s",
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/lint/canonical/test_diagnostic.py -v`
Expected: 4 errors / failures (`ModuleNotFoundError: tools.lint.canonical.diagnostic`)

- [ ] **Step 3: Write the implementation**

Create `tools/lint/canonical/diagnostic.py`:

```python
"""Shared violation record for the canonical-check workflow.

Every rule in every runner emits Diagnostic instances. Reporter formatters
consume the same shape regardless of whether the rule was Python AST,
frontend regex, or infra YAML.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

Severity = Literal["block", "warn", "audit"]
_VALID_SEVERITIES: frozenset[str] = frozenset({"block", "warn", "audit"})


@dataclass(frozen=True)
class Diagnostic:
    rule_id: str
    issue: str
    severity: Severity
    file: Path
    line: int
    col: int
    message: str
    snippet: str
    fix_hint: str = ""
    auto_fixable: bool = False

    def __post_init__(self) -> None:
        if self.severity not in _VALID_SEVERITIES:
            raise ValueError(
                f"severity must be one of {sorted(_VALID_SEVERITIES)}, got {self.severity!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "issue": self.issue,
            "severity": self.severity,
            "file": str(self.file),
            "line": self.line,
            "col": self.col,
            "message": self.message,
            "snippet": self.snippet,
            "fix_hint": self.fix_hint,
            "auto_fixable": self.auto_fixable,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/lint/canonical/test_diagnostic.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add tools/lint/canonical/diagnostic.py tests/lint/canonical/test_diagnostic.py
git commit -m "feat(canonical-check): add Diagnostic dataclass with severity validation (#7458)"
```

---

## Task 3: Context (file iterator + AST cache)

**Files:**
- Create: `tools/lint/canonical/context.py`
- Test: `tests/lint/canonical/test_context.py`

- [ ] **Step 1: Write the failing test**

Create `tests/lint/canonical/test_context.py`:

```python
"""Tests for Context — file iteration + AST cache."""
import ast
from pathlib import Path

import pytest

from tools.lint.canonical.context import Context, file_in_targets


def test_parse_caches_ast(tmp_path: Path) -> None:
    src = tmp_path / "sample.py"
    src.write_text("x = 1\n", encoding="utf-8")
    ctx = Context(repo_root=tmp_path)
    tree_a = ctx.parse(src)
    tree_b = ctx.parse(src)
    assert tree_a is tree_b
    assert isinstance(tree_a, ast.Module)


def test_parse_returns_none_on_syntax_error(tmp_path: Path) -> None:
    src = tmp_path / "broken.py"
    src.write_text("def (\n", encoding="utf-8")
    ctx = Context(repo_root=tmp_path)
    assert ctx.parse(src) is None


def test_parse_returns_none_for_missing_file(tmp_path: Path) -> None:
    ctx = Context(repo_root=tmp_path)
    assert ctx.parse(tmp_path / "nope.py") is None


def test_file_in_targets_matches_prefix(tmp_path: Path) -> None:
    f = tmp_path / "autobot-backend" / "api" / "foo.py"
    f.parent.mkdir(parents=True)
    f.write_text("", encoding="utf-8")
    assert file_in_targets(f, ["autobot-backend"], repo_root=tmp_path) is True
    assert file_in_targets(f, ["autobot-frontend"], repo_root=tmp_path) is False


def test_file_in_targets_handles_absolute_path(tmp_path: Path) -> None:
    f = tmp_path / "autobot-backend" / "x.py"
    f.parent.mkdir(parents=True)
    f.write_text("", encoding="utf-8")
    # relative prefix match against absolute path
    assert file_in_targets(f, ["autobot-backend"], repo_root=tmp_path) is True


def test_iter_targets_walks_only_targets(tmp_path: Path) -> None:
    (tmp_path / "autobot-backend").mkdir()
    (tmp_path / "autobot-backend" / "a.py").write_text("", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "b.py").write_text("", encoding="utf-8")
    ctx = Context(repo_root=tmp_path)
    files = list(ctx.iter_targets(["autobot-backend"], suffixes={".py"}))
    assert len(files) == 1
    assert files[0].name == "a.py"


def test_iter_targets_skips_excluded_dirs(tmp_path: Path) -> None:
    (tmp_path / "autobot-backend").mkdir()
    (tmp_path / "autobot-backend" / "a.py").write_text("", encoding="utf-8")
    cache = tmp_path / "autobot-backend" / "__pycache__"
    cache.mkdir()
    (cache / "b.py").write_text("", encoding="utf-8")
    ctx = Context(repo_root=tmp_path)
    files = list(ctx.iter_targets(["autobot-backend"], suffixes={".py"}))
    assert len(files) == 1
    assert "__pycache__" not in str(files[0])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/lint/canonical/test_context.py -v`
Expected: 7 errors (`ModuleNotFoundError`)

- [ ] **Step 3: Write the implementation**

Create `tools/lint/canonical/context.py`:

```python
"""Shared parsing context — AST cache + target file iteration."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

_EXCLUDED_DIRS: frozenset[str] = frozenset({
    "__pycache__", "node_modules", ".venv", "venv", ".git",
    "dist", "build", ".tox", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".worktrees", "htmlcov",
})


@dataclass
class Context:
    repo_root: Path
    _ast_cache: dict[Path, ast.AST | None] = field(default_factory=dict)

    def parse(self, file_path: Path) -> ast.AST | None:
        if file_path in self._ast_cache:
            return self._ast_cache[file_path]
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(file_path))
        except (SyntaxError, OSError, UnicodeDecodeError):
            self._ast_cache[file_path] = None
            return None
        self._ast_cache[file_path] = tree
        return tree

    def iter_targets(
        self, targets: list[str], *, suffixes: set[str]
    ) -> Iterator[Path]:
        for target in targets:
            base = self.repo_root / target
            if not base.exists():
                continue
            yield from _walk(base, suffixes)


def _walk(base: Path, suffixes: set[str]) -> Iterator[Path]:
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in suffixes:
            continue
        if any(part in _EXCLUDED_DIRS for part in path.parts):
            continue
        yield path


def file_in_targets(
    file_path: Path, targets: list[str], *, repo_root: Path
) -> bool:
    try:
        rel = file_path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return False
    rel_str = str(rel)
    return any(rel_str == t or rel_str.startswith(f"{t}/") for t in targets)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/lint/canonical/test_context.py -v`
Expected: 7 PASS

- [ ] **Step 5: Commit**

```bash
git add tools/lint/canonical/context.py tests/lint/canonical/test_context.py
git commit -m "feat(canonical-check): add Context with AST cache and target file iteration (#7458)"
```

---

## Task 4: Registry (rule discovery + execution)

**Files:**
- Create: `tools/lint/canonical/registry.py`
- Test: `tests/lint/canonical/test_registry.py`

- [ ] **Step 1: Write the failing test**

Create `tests/lint/canonical/test_registry.py`:

```python
"""Tests for rule discovery + execution."""
import ast
import textwrap
from pathlib import Path
from types import ModuleType

import pytest

from tools.lint.canonical.context import Context
from tools.lint.canonical.diagnostic import Diagnostic
from tools.lint.canonical.registry import discover_rules, run_rules


def _make_rule_module(name: str, severity: str = "warn") -> ModuleType:
    mod = ModuleType(name)
    mod.RULE_ID = name.replace("_", "-")
    mod.ISSUE = "#7458"
    mod.SEVERITY = severity
    mod.TARGETS = ["pkg"]
    mod.DESCRIPTION = "test rule"
    mod.FIX_HINT = "fix it"

    def check(file_path: Path, tree: ast.AST, ctx: Context) -> list[Diagnostic]:
        return [Diagnostic(
            rule_id=mod.RULE_ID, issue=mod.ISSUE, severity=mod.SEVERITY,
            file=file_path, line=1, col=0, message="m", snippet="s",
        )]

    mod.check = check
    return mod


def test_discover_rules_loads_canonical_smoke_module():
    rules = discover_rules("tools.lint.canonical.rules")
    rule_ids = {r.RULE_ID for r in rules}
    assert "py-print-smoke" in rule_ids


def test_run_rules_invokes_each_rule_per_file(tmp_path: Path):
    src = tmp_path / "pkg" / "x.py"
    src.parent.mkdir()
    src.write_text("x = 1\n", encoding="utf-8")
    ctx = Context(repo_root=tmp_path)
    rule = _make_rule_module("rule_a")
    diags = run_rules([rule], [src], ctx)
    assert len(diags) == 1
    assert diags[0].rule_id == "rule-a"


def test_run_rules_skips_files_outside_targets(tmp_path: Path):
    src = tmp_path / "other" / "x.py"
    src.parent.mkdir()
    src.write_text("x = 1\n", encoding="utf-8")
    ctx = Context(repo_root=tmp_path)
    rule = _make_rule_module("rule_a")  # TARGETS = ["pkg"]
    diags = run_rules([rule], [src], ctx)
    assert diags == []


def test_run_rules_skips_files_with_syntax_errors(tmp_path: Path):
    src = tmp_path / "pkg" / "broken.py"
    src.parent.mkdir()
    src.write_text("def (\n", encoding="utf-8")
    ctx = Context(repo_root=tmp_path)
    rule = _make_rule_module("rule_a")
    assert run_rules([rule], [src], ctx) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/lint/canonical/test_registry.py -v`
Expected: 4 errors (module missing). Note `test_discover_rules_loads_canonical_smoke_module` will continue to fail until Task 7 — leave it.

- [ ] **Step 3: Write the implementation**

Create `tools/lint/canonical/registry.py`:

```python
"""Rule discovery and execution.

Rule modules are auto-discovered from a Python package via pkgutil. A valid
rule module exports module-level constants (RULE_ID, ISSUE, SEVERITY, TARGETS,
DESCRIPTION, FIX_HINT) and a `check(file_path, tree, ctx) -> list[Diagnostic]`
function. Anything else in the package is ignored.
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
from collections.abc import Iterable
from pathlib import Path
from types import ModuleType

from tools.lint.canonical.context import Context, file_in_targets
from tools.lint.canonical.diagnostic import Diagnostic

_REQUIRED_ATTRS = ("RULE_ID", "ISSUE", "SEVERITY", "TARGETS", "DESCRIPTION", "FIX_HINT", "check")


def discover_rules(package: str) -> list[ModuleType]:
    pkg = importlib.import_module(package)
    rules: list[ModuleType] = []
    if not hasattr(pkg, "__path__"):
        return rules
    for _finder, modname, _ispkg in pkgutil.iter_modules(pkg.__path__):
        if modname.startswith("_"):
            continue
        mod = importlib.import_module(f"{package}.{modname}")
        if all(hasattr(mod, attr) for attr in _REQUIRED_ATTRS):
            rules.append(mod)
    return rules


def run_rules(
    rules: list[ModuleType],
    files: Iterable[Path],
    ctx: Context,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for file_path in files:
        tree = ctx.parse(file_path)
        if tree is None:
            continue
        for rule in rules:
            if not file_in_targets(file_path, rule.TARGETS, repo_root=ctx.repo_root):
                continue
            diagnostics.extend(rule.check(file_path, tree, ctx))
    return diagnostics
```

- [ ] **Step 4: Run test to verify the 3 non-discovery tests pass**

Run: `pytest tests/lint/canonical/test_registry.py -v -k 'not discover'`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add tools/lint/canonical/registry.py tests/lint/canonical/test_registry.py
git commit -m "feat(canonical-check): add rule discovery and execution registry (#7458)"
```

---

## Task 5: Reporter (pretty / markdown / json)

**Files:**
- Create: `tools/lint/canonical/reporter.py`
- Test: `tests/lint/canonical/test_reporter.py`

- [ ] **Step 1: Write the failing test**

Create `tests/lint/canonical/test_reporter.py`:

```python
"""Tests for the three reporter formatters."""
import json
from pathlib import Path

import pytest

from tools.lint.canonical.diagnostic import Diagnostic
from tools.lint.canonical.reporter import to_json, to_markdown, to_pretty


@pytest.fixture
def sample_diagnostics() -> list[Diagnostic]:
    return [
        Diagnostic(
            rule_id="py-print-smoke", issue="#7458", severity="warn",
            file=Path("autobot-backend/api/foo.py"), line=42, col=4,
            message="print() in production",
            snippet="print('hi')",
            fix_hint="use logger",
        ),
        Diagnostic(
            rule_id="py-other", issue="#9999", severity="block",
            file=Path("autobot-backend/api/foo.py"), line=10, col=0,
            message="bad pattern", snippet="x", fix_hint="",
        ),
    ]


def test_to_pretty_groups_by_file(sample_diagnostics):
    out = to_pretty(sample_diagnostics)
    assert "autobot-backend/api/foo.py:10" in out
    assert "autobot-backend/api/foo.py:42" in out
    assert "py-print-smoke" in out
    assert "py-other" in out


def test_to_pretty_empty_returns_zero_violations():
    out = to_pretty([])
    assert "0 violations" in out


def test_to_json_is_round_trippable(sample_diagnostics):
    payload = to_json(sample_diagnostics)
    parsed = json.loads(payload)
    assert isinstance(parsed, list)
    assert parsed[0]["rule_id"] in {"py-print-smoke", "py-other"}
    assert parsed[0]["file"].endswith("foo.py")


def test_to_markdown_summary_table(sample_diagnostics):
    out = to_markdown(sample_diagnostics, scan_meta={
        "scanned_files": 100, "duration_seconds": 1.2, "rule_count": 2,
    })
    assert "# Canonical-style audit" in out
    assert "block" in out
    assert "warn" in out
    assert "py-print-smoke" in out
    assert "scanned 100 files" in out


def test_to_markdown_handles_empty():
    out = to_markdown([], scan_meta={"scanned_files": 0, "duration_seconds": 0, "rule_count": 0})
    assert "no violations" in out.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/lint/canonical/test_reporter.py -v`
Expected: 5 errors (module missing).

- [ ] **Step 3: Write the implementation**

Create `tools/lint/canonical/reporter.py`:

```python
"""Output formatters: pretty (terminal), markdown (audit), JSON (artifact)."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from tools.lint.canonical.diagnostic import Diagnostic


def to_pretty(diagnostics: Sequence[Diagnostic]) -> str:
    if not diagnostics:
        return "canonical-check: 0 violations\n"

    by_severity: dict[str, int] = defaultdict(int)
    for d in diagnostics:
        by_severity[d.severity] += 1

    lines = [
        f"canonical-check: {len(diagnostics)} violations "
        f"(block={by_severity['block']}, warn={by_severity['warn']}, audit={by_severity['audit']})"
    ]

    grouped: dict[str, list[Diagnostic]] = defaultdict(list)
    for d in diagnostics:
        grouped[str(d.file)].append(d)

    for file_str in sorted(grouped):
        for d in sorted(grouped[file_str], key=lambda x: (x.line, x.col)):
            lines.append(f"  {file_str}:{d.line}  {d.rule_id}  ({d.issue}) [{d.severity}]")
            lines.append(f"    {d.message}")
    lines.append("")
    return "\n".join(lines)


def to_json(diagnostics: Sequence[Diagnostic]) -> str:
    return json.dumps([d.to_dict() for d in diagnostics], indent=2, sort_keys=True)


def to_markdown(
    diagnostics: Sequence[Diagnostic],
    *,
    scan_meta: dict[str, Any],
) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        f"# Canonical-style audit — {today}",
        f"{scan_meta.get('rule_count', 0)} rules · scanned "
        f"{scan_meta.get('scanned_files', 0)} files in "
        f"{scan_meta.get('duration_seconds', 0):.1f}s",
        "",
    ]

    if not diagnostics:
        lines.append("**no violations** — all rules clean.")
        lines.append("")
        return "\n".join(lines)

    by_sev: dict[str, list[Diagnostic]] = defaultdict(list)
    for d in diagnostics:
        by_sev[d.severity].append(d)

    by_rule: dict[str, list[Diagnostic]] = defaultdict(list)
    for d in diagnostics:
        by_rule[d.rule_id].append(d)

    top_rules = {
        sev: max(
            ((rid, len([d for d in ds if d.rule_id == rid])) for rid in {d.rule_id for d in ds}),
            key=lambda x: x[1],
            default=("—", 0),
        )
        for sev, ds in by_sev.items()
    }

    lines += [
        "## Summary",
        "| Severity | Total | Top rule |",
        "|---|---|---|",
    ]
    for sev in ("block", "warn", "audit"):
        ds = by_sev.get(sev, [])
        rule_id, rule_n = top_rules.get(sev, ("—", 0))
        lines.append(f"| {sev} | {len(ds)} | {rule_id} ({rule_n}) |")
    lines.append("")

    lines.append("## By rule")
    for rid in sorted(by_rule, key=lambda r: -len(by_rule[r])):
        ds = by_rule[rid]
        sev = ds[0].severity
        issue = ds[0].issue
        files = sorted({str(d.file) for d in ds})
        lines.append(f"### {rid} ({issue}) — {len(ds)} violations in {len(files)} files ({sev})")
        for f in files[:5]:
            n = sum(1 for d in ds if str(d.file) == f)
            lines.append(f"- {f} — {n} violations")
        if len(files) > 5:
            lines.append(f"- … +{len(files) - 5} more files")
        lines.append("")

    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/lint/canonical/test_reporter.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add tools/lint/canonical/reporter.py tests/lint/canonical/test_reporter.py
git commit -m "feat(canonical-check): add pretty/markdown/json reporter formatters (#7458)"
```

---

## Task 6: Python runner CLI entry

**Files:**
- Create: `tools/lint/canonical_check.py`
- Test: `tests/lint/canonical/test_runner_cli.py`

- [ ] **Step 1: Write the failing test**

Create `tests/lint/canonical/test_runner_cli.py`:

```python
"""End-to-end CLI tests for the Python runner."""
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER = REPO_ROOT / "tools" / "lint" / "canonical_check.py"


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(RUNNER), *args],
        cwd=cwd or REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_runner_no_files_no_all_errors():
    result = _run()
    assert result.returncode == 2  # argparse error
    assert "--files" in result.stderr or "--all" in result.stderr


def test_runner_with_clean_file_exits_zero(tmp_path: Path):
    f = tmp_path / "clean.py"
    f.write_text("x = 1\n", encoding="utf-8")
    result = _run("--files", str(f))
    assert result.returncode == 0


def test_runner_explain_known_rule():
    result = _run("--explain", "py-print-smoke")
    assert result.returncode == 0
    assert "py-print-smoke" in result.stdout or "print" in result.stdout.lower()


def test_runner_explain_unknown_rule_exits_2():
    result = _run("--explain", "no-such-rule")
    assert result.returncode == 2


def test_runner_format_json_emits_array():
    result = _run("--files", str(REPO_ROOT / "tools" / "lint" / "canonical_check.py"), "--format", "json")
    assert result.stdout.startswith("[")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/lint/canonical/test_runner_cli.py -v`
Expected: 5 errors (`tools/lint/canonical_check.py` doesn't exist).

- [ ] **Step 3: Write the implementation**

Create `tools/lint/canonical_check.py`:

```python
#!/usr/bin/env python3
"""Canonical-check Python runner.

Two modes:
    --files <paths>   pre-commit mode: scan staged files only.
    --all             audit mode: walk every TARGETS directory.

Output:
    --format pretty    (default; stderr) terse violations grouped by file.
    --format markdown  (stdout) full audit report.
    --format json      (stdout) machine-readable diagnostic array.

Exit code:
    0   no BLOCK violations.
    1   one or more BLOCK violations.
    2   CLI / explain error.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Make tools/ importable when invoked via shebang from anywhere
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.lint.canonical.context import Context  # noqa: E402
from tools.lint.canonical.registry import discover_rules, run_rules  # noqa: E402
from tools.lint.canonical.reporter import to_json, to_markdown, to_pretty  # noqa: E402

_RULES_PACKAGE = "tools.lint.canonical.rules"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--files", nargs="*", help="Files to check (pre-commit mode)")
    g.add_argument("--all", action="store_true", help="Walk all TARGETS (audit mode)")
    p.add_argument("--explain", help="Print rule rationale and exit")
    p.add_argument("--format", choices=["pretty", "markdown", "json"], default="pretty")
    p.add_argument("--output", help="Write output to file instead of stdout")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    rules = discover_rules(_RULES_PACKAGE)

    if args.explain:
        rule = next((r for r in rules if r.RULE_ID == args.explain), None)
        if rule is None:
            print(f"unknown rule: {args.explain}", file=sys.stderr)
            return 2
        print(f"{rule.RULE_ID} ({rule.ISSUE}) [{rule.SEVERITY}]")
        print(rule.DESCRIPTION)
        print()
        print("Fix:")
        print(rule.FIX_HINT)
        return 0

    if not args.files and not args.all:
        print("error: --files or --all required", file=sys.stderr)
        return 2

    ctx = Context(repo_root=_REPO_ROOT)

    if args.all:
        all_targets = sorted({t for r in rules for t in r.TARGETS})
        files = list(ctx.iter_targets(all_targets, suffixes={".py"}))
    else:
        files = [Path(f) for f in (args.files or []) if f.endswith(".py")]

    start = time.monotonic()
    diagnostics = run_rules(rules, files, ctx)
    duration = time.monotonic() - start

    if args.format == "pretty":
        out = to_pretty(diagnostics)
        sink = sys.stderr
    elif args.format == "markdown":
        out = to_markdown(
            diagnostics,
            scan_meta={
                "scanned_files": len(files),
                "duration_seconds": duration,
                "rule_count": len(rules),
            },
        )
        sink = sys.stdout
    else:
        out = to_json(diagnostics)
        sink = sys.stdout

    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
    else:
        sink.write(out)
        if not out.endswith("\n"):
            sink.write("\n")

    blocking = sum(1 for d in diagnostics if d.severity == "block")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Mark runner executable**

```bash
chmod +x tools/lint/canonical_check.py
```

- [ ] **Step 5: Run tests**

The discovery test from Task 4 (`test_discover_rules_loads_canonical_smoke_module`) and explain test from this Task will still fail until Task 7 lands the smoke rule. Run only the tests that should pass now:

Run: `pytest tests/lint/canonical/test_runner_cli.py -v -k 'no_files or clean_file or unknown_rule or format_json'`
Expected: 4 PASS

- [ ] **Step 6: Commit**

```bash
git add tools/lint/canonical_check.py tests/lint/canonical/test_runner_cli.py
git commit -m "feat(canonical-check): add Python runner CLI with pretty/markdown/json output (#7458)"
```

---

## Task 7: Python smoke rule (py-print-smoke)

**Files:**
- Create: `tools/lint/canonical/rules/py_print_smoke.py`
- Create: `tests/lint/canonical/fixtures/py_print_smoke/positive.py`
- Create: `tests/lint/canonical/fixtures/py_print_smoke/negative.py`
- Create: `tests/lint/canonical/fixtures/py_print_smoke/waiver.py`
- Test: `tests/lint/canonical/rules/test_py_print_smoke.py`

- [ ] **Step 1: Write the fixtures**

Create `tests/lint/canonical/fixtures/py_print_smoke/positive.py`:

```python
"""Fixture: contains a print() call — should produce one diagnostic."""


def main() -> None:
    print("hi")
```

Create `tests/lint/canonical/fixtures/py_print_smoke/negative.py`:

```python
"""Fixture: no print() — should produce zero diagnostics."""

import logging

logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("hi")
```

Create `tests/lint/canonical/fixtures/py_print_smoke/waiver.py`:

```python
"""Fixture: print() suppressed via inline waiver — zero diagnostics."""


def main() -> None:
    print("hi")  # canonical: ignore py-print-smoke — bootstrap script (#7458)
```

- [ ] **Step 2: Write the failing test**

Create `tests/lint/canonical/rules/test_py_print_smoke.py`:

```python
"""Tests for the py-print-smoke rule (Wave 0 smoke-test rule)."""
import ast
from pathlib import Path

import pytest

from tools.lint.canonical import rules
from tools.lint.canonical.context import Context
from tools.lint.canonical.rules import py_print_smoke

FIXTURES = Path(__file__).parent.parent / "fixtures" / "py_print_smoke"


def _check(name: str) -> list:
    path = FIXTURES / name
    ctx = Context(repo_root=path.parent)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return py_print_smoke.check(path, tree, ctx)


def test_positive_fixture_produces_one_diagnostic():
    diags = _check("positive.py")
    assert len(diags) == 1
    assert diags[0].rule_id == "py-print-smoke"
    assert diags[0].severity == "warn"


def test_negative_fixture_produces_no_diagnostics():
    assert _check("negative.py") == []


def test_waiver_fixture_produces_no_diagnostics():
    assert _check("waiver.py") == []


def test_rule_metadata_present():
    for attr in ("RULE_ID", "ISSUE", "SEVERITY", "TARGETS", "DESCRIPTION", "FIX_HINT"):
        assert hasattr(py_print_smoke, attr), f"missing {attr}"
    assert py_print_smoke.SEVERITY == "warn"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/lint/canonical/rules/test_py_print_smoke.py -v`
Expected: 4 errors (rule module missing).

- [ ] **Step 4: Write the rule implementation**

Create `tools/lint/canonical/rules/py_print_smoke.py`:

```python
"""py-print-smoke — pipeline smoke-test rule.

Detects bare `print()` calls in production Python code. Aliases the existing
no-print-console pre-commit hook but routes through the canonical-check
registry — exists only to prove the pipeline. WARN severity so it never blocks.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from tools.lint.canonical.context import Context
from tools.lint.canonical.diagnostic import Diagnostic

RULE_ID = "py-print-smoke"
ISSUE = "#7458"
SEVERITY = "warn"
TARGETS = ["autobot-backend", "autobot-slm-backend", "autobot_shared", "tests/lint/canonical/fixtures"]
DESCRIPTION = "print() in production code — pipeline smoke-test rule for canonical-check"
FIX_HINT = (
    "Replace print() with a logger call:\n"
    "    from autobot_shared.logging import get_logger\n"
    "    logger = get_logger(__name__)\n"
    "    logger.info(\"...\")"
)

_WAIVER = re.compile(r"#\s*canonical:\s*ignore\s+py-print-smoke\b")


def check(file_path: Path, tree: ast.AST, ctx: Context) -> list[Diagnostic]:
    try:
        source_lines = file_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    diagnostics: list[Diagnostic] = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
        ):
            continue
        line_idx = node.lineno - 1
        if 0 <= line_idx < len(source_lines) and _WAIVER.search(source_lines[line_idx]):
            continue
        snippet = source_lines[line_idx].strip() if 0 <= line_idx < len(source_lines) else ""
        diagnostics.append(
            Diagnostic(
                rule_id=RULE_ID,
                issue=ISSUE,
                severity=SEVERITY,
                file=file_path,
                line=node.lineno,
                col=node.col_offset,
                message="print() in production code — use logger",
                snippet=snippet[:120],
                fix_hint=FIX_HINT,
            )
        )
    return diagnostics
```

- [ ] **Step 5: Run all tests including the previously-deferred ones**

Run: `pytest tests/lint/canonical/ -v`
Expected: ALL pass (registry discovery test + py-print-smoke tests + runner explain test from Task 6 now succeed).

- [ ] **Step 6: Verify CLI smoke**

```bash
echo 'print("hi")' > /tmp/smoke.py
python tools/lint/canonical_check.py --files tests/lint/canonical/fixtures/py_print_smoke/positive.py --format json
```
Expected: JSON array with one element whose `rule_id` is `py-print-smoke`.

- [ ] **Step 7: Commit**

```bash
git add tools/lint/canonical/rules/py_print_smoke.py tests/lint/canonical/fixtures/py_print_smoke/ tests/lint/canonical/rules/test_py_print_smoke.py
git commit -m "feat(canonical-check): add py-print-smoke pipeline-validation rule (#7458)"
```

---

## Task 8: Infrastructure runner + smoke rule

**Files:**
- Create: `tools/lint/canonical_check_infra.py`
- Create: `tools/lint/canonical/infra_rules/sh_echo_debug_smoke.py`
- Create: `tests/lint/canonical/fixtures/sh_echo_debug_smoke/positive.sh`
- Create: `tests/lint/canonical/fixtures/sh_echo_debug_smoke/negative.sh`
- Test: `tests/lint/canonical/test_runner_infra_cli.py`
- Test: `tests/lint/canonical/rules/test_sh_echo_debug_smoke.py`

- [ ] **Step 1: Write the fixtures**

Create `tests/lint/canonical/fixtures/sh_echo_debug_smoke/positive.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
echo "DEBUG: about to start"
echo "all good"
```

Create `tests/lint/canonical/fixtures/sh_echo_debug_smoke/negative.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
echo "starting up"
echo "all good"
```

- [ ] **Step 2: Write the rule test**

Create `tests/lint/canonical/rules/test_sh_echo_debug_smoke.py`:

```python
"""Tests for the sh-echo-debug-smoke rule (Wave 0 infra smoke-test rule)."""
from pathlib import Path

import pytest

from tools.lint.canonical.infra_rules import sh_echo_debug_smoke

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sh_echo_debug_smoke"


def test_positive_fixture_produces_one_diagnostic():
    diags = sh_echo_debug_smoke.check(FIXTURES / "positive.sh")
    assert len(diags) == 1
    assert diags[0].rule_id == "sh-echo-debug-smoke"


def test_negative_fixture_produces_no_diagnostics():
    diags = sh_echo_debug_smoke.check(FIXTURES / "negative.sh")
    assert diags == []


def test_rule_metadata_present():
    for attr in ("RULE_ID", "ISSUE", "SEVERITY", "TARGETS", "DESCRIPTION", "FIX_HINT"):
        assert hasattr(sh_echo_debug_smoke, attr)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/lint/canonical/rules/test_sh_echo_debug_smoke.py -v`
Expected: 3 errors (`ModuleNotFoundError`).

- [ ] **Step 4: Write the rule**

Create `tools/lint/canonical/infra_rules/sh_echo_debug_smoke.py`:

```python
"""sh-echo-debug-smoke — infra-runner smoke-test rule.

Detects `echo "DEBUG: ..."` in shell scripts. Exists only to prove the infra
runner can find rules, run them, and report violations. WARN severity.
"""

from __future__ import annotations

import re
from pathlib import Path

from tools.lint.canonical.diagnostic import Diagnostic

RULE_ID = "sh-echo-debug-smoke"
ISSUE = "#7458"
SEVERITY = "warn"
TARGETS = ["scripts", "tests/lint/canonical/fixtures"]
DESCRIPTION = "echo DEBUG: in shell scripts — pipeline smoke-test rule"
FIX_HINT = "Use a structured logger or remove debug echoes before shipping."

_PATTERN = re.compile(r'echo\s+["\']?DEBUG:')


def check(file_path: Path) -> list[Diagnostic]:
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError:
        return []
    diagnostics: list[Diagnostic] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _PATTERN.search(line):
            diagnostics.append(
                Diagnostic(
                    rule_id=RULE_ID,
                    issue=ISSUE,
                    severity=SEVERITY,
                    file=file_path,
                    line=lineno,
                    col=line.index("echo"),
                    message='echo "DEBUG: ..." in shell script',
                    snippet=line.strip()[:120],
                    fix_hint=FIX_HINT,
                )
            )
    return diagnostics
```

- [ ] **Step 5: Write the runner CLI test**

Create `tests/lint/canonical/test_runner_infra_cli.py`:

```python
"""End-to-end CLI tests for the Infra runner."""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER = REPO_ROOT / "tools" / "lint" / "canonical_check_infra.py"
FIXTURES = REPO_ROOT / "tests" / "lint" / "canonical" / "fixtures" / "sh_echo_debug_smoke"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(RUNNER), *args],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )


def test_runner_clean_file_exits_zero():
    result = _run("--files", str(FIXTURES / "negative.sh"))
    assert result.returncode == 0


def test_runner_violation_produces_warning_but_exits_zero():
    # sh-echo-debug-smoke is severity=warn, so exit 0
    result = _run("--files", str(FIXTURES / "positive.sh"))
    assert result.returncode == 0
    assert "sh-echo-debug-smoke" in result.stderr


def test_runner_format_json():
    result = _run("--files", str(FIXTURES / "positive.sh"), "--format", "json")
    assert result.stdout.startswith("[")
    assert "sh-echo-debug-smoke" in result.stdout
```

- [ ] **Step 6: Run runner tests to verify they fail**

Run: `pytest tests/lint/canonical/test_runner_infra_cli.py -v`
Expected: 3 errors (runner missing).

- [ ] **Step 7: Write the infra runner**

Create `tools/lint/canonical_check_infra.py`:

```python
#!/usr/bin/env python3
"""Canonical-check Infrastructure runner.

Mirrors canonical_check.py but operates on shell scripts, Ansible YAML, and
Dockerfiles. Rules receive only the file path (no AST) — they parse the text
themselves with appropriate tooling (regex, PyYAML, etc.).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.lint.canonical.context import Context  # noqa: E402
from tools.lint.canonical.registry import discover_rules  # noqa: E402
from tools.lint.canonical.reporter import to_json, to_markdown, to_pretty  # noqa: E402

_RULES_PACKAGE = "tools.lint.canonical.infra_rules"
_INFRA_SUFFIXES = {".sh", ".yml", ".yaml"}


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--files", nargs="*", help="Files to check (pre-commit mode)")
    g.add_argument("--all", action="store_true", help="Walk all TARGETS (audit mode)")
    p.add_argument("--explain", help="Print rule rationale and exit")
    p.add_argument("--format", choices=["pretty", "markdown", "json"], default="pretty")
    p.add_argument("--output", help="Write output to file instead of stdout")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    rules = discover_rules(_RULES_PACKAGE)

    if args.explain:
        rule = next((r for r in rules if r.RULE_ID == args.explain), None)
        if rule is None:
            print(f"unknown rule: {args.explain}", file=sys.stderr)
            return 2
        print(f"{rule.RULE_ID} ({rule.ISSUE}) [{rule.SEVERITY}]")
        print(rule.DESCRIPTION)
        print()
        print("Fix:")
        print(rule.FIX_HINT)
        return 0

    if not args.files and not args.all:
        print("error: --files or --all required", file=sys.stderr)
        return 2

    ctx = Context(repo_root=_REPO_ROOT)

    if args.all:
        all_targets = sorted({t for r in rules for t in r.TARGETS})
        files = list(ctx.iter_targets(all_targets, suffixes=_INFRA_SUFFIXES))
        # Dockerfiles too — extension-less, but add by name match
        for target in all_targets:
            base = _REPO_ROOT / target
            if base.exists():
                files.extend(p for p in base.rglob("Dockerfile*") if p.is_file())
    else:
        files = [Path(f) for f in (args.files or [])]

    diagnostics = []
    start = time.monotonic()
    for f in files:
        for rule in rules:
            from tools.lint.canonical.context import file_in_targets
            if not file_in_targets(f, rule.TARGETS, repo_root=_REPO_ROOT):
                continue
            diagnostics.extend(rule.check(f))
    duration = time.monotonic() - start

    if args.format == "pretty":
        out = to_pretty(diagnostics)
        sink = sys.stderr
    elif args.format == "markdown":
        out = to_markdown(diagnostics, scan_meta={
            "scanned_files": len(files), "duration_seconds": duration, "rule_count": len(rules),
        })
        sink = sys.stdout
    else:
        out = to_json(diagnostics)
        sink = sys.stdout

    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
    else:
        sink.write(out)
        if not out.endswith("\n"):
            sink.write("\n")

    blocking = sum(1 for d in diagnostics if d.severity == "block")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 8: Mark infra runner executable**

```bash
chmod +x tools/lint/canonical_check_infra.py
```

- [ ] **Step 9: Run all infra tests**

Run: `pytest tests/lint/canonical/test_runner_infra_cli.py tests/lint/canonical/rules/test_sh_echo_debug_smoke.py -v`
Expected: 6 PASS

- [ ] **Step 10: Commit**

```bash
git add tools/lint/canonical_check_infra.py tools/lint/canonical/infra_rules/sh_echo_debug_smoke.py tests/lint/canonical/fixtures/sh_echo_debug_smoke/ tests/lint/canonical/rules/test_sh_echo_debug_smoke.py tests/lint/canonical/test_runner_infra_cli.py
git commit -m "feat(canonical-check): add infra runner + sh-echo-debug-smoke rule (#7458)"
```

---

## Task 9: Frontend runner + smoke rule

**Files:**
- Create: `autobot-frontend/scripts/canonical/diagnostic.mjs`
- Create: `autobot-frontend/scripts/canonical/registry.mjs`
- Create: `autobot-frontend/scripts/canonical/reporter.mjs`
- Create: `autobot-frontend/scripts/canonical/rules/fe_console_log_smoke.mjs`
- Create: `autobot-frontend/scripts/canonical_check.mjs`
- Create: `autobot-frontend/scripts/canonical/__tests__/runner.test.mjs`
- Create: `autobot-frontend/scripts/canonical/__tests__/fixtures/positive.ts`
- Create: `autobot-frontend/scripts/canonical/__tests__/fixtures/negative.ts`

- [ ] **Step 1: Write the fixtures**

Create `autobot-frontend/scripts/canonical/__tests__/fixtures/positive.ts`:

```ts
export function greet(): void {
  console.log("hello world");
}
```

Create `autobot-frontend/scripts/canonical/__tests__/fixtures/negative.ts`:

```ts
import { logger } from "@/utils/logger";

export function greet(): void {
  logger.info("hello world");
}
```

- [ ] **Step 2: Write the diagnostic shape**

Create `autobot-frontend/scripts/canonical/diagnostic.mjs`:

```javascript
// Mirror of tools/lint/canonical/diagnostic.py
const VALID_SEVERITIES = new Set(["block", "warn", "audit"]);

export function makeDiagnostic({
  ruleId, issue, severity, file, line, col, message, snippet,
  fixHint = "", autoFixable = false,
}) {
  if (!VALID_SEVERITIES.has(severity)) {
    throw new Error(`severity must be one of [block, warn, audit], got ${severity}`);
  }
  return Object.freeze({
    rule_id: ruleId,
    issue,
    severity,
    file: String(file),
    line,
    col,
    message,
    snippet,
    fix_hint: fixHint,
    auto_fixable: autoFixable,
  });
}
```

- [ ] **Step 3: Write the registry**

Create `autobot-frontend/scripts/canonical/registry.mjs`:

```javascript
import { readdir } from "node:fs/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REQUIRED_KEYS = ["RULE_ID", "ISSUE", "SEVERITY", "TARGETS", "DESCRIPTION", "FIX_HINT", "check"];

export async function discoverRules(rulesDir = join(__dirname, "rules")) {
  let entries;
  try {
    entries = await readdir(rulesDir, { withFileTypes: true });
  } catch {
    return [];
  }
  const rules = [];
  for (const entry of entries) {
    if (!entry.isFile() || !entry.name.endsWith(".mjs") || entry.name.startsWith("_")) continue;
    const url = pathToFileURL(join(rulesDir, entry.name));
    const mod = await import(url.href);
    if (REQUIRED_KEYS.every((k) => k in mod)) {
      rules.push(mod);
    }
  }
  return rules;
}

export async function runRules(rules, files) {
  const diagnostics = [];
  for (const file of files) {
    for (const rule of rules) {
      diagnostics.push(...(await rule.check(file)));
    }
  }
  return diagnostics;
}
```

- [ ] **Step 4: Write the reporter**

Create `autobot-frontend/scripts/canonical/reporter.mjs`:

```javascript
export function toPretty(diagnostics) {
  if (diagnostics.length === 0) return "canonical-check: 0 violations\n";
  const counts = { block: 0, warn: 0, audit: 0 };
  for (const d of diagnostics) counts[d.severity]++;
  const lines = [
    `canonical-check: ${diagnostics.length} violations (block=${counts.block}, warn=${counts.warn}, audit=${counts.audit})`,
  ];
  const grouped = new Map();
  for (const d of diagnostics) {
    if (!grouped.has(d.file)) grouped.set(d.file, []);
    grouped.get(d.file).push(d);
  }
  for (const [file, ds] of [...grouped.entries()].sort()) {
    for (const d of ds.sort((a, b) => a.line - b.line || a.col - b.col)) {
      lines.push(`  ${file}:${d.line}  ${d.rule_id}  (${d.issue}) [${d.severity}]`);
      lines.push(`    ${d.message}`);
    }
  }
  return lines.join("\n") + "\n";
}

export function toJson(diagnostics) {
  return JSON.stringify(diagnostics, null, 2);
}
```

- [ ] **Step 5: Write the smoke rule**

Create `autobot-frontend/scripts/canonical/rules/fe_console_log_smoke.mjs`:

```javascript
import { readFile } from "node:fs/promises";

import { makeDiagnostic } from "../diagnostic.mjs";

export const RULE_ID = "fe-console-log-smoke";
export const ISSUE = "#7458";
export const SEVERITY = "warn";
export const TARGETS = ["autobot-frontend/src", "autobot-frontend/scripts/canonical/__tests__/fixtures"];
export const DESCRIPTION = "console.log() in frontend code — pipeline smoke-test rule";
export const FIX_HINT = "Use the canonical logger from @/utils/logger";

const PATTERN = /\bconsole\.log\s*\(/;
const WAIVER = /\/\/\s*canonical:\s*ignore\s+fe-console-log-smoke\b/;

export async function check(filePath) {
  let text;
  try {
    text = await readFile(filePath, "utf-8");
  } catch {
    return [];
  }
  const lines = text.split(/\r?\n/);
  const diagnostics = [];
  lines.forEach((line, idx) => {
    if (PATTERN.test(line) && !WAIVER.test(line)) {
      diagnostics.push(makeDiagnostic({
        ruleId: RULE_ID,
        issue: ISSUE,
        severity: SEVERITY,
        file: filePath,
        line: idx + 1,
        col: line.search(PATTERN),
        message: "console.log() in production code — use logger",
        snippet: line.trim().slice(0, 120),
        fixHint: FIX_HINT,
      }));
    }
  });
  return diagnostics;
}
```

- [ ] **Step 6: Write the runner CLI**

Create `autobot-frontend/scripts/canonical_check.mjs`:

```javascript
#!/usr/bin/env node
import { argv, exit, stderr, stdout } from "node:process";
import { writeFile } from "node:fs/promises";

import { discoverRules, runRules } from "./canonical/registry.mjs";
import { toJson, toPretty } from "./canonical/reporter.mjs";

function parseArgs(rawArgs) {
  const args = { files: [], all: false, format: "pretty", explain: null, output: null };
  for (let i = 0; i < rawArgs.length; i++) {
    const a = rawArgs[i];
    if (a === "--files") {
      while (i + 1 < rawArgs.length && !rawArgs[i + 1].startsWith("--")) {
        args.files.push(rawArgs[++i]);
      }
    } else if (a === "--all") {
      args.all = true;
    } else if (a === "--explain") {
      args.explain = rawArgs[++i];
    } else if (a === "--format") {
      args.format = rawArgs[++i];
    } else if (a === "--output") {
      args.output = rawArgs[++i];
    }
  }
  return args;
}

async function main() {
  const args = parseArgs(argv.slice(2));
  const rules = await discoverRules();

  if (args.explain) {
    const rule = rules.find((r) => r.RULE_ID === args.explain);
    if (!rule) {
      stderr.write(`unknown rule: ${args.explain}\n`);
      return 2;
    }
    stdout.write(`${rule.RULE_ID} (${rule.ISSUE}) [${rule.SEVERITY}]\n`);
    stdout.write(`${rule.DESCRIPTION}\n\nFix:\n${rule.FIX_HINT}\n`);
    return 0;
  }

  if (args.files.length === 0 && !args.all) {
    stderr.write("error: --files or --all required\n");
    return 2;
  }

  // Wave 0: only --files mode is supported. --all walking is a Wave 3 task.
  const files = args.files.filter((f) => /\.(ts|vue|mjs|js)$/.test(f));
  const diagnostics = await runRules(rules, files);

  let out;
  let sink = stderr;
  if (args.format === "pretty") {
    out = toPretty(diagnostics);
  } else if (args.format === "json") {
    out = toJson(diagnostics);
    sink = stdout;
  } else {
    stderr.write(`format ${args.format} not implemented in Wave 0\n`);
    return 2;
  }

  if (args.output) {
    await writeFile(args.output, out, "utf-8");
  } else {
    sink.write(out);
    if (!out.endsWith("\n")) sink.write("\n");
  }

  return diagnostics.some((d) => d.severity === "block") ? 1 : 0;
}

main().then((code) => exit(code)).catch((err) => {
  stderr.write(`${err.stack || err}\n`);
  exit(2);
});
```

- [ ] **Step 7: Mark frontend runner executable**

```bash
chmod +x autobot-frontend/scripts/canonical_check.mjs
```

- [ ] **Step 8: Write the runner test**

Create `autobot-frontend/scripts/canonical/__tests__/runner.test.mjs`:

```javascript
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { describe, it, expect } from "vitest";

const __dirname = dirname(fileURLToPath(import.meta.url));
const RUNNER = join(__dirname, "..", "..", "canonical_check.mjs");
const FIXTURES = join(__dirname, "fixtures");

function run(...args) {
  return spawnSync("node", [RUNNER, ...args], { encoding: "utf-8" });
}

describe("frontend canonical-check runner", () => {
  it("exits 0 on clean file", () => {
    const r = run("--files", join(FIXTURES, "negative.ts"));
    expect(r.status).toBe(0);
  });

  it("warns on console.log but exits 0 (severity=warn)", () => {
    const r = run("--files", join(FIXTURES, "positive.ts"));
    expect(r.status).toBe(0);
    expect(r.stderr).toContain("fe-console-log-smoke");
  });

  it("--format json emits a JSON array", () => {
    const r = run("--files", join(FIXTURES, "positive.ts"), "--format", "json");
    expect(r.stdout.trim().startsWith("[")).toBe(true);
    expect(r.stdout).toContain("fe-console-log-smoke");
  });

  it("--explain prints rule metadata", () => {
    const r = run("--explain", "fe-console-log-smoke");
    expect(r.status).toBe(0);
    expect(r.stdout).toContain("fe-console-log-smoke");
  });

  it("--explain unknown rule exits 2", () => {
    const r = run("--explain", "no-such-rule");
    expect(r.status).toBe(2);
  });
});
```

- [ ] **Step 9: Run frontend tests**

Run: `cd autobot-frontend && npx vitest run scripts/canonical/__tests__/runner.test.mjs`
Expected: 5 PASS

- [ ] **Step 10: Commit**

```bash
git add autobot-frontend/scripts/canonical/ autobot-frontend/scripts/canonical_check.mjs
git commit -m "feat(canonical-check): add frontend runner with fe-console-log-smoke rule (#7458)"
```

---

## Task 10: Makefile targets

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Read existing Makefile**

```bash
head -40 Makefile
```

Note the existing target style and `.PHONY` declarations.

- [ ] **Step 2: Append new targets**

Add to end of `Makefile`:

```makefile

# ─── Canonical-style checks (#7458) ──────────────────────────────────────────

.PHONY: canonical-check canonical-check-py canonical-check-fe canonical-check-infra canonical-audit

canonical-check: canonical-check-py canonical-check-fe canonical-check-infra
	@echo "canonical-check: all layers passed"

canonical-check-py:
	@python tools/lint/canonical_check.py --all --format pretty || \
		(echo "canonical-check-py: violations found"; exit 1)

canonical-check-fe:
	@cd autobot-frontend && find src -type f \( -name '*.ts' -o -name '*.vue' \) \
		-print0 2>/dev/null | xargs -0 --no-run-if-empty node scripts/canonical_check.mjs --files

canonical-check-infra:
	@find scripts -type f \( -name '*.sh' -o -name '*.yml' -o -name '*.yaml' \) \
		-print0 2>/dev/null | xargs -0 --no-run-if-empty python tools/lint/canonical_check_infra.py --files

canonical-audit:
	@mkdir -p .canonical-audit
	@python tools/lint/canonical_check.py --all --format markdown \
		--output .canonical-audit/canonical-audit-py-$$(date -u +%Y-%m-%d).md
	@python tools/lint/canonical_check_infra.py --all --format markdown \
		--output .canonical-audit/canonical-audit-infra-$$(date -u +%Y-%m-%d).md
	@echo "canonical-audit: report written to .canonical-audit/"
```

- [ ] **Step 3: Verify targets exist**

Run: `make -n canonical-check 2>&1 | head -5`
Expected: prints commands that would run.

- [ ] **Step 4: Run canonical-check on smoke fixtures**

Run: `python tools/lint/canonical_check.py --files tests/lint/canonical/fixtures/py_print_smoke/positive.py`
Expected: exit 0 (warn only), one diagnostic on stderr.

- [ ] **Step 5: Commit**

```bash
git add Makefile
git commit -m "feat(canonical-check): add Makefile targets for canonical-check and audit (#7458)"
```

---

## Task 11: Pre-commit hook entries

**Files:**
- Modify: `.pre-commit-config.yaml`

- [ ] **Step 1: Read the existing pre-commit config tail**

```bash
tail -25 .pre-commit-config.yaml
```

Confirm the file ends with the bootstrap-install hooks block.

- [ ] **Step 2: Insert three new hooks before the global `default_language_version` block**

Open `.pre-commit-config.yaml`, find the line `# Configuration for specific file types` and add the following block immediately above it (still inside the top-level `repos:` list, indented as a single `- repo: local` block followed by hooks):

```yaml
  # AutoBot custom: canonical-check Wave 0 (#7458). The three runners discover
  # rule modules from their respective registries and emit pre-commit-style
  # violations on staged files only. BLOCK-severity rules fail the commit;
  # WARN/AUDIT rules print but exit 0. See docs/developer/CANONICAL_RULES.md.
  - repo: local
    hooks:
      - id: canonical-check-py
        name: Canonical check — Python (#7458)
        entry: python tools/lint/canonical_check.py --files
        language: python
        files: \.py$
        exclude: ^(\.worktrees/|tests/lint/canonical/fixtures/)
        stages: [pre-commit]
        description: "Pluggable canonical-pattern checks for Python files (#7458)"

      - id: canonical-check-fe
        name: Canonical check — Frontend (#7458)
        entry: node autobot-frontend/scripts/canonical_check.mjs --files
        language: system
        files: ^autobot-frontend/.*\.(ts|vue|mjs|js)$
        exclude: ^(autobot-frontend/node_modules/|autobot-frontend/dist/)
        stages: [pre-commit]
        description: "Pluggable canonical-pattern checks for Vue/TS files (#7458)"

      - id: canonical-check-infra
        name: Canonical check — Infrastructure (#7458)
        entry: python tools/lint/canonical_check_infra.py --files
        language: python
        files: \.(sh|yml|yaml)$
        exclude: ^(\.worktrees/|node_modules/|tests/lint/canonical/fixtures/)
        stages: [pre-commit]
        description: "Pluggable canonical-pattern checks for shell/YAML files (#7458)"
```

- [ ] **Step 3: Verify pre-commit accepts the config**

Run: `pre-commit run canonical-check-py --files tests/lint/canonical/fixtures/py_print_smoke/positive.py`
Expected: prints diagnostic on stderr, exits 0 (warn-only rule).

- [ ] **Step 4: Verify pre-commit BLOCK enforcement (manual check)**

Temporarily flip `py-print-smoke`'s `SEVERITY = "warn"` to `"block"` in the rule file, then re-run:

Run: `pre-commit run canonical-check-py --files tests/lint/canonical/fixtures/py_print_smoke/positive.py; echo "exit=$?"`
Expected: `exit=1`

Restore `SEVERITY = "warn"` afterwards (no commit of this temporary change).

- [ ] **Step 5: Commit**

```bash
git add .pre-commit-config.yaml
git commit -m "feat(canonical-check): wire 3 pre-commit hooks for Python/Frontend/Infra runners (#7458)"
```

---

## Task 12: GitHub Actions weekly cron

**Files:**
- Create: `.github/workflows/canonical-audit.yml`

- [ ] **Step 1: Verify directory exists**

```bash
ls .github/workflows/ | head -5
```

Expected: existing workflow files visible.

- [ ] **Step 2: Create the workflow**

Create `.github/workflows/canonical-audit.yml`:

```yaml
name: canonical-audit

on:
  schedule:
    - cron: "0 3 * * 1"  # Mondays 03:00 UTC
  workflow_dispatch:

permissions:
  contents: read
  actions: read

concurrency:
  group: canonical-audit-${{ github.ref }}
  cancel-in-progress: false

jobs:
  audit:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11  # v4.1.1
        with:
          fetch-depth: 1

      - uses: actions/setup-python@0a5c61591373683505ea898e09a3ea4f39ef2b9c  # v5.0.0
        with:
          python-version: "3.11"

      - uses: actions/setup-node@60edb5dd545a775178f52524783378180af0d1f8  # v4.0.2
        with:
          node-version: "20"

      - name: Generate audit reports
        id: audit
        run: |
          DATE=$(date -u +%Y-%m-%d)
          mkdir -p audit-output
          python tools/lint/canonical_check.py --all --format markdown \
            --output audit-output/canonical-audit-py-$DATE.md
          python tools/lint/canonical_check.py --all --format json \
            --output audit-output/canonical-audit-py-$DATE.json
          python tools/lint/canonical_check_infra.py --all --format markdown \
            --output audit-output/canonical-audit-infra-$DATE.md
          python tools/lint/canonical_check_infra.py --all --format json \
            --output audit-output/canonical-audit-infra-$DATE.json
          # Frontend audit deferred to Wave 3 (no --all support yet); empty placeholder
          echo "# Canonical-style audit — Frontend ($DATE)" > audit-output/canonical-audit-fe-$DATE.md
          echo "Frontend full-codebase audit not yet implemented (Wave 3)." >> audit-output/canonical-audit-fe-$DATE.md
          echo "date=$DATE" >> "$GITHUB_OUTPUT"

      - name: Upload audit artifact
        uses: actions/upload-artifact@26f96dfa697d77e81fd5907df203aa23a56210a8  # v4.3.0
        with:
          name: canonical-audit-${{ steps.audit.outputs.date }}
          path: audit-output/
          retention-days: 365
          if-no-files-found: error

      - name: Job summary
        run: |
          echo "## Canonical audit — ${{ steps.audit.outputs.date }}" >> $GITHUB_STEP_SUMMARY
          for f in audit-output/*.md; do
            echo "" >> $GITHUB_STEP_SUMMARY
            cat "$f" >> $GITHUB_STEP_SUMMARY
          done
```

- [ ] **Step 3: Verify YAML parses**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/canonical-audit.yml'))"`
Expected: no output (valid YAML).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/canonical-audit.yml
git commit -m "feat(canonical-check): add weekly GitHub Actions cron uploading audit artifacts (#7458)"
```

---

## Task 13: /canonical-audit slash command skill

**Files:**
- Create: `.claude/skills/canonical-audit/SKILL.md`

- [ ] **Step 1: Verify directory layout**

```bash
ls .claude/skills/ | head -10
```

Expected: existing skill directories visible.

- [ ] **Step 2: Create the skill**

Create `.claude/skills/canonical-audit/SKILL.md`:

```markdown
---
name: canonical-audit
description: Run a full-codebase canonical-pattern audit and write a markdown report to .canonical-audit/. Use when the user asks for a canonical-style scan, a #7458 progress check, or a periodic audit between cron runs.
---

# /canonical-audit

Runs the canonical-check Python and infra runners in `--all` mode and writes both markdown and JSON sidecars to `.canonical-audit/` (gitignored). Then summarizes the report inline.

## Steps

1. Verify the runners exist:
   ```bash
   test -f tools/lint/canonical_check.py && test -f tools/lint/canonical_check_infra.py || echo "ERROR: canonical-check not installed"
   ```

2. Run the audit via the Make target (also creates `.canonical-audit/` if missing):
   ```bash
   make canonical-audit
   ```

3. Read the most recent markdown reports:
   ```bash
   ls -1t .canonical-audit/*.md | head -3
   ```
   Open each and surface the Summary table to the user.

4. If any rule has BLOCK-severity violations, also surface the top 5 offending files for that rule.

5. Do NOT auto-file GitHub issues. Report findings inline. Filing is a separate user-driven step.

## Notes

- Frontend audit (`canonical-check-fe`) does not yet support `--all` mode (deferred to Wave 3). It is skipped here.
- Reports go to `.canonical-audit/` locally and to GitHub Actions artifacts on the weekly cron run. Neither is committed.
```

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/canonical-audit/SKILL.md
git commit -m "feat(canonical-check): add /canonical-audit slash command skill (#7458)"
```

---

## Task 14: Catalog skeleton (CANONICAL_RULES.md)

**Files:**
- Create: `docs/developer/CANONICAL_RULES.md`

- [ ] **Step 1: Create the catalog**

Create `docs/developer/CANONICAL_RULES.md`:

```markdown
# Canonical Rules Catalog

> **Tracking:** sub-umbrella [#7458](https://github.com/mrveiss/AutoBot-AI/issues/7458) of [#5060](https://github.com/mrveiss/AutoBot-AI/issues/5060)
> **Spec:** [`docs/superpowers/specs/2026-05-10-canonical-check-workflow-design.md`](../superpowers/specs/2026-05-10-canonical-check-workflow-design.md)

This file lists every canonical-pattern rule enforced by `tools/lint/canonical_check*.py` and `autobot-frontend/scripts/canonical_check.mjs`. Each rule has a stable `RULE_ID`, a tracking GitHub issue, and a severity. **BLOCK** rules fail pre-commit; **WARN** rules emit a notice; **AUDIT** rules appear only in the periodic audit report.

## How rules are organized

```
tools/lint/canonical/rules/        Python AST rules (run by canonical_check.py)
tools/lint/canonical/infra_rules/  Shell / YAML / Dockerfile rules (run by canonical_check_infra.py)
autobot-frontend/scripts/canonical/rules/  Vue / TS / JS rules (run by canonical_check.mjs)
```

Each rule module exports: `RULE_ID`, `ISSUE`, `SEVERITY`, `TARGETS`, `DESCRIPTION`, `FIX_HINT`, and a `check()` function.

## Wave 0 — foundation rules

| Rule ID | Issue | Layer | Severity | Description |
|---|---|---|---|---|
| `py-print-smoke` | #7458 | Python | warn | Pipeline smoke test — bare `print()` in production code |
| `sh-echo-debug-smoke` | #7458 | Infra | warn | Pipeline smoke test — `echo "DEBUG: ..."` in shell |
| `fe-console-log-smoke` | #7458 | Frontend | warn | Pipeline smoke test — `console.log()` in production code |

## Waves 1–5 — placeholder

The 22 production rules from sub-umbrella #7458 (#7435–#7457) and 4 bonus rules from MEMORY.md will land in subsequent waves. Each rule will be added to the table above in the same PR that adds the rule module.

## Waivers

Inline waiver:

```python
print("hi")  # canonical: ignore py-print-smoke — bootstrap script (#7458)
```

File-level waiver (top of file):

```python
# canonical: file-ignore py-pep604 — generated by openapi-codegen
```

A waiver without a `#NNNN` issue reference is itself a violation. Globally disabling a rule is not supported via waivers — edit the rule's registry instead, which appears in PR diffs and code review.

## Adding a new rule

1. Create `tools/lint/canonical/rules/py_<name>.py` (or appropriate package) exporting the rule contract.
2. Add positive / negative / waiver fixtures under `tests/lint/canonical/fixtures/<rule>/`.
3. Add `tests/lint/canonical/rules/test_<rule>.py` with at least 4 assertions (positive, negative, waiver, metadata).
4. Add a row to the table above.
5. File or reference a tracking issue under [#7458](https://github.com/mrveiss/AutoBot-AI/issues/7458).
```

- [ ] **Step 2: Commit**

```bash
git add docs/developer/CANONICAL_RULES.md
git commit -m "docs(canonical-check): add CANONICAL_RULES.md catalog skeleton (#7458)"
```

---

## Task 15: End-to-end verification + final commit

**Files:** none — verification only.

- [ ] **Step 1: Run the full Python test suite for canonical-check**

Run: `pytest tests/lint/canonical/ -v`
Expected: ALL pass (~25 tests).

- [ ] **Step 2: Run the frontend tests**

Run: `cd autobot-frontend && npx vitest run scripts/canonical/`
Expected: 5 PASS.

- [ ] **Step 3: Run pre-commit on a test file**

Run: `pre-commit run canonical-check-py --files tools/lint/canonical_check.py; echo "exit=$?"`
Expected: `exit=0` (the runner itself doesn't `print()`).

- [ ] **Step 4: Run pre-commit on the smoke fixture**

Run: `pre-commit run canonical-check-py --files tests/lint/canonical/fixtures/py_print_smoke/positive.py; echo "exit=$?"`
Expected: `exit=0` with stderr showing `py-print-smoke` violation (warn-only).

- [ ] **Step 5: Run the audit Make target**

Run: `make canonical-audit`
Expected: creates `.canonical-audit/canonical-audit-py-YYYY-MM-DD.md` and the matching infra report. The reports should not be committed (verify via `git status` — `.canonical-audit/` should not appear).

Run: `git status --short`
Expected: no `.canonical-audit/` lines.

- [ ] **Step 6: Run --explain for each smoke rule**

```bash
python tools/lint/canonical_check.py --explain py-print-smoke
python tools/lint/canonical_check_infra.py --explain sh-echo-debug-smoke
node autobot-frontend/scripts/canonical_check.mjs --explain fe-console-log-smoke
```
Expected: each prints rule metadata and exits 0.

- [ ] **Step 7: Final commit only if any tracked file remains uncommitted**

Run: `git status --short`
If empty, no commit needed. Wave 0 is complete.

If something is missing, add and commit:

```bash
git add -- <missing files>
git commit -m "feat(canonical-check): complete Wave 0 foundation (#7458)"
```

- [ ] **Step 8: Push branch and open PR**

```bash
git push -u origin <branch>
gh pr create --base Dev_new_gui --title "feat(canonical-check): Wave 0 foundation skeleton (#7458)" \
  --body "$(cat <<'EOF'
## Summary
- Three runners (Python AST, Frontend Vue/TS, Infra YAML/shell) with shared diagnostic schema
- Pluggable rule registry per layer with auto-discovery via pkgutil / dynamic import
- Pretty / markdown / JSON reporters
- One smoke-test rule per layer (py-print-smoke, sh-echo-debug-smoke, fe-console-log-smoke)
- Three pre-commit hooks (block on staged files only, matches existing 18-hook pattern)
- Weekly GitHub Actions cron uploading audit reports as 365-day artifacts
- /canonical-audit slash command skill
- docs/developer/CANONICAL_RULES.md catalog skeleton

Spec: docs/superpowers/specs/2026-05-10-canonical-check-workflow-design.md

## Test plan
- [ ] pytest tests/lint/canonical/ — all pass
- [ ] vitest scripts/canonical/ — all pass
- [ ] pre-commit run canonical-check-py against fixture — warn-only, exit 0
- [ ] make canonical-audit — generates reports in .canonical-audit/, not committed
- [ ] --explain works for all 3 smoke rules

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Acceptance Criteria

- All 25+ tests pass.
- `make canonical-check` runs in <30s on a clean checkout (no rules yet beyond smoke; trivially fast).
- `pre-commit run canonical-check-{py,fe,infra}` works for the relevant file types.
- `make canonical-audit` produces `.canonical-audit/*.md` and `.canonical-audit/*.json`, none committed.
- `python tools/lint/canonical_check.py --explain py-print-smoke` prints rule metadata.
- The 18 existing pre-commit hooks continue to function unchanged.
- `docs/developer/CANONICAL_RULES.md` lists each Wave 0 rule.
