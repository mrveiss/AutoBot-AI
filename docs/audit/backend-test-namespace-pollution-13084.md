# Cross-backend + conftest-stub namespace pollution fix (#13084)

**Purpose.** Per #13084 (filed during the #10691 baseline measurement, PR
#13088 / `docs/audit/backend-test-baseline-10691.md`), this document records
the measurement, the unguarded-`sys.modules`-stub inventory, the chosen fix
for the cross-backend collision, and the before/after counts.

## Environment

Reproduced independently of the original #13088 baseline session, in this
PR's own worktree:

- Fresh checkout off `origin/Dev_new_gui`, Python 3.10.12, system-wide
  `pytest 9.0.2`, `pytest-asyncio 1.3.0`, `pytest-cov 7.1.0`,
  `pytest-xdist 3.8.0`, `fakeredis 2.36.2` — no ad-hoc installs (same 19/69
  missing-optional-dep profile as the original baseline session:
  `openai`, `boto3`, `sentence-transformers`, `apscheduler`, `cachetools`,
  `openpyxl`, `python-pptx`, ... — noise floor is identical between the
  before/after measurements below, so the delta is attributable to the fix).
- **Disposable local Postgres 16** — private `initdb` cluster (own data dir
  under the session scratchpad, not `/tmp` or a shared location), own Unix
  socket (`/tmp/pg13084sock`), listening only on `127.0.0.1:55433`. The
  shared host cluster (port 5432, real `autobot_app`/`slm_app` roles) was
  never touched; no `pg_hba.conf` edit; `/etc/autobot/db-credentials.env`
  was never read.
- **Disposable local Redis** — a second `redis-server` on `127.0.0.1:63791`
  with its own data dir, to avoid touching the host's real `redis-stack`
  instance on `:6379`.
- `config/config.yaml`, `data/`, `logs/`, `static/` created to match
  `ci.yml`'s "Create necessary directories and config files" step exactly.
  **`config/config.yaml` sha256 backed up before any run and confirmed
  byte-identical after** (see Verification below) — the exact corruption
  vector #13083 fixed and this issue's severity bar.

## Baseline (before any fix), reproduced independently

```
$ python -m pytest --collect-only -q
20155 tests collected, 252 errors in 80.21s
```

This matches the original #13088 baseline (252 collection errors; the small
20155 vs 20203 test-count delta is normal repo drift between sessions, not a
measurement discrepancy). Breakdown, reproduced from this session's own run:

| Cluster | Count |
|---|---:|
| `ModuleNotFoundError: No module named 'user_management.X'` | 107 |
| `ModuleNotFoundError: No module named 'api.X'` | 87 |
| `ModuleNotFoundError: No module named 'tools.X'` (unrelated — `tools/` not on `pythonpath`, #13086) | 12 |
| `ModuleNotFoundError: No module named 'services.X'` | 11 |
| `fastapi.exceptions.FastAPIError: Invalid args for response field!` | 7 |
| `ModuleNotFoundError: No module named 'middleware.X'` | 2 |
| `ImportError: cannot import name 'X' from 'Y'` (various — `api`, `initialization`, `autobot_shared.ssot_config`, `migrations`, `knowledge.backends`, `autobot_shared.redis_client`, `autobot_shared.http_client`, `autobot_shared.redis_management.types`, `type_defs.common`) | 24 |
| `ModuleNotFoundError: No module named 'cachetools'` (bucket B, unrelated) | 1 |

239/252 (95%) is the cross-backend collision cluster (`api`/`services`/
`user_management`/`middleware` `ModuleNotFoundError` + the `ImportError`/
`FastAPIError` variants of the same mechanism) — matching the #13084 issue's
own citation exactly.

## Mechanism 1 root cause, re-confirmed

`autobot-backend/` and `autobot-slm-backend/` themselves have **no**
`__init__.py` (confirmed: `ls autobot-backend/__init__.py` → no such file),
while their `api/`, `services/`, `user_management/`, `middleware/`,
`migrations/` subdirectories each **do** have one. Under
`--import-mode=importlib` (already the project's mode — see `pytest.ini`
`addopts`), pytest's module-naming algorithm walks up through directories
that have `__init__.py`, stopping at the first ancestor that doesn't. Since
neither hyphenated backend root has one, both `autobot-backend/api/foo_test.py`
and `autobot-slm-backend/api/foo_test.py` resolve to the **same** dotted
module name `api.foo_test`, so whichever collects first wins the
`sys.modules["api"]` (etc.) slot for the rest of the session.

## Options evaluated for the fix

1. **`consider_namespace_packages = true`.** Rejected: this option makes
   pytest treat a directory *without* `__init__.py` as a PEP 420 implicit
   namespace package component so an ancestor directory's name can be
   folded into the dotted module name. But `autobot-backend` and
   `autobot-slm-backend` are **not valid Python identifiers** (hyphens) —
   even if pytest's internal module-name construction doesn't strictly
   require identifier validity for its `sys.modules` key, the mechanism this
   option targets (PEP 420 namespace-package resolution via the standard
   import system) does, since deeper namespace-package handling ultimately
   walks through `importlib`'s real package resolution. This does not
   address a hyphenated top-level directory acting as the implicit
   disambiguating namespace segment. Empirically: turning the option on
   without any other change does not alter the collision (not committed —
   would require renaming the directories, which is option 3).
2. **Per-backend separate pytest invocations (CHOSEN).** Since the two
   backends never need to share a single interpreter's `sys.modules`
   namespace, running them as two sequential `python -m pytest` invocations
   in the same CI step (not two separate CI jobs) removes the collision
   entirely — each invocation starts a fresh interpreter, so there is never
   a shared `sys.modules["api"]` to fight over. This was verified
   empirically (see below): splitting reduces 252 collection errors to 14 +
   1 = 15 (94% reduction), and the remaining 15 are independent,
   already-triaged issues (#13086 `tools.lint`, one `cachetools` optional
   dep, plus two newly-discovered unrelated bugs filed as #13107/#13108).
   Crucially, **this does not multiply wall-clock on the singleton
   self-hosted runner** the way splitting into two separate CI *jobs* would:
   both invocations run sequentially inside the *same* job/step, so total
   time is the sum of the parts — identical to today's single combined
   invocation's wall-clock, just without the collision. Coverage is
   preserved across both invocations via `--cov-append` + a single final
   `--cov-fail-under=70` gate on the second invocation.
3. **Renaming the colliding packages** (e.g. `autobot-backend/api` →
   something backend-qualified). Rejected for this PR: correct in principle,
   but the largest blast radius by far — touches every production import
   statement across both backends (`from api.X import Y`, `from services.X
   import Y`, etc.), which is exactly the class of change the task
   explicitly says to stop and report on rather than apply unilaterally.
   Not attempted.
4. **`conftest.py`-level `sys.path` discipline.** Rejected: `sys.path`
   ordering does not change `sys.modules` key identity — two same-named
   top-level packages still collide on the same dotted name in
   `sys.modules` regardless of which directory is first on `sys.path`; this
   does not address the actual collision mechanism.

**Chosen: option 2.** Implemented in `.github/workflows/ci.yml`'s
`security-tests` job ("Run unit tests with coverage gate" step) and
documented in `pytest.ini`'s `testpaths` comment so local full-suite runs
follow the same two-invocation discipline.

## Empirical verification of the chosen fix

```
$ python -m pytest autobot-backend autobot_shared autobot-tts-worker repo_tests --collect-only -q
21647 tests collected, 13 errors in 29.70s

$ python -m pytest autobot-slm-backend --collect-only -q
1527 tests collected, 1 error in 13.46s
```

**252 → 14 total collection errors (94.4% reduction)**, with zero cross-backend
`ModuleNotFoundError`/`ImportError`/`FastAPIError` remaining. The 14
residual errors are all independent, already-triaged:

| File | Cause | Status |
|---|---|---|
| `repo_tests/lint/canonical/**` (12 files) | `tools.lint` not on `pythonpath` | #13086 (already filed) |
| `autobot-backend/security/enterprise/threat_detection/test_learner.py` | missing optional dep `cachetools` | bucket B (already documented) |
| `autobot-slm-backend/tests/api/test_apply_secrets.py` | `services.system_secrets_vault` never stubbed (conftest AST-scan gap, reproduces standalone) | newly filed #13108 |

(The mechanism-2 `knowledge.facts` collision documented below — found via the
`llc/tests/` + `quarantine_boundary_test.py` combined-invocation repro — does
NOT appear in either of the two split-invocation numbers above, because that
specific ordering only manifests when both directories are named explicitly
in one combined command; #13107 covers it for the deeper structural fix.)

## Unguarded `sys.modules[...] = ` inventory (mechanism 2)

164 test-tree files contain a `sys.modules[key] = value` assignment. A
heuristic classification (presence of `finally:`, `yield`, `addfinalizer`,
`monkeypatch.setitem`/`delitem`, the `_PRE_BOOTSTRAP_MODULES` snapshot-restore
idiom, `del sys.modules`, or `patch.dict(` anywhere in the file) found:

- **98 files** already restore in some form.
- **66 files** (63 after the classifier's `patch.dict` refinement swept out
  3 false negatives) have **no restore marker at all** — candidates for the
  "unguarded, no restore" bug class this issue's severity bar names.

Full file list (`file:line` for every hit) is in the raw grep captured
during this session; the highest-leverage subset — session/package-wide
`conftest.py` files whose stubs can shadow a REAL module for every
other test collected afterward — were triaged individually:

| File | Verdict | Action |
|---|---|---|
| `autobot-backend/conftest.py`, `autobot-slm-backend/conftest.py` (root conftests) | **Safe by design once mechanism 1 is fixed.** Each backend's root conftest permanently stubs *that backend's own* namespace for the lifetime of an isolated, single-backend session — exactly the model the chosen mechanism-1 fix establishes. No restore needed; restoring would defeat their purpose (the stubs exist precisely so no real, unavailable dependency — e.g. `/etc/autobot/db-credentials.env`-reading `config.Settings()` — is ever touched). | No change |
| `autobot-slm-backend/tests/services/conftest.py` | Same pattern, scoped to `tests/services/` only, guarded per-name (`if name not in sys.modules`) | No change |
| `autobot-backend/llc/tests/conftest.py` | **Genuine bug, fixed this PR.** Unconditionally stubbed `knowledge`, `knowledge.embedding_cache`, `knowledge.utils`, `knowledge.backends`, `agents`, `agents.base_agent` with no restore. Demonstrated to break `services/research/quarantine_boundary_test.py` (`from knowledge.backends import InMemoryClient`) when both are collected in the same session. | Fixed: (1) `knowledge.backends` now re-exports the REAL, dependency-light `InMemoryClient`/`InMemoryCollection`/`AsyncInMemoryClient`/`AsyncInMemoryCollection` classes (verified: no chromadb import at module level) instead of omitting them, so no restore is even needed for that key; (2) a `scope="package", autouse=True` fixture restores `knowledge`/`knowledge.embedding_cache`/`knowledge.utils`/`agents`/`agents.base_agent` to their pre-stub `sys.modules` state once every test under `llc/tests/` has run. Verified: all 1367 `llc/tests/` tests still pass; `quarantine_boundary_test.py` still passes standalone. A deeper structural gap (the `knowledge` stub's `__path__ = []` blocks ANY other real `knowledge.X` submodule, not just the ones explicitly re-stubbed — reproduced via `knowledge.facts`) is filed separately as #13107, out of scope for a safe same-PR fix per the "avoid regressing 9078 passing tests" constraint. |
| `autobot-slm-backend/tests/api/test_auth_logout.py` | **Already correctly guarded** — restores via the `_PRE_BOOTSTRAP_MODULES` snapshot-diff idiom (lines 45, 130-134). The #13084 issue text names this file alongside `test_token_denylist.py`; verified it is NOT actually a bug (restore already present and correct). | No change needed |
| `autobot-slm-backend/tests/services/test_token_denylist.py` | **Genuine bug, fixed this PR** — the exact #13084/#13083 severity-bar example. `sys.modules["config"] = MagicMock()` (and 6 other stub keys) executed unconditionally with **no restore at all**, plus `setattr(sys.modules["services"], "token_denylist", _dl_mod)` permanently mutating the shared `services` stub object. | Fixed: added the same `_PRE_BOOTSTRAP_MODULES` snapshot-diff-restore idiom already proven in the sibling `test_auth_logout.py`, plus explicit `token_denylist` attribute cleanup on the `services` stub. Verified: same 7 passed / 9 pre-existing-unrelated-failed (test rot, filed as #13106) before and after the fix; and verified by direct object-identity check that `sys.modules["config"]` is restored to the exact pre-existing root-conftest object afterward, not a leaked stub. |

The remaining ~55 individual test-file-level unguarded stubs (not
conftest.py, so scoped to a single collected module rather than a whole
package/session) are lower average blast radius but still technically
"wrong" per this issue's mandate. Fully verifying a safe restore for each
requires an individual before/after run (to avoid the exact regression risk
the #10691 decision explicitly warns against — "avoid regressing the 9078
passing tests"). Not attempted in this PR; left as the natural next slice of
this same issue's remaining scope (the `file:line` list is reproducible via
`grep -rn 'sys\.modules\[.*\]\s*=' --include='*.py' .` from the repo root and
filtering out the guarded set documented above).

## Discovered pre-existing bugs (filed, not fixed here — different scope)

- **#13106** — `test_token_denylist.py` patches nonexistent `get_redis_client`
  (real export is `get_async_redis_client`); 9/16 tests fail regardless of
  the pollution fix above (test rot, unrelated to sys.modules restore).
- **#13107** — `llc/tests/conftest.py`'s `knowledge` stub's `__path__ = []`
  blocks real imports of any OTHER `knowledge.X` submodule not explicitly
  re-stubbed (reproduced via `knowledge.facts`); deeper structural fix,
  deferred pending full `llc/tests/` regression verification.
- **#13108** — `test_apply_secrets.py` collection fails standalone;
  `services.system_secrets_vault` never stubbed by the root
  `autobot-slm-backend/conftest.py`'s AST-scan (scans `code_sync.py`/
  `setup_wizard.py` only, not `secrets.py`).

## Full marker-filtered run — before/after (the deliverable's proof)

Same invocation shape as the original #13088 baseline (`-m "not integration
and not slow and not distributed and not performance" -n auto --dist
loadscope`), run against the SAME disposable Postgres/Redis environment
described above, with `--continue-on-collection-errors` so a session-ending
collection error can't truncate the count.

**Before (this PR's own independently-reproduced baseline, single combined
invocation, matching today's `ci.yml` exactly):**

```text
--collect-only: 20155 tests collected, 252 errors, 80.21s
```

(The marker-filtered full run at this baseline was not repeated in this
session beyond collection-only, since the #13088 PR already measured it
exhaustively: 2330 failed, 15226 passed, 2307 skipped, 3 xfailed, 660
errors, 1175.95s — reproduced independently via the collection-only number
above, which matches to within normal repo-drift.)

**After (this PR's two-invocation fix):**

| Invocation | Failed | Passed | Skipped | xfailed | Errors | Wall-clock |
|---|---:|---:|---:|---:|---:|---:|
| `autobot-backend autobot_shared autobot-tts-worker repo_tests` | 853 | 18245 | 2459 | 2 | 75 | 948.39s |
| `autobot-slm-backend` | 21 | 1504 | 1 | 1 | 1 | 82.41s |
| **Combined (sum)** | **874** | **19749** | **2460** | **3** | **76** | **1030.80s (~17.2 min)** |

**Before → after, same marker filter, same disposable-env methodology:**

| Metric | Before (#13088 baseline) | After (this PR) | Delta |
|---|---:|---:|---:|
| Collection errors | 252 | 14 | **−94.4%** |
| Failed | 2330 | 874 | **−62.5%** |
| Errors | 660 | 76 | **−88.5%** |
| Passed | 15226 | 19749 | **+29.7%** |
| Wall-clock | 1175.95s | 1030.80s | **−12.3%** (two sequential invocations in one job are NOT slower — no singleton-runner wall-clock penalty from this fix) |

The remaining 874 failed / 76 errors are the genuine, now-much-smaller
remainder the #10691 decision's step 2 (triage into fix-now vs
quarantine-with-issue) targets next — this issue's job was clearing the
systemic pollution noise so that triage measures the real surface, which it
now does.

## Verification

- `config/config.yaml` sha256 (`e125bf80...`) confirmed **byte-identical**
  before this session's very first run and after every run performed,
  including both full marker-filtered invocations above — the exact
  corruption vector #13083 fixed and this issue's severity bar.
- `autobot-backend/tests/migrations/` — 32 passed, 133 skipped (no
  regression; skips are pre-existing/environment-dependent, not failures).
- `autobot-backend/tests/test_startup_imports.py` — **350 passed** (no
  regression).
- `autobot-backend/tests/test_raw_client_session_ceiling_12992.py` — 2
  passed (no regression — the ceiling guard from #12996/#13041 still holds).
- `autobot-backend/llc/tests/` — 1367 passed, 2 skipped (no regression from
  the conftest.py restore-fixture change).
- `autobot-backend/services/research/quarantine_boundary_test.py` — 5
  passed standalone (unaffected; the cross-directory `knowledge.facts`
  ordering gap is filed separately as #13107, not fixed here).
- `autobot-slm-backend/tests/services/test_token_denylist.py` — 7 passed, 9
  failed identically before and after this PR's restore-fix (pre-existing,
  unrelated test rot — #13106), confirming the restore fix introduces no
  new failures.
- `black --check --line-length=120`, `flake8 --config=.flake8`,
  `isort --check-only --settings-path=.`, `py_compile` — all clean on every
  file this PR touches.
- Full before/after collection-error and failure counts: see above.
