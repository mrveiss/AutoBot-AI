# Handoff: issue-14111-stable-shard

status: complete (implementation) — wiring is a pending decision
pr: (none yet — see "The remaining decision")
base_at_push: origin/Dev_new_gui @ 7f5d11605
gates: tests=PASS (18/18), validated against the real .test_durations
needs_rebase_before_merge: yes
remaining: decide whether ci.yml adopts this; it is inert until something passes --shard-splits

## Why this exists

#14111: unrelated tests fail inside `python-suite` shards when the split shifts.
pytest-split's `duration_based_chunks` cuts the *collected list* into contiguous
chunks, so a shard's membership is a function of the collected list's order AND
membership. Adding one test file shifts every downstream boundary, and a PR is
reddened by a failure nowhere near its change.

This is an attempt at module-level assignment that does not move existing modules
when the collection changes.

## The four failures were in the TESTS, not the implementation

Earlier note here said the implementation did not satisfy its tests. That was the
wrong diagnosis, and it is worth recording because it is subtle.

`_assignment()` rebuilt the bucket table from the *mutated collection* on both
sides of each comparison. Adding a module then changed the weights, which changed
the table, which re-dealt everything — so the tests asserted a property the design
deliberately does not have.

**The durations file and the collected set are different inputs, and only the first
may feed the table.** A PR that adds tests changes what is collected; it does not
touch `.test_durations`. That separation *is* the mechanism. The tests now build
the table once and route different collections through it, which is what production
does.

Confirmed independently by another session working the same issue, which measured
LPT-over-modules at 1,019 of 1,283 modules moved and pure-hash at 2.97x imbalance —
the hash→bucket→LPT combination is the one that gets both properties.

## Validated against the real durations file

| Measure | Independent figure | This implementation |
|---|---|---|
| modules in `.test_durations` | 1,283 | 1,283 |
| balance by test count | 1.18x | 1.18x |
| modules moved, 50 trials | 0 | 0 |

## The remaining decision

Nothing passes `--shard-splits`, so this plugin is inert. Adopting it means editing
`ci.yml`, next to an explicit "Do not switch it" note at `ci.yml:243`. That note
warns against `least_duration`, which scatters individual tests — a module-level
assignment keeps modules whole, so it is not what the note forbids. Even so, a
CI-wide change deserves a decision rather than a surprise PR.

## How it got here

Found uncommitted and untracked in the `issue-14270` worktree during session
close — written earlier in the session, then stranded when work moved on. Committed
here on its own branch so it is not lost to a worktree sweep. It has never been
pushed as a PR and nothing depends on it.

## Do not

- Do not open a PR from this as-is; it would be a red PR with no fix.
- Do not delete it as dead code. It is unfinished work with a live issue (#14111)
  and its failing tests are the specification.
