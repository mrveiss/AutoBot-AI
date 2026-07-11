# Issue Closure Verification Gate

**NEVER close an issue without 100% verification. Issues remain OPEN until ALL acceptance criteria are proven met.**

## The Three Mechanical Gates (#11599 — post-mortem of #6828/#8082)

These compare the delivery against the ORIGINAL ISSUE BODY — implementation health (tests pass, modules have callers) is necessary but not sufficient.

1. **Verbatim ACs.** The closure comment quotes the original issue-body acceptance criteria verbatim, one per line, each followed by evidence or an explicit `❌ NOT met → follow-up #X`. Never restate/paraphrase what was shipped — an AC that can't be quoted-and-checked can't be silently rescoped.
2. **Dangling-reference grep.** Before `gh issue close N`, run:
   ```bash
   pipeline-scripts/check-issue-close-refs.sh <N>
   ```
   Forward-tracking references (`tracked in #N`, `TODO(#N)`, `deferred to #N`, wrapped across lines included) **block closure** until a real follow-up issue exists and each reference is updated. Historical mentions pass. Also eyeball the credited PR diff for `#N`. Exit 1 ⇒ do not close.
3. **No partial close.** A bundled/multi-issue PR's `Closes #N` requires the FULL AC set of N. If a PR delivers a subset: check off the delivered subtask on the issue and either leave it open or name the follow-up issue number in the same comment. Riding along on a bundle's momentum never closes an issue.

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

5. **Close with proof comment** (Gate 1: criteria are QUOTED VERBATIM from the issue body, not restated):
```bash
gh api repos/mrveiss/AutoBot-AI/issues/<number>/comments -f body="✅ Closed with proof of implementation

**Commit(s):** <hash1> (<msg1>), <hash2> (<msg2>)
**Gate 2:** \`check-issue-close-refs.sh <number>\` → clear

**Acceptance Criteria (quoted verbatim from issue body):**
- \"<exact AC text from issue>\" — ✅ evidence here
- \"<exact AC text from issue>\" — ✅ evidence here
- \"<exact AC text from issue>\" — ❌ NOT met → follow-up #XXXX"
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
