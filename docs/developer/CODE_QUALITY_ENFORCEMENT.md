# Code Quality Enforcement

**Status**: ✅ Automated (as of 2025-10-09)
**Replaces**: Manual fix scripts in `scripts/` directory

## Overview

AutoBot uses automated code quality enforcement to ensure consistent code style, catch common errors, and improve security. This system **replaces all manual code quality fix scripts** with automated checks that run on every commit and in CI/CD.

## Automated Checks

### Pre-Commit Hooks (Local Development)

Runs automatically before each git commit:

- ✅ **Black** - Python code formatting (88 char line length)
- ✅ **isort** - Import sorting (Black-compatible profile)
- ✅ **flake8** - Python linting and style guide enforcement
- ✅ **autoflake** - Remove unused imports and variables
- ✅ **bandit** - Security vulnerability scanning
- ✅ **Trailing whitespace** - Remove trailing whitespace
- ✅ **YAML/JSON** - Validate configuration files
- ✅ **File size** - Prevent accidental large file commits

### CI/CD Pipeline (GitHub Actions)

Runs on every push and pull request to main branches:

- All pre-commit checks
- Additional validation for production readiness
- Fails the build if code quality issues detected

## Installation

### Quick Setup

```bash
# Run the installation script
bash scripts/install-pre-commit-hooks.sh
```

This script:
1. Installs pre-commit and code quality tools
2. Configures pre-commit hooks in `.git/hooks/`
3. Runs initial check on all files
4. Reports any issues that need fixing

### Manual Setup

If you prefer manual installation:

```bash
# Install tools
pip install pre-commit black isort flake8 autoflake bandit[toml]

# Install hooks
pre-commit install

# Run on all files
pre-commit run --all-files
```

## Usage

### Automatic (Recommended)

Pre-commit hooks run automatically on `git commit`. If issues are found:

1. **Auto-fixable issues** (formatting, whitespace) are fixed automatically
2. **Manual fixes required** (complex linting errors) will abort the commit with instructions
3. Fix the issues and commit again

### Manual Execution

Run pre-commit hooks manually anytime:

```bash
# Run on all files
pre-commit run --all-files

# Run on specific files
pre-commit run --files backend/api/files.py src/config.py

# Run specific hook
pre-commit run black --all-files
pre-commit run flake8 --all-files
```

### Skip Hooks (Not Recommended)

In rare cases where you need to skip hooks (e.g., work-in-progress commit):

```bash
git commit --no-verify -m "WIP: incomplete feature"
```

**⚠️ Warning**: Skipping hooks means your code will fail CI/CD checks.

## Configuration Files

### `.pre-commit-config.yaml`

Main configuration for all hooks:
- Hook repositories and versions
- Arguments for each tool
- File exclusions

### `.bandit`

Security scanning configuration:
- Excluded directories
- Severity and confidence levels
- Specific tests to skip

### `.github/workflows/code-quality.yml`

CI/CD pipeline configuration:
- Runs on push/PR to main branches
- Same checks as local pre-commit
- Fails build on quality issues

## Common Scenarios

### First-Time Setup with Existing Code

When installing pre-commit on existing codebase with quality issues:

```bash
# 1. Install hooks
bash scripts/install-pre-commit-hooks.sh

# 2. Initial run will likely find issues
# Output shows what needs fixing

# 3. Auto-fix most issues
black --line-length=88 backend/ src/
isort --profile=black --line-length=88 backend/ src/
autoflake --in-place --recursive --remove-all-unused-imports --remove-unused-variables backend/ src/

# 4. Fix remaining issues manually (follow flake8 error messages)

# 5. Verify all checks pass
pre-commit run --all-files

# 6. Commit the fixes
git add .
git commit -m "chore: apply code quality fixes for pre-commit enforcement"
```

### Updating Pre-Commit Hooks

Update to latest versions of hooks:

```bash
# Update hook versions
pre-commit autoupdate

# Test updated hooks
pre-commit run --all-files

# Commit updated config
git add .pre-commit-config.yaml
git commit -m "chore: update pre-commit hooks"
```

### Fixing Specific Issues

**Formatting issues (Black)**:
```bash
black --line-length=88 path/to/file.py
```

**Import sorting issues (isort)**:
```bash
isort --profile=black path/to/file.py
```

**Unused imports/variables (autoflake)**:
```bash
autoflake --in-place --remove-all-unused-imports --remove-unused-variables path/to/file.py
```

**Linting errors (flake8)**:
- Read error message carefully
- Fix manually based on flake8 guidance
- Common errors:
  - E501: Line too long (break into multiple lines)
  - F401: Unused import (remove it)
  - E402: Import not at top (move imports up)

**Security issues (bandit)**:
- Review security warning
- If false positive, add to `.bandit` skip list
- If real issue, fix the security vulnerability

## Integration with Development Workflow

### Daily Development

1. Write code normally
2. `git add` files as usual
3. `git commit` - hooks run automatically
4. If hooks pass, commit succeeds
5. If hooks fail, fix issues and commit again

### Pull Requests

1. Create PR normally
2. GitHub Actions runs code quality checks
3. PR shows check status (✅ passed or ❌ failed)
4. Fix any issues if checks fail
5. Merge only after all checks pass

## Obsolete Scripts (Now Automated)

The following manual fix scripts are **no longer needed** and have been archived:

**Archived to `archive/scripts-code-quality-fixes-2025-10-09/`**:
- `scripts/fix_critical_flake8.py` → Replaced by pre-commit flake8
- `scripts/fix_unused_imports.py` → Replaced by autoflake hook
- `scripts/fix_whitespace.py` → Replaced by trailing-whitespace hook
- `scripts/fix_long_lines.py` → Replaced by Black formatter
- `scripts/fix-files-formatting.sh` → Replaced by Black + isort + flake8
- `scripts/utilities/fix_bare_excepts.py` → Caught by flake8
- `scripts/utilities/fix_code_quality.py` → Replaced by combined hooks
- `scripts/utilities/fix_specific_issues.py` → Caught by flake8 + bandit
- `scripts/analysis/fix_linting.py` → Replaced by pre-commit flake8

**Do not use these archived scripts** - use pre-commit instead.

## Troubleshooting

### "pre-commit not found"

```bash
pip install pre-commit
pre-commit install
```

### "Hooks don't run on commit"

```bash
# Reinstall hooks
pre-commit install

# Verify installation
ls -la .git/hooks/pre-commit
```

### "Too many errors, can't fix them all"

Focus on auto-fixable ones first:

```bash
# Auto-fix formatting and imports
black --line-length=88 backend/ src/
isort --profile=black backend/ src/
autoflake --in-place --recursive --remove-all-unused-imports backend/ src/

# Then handle remaining flake8 errors one by one
pre-commit run flake8 --all-files
```

### "Hook is slow"

First run is slow because it installs hook environments. Subsequent runs are fast (< 5 seconds).

To speed up:
```bash
# Cache is in ~/.cache/pre-commit/
# Delete cache to free space (will reinstall on next run)
pre-commit clean
```

### "Need to commit without running hooks"

Use `--no-verify` sparingly:

```bash
git commit --no-verify -m "WIP: work in progress"
```

Remember: This will cause CI/CD to fail.

## Best Practices

1. **Run pre-commit before pushing** - Catch issues locally
2. **Fix issues incrementally** - Don't accumulate quality debt
3. **Don't skip hooks habitually** - They prevent bugs
4. **Update hooks regularly** - `pre-commit autoupdate`
5. **Configure IDE integration** - Many IDEs support Black, isort, flake8

## IDE Integration

### VS Code

Install extensions:
- Python (Microsoft)
- Black Formatter
- isort
- Pylance

Configure in `.vscode/settings.json`:
```json
{
  "python.formatting.provider": "black",
  "python.formatting.blackArgs": ["--line-length=88"],
  "python.linting.enabled": true,
  "python.linting.flake8Enabled": true,
  "editor.formatOnSave": true,
  "python.sortImports.args": ["--profile=black"]
}
```

### PyCharm

1. Settings → Tools → Black → Enable
2. Settings → Tools → isort → Enable
3. Settings → Tools → External Tools → Add flake8
4. Settings → Tools → Actions on Save → Reformat code

## Support

For issues with code quality enforcement:

1. Check this documentation
2. Review pre-commit documentation: https://pre-commit.com
3. Check tool-specific docs (Black, isort, flake8, bandit)
4. Open issue in AutoBot repository

## Migration Notes

**For developers upgrading from manual fix scripts**:

1. Install pre-commit hooks: `bash scripts/install-pre-commit-hooks.sh`
2. Run initial fix: `pre-commit run --all-files`
3. Fix any remaining issues manually
4. Commit: `git commit -m "chore: enable automated code quality"`
5. **Delete bookmarks/aliases** for old fix scripts - they're obsolete

**Benefits of automated enforcement**:
- ✅ Consistent code style across entire codebase
- ✅ Catch errors before commit (not after push)
- ✅ No need to remember to run fix scripts
- ✅ Enforced in CI/CD for all contributors
- ✅ Faster code reviews (no style discussions)
