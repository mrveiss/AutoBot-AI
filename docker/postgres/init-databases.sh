#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Create the databases beside POSTGRES_DB (#1854, #1981). The name is the one compose hands the
# services (#19408), so a custom AUTOBOT_POSTGRES_DB exists on a fresh volume. Postgres runs this
# only when it initialises an empty volume; on an existing one, create a renamed database by hand.
set -euo pipefail

psql -v ON_ERROR_STOP=1 -v users_db="${AUTOBOT_POSTGRES_DB:?compose sets this}" \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
CREATE DATABASE slm_users;
CREATE DATABASE :"users_db";
SQL
