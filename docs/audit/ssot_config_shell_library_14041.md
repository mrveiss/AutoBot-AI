# Shell SSOT library enumeration (#14041)

56 shell scripts under `autobot-infrastructure/` `source` a file that has never existed:
`lib/ssot-config.sh`. Every one of them does so with `2>/dev/null || true` (or an
equivalent silent-fallback shape), so the missing file has never produced a visible
error — each `${VAR:-literal}` in these scripts has always resolved to its literal
right-hand side.

## Root cause: the directory was gitignored, not merely unwritten

`.gitignore` has a bare `lib/` pattern (from the Python-venv block: `bin/`, `lib/`,
`lib64/`, `include/`, `share/`, `pyvenv.cfg`), which matches *any* directory named
`lib` anywhere in the tree. Two narrow exceptions already exist for exactly this
reason — `!scripts/lib/` and `!autobot-infrastructure/shared/scripts/hooks/lib/` —
proving the same shadowing bug has been hit and fixed twice before. There was no third
exception for `autobot-infrastructure/shared/scripts/lib/`, the one directory these 56
scripts actually source from: any prior local attempt to add `ssot-config.sh` there
would have been silently dropped by `git add -A` / a broad `git add`, look correct in
the working tree, and never reach a commit, a review, or CI. This PR adds the missing
`!autobot-infrastructure/shared/scripts/lib/` negation alongside the library file
itself — without it, the library could not be committed at all.

This document is the enumeration required before the library could be written safely
(#14041 decision comment): what each script would newly receive once the library
exists, and which of those values differ from what the script does today.

## Source-line shapes found (Step 3)

| Shape | Count | Behaviour today | Behaviour once the library exists |
|---|---|---|---|
| A — `source PATH 2>/dev/null \|\| true` | 48 | Silent no-op; script runs entirely on literals | Library sourced; `${VAR:-literal}` now resolves to the library's value when it sets one |
| B — two-path attempt then a `\|\| { ... }` block that falls back to sourcing `$PROJECT_ROOT/.env` directly (`check_status.sh`, `distributed/check-health.sh`, `utilities/check-time-sync.sh`, `utilities/setup-ssh-keys.sh`, `utilities/sync-all-vms.sh`) | 5 | One of the two path attempts always fails (wrong depth for that script's location); the other already resolves to the correct file location once it exists, so the `.env`-only fallback block was dead code whenever the library exists | First or second `source` attempt succeeds (library is at the depth one of the two guesses already assumes); the `.env` fallback block becomes genuinely unreachable, which is correct — it was written as a belt-and-braces path for a library that was never there |
| C — unguarded `source PATH` under `set -e`, no `\|\| true` at all (`vm-management/status-all-vms.sh:21`) | 1 | Script **crashes on every invocation** — `set -e` + a failing `source` of a nonexistent file exits the script before it does anything | Script runs for the first time. This is the single largest behaviour change in the enumeration — not a fallback-literal swap, a script that currently cannot run at all |
| D — wrong path segment: `$_PROJECT_ROOT/infrastructure/shared/scripts/lib/ssot-config.sh` (note: `infrastructure/`, not `autobot-infrastructure/` — this repo has no top-level `infrastructure/` directory) | 23 | Same as shape A — silent no-op, but for a *second*, independent reason: even a library placed at the canonical path would still not be found by these, because the path itself is wrong | Fixed as part of this change so the library is actually reachable; without the fix, these would keep silently no-op'ing forever, same failure mode with an extra layer |

**Scope-probe defect, corrected mid-PR:** the first pass found 9 shape-D files
because the search was `grep`'d under `autobot-infrastructure/` only — the same
"probe can't reach it" failure mode this whole issue family is about. A
follow-up `git grep` scoped to the full tracked tree (`git ls-files`, not a bare
recursive grep, to stay out of any other worktree) found **14 more** tracked
files with the identical defect outside `autobot-infrastructure/`: 13 flagged in
review plus `sync-frontend.sh` (repo root) found during the same sweep. All 23
are fixed in this PR, and `test_ssot_config_lib.sh` now asserts no tracked file
carries the non-`autobot-` path, so this can't regrow silently again.

Shape D files (fixed in this PR — `infrastructure/` → `autobot-infrastructure/`):

Originally in scope (`autobot-infrastructure/`, 9):
`autobot-infrastructure/autobot-ai-stack/templates/ai-status.sh`,
`autobot-infrastructure/autobot-slm-backend/scripts/bootstrap-slm.sh`,
`autobot-infrastructure/shared/config/load_config.sh`,
`autobot-infrastructure/shared/mcp/tools/mcp-autobot-tracker/dev-run.sh`,
`autobot-infrastructure/shared/mcp/tools/mcp-autobot-tracker/install.sh`,
`autobot-infrastructure/shared/mcp/tools/mcp-autobot-tracker/production-install.sh`,
`autobot-infrastructure/shared/tests/performance/run_baseline.sh`,
`autobot-infrastructure/shared/tests/run_phase9_tests.sh`,
`autobot-infrastructure/shared/tests/test_crud_endpoints.sh`.

Found by the full-tree sweep, outside `autobot-infrastructure/` (14):
`autobot-frontend/start-frontend-dev.sh`,
`autobot-frontend/scripts/knowledge_base/reload-documentation.sh`,
`autobot-slm-frontend/scripts/sync-to-admin.sh`,
`scripts/service-auth/validate-service-auth.sh`,
`scripts/service-auth/circuit-breaker-ramp.sh`,
`scripts/service-auth/emergency-rollback.sh`,
`autobot-slm-backend/monitoring/start_monitoring.sh`,
`autobot-slm-backend/ansible/deploy.sh`,
`autobot-slm-backend/ansible/deploy-native.sh`,
`autobot-slm-backend/ansible/deploy-hybrid.sh`,
`autobot-slm-backend/ansible/deploy-autobot-native.sh`,
`autobot-slm-backend/ansible/utils/backup.sh`,
`autobot-slm-backend/ansible/utils/health-check.sh`,
`sync-frontend.sh` (repo root).

Two documentation/comment references to the same wrong path were also corrected
for consistency (neither is executable, both would mislead a reader who copied
them): `docs/api/IP_ADDRESSING_SCHEME.md` (an example `source` command) and
`autobot-slm-backend/ansible/inventory/group_vars/infrastructure.yml` (a
comment).

Two more single-script special cases, found while enumerating:

- **`vm-management/status-all-vms.sh`** does not declare its own `VMS` associative array
  — a comment at line 25 says `# VMS array is provided by ssot-config.sh`. No other
  script depends on the library for anything beyond scalar variables. The library
  declares `VMS` (guarded — see below) so this one script's only-ever-working path is
  preserved.
- **`security/ssh-hardening/configure-ssh.sh`** and **`native-vm/validate_native_deployment.sh`**
  read `${AUTOBOT_*_HOST}` with **no `:-` fallback at all**. Today those resolve to an
  **empty string**, not a hardcoded default — a different failure shape than the rest of
  the enumeration (a missing default vs. a wrong-but-present one). Once the library sets
  these variables, both scripts get real values for the first time.
- **`network/discover-vms.sh`** and **`detect-hardcoded-values.sh`** consume nothing the
  library provides (0 matching `${VAR:-...}` references) — sourcing the library is a true
  no-op for their behaviour, then and now.

## Divergence table (Step 1 + Step 2)

One row per distinct `${VAR:-literal}` pair found across the 56 scripts: **31 total**
— 30 distinct `${AUTOBOT_VAR:-literal}` pairs plus the one non-`AUTOBOT_`-prefixed
`${NETWORK_SUBNET:-}` pair (several var names repeat the same literal across many
files — see "Files" for the fan-out; the table below bundles the four
`AUTOBOT_VNC_*` names sharing one no-SSOT explanation into a single row for
readability, so it has fewer rows than 31 while still covering all 31 pairs). SSOT
column is `autobot_shared/ssot_config.py`'s Pydantic field default for that alias,
which is what a `.env`-less deployment gets from the Python side too — the shell
library mirrors it so both languages agree on the same unconfigured default.
Ports/paths where the two agree are the safe majority; the `DIFFERS` rows are what
changes on the day this lands.

| Variable | Script literal | SSOT value | Differs? | Note |
|---|---|---|---|---|
| `AUTOBOT_BACKEND_PORT` | `8001` | `8001` | no | |
| `AUTOBOT_FRONTEND_PORT` | `5173` | `5173` | no | |
| `AUTOBOT_NPU_WORKER_PORT` | `8081` | `8081` | no | |
| `AUTOBOT_REDIS_PORT` | `6379` | `6379` | no | |
| `AUTOBOT_AI_STACK_PORT` | `8080` | `8080` | no | |
| `AUTOBOT_OLLAMA_PORT` | `11434` | `11434` | no | |
| `AUTOBOT_VNC_PORT` | `6080` | `6080` | no | |
| `AUTOBOT_NOVNC_PATH` | `/opt/novnc` | `/opt/novnc` | no | |
| `AUTOBOT_REDIS_DB_CELERY_BROKER` | `14` | `14` | no | |
| `AUTOBOT_REDIS_DB_CELERY_RESULTS` | `15` | `15` | no | |
| `AUTOBOT_REDIS_PASSWORD` | `` (empty) | `` (`None`) | no | |
| `NETWORK_SUBNET` | `` (empty) | `` (empty) | no | non-`AUTOBOT_`-prefixed; only `network/discover-vms.sh` reads it |
| `AUTOBOT_BACKEND_HOST` | `127.0.0.1` (some files) / `localhost` (most) | `127.0.0.1` | **partially** | same loopback host, different string — see "cosmetic" note below |
| `AUTOBOT_FRONTEND_HOST` | `localhost` | `127.0.0.1` | **yes (cosmetic)** | |
| `AUTOBOT_NPU_WORKER_HOST` | `localhost` | `127.0.0.1` | **yes (cosmetic)** | |
| `AUTOBOT_REDIS_HOST` | `localhost` | `127.0.0.1` | **yes (cosmetic)** | |
| `AUTOBOT_AI_STACK_HOST` | `localhost` | `127.0.0.1` | **yes (cosmetic)** | |
| `AUTOBOT_BROWSER_SERVICE_HOST` | `localhost` | `127.0.0.1` | **yes (cosmetic)** | |
| `AUTOBOT_SLM_HOST` | `localhost` | `127.0.0.1` | **yes (cosmetic)** | |
| `AUTOBOT_OLLAMA_HOST` | `127.0.0.1` (some files) / `localhost` (most) | `127.0.0.1` | **partially (cosmetic)** | |
| `AUTOBOT_BACKEND_URL` | computed as `http://${AUTOBOT_BACKEND_HOST:-localhost}:${AUTOBOT_BACKEND_PORT:-8001}` | not a modeled field — `config.backend_url` is the same computation from `vm.main` + `port.backend` | **yes (cosmetic, same shape as HOST rows above)** | not an independent literal; folds into the host divergence |
| **`AUTOBOT_BROWSER_SERVICE_PORT`** | **`3000`** | **`9001`** | **YES — real** | `ssot_config.py` line 201 comment: *"Issue #4052: 9001; 3000 is Grafana"*. 7 of the 56 scripts (`vm-management/fix-architecture-issues.sh`, `vm-management/status-all-vms.sh`, `distributed/check-health.sh`, `distributed/distributed-status.sh`, `distributed/start-coordinator.sh`, `native-vm/start_autobot_native.sh`, `native-vm/status_autobot_native.sh`) currently probe **Grafana's port** when they mean to probe the browser service. This is the one divergence in the set that is not cosmetic. |
| `AUTOBOT_SSH_KEY` | `$HOME/.ssh/autobot_key` | **no field under this name** — canonical is `ssh_key_path` / alias `AUTOBOT_SSH_KEY_PATH` (legacy `SLM_SSH_KEY`), default `/etc/autobot/ssh/autobot_key` (#12429) | n/a — name mismatch, not a value mismatch | Library does **not** export `AUTOBOT_SSH_KEY` (would require inventing a name mapping the enumeration wasn't asked to decide). Literal stays exactly as today — safe. Flagged as a follow-up. |
| `AUTOBOT_SSH_USER` | `autobot` | no field anywhere in `ssot_config.py`, `.env.example`, or the Ansible `group_vars` | n/a — no SSOT source | Library does not export it; literal unchanged. Follow-up candidate. |
| `AUTOBOT_SLM_NODE_ID` | `00-SLM-Manager` | no field anywhere | n/a — no SSOT source | Same — unchanged, follow-up candidate. |
| `AUTOBOT_VNC_SERVER_HOST` / `AUTOBOT_VNC_SERVER_PORT` / `AUTOBOT_VNC_WEB_HOST` / `AUTOBOT_VNC_WEB_PORT` | `localhost` / `5902` / `localhost` / `6080` | no fields under these exact names. `AUTOBOT_VNC_PORT` (6080, `PortConfig`) is the closest match for the two `*_PORT` names; `AUTOBOT_VNC_HOST` (`ssot_config.py:1853`, `MiscConfig`, default `""`) is a closer name-match for the two `*_HOST` names than anything reported in the first pass of this doc | n/a — no SSOT source under these exact names (5 unmodeled/mismatched names total) | Library does not export any of the four; literals unchanged, behaviour provably identical. Follow-up (#14173, updated) — looks like an un-consolidated fork of `AUTOBOT_VNC_PORT` and `AUTOBOT_VNC_HOST` into four names (`network/network-config.sh` is the only script that reads all four). |

**"Cosmetic" here means**: `localhost` and `127.0.0.1` both resolve to the loopback
interface, so on a default single-host install there is no *observable* difference —
but the strings are not equal, so a script that treats the value as an opaque string
(e.g. writing it into a URL and string-comparing it elsewhere) would see a different
value after this lands. On a distributed multi-VM deployment where `.env` sets a real
IP for these hosts, the library now honours it (today it never could) — that is the
whole point of building the library, not a regression.

## Files with zero divergent literals

`network/discover-vms.sh` and `detect-hardcoded-values.sh` consume nothing from the
library (see above) — building it changes nothing about their runtime behaviour.

## Recommendation: no staging needed

Of the **31** distinct `${VAR:-literal}` pairs enumerated (30 `${AUTOBOT_VAR:-literal}`
+ 1 `${NETWORK_SUBNET:-}`), bucketed so the count reconciles against the table above:

- **14 already match the SSOT exactly** — 13 `AUTOBOT_` pairs (every port,
  `AUTOBOT_NOVNC_PATH`, the Redis DB indices and password, plus the `127.0.0.1`-literal
  variant of `AUTOBOT_BACKEND_HOST` and `AUTOBOT_OLLAMA_HOST`) + `NETWORK_SUBNET`.
- **9 differ only in `localhost` vs `127.0.0.1`** (`AUTOBOT_AI_STACK_HOST`, the
  `localhost`-literal variant of `AUTOBOT_BACKEND_HOST`, `AUTOBOT_BROWSER_SERVICE_HOST`,
  `AUTOBOT_FRONTEND_HOST`, `AUTOBOT_NPU_WORKER_HOST`, the `localhost`-literal variant of
  `AUTOBOT_OLLAMA_HOST`, `AUTOBOT_REDIS_HOST`, `AUTOBOT_SLM_HOST`, and
  `AUTOBOT_BACKEND_URL`) — same effective host on every install that has not overridden
  it, and the whole reason for this change is to let overrides (a real `.env`) reach
  these scripts for the first time on distributed installs, where today they cannot.
- **1 differs for real**: `AUTOBOT_BROWSER_SERVICE_PORT` (`3000` → `9001`), affecting 7
  scripts that currently health-check Grafana's port by accident. This is a **fix**, not
  a regression — landing the library corrects a wrong port a diagnostic script has always
  used, in scripts whose job is exactly to report service health accurately.
- **7 pairs across 5 var families have no SSOT source under their exact name**
  (`AUTOBOT_SSH_KEY`, `AUTOBOT_SSH_USER`, `AUTOBOT_SLM_NODE_ID`, and the four
  `AUTOBOT_VNC_*` names — two of which, `_SERVER_HOST`/`_WEB_HOST`, have a closer
  name-match in `AUTOBOT_VNC_HOST`, still not exported) — the library does not export
  any of these, so these 7 literals are provably unchanged by this PR.

14 + 9 + 1 + 7 = 31. Given that split — no case where a script silently starts pointing
somewhere materially different and wrong — this lands as a single change, not staged.
The one real-value divergence (`AUTOBOT_BROWSER_SERVICE_PORT`) is a correction the
scripts have needed since #4052 renumbered the port away from Grafana's.

## Follow-up (filed separately, not blocking this PR)

- `AUTOBOT_SSH_KEY` (script convention) vs `AUTOBOT_SSH_KEY_PATH`/`SLM_SSH_KEY` (SSOT,
  #12429) is a naming split across the same concept — deciding whether to alias or
  rename is a scope call for the owner, not something to invent silently here.
- `AUTOBOT_SSH_USER` and `AUTOBOT_SLM_NODE_ID` have no SSOT entry anywhere (Python,
  `.env.example`, or Ansible `group_vars`) — either they should be added to
  `autobot_shared/ssot_config.py`, or the scripts should stop presenting them as
  SSOT-backed.
- The four `AUTOBOT_VNC_*` names have no field under their exact names, but two closer
  candidates already exist and are just as unused by these scripts:
  `AUTOBOT_VNC_PORT` (`PortConfig`, 6080) and `AUTOBOT_VNC_HOST`
  (`ssot_config.py:1853`, `MiscConfig`, default `""`). Behaviour is unchanged either way
  (the library still exports neither the four script-side names nor rewires them to the
  two SSOT names), but this narrows the follow-up to "consolidate four names down to
  two that already exist" rather than "invent new SSOT fields".
