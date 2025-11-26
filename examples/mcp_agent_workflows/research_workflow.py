#!/usr/bin/env python3
"""
Research Workflow Example

Demonstrates multi-step workflow using:
1. Knowledge base search (knowledge_mcp)
2. Structured thinking to organize findings (structured_thinking_mcp)
3. File writing for documentation (filesystem_mcp)

Issue: #48 - LangChain Agent Integration Examples for MCP Tools
"""

import asyncio
import json
from typing import Any, Dict, List

from base import (
    WorkflowResult,
    call_mcp_tool,
    ensure_directory_exists,
    format_iso_timestamp,
    generate_session_id,
    write_file_safe,
)


async def research_and_document(topic: str, output_path: str) -> Dict[str, Any]:
    """
    Multi-step research workflow:
    1. Search knowledge base for topic
    2. Use structured thinking to organize findings
    3. Write research report to file

    Args:
        topic: Research topic to investigate
        output_path: Path to save research report

    Returns:
        Workflow results including search results, thinking process, and file path
    """
    print(f"\n{'='*60}")
    print(f"RESEARCH WORKFLOW: {topic}")
    print(f"{'='*60}")

    workflow = WorkflowResult("research_workflow")

    # Step 1: Search Knowledge Base
    print("\n📚 Step 1: Searching knowledge base...")
    try:
        search_results = await call_mcp_tool(
            "knowledge_mcp",
            "search_knowledge_base",
            {"query": topic, "top_k": 10},
        )
        workflow.add_step("knowledge_search", "success", search_results)
        print(f"   Found {len(search_results.get('results', []))} relevant entries")
    except Exception as e:
        workflow.add_step("knowledge_search", "error", error=str(e))
        print(f"   ❌ Search failed: {e}")
        search_results = {"results": []}

    # Step 2: Organize with Structured Thinking
    print("\n🧠 Step 2: Organizing findings with structured thinking...")
    session_id = generate_session_id("research")
    thinking_stages = ["problem_definition", "research", "analysis", "synthesis", "conclusion"]

    thinking_results = []
    for stage in thinking_stages:
        try:
            thought_content = generate_thought_for_stage(stage, topic, search_results)
            thought_result = await call_mcp_tool(
                "structured_thinking_mcp",
                "process_thought",
                {
                    "stage": stage,
                    "thought": thought_content,
                    "session_id": session_id,
                },
            )
            thinking_results.append(thought_result)
            print(f"   ✅ {stage}: processed")
        except Exception as e:
            print(f"   ❌ {stage}: {e}")
            thinking_results.append({"error": str(e), "stage": stage})

    workflow.add_step("structured_thinking", "success", thinking_results)

    # Step 3: Generate Summary
    print("\n📝 Step 3: Generating research summary...")
    try:
        summary = await call_mcp_tool(
            "structured_thinking_mcp",
            "generate_summary",
            {"session_id": session_id},
        )
        workflow.add_step("generate_summary", "success", summary)
    except Exception as e:
        summary = {"summary": f"Error generating summary: {e}"}
        workflow.add_step("generate_summary", "error", error=str(e))

    # Step 4: Write Research Report
    print("\n💾 Step 4: Writing research report...")
    report_content = format_research_report(topic, search_results, thinking_results, summary)

    success = await write_file_safe(output_path, report_content)
    if success:
        workflow.add_step("write_report", "success", {"path": output_path})
        print(f"   ✅ Report saved to: {output_path}")
    else:
        workflow.add_step("write_report", "error", error="Write operation failed")
        print("   ❌ Write failed")

    workflow.complete()

    print(f"\n{'='*60}")
    print("WORKFLOW COMPLETE")
    print(f"{'='*60}")

    return workflow.to_dict()


def generate_thought_for_stage(
    stage: str, topic: str, search_results: Dict[str, Any]
) -> str:
    """Generate appropriate thought content for each thinking stage"""
    num_results = len(search_results.get("results", []))

    thoughts = {
        "problem_definition": (
            f"Researching topic: '{topic}'. "
            f"Goal: Compile comprehensive information from knowledge base. "
            f"Found {num_results} relevant entries to analyze."
        ),
        "research": (
            f"Analyzing {num_results} knowledge base entries for '{topic}'. "
            "Extracting key concepts, patterns, and relationships. "
            "Identifying gaps in current knowledge."
        ),
        "analysis": (
            f"Evaluating quality and relevance of findings about '{topic}'. "
            "Categorizing information by theme. "
            "Assessing confidence levels of each finding."
        ),
        "synthesis": (
            f"Synthesizing findings about '{topic}' into coherent narrative. "
            "Connecting related concepts. "
            "Building comprehensive understanding from individual pieces."
        ),
        "conclusion": (
            f"Research on '{topic}' complete. "
            f"Key insights: {num_results} sources analyzed. "
            "Ready to generate final report with structured findings."
        ),
    }

    return thoughts.get(stage, f"Processing {stage} for {topic}")


def format_research_report(
    topic: str,
    search_results: Dict[str, Any],
    thinking_results: List[Dict[str, Any]],
    summary: Dict[str, Any],
) -> str:
    """Format research findings into a markdown report"""
    timestamp = format_iso_timestamp()

    report = f"""# Research Report: {topic}

**Generated**: {timestamp}
**Author**: AutoBot Research Agent
**Issue**: #48 - LangChain Agent Integration Examples

---

## Executive Summary

{summary.get('summary', 'No summary available')}

---

## Knowledge Base Findings

Total entries found: {len(search_results.get('results', []))}

"""

    # Add search results
    for i, result in enumerate(search_results.get("results", []), 1):
        report += f"""### Finding #{i}

{result.get('content', 'No content')}

**Relevance Score**: {result.get('score', 'N/A')}

---

"""

    # Add thinking process
    report += """## Structured Thinking Process

"""
    stages = ["problem_definition", "research", "analysis", "synthesis", "conclusion"]
    for i, (stage, result) in enumerate(zip(stages, thinking_results), 1):
        report += f"""### Stage {i}: {stage.replace('_', ' ').title()}

{result.get('thought', result.get('error', 'No data'))}

"""

    # Footer
    report += """---

## Methodology

This research was conducted using AutoBot's MCP tool ecosystem:
- **Knowledge MCP**: Vector similarity search over knowledge base
- **Structured Thinking MCP**: 5-stage cognitive framework for organization
- **Filesystem MCP**: Secure file output generation

---

*Report generated by AutoBot MCP Agent Workflow*
"""

    return report


async def main():
    """Main entry point for research workflow example"""

    # Example: Research error handling patterns
    topic = "error handling patterns in Python"
    output_path = "/tmp/autobot/research_report.md"

    # Ensure output directory exists
    await ensure_directory_exists("/tmp/autobot")

    # Run research workflow
    results = await research_and_document(topic, output_path)

    # Print summary
    print("\nWorkflow Results Summary:")
    print(f"  Workflow: {results.get('workflow')}")
    print(f"  Success: {results.get('success')}")
    print(f"  Total Steps: {results.get('total_steps')}")
    print(f"  Successful Steps: {results.get('successful_steps')}")

    # Save workflow results
    results_path = "/tmp/autobot/research_workflow_results.json"
    await write_file_safe(results_path, json.dumps(results, indent=2, default=str))
    print(f"\nDetailed results saved to: {results_path}")


if __name__ == "__main__":
    asyncio.run(main())
