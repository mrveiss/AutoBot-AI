# Handoff: issue-14306

status: complete
pr: #14347
base_at_push: origin/Dev_new_gui @ 7f5d11605
gates: flake8=PASS black=PASS isort=PASS tests=PASS (10 new, 18 with adjacent)
needs_rebase_before_merge: no
remaining: (none — awaiting review + CI + merge)

## What landed here

`keep_system_prompt` defaults to True, so the DEFAULT session reset was silently
discarding the system prompt. The filter compared the API-shape role key against
records the store keeps under the stored key, so it never matched, and the endpoint
reported 0 preserved — which reads as "there was no prompt", not as a failure.

## The part worth remembering

Both halves needed fixing, and the second is the instructive one.

`_to_persisted_system_message` was written correctly **for its stated input**. Its
#7025 docstring asserts "`_preserve_system_messages` returns messages with `role`
keys". That was never true. The translator was built to match the assertion rather
than the records, so the two functions agreed with each other about a shape the
store does not produce — and each looked correct read in isolation.

Fixing only the filter would have moved the failure one function downstream.

## Deliberately NOT done here

The `llm_role` clamp from the sibling PR (#14338) is not used on this path, and
should not be. That clamp exists to make a **provider request** legal. This path
writes back to storage, where the faithful speaker is the correct one.
