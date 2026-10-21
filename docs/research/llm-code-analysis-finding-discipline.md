# Research: LLM-driven code analysis — finding discipline and coverage

Status: Phase 1 + Phase 2 complete; issues filed under umbrella #18330. Scoped to the **code-analysis suite** angle — patterns
that help find and close defects in our own code.
Date: 2026-10-11

## Source Analysis: an open-source, vendor-backed LLM application-security review agent

### What It Is

A Python CLI (Apache-2.0, about 14 months old, very actively maintained) that runs a graph of LLM
agents over a target. The target can be a source tree, a diff, or a running service, and the
agents produce validated findings in JSON, SARIF and PDF. This analysis covers only the
white-box, code-review half: how it decides what to look at, when a candidate counts as closed,
and how findings are structured, deduplicated and exported. The runtime tooling is out of scope.

### Architecture & Key Patterns

- **Agent graph** — a root coordinator spawns sub-agents with their own scope, then waits for
  them; children report back through a structured finish call that carries `open_items`
  (`tools/agents_graph/tools.py`).
- **Methodology as loadable markdown skills** — `analysis/` (closure, fix verification, severity
  calibration, source-aware discovery), `scan_modes/` (quick/standard/deep/diff), and
  per-framework and per-defect-class skills. The model loads them on demand through a
  `load_skill` tool.
- **Run state persisted per run** — coverage, threat model and reports are each mirrored to a
  JSON file under the run's state dir so a run can resume.
- Built on an agents SDK plus a multi-provider LLM shim; model metadata drives token budgets.

### Notable Implementation Details (code-analysis relevant)

1. **Three closure states, no silent drop** (`skills/analysis/counterevidence.md`). Every
   candidate ends as one of three states:
   - `confirmed`: a full source → control → sink → impact trace.
   - `ruled_out`: the reviewer can name the specific control at `file:line` and confirm it runs
     on every reachable path.
   - `open_proof_gap`: the candidate is recorded and carried upward, never dropped.

   The skill also lists what does **not** rule a candidate out: generic trust in a library,
   escaping meant for a different context, or a guard that sits on a sibling route.
2. **Coverage ledger: the negative space** (`tools/coverage/tools.py`). Each agent records
   `(surface, risk_area, outcome)` with outcomes `reported | no_issue_found | ruled_out |
   not_applicable | needs_follow_up`. The last three require evidence text, and duplicates are
   detected on `(surface, risk_area)`. The coverage report keeps agent-reported entries apart
   from machine-observed facts (which agents ran, which skills they loaded, how the run ended).
   This is the same split as "did not look" versus "found nothing".
3. **Validated finding schema** (`tools/reporting/tool.py`). Required fields include code
   locations with start and end lines, a PoC, `counterevidence`, and a `confidence_rationale`
   whenever confidence is not `high`. CVSS is **computed** from an 8-metric breakdown, never
   typed in by the model. Reports that fail validation are rejected back to the agent.
4. **Two-stage dedupe** (`report/dedupe.py`). The first stage is deterministic: dependency
   findings are matched on (package, version, CVE, manifest path), and different manifests are
   kept apart. The second stage asks an LLM for a JSON verdict with a confidence score. A
   separate dedupe model gets its own credentials, so it never receives the main endpoint's
   headers.
5. **Diff-scoped review mode** (`skills/scan_modes/diff.md`). These count as in scope:
   - a pre-existing unsafe sink that the diff **newly makes reachable**;
   - a shared helper the diff weakens, with every affected caller listed;
   - a control the diff removes or narrows, even when no code was added;
   - a default or validator that is loosened.

   Unrelated pre-existing bugs are noted and not filed against the PR. The skill also says to
   read the code rather than trust the PR description.
6. **Source-aware discovery** (`skills/analysis/source_aware_discovery.md`). One root cause is
   *not* one candidate: each vulnerable call site stays separately addressable, and a safe
   sibling proves nothing about its neighbours. Each location is tagged entrypoint, control,
   sink or impact. The skill also gives per-family sweep lists (parsers, deserialisation,
   archive extraction, object construction).
7. **Fix verification gates** (`skills/analysis/fix_verification.md`). The gates run in order:
   1. the fix applies;
   2. it closes the hole (the original reproduction is re-run);
   3. a fresh bypass review finds nothing;
   4. legitimate behaviour still works;
   5. the repo's tests pass.

   A fix may never trade an earlier gate for a later one, and a fix that fails a gate is
   withheld rather than shipped.
8. **Severity calibration** (`skills/analysis/severity_calibration.md`). Unconfirmed impact
   lowers *confidence*, not the severity floor ("downgrade, don't delete"). High and critical
   ratings go through an acceptance checklist.
9. **SARIF with stable fingerprints** (`report/sarif.py`). Each result gets
   `partialFingerprints.primaryLocationLineHash` plus a class hash, so a finding the user has
   dismissed stays dismissed across runs in code-scanning UIs.
10. **Run hygiene**:
    - per-turn tool-call cap (`config/tool_call_limits.py`): a runaway response that queues
      hundreds of calls is cut to the first N;
    - staged budget-wind-down directives, with different wording for the root agent and
      sub-agents (`core/hooks.py`);
    - context compaction that keeps tool-call/tool-result pairs intact (`llm/compaction.py`);
    - large tool output is bounded to its head and tail, with the full text spilled to a store
      (`tools/output_store.py`).

### Strengths

- The closure discipline is explicit and checkable. It is aimed squarely at the false negative
  where "I felt unsure and moved on" is recorded as "safe".
- Coverage is reported as a first-class result, so a clean report can be told apart from a
  shallow one.
- Deterministic checks run before LLM judgement wherever a deterministic answer exists (CVSS,
  dependency dedupe, schema validation).
- The methodology lives in versioned markdown rather than in prompt strings scattered through
  the code.

### Weaknesses / Limitations

- Coverage entries are the agents' own account and are not verified. The tool labels them as
  self-reported but cannot confirm that a surface was actually read.
- LLM dedupe is non-deterministic, so the same pair of findings can be merged in one run and
  kept apart in the next.
- Several core modules are very large (the reporting tool is about 2.6k lines, execution about
  1.2k), well past a 600-line ceiling.
- The published benchmark result is self-reported and black-box. It says nothing about the
  white-box code-review path.
- Telemetry is on by default (anonymised, opt-out).

### Visible vs Hidden Metrics

- **Visible:** a high benchmark solve rate (self-reported, black-box only), PoC-backed findings,
  SARIF export, a broad skill library, and a large community following.
- **Hidden:**
  - LLM cost per run: the published figure is about $3 per challenge solved;
  - non-deterministic dedupe and closure, so runs are hard to reproduce;
  - a Docker sandbox to operate;
  - a methodology corpus (about 70 skill files) that must be kept current;
  - the SDK and LLM-shim coupling;
  - self-reported coverage that can read as stronger assurance than it gives.
- **Weighing:** adopting the whole tool would be a poor fit for us: the cost and operational
  load are high for a repo that already runs CI and guard tooling. The *discipline* artifacts
  are cheap to adopt and have no hidden cost beyond upkeep: the closure states, the coverage
  outcomes with evidence, the finding schema, the diff-scope rules, the fix gates and SARIF
  fingerprinting. Phase 2 should compare those against AutoBot's review and audit tooling, not
  the runtime.

---

## AutoBot Comparison: the reference work → AutoBot (code-analysis suite angle)

Audit method: I grepped and read `.claude/skills/{secreview,bugfix}`, the `review-fleet`
plugin skill (in the `AutoBot-AI-Claude-dev-skills` repo), `.claude/agents/security-auditor.md`,
`docs/developer/{MEASUREMENT_DISCIPLINE,CLAUDE_REVIEW,CLAUDE_RULES,CODE_REVIEW_HARDENING,CODEQL_SUPPRESSION}.md`,
`.github/workflows/{security,codeql,ai-security-review}.yml` and `pipeline-scripts/security_scan_gate.py`.
I then searched open and closed issues for each pattern.

**Not looked at:** I did not read the backend or shared runtime code; it got only a keyword
grep for `sarif|partialFingerprints`, which found nothing. Also unread: `.semgrep/rules.yaml`,
`THREAT_MODEL.md`, the bulk/claims/canonical-audit skills, and live alert state.

### What We Can Adopt

| # | Pattern | Already-exists audit | Missing delta | Visible benefit | Hidden cost | Verdict | Effort | Existing issues |
|---|---|---|---|---|---|---|---|---|
| A1 | Three closure states (confirmed / ruled_out-with-named-control / open_proof_gap) | review-fleet SKILL.md:83 *drops* findings with `confirmed:false` or `confidence<0.7`. secreview SKILL.md:61,109 has only an `(unverified)` marker. MEASUREMENT_DISCIPLINE.md:369 states the principle in prose. The grep for `ruled_out\|proof_gap\|counterevidence` finds nothing in skills or agents. | Add a state enum to the review skills. `ruled_out` must cite the protecting control at `file:line`. A low-confidence item becomes `open_proof_gap` and is filed or listed, never dropped. | Turns the honesty doctrine into the review output format. Fixes review-fleet's silent drop, which contradicts MEASUREMENT_DISCIPLINE. | Longer review output; needs a reviewer prompt change across 3 skills. | **adopt** | trivial | Rule exists in prose: #17259 (honesty umbrella), #15826 (examined-nothing guards). No issue covers the review-fleet drop, so **file one** (in the skills repo). |
| A2 | Coverage ledger: per-surface outcome with evidence | secreview SKILL.md:47-49 lists deferred files. review-fleet SKILL.md:106,127 gives only angle and candidate counts. | A `Coverage` section in the review/audit output: one row per surface or angle, with outcome `reported / no_issue_found / ruled_out / not_applicable / needs_follow_up`. The last three require evidence. | Separates "did not look" from "nothing found" in every review, as the global rules require. | Reviewers may fill it in by rote, and the reference work itself can't verify it. Label it self-reported. | **adopt-with-conditions** (label as self-reported; combine with machine facts such as files actually read) | moderate | #15826 (same class, for guards), #14896 (33 checkers clean on empty scan), #16185 (failed scan read as zero). Nothing covers *review* coverage, so **file one**. |
| A3 | Validated finding schema: computed severity, counterevidence, confidence_rationale | review-fleet SKILL.md:49-61 and CLAUDE_REVIEW.md:81 define a JSON shape (`file,line,severity,evidence`) with no validator. Severity is typed by the model, though CODE_REVIEW_HARDENING.md:87-97 downgrades unexploitable criticals. | Add `counterevidence` and `confidence_rationale` (required when confidence is not high), and either a severity rubric or derived severity. Reject malformed findings. | Consistent findings that can be triaged; less inflated severity. | A schema to maintain, and LLM output must be re-prompted when invalid. | **adopt** for the fields and the rubric; **reject** CVSS computation as overkill for internal review | trivial–moderate | None. **File one**. |
| A4 | Diff-scope rules | secreview SKILL.md:101-105 covers rename fallout and fail-open defaults; CLAUDE_REVIEW.md:107,241 covers grepping removed functions. | Four rules: (a) a pre-existing sink the diff newly reaches counts as this PR's finding; (b) a shared helper weakened in place means enumerating sibling call sites; (c) a removed or narrowed control is a finding even with no new code; (d) read the code, not the PR description. | Catches the most common refactor-induced security regression. Rule 7 of CLAUDE_RULES ("grep the behavior") already points this way. | A few lines of skill text. | **adopt** | trivial | Real instances of (b) and (c) already in the backlog: #15989 (tenant check hand-written at 26 call sites), #17416, #13995. Needs a **skill-text issue**. |
| A5 | Per-instance discipline and per-family sweep lists | gap-audit (plugin) globs only the same directories as the fix; secreview has one-line checklist items for path traversal and deserialisation. | "One root cause, N addressable sites"; "a safe sibling proves nothing"; per-family sweep checklists for parsers, deserialisation, archive extract/restore, path joins and subprocess argv, each run repo-wide. | Directly supports the one-defect, many-sightings owner rule (2026-09-24): list every instance in one issue. | The checklists go stale as the stack changes. | **adopt** | moderate | Existing class-shaped issues it would have found: #16713 (13 path-injection alerts in one file), #16007 (argv through a variable), #15287 (9 unscrubbed git sites), #13805 (17 call sites). **File one**. |
| A6 | Ordered fix-verification gates with withhold | bugfix SKILL.md:8,309 is an iterate-until-tests-pass loop; CLAUDE_RULES.md:286 requires a regression test. Neither has a bypass review or a reproduction re-run. | Add gates in order (applies → re-run the reproduction → independent bypass review → legitimate path preserved → repo tests) to the bugfix and implement skills. A security fix that fails any gate is not shipped. | Catches the incomplete fixes the backlog already records (e.g. "#12425 incomplete" in #12596). | One more agent pass per security fix. | **adopt** for security-labelled fixes only | trivial | None. **File one**. |
| A7 | Stable finding fingerprints and cross-run dismissal for LLM findings; bandit as SARIF | semgrep is uploaded as SARIF (security.yml:421-439) and CodeQL natively. Bandit is JSON-only (security.yml:398) and gated by security_scan_gate.py. LLM review findings exist only as PR comments (ai-security-review.yml:160-170). `partialFingerprints` appears nowhere. | (i) Upload bandit as SARIF so it joins the alert list. (ii) Give LLM review findings a content-keyed fingerprint (rule plus a normalised line-content hash, not the path) so a dismissed finding stays dismissed and duplicates merge across runs. | Kills the re-alert-on-move class; one triage surface. | SARIF plumbing, and the Security tab becomes noisier once bandit's 336 suppressed findings are visible. | **adopt-with-conditions**: do (i) only after #15334 settles the suppressions; for (ii), the fingerprint must be content-keyed, the exact defect in #13131 | moderate | #13131 (path-keyed dismissal, semgrep surface; sighting linked); #16166 (inline suppression is not reflected as dismissed); #13697, #15486 (exclusions are no-ops); #15334 (bandit suppressions); #12262 (alert reconciliation umbrella). Filed: (i) #18334, blocked by #15334; (ii) #18335, a separate surface because LLM findings have no fingerprint at all. |

### What We Already Do Better

- **Absence is an error, not "clean".** `security_scan_gate.py` treats a missing report as a hard
  failure, and its `--allow-id` allowances fail when stale (line 355). The reference work has
  nothing similar for its scanners.
- **Measurement doctrine.** MEASUREMENT_DISCIPLINE.md (family F, control strings, "did not look"
  versus "nothing found") is deeper than the reference work's closure skill. Our gap is enforcing
  it in review output (A1, A2), not the doctrine itself.
- **Ratchets and baselines.** The audited `.secrets.baseline`, the down-only file-size ratchet and
  the api-wiring and dead-surface baselines. The reference work has no regression ratchets.
- **Deterministic before LLM.** This is already house style (guards, ratchets). Only the LLM
  review path lacks it (A7-ii).
- **Module size.** Our 600-line ceiling versus their 1.2–2.6k-line core modules.

### Gaps & Opportunities (by impact)

1. **A1 and A2.** Review output must not drop or hide uncertainty. This has the highest impact,
   is trivial, and closes a direct contradiction between review-fleet and MEASUREMENT_DISCIPLINE.
2. **A7-ii via #13131.** Content-keyed fingerprints for dismissals and LLM findings.
3. **A4 and A5.** Diff-scope and per-family sweep rules in secreview and gap-audit. These are the
   class-finding engine for issues like #15989 and #16713.
4. **A6.** Fix gates for security fixes.
5. **A3.** Finding schema fields.

### Specific Code/Files Affected

| File | Change |
|---|---|
| `review-fleet/SKILL.md` (skills repo) | Phase 2: replace "drop" with the closure-state enum; add a Coverage section; extend the finding JSON (A1–A3) |
| `.claude/skills/secreview/SKILL.md` | Closure states, coverage rows, the four diff-scope rules, per-family sweep checklists (A1, A2, A4, A5) |
| `gap-audit/SKILL.md` (skills repo) | Repo-wide family sweep in place of the same-directory glob; one issue listing every instance (A5) |
| `.claude/skills/bugfix/SKILL.md`, `implement` plugin skill | Ordered security-fix gates with withhold (A6) |
| `docs/developer/CLAUDE_REVIEW.md` | Point to the closure states and the schema; no duplicate rule text (A1, A3) |
| `.github/workflows/security.yml`, `ai-security-review.yml` | Bandit SARIF upload; fingerprinted LLM findings (A7) |

## Linked issues

Issues this research produced or is the analysis for (#18967). Each one links back to this document.

- #18330 — Umbrella: review finding discipline — closure states, coverage, diff-scope, instance sweeps, fix gates, fingerprints
- #18331 — feat(skills): secreview output contract — closure states, coverage section, counterevidence and confidence fields
- #18332 — feat(skills): secreview diff-scope triggers (newly-reachable sink, helper weakened in place, removed control) and repo-wide family sweeps
- #18333 — feat(skills): bugfix — ordered security-fix gates (reproduction re-run, independent bypass review, withhold on failure)
- #18334 — ci(security): upload bandit results as SARIF so they enter code scanning (after #15334)
- #18335 — ci(security): LLM review findings have no stable fingerprint — re-raised every run, dismissals cannot stick
