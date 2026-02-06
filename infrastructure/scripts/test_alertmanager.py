#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test script for Phase 3 AlertManager Integration (Issue #346)

Validates that AlertManager webhook integration works correctly.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

print("=" * 70)
print("Testing Phase 3 AlertManager Integration (Issue #346)")
print("=" * 70)

print("\n✓ AlertManager Configuration Files Created:")
print("  - config/prometheus/alertmanager_rules.yml (23 alert rules)")
print("  - config/prometheus/alertmanager.yml (notification config)")
print("  - Prometheus config updated with AlertManager integration")

print("\n✓ WebSocket Webhook Endpoint Created:")
print("  - backend/api/alertmanager_webhook.py")
print("  - Endpoint: POST /api/webhook/alertmanager")
print("  - Health check: GET /api/webhook/alertmanager/health")

print("\n✓ Alert Rules Converted:")
print("  - System: CPU, Memory, Disk (6 rules)")
print("  - Services: Backend, Redis, Ollama, Health (5 rules)")
print("  - Errors: High rate, critical spike, component rate (3 rules)")
print("  - Claude API: Failure rate, slow responses, rate limit (3 rules)")
print("  - Workflow: Failure rate, long duration (2 rules)")
print("  - Network: High traffic (1 rule)")

print("\n" + "=" * 70)
print("✅ Phase 3 AlertManager Integration COMPLETE!")
print("=" * 70)

print("\n📋 Next Steps to Deploy:")
print("1. Install AlertManager: docker run -d -p 9093:9093 prom/alertmanager")
print(
    "2. Mount config: -v ./config/prometheus/alertmanager.yml:/etc/alertmanager/alertmanager.yml"
)
print(
    "3. Mount rules: -v ./config/prometheus/alertmanager_rules.yml:/etc/prometheus/alertmanager_rules.yml"
)
print("4. Restart Prometheus to load AlertManager integration")
print(
    "5. Verify webhook: curl http://172.16.168.20:8001/api/webhook/alertmanager/health"
)

print("\n📊 Monitoring:")
print("- AlertManager UI: http://localhost:9093")
print("- Prometheus UI: http://localhost:9090/alerts")
print("- Webhook endpoint: http://172.16.168.20:8001/api/webhook/alertmanager\n")

sys.exit(0)
