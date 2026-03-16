#!/bin/bash
# Create additional databases for SLM user management (#1854)
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    CREATE DATABASE slm_users OWNER $POSTGRES_USER;
EOSQL
