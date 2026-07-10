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

## LLM-judge quality assertions (#11521)

`llm_judge_fixture.py` exposes the `llm_judge` pytest fixture, which wraps the
existing `judges/` framework to let tests assert LLM output quality.

### Quickstart

```python
@pytest.mark.llm_judge
async def test_answer_quality(llm_judge) -> None:
    await llm_judge.assert_llm(
        output="Paris is the capital of France.",
        criteria="The answer must be factually correct and relevant.",
        min_score=0.8,
        context="What is the capital of France?",
    )
```

### Opt-in gate

These tests **skip by default** and are never a CI dependency.  To run them
locally against a configured Ollama or cloud provider:

```bash
AUTOBOT_LLM_JUDGE_TESTS=1 python -m pytest autobot-backend/tests/test_llm_judge_example.py -v
```

The fixture also skips when no provider environment variable is set
(`AUTOBOT_OLLAMA_ENDPOINT`, `AUTOBOT_OPENAI_API_KEY`, etc.).

### Minimum score threshold

Override the default 0.7 threshold per call with `min_score=<float>`, or
globally via the `AUTOBOT_LLM_JUDGE_MIN_SCORE` environment variable.

## See also

- Root `autobot-backend/conftest.py` — shared pytest fixtures (auto-discoverable)
- `docs/developer/PRIMITIVES.md` — repo-wide extraction rules
- Issue #5437 — this directory's creation rationale
- Issues #5431, #5432 — first consumers of this directory
- Issue #11521 — llm_judge fixture origin
