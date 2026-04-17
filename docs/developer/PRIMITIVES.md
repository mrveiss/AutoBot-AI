# AutoBot Task Primitives

Small, single-purpose, reusable helpers. Every new extraction adds a row here.
See #5060 for the extraction-first methodology.

| Primitive | Module | Signature | Consumers | Issue |
|-----------|--------|-----------|-----------|-------|
| `bounded_gather` | `autobot-backend/orchestration/primitives/concurrency.py` | `bounded_gather(coros, max_parallel, *, return_exceptions=True)` | `Orchestrator._execute_agents_in_parallel`, `SubagentDispatcher.spawn_parallel_tasks` | #5059 |
