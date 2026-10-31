# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Run the real AutoBot backend with only the LLM adapter stubbed (#19253).

Everything else is production: create_app(), its lifespan, the Company OS routers, the auth
middleware, the heartbeat scheduler and the Agent API. The test fixture starts this as a
subprocess and talks to it over HTTP, exactly as a client would.

Usage: python _serve.py   (host/port come from AUTOBOT_COMPANY_OS_E2E_SERVE_HOST / _PORT)
"""

import os

import uvicorn

from app_factory import create_app
from tests.company_os_e2e._stub_adapter import install_stub_adapter

HOST_ENV = "AUTOBOT_COMPANY_OS_E2E_SERVE_HOST"
PORT_ENV = "AUTOBOT_COMPANY_OS_E2E_SERVE_PORT"


def main() -> None:
    install_stub_adapter()
    uvicorn.run(create_app(), host=os.environ[HOST_ENV], port=int(os.environ[PORT_ENV]), log_level="info")


if __name__ == "__main__":
    main()
