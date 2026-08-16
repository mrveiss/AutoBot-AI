# Handoff: issue-14305

status: complete
pr: #14338
base_at_push: origin/Dev_new_gui @ 7f5d11605
gates: flake8=PASS black=PASS isort=PASS tests=PASS (49 targeted, 208 surrounding)
needs_rebase_before_merge: no
remaining: (none — awaiting CI + merge)

## What landed here

Every prior turn reached the model attributed to the caller, the assistant's own
replies included, because the reader asked for the API-shape role key over records
whose writer stores the speaker under the stored key.

Two things a successor must not undo:

1. **`llm_role` is an allowlist, deliberately.** Not a denylist of the terminal /
   agent-terminal / state-machine speakers. Those were found by grepping ONE
   keyword-argument form; a sender passed positionally or via a variable would not
   have appeared, and review found ~a dozen more from the websocket layer. Naming
   what may pass is what keeps the unenumerated ones safe.

2. **The system role is excluded on purpose.** Persisted approval notices use that
   speaker, and an adapter that splits the role out hoists it into the instruction
   channel. Today the plain chat path carries no competing system prompt for it to
   overwrite (`chat_optimized` does); the exclusion is about not elevating ordinary
   history into the highest-trust slot, not about a live collision.

## Sequencing constraint

**#14342 must not be fixed before this merges.** The websocket layer drops its
session id, which is the only reason its ~dozen non-conversational speakers are
inert. Close that routing gap first and they go straight into provider requests.

## Filed from this work

#14340 (shared-link viewer renders every session empty), #14341 (overflow summaries
persist empty — the conversation they replaced is lost), #14342 (websocket events
never reach their session).
