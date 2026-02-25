# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import json
import shutil
import subprocess

ESSENTIAL_TOOLS = [
    "bash",
    "python3",
    "git",
    "curl",
    "wget",
    "nmap",
    "docker",
    "apt",
    "yum",
    "dn",
    "pacman",
    "pip",
    "systemctl",
    "ssh",
    "ls",
    "ps",
    "cat",
    "echo",
    "grep",
    "find",
    "mv",
    "cp",
    "rm",
    "mkdir",
    "chmod",
    "ping",
    "ifconfig",
    "ip",
    "netstat",
    "ss",
    "journalctl",
    "nano",
    "vim",
    "code",
    "npm",
    "node",
    "java",
    "gcc",
    "make",
    "ansible",
    "terraform",
    "kubectl",
    "helm",
    "docker-compose",
]


def discover_tools():
    """Discover available system tools and their versions from predefined list."""
    found = {}
    for tool in ESSENTIAL_TOOLS:
        path = shutil.which(tool)
        if path:
            try:
                # Attempt to get version, but handle cases where --version
                # might not work
                # Tool from ESSENTIAL_TOOLS constant, not user input
                version_output = subprocess.getoutput(f"{tool} --version")  # nosec B605
                version = (
                    version_output.splitlines()[0] if version_output else "available"
                )
            except Exception:
                version = "available"
            found[tool] = {"path": path, "version": version}
    return found


if __name__ == "__main__":
    available_tools = discover_tools()
    print(json.dumps(available_tools, indent=2))  # noqa: print
