# Research: multi-phase, independently verified security-audit workflow for coding agents

Status: Phase 1 and Phase 2 complete — issues filed (umbrella #19554).
Date: 2026-10-25

## Linked issues

- #19554 Umbrella(security): whole-codebase audit discipline and runtime agent/LLM threat coverage
- #19555 docs(security): THREAT_MODEL has no runtime agent/LLM trust boundaries, and secreview has no AI/agent checklist
- #19556 fix(agents): security-auditor's report contract is placeholders; add phased audit with coverage ledger and fresh verifiers
- #19557 feat(security): shared findings schema and Python validator — three verdicts, no severity on unresolved leads
- #19558 feat(security): additive multi-run audits — carry forward re-verified findings and unresolved leads

## Source Analysis: a vendor-published agent skill for source-first security audits

### What It Is

A coding-agent skill, published by an infrastructure vendor under MIT, that turns an agent into a
defensive, source-first security auditor. It is the single-repository seed of a larger, fleet-wide
vulnerability-discovery harness the vendor runs internally. It is pure instruction material
(~15 Markdown files, ~170 KB) plus two zero-dependency Node.js validators (with tests) and one JSON
Schema. Created mid-2026, last pushed 2026-09; mature in contract design, but there is no runtime —
the agent is the runtime.

### Architecture & Key Patterns

- **Two operating modes.** *Guidance mode* (default: answer a security question, no files written)
  vs *full audit mode* (only on an explicit audit / pen-test / report request). Ambiguous → one
  question before writing anything.
- **Six phases, parent-orchestrated:** (1) reconnaissance → `architecture.md` + a deterministic
  coverage ledger; (2) coverage-led hunting waves of isolated sub-agents; (3) every candidate goes to
  a *fresh* verifier that tries to disprove it; (4) structured `findings.json` validated against the
  schema; (5) fresh agents re-verify the final records; (6) prose reports *derived from* the JSON.
- **Progressive disclosure.** A core `SKILL.md` plus a fixed attack-class file and ~11 domain
  companions (web/auth, client-side, AI/LLM, supply chain, cloud, RPC/messaging, resource exhaustion,
  data isolation/lifecycle, desktop/IPC, memory safety). Reconnaissance selects which companions
  (and which sections of them) each hunter receives.
- **Single writer.** The parent alone writes shared run files; every sub-agent gets its own
  `agents/<id>/{scratch,artifacts}` root.
- **Three-verdict output contract.** `confirmed` (full trace, observed bounded result, severity),
  `needs_validation` (exact unresolved fact + validation plan, **no severity allowed**),
  `rejected` (disproved candidate, kept so it is not re-reported).

### Notable Implementation Details

- **Coverage ledger as a state machine.** Units = surface × trust boundary × subsystem × attack
  class, with states `planned / covered / candidate / blocked / deferred / out_of_scope`. A
  `covered` unit must carry an owner, reviewed paths and per-check evidence; a validator rejects a
  ledger whose claims are not backed. "Absence of a finding" is therefore an evidenced claim, not a
  silence.
- **Coverage critics.** After each hunter wave a fresh critic agent reads the ledger and proposes
  missing units (unmapped entry points, unchecked parallel paths, unjustified exclusions, units
  closed without evidence). Loop until a clean critic pass (profile-bounded).
- **Fingerprints** — one source-derived fingerprint per root cause, stable across verdict states and
  across runs; dedupe by fingerprint then root cause.
- **Additive multi-run.** Prior ledgers and findings are re-read; a prior `confirmed` record is
  carried only if its source is unchanged *and* it passes current verification; a prior run never
  implies "the rest is fine". The vendor reports a single run found roughly half of what repeated
  runs found (self-reported).
- **Budget accounting.** Budget = max agent invocations; critics and verifier reserves are booked
  *before* hunters are assigned, so a budget squeeze thins hunting, never validation. Exhausted
  budget → a named `incomplete` terminal state, disclosed in the report.
- **Exactly two terminal states:** all artifacts written and both validators pass, or
  `run_status: incomplete` with its reason. Never stop mid-phase.
- **Candidate gate.** Every candidate must name lower-trust principal, accepted input, intended
  control, crossed boundary, affected principal/resource and observed result. Defense-in-depth gaps
  are *hardening notes*, not vulnerabilities. Severity is anchored (critical/high/medium/low/info with
  a stated high-vs-medium discriminator: "fully defeats an explicit control" vs "weakens it").
- **Execution safety.** Target code runs only in an OS-enforced sandbox (no network, allowlisted env,
  read-only target, resource limits); without one the lead stays `needs_validation`. Artifact
  promotion out of scratch is an 11-step race-safe, no-follow, descriptor-based copy procedure.
- **Source-visibility rule.** Controls that live outside the repo (proxy, IdP, provider settings) are
  never assumed present *or* absent — the lead becomes `needs_validation` naming the missing fact.
- **AI/LLM companion** covers context/retrieval/memory poisoning, tool and action abuse, MCP and
  sub-agent trust, and output/disclosure classes — directly relevant to an agent platform.

### Strengths

- Evidence contract is enforced by code (schema + validators with tests), not by prose alone.
- Independence is structural: the finder never verifies its own finding; reports derive from verified
  JSON so prose and data cannot disagree.
- Explicit, honest partial-coverage semantics (scoped / quick runs present themselves as partial).
- Strong anti-pattern list (checklist deviations as vulns, self-impact as cross-boundary, guessed
  deployment behaviour, severity on unresolved leads).

### Weaknesses / Limitations

- **Cost.** A `standard` run is dozens of agent invocations (4 recon + one hunter per unit + critics +
  1–2 verifiers per candidate); `deep` is more. No token/cost figures are published.
- **Instruction density.** `SKILL.md` alone is 22 KB; the promotion procedure must be pasted verbatim
  into every hunter and verifier prompt. High context load per sub-agent; drift risk when edited.
- **Sandbox prerequisite** is stated but not provided — most local agent environments cannot meet it,
  so dynamic confirmation silently degrades to `needs_validation`.
- **Output lives outside the repo** by default; no integration with an issue tracker, CI or a
  findings database — fingerprints are only compared run-to-run on disk.
- Validators are Node.js; a Python-first repo inherits a second toolchain for them.
- Recall claim ("~half per run") is self-reported, no benchmark corpus published.

### Visible vs Hidden Metrics

- **Visible:** six-phase rigour, machine-validated findings, adversarial verification, additive
  multi-run coverage, large public adoption signal (star count — popularity, not quality), recall
  claim (self-reported, unverified).
- **Hidden:** per-run agent spend (the dominant cost; an Opus-class fleet run competes directly with
  the weekly model budget); maintenance of a large prompt corpus whose sections must stay identical
  across files; second toolchain (Node) for validators; an OS sandbox an adopter must build; review
  load of `needs_validation` leads that require a human owner to resolve; false sense of coverage if
  the ledger's unit taxonomy is coarse (`quick` profile).
- **Weighing:** the *contracts* (three verdicts, no-severity-on-unresolved, ledger-backed coverage
  claims, fingerprints, reserve-validation-before-hunting) are cheap to adopt and carry most of the
  value. The *full fleet workflow* is expensive and only pays off for high-stakes, periodic audits;
  for per-PR or per-diff review its hidden spend outweighs the recall gain.

## AutoBot Comparison: the reference work → AutoBot

Audited against `origin/main` on 2026-10-25. A prior comparative audit of *diff-review* finding
discipline already filed most of the contract-level overlap under umbrella **#18330**
(`docs/research/llm-code-analysis-finding-discipline.md`); this source re-witnesses those items and
adds a **whole-codebase audit** delta that #18330 does not cover.

### Already-exists audit (what was checked)

| AutoBot asset | Checked | State |
|---|---|---|
| `.claude/skills/secreview/SKILL.md` (133 lines) | full read | diff-scoped fast path; severity table + `BLOCK/APPROVE` verdict; no closure states, no coverage record, no LLM/agent attack class (0 hits for `prompt`/`llm`) |
| `review-fleet` skill (plugin repo, 141 lines) | grep of phases | 10 finders + verifiers; drops `confirmed:false` / `confidence<0.7` silently |
| `.claude/agents/security-auditor.md` (308 lines) | process + report sections | single pass, prose `security-report.md`; **no verification, coverage, fingerprint or schema**; lines 197, 230, 286, 291 are `[Code example removed for token optimization …]` placeholders — the report template the agent is told to follow is missing |
| `.github/workflows/ai-security-review.yml` | prompt + output steps | runs `secreview` read-only, advisory comment + step summary; untrusted-diff mitigation documented |
| `.github/workflows/security.yml`, `pr-blocking-findings.yml` | headers / tool lines | semgrep/CodeQL SARIF; `blocks-merge` label gate (#10024) |
| `docs/developer/THREAT_MODEL.md` | section list + grep | six subsystems (path, session, plugins, secrets, remote desktop, graph-RAG); prompt injection only for dev research tooling (line 142) — **no runtime agent/LLM trust-boundary section** |
| Open issues | `gh issue list --search` ×3 | #18330 children #18331–#18335 + plugin-repo #17/#18, Claude-Dev-Skills #10 |

### What We Can Adopt

| # | Candidate (delta only) | Applies to | Visible benefit | Hidden cost | Verdict | Effort |
|---|---|---|---|---|---|---|
| 1 | **Phased whole-codebase audit mode** for the `security-auditor` agent: recon → coverage ledger (surface × boundary × subsystem × attack class, states `planned/covered/candidate/blocked/deferred/out_of_scope`) → hunter waves → fresh disprove-verifier per candidate → validated JSON → report derived from JSON; exactly two terminal states (complete / `incomplete` + reason) | `.claude/agents/security-auditor.md` | turns a one-shot prose report into evidenced, resumable coverage; "nothing found" becomes distinguishable from "did not look" | dozens of agent calls per run vs the weekly model budget; long prompt corpus to maintain | **adopt-with-conditions** — explicit `quick`/`standard` profile and an invocation budget that reserves verifiers *before* hunters; never a per-PR job | significant |
| 2 | **Restore the missing report template** in `security-auditor.md` (4 placeholders) — subsumed by #1's JSON-derived report | same | the agent's stated output contract becomes real | none | **adopt** (defect, not a feature) | trivial |
| 3 | **Findings schema + Python validator** (three verdicts; `needs_validation` forbids severity and requires the exact blocker + validation plan; `rejected` retained so it is not re-raised) shared by secreview, review-fleet and the auditor | new `scripts/security/` validator + schema; consumers #18331, plugin #17 | #18331 adds fields but nothing machine-checks them; one schema serves three producers | a schema everyone must keep in step | **adopt** — Python, not the reference's Node, to avoid a second toolchain; extends #18331 rather than duplicating it | moderate |
| 4 | **Additive multi-run carry-forward**: a prior confirmed finding carries only if its source is unchanged *and* it re-verifies; prior `needs_validation`/`blocked`/`deferred` become current work; a scoped run never implies "rest is fine" | auditor ledger (#1); fingerprints from #18335 | repeated runs compound coverage (vendor: one run ≈ half of total, self-reported) | needs a durable ledger location outside the scratchpad | **adopt-with-conditions** — depends on #18335 fingerprints | moderate |
| 5 | **Runtime AI/agent attack classes**: context/retrieval/memory poisoning, tool & action abuse, MCP and sub-agent trust, output-handling/disclosure — as a THREAT_MODEL section *and* a secreview checklist block | `docs/developer/THREAT_MODEL.md`, `secreview/SKILL.md` checklist | AutoBot is an agent platform; its most distinctive attack surface has no checklist entry | doc upkeep only | **adopt** | moderate |
| 6 | **Source-visibility rule + candidate gate wording**: a control living outside the repo (proxy, IdP, provider setting) is never assumed present or absent → `needs_validation` naming the missing fact; defense-in-depth gaps are hardening notes | `secreview/SKILL.md` | fewer speculative HIGHs | none | **adopt** — fold into #18331 (same file, one PR) | trivial |

### Rejected by hidden metrics

- **Install the reference skill wholesale** — Node validators in a Python repo, 170 KB of prompts
  overlapping our own skills (canonical-source rule: a second implementation is a violation).
- **Sandboxed dynamic confirmation of target code** — the reference's OS-sandbox prerequisite is
  unbuilt here, and the standing rule is never to run code from the codebase; leads stay
  `needs_validation` instead.
- **11-step descriptor-based artifact promotion** — solves a multi-agent write race our audits do
  not have (agents return results; the parent writes).

### What We Already Do Better

- **Merge enforcement.** `pr-blocking-findings.yml` turns a filed finding into a required red check
  (#10024); the reference output never reaches a gate.
- **Static + LLM layering.** semgrep/CodeQL SARIF in `security.yml`, with the LLM review explicitly
  advisory and its untrusted-diff mitigations documented in `ai-security-review.yml`.
- **Findings become tracked issues** (`secreview` follow-up rule, `research-to-issues`), whereas the
  reference leaves Markdown in a home directory.
- **Codified trust boundaries** per subsystem with canonical enforcement points (THREAT_MODEL) —
  the reference re-derives the architecture in every run's recon phase.
- **Measurement discipline** and down-only ratchets go deeper than the reference's closure rules
  (already recorded in #18330).

### Gaps & Opportunities (by impact)

1. Runtime agent/LLM trust boundaries absent from THREAT_MODEL and secreview (#5) — highest: the
   product's core surface is unchecked by our own review tooling.
2. Whole-codebase audit has no coverage, verification or schema; its template is placeholders (#1, #2).
3. No machine validator for any finding format (#3).
4. No cross-run carry-forward (#4) — blocked on #18335.
5. Re-witnesses for #18330 (no new issues): severity rubric with a high-vs-medium discriminator and
   `needs_validation` carrying no severity → #18331; fingerprints → #18335; review-fleet silent drops
   → plugin #17.

### Specific Code/Files Affected

| File | Change |
|---|---|
| `.claude/agents/security-auditor.md` | replace prose process with phased mode + profiles + budget; replace the 4 placeholders with the JSON-derived report contract |
| `.claude/skills/secreview/SKILL.md` | add the AI/agent checklist block and the source-visibility rule (rides in the #18331/#18332 PR — same file) |
| `docs/developer/THREAT_MODEL.md` | new section 7: runtime agent/LLM trust boundaries with canonical enforcement points (`knowledge/ingest_sanitize.py`, `knowledge/query_sanitizer.py`, `a2a/trust_score.py`, MCP routes) |
| `scripts/security/` (new) | findings schema + Python validator + test; invoked by the auditor and, optionally, `ai-security-review.yml` |
