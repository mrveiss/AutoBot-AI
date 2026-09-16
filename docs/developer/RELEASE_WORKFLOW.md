---
tags:
  - developer
  - release
  - changelog
  - ci
aliases:
  - Release Workflow
  - Changelog Generation
---

# Release & Changelog Workflow

How AutoBot versions, tags, and changelogs are produced. Issue refs: #1296 (design), #9870 (staleness audit).

## Pipeline at a glance

| Piece | Path | Role |
| --- | --- | --- |
| Trigger workflow | `.github/workflows/release.yml` | Fires on every push to `release` |
| Generator config | `cliff.toml` | git-cliff template, commit parsers, `tag_pattern = "v[0-9].*"`, SemVer bump rules |
| Full history index | `CHANGELOG.md` (repo root) | Auto-generated wholesale by git-cliff — **never hand-edit entries** |
| Human-written fragments | `changelog/unreleased/*.md` | One file per notable PR (copy `TEMPLATE.md`, name `{issue}-{slug}.md`) |
| Fragment compiler | `scripts/compile_changelog.py` | Merges fragments + git-cliff notes into `changelog/{version}.md` at release time |
| Per-version notes | `changelog/{version}.md` + `changelog/_index.md` | Release-notes body for the GitHub Release |

## What happens on a push to `release`

1. **Determine next version** — `orhun/git-cliff-action` runs `git-cliff --bumped-version`: scans conventional commits since the last `v*` tag (`feat` → minor, `fix` → patch, breaking → major).
2. **Check if release needed** — reads the bumped version from the action's `content` output, validates `^v[0-9]+\.[0-9]+\.[0-9]+$`, and skips if that tag already exists (no bump → git-cliff echoes the *current* version).
3. **Generate release notes** — `git-cliff --latest --strip header` → `RELEASE_NOTES.md`.
4. **Compile fragments** — `compile_changelog.py` writes `changelog/{version}.md` (fragments first, git-cliff commit log after) and archives fragments to `changelog/{version}/fragments/`.
5. **Regenerate `CHANGELOG.md`** — git-cliff rewrites the full history index from scratch.
6. **Commit + tag + release** — bot commits the changelog files, tags `vX.Y.Z`, pushes, and creates a (prerelease) GitHub Release with the compiled notes as body.

`release` only receives pushes via `main` promotions (Dependabot security merges now land on `main` directly, like everything else, since `main` is the default branch), so releases are cut at promotion time.

## Why CHANGELOG.md went stale (2026-03-01 → 2026-06-13)

Root cause (#9870): the workflow read `steps.version.outputs.version` from
`git-cliff-action`. For `--bumped-version` args that output is **always empty** —
the action's `run.sh` re-runs git-cliff with `--context`, which then emits the
plain version string instead of JSON context, so the action's internal
`jq -r '.[0].version'` fails (`jq: parse error`) and writes `version=`.
The empty value made the "Check if release needed" step conclude
`release_needed=false` on *every* push, so all generate/commit/tag/release steps
were skipped while the workflow itself reported **success** — a silent failure
for ~3 months (~8,700 PRs). git-cliff itself was computing `v0.4.0` correctly
the whole time.

Secondary findings from the audit:

- None of the existing tags (`v0.1.0`–`v0.3.0`) were created by the workflow — all were manual. The pipeline has never cut a release end-to-end.
- ~750 commits were skipped by git-cliff as non-conventional (`WARN ... skipped due to parse error`) and never appeared in generated output. **Resolved (#10118):** `cliff.toml` now sets `filter_unconventional = false` and adds a catch-all `commit_parser` so non-conventional commits surface under an **"Other / Uncategorized"** section; merge-bubble commits are skipped to keep that section clean. Note this only restores *changelog visibility* — non-conventional commits still cannot drive a semver bump (that needs commit-message enforcement, tracked separately).

Fix: derive the bumped version from the action's `content` output (the output
*file* contains the version string), validate its shape, and guard against
re-tagging an existing version.

## Why no changelog reached `release` (v0.5.1 → v0.9.0)

The second time the changelog stopped arriving, and for two reasons at once. Both
sat in the same step — "Open changelog PR to release" — and both left the tag and
the GitHub Release published, so every run looked like a successful release from
the outside. The last three before the fix all failed here: 32514348218
(2026-08-21), 33378585208 (2026-08-31, v0.8.0's own run) and 34711633744
(2026-09-12).

**The branch name could not be pushed (#16563).** The step built
`release/changelog-${VERSION}`. Git stores refs as paths, so `refs/heads/release`
is a file and `refs/heads/release/changelog-v0.9.0` would be a directory at the
same location — they cannot coexist. From the moment the 2026-09-12 rename created
a branch named `release`, the push was refused with `directory file conflict`. The
name is now flat, `changelog-${VERSION}`, and `repo_tests/changelog_branch_name_16563_test.py`
pins the absence of a slash rather than the particular name, so the whole class is
closed rather than this one instance. That guard also checks the prefix against
`BRANCH_ARCHIVAL_PREFIXES` in `scripts/lib/branch-guards.sh` — rename it in one
place and the branch sweep starts reading released changelog branches as abandoned
work.

**Opening the PR is a repository setting, not a token scope (#15167).**
`gh pr create` from Actions fails with "GitHub Actions is not permitted to create
or approve pull requests" when `can_approve_pull_request_reviews` is false on
`/repos/{owner}/{repo}/actions/permissions/workflow`. No `permissions:` block can
grant it; the setting sits above the token. The step now reads that setting and
reports what is left to do instead of failing the release — and distinguishes
three outcomes, not two: permitted, refused, and *could not ask*. Swallowing the
read error and treating it as "refused" would look correct for exactly as long as
the setting stayed false, and would start lying the day someone enabled it. That
read needs `administration: read`, which the workflow now declares.

The shared shape with #9870 is worth naming: in both cases the release kept
succeeding visibly while the changelog silently did not arrive, because the failing
work happened after the parts anyone watches. A release that reports success is not
evidence that the changelog landed — check `release` for the version's entry.

## Rules of thumb

- **Never hand-edit `CHANGELOG.md` entries** — the next release regenerates the whole file; manual edits are lost.
- **Add a fragment** under `changelog/unreleased/` for user-visible changes; that text becomes the headline of the release notes.
- **Conventional commits are load-bearing** — non-conforming subjects are invisible to the changelog and to version bumping.
- **Verify after a promotion to `release`**: `gh run list --workflow=release.yml --limit 1` then check the job's "Check if release needed" step actually printed `Next version: vX.Y.Z` — a green run alone does not mean a release happened.
