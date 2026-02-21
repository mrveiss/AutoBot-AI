"""
Network Information Utility
Detects and formats network interface information for the NPU worker
"""

import logging
import platform
import socket
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def get_network_interfaces() -> List[Dict[str, str]]:
    """
    Get all network interfaces with IP addresses

    Returns:
        List of dicts with 'interface', 'ip', and 'type' keys
    """
    interfaces = []

    try:
        # Try using netifaces if available (more detailed info)
        import netifaces

        for iface_name in netifaces.interfaces():
            addrs = netifaces.ifaddresses(iface_name)

            # Get IPv4 addresses
            if netifaces.AF_INET in addrs:
                for addr_info in addrs[netifaces.AF_INET]:
                    ip = addr_info.get("addr")
                    if ip and not ip.startswith("127."):
                        iface_type = _get_interface_type(iface_name)
                        interfaces.append(
                            {
                                "interface": iface_name,
                                "ip": ip,
                                "type": iface_type,
                                "is_primary": _is_primary_interface(ip),
                            }
                        )

    except ImportError:
        # Fallback to socket-based detection
        interfaces = _get_interfaces_fallback()

    # Sort by primary interface first
    interfaces.sort(key=lambda x: (not x.get("is_primary", False), x["interface"]))

    return interfaces


def _get_interfaces_fallback() -> List[Dict[str, str]]:
    """Fallback network detection using socket module"""
    interfaces = []

    try:
        # Get hostname and all associated IPs
        hostname = socket.gethostname()

        # Try to get all IP addresses
        try:
            addr_infos = socket.getaddrinfo(hostname, None, socket.AF_INET)
            seen_ips = set()

            for addr_info in addr_infos:
                ip = addr_info[4][0]
                if ip and not ip.startswith("127.") and ip not in seen_ips:
                    seen_ips.add(ip)
                    interfaces.append(
                        {
                            "interface": "Unknown",
                            "ip": ip,
                            "type": "Network",
                            "is_primary": True,
                        }
                    )
        except Exception:
            logger.debug("Suppressed exception in try block", exc_info=True)

        # Also try getting IP by connecting to external address
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect(("8.8.8.8", 80))
            local_ip = sock.getsockname()[0]

            if local_ip and not local_ip.startswith("127."):
                # Check if we already have this IP
                if not any(iface["ip"] == local_ip for iface in interfaces):
                    interfaces.append(
                        {
                            "interface": "Primary",
                            "ip": local_ip,
                            "type": "Network",
                            "is_primary": True,
                        }
                    )
        except Exception:
            logger.debug("Suppressed exception in try block", exc_info=True)
        finally:
            # Proper socket cleanup to prevent resource leak
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    logger.debug("Suppressed exception in try block", exc_info=True)

    except Exception:
        logger.debug("Suppressed exception in try block", exc_info=True)

    return interfaces


def _get_interface_type(interface_name: str) -> str:
    """Determine interface type from name"""
    name_lower = interface_name.lower()

    if "eth" in name_lower or "ethernet" in name_lower:
        return "Ethernet"
    elif "wi-fi" in name_lower or "wlan" in name_lower or "wireless" in name_lower:
        return "Wi-Fi"
    elif "wsl" in name_lower or "veth" in name_lower:
        return "WSL Bridge"
    elif "docker" in name_lower or "br-" in name_lower:
        return "Docker Bridge"
    elif "vmware" in name_lower or "virtualbox" in name_lower:
        return "Virtual"
    else:
        return "Network"


def _is_primary_interface(ip: str) -> bool:
    """Determine if this is likely the primary interface based on IP"""
    # Common private network ranges
    # Prioritize 192.168.x.x and 172.16-31.x.x ranges
    if ip.startswith("192.168.") or ip.startswith("172.16."):
        return True
    return False


def get_primary_ip() -> Optional[str]:
    """Get the primary IP address for backend connectivity"""
    interfaces = get_network_interfaces()

    if not interfaces:
        return None

    # Return first primary interface, or just first interface
    for iface in interfaces:
        if iface.get("is_primary"):
            return iface["ip"]

    return interfaces[0]["ip"] if interfaces else None


def get_platform_info() -> Dict[str, str]:
    """Get platform information"""
    system = platform.system()
    release = platform.release()
    version = platform.version()

    # Windows 11 detection: Windows 11 reports as version 10 but build >= 22000
    # Example version string: "10.0.22631" (Windows 11 23H2)
    if system == "Windows" and release == "10":
        try:
            # Parse build number from version string (e.g., "10.0.22631")
            parts = version.split(".")
            if len(parts) >= 3:
                build_number = int(parts[2])
                if build_number >= 22000:
                    release = "11"
        except (ValueError, IndexError):
            pass

    info = {
        "system": system,
        "release": release,
        "version": version,
        "machine": platform.machine(),
        "processor": platform.processor(),
    }

    # Check for NPU availability using ONNX Runtime + OpenVINO EP
    # Issue #640: Uses OpenVINO Execution Provider for proper Intel NPU support.
    # DirectML doesn't expose Intel NPUs - OpenVINO EP has explicit NPU device option.
    try:
        import onnxruntime as ort

        providers = ort.get_available_providers()
        info["available_providers"] = providers

        # Check for OpenVINO EP (preferred for Intel NPU)
        has_openvino = "OpenVINOExecutionProvider" in providers
        has_directml = "DmlExecutionProvider" in providers
        has_cuda = "CUDAExecutionProvider" in providers

        npu_devices = []

        # OpenVINO EP can detect NPU, GPU, CPU
        if has_openvino:
            try:
                from openvino import Core

                core = Core()
                available_devices = core.available_devices
                info["openvino_devices"] = available_devices

                if "NPU" in available_devices:
                    npu_devices.append("Intel NPU (OpenVINO)")
                    info["npu_detected"] = True
                elif "GPU" in available_devices:
                    npu_devices.append("Intel GPU (OpenVINO)")
                    info["npu_detected"] = True
                else:
                    info["npu_detected"] = False
            except ImportError:
                # OpenVINO EP available but Core not installed
                npu_devices.append("OpenVINO EP (auto-detect)")
                info["npu_detected"] = True
        elif has_directml:
            # DirectML as fallback (GPU only, not NPU)
            npu_devices.append("DirectML (GPU only)")
            info["npu_detected"] = True
        elif has_cuda:
            npu_devices.append("CUDA (NVIDIA GPU)")
            info["npu_detected"] = True
        else:
            info["npu_detected"] = False

        info["npu_devices"] = npu_devices
    except Exception:
        info["npu_detected"] = False
        info["npu_devices"] = []
        info["available_providers"] = []

    return info


def format_connection_info_box(
    worker_id: str,
    port: int,
    interfaces: List[Dict[str, str]],
    platform_info: Dict[str, str],
) -> str:
    """
    Format connection information as ASCII box

    Args:
        worker_id: Worker identifier
        port: Service port number
        interfaces: List of network interfaces
        platform_info: Platform information dict

    Returns:
        Formatted ASCII box string
    """
    # Build platform description
    system = platform_info.get("system", "Unknown")
    release = platform_info.get("release", "")
    npu_detected = platform_info.get("npu_detected", False)
    npu_status = "NPU Detected" if npu_detected else "CPU Only"

    platform_desc = f"{system} {release} ({npu_status})"

    # Get primary IP for registration URL
    primary_ip = get_primary_ip() or "N/A"
    registration_url = f"http://{primary_ip}:{port}"
    health_url = f"{registration_url}/health"

    # Build the box content
    lines = [
        "AutoBot NPU Worker - Connection Info",
        "=" * 55,
        f"Worker ID:    {worker_id}",
        f"Platform:     {platform_desc}",
        f"Port:         {port}",
        "",
        "Network Interfaces:",
    ]

    # Add interface information
    if interfaces:
        for iface in interfaces:
            iface_name = iface["interface"]
            iface_type = iface["type"]
            iface_ip = iface["ip"]
            primary_mark = " ★" if iface.get("is_primary") else ""
            lines.append(
                f"  • {iface_type:15} ({iface_name}): {iface_ip}{primary_mark}"
            )
    else:
        lines.append("  (No network interfaces detected)")

    lines.extend(
        [
            "",
            "Add to Backend Settings:",
            f"  URL: {registration_url}",
            "",
            f"Health Check: {health_url}",
        ]
    )

    # Calculate box width
    max_width = max(len(line) for line in lines)
    box_width = max_width + 4

    # Build the box
    box_lines = ["╔" + "═" * (box_width - 2) + "╗"]

    for line in lines:
        padding = box_width - len(line) - 4
        box_lines.append(f"║ {line}{' ' * padding} ║")

    box_lines.append("╚" + "═" * (box_width - 2) + "╝")

    return "\n".join(box_lines)


def get_registration_config(port: int) -> str:
    """
    Get backend registration configuration snippet

    Args:
        port: Service port number

    Returns:
        Configuration text to copy to backend settings
    """
    primary_ip = get_primary_ip() or "REPLACE_WITH_IP"

    config = f"""# Windows NPU Worker Configuration
# Add this to your backend NPU worker settings

windows_npu_worker:
  enabled: true
  url: http://{primary_ip}:{port}
  health_check_interval: 60
  timeout: 30
"""

    return config
