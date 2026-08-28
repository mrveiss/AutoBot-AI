# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Performance benchmarks for AutoBot system components
Tests performance characteristics, resource usage, and scalability
"""

import asyncio
import os
import time
from contextvars import ContextVar
from typing import Callable
from unittest.mock import AsyncMock, Mock, patch

import psutil
import pytest

from autobot_shared.env_utils import env_flag, env_float, env_int, env_str
from config.manager import ConfigManager as ConfigManager
from memory import MemoryManager, TaskPriority
from multimodal_processor import (
    ModalityType,
    MultiModalInput,
    MultiModalProcessor,
    ProcessingIntent,
)
from services.config_service import ConfigService

# #13162: every test in this module asserts a wall-clock budget (ms elapsed) or
# an RSS delta — there is not one functional-only test here, and the filename
# already declares it (`*_performance_test.py`). That makes the module a
# benchmark suite, so it belongs to the `performance` selection rather than the
# unit selection, where a millisecond budget measures the CI runner's
# contention instead of the code. No budget in this file was changed.
pytestmark = pytest.mark.performance


# #15055: every budget in this module is expressed in RUNNER-CALIBRATED WORK
# UNITS. None of them compares milliseconds against a hardcoded constant, and
# none of them may be "raised" because a run came close.
#
# A millisecond ceiling measures the runner, not the code. `assert
# processor_startup_time < 500.0` passed on run 32837489748 and failed on
# 32839088246 (547.2ms) and 33154304714 (538.9ms) — the last of those on the
# commit immediately after a green one, whose entire diff was a file that run
# deselects, with this module untouched on that branch. Both overshoots sit
# within 10% of the budget, which is the signature of a constant set near the
# runner's median rather than above its worst case. This selection runs on a
# shared, multi-tenant runner under pytest-xdist, so contention from a
# noisy neighbour and from sibling workers is the normal condition here, not an
# anomaly — and a constant at the median will keep meeting it.
#
# One WORK UNIT is the wall-clock cost of `_reference_workload()` — a fixed,
# deterministic slice of pure-Python work — measured in THIS process, in the
# same moment as the operation under test. Both sides of the comparison see the
# same contention, so a runner that is uniformly 3x slow inflates numerator and
# denominator alike and the ratio holds. This is the move #14930 made for RSS
# (measure the delta the assertion always meant, not the absolute figure the
# process happened to sit at) and the move #13162 made for the cache and
# concurrency checks below (assert the property, not the clock).
#
# What a unit budget still catches: an eager model load, a network call or a
# file read added to a constructor, an O(n^2) traversal, a lock introduced on a
# hot path. Those are order-of-magnitude changes, which is what this module can
# actually detect. A 10% wall-clock regression was never detectable here — the
# noise band was already wider than that, which is exactly why the constants
# fired on runner weather instead.
#
# HOW TO CHANGE A BUDGET. Every site records its measurement on every run, pass
# or fail, by two routes: a `[perf #15055] ...` line on stdout, which pytest
# shows for a FAILING test (and locally under `-s`), and a `perf_work_units`
# property in the junit XML, which is written for PASSING tests too and is
# uploaded by marker-tests.yml as `marker-suite-reports`. The junit route exists
# because this selection runs under `-n auto`, where xdist captures worker
# stdout and a green run would otherwise report nothing — which is how the old
# constants went years without ever being re-derived.
#
# Read the number off a run, then move the budget to sit above the highest
# OBSERVED value with the headroom stated below — never to a round figure chosen
# for comfort, and never upwards because a run came close. A budget that has to
# be relaxed to stay green is reporting a real change in the code's work, and
# that is the finding, not the obstacle.
#
# HOW THESE BUDGETS WERE DERIVED. Five local runs gave a highest-observed value
# per site. Run 33156790797 then measured `Config manager startup` at 1.474
# units on CI against a local high of 0.459 — so ordinary Python work costs
# about 3.2x more units on the CI runner than here, and every local figure is
# converted by that factor before headroom is applied. Headroom on top: 3x for
# sites whose measurement is large and steady (cv of units under ~12% across the
# five runs), 8x for sites measuring single-digit microseconds, where timer
# granularity rather than load sets the spread, with a 0.20-unit floor below
# which the ratio is granularity and nothing else.
#
# THREE SITES ARE FIRST-OBSERVATION CEILINGS, NOT MEASUREMENTS, and are labelled
# as such at the call site: the local interpreter has no torch, so it does not
# execute what CI executes in `Multimodal processor startup` and `Single
# multimodal processing`, and `Memory manager startup` opens SQLite against a
# different filesystem. Read their reported units off a run and ratchet them
# DOWN. That direction is the only permitted one.

_REFERENCE_WORKLOAD_ITERATIONS = 20_000
_REFERENCE_WORKLOAD_SAMPLES = 9

# #15055: the junit sink for the reported measurements. Set per test by the
# autouse fixture below, so `assert_within_work_budget` can record without every
# call site having to thread a fixture through.
_WORK_UNIT_RECORDER: ContextVar[Callable[[str, object], None] | None] = ContextVar(
    "autobot_work_unit_recorder", default=None
)


@pytest.fixture(autouse=True)
def _record_work_units(record_property):
    """#15055: send every measurement to the junit XML, green runs included.

    marker-tests.yml runs this selection with `-n auto`, and xdist captures
    worker stdout, so the printed line below survives only on a FAILING test.
    A budget that can only be re-derived from a red run is a budget nobody
    re-derives -- which is how the millisecond constants stayed at the runner's
    median. `--junitxml` is already passed by that workflow and the file is
    uploaded as `marker-suite-reports`, so this costs nothing to collect.
    """
    token = _WORK_UNIT_RECORDER.set(record_property)
    try:
        yield
    finally:
        _WORK_UNIT_RECORDER.reset(token)


def _reference_workload() -> int:
    """One work unit: a fixed, deterministic slice of pure-Python work.

    Deliberately CPU-bound, allocation-light and dependency-free, so its cost is
    a property of how contended this machine is right now and of nothing else.
    Never change its shape without re-deriving every budget below — the unit is
    the yardstick, and silently rescaling it rescales all of them.
    """
    total = 0
    for i in range(_REFERENCE_WORKLOAD_ITERATIONS):
        total += (i * i) % 7
    return total


def measure_reference_ms() -> float:
    """Cost in milliseconds of one work unit on this runner, right now.

    The MEDIAN of several samples, not the minimum: the denominator has to
    describe the contention the numerator was measured under. A best-of-N
    denominator would describe an idle machine while the numerator described a
    busy one, which is the failure the millisecond constants already had.
    """
    samples = []
    for _ in range(_REFERENCE_WORKLOAD_SAMPLES):
        start = time.perf_counter()
        _reference_workload()
        samples.append((time.perf_counter() - start) * 1000.0)
    samples.sort()
    return samples[len(samples) // 2]


def assert_within_work_budget(elapsed_ms: float, budget_units: float, what: str) -> None:
    """Assert an operation cost fewer than `budget_units` calibrated work units.

    Fails on three distinct conditions, all of them real:

    * the operation exceeded its budget relative to this runner's own speed —
      the regression this module exists to catch;
    * nothing was measured (`elapsed_ms` is zero, negative or not a number), so
      the assertion cannot pass vacuously by timing an operation that never ran
      or by being handed a stub in place of a measurement;
    * the calibration itself measured nothing, which would make the ratio
      meaningless rather than merely generous.
    """
    assert isinstance(elapsed_ms, (int, float)), f"{what}: no measurement was taken (got {elapsed_ms!r})"
    assert elapsed_ms > 0.0, f"{what}: measured {elapsed_ms}ms — the operation under test did not run"

    reference_ms = measure_reference_ms()
    assert reference_ms > 0.0, f"{what}: work-unit calibration measured {reference_ms}ms and cannot be a divisor"

    units = elapsed_ms / reference_ms

    # #15055: report the fine-grained number on every run, pass or fail. The
    # budgets below are ratchets and a ratchet needs observations to be set
    # from -- the millisecond constants were picked once and never re-derived,
    # which is how they ended up at the runner's median. Same reporting habit
    # as performance_benchmarks_test.py.
    report = (
        f"{what}: {units:.3f} work units (budget {budget_units}) " f"= {elapsed_ms:.3f}ms / {reference_ms:.3f}ms unit"
    )
    print(f"[perf #15055] {report}")  # noqa: print
    recorder = _WORK_UNIT_RECORDER.get()
    if recorder is not None:
        recorder("perf_work_units", report)
    assert units < budget_units, (
        f"{what}: {units:.3f} work units, budget {budget_units} "
        f"({elapsed_ms:.3f}ms measured against a {reference_ms:.3f}ms work unit on this runner). "
        f"This is a load-invariant ratio, not a wall-clock ceiling — investigate the code, do not raise it."
    )


class TestSystemPerformanceBenchmarks:
    """Performance benchmarks for system components"""

    def measure_execution_time(self, func, *args, **kwargs):
        """Measure function execution time.

        #15055: `time.perf_counter()`, not `time.time()` — a duration needs the
        monotonic clock. A wall-clock delta can go backwards across an NTP step.
        """
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        return (
            result,
            (end_time - start_time) * 1000,
        )  # Return result and time in milliseconds

    async def measure_async_execution_time(self, coro):
        """Measure async function execution time.

        #15055: monotonic clock, same reason as `measure_execution_time`.
        """
        start_time = time.perf_counter()
        result = await coro
        end_time = time.perf_counter()
        return (
            result,
            (end_time - start_time) * 1000,
        )  # Return result and time in milliseconds

    def measure_memory_usage(self, func, *args, **kwargs):
        """Measure memory usage during function execution"""
        process = psutil.Process()

        # Get initial memory usage
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Execute function
        result = func(*args, **kwargs)

        # Get final memory usage
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_delta = final_memory - initial_memory

        return result, memory_delta

    def test_config_manager_performance(self):
        """Test configuration manager performance"""
        config_manager = ConfigManager()

        # Test single config access performance
        _, access_time = self.measure_execution_time(config_manager.get, "llm.orchestrator_llm")
        assert_within_work_budget(access_time, 0.50, "Config access")

        # Test bulk config access performance
        def bulk_access():
            results = []
            for i in range(100):
                results.append(config_manager.get(f"test.key.{i}", f"default_{i}"))
            return results

        _, bulk_time = self.measure_execution_time(bulk_access)
        assert_within_work_budget(bulk_time, 2.2, "Bulk config access (100 keys)")

        # Test section retrieval performance
        # #13199: the section reader on ConfigManager is get_config_section()
        # (dot-path traversal via get_nested); get_section() belongs to ConfigRegistry.
        _, section_time = self.measure_execution_time(config_manager.get_config_section, "multimodal")
        assert_within_work_budget(section_time, 1.5, "Config section retrieval")

    def test_config_service_caching_performance(self):
        """Test config service caching performance"""
        # #13162: the cached reader is get_full_config() — get_all_settings()
        # has never existed on ConfigService. The cache is class-level, so the
        # benchmark clears it first to guarantee the first call is a real build.
        config_service = ConfigService()
        config_service.clear_cache()

        # First call should be slower (no cache)
        first_config, first_call_time = self.measure_execution_time(config_service.get_full_config)

        # Second call should be faster (cached)
        cached_config, cached_call_time = self.measure_execution_time(config_service.get_full_config)

        # #13162: prove the cache by the property that defines it rather than by
        # racing two wall clocks. The previous `cached < first * 0.5` compared
        # two sub-millisecond samples, so a single scheduler hiccup on the
        # second call inverted the ratio under parallel load. A cache hit hands
        # back the very object it stored; a rebuild produces a fresh dict.
        assert cached_config is first_config, "Second get_full_config() rebuilt the config instead of serving the cache"

        # Cached calls should be very fast
        assert_within_work_budget(cached_call_time, 0.20, "Cached config access")

    @pytest.mark.asyncio
    async def test_multimodal_processor_performance(self):
        """Test multi-modal processor performance"""
        processor = MultiModalProcessor()

        # Test single processing performance
        test_input = MultiModalInput(
            input_id="perf_test_001",
            modality_type=ModalityType.TEXT,
            intent=ProcessingIntent.DECISION_MAKING,
            data="Test processing performance",
        )

        # Mock the context processor for consistent timing
        with patch.object(processor.context_processor, "process", new_callable=AsyncMock) as mock_process:
            mock_process.return_value = Mock(
                success=True,
                confidence=0.8,
                processing_time=0.1,
                result_data={"decision": "test"},
                modality_type=ModalityType.TEXT,
                intent=ProcessingIntent.DECISION_MAKING,
                result_id="test",
            )

            result, processing_time = await self.measure_async_execution_time(processor.process(test_input))

            # First-observation ceiling, not a measurement: this is the one
            # processing benchmark that does NOT mock `_store_result`, so it
            # writes to the shared SQLite memory database, and the local
            # interpreter has no torch. Ratchet it DOWN to the reported units.
            assert_within_work_budget(processing_time, 150.0, "Single multimodal processing")
            assert result.success is True

    @pytest.mark.asyncio
    async def test_concurrent_processing_performance(self):
        """Test concurrent processing performance"""
        processor = MultiModalProcessor()

        # Create multiple test inputs
        inputs = [
            MultiModalInput(
                input_id=f"concurrent_test_{i}",
                modality_type=ModalityType.TEXT,
                intent=ProcessingIntent.DECISION_MAKING,
                data=f"Concurrent test {i}",
            )
            for i in range(10)
        ]

        mock_result = Mock(
            success=True,
            confidence=0.8,
            processing_time=0.05,
            result_data={"decision": "test"},
            modality_type=ModalityType.TEXT,
            intent=ProcessingIntent.DECISION_MAKING,
            result_id="test",
        )

        # #13162: prove concurrency directly instead of inferring it from the
        # clock. The counter records how many calls were inside the modality
        # processor at once; if `process()` ever serialized, the peak would
        # collapse to 1 no matter how fast the run happened to be.
        in_flight = 0
        peak_in_flight = 0

        async def tracked_process(_input_data):
            nonlocal in_flight, peak_in_flight
            in_flight += 1
            peak_in_flight = max(peak_in_flight, in_flight)
            await asyncio.sleep(0)  # yield so siblings can enter
            in_flight -= 1
            return mock_result

        # Mock processors for consistent results. #13162: `_store_result` is
        # also mocked — it writes each result to the shared SQLite memory
        # database, and concurrent writers serialize on that file's lock, so
        # leaving it live made this benchmark measure disk contention rather
        # than the processor's own concurrency. Budgets below are unchanged.
        with (
            patch.object(processor.context_processor, "process", side_effect=tracked_process),
            patch.object(processor, "_store_result", new_callable=AsyncMock),
        ):
            # Process all inputs concurrently
            start_time = time.time()
            tasks = [processor.process(inp) for inp in inputs]
            results = await asyncio.gather(*tasks)
            end_time = time.time()

            total_time = (end_time - start_time) * 1000  # Convert to ms

            # Concurrent processing should be faster than sequential
            assert_within_work_budget(total_time, 30.0, "Concurrent processing (10 inputs)")
            assert peak_in_flight == 10, f"Processing serialized: peak concurrency was {peak_in_flight}, expected 10"
            assert len(results) == 10
            assert all(r.success for r in results)

    def test_memory_manager_performance(self):
        """Test memory manager performance"""
        memory_manager = MemoryManager()

        # Test memory usage during task storage.
        # #13162: MemoryManager has no store_task() and no TaskPriority
        # attribute. Task records are created through create_task_record(),
        # which is synchronous — the asyncio.run() per iteration was spinning up
        # and tearing down 50 event loops purely to call it.  TaskPriority is
        # exported by the memory package.
        def store_multiple_tasks():
            for i in range(50):
                memory_manager.create_task_record(
                    task_name=f"perf_task_{i}",
                    description=f"Performance test task {i}",
                    priority=TaskPriority.MEDIUM,
                    agent_type="performance_test",
                    inputs={"test": f"data_{i}"},
                    metadata={"result": f"success_{i}"},
                )

        _, memory_usage = self.measure_memory_usage(store_multiple_tasks)

        # Memory usage should be reasonable (less than 50MB for 50 tasks)
        assert memory_usage < 50.0, f"Memory usage too high: {memory_usage}MB"

    def test_config_validation_performance(self):
        """Test configuration validation performance"""
        config_manager = ConfigManager()

        # Test validation performance
        _, validation_time = self.measure_execution_time(config_manager.validate_config)

        assert_within_work_budget(validation_time, 0.70, "Config validation")

        # Test multiple validations (should be consistent)
        validation_times = []
        for _ in range(5):
            _, time_taken = self.measure_execution_time(config_manager.validate_config)
            validation_times.append(time_taken)

        avg_validation_time = sum(validation_times) / len(validation_times)
        assert_within_work_budget(avg_validation_time, 0.50, "Config validation (mean of 5)")

    def test_environment_variable_parsing_performance(self):
        """Test environment variable parsing performance"""
        # #13162: ConfigManager._parse_env_value no longer exists — env values
        # are coerced by the canonical autobot_shared.env_utils helpers, which
        # read the variable and apply the type themselves. The benchmark now
        # measures those, one case per coercion the retired helper covered.
        # (Comma-separated values have no canonical list helper; env_str is the
        # current behaviour for them.)
        parse_cases = [
            ("AUTOBOT_BENCH_BOOL_TRUE", "true", lambda name: env_flag(name, False)),
            ("AUTOBOT_BENCH_BOOL_FALSE", "false", lambda name: env_flag(name, True)),
            ("AUTOBOT_BENCH_INT", "12345", lambda name: env_int(name, 0)),
            ("AUTOBOT_BENCH_FLOAT", "3.14159", lambda name: env_float(name, 0.0)),
            ("AUTOBOT_BENCH_LIST", "item1,item2,item3", lambda name: env_str(name, "")),
            ("AUTOBOT_BENCH_STR", "simple_string", lambda name: env_str(name, "")),
        ]

        for name, value, _parse in parse_cases:
            os.environ[name] = value

        try:
            total_parse_time = 0.0
            for name, value, parse in parse_cases:
                _, parse_time = self.measure_execution_time(parse, name)
                total_parse_time += parse_time

                # Each parse should be very fast
                assert_within_work_budget(parse_time, 0.70, f"Environment value parsing of {value!r}")

            # Total parsing time should be minimal
            assert_within_work_budget(total_parse_time, 2.2, "Environment value parsing (all cases)")
        finally:
            for name, _value, _parse in parse_cases:
                os.environ.pop(name, None)

    @pytest.mark.asyncio
    async def test_system_startup_performance(self):
        """Test system component startup performance.

        #15055: each component is constructed ONCE before the clock starts, and
        the budget is measured on a second construction.

        The discarded construction is what makes the number mean "startup".
        `MultiModalProcessor.__init__` calls `_get_torch()`, so the first
        construction in a worker also pays a one-time lazy `import torch` that
        belongs to the interpreter, happens once per process, and lands on
        whichever test happens to construct first — a cost that moves with test
        ordering rather than with this code. The same holds for `ConfigManager`
        and `MemoryManager`, whose first construction primes module-level caches
        and singletons. The second construction is the per-instance cost, which
        is the quantity a "component startup" budget means and the one a
        regression moves: an eager model load, a network call or a file read
        added to `__init__` is paid on EVERY construction, so it lands here.

        MEASURED, and it is not what the old constant assumed. Run 33156790797
        put the WARM construction at 466.351ms — 315.602 work units. So the
        one-time import was only a small part of the old 538.9ms reading: the
        constructor genuinely costs most of that on every instantiation, and the
        500ms constant sat about 7% above the real per-construction cost. A
        budget with 7% of headroom over the true value does not need runner
        weather to be a coin toss, it only needs a little. That is the second
        defect behind the same symptom, and it is why raising the constant would
        have bought one or two green runs and no more.

        The 466ms is itself suspect rather than accepted: #15054 has
        `VisionProcessor`'s CLIP load raising `TypeError` on the pinned
        transformers, so this constructor is timed on an error path. The budget
        below is a ceiling to ratchet DOWN once that lands, not a blessing of
        the current figure.
        """
        # Test config manager startup
        ConfigManager()  # discard: primes module-level caches, not startup cost
        start_time = time.perf_counter()
        config_manager = ConfigManager()
        config_startup_time = (time.perf_counter() - start_time) * 1000

        assert isinstance(config_manager, ConfigManager), "ConfigManager() returned no instance to time"
        assert_within_work_budget(config_startup_time, 8.0, "Config manager startup")

        # Test multimodal processor startup
        MultiModalProcessor()  # discard: pays the one-time lazy `import torch`
        start_time = time.perf_counter()
        processor = MultiModalProcessor()
        processor_startup_time = (time.perf_counter() - start_time) * 1000

        # First-observation ceiling: 315.602 units measured on run 33156790797,
        # on #15054's error path. Ratchet DOWN, never up.
        assert isinstance(processor, MultiModalProcessor), "MultiModalProcessor() returned no instance to time"
        assert_within_work_budget(processor_startup_time, 600.0, "Multimodal processor startup")

        # Test memory manager startup
        MemoryManager()  # discard: primes the shared memory backend
        start_time = time.perf_counter()
        memory_manager = MemoryManager()
        memory_startup_time = (time.perf_counter() - start_time) * 1000

        # First-observation ceiling: no CI reading yet — run 33156790797 failed
        # at the assertion above before reaching this one. Ratchet DOWN once the
        # junit report carries a number for it.
        assert isinstance(memory_manager, MemoryManager), "MemoryManager() returned no instance to time"
        assert_within_work_budget(memory_startup_time, 20.0, "Memory manager startup")

    def test_configuration_file_loading_performance(self):
        """Test configuration file loading performance"""
        import tempfile

        import yaml

        # Create a large test configuration file
        large_config = {
            "section_"
            + str(i): {
                "subsection_" + str(j): {"value_" + str(k): f"data_{i}_{j}_{k}" for k in range(10)} for j in range(10)
            }
            for i in range(20)
        }

        # #13162: ConfigManager takes a config *directory* (config_dir), not a
        # config_file — it loads <config_dir>/config.yaml alongside
        # settings.json. The old NamedTemporaryFile handed it a path it has
        # never accepted, so nothing was ever loaded here.
        with tempfile.TemporaryDirectory(prefix="autobot-config-benchmark-") as config_dir:
            with open(os.path.join(config_dir, "config.yaml"), "w", encoding="utf-8") as f:
                yaml.dump(large_config, f)

            # Test loading performance
            _, load_time = self.measure_execution_time(ConfigManager, config_dir=config_dir)

            assert_within_work_budget(load_time, 1300.0, "Large config file loading")

    def test_statistics_tracking_performance(self):
        """Test performance statistics tracking overhead"""
        processor = MultiModalProcessor()

        # Create mock results for statistics
        mock_results = [
            Mock(
                success=True,
                modality_type=ModalityType.TEXT,
                processing_time=0.1 + (i * 0.01),
            )
            for i in range(100)
        ]

        # Test stats update performance
        start_time = time.time()
        for result in mock_results:
            processor._update_stats(result)
        stats_time = (time.time() - start_time) * 1000

        # Stats tracking should have minimal overhead
        assert_within_work_budget(stats_time, 2.0, "Statistics tracking (100 updates)")

        # Verify stats are correct
        stats = processor.get_stats()
        assert stats["total_processed"] == 100
        assert stats["successful_processed"] == 100
        assert stats["failed_processed"] == 0

    def test_config_get_performance_with_deep_nesting(self):
        """Test configuration access performance with deeply nested keys"""
        config_manager = ConfigManager()

        # Set deeply nested configuration
        config_manager.set("level1.level2.level3.level4.level5.deep_value", "test_data")

        # Test deep access performance
        _, deep_access_time = self.measure_execution_time(
            config_manager.get, "level1.level2.level3.level4.level5.deep_value"
        )

        assert_within_work_budget(deep_access_time, 0.20, "Deep config access")

        # Test bulk deep access
        def bulk_deep_access():
            results = []
            for i in range(50):
                key = f"level1.level2.level3.level4.level5.value_{i}"
                results.append(config_manager.get(key, f"default_{i}"))
            return results

        _, bulk_deep_time = self.measure_execution_time(bulk_deep_access)
        assert_within_work_budget(bulk_deep_time, 1.6, "Bulk deep config access (50 keys)")


class TestScalabilityBenchmarks:
    """Test system scalability characteristics"""

    def test_config_scalability_with_many_keys(self):
        """Test config manager scalability with many configuration keys"""
        config_manager = ConfigManager()

        # Add many configuration keys
        num_keys = 1000
        start_time = time.time()

        for i in range(num_keys):
            config_manager.set(f"scale_test.section_{i // 100}.key_{i}", f"value_{i}")

        set_time = (time.time() - start_time) * 1000

        # Setting 1000 keys should be reasonable
        assert_within_work_budget(set_time, 8.0, f"Setting {num_keys} config keys")

        # Test retrieval performance with many keys
        start_time = time.time()
        for i in range(0, num_keys, 10):  # Test every 10th key
            value = config_manager.get(f"scale_test.section_{i // 100}.key_{i}")
            assert value == f"value_{i}"

        get_time = (time.time() - start_time) * 1000
        assert_within_work_budget(get_time, 2.5, "Reading config keys with many configs loaded")

    @pytest.mark.asyncio
    async def test_multimodal_processor_scalability(self):
        """Test multi-modal processor scalability with many concurrent requests"""
        processor = MultiModalProcessor()

        # Create many test inputs
        num_inputs = 50
        inputs = [
            MultiModalInput(
                input_id=f"scale_test_{i}",
                modality_type=ModalityType.TEXT,
                intent=ProcessingIntent.DECISION_MAKING,
                data=f"Scale test {i}",
            )
            for i in range(num_inputs)
        ]

        # Mock processor for consistent results. #13162: `_store_result` is
        # mocked for the same reason as in the concurrency benchmark above — it
        # writes every result to the shared SQLite memory database, whose write
        # lock serializes concurrent callers, so it measured disk contention
        # rather than the processor's scalability. The budget is unchanged.
        with (
            patch.object(processor.context_processor, "process", new_callable=AsyncMock) as mock_process,
            patch.object(processor, "_store_result", new_callable=AsyncMock),
        ):
            mock_process.return_value = Mock(
                success=True,
                confidence=0.8,
                processing_time=0.02,
                result_data={"decision": "test"},
                modality_type=ModalityType.TEXT,
                intent=ProcessingIntent.DECISION_MAKING,
                result_id="test",
            )

            # Process all inputs concurrently
            start_time = time.time()
            tasks = [processor.process(inp) for inp in inputs]
            results = await asyncio.gather(*tasks)
            total_time = (time.time() - start_time) * 1000

            # Should handle many concurrent requests efficiently
            assert_within_work_budget(total_time, 60.0, f"Scaling to {num_inputs} concurrent requests")
            assert len(results) == num_inputs
            assert all(r.success for r in results)

    def test_memory_usage_stability(self):
        """Test memory usage stability under load"""
        import gc

        config_manager = ConfigManager()
        # #13199: pin the sync cache — get_nested() would otherwise reload from disk
        # after CACHE_DURATION (30s) and discard the keys written below, making the
        # loop measure an empty config instead of a populated one.
        config_manager.CACHE_DURATION = float("inf")
        process = psutil.Process()

        # Get baseline memory
        gc.collect()
        initial_memory = process.memory_info().rss / 1024 / 1024

        # Perform many operations.
        # #13199: use the nested writer/readers consistently — get_config_section()
        # traverses dot paths, so keys written with the flat set()/get() pair were
        # invisible to it and the section loop would have measured empty dicts.
        for iteration in range(10):
            # Add many configs
            for i in range(100):
                config_manager.set_nested(f"memory_test.iter_{iteration}.key_{i}", f"data_{i}")

            # Get many configs
            for i in range(100):
                config_manager.get_nested(f"memory_test.iter_{iteration}.key_{i}")

            # Get sections
            for i in range(10):
                config_manager.get_config_section(f"memory_test.iter_{iteration}")

        # Check final memory
        gc.collect()
        final_memory = process.memory_info().rss / 1024 / 1024
        memory_growth = final_memory - initial_memory

        # Memory growth should be reasonable (less than 100MB)
        assert memory_growth < 100.0, f"Excessive memory growth: {memory_growth}MB"


class TestWorkBudgetHarness:
    """#15055: guards on the budget harness itself.

    A budget that can pass without measuring anything is the failure mode the
    millisecond constants were replaced to avoid repeating, so the property is
    asserted here rather than left to review. These are cheap and deterministic:
    they exercise `assert_within_work_budget` directly and time nothing.
    """

    def test_zero_elapsed_cannot_pass(self):
        """A measurement of zero is a measurement that did not happen."""
        with pytest.raises(AssertionError, match="did not run"):
            assert_within_work_budget(0.0, 1000.0, "zero measurement")

    def test_negative_elapsed_cannot_pass(self):
        """A negative duration means the clock, not the code, was measured."""
        with pytest.raises(AssertionError, match="did not run"):
            assert_within_work_budget(-1.0, 1000.0, "negative measurement")

    def test_absent_measurement_cannot_pass(self):
        """A missing measurement fails instead of comparing None to a budget."""
        with pytest.raises(AssertionError, match="no measurement was taken"):
            assert_within_work_budget(None, 1000.0, "absent measurement")

    def test_budget_still_fails_when_exceeded(self):
        """The counterpart guard: the assertion is not unconditionally green."""
        with pytest.raises(AssertionError, match="work units"):
            assert_within_work_budget(measure_reference_ms() * 100.0, 1.0, "deliberate overrun")

    def test_work_unit_is_measurable_and_positive(self):
        """The divisor is a real measurement, so a ratio means something."""
        reference_ms = measure_reference_ms()
        assert reference_ms > 0.0, f"work-unit calibration measured {reference_ms}ms"

    def test_reference_workload_is_deterministic(self):
        """The yardstick does the same work every time it is used."""
        assert _reference_workload() == _reference_workload()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
