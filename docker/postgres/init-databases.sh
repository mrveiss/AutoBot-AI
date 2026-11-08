#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Create the database beside POSTGRES_DB in the SLM's Postgres (#1854, #1981, #20639). Postgres runs
# this only when it initialises an empty volume.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
CREATE DATABASE slm_users;
SQL
