# Agent memory governance — comparative study

Date: 2026-10-18 · AutoBot base: `origin/main@555e91450e`
Scope: the 10 reference systems (of 754 catalogued) that a public memory-system index marks with all seven
governance mechanisms — tombstone, trust state, bi-temporal, scope enforced, mutation audit, human review,
negative evals. Each was read from source (read-only); two upstream repos were gone and were read from an
archive fork. Nothing from any source was executed. All benchmark figures are self-reported and unverified.

Reference systems are anonymized as Ref A–J. Per-system notes: kept with the session, not landed.

## Phase 1 — what the reference set does

| Ref | Stack | Distinctive mechanism |
|---|---|---|
| A | C + Go owner, Postgres | Authority comes from the verified caller, never the text; model writes are candidates no read serves and no model tool can approve |
| B | Python, DuckDB | Two "ghost" ledgers (deletion hash + rejection slot) checked on every write; auto-reviewer may never set `approved` |
| C | Python, Postgres + Redis | Per-tenant hash-chained audit; single scope-predicate builder; quarantine status |
| D | Rust, SQLite | Digest-only rejected-value tombstone; override journaled, tombstone stays; suppression follows derivations |
| E | Python | Per-tenant erasure registry + ordered, explainable exclusion reasons at read |
| F | Python, Postgres | Verdict per hit, fail-closed (`invalid_metadata`, `ambiguous_supersession`, `unverified` ≠ `low_confidence`) |
| G | Rust, Postgres | Tombstone checked on write AND on raw-chunk recall; restore = exemption row; monotonic `recorded_at` |
| H | Python, SQLite | Tool layer stamps origin; deterministic qualify gate with nine refusal rules; model proposes, never promotes |
| I | Rust, Postgres | Trust states as separate tables (pending / facts / rejected), so a missed WHERE fails safe |
| J | Python | Tombstone guard inside the `promote()` primitive; review only off the agent transport |

### Cross-cutting patterns (present in most of the set)
1. **Authority from the channel, not the content.** The origin (user / agent / system / operator) is set by the calling layer and caps confidence (A, H, I).
2. **The model proposes, a human disposes.** The agent transport has no approve verb, and the reviewer identity is the authenticated principal (A, B, H, I, J).
3. **Value-keyed tombstones on a canonical identity**, checked in the write primitive and sometimes at recall (A, B, D, G, J).
4. **Bi-temporal**: validity time is kept separate from belief/record time, and corrections supersede instead of overwriting (A, F, G, H).
5. **Audit at the store seam**, append-only, and often hash-chained (A, C, D, E, J).
6. **Negative evals paired with positive controls**, plus an empty-store control against vacuous passes (A, B, C, D, I, J).

### Shared weaknesses (none of the set solves these)
- Tombstones match exact or lexical values, so paraphrases get through.
- Hash chains without an externally published head cannot detect tail truncation.
- Scope often rests on caller convention or non-forced RLS.
- Self-authored benchmarks.
- Large single files (2.8 MB, 797 KB, 4,280 lines) and dead lifecycle paths.

### Visible vs hidden
- **Visible**: all-seven-marks status (a single reviewer's code reading, revised over time), plus LongMemEval and LoCoMo scores (self-run).
- **Hidden**: a mandatory Postgres version, separate audit workers, 88k-line memory owners, global write locks, and review queues with no proof that anyone drains them.
- **Verdict**: copy the invariants. The machinery is not worth adopting.

## Phase 2 — AutoBot against the seven

| Mechanism | AutoBot today | Evidence | Gap issue |
|---|---|---|---|
| Tombstone | ABSENT | `delete_fact` drops the `content_hash:` key (`knowledge/facts.py:1215`) | #18078 (+ deltas comment), #18824 |
| Trust state | PARTIAL | `verification_status` written; read by **no** retrieval path → rejected facts are served | #18820, #18077 |
| Bi-temporal | PARTIAL | graph `valid_from/valid_to` always write-time; no record-time axis; KB edits overwrite | #18079 |
| Scope enforced | PARTIAL | general/verbatim stores enforce owner; memory graph has no owner; KB search scopes only if caller passes a filter | #18825, #16727, #16701, #18076, #18073 |
| Mutation audit | PARTIAL | route-level, fire-and-forget; 6 store writers emit nothing; no tamper evidence | #18821 |
| Human review | PARTIAL | admin queue exists, but `verified_by` = request body, queue always empty, agent facts served unreviewed | #18077, #18162 |
| Negative evals | ABSENT | no test asserts excluded facts are absent from recall | #18823 |
| Write-time screening | PARTIAL | KB facts only; graph / verbatim / atomic / general unscreened | #18822 |

### What AutoBot already does better
- **Approval-gate infrastructure exists and is general**: `services/approval_gate_service.py` and `services/approval_execution.py`. The decider is taken from the authenticated route, and resubmits cannot change the fields that were reviewed. Only A comes close; the others use free-text reviewer ids or a CLI by omission.
- **Canonical audit trail and redaction SSOT already exist** (`services/audit/store.py`, `autobot_shared/secret_redaction`). The work is wiring, not building. Several reference systems maintain a second, bespoke chain.
- **Owner enforcement in the store layer** for general and verbatim memory (`general_storage._require_user_id`). Many of the set leave this to caller convention.

### How to become superior rather than equal
Closing #18077/#18078/#18079/#18162 plus #18820–#18825 gives all seven, on AutoBot's existing approval and
audit seams. Two steps would put AutoBot ahead of the whole set:
1. **Paraphrase-resistant tombstones.** Every reference system misses restated values. Check the tombstone against the embedding neighbourhood as well as the canonical digest, with a measured false-positive rate. File this once #18078 lands, as an evidence-gated follow-up.
2. **A truncation-proof audit head.** Publish the chain head to the existing approval / paper-trail store, so tail truncation becomes detectable. No reference system does this; Ref E documents it as a known hole.
