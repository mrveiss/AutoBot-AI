import json
import os
import platform
import subprocess


def get_os_info():
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
                "REDACTED"
                if any(s in k.lower() for s in ["key", "token", "secret", "password"])
                else v
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
    print(json.dumps(os_info, indent=2))
