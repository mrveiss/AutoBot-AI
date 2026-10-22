# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Equivalence of the two meta-device eviction paths on a real torch module.

Issue #13404: ``LayerInferenceEngine.evict_layer`` now delegates to
``meta_eviction.evict_layer_to_meta`` (``layer.to("meta")``). The removed
hand-rolled ``_move_to_meta`` (re-register every alias) is kept below as a
reference oracle: the canonical path must leave a layer in the same state, with
the same memory released (including tied weights) and a reload that restores
identical weights.
"""

import gc
import os
import types
import weakref

import pytest
import torch

_TORCH_IS_STUB = not isinstance(torch, types.ModuleType)
# AUTOBOT_REQUIRE_REAL_TORCH=1 (set by the real-torch CI job) turns the skip into a failure.
_REQUIRE_REAL_TORCH = os.environ.get("AUTOBOT_REQUIRE_REAL_TORCH") == "1"
pytestmark = pytest.mark.skipif(_TORCH_IS_STUB and not _REQUIRE_REAL_TORCH, reason="requires real PyTorch")

from llm_shared.optimization.layer_inference import LayerInferenceConfig, LayerInferenceEngine  # noqa: E402
from llm_shared.optimization.meta_eviction import evict_layer_to_meta  # noqa: E402


def test_real_torch_is_installed_when_required():
    if _REQUIRE_REAL_TORCH:
        assert not _TORCH_IS_STUB, "AUTOBOT_REQUIRE_REAL_TORCH=1 but torch is a stub: the install is broken"


class _Block(torch.nn.Module):
    """Tiny layer with tied weights, a frozen parameter and a buffer."""

    def __init__(self) -> None:
        super().__init__()
        self.up = torch.nn.Linear(16, 16)
        self.down = torch.nn.Linear(16, 16)
        self.down.weight = self.up.weight  # tied: two names, one Parameter
        self.up.bias.requires_grad_(False)
        self.register_buffer("scale", torch.arange(4, dtype=torch.float32))


def _canonical(module):
    evict_layer_to_meta(module)


def _hand_rolled(module):
    """Reference copy of the removed ``_move_to_meta`` (oracle only)."""
    meta = torch.device("meta")
    for name, p in list(module.named_parameters(remove_duplicate=False)):
        parts = name.split(".")
        owner = module
        for part in parts[:-1]:
            owner = getattr(owner, part)
        owner.register_parameter(
            parts[-1],
            torch.nn.Parameter(torch.empty(p.shape, dtype=p.dtype, device=meta), requires_grad=p.requires_grad),
        )
    for name, b in list(module.named_buffers()):
        parts = name.split(".")
        owner = module
        for part in parts[:-1]:
            owner = getattr(owner, part)
        owner.register_buffer(parts[-1], torch.empty(b.shape, dtype=b.dtype, device=meta))


def _engine(module):
    LayerInferenceEngine(LayerInferenceConfig(model_name="m")).evict_layer(module)


PATHS = [
    pytest.param(_canonical, id="to_meta"),
    pytest.param(_hand_rolled, id="move_to_meta"),
    pytest.param(_engine, id="engine_evict_layer"),
]


def _state(module):
    return {
        "params": {
            n: (tuple(p.shape), p.dtype, p.requires_grad, p.device.type)
            for n, p in module.named_parameters(remove_duplicate=False)
        },
        "buffers": {n: (tuple(b.shape), b.dtype, b.device.type) for n, b in module.named_buffers()},
    }


def test_both_paths_leave_identical_meta_state():
    torch.manual_seed(0)
    a, b = _Block(), _Block()
    b.load_state_dict(a.state_dict())
    c = _Block()
    c.load_state_dict(a.state_dict())
    _canonical(a)
    _hand_rolled(b)
    _engine(c)
    assert _state(a) == _state(b) == _state(c)
    assert all(v[3] == "meta" for v in _state(a)["params"].values())
    assert all(v[2] == "meta" for v in _state(a)["buffers"].values())
    assert set(_state(a)["params"]) == {"up.weight", "up.bias", "down.weight", "down.bias"}


@pytest.mark.parametrize("evict", PATHS)
def test_memory_is_released_including_tied_weight(evict):
    module = _Block()
    storages = {id(p.untyped_storage()): p.untyped_storage().nbytes() for p in module.parameters()}
    storages.update({id(module.scale.untyped_storage()): module.scale.untyped_storage().nbytes()})
    probes = [weakref.ref(p) for p in module.parameters()] + [weakref.ref(module.scale)]
    evict(module)
    gc.collect()
    # Every original dense tensor object is unreachable: nothing keeps real storage alive.
    assert all(ref() is None for ref in probes)
    for t in list(module.parameters()) + list(module.buffers()):
        assert t.device.type == "meta"
    assert sum(storages.values()) > 0


@pytest.mark.parametrize("evict", PATHS)
def test_reload_restores_identical_weights(evict):
    torch.manual_seed(1)
    module = _Block()
    saved = {k: v.clone() for k, v in module.state_dict().items()}
    evict(module)
    module.to_empty(device="cpu")
    module.load_state_dict(saved)
    for key, value in module.state_dict().items():
        assert torch.equal(value, saved[key]), key
    assert module.up.bias.requires_grad is False
