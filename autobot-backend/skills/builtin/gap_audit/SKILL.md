---
name: gap-audit
description: After completing a batch fix or implementation, audit adjacent files for the same issue and file GitHub discovery issues for each gap found. Use after any batch implementation, bug fix, or remediation campaign.
metadata:
  type: skill
---

# Gap Audit

Run after completing work to catch similar issues in adjacent files that weren't part of the original batch.

## Steps

1. **Identify modified files from the completed work**
   ```bash
   git diff --name-only HEAD~1..HEAD
   # or for a specific PR:
   gh pr diff <PR_NUMBER> --name-only
   ```

2. **State the fix pattern in one sentence** — e.g., "adds response_model=None to router decorators", "adds source_id ownership guard to analytics endpoints", "adds --exclude=.env to rsync calls".

3. **Find candidate files** — glob for files with the same extension and directory as the modified files:
   ```bash
   find <same-directories> -name "*.py" | grep -v __pycache__ | sort
   # Compare against already-fixed list; drop those
   ```

4. **Check each candidate** — for each file NOT in the already-fixed list:
   - Read the file
   - Apply the same fix criteria used in the completed work
   - If the same issue exists → add to gap list with specific line numbers

5. **File a discovery issue per gap** (or one issue with a checklist if gaps are in the same module):
   ```bash
   gh issue create \
     --title "Gap: <fix-pattern> needed in <file-or-module>" \
     --body "$(cat <<'EOF'
   ## Discovered Gap

   **Pattern:** <what needs fixing>
   **Found during:** gap audit after <PR/commit reference>

   ### Affected Files
   - [ ] `path/to/file.py` line <N> — <specific issue>

   ### Fix
   Apply the same fix as in <reference PR/commit>.

   **Estimated effort:** small
   EOF
   )" \
     --label "discovered,gap"
   ```

6. **Report** — output a summary:
   - Total candidates checked
   - Gaps found (with issue numbers filed)
   - Confirmation that no gaps = coverage complete

## Scope Heuristics

- **Default:** Same directories as modified files
- **Cross-cutting security fix:** Expand to full codebase (`find . -name "*.py"`)
- **API endpoint fix:** Scope to `api/` and `tests/api/` directories
- **Shared utility fix:** Check all importers (`grep -r "from module import"`)

## Example Invocation

> "I just fixed source_id guards in 3 analytics endpoints. Run a gap audit."

1. `git diff --name-only HEAD~3..HEAD` → lists `api/analytics_quality.py`, `api/analytics_code.py`, `api/analytics_cfg.py`
2. Pattern: "missing source_id ownership check before returning data"
3. Find all `api/analytics_*.py` files → check each for the pattern
4. Found gap in `api/analytics_debt.py` → file issue
5. Report: "1 gap found, filed as #9234. 4 other analytics files clean."
