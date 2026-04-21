# tests/helpers/

Shared test doubles, fixtures, and stubs for the AutoBot backend test suite.

## When to add a helper here

A helper belongs in this directory when it is reused across **3 or more
test files**. The bar is deliberate:

- **1-2 sites** — keep inline in the test file. Extraction adds indirection
  without removing meaningful duplication.
- **3+ sites** — extract here. Consolidation reduces maintenance cost and
  makes the test fixture conventions discoverable.

This matches the third-occurrence rule from `docs/developer/PRIMITIVES.md`.

## Naming conventions

- `fake_redis.py` — in-memory Redis stubs (sync + async variants)
- `fake_kb.py` — Knowledge Base test doubles
- `llm_fixtures.py` — LLM mock fixtures (if not better placed in root `conftest.py`)
- `<subsystem>_fixtures.py` — domain-specific fixture collections

## Preferred extraction pattern

Each fake class should expose the **minimum** surface needed by its
consumers. Over-generalization is worse than duplication — a helper that
tries to cover every possible consumer's needs becomes its own
maintenance burden.

If two consumers need slightly different shapes, prefer composition over
parameterization:

- Subclass the base fake and override methods per consumer
- Or provide related but distinct classes (`SimpleFakeRedis`, `HashFakeRedis`,
  `FullFakeRedis`) — callers import the one they need

## What doesn't belong here

- Test data builders specific to one module (keep co-located with the test)
- pytest fixtures that are auto-discoverable via `conftest.py` (prefer
  placing fixtures in `conftest.py` unless they require non-trivial setup)
- Production code disguised as a test utility (never)

## See also

- Root `autobot-backend/conftest.py` — shared pytest fixtures (auto-discoverable)
- `docs/developer/PRIMITIVES.md` — repo-wide extraction rules
- Issue #5437 — this directory's creation rationale
- Issues #5431, #5432 — first consumers of this directory
