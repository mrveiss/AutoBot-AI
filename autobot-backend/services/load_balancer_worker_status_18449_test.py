# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""load_balancer serves its former WorkerStatus callers from the NPU models enum (#18449)."""

from models import npu_models
from services import load_balancer


def test_load_balancer_uses_the_canonical_worker_status():
    assert load_balancer.WorkerStatus is npu_models.WorkerStatus


def test_every_former_load_balancer_member_survives_with_its_value():
    former = {"ONLINE": "online", "OFFLINE": "offline", "BUSY": "busy", "ERROR": "error"}
    for name, value in former.items():
        assert load_balancer.WorkerStatus[name].value == value


def test_strategy_base_no_longer_shares_the_enum_name():
    assert issubclass(load_balancer.RoundRobinStrategy, load_balancer.WorkerSelectionStrategy)
    assert not hasattr(load_balancer, "LoadBalancingStrategy")
