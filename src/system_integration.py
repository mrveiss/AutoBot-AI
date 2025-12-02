# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import json
import logging
import os
import platform
import subprocess
from typing import Any, Dict, List, Optional

import aiohttp  # Import aiohttp for async web fetching
from markdownify import (
    markdownify as md,  # Import markdownify for HTML to Markdown conversion
)

from src.utils.http_client import get_http_client

logger = logging.getLogger(__name__)


class SystemIntegration:
    def __init__(self):
        self.os_type = platform.system()
        logger.info(f"SystemIntegration initialized for OS: {self.os_type}")

    def _run_command(self, command: List[str], shell: bool = False) -> Dict[str, Any]:
        """Helper to run shell commands and capture output."""
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, check=True, shell=shell
            )
            return {
                "status": "success",
                "output": result.stdout.strip(),
                "error": result.stderr.strip(),
            }
        except subprocess.CalledProcessError as e:
            return {
                "status": "error",
                "message": f"Command failed with exit code {e.returncode}",
                "output": e.stdout.strip(),
                "error": e.stderr.strip(),
            }
        except FileNotFoundError:
            return {
                "status": "error",
                "message": f"Command not found: {command[0]}",
                "output": "",
                "error": "",
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"An unexpected error occurred: {e}",
                "output": "",
                "error": str(e),
            }

    def query_system_info(self) -> Dict[str, Any]:
        """Queries basic system information."""
        info = {
            "os_type": self.os_type,
            "os_name": platform.platform(),
            "architecture": platform.machine(),
            "hostname": platform.node(),
            "cpu_count": os.cpu_count(),
            "python_version": platform.python_version(),
        }

        if self.os_type == "Windows":
            # Example: Get Windows version
            win_version_cmd = ["systeminfo", "/fo", "csv", "/nh"]
            cmd_result = self._run_command(win_version_cmd)
            if cmd_result["status"] == "success":
                try:
                    # Parse CSV output for OS Name and Version
                    lines = cmd_result["output"].splitlines()
                    if lines:
                        parts = lines[0].split(",")
                        # Assuming specific indices for OS Name and Version
                        # This is fragile and depends on systeminfo output format
                        # A more robust solution would parse the full CSV or use WMI
                        if len(parts) > 1:
                            info["windows_os_name"] = parts[0].strip('"')
                            info["windows_os_version"] = parts[1].strip('"')
                except Exception as e:
                    logger.debug(f"Failed to parse Windows systeminfo: {e}")

        elif self.os_type == "Linux":
            # Example: Get distribution info
            lsb_release_cmd = ["lsb_release", "-a"]
            cmd_result = self._run_command(lsb_release_cmd)
            if cmd_result["status"] == "success":
                for line in cmd_result["output"].splitlines():
                    if "Description:" in line:
                        info["linux_distro"] = line.split(":", 1)[1].strip()
                    elif "Release:" in line:
                        info["linux_release"] = line.split(":", 1)[1].strip()

            # Example: Kernel version
            info["kernel_version"] = platform.release()

        return {"status": "success", "info": info}

    def list_services(self) -> Dict[str, Any]:
        """Lists active services."""
        if self.os_type == "Windows":
            cmd = [
                "powershell",
                "Get-Service | Select-Object Name, Status | "
                "ConvertTo-Csv -NoTypeInformation",
            ]
            result = self._run_command(cmd)
            if result["status"] == "success":
                # Parse CSV output
                lines = result["output"].strip().split("\n")
                services = []
                if len(lines) > 1:
                    headers = [h.strip('"') for h in lines[0].split(",")]
                    for line in lines[1:]:
                        parts = [p.strip('"') for p in line.split(",")]
                        if len(parts) == len(headers):
                            services.append(dict(zip(headers, parts)))
                return {"status": "success", "services": services}
            return result
        elif self.os_type == "Linux":
            cmd = [
                "systemctl",
                "list-units",
                "--type=service",
                "--all",
                "--no-pager",
                "--output=json",
            ]
            result = self._run_command(cmd)
            if result["status"] == "success":
                try:
                    services_data = json.loads(result["output"])
                    # Extract relevant info: Name, Description, ActiveState
                    parsed_services = []
                    for service in services_data:
                        parsed_services.append(
                            {
                                "Name": service.get("unit", "").replace(".service", ""),
                                "Description": service.get("description", ""),
                                "Status": service.get("activestate", ""),
                            }
                        )
                    return {"status": "success", "services": parsed_services}
                except json.JSONDecodeError:
                    return {
                        "status": "error",
                        "message": "Failed to parse systemctl JSON output.",
                        "output": result["output"],
                    }
            return result
        else:
            return {
                "status": "error",
                "message": "Unsupported OS for listing services.",
            }

    def manage_service(self, service_name: str, action: str) -> Dict[str, Any]:
        """Starts, stops, or restarts a system service."""
        if action not in ["start", "stop", "restart"]:
            return {
                "status": "error",
                "message": (
                    "Invalid service action. Must be 'start', " "'stop', or 'restart'."
                ),
            }

        if self.os_type == "Windows":
            cmd = [
                "powershell",
                f"Set-Service -Name '{service_name}' -Status '{action}'",
            ]
            # Note: Set-Service -Status doesn't directly start/stop,
            # it sets desired state. For immediate action, use Start-Service,
            # Stop-Service, Restart-Service
            if action == "start":
                cmd = ["powershell", f"Start-Service -Name '{service_name}'"]
            elif action == "stop":
                cmd = ["powershell", f"Stop-Service -Name '{service_name}'"]
            elif action == "restart":
                cmd = ["powershell", f"Restart-Service -Name '{service_name}'"]

            result = self._run_command(cmd)
            if result["status"] == "success":
                return {
                    "status": "success",
                    "message": f"Service '{service_name}' {action}ed successfully.",
                }
            return result
        elif self.os_type == "Linux":
            # Use systemctl without sudo - elevation will be handled if needed
            cmd = ["systemctl", action, service_name]
            result = self._run_command(cmd)

            # Check if permission denied
            if (
                result.get("status") == "error"
                and "permission denied" in result.get("error", "").lower()
            ):
                # Try with elevation wrapper
                import asyncio

                from src.elevation_wrapper import execute_with_elevation

                elevation_result = asyncio.run(
                    execute_with_elevation(
                        f"systemctl {action} {service_name}",
                        operation=f"Manage service: {service_name}",
                        reason=(
                            f"Need administrator privileges to {action} the {service_name}"
                            f"service"
                        ),
                        risk_level="MEDIUM",
                    )
                )

                if elevation_result.get("success"):
                    return {
                        "status": "success",
                        "message": f"Service '{service_name}' {action}ed successfully.",
                    }
                else:
                    return {
                        "status": "error",
                        "message": elevation_result.get(
                            "error", "Failed to manage service with elevation"
                        ),
                    }

            if result["status"] == "success":
                return {
                    "status": "success",
                    "message": f"Service '{service_name}' {action}ed successfully.",
                }
            return result
        else:
            return {
                "status": "error",
                "message": "Unsupported OS for service management.",
            }

    def execute_system_command(self, command: str) -> Dict[str, Any]:
        """Executes a general system command."""
        # This is similar to execute_shell_command in worker_node,
        # but kept here for abstraction and potential future OS-specific
        # enhancements (e.g., direct API calls instead of shell)
        return self._run_command([command], shell=True)

    # --- Windows-specific (pywin32/COM - placeholders) ---
    def _windows_interact_com_app(
        self, app_name: str, action: str, **kwargs
    ) -> Dict[str, Any]:
        """
        Placeholder for interacting with COM-based applications
        like Word/Excel using pywin32. This would require pywin32 to be
        installed and specific COM object knowledge.
        """
        if self.os_type != "Windows":
            return {"status": "error", "message": "This function is Windows-specific."}

        # Example:
        # import win32com.client
        # try:
        #     app = win32com.client.Dispatch(app_name)
        #     if action == "open_document":
        #         doc_path = kwargs.get("path")
        #         app.Documents.Open(doc_path)
        #         return {"status": "success",
        #                 "message": f"Opened {doc_path} in {app_name}."}
        #     elif action == "save_document":
        #         app.ActiveDocument.SaveAs(kwargs.get("path"))
        #         return {"status": "success",
        #                 "message": f"Saved document in {app_name}."}
        #     # ... more actions
        # except Exception as e:
        #     return {"status": "error",
        #             "message": f"COM interaction failed: {e}"}
        return {
            "status": "error",
            "message": (
                f"Windows COM interaction for '{app_name}' is a "
                "placeholder. Not implemented without pywin32 and "
                "specific use case."
            ),
        }

    # --- Linux-specific (DBus - placeholders) ---
    def _linux_dbus_action(
        self, service: str, path: str, interface: str, method: str, *args
    ) -> Dict[str, Any]:
        """
        Placeholder for interacting with DBus services on Linux.
        Requires `dbus-python` or `pydbus` library.
        """
        if self.os_type != "Linux":
            return {"status": "error", "message": "This function is Linux-specific."}

        # Example using dbus-send CLI tool (simpler, no extra Python lib needed)
        # cmd = ["dbus-send", "--print-reply", "--dest", service, path,
        #        interface + "." + method] + list(args)
        # result = self._run_command(cmd)
        # return result

        # Example using pydbus (requires 'pydbus' pip package)
        # from pydbus import SystemBus
        # bus = SystemBus()
        # try:
        #     obj = bus.get(service, path)
        #     method_to_call = getattr(obj, method)
        #     response = method_to_call(*args)
        #     return {"status": "success",
        #             "response": str(response)"}
        # except Exception as e:
        #     return {"status": "error",
        #             "message": f"DBus interaction failed: {e}"}
        return {
            "status": "error",
            "message": (
                f"Linux DBus interaction for '{service}' is a "
                "placeholder. Not implemented without specific use case."
            ),
        }

    def get_process_info(
        self, process_name: Optional[str] = None, pid: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Retrieves information about running processes.
        If no arguments, lists all processes.
        """
        import psutil  # psutil is already in requirements.txt

        processes_info = []
        for proc in psutil.process_iter(
            ["pid", "name", "username", "cpu_percent", "memory_percent"]
        ):
            try:
                pinfo = proc.info
                if (
                    (process_name and process_name.lower() in pinfo["name"].lower())
                    or (pid and pinfo["pid"] == pid)
                    or (not process_name and not pid)
                ):
                    processes_info.append(pinfo)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
                logger.debug("Process access error: %s", e)

        if not processes_info and (process_name or pid):
            return {
                "status": "error",
                "message": (
                    f"No process found matching name '{process_name}' "
                    f"or PID '{pid}'."
                ),
            }

        return {"status": "success", "processes": processes_info}

    def terminate_process(self, pid: int) -> Dict[str, Any]:
        """Terminates a process by PID."""
        import psutil

        try:
            process = psutil.Process(pid)
            process.terminate()
            return {
                "status": "success",
                "message": f"Process with PID {pid} terminated.",
            }
        except psutil.NoSuchProcess:
            return {"status": "error", "message": f"No process found with PID {pid}."}
        except psutil.AccessDenied:
            return {
                "status": "error",
                "message": (
                    "Access denied to terminate process with PID "
                    f"{pid}. Requires elevated privileges."
                ),
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error terminating process {pid}: {e}",
            }

    async def web_fetch(self, url: str) -> Dict[str, Any]:
        """
        Fetches content from a specified URL and processes it into markdown.
        """
        try:
            # Ensure URL starts with http:// or https://
            if not url.startswith("http://") and not url.startswith("https://"):
                url = "https://" + url  # Default to HTTPS

            # Use singleton HTTP client for connection pooling
            http_client = get_http_client()
            async with await http_client.get(
                url, timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                # Raise an exception for HTTP errors (4xx or 5xx)
                response.raise_for_status()

                content_type = response.headers.get("Content-Type", "").lower()
                content = await response.text()

                if "text/html" in content_type:
                    markdown_content = md(content)
                    return {
                        "status": "success",
                        "url": url,
                        "content_type": "text/markdown",
                        "content": markdown_content,
                    }
                elif "text/plain" in content_type or "application/json" in content_type:
                    return {
                        "status": "success",
                        "url": url,
                        "content_type": content_type,
                        "content": content,
                    }
                else:
                    # For other content types, return a message indicating it's not text
                    return {
                        "status": "error",
                        "message": (
                            "Unsupported content type for direct text "
                            f"extraction: {content_type}"
                        ),
                        "url": url,
                    }

        except aiohttp.ClientError as e:
            return {
                "status": "error",
                "message": f"Failed to fetch URL {url}: {e}",
                "url": url,
            }
        except Exception as e:
            return {
                "status": "error",
                "message": "An unexpected error occurred during " f"web fetch: {e}",
                "url": url,
            }


# Example Usage (for testing)
if __name__ == "__main__":
    si = SystemIntegration()

    print("--- System Info ---")
    print(si.query_system_info())

    print("\n--- List Services ---")
    # This might require elevated privileges on Windows or sudo on Linux for full list
    print(si.list_services())

    print("\n--- Manage Service (Example: SSH on Linux, Spooler on Windows) ---")
    # On Linux, try: print(si.manage_service("ssh", "restart"))
    # On Windows, try: print(si.manage_service("Spooler", "stop"))
    # print(si.manage_service("nonexistent_service", "start"))

    print("\n--- Execute System Command ---")
    print(si.execute_system_command("echo Hello from system integration!"))
    print(si.execute_system_command("ls -l /tmp"))  # Linux example
    print(si.execute_system_command("dir C:\\"))  # Windows example

    print("\n--- Get Process Info ---")
    print(si.get_process_info(process_name="python"))  # Find Python processes
    # print(si.get_process_info(pid=1234)) # Find a specific PID

    print("\n--- Terminate Process (DANGEROUS - use with caution!) ---")
    # Find a PID from get_process_info and try to terminate it.
    # For example, if you have a simple script running:
    # import time
    # time.sleep(60)
    # Run this in another terminal, get its PID, then try to terminate it here.
    # print(si.terminate_process(12345))
