#!/usr/bin/env python3
"""
VNC Monitoring Workflow Example

Demonstrates multi-step workflow using:
1. VNC status checking (vnc_mcp)
2. Browser context monitoring (vnc_mcp)
3. Activity logging to file (filesystem_mcp)

Issue: #48 - LangChain Agent Integration Examples for MCP Tools
"""

import asyncio
from typing import Any, Dict

from base import (
    WorkflowResult,
    call_mcp_tool,
    ensure_directory_exists,
    format_iso_timestamp,
    generate_session_id,
    write_file_safe,
)


async def monitor_browser_activity(
    monitoring_duration_seconds: int = 30, check_interval: int = 10
) -> Dict[str, Any]:
    """
    Multi-step VNC monitoring workflow:
    1. Check VNC status
    2. Observe browser activity
    3. Get browser context
    4. Log findings to file

    Args:
        monitoring_duration_seconds: How long to monitor (default: 30 seconds)
        check_interval: Seconds between checks (default: 10)

    Returns:
        Monitoring results including VNC status, activity observations, and log file path
    """
    print(f"\n{'='*60}")
    print("VNC MONITORING WORKFLOW")
    print(f"Duration: {monitoring_duration_seconds}s, Interval: {check_interval}s")
    print(f"{'='*60}")

    workflow = WorkflowResult("vnc_monitoring")
    observations = []

    # Step 1: Initial VNC Status Check
    print("\n🖥️ Step 1: Checking VNC status...")
    try:
        vnc_status = await call_mcp_tool("vnc_mcp", "vnc_status", {})
        workflow.add_step("vnc_status", "success", vnc_status)
        print(f"   VNC Status: {vnc_status.get('status', 'unknown')}")
        print(f"   Desktop Size: {vnc_status.get('desktop_size', 'N/A')}")
        print(f"   Connected Clients: {vnc_status.get('connected_clients', 0)}")
    except Exception as e:
        workflow.add_step("vnc_status", "error", error=str(e))
        print(f"   ❌ VNC status check failed: {e}")
        vnc_status = {}

    # Step 2: Monitor Activity Loop
    print(f"\n📊 Step 2: Monitoring activity for {monitoring_duration_seconds} seconds...")
    num_checks = monitoring_duration_seconds // check_interval

    for i in range(num_checks):
        check_time = format_iso_timestamp()
        print(f"\n   Check #{i+1}/{num_checks} at {check_time}")

        observation = {
            "check_number": i + 1,
            "timestamp": check_time,
            "activity": None,
            "browser_context": None,
        }

        # Observe desktop activity
        try:
            activity = await call_mcp_tool("vnc_mcp", "observe_activity", {})
            observation["activity"] = activity
            print(f"   📸 Activity captured: {activity.get('description', 'N/A')[:50]}...")
        except Exception as e:
            print(f"   ❌ Activity observation failed: {e}")
            observation["activity"] = {"error": str(e)}

        # Get browser context
        try:
            browser_ctx = await call_mcp_tool("vnc_mcp", "browser_context", {})
            observation["browser_context"] = browser_ctx
            print(f"   🌐 Browser: {browser_ctx.get('current_url', 'N/A')[:50]}...")
        except Exception as e:
            print(f"   ❌ Browser context failed: {e}")
            observation["browser_context"] = {"error": str(e)}

        observations.append(observation)

        # Wait for next check (except on last iteration)
        if i < num_checks - 1:
            print(f"   ⏳ Waiting {check_interval}s...")
            await asyncio.sleep(check_interval)

    workflow.add_step(
        "activity_monitoring",
        "success",
        {"total_checks": num_checks, "observations": observations},
    )

    # Step 3: Generate Activity Log
    print("\n📝 Step 3: Generating activity log...")
    log_content = generate_activity_log(workflow, vnc_status, observations)

    # Step 4: Write Log to File
    print("\n💾 Step 4: Writing activity log to file...")
    session_id = generate_session_id("vnc_activity")
    log_path = f"/tmp/autobot/{session_id}.md"

    await ensure_directory_exists("/tmp/autobot")

    success = await write_file_safe(log_path, log_content)
    if success:
        workflow.add_step("write_log", "success", {"path": log_path})
        print(f"   ✅ Log saved to: {log_path}")
    else:
        workflow.add_step("write_log", "error", error="Write operation failed")
        print("   ❌ Log write failed")

    workflow.complete()

    print(f"\n{'='*60}")
    print("MONITORING WORKFLOW COMPLETE")
    print(f"{'='*60}")

    return workflow.to_dict()


def generate_activity_log(
    workflow: WorkflowResult,
    vnc_status: Dict[str, Any],
    observations: list,
) -> str:
    """Generate formatted activity log"""

    log = f"""# VNC Activity Monitoring Log

**Start Time**: {workflow.start_time}
**End Time**: {workflow.end_time or 'In Progress'}
**Duration**: {len(observations) * 10} seconds (approx)
**Check Interval**: 10 seconds
**Total Observations**: {len(observations)}

---

## Initial VNC Status

"""

    # Add VNC status
    if vnc_status:
        log += f"""- **Status**: {vnc_status.get('status', 'unknown')}
- **Desktop Size**: {vnc_status.get('desktop_size', 'N/A')}
- **Connected Clients**: {vnc_status.get('connected_clients', 0)}
- **Streaming**: {vnc_status.get('streaming', False)}

"""
    else:
        log += "**Error**: VNC status check failed\n\n"

    log += "---\n\n## Activity Observations\n\n"

    # Add each observation
    for obs in observations:
        log += f"""### Observation #{obs.get('check_number', 'N/A')}

**Timestamp**: {obs.get('timestamp', 'N/A')}

**Desktop Activity**:
"""
        activity = obs.get("activity", {})
        if "error" in activity:
            log += f"Error: {activity['error']}\n"
        else:
            log += f"""- Description: {activity.get('description', 'N/A')}
- Active Window: {activity.get('active_window', 'N/A')}
- Mouse Position: {activity.get('mouse_position', 'N/A')}
- Recent Actions: {activity.get('recent_actions', [])}
"""

        log += "\n**Browser Context**:\n"
        browser = obs.get("browser_context", {})
        if "error" in browser:
            log += f"Error: {browser['error']}\n"
        else:
            log += f"""- Current URL: {browser.get('current_url', 'N/A')}
- Page Title: {browser.get('page_title', 'N/A')}
- Tabs Open: {browser.get('tabs_count', 0)}
- Loading: {browser.get('is_loading', False)}
"""

        log += "\n---\n\n"

    # Summary
    log += """## Summary

This monitoring session captured desktop and browser activity using AutoBot's VNC MCP bridge.

**Key Metrics**:
"""

    total_checks = len(observations)
    successful_activity = sum(
        1
        for obs in observations
        if "error" not in obs.get("activity", {})
    )
    successful_browser = sum(
        1
        for obs in observations
        if "error" not in obs.get("browser_context", {})
    )

    log += f"""- Total Checks: {total_checks}
- Successful Activity Captures: {successful_activity}/{total_checks}
- Successful Browser Context Captures: {successful_browser}/{total_checks}

---

*Generated by AutoBot VNC Monitoring Workflow*
*MCP Tools Used: vnc_status, observe_activity, browser_context, write_file*
"""

    return log


async def main():
    """Main entry point for VNC monitoring workflow example"""

    # Monitor for 30 seconds, checking every 10 seconds
    results = await monitor_browser_activity(
        monitoring_duration_seconds=30, check_interval=10
    )

    # Print summary
    print("\nMonitoring Summary:")
    print(f"  Workflow: {results.get('workflow')}")
    print(f"  Success: {results.get('success')}")
    print(f"  Total Steps: {results.get('total_steps')}")
    print(f"  Successful Steps: {results.get('successful_steps')}")

    # Show log file location
    for step in results.get("steps", []):
        if step.get("step") == "write_log" and step.get("status") == "success":
            print(f"\n  Activity log saved to: {step.get('data', {}).get('path')}")


if __name__ == "__main__":
    asyncio.run(main())
