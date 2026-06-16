#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - Self-Signed TLS Certificate Generator (#1896)
# For development/testing only. Use proper CA certs in production.
#
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss

set -e

CERT_DIR="$(cd "$(dirname "$0")" && pwd)"
CERT_FILE="$CERT_DIR/autobot.crt"
KEY_FILE="$CERT_DIR/autobot.key"

if [ -f "$CERT_FILE" ] && [ -f "$KEY_FILE" ]; then
    echo "Certificates already exist at $CERT_DIR"
    echo "  Delete them first to regenerate."
    exit 0
fi

echo "Generating self-signed TLS certificate..."
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout "$KEY_FILE" \
    -out "$CERT_FILE" \
    -subj "/C=US/ST=Local/L=Local/O=AutoBot/CN=localhost" \
    -addext "subjectAltName=DNS:localhost,DNS:autobot,IP:127.0.0.1"

chmod 600 "$KEY_FILE"
chmod 644 "$CERT_FILE"

echo "Certificate generated:"
echo "  Cert: $CERT_FILE"
echo "  Key:  $KEY_FILE"
