---
name: bulk-audit
description: Systematic codebase audit and batch remediation — scan for anti-patterns, file issues, fix in validated batches
---

# Bulk Audit & Batch Remediation

Use for: hardcoded credentials/IPs, missing error handling, security anti-patterns, TODO/FIXME sweeps, or any fix that touches 10+ files.

## Phase 1: Discover

1. **Define the pattern to find:**
   ```bash
   grep -rn "<pattern>" --include="*.py" --include="*.ts" --include="*.vue" . | head -50
   ```

2. **Count scope:**
   ```bash
   grep -rl "<pattern>" --include="*.py" . | wc -l
   ```

3. **Classify findings by severity** (critical / high / medium / low):
   - Critical: security vulnerabilities, data corruption risk
   - High: hardcoded credentials, IPs, broken error handling
   - Medium: performance issues, code smells
   - Low: style, minor tech debt

4. **Create a GitHub issue per category** (not one per file):
   ```bash
   gh issue create --title "Fix: <description>" \
     --body "$(cat <<'EOF'
   ## Problem
   <pattern found, severity, impact>

   ## Scope
   <N files affected — list first 10>

   ## Fix Approach
   <how to fix>
   EOF
   )" --label "bug,backend,priority: high"
   ```

## Phase 2: Validate Fix on Sample

**NEVER apply bulk fixes without validating on 2-3 files first.**

1. Pick 2-3 representative files from the findings
2. Apply the fix manually to those files
3. Run pre-commit on them:
   ```bash
   pre-commit run --files <file1> <file2> <file3>
   ```
4. Run affected tests:
   ```bash
   python -m pytest tests/ -k "<relevant_keyword>" -x
   ```
5. Only proceed to Phase 3 if all checks pass

## Phase 3: Batch Fix (10-20 files per batch)

**Never apply across all files at once — work in batches of 10-20.**

For each batch:
```bash
# Get next batch of files
FILES=$(grep -rl "<pattern>" --include="*.py" . | head -20)

# Apply fix to each file (Edit tool, not sed/awk)
# ... apply fixes ...

# Validate batch
pre-commit run --files $FILES

# If clean, commit this batch
git add $FILES
git commit -m "fix(scope): <description> (#{issue_number}) batch N/M"
git show --stat HEAD
```

If pre-commit fails on any file in the batch:
- Fix that file
- Re-run pre-commit on the fixed file
- Do NOT move to next batch until current batch is clean

## Phase 4: Verify & Close

```bash
# Confirm pattern is gone
grep -rn "<pattern>" --include="*.py" . | wc -l  # Should be 0

# Run full test suite
python -m pytest tests/ -x --tb=short

# Close the issue
gh issue close {issue_number} --comment "Fixed across N files in M batches. Tests passing."
```

## Guardrails

- **Stop if a batch produces unexpected test failures** — diagnose before continuing
- **Stop if pre-commit fails 3 times on same file** — manual inspection needed
- **Never use `--no-verify`** — fix the underlying issue
- **File per-file issues** if a specific file needs structural changes beyond a simple search-replace
- **Log each batch as a GitHub issue comment** so progress is tracked if session ends early:
  ```bash
  gh issue comment {issue_number} --body "Batch N/M complete: fixed files X, Y, Z. Remaining: N files."
  ```
