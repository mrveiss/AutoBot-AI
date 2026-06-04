# Claims Audit - Report Generator & Issue Filer

This directory contains the report generation and issue filing components of the claims-audit pipeline.

## Components

### Phase 3: `generate-report.py` — Report Generator

Generates human-readable `docs/verification.md` from `docs/verification-inventory.json`.

**Usage:**
```bash
# Generate from default paths
python3 .claude/skills/claims-audit/generate-report.py

# Custom paths
python3 .claude/skills/claims-audit/generate-report.py \
  --inventory path/to/inventory.json \
  --output path/to/verification.md
```

**Output Format:**
- Header with auto-generated notice, last verified date, source issue link
- Summary table with claim counts and percentages by status
- Category sections (Infrastructure, API, Features, Architecture)
- Discovery issue links for broken claims
- Footer with regeneration instructions

**Features:**
- ✅ Categorization by infrastructure/api/features/architecture
- ✅ GitHub permalinks to exact code locations
- ✅ Summary percentages and distribution
- ✅ Multiple evidence types (endpoint, service, test, implementation)
- ✅ Discovery issue links
- ✅ Clean markdown tables

### Phase 4: `file_issues.py` — Issue Filer

Files discovery issues for broken claims found during verification.

**Usage:**
```bash
# File issues for all unfiled broken claims
python3 .claude/skills/claims-audit/file_issues.py

# Dry run to see what would be filed
python3 .claude/skills/claims-audit/file_issues.py --dry-run

# Use custom inventory path
python3 .claude/skills/claims-audit/file_issues.py --inventory-path /path/to/inventory.json
```

**Features:**
- Loads verification inventory from `docs/verification-inventory.json`
- For each claim with `status: "broken"` and no `discovery_issue` field:
  - Checks GitHub for duplicate issues
  - Files a new discovery issue with structured body
  - Updates inventory with the filed issue URL
- Skips claims that already have discovery issues filed
- Provides summary of filed issues

**Issue Format:**
```markdown
## Finding
**Capability:** <capability name>
**Claim source:** [file:line](link)
**Status:** ❌ broken

## Evidence
<evidence found or "No evidence found">

## Details
<notes from verification>

## Impact
<description of user impact>

## Suggested Fix
<concrete steps to resolve>

## Related
- Verification report
- Verification inventory
- Parent issue #7359
```

**Duplicate Detection:**
Before filing, searches GitHub for existing issues with "discovery" + capability name in title.

## Integration with Claims Audit

Full claims-audit workflow:

1. **Phase 1** (MVA-2720) - Extract claims from docs
2. **Phase 2** (MVA-2721) - Verify claims against codebase
3. **Phase 3** (this dir, `generate-report.py`) - Generate verification report and inventory
4. **Phase 4** (this dir, `file_issues.py`) - File discovery issues for broken claims

## Testing

Run unit tests:
```bash
python3 -m pytest .claude/skills/claims-audit/test_file_issues.py -v
```

**Test coverage:**
- Inventory loading and saving
- Duplicate issue checking
- Issue body generation
- Broken claim processing
- Skipping already-filed and wired claims
