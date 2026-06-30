# Umbrella #9931 — codebase-recovery: closed-unmerged PR archaeology

**Session date:** 2026-06-15
**Outcome:** All 3 members closed. **Net recovery = 0 lost features** — and that is the finding, not a gap.
**Umbrella #9931:** left OPEN (umbrella close is a human action per the lifecycle rule); flagged ready.

---

## TL;DR

The closed-unmerged PR episodes were **safety snapshots taken before cleanups**. In every audited case the underlying work was later carried forward canonically and is present in `Dev_new_gui`. The risk these episodes ever posed was **process** (wrong-base PRs, oversized PRs), never **lost code**. No PR reopens and no fresh feature issues were warranted.

---

## Member outcomes

### #9545 — recreate issue-9035 PR correctly (S) — CLOSED
- Recreated PR **#9704** `feat(admin): telemetry and analytics opt-out (GH#9035)` **MERGED 2026-06-08** (`50b5e13d3`), base `Dev_new_gui`, head `issue-9035-clean`.
- Out-of-process PR #9538 (wrong base `main`, 100-commit scope) correctly stayed closed.
- Target issue **#9035 CLOSED**.
- Feature verified in tree: `TelemetrySettingsPanel.vue`, `TelemetryConsentModal.vue`, Privacy tab in `SettingsView.vue`, `GET/POST /api/settings/telemetry`, `AnalyticsMiddleware` opt-out gate, `docs/user/TELEMETRY_PRIVACY.md`.

### #9656 — recover Jun 1–5 missed features (L) — CLOSED
Audited all **18** enumerated PRs against current `Dev_new_gui`. Method: inspect original commit (`git show --stat <sha>`), then verify equivalent functionality exists and is wired.

| Cluster | PRs | Result |
|---|---|---|
| Voice / RBAC | #9377, #9338 | PRESENT (via #8605) |
| Transcriber / media | #9241, #9194, #9193 | PRESENT (via umbrella #9925) |
| LLM | #9421, #9380, #9166 | PRESENT |
| KB / MCP / Telegram | #9237, #9188, #9183 | PRESENT |
| CI / infra / security | #9181, #9148, #9366, #9355, #9279 | PRESENT |
| Pre-commit | #9210, #9233 | SUPERSEDED by canonical PR #9698 |

**16 PRESENT, 2 SUPERSEDED, 0 lost.** Full file:line evidence posted on the issue.

**Full-window follow-up (correcting the "~59 missed" premise):** enumerated *every* closed-unmerged PR in `closed:2026-06-01..2026-06-05` = **90**. Of those, **37 dependabot** (auto-superseded), and the **53 non-dependabot** are mostly CI-fix meta-PRs + 2–3 duplicate re-pushes per feature → they collapse to **22 distinct underlying issues**. **21 CLOSED/MERGED + landed; 1 OPEN (#9004 OneDrive/SharePoint connector), and that one is an active tracked member of umbrella #9928 — not orphaned.** Verified 12 not-in-original-18 features landed (incl. #8957 TrustLevel, #9525/#9526 nullable fields, #9567 SSRF fix, #9606 telegram-token encryption, #9686 SSO migration; #9220 ChartCell dedup confirmed *resolved* — only one copy remains). The "~59" figure was an artifact of counting raw PRs (dependabot + meta-fixes + re-pushes). **Distinct genuinely-lost features in W23: 0.**

### #9655 — May-17 preserve() batch (L) — CLOSED
Batch = PRs **#7935–#8073** (**138 PRs**, closed 2026-05-17).

| Metric | Count |
|---|---|
| Total preserve() PRs | 138 |
| Merged on 2026-05-17 (snapshot landed) | 20 |
| Unmerged | 118 |
| Unmerged with live remote branch | **0 / 118** |
| Distinct GH issues referenced (unmerged set) | 73 |
| Of those, currently OPEN | **0 / 73** |

12-item sample verified the work **landed** (not just the issue closed): **11 PRESENT, 1 PARTIAL** (architecturally landed — extension→middleware rename, legacy term lingers in comments). Classification: category (b) superseded WIP snapshots / (c) duplicates throughout; category (a) genuinely-lost = **0**.

**Residual:** ~30 unmerged snapshots reference Paperclip work items (`MVA-xxx`), not GitHub issues — not checkable via `gh`. Their branches are likewise deleted; spot-checks (canvas MVA-484/485, a11y MVA-322/333/345, toast MVA-345/347) indicate the same re-done-canonically pattern. No GitHub-side recovery action applies.

---

## Why no recovery was performed
Reopening 118 two-week-stale, branch-deleted, hundreds-of-commits-behind snapshots would only re-introduce merge conflicts for work already shipped correctly. The issues' own remediation guidance for categories (b)/(c) is "document as intentionally closed, no action needed" — which is what was done.

## Prevention
No new guardrail issue filed. The recurrence concern is structurally handled: a snapshotted-and-closed WIP branch is followed by the canonical work landing through normal issue flow. The only real failure mode observed was process discipline on individual PRs (#9545), already corrected.

## Method notes (for future archaeology sessions)
- Branch survival in bulk: `git ls-remote --heads origin` once, grep per head — far faster than per-PR lookups.
- "Issue CLOSED" ≠ "work landed" — always sample-verify the canonical end-state exists in the tree (grep symbol/file:line).
- Deleted-branch SHAs from prior recovery comments are still resolvable in local git (`git show --stat <sha>`) to recover the original file list for comparison.

## Session hygiene
Investigation + GitHub-issue operations only — **zero code changes**, so no worktree/branch/PR. Pre-existing untracked report files in the repo root (`U7_DOCS_POSITIONING_REPORT.md`, `UMBRELLA_9925_TRANSCRIBER_REPORT.md`) belong to other sessions and were left untouched.
