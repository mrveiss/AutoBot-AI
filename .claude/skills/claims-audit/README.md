# Claims Audit Report Generator

Generates human-readable `docs/verification.md` from `docs/verification-inventory.json`.

## Usage

### Command Line

```bash
# Generate from default paths
python3 .claude/skills/claims-audit/generate-report.py

# Custom paths
python3 .claude/skills/claims-audit/generate-report.py \
  --inventory path/to/inventory.json \
  --output path/to/verification.md
```

### As Module

```python
from generate_report import generate_report, load_inventory

# Load inventory
inventory = load_inventory(Path('docs/verification-inventory.json'))

# Generate report
report = generate_report(inventory)

# Write to file
with open('docs/verification.md', 'w') as f:
    f.write(report)
```

## Output Format

The generated report includes:

1. **Header** - Auto-generated notice, last verified date, source issue link
2. **Summary** - Claim counts and percentages by status
3. **Category Sections** - Claims grouped by:
   - Infrastructure (Docker, Redis, PostgreSQL, Ansible, etc.)
   - API (FastAPI, WebSocket, A2A, etc.)
   - Features (RAG, NPU, Vision, Workflow Builder, etc.)
   - Architecture (Celery, Workers, etc.)
4. **Discovery Issues** - Links to filed issues for broken claims
5. **Footer** - Instructions for regeneration

### Example Summary

```markdown
## Summary

| Status | Count | Percentage |
|--------|-------|------------|
| ✅ wired | 13 | 76.5% |
| ⚠️ partial | 3 | 17.6% |
| ❌ broken | 1 | 5.9% |
| **Total** | **17** | **100.0%** |
```

### Example Claim Entry

```markdown
| 1 | FastAPI REST API | "Backend (FastAPI API server)" | [README.md:188](../README.md#L188) | [implementation](../autobot-backend/main.py#L1), [test](../autobot-backend/tests/) | ✅ wired | 100+ routers registered; smoke-tested by CI |
```

## Features

- ✅ **Categorization** - Automatically groups claims by infrastructure/api/features/architecture
- ✅ **GitHub Permalinks** - File:line citations link to exact code locations
- ✅ **Percentages** - Summary shows distribution of claim statuses
- ✅ **Evidence Formatting** - Multiple evidence types (endpoint, service, test, implementation)
- ✅ **Discovery Issues** - Links to filed GitHub issues for broken claims
- ✅ **Markdown Tables** - Clean, readable format for documentation

## Testing

Run unit tests:

```bash
python3 -m pytest .claude/skills/claims-audit/test_generate_report.py -v
```

All 14 tests should pass:
- Status emoji formatting
- Category inference
- GitHub permalink generation
- Percentage calculation
- Evidence list formatting
- Summary section generation
- Claim grouping
- Complete report generation
- Inventory loading
- Discovery issue handling

## Schema

### Input: `verification-inventory.json`

```json
{
  "meta": {
    "generated_at": "2026-05-26",
    "generated_by": "claims-audit skill",
    "source_issue": "https://github.com/mrveiss/AutoBot-AI/issues/7359",
    "skill_path": ".claude/skills/claims-audit/SKILL.md",
    "schema_version": "1"
  },
  "summary": {
    "total": 17,
    "wired": 13,
    "partial": 3,
    "broken": 1
  },
  "claims": [
    {
      "id": "fastapi-rest-api",
      "capability": "FastAPI REST API",
      "claim": "Backend (FastAPI API server)",
      "source": {
        "file": "README.md",
        "line": 188
      },
      "evidence": [
        {
          "kind": "implementation",
          "file": "autobot-backend/main.py",
          "line": 1
        }
      ],
      "status": "wired",
      "notes": "100+ routers registered",
      "discovery_issue": "https://github.com/..."
    }
  ]
}
```

### Output: `verification.md`

Markdown document with:
- Header (auto-generated notice, metadata)
- Summary table (counts + percentages)
- Category sections (Infrastructure, API, Features, Architecture)
- Discovery issues table
- Footer (regeneration instructions)

## Integration

Called by `/claims-audit` skill after verification phase:

```bash
# Phase 3 in SKILL.md
python3 .claude/skills/claims-audit/generate-report.py \
  --inventory docs/verification-inventory.json \
  --output docs/verification.md
```

## Related

- **Parent Issue**: [MVA-2713](/MVA/issues/MVA-2713)
- **This Implementation**: [MVA-2722](/MVA/issues/MVA-2722)
- **Verification Script**: [MVA-2721](/MVA/issues/MVA-2721)
- **Skill Definition**: [SKILL.md](./SKILL.md)
