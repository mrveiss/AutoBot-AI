# Python 3.14 consistency audit — docker vs native vs CI

**Date:** 2026-08-08
**Trigger:** "use 3.14 everywhere where possible", raised while root-causing #13727 — five
scheduler tests that looked like a broken cancellation contract but were one unsupported
interpreter.
**Method:** every declaration of a Python version in the repo — CI workflows, `.python-version`,
tool configs, Dockerfiles, Ansible roles and playbooks, runtime `sys.version_info` checks —
enumerated and compared. Wheel availability re-measured against PyPI rather than assumed.

## Summary

The repo is **already on 3.14 nearly everywhere**. CI, `.python-version`, mypy, both Dockerfiles
and every Ansible role except the NPU worker are 3.14. What remains is four items of genuine
drift, two documented exceptions whose justification has **expired**, and two live bugs in the
native deployment path found while checking venv consistency.

| Surface | Declared | Verdict |
|---|---|---|
| CI workflows (15 files) | 3.14 | ✅ consistent |
| `.python-version` (2 files) | 3.14 | ✅ consistent |
| mypy `python_version` | 3.14 | ✅ consistent |
| `docker/backend/Dockerfile` | 3.14 | ✅ consistent |
| `docker/slm/Dockerfile` | 3.14 (`ARG PYTHON_VERSION`) | ✅ consistent |
| Ansible: backend, backend_services, ai-stack, tts-worker, slm_manager, chromadb, agent_config | 3.14 | ✅ consistent |
| Ansible: `roles/npu-worker` | **3.11** | ⚠️ exception — justification expired, see F1 |
| black `target-version` | **py312** | ⚠️ exception — justification expired, see F1 |
| `startup_validator.py:320` floor | **3.12** | ❌ drift, see F2 |
| `pyproject.toml:4` comment | claims worker "pins 3.12+" | ❌ factually wrong, see F3 |
| `scripts/format.sh` | falls back to 3.10; advises `python3.12 -m pip` | ❌ drift, see F4 |
| `deploy-native-services.yml` NPU play | 3.11 into a **shared** venv path | ❌ collision, see F5 |
| `deploy-native-services.yml` NPU play | requirements path **does not exist** | ❌ broken, see F6 |
| `deploy-native-services.yml` host groups | `npu` / `aiml` | ❌ not in the inventory, see F7 |
| `docs/` (all `.md`) | mixed | ⚠️ 7 stale claims, 1 pointing at live code, see F8 |

`autobot-npu-worker` (Windows variant) is blocked and stays blocked — see F1.

---

## F1 — The 3.11 pin and the py312 black target are both unblocked now

Both exceptions trace to one claim, recorded in **#10877** (CLOSED): OpenVINO has no 3.14 wheels,
so the NPU worker must stay on 3.11, so black must not emit PEP 758 syntax (`except A, B:`
without parentheses) that would be a hard `SyntaxError` on that worker's cross-imported
`autobot_shared` code.

That claim was true when written. It is no longer true. Measured against PyPI on 2026-08-08:

| Package | Latest | Python tags | 3.14? |
|---|---|---|---|
| `openvino` | 2026.3.0 | cp310, cp311, cp312, cp313, **cp314** | ✅ |
| `torch` | 2.13.0 | cp310, cp311, cp312, cp313, **cp314** | ✅ |
| `numpy` | 2.5.1 | cp312, cp313, **cp314** | ✅ |
| `openvino-dev` | 2024.6.0 | `py3-none-any` (universal) | ✅ |
| `onnxruntime-openvino` | 1.24.1 | cp311, cp312, cp313 | ❌ **no cp314** |

The Linux native NPU worker (`autobot-npu-worker/requirements.txt`) needs `openvino` + `torch` +
`numpy` and **not** `onnxruntime-openvino`. Its pin is already `openvino>=2026.2.1`, which
resolves to a cp314-carrying release. So it can move to 3.14 today.

`onnxruntime-openvino` appears only in
`autobot-npu-worker/resources/windows-npu-worker/requirements.txt` — the **Windows** worker. That
one stays blocked until onnxruntime ships cp314. Whether that also keeps the black target pinned
depends on whether the Windows worker consumes the same `autobot_shared` modules; #10877's
argument was written about the Linux worker and does not answer this. **Confirm before bumping
the black target** — a wrong call here is a `SyntaxError` on a worker, not a lint nit.

Order matters: the NPU worker moves to 3.14 **first**, the black target follows. Reversing them
reformats shared code into syntax the still-3.11 worker cannot parse.

## F2 — The declared runtime floor is 3.12, four minors below everything else

`autobot-backend/startup_validator.py:320`:

```python
if sys.version_info < (3, 12):
    self.result.add_error(f"Python 3.12+ required, found {sys.version}")
```

Nothing justifies 3.12 — the backend ships on 3.14 in both Docker and Ansible. This is the only
runtime-enforced statement of the floor in the codebase, so it is the one a reader trusts.

It is also **never executed**: `validate_startup_dependencies` / `StartupValidator` have zero
callers repo-wide (filed as **#13738**). Correcting the number and wiring the check are separate
fixes; both are needed for the floor to mean anything.

## F3 — The comment justifying the black pin states the wrong version

`pyproject.toml:4-5` says the NPU worker's "requirements pin 3.12+". The worker is pinned to
**3.11** (`roles/npu-worker/tasks/main.yml:153`, `deploy-native-services.yml:365`), and #10877
says 3.11 throughout. The comment understates the constraint it exists to explain, which makes
`target-version = ["py312"]` look like it has one more minor of headroom than it does.

## F4 — `scripts/format.sh` contradicts the project target

The interpreter search falls back through `python3.13 → 3.12 → 3.11 → 3.10`, the "project target"
check accepts `3.12|3.13|3.14`, and the remediation text tells the user to install black on
**3.12** while the sentence above it says to install it on 3.14. Black's emitted output differs
by interpreter, which is the entire reason the wrapper exists — so a silent fall back to 3.10
produces formatting that CI will disagree with.

## F5 — `/opt/autobot/venv` is built by three producers with two interpreters

| Producer | Path | Interpreter |
|---|---|---|
| `roles/backend_services/tasks/main.yml:49` | `/opt/autobot/venv` | **3.14** |
| `deploy-native-services.yml:365` (`hosts: npu`) | `/opt/autobot/venv` | **3.11** |
| `deploy-native-services.yml:511` (`hosts: aiml`) | `/opt/autobot/venv` | **3.14** |

The role-based NPU path is fine — `roles/npu-worker` uses `{{ npu_install_dir }}/venv`
(`/opt/autobot/autobot-npu-worker/venv`), its own directory. The **playbook** path is not: it
writes the NPU venv into the shared `/opt/autobot/venv`.

Co-location is a supported layout (the role-facts test inventory covers a single host carrying
SLM + backend + vnc), so these plays can land on one machine. The `aiml` play creates its venv
with a bare `shell:` and **no `creates:` guard**, so on a co-located host it re-runs
`python3.14 -m venv venv` over an existing 3.11 tree — rewriting `pyvenv.cfg` to 3.14 while
site-packages still holds 3.11-built OpenVINO binaries. That fails at import, not at deploy.

## F6 — The NPU play installs from a requirements file that does not exist

`deploy-native-services.yml:371` installs
`requirements: /opt/autobot/src/docker/npu-worker/requirements.txt`. There is no
`docker/npu-worker/` directory in the repo. The real files are `autobot-npu-worker/requirements.txt`
and `autobot-infrastructure/autobot-npu-worker/docker/requirements-npu.txt`.

This play is not dead code: `docs/developer/SERVICE_MANAGEMENT.md` and
`INFRASTRUCTURE_DEPLOYMENT.md` document `ansible-playbook playbooks/deploy-native-services.yml
--tags npu` as the operator entry point.

## F7 — The playbook targets host groups the inventory does not define

`deploy-native-services.yml` uses `hosts: npu` and `hosts: aiml`. `inventory/hosts.yml` defines
`npu_workers` and `ai_stack`. A play whose host pattern matches nothing is skipped silently —
"ok=0 changed=0" reads like success.

F5, F6 and F7 are all in the same documented-but-unexercised playbook, which is why three
independent defects accumulated in it.

---

## F8 — Documentation: mostly consistent, seven stale claims, one pointing at live code

Every `.md` under `docs/` and `README.md` was grepped for a Python version claim and each hit
classified. The **user-facing install and deploy path is already correct** — `docs/user-guide/`,
`docs/runbooks/SINGLE_HOST_DEPLOYMENT.md` and `docs/deployment/` all say 3.14, and `install.sh`
really does install 3.14 (`install.sh:397`).

Stale claims, corrected in this PR:

| File | Said | Reality |
|---|---|---|
| `docs/GETTING_STARTED_COMPLETE.md:22` | "`install.sh` installs Python **3.12**" | installs 3.14 — and this is the first-contact doc |
| `docs/architecture/README.md:64` | "Python **3.11+** — Core backend language" | 3.14 |
| `docs/architecture/CODE_VECTORIZATION_README.md:257` | "Python **3.9+**" | 3.14 |
| `docs/guides/VLLM_SETUP_GUIDE.md:66` | "Python **3.9+** required" | 3.14 |
| `docs/developer/CODE_QUALITY_IMPLEMENTATION.md:91` | CI step "Set up Python **3.11**" | CI is 3.14 |
| `docs/developer/BACKEND_DEBUGGING.md:221` | writes a shim into `.../lib/**python3.13**/site-packages/` | hardcoded minor; the backend is 3.14, so the shim lands where nothing imports it. Now resolved from the venv via `sysconfig` |
| `docs/ROADMAP.md:190` | "Actual: 3.14 (conda, backend), **3.10 (dev)**" | dev is now 3.14 too |

**Deliberately left as-is** — these are correct *as historical records*, and rewriting them would
falsify the measurement they exist to preserve:

- `docs/audit/*` — dated baselines that state the interpreter they were measured on ("Python 3.10.12").
- `docs/archives/plans/*`, `docs/superpowers/plans/*` — plan documents with a "Tech Stack: Python 3.11+"
  line, describing what was true when written.
- `docs/developer/BACKEND_DEBUGGING.md:245` — the red-herrings table row "Python 3.13 incompatibility |
  Tested with Python 3.14 | ❌ Same issue" is an investigation record, not an instruction.

### The one that is not a doc problem

`docs/developer/audits/datetime-parsing-audit.md` and `autobot_shared/time_utils.py:42` both carry a
migration plan whose step 6 is:

> ⏳ Python 3.11+ upgrade — drops the 9 `.replace("Z", "+00:00")` workaround sites since 3.11
> `fromisoformat` accepts `Z` natively

**That precondition was met four minor versions ago.** The step is still marked pending, and three
shim sites remain in shipped code:

- `autobot_shared/time_utils.py:127`
- `autobot-backend/integrations/microsoft365_integration.py:84`
- `autobot-slm-backend/api/security.py:852`

Not fixed here — removing a parsing shim is a code change with its own blast radius, and the
docstring's "9 sites" no longer matches the 3 that are left, so the migration state needs
re-establishing before anything is deleted. Filed separately.

## Recommended order

1. **F2, F3, F4** — pure drift, no runtime risk. Fixable in one PR.
2. **F6, F7** — the native NPU deploy path is broken today, independent of any version bump.
3. **F5** — give the NPU worker its own venv path in the playbook, matching the role.
4. **F1a** — move the Linux NPU worker to 3.14 (openvino/torch/numpy all ship cp314).
5. **F1b** — only then, and only after settling the Windows-worker question, bump black to py314.

## Not proposed, deliberately

- **Bumping the Windows NPU worker** — `onnxruntime-openvino` has no cp314. Re-check when it does.
- **`openvino-dev`** — frozen at 2024.6.0 and universal-wheel; it is a deprecated meta-package.
  Removing it is a separate question from the interpreter version.
- **Changing the local dev box** — out of repo scope. Worth knowing that it runs 3.10, which is
  what made #13727 look like five broken contracts; see the memory note on local-env floors.
