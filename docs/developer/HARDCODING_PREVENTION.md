# Hardcoding Prevention Guide

**Status**: Automated enforcement via pre-commit hooks

This guide provides detailed implementation instructions for the **NO HARDCODED VALUES** policy.

> **MANDATORY RULE**: NO HARDCODED VALUES - USE SSOT CONFIG

---

## What Constitutes Hardcoding

The following values must NEVER be hardcoded in source files:

| Type | Examples | Correct Alternative |
|------|----------|---------------------|
| **IP Addresses** | `"<backend-ip>"`, `"192.168.1.100"` | `config.backend.host` (Python) or SSOT env vars |
| **Port Numbers** | `8001`, `6379`, `5173` | `config.backend.port` (Python) or SSOT env vars |
| **LLM Model Names** | `"qwen3.5:9b"`, `"mistral:7b-instruct"` | `config.llm.default_model` or `AUTOBOT_DEFAULT_LLM_MODEL` |
| **URLs** | `"http://example.com/api"` | `getBackendUrl()` (TypeScript) or SSOT config |
| **API Keys/Secrets** | `"sk-abc123..."`, `"password123"` | Environment variables (NEVER commit) |

> See also: [SSOT_CONFIG_GUIDE.md](SSOT_CONFIG_GUIDE.md) for complete configuration patterns

---

## Automated Detection

### Pre-Commit Hook

The pre-commit hook (`autobot-infrastructure/shared/scripts/hooks/pre-commit-hardcoded-values`) scans staged files before every commit and runs again on every PR via the `code-quality` GitHub Actions workflow. The local hook and the CI step share the same script and allowlist, so a violation that's blocked locally can't be bypassed by skipping pre-commit (`--no-verify`).

```bash
# Local: runs automatically on git commit (configured in .pre-commit-config.yaml)
git commit ...

# CI: runs as the "Block hardcoded value regressions" step
# in .github/workflows/code-quality.yml — uses pipeline-scripts/check-hardcoded-values-pr.sh
# which calls the same hook in argv mode against changed files.
```

**Run the same check locally** before pushing:

```bash
GITHUB_BASE_REF=Dev_new_gui bash pipeline-scripts/check-hardcoded-values-pr.sh
```

**What it blocks** (by category, see hook source for full patterns):

<!-- fleet-addressing-exempt: states the address range this hook detects; the range is the rule -->

- Hardcoded VM IPs (`172.16.168.19-25`)
- Hardcoded infrastructure ports in URL context
- Magic numbers that should use constants from `threshold_constants.py`
- Hardcoded role / category strings
- Hardcoded AutoBot file paths
- Hardcoded LLM model name literals
- Hardcoded database DSNs
- Hardcoded timeouts

**What it allows** (intentional, see `pre-commit-hardcoded-values_test.py` for the locked-in rules):

- `ssot_config.py` / `ssot-config.ts` (these IS the SSOT — IPs ARE the source of truth there)
- `network_constants.py`, `path_constants.py`, `security_constants.py`, `threshold_constants.py`
- Anything under `constants/`, `config.py`, or `.env*`
- Test files (`test_*.py`, `*_test.py`, `*.test.ts`, `*.spec.ts`) — fixtures legitimately use literal IPs
- Any file under `repo_tests/` (#15273) — that directory is test-support code by construction, so a non-test-named helper module living there (e.g. one holding fixture constants shared by several `*_test.py` siblings) gets the same exemption on the strength of its DIRECTORY rather than its filename. The same file outside `repo_tests/` is still scanned.
- Lines containing `config.`, `getenv`, `CONFIG[`, or `AUTOBOT_` (already routed through SSOT)
- Comments (any line starting with `#` / `//` / ` *`)
- File types other than `.py` / `.ts` / `.vue` (YAML, JSON, etc. are not scanned at all — Ansible inventories are explicitly out of scope). Markdown is not scanned by *this* hook; since #15208 `docs/**/*.md` is gated by `tools/lint/check_docs_no_fleet_addressing.py`, which looks for fleet node addresses only and reads its pattern from the same `HV_VM_IP` rule this hook uses.
- `192.168.x.x` and `127.0.0.x` literals (RFC 1918 example space and loopback — used in SSRF guards, network-tooling examples, test fixtures, i18n placeholders)

<!-- fleet-addressing-exempt: quotes the exact call the hook's `getenv` filter lets through, which is the false negative being described -->

**Known limitation (tracked in #6725 follow-up):** the hook's line filter currently skips any line containing the substring `getenv`, so a literal IP fallback inside `os.getenv("AUTOBOT_REDIS_HOST", "172.16.168.23")` is *not* flagged. This is the false-negative an AST-aware Python rewrite would close. The locked-in test `test_allows_code_using_ssot_config` documents this behavior so any future tightening has a clear regression target.

**When violations are found**:

- Commit (or PR) is blocked
- Violation report shows file, line number, value, and the SSOT alternative
- Fix the violation, re-stage, re-commit (or push the fix)

### Frontend ESLint rule (Issue #6784)

`autobot-frontend/eslint.config.ts` includes a `no-restricted-syntax` rule that blocks hardcoded VM IPs in `.ts` / `.mts` / `.tsx` / `.vue` files. Two selectors:

- `Literal[value=/^(https?:\/\/)?172\.16\.168\.\d+/]` — bare IP literals or HTTP(S) URLs containing them
- `TemplateElement[value.cooked=/172\.16\.168\.\d+/]` — IP inside a template literal

<!-- fleet-addressing-exempt: quotes the literals the ESLint selectors above match; a counter-example without them demonstrates nothing -->

Catches:
- `const x = '172.16.168.20'`
- `const x = 'http://172.16.168.21:5173'`
- `const x = vmHost ?? 'http://172.16.168.20:8001'` (the original `||`/`??` fallback anti-pattern)
- `` const x = `ws://172.16.168.21:5173/ws` ``

Doesn't trigger on:
- `127.0.0.1` (loopback — single-host install default)
- `192.168.x.x` (RFC 1918 example space — used in tests, SSRF guards, i18n placeholders)
- IPs in `.json` locale files, generated types (not in lint scope). Markdown under `docs/` is gated separately by `tools/lint/check_docs_no_fleet_addressing.py` (#15208).

Test fixtures live in `autobot-frontend/eslint-tests/` (excluded from production lint by design — see `eslint-tests/README.md`).

### Documentation fleet-addressing guard (Issue #15208)

`tools/lint/check_docs_no_fleet_addressing.py` gates `docs/**/*.md`, which none of the
detectors above reach: `HV_SCAN_EXTENSIONS` in `scripts/lib/hardcoded-value-rules.sh` is
`py|ts|vue|js|sh|yml|yaml`, and Markdown is not in it. #3315 redacted
`docs/architecture/` by hand; with nothing watching, the same addressing survived in
`docs/archives/plans/` until #15208.

It carries no copy of the range. It parses the `HV_VM_IP` assignment out of
`scripts/lib/hardcoded-value-rules.sh`, so code and documentation share one definition of
"a fleet address" and a renumbered fleet updates both at once. A missing or unparseable
rule set aborts the run rather than reporting clean.

```bash
# Sweep every Markdown file under docs/
python3 tools/lint/check_docs_no_fleet_addressing.py --audit

# Check specific files (the pre-commit entry point takes argv)
python3 tools/lint/check_docs_no_fleet_addressing.py docs/runbooks/CODE_UPDATE.md
```

Replace a finding with the role placeholder for its node — see
[VM_ROLES.md](../architecture/VM_ROLES.md) — matching the form #3315 established
(`<backend-ip>`, `<database-ip>`, `<network-subnet>`, and so on).

**Deliberate counter-examples** are exempted by a Markdown comment introducing the block
that needs it, not by a filename in a list:

```markdown
<!-- fleet-addressing-exempt: why this block must keep the literal -->

- the block the marker introduces
```

`fleet-addressing-exempt-file` exempts a whole document. Either marker is a finding when
the text it covers carries no address, so an exemption cannot outlive its reason. This
page uses three block markers, for the sections that document the detection patterns
themselves.

The audit reports how many files it reached and fails below a floor, because a sweep
whose glob stops matching reports "no offenders" over nothing at all — which is exactly
how the gap #15208 names went unnoticed for months.


### Generic CI wrapper for any pre-commit hook (Issue #6785)

`pipeline-scripts/check-pre-commit-hook-pr.sh <hook-name>` runs any pre-commit hook in argv mode against the PR's changed files. Hooks that support argv mode today:

- `pre-commit-hardcoded-values` (#6725) — wrapped by `check-hardcoded-values-pr.sh`
- `pre-commit-no-direct-redis` (#1086, argv mode added in #6785)
- `pre-commit-no-print-console` (#1082, argv mode added in #6785)

To add a new hook to CI:

1. Add argv mode to the hook (positional args = files to scan, no args = `git diff --cached`).
2. Add a step in `.github/workflows/code-quality.yml`:

   ```yaml
   - name: Block <thing> regressions (#issue)
     run: bash pipeline-scripts/check-pre-commit-hook-pr.sh <hook-name>
   ```

3. Optionally add a test class in `pipeline-scripts/check-pre-commit-hook-pr_test.py` for end-to-end coverage.

### Manual Scan

Run the detection script manually to audit the entire codebase:

```bash
# Scan the whole tree; one-line summary
./pipeline-scripts/detect-hardcoded-values.sh

# Detailed report, including the known-backlog count
./pipeline-scripts/detect-hardcoded-values.sh --report | less

# Machine-readable, as ssot-coverage.yml consumes it
./pipeline-scripts/detect-hardcoded-values.sh --json

# Fail if a baseline entry no longer matches anything
./pipeline-scripts/detect-hardcoded-values.sh --audit-baseline

# Scan a specific file list (the staged-files entry point takes argv)
bash autobot-infrastructure/shared/scripts/hooks/pre-commit-hardcoded-values autobot-backend/api/chat.py
```

### Where the rules live (#14371)

There is **one** rule set, in `scripts/lib/hardcoded-value-rules.sh`. Two thin
entry points read it:

| Entry point | Scope | On a violation |
|---|---|---|
| `pipeline-scripts/detect-hardcoded-values.sh` | a tree | always exits 0 on a completed scan; the verdict travels in the JSON `status` field, which `ssot-coverage.yml` enforces as-is. A non-zero exit means the scan did not finish, and that also fails the job |
| `autobot-infrastructure/shared/scripts/hooks/pre-commit-hardcoded-values` | staged files, or an explicit argv list from CI | exits 1 — this is the one that stops a commit |

They differ only in where the lines come from and what they do with the
verdict. Adding a rule means adding it to the library, once, and both entry
points pick it up.

`pipeline-scripts/hardcoded_values_baseline.txt` records the findings that
already existed when the three former detectors were merged. It only ever
shrinks: a finding that is not in it fails the build, and every run prints how
many baselined findings it suppressed.

### What blocks a build (#14914)

**Severity decides, not class.** Every `VIOLATION` blocks — both the `ssot`
class and the `other` class, and this is now true at *both* entry points. The
pre-commit hook has always counted `^VIOLATION|` class-agnostically and exited
1; the tree scan keyed its verdict on `ssot_violations` alone. The same finding,
from the same rule in the same library, blocked a commit and passed CI — the
commit-time gate was stricter than the merge-time one, which is backwards, since
the local one is the one a developer can skip. The two classes differ in what the fix *looks
like*: an `ssot` finding names the exact config key that replaces the value, an
`other` finding names the family. They do not differ in whether the value
belongs in the source, so they do not differ in whether they block.

`WARNING` is the advisory severity and does not block. There is exactly one
today — `offset=0` — and it is advisory because the shape is too common to gate
on, not because of the class it happens to carry. Warnings are counted
separately and are not part of `total_violations`.

So: **an advisory rule emits `WARNING` from the rule itself.** Do not park a
rule outside the gate by choosing a class the verdict does not read — that was
the #14914 defect. Eight of the twelve emit sites (paths, DSNs, URLs, accounts,
roles, categories, timeouts, magic numbers) were detected, counted, JSON-encoded
and printed while the verdict read `ssot_violations` alone, so nine hardcoded
`/opt/autobot` paths sat on the merged base under a green check.

### "STALE baseline entry" — what to do (#14912)

If `ssot-coverage` fails with `N baseline entr(ies) … no longer match anything`,
you have almost certainly just **fixed or moved** a hardcoded value. That is the
outcome the guard wants; the baseline simply still lists it. Recover with one
command:

```bash
./pipeline-scripts/detect-hardcoded-values.sh --prune-baseline
```

then commit the changed baseline alongside your fix.

`--prune-baseline` **only ever removes**. It cannot add a key or raise a count,
by construction: it iterates the keys already in the baseline and writes
`min(baseline_count, found_count)`. So it cannot be used to silence a new
finding — that direction is blocked independently by
`pipeline-scripts/check_baseline_no_growth.sh`, which fails on any new key or
increased count.

It also refuses to run when the scan found **nothing**. An empty result and a
broken detector are indistinguishable, and this is the one path that rewrites
the record, so it will not turn a failed scan into an emptied baseline.

Why the audit blocks rather than warns: an entry naming a path that has moved
exempts nothing today, but silently re-permits the value the moment that path
comes back.

### Adding a baseline entry (#14919)

There is exactly one route, and it does not exist for the case the guard was
built to stop. An entry may be **added** only when both hold:

1. **The file is byte-identical to the base ref.** A detection-rule change that
   suddenly matches code which was already in the tree is a legitimate
   addition — nothing in your change wrote that value. A file your change
   *touches* is the bypass itself (hardcode a value, append its key in the same
   commit) and has **no override at all**: not an env var, not a label, not a
   marker. The two cases are separated by the diff, not by permission.
2. **This change adds a written justification directly above the entry**, of the
   form:

   ```
   # reviewed: #<issue> why this cannot be fixed at the source
   1|ssot|path/to/file.py|value
   ```

   It must be a *new* line in your diff. A justification already in the file
   covers the entry it was written for, not a later append that happens to sit
   under it.

The justification is a preceding **comment**, never a suffix on the entry: the
key is everything after the first `|`, so a trailing `# reviewed: …` would
change the key until it matched no finding at all.

An entry naming a **symlink** is refused. A symlink's content is the target
path, so "byte-identical to the base ref" stays true however much the file it
points at was rewritten — and the detector never attributes a finding to a
symlink path anyway, because its tree walk does not follow them. Baseline the
real path.

An entry whose key does not carry **exactly two** `|` separators is refused
outright rather than parsed. `|` is a legal byte in a filename and the record
format does not escape it, so a crafted path can make the file field resolve to
an unrelated, untouched decoy — which was a working bypass of this route until
the check was added.

Every permitted addition is printed in full and annotated on the run
(`::warning::`), so growth is loud rather than silent. A **rename** of a file
carrying a baselined value is deliberately not covered — the new path is absent
at the base ref, so the addition is refused, and loosening that to "the content
existed somewhere at base" would also admit a verbatim copy.

---

## ConfigRegistry Fallback Pattern (Issue #2671)

`registry_defaults.py` now sources all default values from `autobot_shared.ssot_config` at import time. This means `ConfigRegistry.get()` callers **no longer need hardcoded fallbacks** -- the registry defaults tier provides SSOT-sourced values automatically.

```python
# GOOD -- no hardcoded fallback needed
redis_host = ConfigRegistry.get("vm.redis")
npu_port = ConfigRegistry.get("port.npu")

# BAD -- redundant hardcoded fallback (will trigger detection script)
redis_host = ConfigRegistry.get("vm.redis", "<database-ip>")
```

For model names and embedding models, use the SSOT constants:

```python
from autobot_shared.ssot_config import DEFAULT_LLM_MODEL, DEFAULT_EMBEDDING_MODEL

# GOOD
model = DEFAULT_LLM_MODEL
embedding = DEFAULT_EMBEDDING_MODEL

# BAD
model = "qwen3.5:9b"
embedding = "nomic-embed-text:latest"
```

---

## How to Fix Violations

### 1. For IP Addresses and Port Numbers

**Use the SSOT config (Python)**:

```python
# BAD - Hardcoded values
url = "https://<backend-ip>:8443/api/chat"
redis_host = "<database-ip>"
redis_port = 6379

# GOOD - Use SSOT config
from autobot_shared.ssot_config import config

url = config.backend.url + "/api/chat"
redis_host = config.redis.host
redis_port = config.redis.port
```

**Use the SSOT config (TypeScript)**:

```typescript
// BAD - Hardcoded values
const url = "https://<backend-ip>:8443/api/chat"

// GOOD - Use SSOT config
import { getBackendUrl } from '@/config/ssot-config'

const url = getBackendUrl() + "/api/chat"
```

**Use SSOT in Shell Scripts**:

```bash
# Load .env at script start
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# BAD - Hardcoded
BACKEND_HOST="<backend-ip>"

# GOOD - SSOT env var with fallback
BACKEND_HOST="${AUTOBOT_BACKEND_HOST:-<backend-ip>}"
```

### 2. For LLM Model Names

**Use SSOT config**:

```python
# BAD - Hardcoded model name
model = "qwen3.5:9b"

# GOOD - Use SSOT config
from autobot_shared.ssot_config import config
model = config.llm.default_model
```

**Environment variable**: Set in `.env` file:

```bash
AUTOBOT_DEFAULT_LLM_MODEL=qwen3.5:9b
```

### 3. For Other Values (URLs, API Keys, etc.)

**Use environment variables via SSOT**:

**Step 1**: Add to `.env` file (never commit this file):

```bash
AUTOBOT_API_BASE_URL=http://api.example.com
AUTOBOT_API_KEY=sk-abc123...
AUTOBOT_CUSTOM_SETTING=value
```

**Step 2**: Read via SSOT config or env vars:

```python
# BAD - Hardcoded URL
api_url = "http://api.example.com"

# GOOD - Use SSOT config for standard values
from autobot_shared.ssot_config import config
backend_url = config.backend.url

# GOOD - Use os.getenv for custom values
import os
api_key = os.getenv("AUTOBOT_API_KEY")  # NEVER hardcode secrets!
```

**Step 3**: Document in `.env.example`:

```bash
# API Configuration
AUTOBOT_API_BASE_URL=http://api.example.com
AUTOBOT_API_KEY=your-api-key-here
```

---

## Override (Emergency Only)

**When hardcoding is ABSOLUTELY necessary** (extremely rare cases):

### Prerequisites

1. **Document WHY** in code comments
2. **Add entry** to `.hardcode-exceptions` file
3. **Get approval** in code review

### Exception File Format

Create/edit `.hardcode-exceptions` in repository root:

```text
# Hardcoding Exceptions
# Format: file_path:line_number:reason

autobot-backend/utils/legacy_module.py:45:Legacy API requires hardcoded endpoint
infrastructure/shared/tests/integration/test_fixtures.py:120:Test fixture needs static IP
```

### Bypass Pre-Commit Hook

**NOT RECOMMENDED** - Only use if you've added exception:

```bash
# Bypass pre-commit hook (use with extreme caution)
git commit --no-verify -m "Your message"
```

**Warning**: This bypasses ALL pre-commit checks, not just hardcoding detection.

---

## Detection Script Details

### Script Location

```text
source scripts/lib/hardcoded-value-rules.sh          the rules — SOURCED by both
                                                     entry points, never executed,
                                                     so it is tracked mode 644
./pipeline-scripts/detect-hardcoded-values.sh        tree-scan entry point (755)
bash autobot-infrastructure/shared/scripts/hooks/pre-commit-hardcoded-values
                                                     staged-files entry point (755)
pipeline-scripts/hardcoded_values_baseline.txt       the measured backlog
```

### What It Detects

**IP Address Patterns**:

- IPv4: `<backend-ip>`, `192.168.1.1`, etc.
- IPv6: Full and compressed formats
- Excludes: Comments, documentation, test files

**Port Numbers**:

- Common service ports: 8001, 6379, 5173, etc.
- Excludes: Commented code, examples

**LLM Model Names**:

- Ollama models: `qwen3.5:9b`, `mistral:7b-instruct`, `gemma2:2b`, `llama3.2:1b`
- OpenAI models: `gpt-4`, `gpt-3.5-turbo`
- Anthropic models: `claude-3-opus`

**URLs and Secrets**:

- HTTP/HTTPS URLs
- Potential API keys (pattern matching)
- Tokens and credentials

### Exclusions

The script automatically excludes:

- `.env` files (intended for configuration)
- `.env.example` files (documentation)
- `network_constants.py` (canonical source of truth)
- Documentation files (`.md`)
- Test fixtures (when marked as such)
- Comments and docstrings

---

## Pre-Commit Hook Setup

### Installation

The hook is automatically installed via:

```bash
bash infrastructure/shared/scripts/install-pre-commit-hooks.sh
```

### Manual Installation

If needed, install manually:

```bash
# Nothing to install by hand: the hook is registered in .pre-commit-config.yaml
# as `detect-hardcoded-values` and runs on every commit once `pre-commit
# install` has been run. To invoke it directly against what is staged:
bash autobot-infrastructure/shared/scripts/hooks/pre-commit-hardcoded-values
if [ $? -ne 0 ]; then
    echo "Hardcoded values detected. Fix violations before committing."
    exit 1
fi
EOF

chmod +x .git/hooks/pre-commit-hardcode-check
```

### Hook Location

```text
.git/hooks/pre-commit-hardcode-check
```

---

## Best Practices

### 1. Check Before You Code

- Know the proper pattern before writing code
- Use SSOT `config` for IPs/ports/URLs
- Use `config.llm.default_model` for models
- Use `.env` for custom values

### 2. Run Manual Scans

```bash
# Before starting work
./pipeline-scripts/detect-hardcoded-values.sh

# After making changes, against just what you staged
bash autobot-infrastructure/shared/scripts/hooks/pre-commit-hardcoded-values
```

### 3. Keep .env.example Updated

When adding new environment variables:

```bash
# Add to .env (local only)
AUTOBOT_NEW_FEATURE=value

# Document in .env.example (committed)
AUTOBOT_NEW_FEATURE=example-value
```

### 4. Review Before Committing

- Pre-commit hook runs automatically
- Fix violations immediately
- Don't use `--no-verify` unless absolutely necessary

---

## Troubleshooting

### False Positives

**Issue**: Script flags legitimate code

**Solution 1**: Add comment to clarify

```python
# This is a test fixture, not production code
test_ip = "127.0.0.1"  # Test only
```

**Solution 2**: Add to `.hardcode-exceptions`

```text
infrastructure/shared/tests/fixtures/network_mock.py:45:Test fixture requires static IP
```

### Pre-Commit Hook Not Running

**Issue**: Hook doesn't run on `git commit`

**Solution**:

```bash
# Reinstall hooks
bash infrastructure/shared/scripts/install-pre-commit-hooks.sh

# Verify hook exists and is executable
ls -la .git/hooks/pre-commit-hardcode-check
chmod +x .git/hooks/pre-commit-hardcode-check
```

### Need to Commit Urgently

**Issue**: Need to commit despite violations (emergency)

**Solution**:

1. Document the violation in code comments
2. Create GitHub issue to fix it
3. Add to `.hardcode-exceptions`
4. Use `--no-verify` (last resort)

```bash
# Emergency commit (not recommended)
git commit --no-verify -m "Emergency fix - see issue #123"
```

---

## Related Documentation

- **SSOT Config Guide**: [SSOT_CONFIG_GUIDE.md](SSOT_CONFIG_GUIDE.md) - Complete SSOT configuration patterns
- **Migration Checklist**: [CONFIG_MIGRATION_CHECKLIST.md](CONFIG_MIGRATION_CHECKLIST.md) - Migrating code to SSOT
- **SSOT Architecture**: [../architecture/SSOT_CONFIGURATION_ARCHITECTURE.md](../architecture/SSOT_CONFIGURATION_ARCHITECTURE.md)
- **Python SSOT Config**: `autobot_shared/ssot_config.py`
- **TypeScript SSOT Config**: `autobot-frontend/src/config/ssot-config.ts`
- **Environment Setup**: [DEVELOPER_SETUP.md](DEVELOPER_SETUP.md)
- **Code Quality**: [CODE_QUALITY_ENFORCEMENT.md](CODE_QUALITY_ENFORCEMENT.md)

---

## Summary Checklist

**Before committing**:

- [ ] No hardcoded IP addresses (use SSOT `config.*.host`)
- [ ] No hardcoded port numbers (use SSOT `config.*.port`)
- [ ] No hardcoded model names (use `config.llm.default_model`)
- [ ] No hardcoded URLs (use `getBackendUrl()` or SSOT config)
- [ ] No hardcoded secrets (use environment variables)
- [ ] Pre-commit hook passes
- [ ] `.env.example` updated (if new variables added)

**If you must hardcode** (rare):

- [ ] Documented WHY in code comments
- [ ] Added to `.hardcode-exceptions` file
- [ ] Got approval in code review
- [ ] Created issue to remove hardcoding later

---
