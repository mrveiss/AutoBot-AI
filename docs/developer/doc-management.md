---
tags: [type/reference, status/current]
date: 2026-06-04
---

# Documentation Management Guide

Rules for where docs live, what they're named, how they're tagged, and when they die.

---

## Zones — Where Each Doc Type Lives

| Zone | Path | Purpose | Naming |
|---|---|---|---|
| Reference | `docs/developer/` | Living how-tos, patterns, rules — maintained when the code changes | `kebab-case.md` |
| Architecture | `docs/architecture/` | Design decisions, system structure, ADRs | `kebab-case.md` |
| API | `docs/api/` | Endpoint contracts, response shapes, data models | `kebab-case.md` |
| Connectors | `docs/connectors/` | Per-connector configuration and feature reference | `kebab-case.md` |
| Operations | `docs/operations/` | Runbooks, deployment procedures, incident response | `kebab-case.md` |
| Security | `docs/security/` | Security policies, CVE tracking, auth docs | `kebab-case.md` |
| User | `docs/user/` | End-user guides | `kebab-case.md` |

**Rule:** If a doc doesn't fit a zone, the zone is missing — add it rather than dumping the doc at the repo root or next to the code it describes.

---

## What Is NOT a Doc

These are not documentation — don't commit them as `.md` files:

| Type | Where it belongs |
|---|---|
| Sprint completion report ("Phase 3 — COMPLETE") | Git commit message or PR description |
| One-time verification ("issue #4293 already resolved") | GitHub issue comment |
| Test run output ("5 passed in 1.55s") | CI logs |
| Files-created list from an implementation sprint | Git diff / PR description |

If you find files matching these patterns in the repo, they are candidates for deletion.

---

## Frontmatter — Required on Every Doc

```yaml
---
tags: [type/reference, status/current, component/backend]
date: 2026-06-04
issue: 1234          # linked GitHub issue, if any
---
```

All three frontmatter fields are required. The `issue` field is optional.

---

## Tags

### `type/` — What kind of doc

| Tag | Use for |
|---|---|
| `type/reference` | Living how-to — developer patterns, API usage, configuration |
| `type/architecture` | Design decisions, system structure, ADRs |
| `type/api` | Endpoint contracts, request/response shapes |
| `type/plan` | PRDs, milestones, task breakdowns |
| `type/runbook` | Operational procedure — step-by-step for humans to execute |

### `status/` — Lifecycle state

| Tag | Meaning | Who sets it |
|---|---|---|
| `status/current` | Authoritative, maintained when the thing changes | Author |
| `status/draft` | Being written, not yet authoritative | Author |
| `status/stale` | Content is valuable but known to be out of date — needs owner to rewrite | Anyone who notices |

There is no `status/archived`. If content is still relevant, rewrite it as `status/current`. If it is not relevant, delete it.

### `component/` — Which part of the system

`component/backend`, `component/frontend`, `component/slm`, `component/infrastructure`, `component/shared`, `component/npu`

A doc may have multiple component tags if it spans subsystems.

---

## Naming Rules

- **Always `kebab-case.md`** — no SCREAMING_SNAKE, no `_v2`, no `_fix` suffixes.
- **Descriptive stem** — `llm-fallback.md`, not `IMPLEMENTATION.md`.
- **No dates in filenames** — dates go in frontmatter. Exception: changelog entries.

---

## Zone Indexes

Every zone has a `README.md` that lists every doc in that zone. Format:

```markdown
| Doc | What it covers |
|---|---|
| [[doc-name]] | One-line description |
```

**Rule:** Adding a doc = adding a row to the zone's `README.md`. A doc not listed in its zone's README is effectively invisible.

The zone README also has a **Missing Coverage** section listing topics that *should* be documented but aren't yet. This is how documentation gaps are made visible.

---

## Lifecycle — How Docs Are Born and Die

### Creating a doc
1. Determine the zone.
2. Write with frontmatter (`type/`, `status/draft`, `component/`).
3. Add to zone `README.md`.
4. Mark `status/current` when accurate.

### Updating a doc
Update the doc when the thing it describes changes. If the code ships without the doc being updated, mark it `status/stale` immediately.

### A doc becomes stale
Mark `status/stale` in frontmatter. The Obsidian tag pane (`status/stale`) is the live queue of docs needing attention. Assign an owner to rewrite it.

### Rewriting a stale doc
Rewrite in-place (same file, same path). Update `date:` in frontmatter. Change `status/stale` back to `status/current`. Do not create a new file alongside the old one.

### Deleting a doc
Delete when the content has no ongoing reference value — specifically:
- Sprint completion reports ("Phase N — COMPLETE")
- One-time verification artifacts
- Status tracking docs for work that is now 100% done
- Duplicate content covered by a better doc elsewhere

Never delete a doc that contains design rationale, API contracts, or how-to instructions that aren't captured elsewhere.

---

## Identifying Gaps

Run the orphan scanner to find docs not linked from any zone README:

```bash
python3 tools/doc-orphan-scan.py
```

Gaps show up in two ways:
1. **Orphaned docs** — exist but not in any index → add to zone README or delete
2. **Missing Coverage section** — topics listed in zone READMEs as gaps → write the doc

---

## Anti-Patterns to Avoid

| Pattern | Why it's wrong |
|---|---|
| Doc at repo root (`IMPLEMENTATION_SUMMARY.md`) | No zone = not discoverable |
| Doc next to the code it describes (`autobot-frontend/THEMING.md`) | Code dirs aren't doc dirs |
| `_v2` or `_fix` suffix on a doc name | Version in filename = proliferation; update in-place |
| `status/archived` dumping ground | Archive = slow delete; rewrite if relevant, delete if not |
| No entry in zone README | Doc is invisible; might as well not exist |
