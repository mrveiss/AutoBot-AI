---
name: pre-merge-validate
description: Validate code before merging — syntax, imports, call-site impact, tests, types, and linting
---

# /pre-merge-validate — Pre-Merge Validation Gates

## Usage
```
/pre-merge-validate <PR-number>     # resolve branch via gh pr view
/pre-merge-validate issue-<branch>  # use branch name directly
/pre-merge-validate                 # validate current branch vs Dev_new_gui
```

## Gates

**Setup**
1. Resolve branch: `gh pr view <number> --json headRefName -q '.headRefName'`
2. Fetch and verify: `git fetch origin Dev_new_gui && git rev-parse origin/Dev_new_gui origin/$BRANCH`

**Gate 0 — Squash-Duplicate Detection**
3. Count total vs truly-new commits:
   ```bash
   TOTAL=$(git log origin/Dev_new_gui...$BRANCH --oneline | wc -l)
   NEW=$(git log --cherry-pick --right-only origin/Dev_new_gui...$BRANCH --oneline | wc -l)
   ```
   - Block if `NEW -eq 0` (all already merged — close the PR)
   - Warn if `DUPES -gt 0 && NEW -gt 0` (partial duplicate — don't block)

**Gate 1 — Python Syntax + Imports**
4. Get changed files: `git diff origin/Dev_new_gui...$BRANCH --name-only -- '*.py' | grep -E '^autobot-backend|^autobot-shared'`
5. Per file — syntax: `python -c "import ast; ast.parse(open('$file').read())"`
6. Per file — imports: `python -m py_compile "$file"`
7. For `api/schemas_*.py` — runtime import: `(cd autobot-backend && python3 -c "from api import $SCHEMA_MOD")`
   - Block on any SyntaxError, ImportError, or NameError

**Gate 2 — Call-Site Impact Analysis**
8. Find removed symbols:
   ```bash
   git diff origin/Dev_new_gui...$BRANCH -- '*.py' | grep '^-def \|^-    def \|^-class ' | sed 's/^-//;s/(.*//;s/^[[:space:]]*//' | sort -u
   ```
9. Per symbol — find callers outside changed files:
   ```bash
   grep -r "$symbol" autobot-backend/ autobot-shared/ --include="*.py" --exclude-dir="tests" -l | grep -v "$(git diff --name-only ...)"
   ```
   - Block if any callers found
10. For changed signatures — compare old vs new `def $symbol(` line; block if unchanged callers exist

**Gate 3 — Targeted Test Run**
11. Map `autobot-backend/services/kb_service.py` → `autobot-backend/tests/test_kb_service.py`
12. Run: `cd autobot-backend && pytest $TEST_FILES -x --tb=short -q`
    - Block on test failure; Skip if no matching test files found

**Gate 4 — Frontend Type Check (conditional)**
13. Check: `git diff origin/Dev_new_gui...$BRANCH --name-only | grep -c "^autobot-frontend"`
14. If changed: `cd autobot-frontend && npm run type-check`
    - Block on TypeScript errors; Skip if no frontend changes

**Gate 5 — Linting**
15. Backend: `cd autobot-backend && flake8 --config=.flake8 $BACKEND_CHANGED`
    - Block on E/F codes; W/C codes reported only
16. Frontend (non-blocking): `cd autobot-frontend && npm run lint -- --quiet`

## Verdict
```bash
# Print gate summary table, then:
[ "$VERDICT" = "BLOCKED" ] && exit 1 || exit 0
# CLEAR TO MERGE  or  BLOCKED — fix failures before merging
```

## Integration with /team-implement
17. In SUCCESS path before `gh pr create`:
    ```bash
    /pre-merge-validate issue-$issue || { mark RETRY_QUEUED, Last Failure=VALIDATION_FAILED; return; }
    ```
