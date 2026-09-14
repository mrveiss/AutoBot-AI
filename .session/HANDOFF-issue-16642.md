# Handoff: issue-16642
status: blocked
pr: #16643
base_at_push: b688b3e48cae14d22bb29272fb1d7a72a2d1ac45
gates: wiring=n/a — no new router wiring beyond core_routers.py registration (verified by import) duplication=PASS tests=PASS (pytest local + pre-push hook; 24 tests in claude_memory_importer_test.py, 54 in pii_pipeline_test.py)
needs_rebase_before_merge: yes — origin/main is 10 commits ahead of base_at_push; no overlapping files in this branch's actual diff (confirmed via `git diff origin/main...issue-16642 --name-only`), so a mechanical rebase is expected, not a real conflict
remaining:
- Land #16654 (canonical KB search + grounded-agent RAG enforce no ownership/visibility — pre-existing gap, independent of this PR, but blocks it). Not started by anyone as of this handoff.
- Once #16654 lands: rebase this branch onto current main, re-run CI, get 03's re-review (last verdict was BLOCKED on the read-path gap only — redaction and metadata findings were already resolved and re-verified with a checked-in test, not ad hoc local output)
- Host verification once merged: #16642's own AC calls for a fact-count-before/after run against a live AutoBot instance, plus one imported fact retrievable via KB search — not yet done, can only happen post-merge
blocked_on: #16654 (open, unstarted). #16507 was the other blocker — already closed (merged via #16508 at 9c184227a).
worktree: /home/martins/AutoBot-Ai/worktrees/issue-16642 (safe to remove after #16643 merges)

## done
- `knowledge/claude_memory_importer.py` — frontmatter parser + idempotent upsert into `knowledge_facts` via the existing `store_fact`/`update_fact` write path (declared system-of-record in `store_authority.py`, no bypass)
- `api/knowledge_claude_memory.py` — admin-gated `POST /knowledge_base/import_claude_memory` (background task via `fire_and_forget`) + status-poll endpoint
- Security hardening (3 review rounds, all findings resolved except the read-path gap now tracked as #16654):
  - Redaction via `a2a.pii_pipeline` (reused, not forked) — widened its credential-assignment detector (password/token/secret/private_key, not just API-key-shaped names) and added PEM private-key block detection; added an importer-local `ssh user@host` detector
  - `owner_id`/`visibility=PRIVATE`/`access_level=SYSTEM` on every imported fact, with a test proving `knowledge.ownership.KnowledgeOwnership.check_access` actually honours it (owner reads, everyone else denied) — not just that the metadata is present
  - A dedicated test proving `access_level`'s `AccessLevel.SYSTEM` and `visibility`'s `ScopeLevel.SYSTEM` are different enum members with different semantics, and this importer only ever sets the latter to `PRIVATE`
  - Dropped the caller-supplied `memory_dir` override entirely — the endpoint takes no body
- Fixed two CI-mechanics issues discovered along the way: a background-task retention-ratchet violation (switched to `autobot_shared.async_compat.fire_and_forget`) and a duplication-guard breach (extracted `TaskStatusRecord.to_response_dict()`, shared with `knowledge_population.py`'s existing status endpoints — net shrinks that grandfathered file)
- Filed and linked three follow-ups, none blocking: #16655 (exact-match fleet-hostname/IP redaction — closes a disclosed, deliberately-not-forced gap), #16656 (isolated knowledge buckets — commented with the owner's user/group/LLC sharing requirement, reusing existing `ScopeLevel`), #16661 (folder-watch continuous auto-import, owner's idea)

## notes
- `ssot_config.py` and `knowledge_population.py` are both at their frozen python-file-size-ratchet ceilings (#14236) — the configurable memory-dir path and the two new endpoints landed as new sibling modules instead of growing either file; `knowledge_population.py`'s ceiling was lowered (1547→1525) since the dedup extraction shrank it
- Declined a coordinator-assigned pickup of #16665 (T3 of the #16654 decomposition) — out of scope for this session per the owner; someone else is taking it
- A multi-session coordination layer (`~/.claude/scripts/ledger`, backed by a private redis-stack) is active on this repo — `ledger pr 16643` / `ledger events` shows live state. This session's claims on `pr 16643` and `worktree issue-16642` were released at session end.
