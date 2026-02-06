#!/usr/bin/env python3
"""
Test script for network information display
Verifies network detection and formatting without starting full worker
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from gui.utils.network_info import (
    get_network_interfaces,
    get_platform_info,
    get_primary_ip,
    format_connection_info_box,
    get_registration_config
)


def test_network_detection():
    """Test network interface detection"""
    print("=" * 70)
    print("Testing Network Interface Detection")
    print("=" * 70)

    interfaces = get_network_interfaces()

    if not interfaces:
        print("⚠ WARNING: No network interfaces detected")
        print("This may be expected on some systems or if netifaces is not installed")
        return False

    print(f"\n✓ Found {len(interfaces)} network interface(s):\n")

    for i, iface in enumerate(interfaces, 1):
        primary = " ★ PRIMARY" if iface.get('is_primary') else ""
        print(f"  {i}. {iface['type']:15} ({iface['interface']})")
        print(f"     IP: {iface['ip']}{primary}")
        print()

    return True


def test_platform_info():
    """Test platform information detection"""
    print("=" * 70)
    print("Testing Platform Information Detection")
    print("=" * 70)

    info = get_platform_info()

    print("\n✓ Platform Information:")
    print(f"  System:    {info.get('system', 'Unknown')}")
    print(f"  Release:   {info.get('release', 'Unknown')}")
    print(f"  Machine:   {info.get('machine', 'Unknown')}")
    print(f"  Processor: {info.get('processor', 'Unknown')}")

    npu_detected = info.get('npu_detected', False)
    npu_devices = info.get('npu_devices', [])

    if npu_detected:
        print(f"  NPU:       ✓ Detected ({len(npu_devices)} device(s))")
        for device in npu_devices:
            print(f"             - {device}")
    else:
        print("  NPU:       ✗ Not detected (CPU fallback)")

    print()
    return True


def test_primary_ip():
    """Test primary IP detection"""
    print("=" * 70)
    print("Testing Primary IP Detection")
    print("=" * 70)

    primary_ip = get_primary_ip()

    if primary_ip:
        print(f"\n✓ Primary IP: {primary_ip}")
    else:
        print("\n⚠ WARNING: No primary IP detected")

    print()
    return primary_ip is not None


def test_connection_info_box():
    """Test ASCII box formatting"""
    print("=" * 70)
    print("Testing Connection Info Box Formatting")
    print("=" * 70)

    worker_id = "test-npu-worker-12345678"
    port = 8082
    interfaces = get_network_interfaces()
    platform_info = get_platform_info()

    box = format_connection_info_box(
        worker_id=worker_id,
        port=port,
        interfaces=interfaces,
        platform_info=platform_info
    )

    print("\n✓ Generated Connection Info Box:\n")
    print(box)
    print()

    return True


def test_registration_config():
    """Test registration configuration generation"""
    print("=" * 70)
    print("Testing Registration Configuration Generation")
    print("=" * 70)

    config = get_registration_config(port=8082)

    print("\n✓ Generated Registration Configuration:\n")
    print(config)

    return True


def main():
    """Run all tests"""
    print("\n" + "=" * 70)
    print("Network Information Feature Test Suite")
    print("=" * 70 + "\n")

    tests = [
        ("Network Detection", test_network_detection),
        ("Platform Info", test_platform_info),
        ("Primary IP", test_primary_ip),
        ("Connection Info Box", test_connection_info_box),
        ("Registration Config", test_registration_config),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result, None))
        except Exception as e:
            results.append((test_name, False, str(e)))
            print(f"\n✗ ERROR in {test_name}: {e}\n")

    # Summary
    print("=" * 70)
    print("Test Summary")
    print("=" * 70)

    passed = sum(1 for _, result, _ in results if result)
    total = len(results)

    for test_name, result, error in results:
        if result:
            print(f"  ✓ {test_name:30} PASSED")
        else:
            print(f"  ✗ {test_name:30} FAILED")
            if error:
                print(f"    Error: {error}")

    print(f"\n  Total: {passed}/{total} tests passed")

    if passed == total:
        print("\n  🎉 All tests passed!")
    else:
        print(f"\n  ⚠ {total - passed} test(s) failed")

    print("=" * 70 + "\n")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
