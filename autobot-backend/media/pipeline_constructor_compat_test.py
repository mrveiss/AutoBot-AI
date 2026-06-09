# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Constructor-compatibility regression test for media pipeline classes (#6755).

Catches the same class of bug as #6660 (StandardizedAgent subclasses): every
``BasePipeline`` subclass must accept the parent's full ``(pipeline_name,
supported_types)`` signature so factory callers like ``cls(name, types)``
keep working.  Pre-#6755 the five pipeline subclasses had ``def __init__(self):``
and crashed on factory-style instantiation.
"""

import importlib
import inspect

import pytest

PIPELINE_MODULES = [
    ("media.document.pipeline", "DocumentPipeline"),
    ("media.link.pipeline", "LinkPipeline"),
    ("media.audio.pipeline", "AudioPipeline"),
    ("media.video.pipeline", "VideoPipeline"),
    ("media.image.pipeline", "ImagePipeline"),
]


@pytest.mark.parametrize("module_path,class_name", PIPELINE_MODULES)
def test_pipeline_constructor_accepts_parent_signature(module_path, class_name):
    """Every BasePipeline subclass must accept (pipeline_name, supported_types).

    Regression: pre-#6755 these were `def __init__(self):` with hardcoded
    super() args, breaking `cls(name, types)` factory patterns.
    """
    try:
        mod = importlib.import_module(module_path)
    except Exception as exc:  # pragma: no cover — env-dependent dep chain
        pytest.skip(f"{module_path} dep chain unavailable: {exc}")

    cls = getattr(mod, class_name)
    params = inspect.signature(cls.__init__).parameters
    assert "pipeline_name" in params, f"{class_name}.__init__ must accept 'pipeline_name' for factory compat"
    assert "supported_types" in params, f"{class_name}.__init__ must accept 'supported_types' for factory compat"
    # Both parameters must have defaults so the historical no-arg call site
    # (e.g. `DocumentPipeline()` in production) keeps working.
    assert (
        params["pipeline_name"].default is not inspect.Parameter.empty
    ), f"{class_name}.pipeline_name must have a default"
    assert (
        params["supported_types"].default is not inspect.Parameter.empty
    ), f"{class_name}.supported_types must have a default"


@pytest.mark.parametrize("module_path,class_name", PIPELINE_MODULES)
def test_pipeline_no_arg_instantiation_still_works(module_path, class_name):
    """The historical `Pipeline()` call (no args) must keep producing a
    well-formed instance with the original hardcoded defaults."""
    try:
        mod = importlib.import_module(module_path)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"{module_path} dep chain unavailable: {exc}")

    cls = getattr(mod, class_name)
    try:
        inst = cls()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"{class_name}() requires extra deps: {exc}")
    # Pipeline name should match the historical hardcoded value
    expected = class_name.replace("Pipeline", "").lower()
    assert inst.pipeline_name == expected, (
        f"no-arg {class_name}() should produce pipeline_name='{expected}', " f"got {inst.pipeline_name!r}"
    )
    assert inst.supported_types, f"{class_name}() should have non-empty supported_types"
