# Handoff: issue-14111-stable-shard

status: partial
pr: (none — not opened, the implementation does not yet satisfy its own tests)
base_at_push: origin/Dev_new_gui @ 7f5d11605
gates: tests=FAIL (4 of 16 in repo_tests/stable_shard_test.py)
needs_rebase_before_merge: yes
remaining: make the assignment stable; then wire it into the shard workflow

## Why this exists

#14111: unrelated tests fail inside `python-suite` shards when the split shifts.
pytest-split's `duration_based_chunks` cuts the *collected list* into contiguous
chunks, so a shard's membership is a function of the collected list's order AND
membership. Adding one test file shifts every downstream boundary, and a PR is
reddened by a failure nowhere near its change.

This is an attempt at module-level assignment that does not move existing modules
when the collection changes.

## Where it actually is

**The implementation does not do what its tests demand.** The tests are right; the
implementation is not:

```
test_adding_a_module_moves_no_existing_module
  AssertionError: 271 existing modules changed shard when one module was added
```

All four `TestStability` cases fail the same way — contiguous chunking still
reshuffles on any change. A stable assignment needs to be a function of the module
identity alone (a hash-based bucket, or a persisted assignment map), not of the
module's position in a sorted list. That is the redesign this needs; the 12 passing
tests cover the non-stability properties and should keep passing through it.

## How it got here

Found uncommitted and untracked in the `issue-14270` worktree during session
close — written earlier in the session, then stranded when work moved on. Committed
here on its own branch so it is not lost to a worktree sweep. It has never been
pushed as a PR and nothing depends on it.

## Do not

- Do not open a PR from this as-is; it would be a red PR with no fix.
- Do not delete it as dead code. It is unfinished work with a live issue (#14111)
  and its failing tests are the specification.
