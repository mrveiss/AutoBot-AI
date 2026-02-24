# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import json
import os
import platform
import subprocess

# Performance optimization: O(1) lookup for sensitive env var keywords (Issue #326)
SENSITIVE_ENV_KEYWORDS = {"key", "token", "secret", "password"}


def get_os_info():
    """Collect OS and environment info with sensitive data redaction."""
    info = {
        "system": platform.system(),
        "node": platform.node(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        # Filter out sensitive environment variables
        "env": {
            k: (
                "REDACTED" if any(s in k.lower() for s in SENSITIVE_ENV_KEYWORDS) else v
            )
            for k, v in os.environ.items()
        },
    }
    if platform.system() == "Linux":
        try:
            info["distro"] = subprocess.getoutput("lsb_release -a 2>/dev/null")
        except FileNotFoundError:
            info["distro"] = "lsb_release not found"
        try:
            info["os_release"] = subprocess.getoutput("cat /etc/os-release 2>/dev/null")
        except FileNotFoundError:
            info["os_release"] = "/etc/os-release not found"
    return info


if __name__ == "__main__":
    os_info = get_os_info()
    print(json.dumps(os_info, indent=2))  # noqa: print
