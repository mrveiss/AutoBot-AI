# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Process-wide accessor for the DockerBackend singleton (#20889).

``lazy_singleton`` returns a *factory*; it must be built once at module level
and the factory called to obtain the instance. Every caller (the snapshot API
and the nightly snapshot cleanup) shares this one accessor, so they also share
one DockerBackend and one snapshot index.
"""

from autobot_shared.singleton_factory import lazy_singleton
from services.execution.docker_backend import DockerBackend

get_docker_backend_singleton = lazy_singleton(DockerBackend)
