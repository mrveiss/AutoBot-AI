#!/bin/sh
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Compose secret loader (GH#9905). Runs as the entrypoint wrapper for services
# that need the shared signing secret. It sources the auto-generated secret from
# the shared `autobot_secrets` volume (/secrets/autobot.env) and applies each
# value ONLY when the corresponding env var is empty/unset — so an explicit
# operator-provided AUTOBOT_JWT_SECRET / SECRET_KEY (e.g. real production
# secrets via --env-file or the host environment) always takes precedence.
#
# SLM_SECRET_KEY is also propagated from _GEN_JWT (AUTOBOT_JWT_SECRET) so the
# SLM and the backend share one HS256 signing secret, enabling the backend to
# mint a service JWT that the SLM's auth_service.decode_token can verify
# (GH#9852).
#
# Then it execs the real command (passed as "$@"), so the service's normal
# entrypoint/CMD runs unchanged.
set -eu

SECRETS_FILE="/secrets/autobot.env"

if [ -r "$SECRETS_FILE" ]; then
    # _GEN_JWT / _GEN_SECRET_KEY are defined by docker/secrets-init.sh.
    . "$SECRETS_FILE"
    # `:=` assigns only when the variable is unset OR empty.
    : "${AUTOBOT_JWT_SECRET:=${_GEN_JWT:-}}"
    : "${SECRET_KEY:=${_GEN_SECRET_KEY:-}}"
    # SLM reads SLM_SECRET_KEY for decode_token.  The backend signs service
    # JWTs with AUTOBOT_JWT_SECRET (_GEN_JWT), so SLM_SECRET_KEY MUST be the
    # same value — NOT _GEN_SECRET_KEY (GH#9852: signing-secret alignment).
    : "${SLM_SECRET_KEY:=${_GEN_JWT:-}}"
    export AUTOBOT_JWT_SECRET SECRET_KEY SLM_SECRET_KEY
fi

exec "$@"
