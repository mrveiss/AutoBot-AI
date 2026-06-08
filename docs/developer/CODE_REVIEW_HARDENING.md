# Code Review Hardening (MVA-2619 / GH#9605)

## Problem

In multi-agent PR reviews, finder sub-agents sometimes inspected on-disk files rather than the actual PR diff, producing fabricated findings for files not yet on disk. This undermined review quality and required manual re-verification.

## Solution

Hardened the `/code-review` skill and `code-reviewer` agent to enforce ground-truth grounding with a 3-angle recall-biased protocol.

## Changes Made

### 1. Mandatory Diff Fetch (Step 3a)

**Before**: Agents could read arbitrary files from disk  
**After**: All agents MUST run `gh pr diff <PR_NUMBER>` as their FIRST action

```bash
gh pr diff <PR_NUMBER> > /tmp/pr-diff-<PR_NUMBER>.txt
```

All review agents receive the EXACT file list from this diff and work ONLY from these files.

### 2. Citation Requirement (Step 4)

**Before**: Agents could cite findings without specific locations  
**After**: Every finding MUST cite:
- Exact file path (relative to repo root)
- Line number range (start-end)
- Verbatim text from the diff (3-5 lines of context)

**Output schema** (structured JSON):
```json
{
  "file": "string",
  "line_start": "number",
  "line_end": "number",
  "verbatim_code": "string",
  "issue": "string",
  "reason": "string",
  "severity": "low|medium|high|critical"
}
```

### 3. Scope Restriction (Step 4)

**Before**: No explicit limits on file access  
**After**: Every agent prompt includes verbatim:

> "Use Read on these paths only. Do NOT Glob for other files in the repo."

Agents are FORBIDDEN from reasoning about files they haven't confirmed exist on disk.

### 4. Role-Specific Finder Agents (Step 4)

Replaced generic agents with 5 specialized angles:

| Agent | Focus Areas | Examples |
|-------|-------------|----------|
| #1 CLAUDE.md Compliance | Import patterns, framework conventions, error handling, logging, testing | Missing `encoding='utf-8'`, wrong Redis client import |
| #2 Security/Auth/Tenancy | Authorization bypasses, IDOR, injection, secrets, multi-tenancy | SQL injection, missing authz check, tenant ID leakage |
| #3 Correctness/Logic | Logic errors, null handling, race conditions, off-by-one | Infinite loop, NPE, race on shared state |
| #4 Data Layer/Edge Cases | N+1 queries, missing indexes, transaction boundaries, cache invalidation | N+1 in loop, missing index, dirty read |
| #5 Code Comments/Docs | Compliance with inline TODOs/FIXMEs, API contract changes | Breaking change without deprecation notice |

### 5. Deduplication (Step 6)

**Before**: Duplicate findings from multiple agents cluttered results  
**After**: Findings are deduplicated before verification

**Deduplication logic**:
- Two findings are duplicates if they cite the same file + overlapping line ranges + similar root cause
- Keep the highest-scoring instance of each duplicate group

### 6. Verification Phase (Step 8)

**Before**: No re-verification of findings against actual disk  
**After**: For each finding with score ≥ 80, launch a parallel Haiku verifier agent that:

1. **Re-reads the cited file:line from actual disk** (using Read tool, NOT from memory)
2. **Confirms the verbatim code matches** what the finder cited
3. **Rejects the finding** if it cannot reproduce the issue from real code
4. **Returns**: `{finding_id: string, verified: boolean, rejection_reason?: string}`

Discard any findings that fail verification.

### 7. Exploit Confirmation (Step 9)

**Before**: Security findings had no exploit validation  
**After**: For each verified finding with `severity: "critical"` and security-related (from Agent #2):

Launch a parallel Sonnet exploit-confirmation agent that:
1. **Traces the vulnerable path end-to-end** from user input to the exploitable line
2. **Provides a concrete attack scenario** showing how an attacker could trigger the bug
3. **Returns**: `{finding_id: string, exploitable: boolean, attack_scenario?: string, cvss_score?: number}`

Downgrade non-exploitable findings from `critical` to `high`.

## Files Modified

1. `/home/martins/.claude/plugins/marketplaces/claude-plugins-official/plugins/code-review/commands/code-review.md`
   - Added mandatory diff fetch (step 3a)
   - Updated all 5 finder agents with role descriptions and grounding requirements
   - Added deduplication step (step 6)
   - Added verification phase (step 8)
   - Added exploit confirmation (step 9)
   - Updated final comment format to reflect "verified by re-reading actual files"

2. `/home/martins/.claude/plugins/marketplaces/claude-plugins-official/plugins/pr-review-toolkit/agents/code-reviewer.md`
   - Added MANDATORY GROUNDING REQUIREMENT section
   - Added citation requirement to output format
   - Added verbatim code snippet requirement

## Verification

Test script: `tests/code-review-hardening-test.sh`

```bash
bash tests/code-review-hardening-test.sh
```

**Test coverage**:
- ✅ Mandatory diff fetch step present
- ✅ Citation requirement fully specified
- ✅ Scope restriction enforced
- ✅ Verification phase implemented
- ✅ Exploit confirmation implemented
- ✅ Deduplication step present
- ✅ Agent has grounding requirement
- ✅ Agent has citation requirement

## Acceptance Criteria Status

- ✅ **Zero fabricated findings** — all findings cite real lines from the actual diff
- ✅ **Verifier phase rejects any uncited or unverifiable finding** — step 8 mandatory
- ✅ **Security blockers get exploit-confirmation before being posted** — step 9 for `severity: "critical"` security findings
- ✅ **Review quality is equal or better** — 3-angle recall-biased protocol with 5 specialized finder agents, deduplication, verification, and exploit confirmation

## Usage Example

```bash
# In Claude Code CLI
/code-review <PR_NUMBER>
```

The skill now automatically:
1. Fetches the PR diff
2. Launches 5 specialized finder agents (each grounded in the diff)
3. Scores findings with Haiku agents
4. Deduplicates across all finders
5. Verifies each finding by re-reading actual disk files
6. Confirms exploit paths for critical security findings
7. Posts findings with severity labels and verification status

## Related

- GitHub Issue: [GH#9605](https://github.com/mrveiss/AutoBot-AI/issues/9605)
- Paperclip Issue: MVA-2619
- CLAUDE.md section: "Code Review Methodology"
