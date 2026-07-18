# tools/git-hooks

Git hooks that enforce the `batch-implement` skill's Phase 0c (verification
mandate + pre-push duplicate check) automatically. Without these, the skill
rules are advisory text — easy to skip when you're in a hurry. With them,
git won't let you push something that fails the rules.

This directory exists because of #5142 (verification mandate) and #5143
(pre-push duplicate check), both filed after I personally caused two
incidents this session that the rules were supposed to prevent:

- **PR #5141 broke 3 tests.** I ran `vue-tsc` and called it verified.
  `vitest run` would have caught the regression in 2 seconds.
- **PR #5141 was a duplicate of merged PR #5128.** I didn't re-fetch
  before pushing. Wasted ~30 minutes.

## Setup (one-time per developer)

```bash
bash scripts/install-git-hooks.sh
```

Copies each hook (`pre-commit`, `pre-push`) into the repo's hooks dir as a
**real file** — never a worktree symlink (those dangle when the worktree is
deleted, silently disabling enforcement — #11598). The installer is idempotent
(a second run is a no-op), normalises a bad absolute `core.hooksPath` back to
git's default, and detects/replaces any dangling symlink left by the old
`install_hooks.sh` (now a shim that delegates here).

## What the pre-commit hook does

Blocks direct commits to the protected branches `main` / `master` (Issue
#4113) and points you at the correct `issue-*` → `Dev_new_gui` PR workflow.
Commits on any other branch pass straight through.

## What the pre-push hook does

For each ref you're pushing, the hook walks the changed files and runs:

| Check | When | What |
|---|---|---|
| **Phase 6 issue check** | branch matches `issue-NNNN` | warn if issue is CLOSED on GitHub OR if `origin/Dev_new_gui` already has a commit citing `#NNNN` |
| **Phase 0c type check** | any `.ts` or `.vue` file changed | `vue-tsc --noEmit -p tsconfig.app.json` (90s timeout); only **errors in changed files** block — pre-existing project errors warn |
| **Phase 0c test run** | any test file or composable changed | `vitest run <relevant test files>` (120s timeout); failures block |
| **Phase 0c backend tests** | any `.py` file changed | `pytest <co-located *_test.py>` (120s timeout); failures block |

Time-boxed: a slow check warns and skips rather than blocking forever. Real
failures block the push with a clear "fix this" message.

## Bypass

```bash
git push --no-verify
```

Use only when you actually have to (e.g. delivering a hotfix and CI will
verify). Don't make a habit of it — every bypass is the path that produces
PR #5141-class incidents.

## Tested manually

Verified on the issue-5142-hooks branch (this PR):
- Phase 6: simulated a push to `issue-5128` (closed), correctly warned about
  the closed issue and the existing `Dev_new_gui` commit citing it
- Phase 0c: simulated a push with a test failure injected — correctly
  blocked with a clear "vitest failures (#5142)" message
- Idempotency: ran `install_hooks.sh` twice; second run was a no-op

## Updating

The hooks are symlinked, so edits to `tools/git-hooks/pre-push` in the repo
are picked up on the next push — no resync needed.
