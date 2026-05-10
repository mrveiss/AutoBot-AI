# Canonical-Check Workflow — Design Spec

**Date:** 2026-05-10
**Status:** Design — pending implementation plan
**Owner:** mrveiss
**Tracking umbrella:** #7458 (sub-umbrella of #5060)
**Related issues:** #7435–#7457 (22 canonical-pattern sub-issues)

---

## 1. Problem

AutoBot has accumulated 22 distinct canonical-pattern gaps across backend Python, frontend Vue/TS, and infrastructure (Ansible, Docker, shell). Each one is tracked as a sub-issue under epic #7458 (e.g. `logging.getLogger(__name__)` vs `get_logger()`, Pydantic v1 vs v2, hardcoded TTLs vs env-resolved constants). The repo already enforces 18 canonical patterns via custom pre-commit hooks under `tools/lint/check_*.py` and `autobot-infrastructure/shared/scripts/hooks/`, but those grew organically — one hook per past regression — and there is no shared registry, taxonomy, or reporting layer.

The result: new canonical drift goes undetected until either (a) a manual audit catches it, or (b) it causes a production incident. Existing hooks are 18 disconnected scripts with no unified reporting, no trend tracking, and no way to scan the whole codebase for legacy violations without writing one-off greps.

This design adds a **canonical-check workflow** that:

1. Enforces the 22 #7458 patterns at commit time (extending the existing per-rule pre-commit pattern).
2. Provides a periodic full-codebase audit producing a markdown report with trend lines.
3. Consolidates rule definitions in a registry so adding a new rule is a single-file change instead of a new pre-commit YAML entry plus a new script plus a new test fixture directory.

## 2. Goals / Non-Goals

**Goals**

- Single registry for canonical rules across backend Python, frontend Vue/TS, and infrastructure (YAML/shell).
- Pre-commit enforcement on staged files only (matches existing 18-hook pattern; no big-bang migration).
- Periodic `/canonical-audit` slash command + weekly CI cron producing a markdown report with trends.
- Strictly additive — does not remove or replace any of the 18 existing hooks during initial rollout.
- All 22 #7458 sub-issues have a corresponding rule module by end of rollout.

**Non-goals (v1)**

- Auto-fix mode (`--fix`). The diagnostic schema reserves `auto_fixable: bool` but no rule ships with auto-fix in v1.
- IDE integration (LSP). Rules run as CLI; IDE integration is a follow-up.
- Auto-filing GitHub issues from audit output. The audit is markdown-report-only; humans triage.
- Replacing the 18 existing hooks. Consolidation is deferred to a post-rollout follow-up.
- Cross-language deduplication of rule logic. Each layer uses its native AST tool.

## 3. Architecture

Three independent runners, one orchestrator (`make canonical-check`).

### 3.1 Layout

```
tools/lint/canonical_check.py                 # Python runner (entry point)
tools/lint/canonical/
  __init__.py
  registry.py                                 # Rule discovery + execution engine
  context.py                                  # Shared AST cache, file iterator, diagnostic types
  reporter.py                                 # Markdown report + machine-readable JSON
  rules/                                      # 11 backend rule modules
    py_error_decorator.py                     # #7435
    py_datetime_now.py                        # #7436
    py_config_ssot.py                         # #7437
    py_get_logger.py                          # #7438
    py_redis_factory.py                       # #7439 (extends existing no-direct-redis)
    py_constants.py                           # #7440
    py_sqlalchemy_session.py                  # #7441
    py_pydantic_v2.py                         # #7442
    py_pep604_typing.py                       # #7443
    py_blocking_io.py                         # #7444 (catalog-only; existing hook covers it)
    py_singleton_lazy.py                      # #7445
  bonus_rules/                                # 4 extras harvested from MEMORY.md
    py_relative_path_guard.py
    py_aiohttp_streaming.py
    py_fastapi_204_response_model.py
    sh_gh_pr_edit_body.py
autobot-frontend/scripts/canonical_check.mjs  # Frontend runner
autobot-frontend/scripts/canonical/
  rules/                                      # 8 frontend rule modules
    fe_use_api.mjs                            # #7446
    fe_error_handler.mjs                      # #7447
    fe_notification_bus.mjs                   # #7448
    fe_slm_alignment.mjs                      # #7449
    fe_date_fns.mjs                           # #7450
    fe_pagination.mjs                         # #7451
    fe_composables_contract.mjs               # #7452
    fe_css_theming.mjs                        # #7453
tools/lint/canonical_check_infra.py           # Infrastructure runner
tools/lint/canonical/infra_rules/             # 4 infrastructure rule modules
  infra_ansible_become.py                     # #7454
  infra_pipefail.py                           # #7455
  infra_docker_healthcheck.py                 # #7456
  infra_module_docstring.py                   # #7457
.pre-commit-config.yaml                       # +3 entries (one per runner)
Makefile                                      # `canonical-check`, `canonical-check-fix`
.github/workflows/canonical-audit.yml         # Weekly cron — Mondays 03:00 UTC
.claude/skills/canonical-audit/SKILL.md       # /canonical-audit slash command
docs/canonical-audit/                         # Reports checked in for trend visibility
  canonical-audit-2026-05-MM.md
  latest.md -> ...                            # Symlink to newest
docs/developer/CANONICAL_RULES.md             # Human-readable catalog
```

### 3.2 Rule module contract

Every rule module exports the same shape:

```python
RULE_ID = "py-datetime-now"          # stable identifier; used in waivers + reports
ISSUE = "#7436"                       # GitHub issue tracking the canonical
SEVERITY = "block"                    # "block" | "warn" | "audit"
TARGETS = ["autobot-backend", "autobot-slm-backend", "autobot_shared"]
DESCRIPTION = "..."                   # one-line human description
FIX_HINT = "..."                      # multi-line replacement template

def check(file_path: Path, tree: ast.AST, ctx: Context) -> list[Diagnostic]: ...
```

Frontend rules use the same shape with `mjs` exports; infra rules use the same shape against the parsed YAML/shell AST.

### 3.3 Modes

- **Pre-commit mode** — runner receives `--files <staged>`, runs all rules over those files only. Returns non-zero on any BLOCK violation. WARN violations are printed but exit 0.
- **Audit mode** — `--all` walks the entire codebase, ignores `--files`, emits a markdown report + JSON sidecar.
- **Explain mode** — `--explain <rule_id>` prints the rule's rationale, canonical replacement, and link to its #7458 issue.

## 4. Rule Taxonomy

26 rules total: 22 from #7458 + 4 bonus rules from past incident memory.

### 4.1 Backend Python (11 rules)

| Rule ID | Issue | Detects | Canonical | Severity | Scale |
|---|---|---|---|---|---|
| `py-error-decorator` | #7435 | `try/except` in `api/` routers; stacked `@with_error_handling` (refines existing `decorator-order`) | `@with_error_handling` between `@router` and `def` | BLOCK | 300+ files |
| `py-datetime-now` | #7436 | `datetime.utcnow()`, `datetime.now()` without `tz=`, `datetime.now(timezone.utc)` (refines existing `no-utcnow-isoformat`) | `from autobot_shared.time_utils import datetime_now` | BLOCK | 20+ files |
| `py-config-ssot` | #7437 | `os.getenv()`, `os.environ[...]` outside SSOT module + allowlist | `from autobot_shared.ssot_config import config` | BLOCK | 504 callsites |
| `py-get-logger` | #7438 | `logging.getLogger(__name__)` in production | `from autobot_shared.logging import get_logger` | BLOCK | 1,221 callsites |
| `py-redis-factory` | #7439 | (Existing `no-direct-redis` covers `redis.Redis()`.) Extension flags `get_redis_client(async_client=True)` | `get_async_redis_client()` for async paths | BLOCK | 325 files |
| `py-constants` | #7440 | Magic literals matching values in `autobot_shared/constants/`; hardcoded TTLs | Import from canonical module or env-resolved module-level constant | WARN | 13 files |
| `py-sqla-session` | #7441 | `Session()`, `sessionmaker()()`, `engine.connect()` outside session factory | `with get_session() as session:` | BLOCK | 101 files |
| `py-pydantic-v2` | #7442 | `class Config:`, `.dict()`, `.json()`, `@validator`, `@root_validator`, `parse_obj`, `parse_raw` | `model_config = ConfigDict(...)`, `.model_dump()`, `@field_validator`, `model_validate` | BLOCK | 281 files |
| `py-pep604` | #7443 | `Optional[X]`, `Union[X,Y]`, `List[X]`, `Dict[K,V]`, missing return-type annotations | `X \| None`, `list[X]`, `-> T` | WARN | 8,000+ |
| `py-blocking-io` | #7444 | (Catalog-only — existing `no-blocking-io-in-async` enforces.) | (existing) | BLOCK | resolved |
| `py-singleton` | #7445 | Class-level `_instance = None` + custom `__new__` | `lazy_singleton(Class)` | WARN | 62 files |

### 4.2 Frontend Vue/TS (8 rules)

| Rule ID | Issue | Detects | Canonical | Severity |
|---|---|---|---|---|
| `fe-use-api` | #7446 | Direct `fetch(`, `axios(`, raw `apiClient.` outside `composables/useApi*` | `useApi().get/post/...` | BLOCK |
| `fe-error-handler` | #7447 | `try { ... } catch { console.error / toast.error }` in components | `useErrorHandler().handle(e)` | WARN |
| `fe-notification-bus` | #7448 | Direct `toast.*`, `notify(`, `vue-sonner` outside canonical composable | `useNotifications().success/error/info` | BLOCK |
| `fe-slm-alignment` | #7449 | SLM frontend: missing `useNotifications`, wrong icon family, missing `router.meta.hideFooter`, ad-hoc breadcrumbs | Match autobot-frontend canonical | WARN |
| `fe-date-fns` | #7450 | `.toLocaleString()`, `Date.parse()`, manual `${y}-${m}-${d}` for dates | `format()`, `parseISO()` from `date-fns` | WARN |
| `fe-pagination` | #7451 | Component-local `ref(1)`/`pageSize` for list pagination | `usePagination()` composable | WARN |
| `fe-composables-contract` | #7452 | Composables exporting bare values, not `{ data, loading, error, refetch }` | Canonical return shape | WARN |
| `fe-css-theming` | #7453 | Hex/rgb literals in `<style>` blocks | `var(--color-*)`, theme tokens | WARN |

### 4.3 Infrastructure (4 rules)

| Rule ID | Issue | Detects | Canonical | Severity |
|---|---|---|---|---|
| `infra-ansible-become` | #7454 | `become: yes` without `become_user:` | Explicit `become_user:` | WARN |
| `infra-pipefail` | #7455 | `*.sh` with `set -e` only or no `set` | `set -euo pipefail` | BLOCK |
| `infra-docker-healthcheck` | #7456 | Dockerfile services without `HEALTHCHECK`; shell-form `HEALTHCHECK CMD` | Exec-form `HEALTHCHECK CMD ["..."]` | WARN |
| `infra-module-docstring` | #7457 | Python modules >50 LOC without top-level docstring | Top-level `"""..."""` | AUDIT |

### 4.4 Bonus rules from MEMORY.md "Key Discoveries" (4 rules)

| Rule ID | Detects | Why | Severity |
|---|---|---|---|
| `py-relative-path-guard` | `os.path.join(BASE, user_input)` without `os.path.isabs()` check | Past denylist-bypass incident | BLOCK |
| `py-aiohttp-streaming` | `ClientTimeout(total=X)` on streaming endpoints | Caps stream length; should be `total=None, connect=X` | WARN |
| `py-fastapi-204-response-model` | `@router.delete(... status_code=204, response_model=...)` | FastAPI raises AssertionError (#6195) | BLOCK |
| `sh-gh-pr-edit-body` | `gh pr edit --body` in scripts | Silently fails (GraphQL); use `gh api ... -X PATCH` | WARN |

**Totals:** 27 rule modules (26 new + 1 catalog-only for `py-blocking-io`) — 13 BLOCK / 13 WARN / 1 AUDIT.

## 5. Diagnostic Schema and Output

### 5.1 Diagnostic JSON shape

Shared by all 3 runners; emitted to stderr in pre-commit, aggregated to JSON sidecar in audit:

```json
{
  "rule_id": "py-get-logger",
  "issue": "#7438",
  "severity": "block",
  "file": "autobot-backend/api/foo.py",
  "line": 42,
  "col": 5,
  "message": "logging.getLogger(__name__) — use autobot_shared.logging.get_logger",
  "snippet": "logger = logging.getLogger(__name__)",
  "fix_hint": "from autobot_shared.logging import get_logger\nlogger = get_logger(__name__)",
  "auto_fixable": false
}
```

### 5.2 Pre-commit output (terse)

```
canonical-check: 3 violations in 2 files (block)
  autobot-backend/api/foo.py:42  py-get-logger  (#7438)
    use autobot_shared.logging.get_logger() instead of logging.getLogger(__name__)
  autobot-backend/api/foo.py:91  py-datetime-now  (#7436)
    datetime.utcnow() — use autobot_shared.time_utils.datetime_now()
  autobot-backend/services/bar.py:12  py-pydantic-v2  (#7442)
    .dict() is Pydantic v1 — use .model_dump()

Run `python tools/lint/canonical_check.py --explain py-get-logger` for rationale.
```

### 5.3 Audit report

`docs/canonical-audit/canonical-audit-YYYY-MM-DD.md` — committed for trend visibility.

```markdown
# Canonical-style audit — 2026-05-10
27 rules · 3 layers · scanned 4,127 files in 38s

## Summary
| Severity | Total | New (vs 2026-05-03) | Top rule |
|---|---|---|---|
| block | 482 | +14 | py-pydantic-v2 (193) |
| warn  | 2,901 | -120 | py-pep604 (2,604) |
| audit | 38 | +0 | infra-module-docstring (38) |

## By Rule
### py-pydantic-v2 (#7442) — 193 violations in 41 files (block)
Top files:
- autobot-backend/services/agent_service.py — 24 violations
- autobot-backend/api/schemas_workflows.py — 18 violations
- ...

## Trend
Block-severity violations over time:
2026-04-26: 612
2026-05-03: 496
2026-05-10: 482  ↓ 14 (3%)

## Rules with zero violations
- py-blocking-io, py-redis-factory, py-relative-path-guard, infra-pipefail
```

A `latest.md` symlink in `docs/canonical-audit/` always points at the newest scan.

## 6. Waivers

Two mechanisms, both per-violation, both required-justification:

1. **Inline:** `# canonical: ignore <rule_id> — <reason> (#issue)` at end of offending line.
2. **File-level:** top-of-file `# canonical: file-ignore <rule_id> — <reason>`.

A waiver without a matching `#NNNN` issue reference is itself a violation reported by `canonical-waiver-needs-issue` (registry-internal rule, not in the 26 count).

A third "rule-disabled-globally" mechanism is **deliberately not provided** — globally disabling a rule requires editing the registry's rule list (visible in PR diff and code review). This matches the existing 18-hook pattern.

## 7. Rollout Plan

### Wave 0 — Foundation (1 PR)
Runner skeletons (Python, Frontend, Infra), Makefile targets, weekly cron workflow, `/canonical-audit` slash command, one trivial smoke-test rule per layer (e.g. `py-print` aliasing existing `no-print-console`) to prove the pipeline.

### Wave 1 — High-priority backend BLOCK rules (1 PR per rule, parallel via `parallel` skill)
- `py-datetime-now` (#7436)
- `py-redis-factory` (#7439 extension)
- `py-error-decorator` (#7435 — supersedes `decorator-order`)

### Wave 2 — Medium-priority backend BLOCK rules (parallel agents)
- `py-config-ssot` (#7437)
- `py-get-logger` (#7438)
- `py-sqla-session` (#7441)
- `py-pydantic-v2` (#7442)

These are higher scale (281–1,221 callsites). The rule blocks new violations only; legacy violations are migrated under their respective #7458 sub-issues.

### Wave 3 — Frontend BLOCK rules
- `fe-use-api` (#7446)
- `fe-notification-bus` (#7448)

Frontend runner exits 0 if no FE files are staged.

### Wave 4 — All WARN-severity rules (single bundled PR)
PEP 604, singletons, error handlers, date-fns, pagination, composables-contract, css-theming, ansible-become, docker-healthcheck.

### Wave 5 — Bonus rules from MEMORY.md
`py-relative-path-guard`, `py-aiohttp-streaming`, `py-fastapi-204-response-model`, `sh-gh-pr-edit-body`.

### Existing-hook migration (post-Wave-5 follow-up)

The 18 existing pre-commit hooks stay in place during all 5 waves. After Wave 5 stabilizes, a follow-up "consolidation" PR ports each existing hook into the registry as a rule module and removes the duplicate `.pre-commit-config.yaml` entry. Strictly additive — at no point is a previously-enforced rule silently dropped.

## 8. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Pre-commit becomes too slow (>5s) | AST cache shared across rules; FE/Infra runners skipped when no relevant files staged; `--max-time` budget per rule |
| False positives block legitimate commits | Every BLOCK rule ships with ≥10 fixture-pair tests (positive + negative + waiver); first 2 weeks after Wave 1 lands, monitor escape rate |
| Rules drift from canonical patterns | Each rule's docstring links to its #7458 issue and to the canonical example file; weekly audit catches drift |
| 22+ rules = 22+ approval reviews | Use `parallel` skill: each Wave 2/3/4 rule lands in its own worktree, batched 3-at-a-time |
| Frontend runner adds Node startup cost to every commit | Runner short-circuits if no FE files staged (`*.vue`, `*.ts`, `*.mjs`, `*.css` outside excluded dirs) |
| Audit report bloat in git history | Reports kept in `docs/canonical-audit/`; old reports pruned to monthly granularity after 6 months |

## 9. Acceptance Criteria

- All 22 #7458 sub-issues have a corresponding rule module (or are explicitly noted as covered by an existing hook).
- `make canonical-check` runs in <30s on a clean checkout.
- Pre-commit passes on `Dev_new_gui` HEAD (zero violations on staged files for any BLOCK rule).
- Weekly audit cron produces a report and commits it to `docs/canonical-audit/`.
- `/canonical-audit` slash command works locally with same output.
- `docs/developer/CANONICAL_RULES.md` lists every rule, severity, and rationale.
- Each Wave 1+ rule has fixture tests covering positive case, negative case, and waiver behavior.
- Existing 18 hooks remain functional throughout rollout (no regressions).

## 10. Open Questions

None at design time — all scope decisions resolved during brainstorm:

- Layers: all three (BE + FE + Infra)
- Enforcement: hooks at commit + periodic audit
- Architecture: pluggable rule registry
- Audit output: markdown report only

## 11. Related Work

- Epic #5060 (architectural primitives umbrella) — parent of #7458
- Sub-umbrella #7458 — 22 canonical-pattern sub-issues #7435–#7457
- Existing 18 pre-commit canonical hooks under `tools/lint/check_*.py` and `autobot-infrastructure/shared/scripts/hooks/`
- Memory: `feedback_priority_label_convention.md`, `feedback_layered_test_rot.md` — relevant operational lessons
- CLAUDE.md: cache TTL override pattern (`AUTOBOT_CHAT_SESSION_CACHE_TTL` example) — informs `py-constants` rule design
