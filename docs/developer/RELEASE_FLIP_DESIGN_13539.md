<!--
Copyright 2025-2026 mrveiss
SPDX-License-Identifier: Apache-2.0
-->

# Release directories with an atomic pointer flip (#13539, #15092)

**Status:** design, not implemented. Owner decision recorded on #13539 (3 Sep 2026): build the
release-directory-with-atomic-pointer-flip scheme as the permanent fix. Stopping services during
the changeover is authorised, so restart cost is not a design constraint.

**Revision 2 (3 Sep 2026).** Revision 1 conceded ground in five places — a shared venv, compat
symlinks, an optional V5, frontends outside the release, and a rollback that could silently be a
lie. The owner rejected the cheaper stop-sync-start variant and directed that this defect class be
made *permanently impossible* rather than minimally patched. Every one of those concessions is
withdrawn below. The layout, the single `rename(2)`, the launcher pinning, the semantic
verification and the six-writer chokepoint are unchanged.

**Scope:** both writers of the deployed tree, in one change — the update playbook
(`autobot-slm-backend/ansible/playbooks/update-all-nodes.yml`) and the drift-resolve path in
`autobot-slm-backend/api/code_sync.py` (#15092). Landing one without the other makes the guarantee
true of one writer and silently false of the other.

Throughout, `<ROOT>` means the deployed root that `services/drift_checker.py:831`
(`get_default_deployed_dir`) derives from `SLM_DEPLOYED_ROOT`. No path in this design is a literal.

---

## 0. What is actually broken, restated as an invariant

A running CPython process resolves an import **lazily**, at first import, against whatever is on
disk at that instant. `sys.modules` is never re-read. Therefore:

> **Invariant R:** every path a live interpreter can import from — source tree *and*
> `site-packages` — must be immutable for the whole lifetime of that interpreter.

Revision 1 stated R over the source tree only. That was too weak, and §1.8 shows why: with a shared
venv the `site-packages` half is a live import surface that `pip` writes to, and one file in it
points straight back at the live source tree. R now covers both halves, and the design satisfies it
for both.

Every measured symptom of #13539 is a violation of R:

| Writer | Where | Violates R by |
|---|---|---|
| update playbook | `update-all-nodes.yml:307-341, 756-766, 1169-1535` — `unarchive: dest: <ROOT>/` | extracting 2000+ `.py` files over the live tree; the restart is ~300 tasks later at `:1080` |
| resolve job | `api/code_sync.py:402` | `_rsync_component_local(dest_dir=get_default_deployed_dir(component))` |
| drift-resolve endpoint | `api/code_sync.py:1093` (`_drift_resolve_rsync_or_fail`, `:994`) | same destination, different entry point (#15092) |
| shared-first sync | `api/code_sync.py:2925` (`_ensure_autobot_shared_synced`) | rewrites the live `autobot_shared` on **every** backend resolve |
| constraints deploy | `api/code_sync.py:1830` (`_deploy_constraints_dir`) | delete-style rsync into a hardcoded `/opt/autobot/constraints/` |
| root requirements | `api/code_sync.py:1858` (`_deploy_repo_root_requirements`) | `cp` into `_get_deploy_base()` |
| **pip, on every deps deploy** | `roles/backend/tasks/main.yml:812-818`; `_install_pip_deps_for_component` | rewrites `site-packages` under the live interpreter — the same defect, in the other half of the import surface |

**#15092 undercounts.** It names one call site; there are four rsync writers plus two file writers
plus the installer. A design that fixes named call sites will miss some. The design below fixes the
*destination*, and guards the *chokepoint*, so all seven are covered by construction.

Shrinking the window is not fixing it. The three measurements are 22 m 00 s, 3 m 44 s, 25 m 36 s —
the variance is the point; it does not converge on "small enough".

---

## 1. Layout

### 1.1 The tree

A release now contains **everything the node executes**: source, the virtualenv, `node_modules`, and
the built frontend bundles.

```
<ROOT>/
  releases/
    <release-id>/                  <- immutable once published; shaped like the repo root
      autobot_shared/
      libs/  autobot-plugins/  constraints/  requirements.txt
      autobot-backend/
        autobot_shared -> ../autobot_shared            (relative)
        venv/                                          (1.9 — IN the release)
        .env    -> ../../../shared/autobot-backend/.env
        data    -> ../../../shared/autobot-backend/data
        logs    -> ../../../shared/autobot-backend/logs
        config  -> ../../../shared/autobot-backend/config
        .deployed_commit -> ../../../shared/autobot-backend/.deployed_commit
      autobot-slm-backend/   (same shape)
      autobot-npu-worker/  autobot-browser-worker/  autobot-ai-stack/
      autobot-frontend/
        node_modules/                                  (1.10 — IN the release)
          @autobot/ui -> ../../../libs/autobot-ui      (relative, resolves in-release)
        dist/                                          (built here; nginx root points at it)
      autobot-slm-frontend/  (same shape)
      RELEASE.json                                     (§9)
    <release-id>.incomplete/       <- a build in flight; can never be flipped to
  current  -> releases/<release-id>          <- THE pointer. One per node.
  previous -> releases/<older-id>            <- rollback target and asset fallback (1.10)
  shared/                                    <- host state ONLY; the exception list of §1.7
    autobot-backend/{.env,.env.*,data,logs,config,.deployed_commit}
    autobot-slm-backend/{...}
    wheels/                                  <- wheel cache (1.9)
  code_source/                               <- unchanged: the git checkout
```

`shared/` is now *strictly* host state: exactly `HOST_STATE_EXCLUDES`
(`services/deploy_artifacts.py:69-77`), which already has a guard test
(`tests/api/test_host_state_excludes_14231.py`). `venv` has left it, `node_modules` never entered
it, and there is no other category. That shrinkage is what makes §1.7's containment rule
exception-free in practice.

There are **no compatibility symlinks at `<ROOT>` level.** See §1.7.

### 1.2 Scope: the whole node

`current` covers everything a release can contain — the Python import surface, the virtualenvs, the
npm trees and the built bundles. One flip publishes the node. The frontends are no longer a separate
vintage; see §1.10 for why that is now cheap and what it fixes for free.

### 1.3 Env-backed configuration

New env-backed module constants in `services/release_layout.py` — the same shape as `_SNAPSHOT_KEEP`
(`api/code_sync.py:2531`) and `backup_retention_count` (`config.py:198`):

| Constant | Env var | Default | Meaning |
|---|---|---|---|
| `RELEASES_DIRNAME` | `AUTOBOT_RELEASES_DIRNAME` | `releases` | directory under `<ROOT>` |
| `CURRENT_LINK_NAME` | `AUTOBOT_CURRENT_LINK` | `current` | the pointer's name |
| `PREVIOUS_LINK_NAME` | `AUTOBOT_PREVIOUS_LINK` | `previous` | rollback pointer |
| `SHARED_STATE_DIRNAME` | `AUTOBOT_SHARED_STATE_DIR` | `shared` | host-state root |
| `RELEASE_KEEP` | `AUTOBOT_RELEASE_KEEP` | `3` | retention count (§6) |
| `RELEASE_MIN_AGE_H` | `AUTOBOT_RELEASE_MIN_AGE_H` | `6` | prune grace period (§6) |
| `RELEASE_MIN_FREE_MB` | `AUTOBOT_RELEASE_MIN_FREE_MB` | `4096` | absolute free-space floor (§8.6) |
| `RELEASE_INCOMPLETE_TTL_H` | `AUTOBOT_RELEASE_INCOMPLETE_TTL_H` | `24` | sweep age for `*.incomplete` |
| `RELEASE_HEALTH_TIMEOUT_S` | `AUTOBOT_RELEASE_HEALTH_TIMEOUT_S` | `180` | post-flip gate budget (§8.8) |
| `WHEEL_CACHE_DIR` | `AUTOBOT_WHEEL_CACHE_DIR` | `<ROOT>/shared/wheels` | offline wheel source (§1.9) |
| `VENV_MAX_AGE_D` | `AUTOBOT_VENV_MAX_AGE_D` | `30` | forced re-resolve interval (§13.1) |

Release id: `<utc-compact-timestamp>-<short-commit>`, e.g. `20260903T114500Z-6a0f4b296`. Sortable,
unique per deploy even for a redeploy of the same commit, carrying the commit the playbook already
computes (`deploy_commit_full`, `update-all-nodes.yml:253`).

### 1.4 Every intra-release link is relative — no exceptions, no allowlist erosion

Today the playbook writes an **absolute** `autobot_shared` link in five places
(`update-all-nodes.yml:405, 417, 791, 1554, 1595`):

```yaml
src: /opt/autobot/autobot_shared
dest: /opt/autobot/autobot-backend/autobot_shared
state: link
```

Inside a release that escapes the release and points back at the live tree. All five become relative
(`autobot-backend/autobot_shared -> ../autobot_shared`). The npm workspace links are already relative
(`node_modules/@autobot/ui -> ../../../libs/autobot-ui`, per
`repo_tests/deployed_workspace_packages_15462_test.py`), so once `libs/` is inside the release they
resolve in-release with no change at all.

That leaves exactly one category of link that legitimately leaves a release: host state. §1.7 states
the rule that keeps it from becoming a growing exception list.

### 1.5 `constraints/` and the root `requirements.txt` — solved for free

`autobot-backend/requirements.txt` uses `-c ../constraints/shared.txt` and `-r ../requirements.txt`,
which is why `code_sync.py:1822` hardcodes `/opt/autobot/constraints/` and `:1858` copies into
`_get_deploy_base()`. Because a release is shaped like the repo root, those `../` references resolve
**inside the release** automatically. Two hardcoded paths disappear and the dependency pins become
part of the release rather than a shared mutable file.

### 1.6 (withdrawn) Compatibility symlinks

Revision 1 kept `<ROOT>/<component> -> current/<component>` and called it "a designed hole" whose
only defence was a guard test. That is withdrawn. See §1.7.

### 1.7 No compat symlinks: every consumer is converted, and containment has one exact exception

Each consumer of a flat `<ROOT>/<component>` path is one of exactly three kinds, and each gets a
correct answer rather than a shim:

| Kind | Consumer | Converted to |
|---|---|---|
| **Pinned process** — must never follow the pointer | backend, slm-backend, celery, celery-beat, npu, browser, ai-stack | the resolved release path, injected by the launcher (§3.2) |
| **Pointer follower** — *should* follow the pointer, has no long-lived state | nginx `root` (`roles/frontend/templates/nginx-frontend.conf.j2:56`, `frontend_dist_dir`) | `<ROOT>/current/<component>/dist`, explicitly and deliberately |
| **Host-state reader** — never wanted the code tree at all | logrotate, `.env` readers, backup jobs, `AUTOBOT_SNAPSHOT_DIR` | `<ROOT>/shared/<component>/...`; the snapshot dir retires entirely (§4.3) |

Nothing is left over, so nothing needs a shim. `<ROOT>` after migration contains `releases/`,
`current`, `previous`, `shared/`, `code_source/` and nothing else.

**Containment rule (verifier check V3), stated so it cannot erode:**

1. Every symlink inside a release whose name is **not** in `HOST_STATE_EXCLUDES` must `realpath` to a
   location inside that same release.
2. Every symlink whose name **is** in `HOST_STATE_EXCLUDES` must `realpath` to *exactly*
   `<ROOT>/<SHARED_STATE_DIRNAME>/<component>/<the same name>` — string equality against a computed
   target, not "somewhere under `shared/`".
3. There is no third rule and no per-path allowlist. The exception set is derived from
   `HOST_STATE_EXCLUDES`, which is itself guard-tested; adding an exception means adding host state,
   which fails that test unless it is genuinely host state.

Rule 2 is the anti-erosion mechanism: a wildcard ("under `shared/`") would let a future link point at
`shared/../releases/<other>/x` and pass. Exact target equality cannot.

### 1.8 The trap that makes per-release venvs mandatory, not merely nicer

`autobot-backend/requirements.txt:1` is:

```
-e ../autobot_shared
```

An **editable install**. `pip install -e` writes an absolute path into `site-packages` — as a `.pth`,
an `__editable__` finder module, or both. Installed from the deployed backend directory, that
absolute path is the **live** `autobot_shared` tree.

Consequences, which revision 1 missed:

- With a shared venv, `import autobot_shared` is satisfied by a path baked into `site-packages`,
  **regardless of `PYTHONPATH`**. The launcher's pinning does not cover it. A running process would
  keep importing `autobot_shared` from the live tree, and the flip would expose new shared code to
  it — reproducing #13539 in the exact module the incident named
  (`autobot_shared.auth.permissions`), with the fix in place and looking correct.
- So revision 1's shared venv did not merely make rollback incomplete. It left the headline defect
  reachable. That is the strongest available argument for §1.9 and it is a defect in the previous
  revision of this document, not a hypothetical.

Under §1.9 the editable install resolves to `<release>/autobot_shared`, inside the release, and V7
asserts it.

### 1.9 Per-release virtualenv — verdict: yes

**Verdict: each release owns its venv, at `<release>/<component>/venv`.** Reasoning, in order:

1. **Correctness.** `pip` writing into a live `site-packages` is an invariant-R violation of exactly
   the same kind as rsync writing into a live source tree. A design that claims the defect class is
   impossible cannot leave one writer pointed at a live import surface.
2. **§1.8.** With a shared venv, pinning is not merely incomplete, it is defeated for
   `autobot_shared`.
3. **Rollback becomes true.** Code and dependencies flip together, so `previous` is the configuration
   that was actually working, not its source half.
4. **The stop-for-pip conditional disappears.** `pip` runs into the staged release, which nothing is
   executing. The only stop is the restart itself (§3.3).

**Cost, addressed concretely.** The backend venv is heavy — `torch==2.13.0`, `torchvision`,
`sentence-transformers`, `chromadb` (`autobot-backend/requirements.txt:42-48`) — realistically
several GB. A naive copy per release would be unacceptable. It is not needed:

> **Seeding rule.** If the release's `requirements_sha256` equals the previous release's, hardlink-copy
> the previous venv (`cp -al`) and **run no installer at all**. If it differs, build a fresh venv and
> install from the wheel cache. **Never install into a hardlink-seeded venv.**

- The common deploy (deps unchanged — the playbook already computes `python_deps_changed` at
  `update-all-nodes.yml:229`) costs **zero additional bytes and seconds**, and the hardlinks are only
  ever read, so sharing is safe by construction rather than by discipline.
- The rare deploy that changes deps builds a fresh venv **inside the staged release, off the critical
  path**: nothing live depends on it and no service is stopped while it runs. Wall-clock cost, not
  downtime.
- The wheel cache at `WHEEL_CACHE_DIR` is populated by `pip download`/`pip wheel` during the build and
  reused with `--find-links <cache> --prefer-binary`; a fully-cached rebuild is local-disk only. The
  network is a fallback, not a dependency, which also removes a class of deploy failure that exists
  today.
- Disk is bounded by *distinct dependency sets*, not by release count: N releases sharing one
  `requirements_sha256` share one venv's inodes. §6 adds the matching retention dimension.

**Enforcement of the seeding rule.** The publisher writes `<venv>/.seeded-from` naming the release it
was hardlinked from; any install path refuses to run when that marker is present. A hash change
deletes the seeded directory and builds fresh rather than upgrading in place.

**The shebang trap.** A hardlink-seeded venv keeps the previous release's absolute paths in
`venv/bin/*` shebangs — so `venv/bin/uvicorn` in release B would exec release A's interpreter and pin
the process to the wrong release. Three defences, all required:

1. Units invoke `venv/bin/python -m uvicorn` / `-m celery`, never the console script. PEP 405 locates
   `pyvenv.cfg` next to the invoked `sys.executable` before symlink resolution, so `sys.prefix` is
   the invoking release's venv and `site-packages` resolves in-release.
2. After seeding, `venv/bin/` is materialised as a **real copy** (a few MB) with shebangs rewritten to
   the new release. Everything under `lib/` stays hardlinked.
3. Verifier check **V6**: no shebang, `.pth`, `RECORD`, `direct_url.json` or `__editable__*` entry
   anywhere under the release names a path outside it.

**`uv`:** it would cut a changed-deps build from roughly ten minutes to about one, and it is the
obvious accelerator. It is deliberately **not** part of this design: its resolver differs from pip's
against a `-c constraints/shared.txt` file that exists precisely because resolution here is
delicate (`requirements.txt` comments record two resolver incidents already), and coupling a
correctness change to a resolver swap makes both harder to review and to revert. Evaluate it as a
separate change once releases exist; the build step is one function and swapping it later is local.

### 1.10 Frontends in the release

Same seeding rule, keyed on `package-lock.json`'s hash:

- lock unchanged → hardlink-copy `node_modules` from the previous release, run no npm command.
- lock changed → `npm ci` in the staged release. `npm ci` removes `node_modules` before extracting,
  so it never writes through a hardlink; the seed is simply discarded.
- `vite build` writes `dist/` inside the staged release. The frontend's own `current`/`previous`
  pointers (#15610) retire: the staged release *is* the staging directory and `<ROOT>/current` is
  already the one pointer, so the component-scoped flip collapses into the node-scoped one.

**What this fixes for free.** #15462's outage was `node_modules/@autobot/ui -> ../../../libs/autobot-ui`
resolving into the **live** tree, so the build read a `libs/` that had not been deployed since July.
With `libs/` inside the release, that relative link resolves in-release and the build can only read
the source it was built from. The invariant `deployed_workspace_packages_15462_test.py` enforces by
enumerating archive entries becomes structural.

**One new user-visible edge, and its fix.** nginx re-resolves `root` per request, so a client that
loaded `index.html` from release A and then requests `assets/index-<hash>.js` after a flip would 404 —
the hashed asset lives in A's `dist/`, and `root` now names B's. This is not new with the release
scheme: it is equally true of #15610's per-component flip and of #15430's two `mv`s before it, and it
is tracked on its own (#15653). The release scheme can fix it in one location block:

```
location /assets/ { try_files $uri @previous_assets; }
location @previous_assets { root <ROOT>/previous/<component>; }
```

One release back, which is what retention guarantees. Worth stating that this is a *new* nginx
config responsibility introduced by the change, not a pre-existing behaviour preserved.

### 1.11 Relationship to the `dist.staging` precedent (#15430 / PR #15556)

**Same idea, strictly stronger mechanism, and now the same mechanism.** #15430 is "build into a
staging directory, verify one artifact exists, publish only on success, keep the previous output
serving on failure" — the failure path is exactly right: a failed build never touches `dist`.

Revision 1 kept the two schemes side by side. Revision 2 subsumes it: the frontends move into the
release (§1.10), so there is one staging concept, one publish, one previous. The two differences that
motivated the upgrade remain the justification for the shape:

1. **The publish is atomic.** #15430 published with two `mv`s; between them `dist` did not exist.
   Tolerable for nginx (a request 403s and the user retries), intolerable for an interpreter, where
   a failed import is cached and a name that exists reads as missing. #15610 has since removed that
   window for the SLM frontend specifically — the served path is a `current` symlink replaced by a
   single `rename(2)` in `roles/_shared/tasks/build_publish_slm_frontend.yml` — which is this
   scheme's mechanism (§2) applied to one component. What remains for this design is the *scope*:
   the Python import surface and the venv, which a per-component frontend flip does not touch.
2. **Verification is semantic, not existential.** `index.html exists` is right for a bundle;
   `main.py exists` would not have caught #13539 at all — every file involved existed and was
   byte-identical across three copies. §8.

---

## 2. The flip

### 2.1 Syscall sequence

One function in `services/release_publisher.py`. All operations use directory file descriptors so an
ancestor rename cannot redirect them mid-sequence.

```
rootfd = open(<ROOT>, O_RDONLY|O_DIRECTORY)
intended = "releases/<new-id>"
prior    = readlink("current", dir_fd=rootfd)          # recorded for §8.8's revert

# 1. record the rollback target (idempotent; a crash here is harmless)
symlink(prior, ".previous.tmp.<pid>", dir_fd=rootfd)
rename(".previous.tmp.<pid>", "previous", src_dir_fd=rootfd, dst_dir_fd=rootfd)

# 2. THE FLIP
symlink(intended, ".current.tmp.<pid>", dir_fd=rootfd)
rename(".current.tmp.<pid>", "current", src_dir_fd=rootfd, dst_dir_fd=rootfd)

# 3. durable before anything acts on it
fsync(rootfd)

# 4. self-check (§8.8): confirm we published what we meant to
assert readlink("current", dir_fd=rootfd) == intended
close(rootfd)
```

Targets are **relative** (`releases/<id>`) so the whole root is relocatable and `SLM_DEPLOYED_ROOT`
remains meaningful.

### 2.2 Why this is atomic and the obvious alternative is not

`rename(2)` within one directory on one filesystem is atomic with respect to other processes: POSIX
requires a concurrent lookup of the destination name to see either the old link or the new one, and
never absence. The kernel swaps one directory entry.

`unlink("current"); symlink(new, "current")` — what `rm && ln -s` does, and what `ln -sfn` may do
depending on coreutils version — has a window in which `<ROOT>/current` **does not exist**. A process
resolving through it then gets `ENOENT`; for the interpreter that is an `ImportError`/`OSError` on a
module present on disk — the same misleading failure class this issue exists to remove, produced by
the fix. A crash in the window leaves the node with no pointer and nothing serving.

The design uses no `ln -s` for the pointer. Guard test T4 asserts it: no `ln -sf`/`ln -sfn` on the
pointer name in any ansible task, and the publisher's AST contains `os.rename`/`os.replace` on the
pointer and no `os.unlink` of it. `mv -T <tmp> current` is `rename(2)` and is the acceptable shell
equivalent.

### 2.3 What each reader observes

| Reader | At t-1 | During rename | At t+1 |
|---|---|---|---|
| Process pinned to old release (§3) | old tree | **does not read `current` at all** | old tree |
| A newly-exec'd process | old release | one side or the other, never both | new release |
| `open("<ROOT>/current/x/y.py")` | old `y.py` | old or new, never a mix, never ENOENT | new `y.py` |
| An `open` fd taken before the flip | still valid — fds are inode handles | | |
| `readlink("<ROOT>/current")` | `releases/<old>` | one or the other | `releases/<new>` |
| nginx (`root` via `current`) | old bundle | old or new per request | new bundle |

The flip is **invisible to every running Python process**, which is the point, and is why §3 matters
more than §2.

---

## 3. Restart, and the pinning that makes the flip a fix

### 3.1 The flip alone fixes nothing

If the running interpreter's import surface contains `<ROOT>/current/...` as a **string** — in
`sys.path`, in `PYTHONPATH`, in `AUTOBOT_BASE_DIR`, or in a `.pth` inside `site-packages` — the flip
makes the new tree visible on the next lazy import and #13539 reproduces with a window of
flip-to-restart. Shorter, identical failure. The owner flagged exactly this: *"the pinning is the
part that must not be dropped in review."*

Revision 2 adds two surfaces revision 1 did not pin: `AUTOBOT_BASE_DIR` (§3.2 step 3) and
`site-packages` (§1.8/§1.9).

### 3.2 The launcher

Every managed Python unit's `ExecStart` becomes a launcher shipped **inside the release**
(`autobot_shared/deploy/release_exec.py`, so it versions with the code it launches):

1. `dirfd = os.open(os.path.dirname(__file__), O_RDONLY|O_DIRECTORY)`, then
   `os.readlink(f"/proc/self/fd/{dirfd}")` — resolution through an **inode handle**, so it names the
   release this launcher was actually loaded from. A flip landing between systemd's exec and this
   line cannot split the process across two releases.
2. Export `AUTOBOT_RELEASE_ROOT=<resolved>` and `AUTOBOT_RELEASE_ID=<id from RELEASE.json>`.
3. Export **`AUTOBOT_BASE_DIR=<resolved>`**. `autobot_shared/ssot_config.py:1330` reads this as the
   SSOT base for `config.path.resolve()`; leaving it at `<ROOT>` would make every SSOT-resolved path
   — including `frontend_bundle_health.bundle_dir()` — point at the live tree while the process
   itself is pinned. A pinned process with an unpinned config resolver is not pinned.
4. Build `PYTHONPATH` from **resolved** paths only. No entry contains the pointer name.
5. `os.chdir(<resolved>/<component>)` — cwd is an inode reference, so it stays pinned even if the
   directory is renamed or the pointer moves. This is also the primary release-identity signal (§9).
6. `os.execv(<resolved>/<component>/venv/bin/python, ["-m", <entrypoint>, ...])` — never a console
   script (§1.9).

The interpreter starts with no occurrence of `current` in its environment, `sys.path`, cwd, or
`site-packages`. It imports from its own frozen release for its entire life. Invariant R holds for
both halves of the import surface because the release is never written again: releases are built
under `<id>.incomplete` and become `<id>` by a rename at the moment they are complete.

**Alternative considered and rejected for v1:** systemd `RootDirectory=`/`BindPaths=`. Strictly
stronger — the process could not reach another release even deliberately — but it breaks
`EnvironmentFile`, `StandardOutput=append:` log paths and `sudo systemctl` interactions, and makes
every debugging session a namespace-entry exercise. The natural v2 if pinning is ever shown to leak.

### 3.3 Ordering

Per node. Note there is no longer a conditional stop: with the venv inside the release, no step
before the flip writes to anything a live process can reach.

```
 1. preflight     prune first; free space >= max(floor, 1.2 x previous release size);
                  pointer is a symlink; no stale .incomplete; acquire flock
 2. build         extract/copy source into releases/<id>.incomplete          [nothing live touched]
 3. venv          seed by hardlink if requirements_sha256 unchanged, else build fresh (§1.9)
 4. node_modules  seed by hardlink if lock hash unchanged, else npm ci (§1.10)
 5. bundles       vite build into <release>/<component>/dist
 6. link state    the HOST_STATE_EXCLUDES symlinks only (§1.7)
 7. migrate       alembic upgrade head, run FROM THE STAGED RELEASE, after the existing pg_dump
                  (§7A) — expand-only by policy, so N-1 code keeps working if the flip is refused
 8. verify        V1-V7 against the STAGED tree (§8)                         [nothing live touched]
 9. rename        releases/<id>.incomplete -> releases/<id>                  [atomic; still not live]
10. stop          the units
11. FLIP          §2.1, including the pointer self-check                     [atomic]
12. start         the units
13. gate          §8.8: every unit active, in the new release, health not degraded-for-release;
                  exactly one auto-revert on failure
14. prune         §6, only after 13 passes
```

**Why steps 1-9 cannot reopen the window:** nothing in them writes to any path a running process can
reach. The release under construction is a directory no live process has ever resolved, and its venv
is either brand new or a read-only hardlink set.

**Why the stop is now unconditional and trivial:** it is a `systemctl stop` immediately before the
flip and a `start` immediately after — seconds, not the length of anything. Revision 1's "stop only
if deps changed" existed solely because `pip` wrote to a shared venv. It is gone.

**Why step 12 is after step 11:** a process started before the flip pins the *old* release and is
immediately stale.

**Why migrations run at step 7, before the flip:** a failed migration must fail the deploy while the
old code is still published and the pg_dump is fresh. This is only safe because migrations are
expand-only by policy (§7A); if step 8 or 13 then refuses the release, the old code runs against an
expanded schema, which by definition it tolerates.

**Downtime:** the stop/start pair. Today's 25 m 36 s silent window becomes a few seconds of
deliberate, visible downtime.

**The self-killing component.** `autobot-slm-backend` restarts itself (`code_sync.py:1731`,
`_SELF_SERVICE_NAME`; `_restart_pending` at `:1732`). It flips first, `fsync`es the root directory
(step 3 of §2.1 — this is why it is not optional), performs the pointer self-check, and only then
issues its own restart. Safe precisely because it is pinned: between flip and its own death it keeps
importing from its old release. Without the `fsync`, a power loss at that instant could leave the
pointer unflipped and the new release orphaned. Its post-flip gate (§8.8) is necessarily performed by
the *new* process on startup, which reads `previous` and auto-reverts if it cannot reach health — the
one case where the gate is not held by the publisher.

---

## 4. Both writers

### 4.1 What they share

One implementation, several entry points:

- `services/release_layout.py` — pure path/id logic, no I/O beyond `stat`. Everything from
  `SLM_DEPLOYED_ROOT`.
- `services/release_publisher.py` — build, seed, link, rename, flip, gate, prune, rollback, lock.
- `services/release_venv.py` — §1.9: hashing, seeding, wheel cache, fresh build, `bin/` rehoming.
- `services/release_bundle.py` — §1.10: `node_modules` seeding and the bundle build.
- `services/release_verifier.py` — §8.
- `services/release_migrations.py` — §7A: expand/contract classification and rollback refusal.
- `tools/release_flip.py` — a thin `__main__` over the above with **no third-party imports**, so
  ansible can run it with the system interpreter.
- `autobot_shared/deploy/release_exec.py` — the launcher (§3.2).
- `autobot_shared/deploy/release_probe.py` — the health probe (§9.4), in `autobot_shared` because
  both backends must expose it.

**Why shared rather than two implementations:** the writers must agree on where releases live, what
"verified" means, and the exact flip sequence. Divergence in any of the three is the #15092 failure
mode; divergence in the third is a corrupted node. A shared helper makes agreement structural instead
of a review responsibility. The counter-argument — ansible calling into SLM backend code couples the
playbook to the service — is answered by the CLI: the playbook invokes a **script inside the release
it is publishing**, with the system python. The release owns the definition of how to publish itself,
which also makes the migration self-bootstrapping (§10).

### 4.2 The update playbook

Smaller than it sounds: the playbook already builds tarballs with `git archive`
(`update-all-nodes.yml:117-119`) and extracts them (`:307-341`, `:756-766`, `:1169-1535`). Extraction
into an **empty release directory** is already a staged build; the defect is that `dest:` is the live
root.

- Play 0 computes `release_id` once from `deploy_commit_full` and passes it to every play.
- Every `unarchive: dest: <ROOT>/` becomes `dest: <ROOT>/releases/<id>.incomplete/`.
- The npm/vite tasks (`:494-573`, `roles/slm_manager/tasks/main.yml:820-856`) run with `chdir` inside
  the staged release; the frontend's own `current`/`previous` flip tasks are deleted (§1.10).
- New tasks: seed/build venv, seed/build node_modules, link host state, migrate, verify, rename,
  stop, `release_flip publish`, start, gate.
- The existing explicit restarts (`:1080` backend, `:1114` celery, and `:1209/:1266/:1348/:1468/:1512`)
  stay explicit. They must **not** become handlers: #15323 measured 12 handler runs on a deploy that
  wrote 3,887 `.py` files, of which **zero** were the backend or celery restart, because a handler
  only fires on `changed` and nothing notified it. The comment at `:1100-1103` already records this;
  ordering test T5 makes it structural.

A useful side effect: `git archive` into an empty directory produces a tree with no stale leftovers,
so "a file deleted upstream lingers on the host forever" disappears for the playbook path without a
delete-style rsync.

### 4.3 Drift-resolve (#15092's AC1)

**It can build and flip a release, and it should.** Refusing drift-resolve while the release scheme is
active was considered and rejected — an operator resolving drift is usually recovering from a broken
deploy, and removing the recovery tool at that moment is worse than the problem.

```
1. cp -al  <current release>/  ->  releases/<id>.incomplete/     (hardlink copy; §4.4 governs writes)
2. rsync -a --whole-file --delete <source>/ -> releases/<id>.incomplete/<component>/
3. re-seed venv/node_modules only if the relevant hash changed; relink host state
4. verify (§8); rename; stop; flip; start; gate
```

Drift-resolve now builds a **whole release**, not a component-shaped one. That is forced by the
pointer being per-root, and it is correct anyway — `autobot_shared` is the shared import surface, and
`_ensure_autobot_shared_synced` (`:2925`) already recognises this by syncing shared ahead of every
backend resolve. One release, one flip, one restart set.

The deletion guard (`_resolve_deletion_guard`, `:1511`) and the shared-first sync keep working; they
now run against the staged copy, so a refused resolve leaves the live tree untouched by construction
rather than by an early return.

**`_snapshot_component` / `_rollback_component` / `_prune_old_snapshots` (`code_sync.py:2530-2594`)
are subsumed and must be retired in the same change.** The previous release *is* the snapshot, and a
better one: verified, actually-was-running, and reverted by a rename instead of a delete-style rsync
over a live tree. Two rollback stories that can disagree is how #15323 happened — the weaker one had
a defect defended by a passing test. Retiring it also funds the line budget for the ratchet (§15 B1).

### 4.4 Hardlink write discipline

`cp -al` shares inodes with the previous release. Three rules, each with a guard test, make a change
to the new release incapable of mutating the old one:

1. **Nothing in a staged release is modified in place.** Every change is write-new-then-rename.
   rsync's default already does this (temp file + rename, which breaks the link); the argv adds
   `--whole-file` to remove the delta path entirely and must never contain `--inplace`, `--append` or
   `--append-verify`. Guard T6 asserts the argv and proves the behaviour: after a real rsync over a
   seeded fixture, the changed file's `st_nlink` is 1 and the previous release's copy is byte-identical
   to what it was.
2. **No installer ever runs into a seeded tree.** Enforced by the `.seeded-from` marker (§1.9) and a
   publisher refusal; a hash change deletes and rebuilds rather than upgrading in place.
3. **No metadata operation runs over a seeded tree.** `chmod`, `chown`, `utime` and `setxattr` act on
   the **inode**, so they propagate to every release sharing it. The playbook's
   `chown --no-dereference -R` (`:772`) and `file: recurse: true owner:` (`:786`) therefore must not
   run over seeded content. Fix: the publisher builds as the service user throughout and those
   recursive tasks are deleted, not reordered. This is blocker **B9**.

---

## 5. Rollback

- `<ROOT>/previous` always names the release that was current before the last flip.
- Reversing a flip is the *same* code path as making one: `release_flip publish --to <id>` performs
  §2.1 with old and new exchanged, then stop/start/gate. There is no separate, less-tested revert
  path — deliberate; the revert path is the one you need when things are already bad.
- `previous` is recomputed from the mtime-sorted release list when the symlink is missing or equal to
  `current` (recoverable from a crash mid-flip, §7 F3).
- With per-release venvs and bundles, a rollback now restores **code, dependencies and bundles**
  together. The only thing it does not restore is the database — which is why it refuses rather than
  lies (§7A).

**Operator surfaces, in order of preference:**

1. **UI** — a Releases panel in the existing maintenance/code-sync screen listing `RELEASE.json` per
   retained release with `current`/`previous` marked and a Roll back action hitting
   `POST /code-sync/releases/{id}/activate`. Same surface an operator already uses.
2. **Recovery page** — `static/recovery.html` (PR #15556, #15462) exists precisely for "the dashboard
   is what broke". Rollback belongs there.
3. **CLI** — `tools/release_flip.py --to <id>` on the host, for when nothing is serving.

All three call the same publisher function, and all three are subject to §7A's refusal.

---

## 6. Retention

- `AUTOBOT_RELEASE_KEEP`, default `3`. Mirrors `AUTOBOT_SNAPSHOT_KEEP` (`code_sync.py:2531`) and
  `SLM_BACKUP_RETENTION_COUNT` (`config.py:198`).
- Pruned by the publisher **after** §3.3 step 13 passes, never before. A prune that runs before the
  gate can delete the tree you are about to roll back to. A second prune runs at step 1 of the *next*
  build, which is where space is reclaimed ahead of a large build.
- **Never pruned, asserted immediately before each `unlink`, not merely filtered by age or count:**
  - the release named by `current` or `previous`;
  - any release younger than `AUTOBOT_RELEASE_MIN_AGE_H` (connections draining out of a
    just-flipped-from release);
  - **any release a process is in.** For every pid in `/proc`, read `cwd`, `exe`, `root` and the
    `AUTOBOT_RELEASE_ID` entry of `environ`; a release named by any of them is retained regardless of
    age or count. `cwd` alone would miss a process that chdir'd elsewhere but still has the release on
    `sys.path`; `environ` catches that.
  - **Fail closed.** If `/proc` cannot be enumerated, or any single pid read fails for a reason other
    than the process having exited, the prune is abandoned and logged. Deleting a tree out from under
    a running process is the same defect class this design removes, in reverse; "I could not check" is
    never permission.
- The venv dimension: releases with equal `requirements_sha256` share one venv's inodes, so retention
  costs distinct dependency sets, not release count. `AUTOBOT_RELEASE_KEEP` is a release count; the
  free-space preflight (§8.6) is what actually bounds disk.
- `*.incomplete` older than `AUTOBOT_RELEASE_INCOMPLETE_TTL_H` are swept at the start of the next
  build, not the end of this one — a build that died is evidence; give an operator a day.
- The prune is `rmtree` of whole release directories only. It never descends into `shared/` and never
  removes a symlink at `<ROOT>` level.

---

## 7. Failure modes

| # | Failure | State immediately after | Recovery |
|---|---|---|---|
| F1 | Build dies mid-extract / mid-rsync / mid-`pip` | `releases/<id>.incomplete` partial; `current`, `previous`, all live processes untouched | Nothing to undo. Next build sweeps `.incomplete` past its TTL. The node keeps serving old code, with its old dependencies — which is now true of `pip` failures too, unlike today. |
| F2 | Verification fails (§8) | As F1, plus the verifier's report | Never renamed to `<id>`, so it can never be flipped to. The intended catch for #13539, and it must be *loud*: the deploy fails naming the module and symbol. |
| F3 | Crash between the `previous` and `current` renames | `previous` == the release still current | Self-correcting: the next flip rewrites both. If a rollback is needed first, `previous` is recomputed from the mtime-sorted list. |
| F4 | Crash after the `current` rename, before restart | New release live on disk; processes pinned to the old one | The state #15323 measured — now detectable in one comparison (§9) and reported as `degraded` by the health probe (§9.4) within one poll. The gate restarts; if the deploy died entirely, the probe is what tells someone. No import can fail meanwhile, because the old processes never read the new tree. |
| F5 | Crash before `fsync`, then power loss | Pointer may or may not have flipped; both releases complete | Either state is consistent. On boot units start from whichever release the pointer names, verified and whole. |
| F6 | Disk fills | Preflight (§8.6) refuses before writing a byte; mid-build becomes F1 | `current` untouched, old code still serving — the property a flat rsync does not have (a full disk mid-rsync leaves a half-written *live* tree). Prune runs before the check so retention reclaims first. |
| F7 | Release complete and verified but broken at start | Units fail after the flip | `Restart=always` + `StartLimitBurst=5`/`StartLimitInterval=120` (`autobot-backend.service.j2`) bounds this to ~5 attempts in 2 minutes, then `failed` — loud, and it cannot loop an operator out of intervening. The gate (§8.8) then performs **exactly one** auto-revert to `previous` and restarts; a second failure stops and escalates rather than flapping. Every auto-revert is recorded in the job row and in `RELEASE.json`'s sibling `releases/.history`. |
| F8 | Dependency install fails | Release staged, nothing stopped, pointer not flipped | The deploy fails; nothing was stopped and nothing was published. Strictly better than today's `code_sync.py:410-421`, where a failed pip leaves the live tree rewritten and the job row committed. |
| F9 | Two writers race | Both would flip | `flock` on `<ROOT>/.release.lock` held for steps 1-14. The loser fails fast, reusing the existing `_reject_if_deploy_in_progress` 409 path (`code_sync.py:1735`). The pointer self-check (§8.8) is the backstop if the lock is ever bypassed. |
| F10 | Migration succeeds, then the release is refused (F2/F7) | Old code running against an expanded schema | Safe **only** because migrations are expand-only (§7A). This is the failure mode that makes that policy load-bearing rather than advisory, and it is why the CI classifier is a gate and not a lint. |
| F11 | Seeded venv would be mutated | — | Cannot happen by construction: `.seeded-from` blocks installers, `--whole-file` without `--inplace` blocks rsync, and the recursive `chown`s are deleted (§4.4). T6 and T13 prove each. |

---

## 7A. Migrations: expand-contract, and a rollback that refuses rather than lies

A flip does not reverse a schema change. Revision 1 recorded the alembic head and asked the operator
to notice. That is withdrawn: the tool refuses.

**Policy — expand-contract across two releases.**

- Every alembic revision declares `revision_kind = "expand" | "contract"` as a module-level attribute.
- **Expand** is additive and N-1-compatible: `CREATE TABLE`, `ADD COLUMN` nullable or defaulted,
  `CREATE INDEX`, additive enum values, new constraints that the previous code cannot violate.
- **Contract** is everything else: `DROP`, `RENAME`, `ALTER TYPE`, `SET NOT NULL` without a default,
  a data migration that destroys information.
- A contract revision may only ship in a release whose `min_rollback_target` is the release that
  introduced the matching expand. Removing the old column is therefore always at least one deploy
  behind adding the new one.

**Enforcement.** A CI test extending `autobot-backend/tests/migrations/test_ansible_migration_contract.py`
— which already asserts pg_dump before `upgrade head`, baseline adoption ordering, and
`any_errors_fatal` — adds: every revision declares `revision_kind`; the declaration matches an AST
scan of the revision's `upgrade()` for contracting DDL (a revision that says `expand` while calling
`op.drop_column` fails); and a contract revision names its `min_rollback_target`.

**Refusal.** `release_flip publish --to <id>` computes the set of revisions applied since `<id>` was
built. If any is `contract`, the flip is **refused** with the blocking revisions named. The only way
past is a different operation — restore the pg_dump the deploy took, then flip — behind an explicit
`--database-has-been-restored` flag that the UI does not offer at all. An operator cannot reach a
silently-wrong state by clicking Roll back.

**Consequence, stated plainly:** rollback is safe by construction for expand-only releases, which is
the overwhelming majority, and impossible-rather-than-wrong otherwise. The residual weakness is that
the classifier trusts a declaration checked against DDL; a destructive `UPDATE` inside an `expand`
revision passes. §13.2.

---

## 8. Verification, before the flip

This decides whether the scheme fixes #13539 or relocates it. "Run the tests" is not an answer: the
deploy host has no fixtures, no test DB, and the failure being prevented is an import-time name
binding against a *specific tree*, which a green CI run on a different machine does not establish.

All checks run against the **staged** release with cwd, `PYTHONPATH`, `AUTOBOT_BASE_DIR` and the
interpreter all pinned there.

**V1 — structural.** `RELEASE.json` parses; every component in its manifest exists and is non-empty;
per-component file count within a sanity band of the previous release (a 90% shrink is a truncated
tarball); every host-state symlink resolves.

**V2 — compile.** `python -m compileall -q -f <release>` over the staged tree. Catches syntax errors
and truncated files. Honestly: this would **not** have caught #13539 — every file compiled.

**V3 — containment.** §1.7's two rules, with no third rule and no allowlist.

**V4 — cross-module symbol check.** Static, AST-based, no interpreter, no side effects, seconds over
~4k files:

> For every `from X import a, b` in the staged tree where `X` resolves to a module **inside the
> staged release**, assert `a` and `b` are bound at module level in `X` — `def`, `class`, assignment,
> re-export, or `__all__`.

This is precisely the check the repo already decided it could not afford dynamically:
`repo_tests/first_party_imports_resolve_test.py` says in its own docstring that it *"deliberately
checks only that the **module** resolves, not that the imported *name* exists inside it. Resolving
names would mean importing the module."* V4 resolves names statically, so it costs nothing, and the
name it resolves is exactly `is_admin_role` from `api/heartbeat.py:38` — #13539's symptom.

**V5 — fresh-interpreter import sweep. Mandatory, no skips (revised).** A subprocess with the staged
release pinned, importing every module under `api/` and `autobot_shared/` for each Python component,
failing on the first `ImportError` with the module named. This is exactly what the #13539
investigation ran by hand *after* the fact (*"fresh import: OK"*, *"OK
api.codebase_analytics.endpoints.import_tree"*); the contribution is running it before the flip.

Revision 1 allowed a recorded skip. Withdrawn: a recorded skip is still a hole, and recording only
means nobody is lied to about having a hole. What it takes to make V5 always runnable:

1. **A hermetic import sandbox.** The probe runs with a generated `sitecustomize.py` on its
   `PYTHONPATH` installing `sys.addaudithook` handlers that raise on `socket.connect`,
   `subprocess.Popen`, `os.system` and `open` for write outside the release. A module with an
   import-time side effect therefore *fails the probe loudly* instead of performing the side effect.
   Deterministic, and it needs no DB, Redis or network.
2. **A CI guard that keeps the population at zero.** A new repo test importing every module under
   `api/` and `autobot_shared/` in that same sandbox. The repo already has the two adjacent halves —
   `repo_tests/collected_modules_inert_on_import_test.py` (no `sys.exit` at import) and
   `first_party_imports_resolve_test.py` (modules resolve) — so this is the third member of an
   existing family, with the same shape and the same "derive the population, don't guess it"
   discipline.
3. **The audit that guard implies.** Its first run enumerates every module with an import-time side
   effect. That list is currently unknown and is the honest unbounded part of this work (§13.6, B12).
   Sequencing: the CI guard lands **first**, independently; offenders are fixed as a tracked batch;
   only then does the release scheme's V5 become a hard gate. Until the guard is green, the release
   scheme is not deployable — which is a real dependency, not a caveat.

**V6 — no cross-release path anywhere in the venv or npm trees.** No shebang, `.pth`, `RECORD`,
`direct_url.json`, `__editable__*` entry or `node_modules/.bin` shim names a path outside this
release. This is the check that catches §1.9's shebang trap and would catch a hardlink seed whose
`bin/` was not rehomed.

**V7 — the editable install points in-release.** `autobot_shared` as imported by the staged venv
resolves to `<release>/autobot_shared`, asserted by running
`python -c "import autobot_shared, sys; print(autobot_shared.__file__)"` in the sandbox and comparing
the resolved path. §1.8 is the reason this is its own check rather than a clause of V6: it is the one
that was actually load-bearing and actually missed.

**V1-V7 are mandatory and hard-fail. There is no skip mechanism and no `RELEASE.json` skip field.**

### 8.6 Pre-flight free space

Refuse before writing a byte when
`free < max(RELEASE_MIN_FREE_MB, 1.2 x size_of(previous release, measured with du -sb --apparent-size=no))`.
Measuring the previous release rather than guessing is what makes this correct as the tree grows;
`du` counting shared inodes once matches how a hardlink-seeded release will actually consume space,
and the 1.2 factor covers the case where the seed is discarded and a fresh venv is built. The prune
(§6) runs first so retention reclaims before the check.

### 8.8 Post-flip self-check and auto-revert

1. **Pointer check**, in §2.1 step 4: re-`readlink` `current` through the same `rootfd` and assert it
   equals the intended target. A mismatch means another writer raced despite the lock; revert to the
   recorded `prior` immediately and fail the deploy.
2. **Process check**, after start: for each managed unit, `systemctl show --property=MainPID`, then
   `readlink /proc/<pid>/cwd` must equal the new release, and the unit must be `active`.
3. **Health check**: poll each component's `/health` until it is not `degraded` for the release
   reason (§9.4), within `RELEASE_HEALTH_TIMEOUT_S`.
4. **Auto-revert**: any of 2-3 failing triggers **exactly one** revert — flip back to `prior`,
   restart, re-run 2-3. A second failure stops, leaves the node on `prior`, and escalates. Never a
   third attempt; a flapping deployer is worse than a stopped one.

---

## 9. Release identity, and the probe that makes divergence self-reporting

#15323 established that three fix verifications (#14866, #14010, #13570) were wrong because the
running process predated the fix, and that the first attempt to detect this was itself wrong twice —
it checked only the first unit per component, and it compared mtimes that rsync preserves from
*source*. The lesson: "which code is this process running" must be answerable **from the process**.

### 9.1 Three artifacts, ascending trustworthiness

1. **`RELEASE.json`** in each release: `{id, commit, ref, built_at, built_by, components[],
   requirements_sha256, resolved_packages_sha256, lockfile_sha256, alembic_head,
   migrations: [{revision, kind}], verifier: {v1..v7 results}}`. Answers *what this tree is*.
   Editable by anyone with root — which is why it is not the primary.
2. **`AUTOBOT_RELEASE_ID`**, exported by the launcher (§3.2) and surfaced on `/health` and per
   component on `GET /code-sync/status`. Answers *what this process believes it is running*.
3. **`readlink /proc/<MainPID>/cwd`** — the primary. The launcher `chdir`s into the release before
   `exec`, and cwd is an **inode handle**, not a string. It cannot be falsified by a later flip, a
   rename, an mtime or a `touch`; it needs no cooperation and works on a hung process. Answers *what
   this process is actually running* — the question the three wrong verifications got wrong.

### 9.2 Detector

Extend `services/process_divergence.py` — already the right home, already free of `api.*` imports,
already correct about never collapsing "cannot tell" into `healthy`. Add an exact comparison per
unit: `release_of(MainPID) == readlink(<ROOT>/current)`. Two ids, string equality; no ctime, no
monotonic timestamps, no locale parsing. The existing ctime path stays for the `unknown` cases. The
conservative aggregation (`stale` > `unknown` > `healthy`) and the multi-unit sweep from #15323's
review are preserved unchanged — both defects that review caught would still be defects here.

### 9.3 Post-deploy assertion

#13539's outstanding unticked criterion — *"no managed service's start time predates the code it is
running"* — becomes a one-line comparison per unit, run as §3.3 step 13 and asserted as a repo test
against the playbook. From then on **a fix verification cites the release id of the process**, and
"the running process predated the fix" is checkable in one command rather than discovered three
issues later.

### 9.4 The health probe (continuous, not post-mortem)

`autobot_shared/deploy/release_probe.py`, exposed on both backends' `/health`. It follows exactly the
shape `services/frontend_bundle_health.py` established for #15462 — a filesystem-derived probe whose
string becomes a field on `HealthResponse`, with the same reasoning about why it is a local check and
not an HTTP fetch of itself, and the same rule that the response is public so **no filesystem paths
appear in it** (release ids are commit-derived and are fine).

**Comparison:** `AUTOBOT_RELEASE_ID` of this process (falling back to `readlink /proc/self/cwd` if the
env var is absent, which is itself a finding) against `readlink(<ROOT>/current)`.

| Probe result | Condition | Overall `/health` |
|---|---|---|
| `healthy` | running release == `current` | unaffected |
| `stale: running <id-a>, current <id-b>` | they differ | **`degraded`** |
| `unknown: <reason>` | pointer unreadable, env var absent and `/proc` unreadable, or `<ROOT>` not a release layout | **`degraded`** |
| `not_applicable` | this node is not on the release scheme (pre-migration, or a dev checkout where `<ROOT>/current` does not exist) | unaffected |

`unknown` degrades rather than passing, for the reason `process_divergence.py`'s docstring already
gives: a false `healthy` is the exact defect being fixed, so "cannot tell" must never collapse into
the good answer. `not_applicable` is a *different* answer from `unknown` and must be distinguishable
by a positive test for the layout, not by an exception — otherwise every dev machine reports
degraded and the signal is ignored within a week.

**What an operator sees.** `/health` reports `degraded` with `release: "stale: running X, current Y"`
from the moment a flip completes without a matching restart, on every poll, on every affected node —
instead of a mtime comparison someone does by hand after a failed investigation. That converts the
whole "deployed but never restarted" class (#12886, #13802, #15323) from a post-mortem into a
monitored condition, and it is what makes #14866, #14010 and #13570 *automatically* measurable rather
than re-measurable by hand.

**Cost:** one `readlink` and one env read per poll, both on local `/proc` and a symlink. No I/O beyond
that. Cached for a poll interval so a hot `/health` cannot storm `/proc`.

---

## 10. Migration from the live flat layout

The node today has real directories at `<ROOT>/<component>` with host state and venvs inside them.
The first release-scheme deploy converts it, once, per node, with services stopped (authorised).

```
M0  preflight   refuse if <ROOT>/current exists and is NOT a symlink (partial prior migration);
                refuse without -e release_migration_confirm=true; require a fresh pg_dump and a
                host backup; emit the full manifest of what M2 will move, before moving anything;
                run the §8.6 space check sized against the CURRENT flat tree.
M1  stop        every managed unit on the node.
M2  move state  per component: mkdir <ROOT>/shared/<c>/ and `mv` exactly the HOST_STATE_EXCLUDES
                entries into it. Same filesystem => rename(2): instantaneous. Idempotent.
M3  seed venv   `mv` the existing flat venv into releases/<id>.incomplete/<c>/venv and rehome its
                bin/ shebangs (§1.9). A move, not a copy: the multi-GB tree changes name only, and
                the first release therefore starts with a venv that is already proven to work on
                this host. Its requirements_sha256 is recorded so the NEXT deploy can seed from it.
M4  build       normal build of the rest of releases/<id>.incomplete; node_modules moved the same
                way as M3; bundles rebuilt in place.
M5  migrate     alembic upgrade head from the staged release (usually a no-op at migration time).
M6  verify      V1-V7. A failure here aborts the migration with the flat tree still intact.
M7  rename      releases/<id>.incomplete -> releases/<id>
M8  flip        §2.1. `previous` is unset on a first migration; the flat dirs are the fallback.
M9  convert     rewrite each consumer per §1.7's table — nginx root, logrotate, unit templates,
                _COMPONENT_PIP_PATHS — then DELETE the flat directories. No compat symlinks are
                created. Each deletion is preceded by an assertion that the flat dir now contains
                nothing that is not already inside the release or shared/.
M10 units       render the new unit templates (launcher ExecStart, resolved PYTHONPATH,
                AUTOBOT_BASE_DIR), daemon-reload, start.
M11 gate        §8.8 in full, plus the §9.4 probe reporting healthy on every unit.
```

**No flying start.** Services are down from M1 to M10. M3's venv move is why the stop is not optional:
a running interpreter survives a rename of its venv (inode handles), but `ExecStart` strings and
`sys.prefix` do not, so a process left running across M3 would be unrestartable.

**Reversibility.** Before M9 the flat directories are still real trees and the venv is the only thing
that moved; aborting means moving the venv and host state back. **M9 is the point of no return** —
after it the pre-migration layout is not restorable without the backup M0 required. That is why M0
gates on an explicit flag and a backup, and why M9 runs after M8 has proved the release works and M11
has not yet run only because it needs the new units.

**Inventory to complete before implementation** — every place naming `<ROOT>/<component>` with a
resolved meaning, each of which M9 must convert: nginx `root`/`alias`
(`roles/frontend/templates/nginx-frontend.conf.j2:56`, `frontend_dist_dir` in
`roles/slm_manager/defaults/main.yml:64`), all unit templates, `_COMPONENT_PIP_PATHS`
(`code_sync.py:1595-1604`), `migration_code_dir` (`update-all-nodes.yml:1046`), logrotate, sudoers,
cron, `AUTOBOT_SNAPSHOT_DIR`, and `AUTOBOT_BASE_DIR` wherever it is set outside the launcher.

---

## 11. Test strategy

| # | Guarantee | Test |
|---|---|---|
| T1 | No path is hardcoded | With `SLM_DEPLOYED_ROOT` a tmpdir, every path from `release_layout` is under it; `"/opt/autobot"` appears in none. |
| T2 | **The vacuity probe (#15092 AC2)** | `test_resolve_destination_is_never_inside_the_live_tree`: take the destination the resolve path actually hands to rsync, `Path(dest).resolve()`, assert it is under `<ROOT>/releases/<id>` resolved and that resolved `<ROOT>/current` is not one of its parents. |
| T3 | **T2 is not vacuous (#15092 AC3)** | Contrast mutation: `<ROOT>/current/autobot-backend/releases/pending` — contains the substring `releases`, reached through the live pointer. A substring assertion **passes** it; T2 **fails** it. Checked in as the mutation. A second mutation targets a would-be compat symlink and must also fail, so the guard stays correct if one is ever reintroduced. |
| T4 | The flip is atomic | (a) A reader loop `open()`ing `<ROOT>/current/marker` across N flips never sees `ENOENT` or a mixed tree. (b) AST scan: publisher uses `os.rename`/`os.replace` on the pointer, never `os.unlink`; YAML scan: no `ln -sf`/`ln -sfn` on the pointer. |
| T5 | Restart never precedes the flip | Repo test parsing `update-all-nodes.yml` (shape of `repo_tests/update_deps_detection_window_test.py`): no `state: restarted`/`started` for a code-importing unit before the flip task, no `unarchive.dest` resolving inside the pointer, and the migrate task before the flip. |
| T6 | **Hardlink write discipline (§4.4)** | Functional: seed a fixture with `cp -al`, run the real rsync argv the code builds, assert the changed file's `st_nlink == 1` and the seed release's copy is byte-identical to before. Argv: `--whole-file` present; `--inplace`/`--append`/`--append-verify` absent. |
| T7 | **#13539's own regression** | A fixture release with `from mod import missing_symbol` fails V4; the contrast fixture with the symbol present passes. Runs in CI without a host. |
| T8 | Containment has no wildcard | A release with an absolute `autobot_shared` link fails V3 rule 1; a host-state link pointing at `shared/../releases/<other>/x` fails V3 rule 2 even though it is "under shared/". |
| T9 | Pinning covers every surface | Rendered unit content and launcher-exported env contain no occurrence of the pointer name; every `PYTHONPATH` entry and `AUTOBOT_BASE_DIR` is under `<ROOT>/releases/`. |
| T10 | **Prune never removes an in-use release** | Fake `/proc` fixture with a pid whose `cwd`/`environ` names release A; prune with `KEEP=1` must retain A. Second case: `/proc` unreadable ⇒ prune abandons and deletes nothing. Third: a release younger than `MIN_AGE_H` is retained. |
| T11 | Divergence | Process on release A while `current` is B ⇒ `stale`; unresolvable ⇒ `unknown`, never `healthy`; multi-unit components aggregate conservatively (preserves #15323's two review fixes). |
| T12 | Rollback is the same path | `publish --to <previous>` and a forward publish execute the identical flip function; asserted structurally. |
| T13 | **Seeded venv is never written** | Installer refuses when `.seeded-from` exists; a `chown -R`/`chmod -R` over a seeded tree is absent from the playbook (YAML scan) — the metadata half of §4.4 that a content test cannot see. |
| T14 | **Shebang rehoming** | A seeded venv whose `bin/` was not rehomed fails V6; after rehoming it passes and `venv/bin/python -c "import sys; print(sys.prefix)"` reports the new release. |
| T15 | **The editable install points in-release** | V7 against a fixture whose `.pth` names another release must fail. This is §1.8's regression test. |
| T16 | **Rollback refuses a lie** | A `contract` revision applied since the target release ⇒ `publish --to` refuses and names the revision; an expand-only history ⇒ it proceeds. Plus the CI classifier test: a revision declaring `expand` while calling `op.drop_column` fails. |
| T17 | **The health probe** | Running-id != current ⇒ `degraded`; pointer unreadable ⇒ `degraded` with `unknown`; no `<ROOT>/current` at all ⇒ `not_applicable` and **not** degraded; no filesystem path appears in any returned string. |
| T18 | **Post-flip gate reverts once** | Gate failure ⇒ exactly one revert, `current` back to `prior`; a second failure ⇒ stop, no third flip. |
| T19 | Import hermeticity (V5's prerequisite) | The new CI guard: every module under `api/` and `autobot_shared/` imports in the sandbox with no network, no subprocess, no writes outside the tree. Population derived, with a floor that fails if the sweep stops matching. |

T7 and T19 deserve emphasis: T7 is the first test in this repo that would have failed on #13539's
actual defect, and T19 is the one that makes V5 possible at all.

---

## 12. Staging — what cannot be proven in CI

CI proves the syscall sequence, path derivation, the verifier, the classifier and the guards. It
cannot prove the layout works on a node. Before this is trusted, on a host, with output pasted
(redacted) onto the issue:

1. Migration (§10) end to end; then a normal deploy; then the same release deployed twice.
2. A rollback, and a roll-forward after it. Confirm the venv and bundles moved with the code.
3. A deploy with changed `requirements.txt` (fresh venv) and one without (hardlink seed). Measure
   both: wall clock, disk delta, and `st_nlink` on a sampled `site-packages` file.
4. `SIGKILL` the publisher at four points — mid-build, mid-`pip`, between the two renames (F3), after
   the flip before restart (F4) — and confirm each recovers as §7 says.
5. Fill the filesystem below the floor; confirm the build refuses **before** touching `current` and
   the old code keeps serving.
6. `readlink /proc/<MainPID>/cwd` for every managed unit resolves to the release `current` names.
   This is the acceptance evidence and it replaces every mtime argument.
7. Deliberately break a release (a module importing a symbol removed from its provider): V4/V5 must
   refuse it before the flip. Separately, break one *after* verification and confirm the gate performs
   exactly one auto-revert and then stops.
8. Stop a unit by hand after a flip and confirm `/health` reports `degraded` with the release reason
   within one poll interval (§9.4) — the probe's whole purpose, and the one thing no test can prove.
9. Confirm an SLM self-update survives its own flip and self-restart, including its new-process-side
   gate (§3.3).
10. A drift-resolve on a live node builds and flips a release; `_resolve_deletion_guard` still refuses
    what it refused before, and refusing leaves `current` untouched.
11. nginx: a client holding an old `index.html` fetches a hashed asset across a flip and gets it from
    `previous` (§1.10), not a 404.
12. Attempt a rollback across a `contract` revision and confirm it is refused (§7A).

---

## 13. Risks, and what I would not do

Revision 2 closed five conceded holes. It did not produce a risk-free design; it moved the risk. What
follows is the honest post-revision set, and three of these are *new*, introduced by the changes the
owner asked for.

### 13.1 (NEW) Dependency resolution silently freezes

`requirements_sha256` hashes the requirements **file**, not the resolved package set, and this repo's
requirements are full of `>=` floors (`fastapi>=0.141.1`, `sentence-transformers>=6.0.0`). So a
release whose file is unchanged hardlink-seeds the previous venv forever, and a dependency that
published a new version is never picked up — the node silently stops receiving upstream updates,
including security ones, while every signal reads healthy. This is a *new* failure mode created by
the seeding rule.

Mitigations, all partial: `VENV_MAX_AGE_D` (default 30) forces a fresh resolve regardless of hash;
`RELEASE.json` records `resolved_packages_sha256` (a `pip freeze` hash) so drift between the declared
and resolved sets is visible and diffable across releases; the forced rebuild is a normal staged
build, so it costs time and not risk. It remains true that between forced rebuilds the node is pinned
to a resolution nobody chose deliberately. Arguably that is an improvement over today, where the
resolution changes silently on every deps deploy instead — but it is a different exposure, not an
eliminated one.

### 13.2 The expand/contract classifier trusts a declaration

§7A's CI test cross-checks `revision_kind` against an AST scan for contracting DDL, which catches
`op.drop_column` mislabelled as `expand`. It cannot catch a destructive `UPDATE` inside an `expand`
revision, or a Python-side data migration that discards information. Rollback across such a revision
would be permitted and would be wrong. Reducing this further needs migration review discipline, not
more code, and I would not pretend otherwise.

### 13.3 (NEW) Disk is now a hard operational requirement

Three releases of source + bundles, plus up to three distinct venvs of several GB each, plus
`node_modules` trees. Hardlink seeding makes the common case nearly free, but a node that changes
dependencies on three consecutive deploys pays in full. Deploys will now *refuse* on a small disk
where they previously succeeded — fail-closed is correct, but it converts "the deploy works" into
"the deploy works if you have the disk", which is a new operational requirement on every node and a
new way for a deploy to fail on a host that was previously fine.

### 13.4 (NEW) Longer builds, and a bigger blast radius per deploy

A deps-changing deploy now builds a full venv and possibly a full `npm ci` before it can publish
anything. That work is off the critical path — nothing is stopped — but the deploy takes materially
longer, and a flaky package index now fails a deploy that previously limped through with a partially
updated venv. The wheel cache reduces this to a local-disk operation once populated, and "limped
through with a partially updated venv" was never a good outcome, but the wall-clock regression is
real and operators will notice it before they notice the correctness win.

### 13.5 Celery tasks and multi-node deploys cross release boundaries

Neither is addressed and neither is new, but the scheme's atomicity claim invites the assumption that
they are:

- A task enqueued by release A can be executed by a worker on release B with a different signature.
  The flip makes the code transition atomic *per process*; it does not drain the queue. Task-argument
  compatibility across one release remains a discipline. Worth its own issue.
- The flip is **per node**. A fleet deploy flips nodes at different instants, so the fleet runs mixed
  releases for the duration. Cross-node API compatibility remains a discipline, not a guarantee, and
  nothing here provides fleet atomicity — that would need a coordinator this design does not propose.

### 13.6 V5's offender list is unbounded until the guard runs once

§8's V5 is mandatory, which is right, and it depends on every module under `api/` and `autobot_shared/`
being importable in a hermetic sandbox. Nobody knows how many are not. The CI guard (T19) is what
produces that number, and it must land and go green *before* the release scheme can deploy. If the
list is large, this is the item that determines the schedule — and I would rather say that now than
discover it during implementation.

### 13.7 Debugging gets harder, and there is no shim to fall back on

Removing the compat symlinks (§1.7) was the right call for correctness and it removes the fallback
that made a half-converted consumer keep working. If M9 misses a consumer, that consumer breaks at
the migration rather than silently reading a stale tree. That is the correct failure — loud, at a
moment when someone is watching — but it makes the M9 inventory load-bearing, and an inventory is
exactly the kind of hand-maintained list #13539's own post-mortem warned about. The mitigation is
that M9's per-consumer assertions fail the migration rather than proceeding.

### 13.8 `/proc`-based liveness is best-effort across namespaces

§6's prune assertion reads `/proc/*/cwd`. A service running in a container with its own mount
namespace still yields host-resolvable paths for `cwd`, but a bind-mounted release may not appear
under the expected prefix, and this repo ships `docker-compose.yml`. On such a node the prune would
not see the process. The fail-closed rule limits this to "a release is deleted while a containerised
process uses it" only when the path prefix genuinely does not match — narrow, but not zero, and it
needs checking on any node that runs a component in a container.

### 13.9 Nothing prevents a human writing into a published release

Releases are ordinary directories owned by the service user. `chattr +i` was considered and rejected:
immutability is an inode attribute, so it would propagate to every hardlink-sharing release, and root
can undo it anyway. The defence is that no automated writer targets a published release, the guard
tests prove it, and §9's identity artifacts make a hand-edit visible as a mismatch — not that it is
impossible.

### 13.10 What I would explicitly not do

- **Not** use systemd `RootDirectory=`/namespaces in v1 (§3.2) — stronger, much harder to operate.
- **Not** couple this to `uv` (§1.9). Correctness change and resolver swap must be separately
  revertible.
- **Not** let drift-resolve build a per-component release. The pointer is per-root; a per-component
  pointer set means N pointers, N flips and a window between them — the defect, reintroduced with
  extra machinery.
- **Not** keep the snapshot/rollback machinery alongside this (§4.3).
- **Not** use `ln -sfn` anywhere near the pointer (§2.2).
- **Not** convert the explicit restarts back into ansible handlers (§4.2) — #15323 measured that
  costing 3,887 files' worth of silent staleness.
- **Not** reintroduce a skip mechanism for V5 under schedule pressure (§8). If the offender list is
  long, the answer is to fix the offenders or to delay the scheme — not to ship a verifier with an
  opt-out, which is how #13539's earlier fix came to look correct while changing nothing.

---

## 14. Scope estimate

Revision 2 is materially larger than revision 1: roughly **+900 lines of implementation and +350 of
tests** on top of it, concentrated in the venv, bundle, migration-classifier and probe modules.

### New files (~1,270 lines)

| File | ~Lines | Contents |
|---|---|---|
| `autobot-slm-backend/services/release_layout.py` | 160 | env-backed paths, id generation, `RELEASE.json` I/O, `release_of_pid` |
| `autobot-slm-backend/services/release_publisher.py` | 280 | build, seed, link, rename, flip, gate, auto-revert, prune, lock |
| `autobot-slm-backend/services/release_venv.py` | 220 | hashing, hardlink seeding, `.seeded-from`, wheel cache, fresh build, `bin/` rehoming |
| `autobot-slm-backend/services/release_bundle.py` | 150 | `node_modules` seeding, `npm ci` gating, bundle build |
| `autobot-slm-backend/services/release_verifier.py` | 260 | V1-V7 including the hermetic sandbox runner |
| `autobot-slm-backend/services/release_migrations.py` | 130 | expand/contract classification, rollback refusal |
| `autobot-slm-backend/tools/release_flip.py` | 90 | CLI; stdlib only, runnable by system python |
| `autobot_shared/deploy/release_exec.py` | 70 | the pinning launcher |
| `autobot_shared/deploy/release_probe.py` | 110 | §9.4, shaped after `frontend_bundle_health.py` |

Every function stays under 30 lines; `release_publisher` splits further if it passes ~300.

### Modified files (~+480 / -280)

| File | Change |
|---|---|
| `services/drift_checker.py` | split `get_default_deployed_dir` into `get_live_dir` (pointer-resolving, readers) and `get_release_component_dir` (writers); ~+25 |
| `api/code_sync.py` | six writers re-pointed at the publisher; **must be net-negative** (B1) — retiring the snapshot trio funds it |
| `services/process_divergence.py` | release-id comparison path; ~+60 |
| `api/health.py` (both backends) | the release probe field; ~+20 each |
| `ansible/playbooks/update-all-nodes.yml` | release fact, `dest:` changes, venv/bundle/link/migrate/verify/rename/stop/flip/start/gate tasks, deletion of the per-component frontend flip block and the recursive `chown`s; ~+180 / -90 |
| `ansible/roles/*/templates/*.service.j2` x8 | launcher ExecStart, resolved PYTHONPATH, `AUTOBOT_BASE_DIR` |
| `roles/frontend/templates/nginx-frontend.conf.j2` | root via `current`, `previous` asset fallback; ~+12 |
| `_shared/tasks/migrate_backend_db.yml` | `migration_code_dir` from the staged release |
| new `ansible/roles/release/` | §10 migration; ~180 |
| `tests/migrations/test_ansible_migration_contract.py` | expand/contract classifier assertions; ~+80 |
| baselines, `docs/runbooks/CODE_UPDATE.md`, `ARCHITECTURE_EXCEPTIONS.md` | mechanical + runbook |

### Tests (~1,000 lines, ~12 files)

T1-T19. T2/T3 (the #15092 vacuity probe and its mutation), T6/T13 (hardlink discipline), T7
(#13539's regression), T15 (the editable-install trap) and T19 (import hermeticity) are load-bearing.

### Incremental vs atomic

**Independently landable, before anything flips — in dependency order:**

1. **T19's import-hermeticity CI guard.** Blocks V5, produces the offender list, and is the schedule
   risk (§13.6). Must be first.
2. **V4 (cross-module symbol check) + T7 as a CI check over the repo.** Catches the #13539 class at PR
   time; the single highest-value item if everything else slips.
3. **The expand/contract classifier + its CI assertions** (§7A). Correct on its own; a prerequisite
   for a truthful rollback.
4. `release_layout.py` + T1 — pure, inert.
5. **The §9.4 probe reporting `not_applicable`** on a flat host, plus the `/proc/cwd` and
   `AUTOBOT_RELEASE_ID` support in `process_divergence.py` — inert until releases exist, and it makes
   the migration observable while it happens.
6. **Making the five absolute `autobot_shared` links relative** (§1.4) — correct today, prerequisite
   tomorrow.
7. **Unifying `backend_install_dir`** (B3) — a correctness fix in its own right.

**Must land atomically, in one change, on one deploy:** the layout migration, the venv and bundle
moves, the unit templates, the nginx root, the playbook flip, all six code_sync writers, and the
`get_default_deployed_dir` split. Splitting these leaves a host where a unit reads a path no writer
maintains, or a writer writes where no unit reads. That is #15092's rule generalised: a guarantee
true of one half of the system and silently false of the other is worse than not having it.

---

## 15. Blockers in existing code

| # | Blocker | Where | Why it blocks |
|---|---|---|---|
| B1 | **The size ratchet is exact.** `api/code_sync.py` pinned at exactly 6112 lines in two baselines | `repo_tests/python_file_size_ratchet_baseline.py:456`, `scripts/python_file_size_known_large.py:451` | The change cannot add a line to the file it must modify. Feasible only by removing more than is added — retiring the snapshot trio (`:2530-2594`) and collapsing `_drift_resolve_rsync_or_fail` into a publisher call. Plan it; do not discover it. |
| B2 | **`get_default_deployed_dir` is one function with ~15 consumers** that would all silently follow the pointer | `services/drift_checker.py:817` | Readers want the live tree; writers must be unable to get it. Split before any writer changes, or T2 has nothing to assert against. |
| B3 | **`backend_install_dir` means two different things** — `/opt/autobot` in `setup-user-backend.yml:26`, `/opt/autobot/autobot-backend` in `roles/backend/defaults/main.yml:10` — and the unit derives autobot_shared's path as `backend_install_dir \| dirname` | `roles/backend/templates/autobot-backend.service.j2` | Under a release root the ambiguity produces a `PYTHONPATH` entry **outside** the release, silently defeating pinning. One variable, one meaning, first. |
| B4 | **The `autobot_shared` symlink is absolute in five places** | `update-all-nodes.yml:405, 417, 791, 1554, 1595` | Inside a release it escapes to the live tree (§1.4). Prerequisite; independently landable. |
| B5 | **The venv lives inside the deployed component dir** and `_COMPONENT_PIP_PATHS` hardcodes two absolute literals per component | `roles/backend/tasks/main.yml:812-818`; `api/code_sync.py:1595-1604` | §1.9 moves the venv into the release; those literals must become derived. They violate the no-hardcode rule today. |
| B6 | **Hardcoded deploy destinations outside the resolve chokepoint** | `code_sync.py:1822` (`/opt/autobot/constraints/`), `:1858` (`_get_deploy_base()`) | Writers not covered by a guard on `_rsync_local_cmd`. §1.5 resolves them, in the same change. |
| B7 | **Self-restart never returns** | `code_sync.py:2477`, `:1732` | The flip must be complete, `fsync`ed and self-checked before the self-restart is issued (§3.3); ordering is not stylistic. |
| B8 | **PR #15556 is open** and touches `api/code_sync.py`, `api/health.py`, the ratchet baselines and `ARCHITECTURE_EXCEPTIONS.md` | not yet in `Dev_new_gui` | It lands the staged-build extraction this design subsumes and moves the same baselines B1 constrains. Sequence behind it. |
| B9 | **(NEW) Recursive `chown`/`chmod` over what will be hardlink-seeded content** | `update-all-nodes.yml:772`, `:786`; `roles/*/tasks` ownership fixes | Metadata operations act on the **inode**, so they propagate to every release sharing it (§4.4 rule 3). The publisher must build as the service user and these tasks must be deleted, not reordered. |
| B10 | **(NEW) `-e ../autobot_shared` writes an absolute path into `site-packages`** | `autobot-backend/requirements.txt:1` | §1.8. With a shared venv it defeats pinning for the exact module #13539 named. It is why per-release venvs are mandatory, and V7/T15 exist to keep it honest. |
| B11 | **(NEW) `AUTOBOT_BASE_DIR` is a second, independent path root** | `autobot_shared/ssot_config.py:1330`, consumed by `config.path.resolve()` and `services/frontend_bundle_health.py` | A process pinned by `PYTHONPATH` but not by `AUTOBOT_BASE_DIR` resolves SSOT paths into the live tree. The launcher must set it (§3.2 step 3) and T9 must assert it. |
| B12 | **(NEW) The import-hermeticity offender list is unknown** | every module under `api/` and `autobot_shared/` | V5 is mandatory and cannot run until the offenders are fixed. T19's guard must land and go green first; its first run sizes the work. This is the schedule risk (§13.6). |

---

## 16. Answers to #15092's acceptance criteria

- **AC1** — drift-resolve **can** build and flip a release and should; refusing it during an incident
  is worse than the problem. Mechanism in §4.3, with the hardlink write discipline of §4.4. It shares
  the publisher with the playbook end to end.
- **AC2** — T2: assert on the **resolved** destination, under `releases/<id>` and not under a resolved
  `current`.
- **AC3** — T3: the contrast mutation is `<ROOT>/current/autobot-backend/releases/pending`, which
  contains the substring `releases` and is nested inside the live tree. A substring check passes it;
  T2 fails it.
- **AC4** — this document is the recorded decision. The release scheme closes the defect **category**
  only because all seven writers move together, including `pip`; that is stated in §0 and enforced by
  §14's "must land atomically" list.
