# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Hostile RUM label values cannot create unbounded Prometheus series (#18368)."""

from prometheus_client import CollectorRegistry, Counter

from autobot_shared.monitoring.metrics.frontend import FrontendMetricsRecorder
from autobot_shared.monitoring.metrics.label_bounds import OTHER, BoundedLabels

_N = 500


def _word(i: int) -> str:
    """A letters-only value, so path collapsing cannot merge them for us."""
    out = ""
    for _ in range(4):
        i, r = divmod(i, 26)
        out += chr(ord("a") + r)
    return out


def _series(registry: CollectorRegistry, metric: str) -> set:
    """Distinct label sets of *metric*'s samples (histograms: the ``_count`` sample)."""
    found = set()
    for family in registry.collect():
        for sample in family.samples:
            if sample.name in (metric, f"{metric}_count", f"{metric}_total"):
                found.add(tuple(sorted(sample.labels.items())))
    return found


def test_n_distinct_hostile_pages_make_at_most_k_plus_one_series(monkeypatch) -> None:
    monkeypatch.setenv("AUTOBOT_RUM_LABEL_MAX_VALUES", "10")
    registry = CollectorRegistry()
    recorder = FrontendMetricsRecorder(registry)
    for i in range(_N):
        recorder.record_page_load(f"/hostile/{_word(i)}", 0.5)
    series = _series(registry, "autobot_frontend_page_load_seconds")
    assert len(series) <= 11
    assert (("page", OTHER),) in series


def test_every_label_of_every_recorder_method_is_bounded(monkeypatch) -> None:
    monkeypatch.setenv("AUTOBOT_RUM_LABEL_MAX_VALUES", "3")
    registry = CollectorRegistry()
    recorder = FrontendMetricsRecorder(registry)
    for i in range(_N):
        v = _word(i)
        recorder.record_api_request(f"/api/{v}", v, v, 0.1, True, True)
        recorder.record_api_error(f"/api/{v}", v, v)
        recorder.record_js_error(v, v)
        recorder.record_unhandled_rejection(v)
        recorder.record_component_error(v, v)
        recorder.record_user_action(v, v)
        recorder.record_form_submission(v, v)
        recorder.record_ws_connection_event(v)
        recorder.record_ws_message(v, v)
        recorder.record_resource_load(v, 0.1)
        recorder.record_slow_resource(v)
        recorder.record_critical_issue(v)
    # Every label of every family holds at most 3 values + "other"; nothing scales with _N.
    for family in registry.collect():
        values: dict = {}
        for sample in family.samples:
            for name, value in sample.labels.items():
                if name != "le":
                    values.setdefault(name, set()).add(value)
        for name, seen in values.items():
            assert len(seen) <= 4, (family.name, name, len(seen))


def test_contrast_an_unbounded_label_grows_with_input() -> None:
    """The pre-fix shape: a raw labelled metric gets one series per distinct value."""
    registry = CollectorRegistry()
    raw = Counter("raw_page_total", "raw", ["page"], registry=registry)
    for i in range(_N):
        raw.labels(page=f"/hostile/{_word(i)}").inc()
    assert len(_series(registry, "raw_page")) == _N


def test_method_has_a_closed_vocabulary() -> None:
    labels = BoundedLabels()
    assert labels.bound("method", "GET") == "GET"
    assert labels.bound("method", "BREW") == OTHER


def test_long_or_control_values_are_other(monkeypatch) -> None:
    monkeypatch.setenv("AUTOBOT_RUM_LABEL_MAX_CHARS", "8")
    labels = BoundedLabels()
    assert labels.bound("page", "/short") == "/short"
    assert labels.bound("page", "/much-too-long") == OTHER
    assert labels.bound("page", "/a\r\nb") == OTHER
    assert labels.bound("page", "") == OTHER


def test_a_seen_value_keeps_recording_after_the_vocabulary_is_full(monkeypatch) -> None:
    monkeypatch.setenv("AUTOBOT_RUM_LABEL_MAX_VALUES", "1")
    labels = BoundedLabels()
    assert labels.bound("page", "/chat") == "/chat"
    assert labels.bound("page", "/new") == OTHER
    assert labels.bound("page", "/chat") == "/chat"
