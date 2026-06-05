# Issue Closure Verification Gate

**NEVER close an issue without 100% verification. Issues remain OPEN until ALL acceptance criteria are proven met.**

## Before Closing an Issue

1. **Read the issue description fully** — identify ALL acceptance criteria (stated and implicit)
2. **Find the merged commit(s):** `git log --all --grep="<issue-number>"`
3. **Verify each acceptance criterion:**
   - Is the feature/fix actually implemented? (check diff)
   - Does it work correctly? (test output, curl, UI verification)
   - All edge cases handled? (review code, error handling)
   - Tests passing? (run test suite for changed modules)
   - Documentation updated if needed?
   - **Integration check (#6836 gate):** for every NEW module added, at least one production caller must import it:
     ```bash
     ./pipeline-scripts/check-new-module-callers.sh
     ```
     Exits 0 if all new modules have callers, 1 if any have zero callers. **Zero callers ⇒ closure blocked**, even if tests pass.
   - **Deliberate-deferral override:** if a new module is infrastructure-only by design, file a follow-up wire-in issue first, then:
     ```bash
     echo "#NNNN" >> .wiring-deferral.txt
     ./pipeline-scripts/check-new-module-callers.sh --allow-deferral .wiring-deferral.txt
     ```
     Document in closure comment: `### Wire-in deferred to #NNNN`

4. **Document the proof:**
   - Commit hash(es) + commit messages
   - `✅ Criterion 1`, `✅ Criterion 2`, etc.
   - Evidence: test output, curl response, screenshot, or CI check reference

5. **Close with proof comment:**
```bash
gh api repos/mrveiss/AutoBot-AI/issues/<number>/comments -f body="✅ Closed with proof of implementation

**Commit(s):** <hash1> (<msg1>), <hash2> (<msg2>)

**Acceptance Criteria Met:**
- ✅ Criterion 1 — evidence here
- ✅ Criterion 2 — evidence here
- ✅ Criterion 3 — evidence here"
```

---

## Discovery Issues (File During Every Task)

While implementing, if you notice **any** bug, inconsistency, dead code, missing test, hardcoded value, or tech debt NOT part of the current issue — file a GitHub issue immediately. Do not fix it inline, do not add a TODO comment.

```bash
gh issue create --title "discovery(<area>): <what you found>" --body "..." --label "tech-debt"
```

**Before closing any issue:** confirm all gaps noticed during implementation have been filed. This is mandatory.

**Why:** Gaps noticed inline and not filed are permanently lost. Discovery issues are the primary source of the issue backlog.

---

## Examples

❌ **Incomplete closure (avoid):**
- "Fixed in PR #1234" (no proof of acceptance criteria)
- Closing based on PR status alone (PR merged ≠ issue resolved)
- No test output or verification

✅ **Complete closure:**
- Commit hash + all criteria verified + test output attached
- Feature tested end-to-end in dev environment
- All edge cases documented as handled
- Follow-up issues filed for any gaps found

---

## If ANY Criterion Not Met

- **DO NOT close the issue** — leave it OPEN
- Comment: `⚠️ Criterion X not met: <reason>`
- File follow-up: `discovery: <gap found>`
