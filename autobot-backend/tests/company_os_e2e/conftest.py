# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Fixtures for the Company OS end-to-end workflow test (#19253).

The scenario needs a disposable Postgres and Redis, named by AUTOBOT_COMPANY_OS_E2E_PG_HOST /
_PG_PORT / _PG_USER / _PG_PASSWORD and _REDIS_HOST / _REDIS_PORT (CI provides both as service
containers; see .github/workflows/company-os-workflow-e2e.yml). Without them every test that needs
the stack is skipped with the reason, the way tests/migrations does; tests that do not need it (the
environment allowlist) still run. The run refuses a Redis that holds data; a superuser Postgres role
is used only to create a throwaway CREATEDB-only role that the run itself uses. Set
AUTOBOT_COMPANY_OS_E2E_ARTIFACT_DIR to keep the server and stub logs.

The scenario is ONE ordered run: files are numbered, each step reads what earlier steps stored on
the session-scoped Scenario, and a step whose prerequisite did not complete fails by name rather
than skipping, so a red earlier step cannot make a later one look green.
"""

import os

import pytest

from tests.company_os_e2e import _stack as stackmod
from tests.company_os_e2e._scenario import Api, Scenario

NEEDS_STACK = {"stack", "scenario"}


def pytest_collection_modifyitems(config, items):  # noqa: ANN001
    if os.environ.get(stackmod.PG_HOST_ENV) and os.environ.get(stackmod.REDIS_HOST_ENV):
        return
    reason = f"{stackmod.PG_HOST_ENV} and {stackmod.REDIS_HOST_ENV} not set: needs disposable Postgres and Redis"
    for item in items:
        if "company_os_e2e" in str(item.fspath) and NEEDS_STACK & set(item.fixturenames):
            item.add_marker(pytest.mark.skip(reason=reason))


@pytest.fixture(scope="session")
def stack(tmp_path_factory):  # noqa: ANN001, ANN201
    running = stackmod.start(stackmod.Endpoints.from_env(), tmp_path_factory.mktemp("company_os_e2e"))
    try:
        yield running
    finally:
        stackmod.stop(running)


@pytest.fixture(scope="session")
def scenario(stack):  # noqa: ANN001, ANN201
    return Scenario(api=Api(stack), stack=stack)
