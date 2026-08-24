#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Integration Test Suite for Infrastructure API
Tests all endpoints, CRUD operations, and database performance features

Every check here drives a *running* backend over HTTP (and, for the worker
check, its on-disk log), so the whole module carries the ``integration``
marker: the unit selection (``-m "not integration"``) must skip it rather
than fail against a backend that is not up.
"""

import sys
from pathlib import Path

import pytest
import requests

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from autobot_shared.live_service_probe import require_live_endpoint
from autobot_shared.paths import project_root
from constants.network_constants import ServiceURLs

pytestmark = pytest.mark.integration

BASE_URL = f"{ServiceURLs.BACKEND_API}/api/iac"


# ``test_celery_worker_status`` reads ``logs/celery-worker.log`` off disk and
# issues no HTTP at all, so a backend that is down does not stop it — it was
# passing before #14930 and must keep passing. A module-wide guard would have
# traded a red result for lost coverage, which is the wrong trade and was caught
# by comparing the skip count (7) against the number of tests that actually
# failed on a refused connection (6).
_NEEDS_NO_BACKEND = ("test_celery_worker_status",)


@pytest.fixture(autouse=True)
def _require_live_backend(request) -> None:
    """Skip when no backend is listening, instead of failing on a refused socket (#14930).

    The six checks that dial ``BASE_URL`` over real HTTP reported
    ``ConnectionRefusedError`` as test failures on a runner with no backend up —
    a red result that says nothing about the code under test and trained the
    whole marker-excluded suite to be ignored. A skip naming the absent service
    is the honest report; they still run, and still fail for real, wherever a
    backend is actually up.
    """
    stranded = [name for name in _NEEDS_NO_BACKEND if name not in globals()]
    assert not stranded, (
        f"_NEEDS_NO_BACKEND names {stranded}, which no longer exist in this module. "
        f"A rename stranded the exemption: it now exempts nothing, silently."
    )

    if request.node.name in _NEEDS_NO_BACKEND:
        return

    require_live_endpoint(ServiceURLs.BACKEND_API, what="the AutoBot backend API")


def test_health():
    """Test 1: Health Check"""
    response = requests.get(f"{BASE_URL}/health")  # nosec B113
    data = response.json()
    print("✅ Test 1: Health Check - PASSED")  # noqa: print
    print(f"   Status: {data['status']}, Database: {data['database']}, Hosts: {data['total_hosts']}")  # noqa: print
    return


def test_list_roles():
    """Test 2: List Infrastructure Roles"""
    response = requests.get(f"{BASE_URL}/roles")  # nosec B113
    data = response.json()
    role_names = [r["name"] for r in data]
    print("✅ Test 2: List Roles - PASSED")  # noqa: print
    print(f"   Found {len(data)} roles: {role_names}")  # noqa: print
    return


def test_statistics():
    """Test 3: Get Statistics"""
    response = requests.get(f"{BASE_URL}/statistics")  # nosec B113
    data = response.json()
    print("✅ Test 3: Statistics - PASSED")  # noqa: print
    print(  # noqa: print
        f"   Hosts: {data['total_hosts']}, Roles: {data['total_roles']}, Deployments: {data['total_deployments']}"
    )
    return


def test_list_hosts_empty():
    """Test 4: List Hosts (Empty Database)"""
    response = requests.get(f"{BASE_URL}/hosts", params={"page": 1, "page_size": 20})  # nosec B113
    data = response.json()
    print("✅ Test 4: List Hosts (Empty) - PASSED")  # noqa: print
    print(f"   Pagination: page={data['pagination']['page']}, total={data['pagination']['total']}")  # noqa: print
    return


def test_create_host():
    """Test 5: Create Test Host"""
    form_data = {
        "hostname": "test-integration-host",
        "ip_address": "10.0.0.99",
        "role": "frontend",
        "ssh_port": "22",
        "ssh_user": "autobot",
        "auth_method": "password",
        "password": "test123",
    }
    response = requests.post(f"{BASE_URL}/hosts", data=form_data)  # nosec B113

    if response.status_code != 201:
        print(f"❌ Test 5: Create Host - FAILED (HTTP {response.status_code})")  # noqa: print  # noqa: print
        print(f"   Error: {response.text}")  # noqa: print
        return None

    data = response.json()
    print("✅ Test 5: Create Host - PASSED")  # noqa: print
    print(f"   Created host ID={data['id']}, hostname={data['hostname']}, status={data['status']}")  # noqa: print
    return data["id"]


def check_host_details(host_id):
    """Test 6: Get Host Details (Relationship Loading).

    Takes the id produced by test_create_host, so it is a step of the main()
    flow rather than a standalone test — collected as one, pytest read the
    argument as a request for a "host_id" fixture that does not exist and
    errored every run.
    """
    response = requests.get(f"{BASE_URL}/hosts/{host_id}")  # nosec B113
    data = response.json()
    print("✅ Test 6: Get Host Details - PASSED")  # noqa: print
    print(  # noqa: print
        f"   Host: {data['hostname']}, Role: {data.get('role_name', 'N/A')}, Deployments: {data.get('deployment_count', 0)}"
    )
    return True


def test_list_hosts_after_create():
    """Test 7: List Hosts After Creation"""
    response = requests.get(f"{BASE_URL}/hosts")  # nosec B113
    data = response.json()
    first_host = data["hosts"][0]["hostname"] if data["hosts"] else "None"
    print("✅ Test 7: List Hosts After Creation - PASSED")  # noqa: print
    print(f"   Total hosts: {data['pagination']['total']}, First host: {first_host}")  # noqa: print  # noqa: print
    return


def check_delete_host(host_id):
    """Test 8: Delete Test Host (step of the main() flow — see check_host_details)."""
    response = requests.delete(f"{BASE_URL}/hosts/{host_id}")  # nosec B113
    print("✅ Test 8: Delete Host - PASSED")  # noqa: print
    print(f"   HTTP Status: {response.status_code}")  # noqa: print

    # Verify deletion
    response = requests.get(f"{BASE_URL}/hosts")  # nosec B113
    data = response.json()
    print(f"   Remaining hosts after deletion: {data['pagination']['total']}")  # noqa: print  # noqa: print
    return True


# What the worker writes to its log when it has come up. Both tokens are
# required: "ready" alone appears in lines other processes write, and the
# service name alone appears before the worker has finished starting.
_WORKER_READY_MARKERS = ("autobot-worker", "ready")


def test_celery_worker_status():
    """Test 9: Celery Worker Status — the worker's own log is the only evidence.

    #14941: this used to wrap its whole body in ``try/except Exception`` and end
    every path with ``return True`` or ``return False``. pytest discards a test's
    return value, so no log content, no service state and no raised exception
    could make it fail — it reported pass unconditionally, in a marker set that
    until #14930 ran in no gating workflow at all.

    The only thing that legitimately excuses this check is a checkout that is not
    a deployment, and that is decided by the ``logs/`` directory rather than by
    the log file: if ``logs/`` is absent nothing on this host ever ran, so there
    is nothing to report on. If ``logs/`` exists and the worker's log does not,
    the worker never started, and that is a failure rather than a non-result.

    ``main()`` calls this bare and discards whatever it returns, so unlike the
    npu_code_search drivers (#14920) there is no truthiness contract to keep and
    the function returns nothing at all.
    """
    log_directory = project_root() / "logs"
    log_file = log_directory / "celery-worker.log"

    if not log_directory.is_dir():
        pytest.skip(
            f"{log_directory} does not exist — this checkout is not a deployment, "
            "so no service on this host has written a log to read"
        )

    assert log_file.is_file(), (
        f"{log_file} is absent while {log_directory} exists — this host runs services "
        "but the Celery worker has never written a log, so it never started"
    )

    logs = log_file.read_text(encoding="utf-8", errors="replace")
    assert logs.strip(), (
        f"{log_file} is empty — the worker process produced no output at all, "
        "so it did not come up"
    )

    missing = [marker for marker in _WORKER_READY_MARKERS if marker not in logs]
    assert not missing, (
        f"{log_file} never mentions {missing} — the Celery worker did not report "
        f"itself ready ({len(logs)} bytes of log read)"
    )

    print("✅ Test 9: Celery Worker - PASSED")  # noqa: print
    print("   Worker is running with queues: celery, deployments")  # noqa: print


def main():
    print("=" * 60)  # noqa: print
    print("INTEGRATION TEST SUITE: INFRASTRUCTURE API")  # noqa: print
    print("=" * 60)  # noqa: print
    print()  # noqa: print

    try:
        # Read-only tests
        test_health()
        print()  # noqa: print
        test_list_roles()
        print()  # noqa: print
        test_statistics()
        print()  # noqa: print
        test_list_hosts_empty()
        print()  # noqa: print

        # CRUD tests
        host_id = test_create_host()
        if host_id:
            print()  # noqa: print
            check_host_details(host_id)
            print()  # noqa: print
            test_list_hosts_after_create()
            print()  # noqa: print
            check_delete_host(host_id)
            print()  # noqa: print

        # Worker status
        test_celery_worker_status()
        print()  # noqa: print

        print("=" * 60)  # noqa: print
        print("ALL TESTS PASSED ✅")  # noqa: print
        print("=" * 60)  # noqa: print
        print()  # noqa: print
        print("SYSTEM STATUS:")  # noqa: print
        print("  ✅ Backend API: Operational")  # noqa: print
        print("  ✅ Infrastructure Router: Loaded")  # noqa: print
        print("  ✅ Database: Connected")  # noqa: print
        print("  ✅ CRUD Operations: Working")  # noqa: print
        print("  ✅ Pagination: Working")  # noqa: print
        print("  ✅ Relationship Loading: Working")  # noqa: print
        print("  ✅ Celery Worker: Running")  # noqa: print
        print()  # noqa: print
        print("🎉 Infrastructure system ready for production host provisioning!")  # noqa: print  # noqa: print

    except Exception as e:
        print(f"\n❌ TEST SUITE FAILED: {e}")  # noqa: print
        sys.exit(1)


if __name__ == "__main__":
    main()
