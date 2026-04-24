# AutoBot Task Primitives

Small, single-purpose, reusable helpers. Every new extraction adds a row here.
See #5060 for the extraction-first methodology.

| Primitive | Module | Signature | Consumers | Issue |
|-----------|--------|-----------|-----------|-------|
| `bounded_gather` | `autobot-backend/orchestration/primitives/concurrency.py` | `bounded_gather(coros, max_parallel, *, return_exceptions=True)` | `Orchestrator._execute_agents_in_parallel`, `SubagentDispatcher.spawn_parallel_tasks` | #5059 |
| `lazy_singleton` | `autobot_shared/singleton_factory.py` | `lazy_singleton(factory) -> Callable` — double-checked locking; raises `RuntimeError` if called again with **different** args (#5445) | `utils/semantic_chunker.py`, `utils/semantic_chunker_gpu.py`, `utils/semantic_chunker_gpu_optimized.py` | #5423 |
| `async_lazy_singleton` | `autobot_shared/singleton_factory.py` | `async_lazy_singleton(factory) -> Callable[[], Awaitable]` — async double-checked locking; factory may be sync or `async def` | `intelligence/os_detector.py`, `conversation_file_manager.py`, `code_embedding_generator.py`, `npu_integration.py` (×3), `utils/distributed_service_discovery.py` | #5632 |
