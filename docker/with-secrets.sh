#!/bin/sh
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Compose secret loader (GH#9905). Runs as the entrypoint wrapper for services
# that need the shared signing secret. It sources the auto-generated secret from
# the shared `autobot_secrets` volume (/secrets/autobot.env) and applies each
# value ONLY when the corresponding env var is empty/unset — so an explicit
# operator-provided AUTOBOT_JWT_SECRET / SECRET_KEY (e.g. real production
# secrets via --env-file or the host environment) always takes precedence.
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
    export AUTOBOT_JWT_SECRET SECRET_KEY
fi

exec "$@"
