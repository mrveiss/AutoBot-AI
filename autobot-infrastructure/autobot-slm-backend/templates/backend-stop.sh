#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot SLM Backend - Stop Script
# Manual intervention script for stopping the backend service

set -e

SERVICE_NAME="autobot-slm-backend"

echo "Stopping ${SERVICE_NAME}..."

if ! systemctl is-active --quiet "${SERVICE_NAME}"; then
    echo "${SERVICE_NAME} is not running"
    exit 0
fi

sudo systemctl stop "${SERVICE_NAME}"

echo "${SERVICE_NAME} stopped"
