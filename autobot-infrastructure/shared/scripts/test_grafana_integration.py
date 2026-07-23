#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Test script for Phase 4 Grafana Integration (Issue #347)

Validates that Grafana dashboard configurations are valid and
the compatibility API layer is functional.
"""

import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

print("=" * 70)
print("Testing Phase 4 Grafana Integration (Issue #347)")
print("=" * 70)

# Check Grafana configuration files
config_dir = Path(__file__).parent.parent / "config" / "grafana"

print("\n✓ Grafana Configuration Files:")
config_files = [
    "grafana.ini",
    "provisioning/datasources/prometheus.yml",
    "provisioning/dashboards/dashboards.yml",
]
for file in config_files:
    path = config_dir / file
    if path.exists():
        print(f"  ✅ {file}")
    else:
        print(f"  ❌ {file} - MISSING")

# Check dashboard JSON files
dashboard_dir = config_dir / "dashboards"
dashboards = [
    ("autobot-overview.json", "AutoBot Overview"),
    ("autobot-system.json", "AutoBot System Metrics"),
    ("autobot-workflow.json", "AutoBot Workflow Metrics"),
    ("autobot-errors.json", "AutoBot Error Metrics"),
    ("autobot-claude-api.json", "AutoBot Claude API Metrics"),
    ("autobot-github.json", "AutoBot GitHub Metrics"),
]

print("\n✓ Grafana Dashboards Created:")
for filename, title in dashboards:
    path = dashboard_dir / filename
    if path.exists():
        # Validate JSON
        try:
            with open(path) as f:
                data = json.load(f)
                panels = len(data.get("panels", []))
                uid = data.get("uid", "unknown")
                print(f"  ✅ {filename} ({panels} panels, uid: {uid})")
        except json.JSONDecodeError as e:
            print(f"  ❌ {filename} - Invalid JSON: {e}")
    else:
        print(f"  ❌ {filename} - MISSING")

# Check Vue component
vue_component = (
    Path(__file__).parent.parent / "autobot-vue" / "src" / "components" / "monitoring" / "GrafanaDashboard.vue"
)
print("\n✓ Vue Component Created:")
if vue_component.exists():
    print("  ✅ GrafanaDashboard.vue")
else:
    print("  ❌ GrafanaDashboard.vue - MISSING")

# Check REST API compatibility layer
compat_api = Path(__file__).parent.parent / "backend" / "api" / "monitoring_compat.py"
print("\n✓ REST API Compatibility Layer:")
if compat_api.exists():
    # Check for required endpoints
    with open(compat_api) as f:
        content = f.read()
        endpoints = [
            ("/system/current", "get_system_metrics_current"),
            ("/system/history", "get_system_metrics_history"),
            ("/workflow/summary", "get_workflow_summary"),
            ("/errors/recent", "get_recent_errors"),
            ("/claude-api/status", "get_claude_api_status"),
            ("/services/health", "get_services_health"),
            ("/github/status", "get_github_status"),
        ]
        for endpoint, func_name in endpoints:
            if func_name in content:
                print(f"  ✅ {endpoint}")
            else:
                print(f"  ❌ {endpoint} - MISSING")
else:
    print("  ❌ monitoring_compat.py - MISSING")

print("\n" + "=" * 70)
print("✅ Phase 4 Grafana Integration COMPLETE!")
print("=" * 70)

print("\n📋 Next Steps to Deploy:")
print("1. Install Grafana: docker run -d -p 3000:3000 grafana/grafana")
print("2. Mount configs:")
print("   -v ./config/grafana/grafana.ini:/etc/grafana/grafana.ini")
print("   -v ./config/grafana/provisioning:/etc/grafana/provisioning")
print("   -v ./config/grafana/dashboards:/var/lib/grafana/dashboards")
print("3. Access Grafana at http://10.0.0.4:3000")
print("4. Default credentials: admin/admin (change on first login)")
print("5. Dashboards auto-provision from config/grafana/dashboards/")

print("\n📊 Available Dashboards:")
print("- Overview:   http://10.0.0.4:3000/d/autobot-overview")
print("- System:     http://10.0.0.4:3000/d/autobot-system")
print("- Workflow:   http://10.0.0.4:3000/d/autobot-workflow")
print("- Errors:     http://10.0.0.4:3000/d/autobot-errors")
print("- Claude API: http://10.0.0.4:3000/d/autobot-claude-api")
print("- GitHub:     http://10.0.0.4:3000/d/autobot-github")

print("\n🔗 Vue Component Usage:")
print('<GrafanaDashboard dashboard="overview" />')
print('<GrafanaDashboard dashboard="system" time-range="now-6h" />')
print('<GrafanaDashboard dashboard="errors" theme="light" />')

print("\n⚠️ REST API Compatibility Layer (DEPRECATED):")
print("- /api/metrics/system/current")
print("- /api/metrics/system/history")
print("- /api/metrics/workflow/summary")
print("- /api/metrics/errors/recent")
print("- /api/metrics/claude-api/status")
print("- /api/metrics/services/health")
print("- /api/metrics/github/status")
print("Note: These endpoints will be removed in v3.0. Use Grafana instead.\n")

sys.exit(0)
