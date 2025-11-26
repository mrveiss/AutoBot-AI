#!/usr/bin/env python3
"""
Code Analysis Workflow Example

Demonstrates multi-step workflow using:
1. File system navigation (filesystem_mcp)
2. Sequential thinking for analysis (sequential_thinking_mcp)
3. Knowledge base updates (knowledge_mcp)

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


async def analyze_codebase(directory: str, file_pattern: str = "*.py") -> Dict[str, Any]:
    """
    Multi-step code analysis workflow:
    1. Search files matching pattern
    2. Read relevant files
    3. Use sequential thinking to analyze code
    4. Add findings to knowledge base

    Args:
        directory: Directory to analyze
        file_pattern: File pattern to match (default: *.py)

    Returns:
        Analysis results including file list, code analysis, and knowledge updates
    """
    print(f"\n{'='*60}")
    print(f"CODE ANALYSIS WORKFLOW: {directory}")
    print(f"{'='*60}")

    workflow = WorkflowResult("code_analysis")

    # Step 1: Search for Files
    print(f"\n🔍 Step 1: Searching for {file_pattern} files...")
    try:
        search_result = await call_mcp_tool(
            "filesystem_mcp",
            "search_files",
            {"path": directory, "pattern": file_pattern},
        )
        files_found = search_result.get("files", [])
        workflow.add_step("search_files", "success", {"files": files_found})
        print(f"   Found {len(files_found)} files")
    except Exception as e:
        workflow.add_step("search_files", "error", error=str(e))
        print(f"   ❌ Search failed: {e}")
        return workflow.to_dict()

    # Limit to first 5 files for analysis
    files_to_analyze = files_found[:5]
    print(f"   Analyzing first {len(files_to_analyze)} files...")

    # Step 2: Read File Contents
    print("\n📖 Step 2: Reading file contents...")
    file_contents = {}
    for file_path in files_to_analyze:
        try:
            content_result = await call_mcp_tool(
                "filesystem_mcp",
                "read_text_file",
                {"path": file_path},
            )
            file_contents[file_path] = content_result.get("content", "")[:2000]  # First 2000 chars
            print(f"   ✅ Read: {file_path.split('/')[-1]}")
        except Exception as e:
            print(f"   ❌ Failed to read {file_path}: {e}")
            file_contents[file_path] = f"Error reading file: {e}"

    workflow.add_step(
        "read_files",
        "success",
        {"files_read": len(file_contents)},
    )

    # Step 3: Sequential Thinking Analysis
    print("\n🧠 Step 3: Analyzing code with sequential thinking...")
    session_id = generate_session_id("code_analysis")
    analysis_thoughts = []

    total_thoughts = 5
    for thought_num in range(1, total_thoughts + 1):
        try:
            thought_content = generate_analysis_thought(
                thought_num, total_thoughts, files_to_analyze, file_contents
            )
            thought_result = await call_mcp_tool(
                "sequential_thinking_mcp",
                "sequential_thinking",
                {
                    "thought": thought_content,
                    "thought_number": thought_num,
                    "total_thoughts": total_thoughts,
                    "next_thought_needed": thought_num < total_thoughts,
                    "session_id": session_id,
                },
            )
            analysis_thoughts.append(thought_result)
            print(f"   ✅ Thought {thought_num}/{total_thoughts} processed")
        except Exception as e:
            print(f"   ❌ Thought {thought_num} failed: {e}")
            analysis_thoughts.append({"error": str(e)})

    workflow.add_step(
        "sequential_thinking",
        "success",
        {"thoughts": analysis_thoughts},
    )

    # Step 4: Update Knowledge Base
    print("\n📚 Step 4: Updating knowledge base with findings...")
    findings_summary = compile_findings(directory, files_to_analyze, analysis_thoughts)

    try:
        kb_result = await call_mcp_tool(
            "knowledge_mcp",
            "add_documents",
            {
                "documents": [findings_summary],
                "metadata": {
                    "type": "code_analysis",
                    "directory": directory,
                    "timestamp": format_iso_timestamp(),
                    "files_analyzed": len(files_to_analyze),
                },
            },
        )
        workflow.add_step("update_knowledge", "success", kb_result)
        print("   ✅ Knowledge base updated with analysis findings")
    except Exception as e:
        workflow.add_step("update_knowledge", "error", error=str(e))
        print(f"   ❌ Knowledge update failed: {e}")

    # Step 5: Generate Analysis Report
    print("\n📊 Step 5: Generating analysis report...")
    report = generate_analysis_report(
        directory, files_to_analyze, file_contents, analysis_thoughts
    )
    workflow.add_step("generate_report", "success", {"report_length": len(report)})

    workflow.complete()

    # Add report to results
    result_dict = workflow.to_dict()
    result_dict["report"] = report

    print(f"\n{'='*60}")
    print("WORKFLOW COMPLETE")
    print(f"{'='*60}")

    return result_dict


def generate_analysis_thought(
    thought_num: int,
    total_thoughts: int,
    files: List[str],
    contents: Dict[str, str],
) -> str:
    """Generate appropriate thought for each analysis step"""

    if thought_num == 1:
        return (
            f"Beginning code analysis. Found {len(files)} files to analyze. "
            f"Files include: {', '.join(f.split('/')[-1] for f in files)}. "
            "Will examine structure, patterns, and potential issues."
        )

    elif thought_num == 2:
        # Analyze structure
        file_sizes = {f.split("/")[-1]: len(contents.get(f, "")) for f in files}
        return (
            f"Analyzing file sizes and structure. "
            f"Size distribution: {json.dumps(file_sizes)}. "
            "Looking for code organization patterns and potential complexity."
        )

    elif thought_num == 3:
        # Look for patterns
        patterns = []
        for content in contents.values():
            if "def " in content:
                patterns.append("functions")
            if "class " in content:
                patterns.append("classes")
            if "import " in content:
                patterns.append("imports")
            if "async " in content:
                patterns.append("async code")
            if "try:" in content:
                patterns.append("error handling")

        unique_patterns = list(set(patterns))
        return (
            f"Identified code patterns: {', '.join(unique_patterns)}. "
            "Analyzing code quality indicators and best practices adherence."
        )

    elif thought_num == 4:
        # Identify potential issues
        issues = []
        for content in contents.values():
            if len(content) > 1500:
                issues.append("large files")
            if "TODO" in content or "FIXME" in content:
                issues.append("TODOs/FIXMEs present")
            if "pass" in content:
                issues.append("empty blocks")

        unique_issues = list(set(issues))
        return (
            f"Potential issues identified: {', '.join(unique_issues) if unique_issues else 'None'}. "
            "Evaluating overall code quality and maintainability."
        )

    else:  # thought_num == 5
        return (
            f"Analysis complete. Analyzed {len(files)} files. "
            "Key findings: Code follows Python patterns, "
            f"contains {sum(c.count('def ') for c in contents.values())} functions, "
            f"{sum(c.count('class ') for c in contents.values())} classes. "
            "Recommendations: Continue following established patterns, "
            "address any TODOs, maintain consistent documentation."
        )


def compile_findings(
    directory: str, files: List[str], thoughts: List[Dict[str, Any]]
) -> str:
    """Compile analysis findings into a knowledge base entry"""

    findings = f"""
Code Analysis Findings for {directory}

Timestamp: {format_iso_timestamp()}
Files Analyzed: {len(files)}

Files:
{chr(10).join('- ' + f for f in files)}

Key Insights:
"""

    for i, thought in enumerate(thoughts, 1):
        if "error" not in thought:
            findings += f"\nThought {i}: {thought.get('thought', 'No content')[:200]}"

    findings += """

Analysis completed using AutoBot Sequential Thinking MCP.
This entry provides insights into code structure, patterns, and potential improvements.
"""

    return findings


def generate_analysis_report(
    directory: str,
    files: List[str],
    contents: Dict[str, str],
    thoughts: List[Dict[str, Any]],
) -> str:
    """Generate formatted analysis report"""

    report = f"""
# Code Analysis Report

**Directory**: {directory}
**Timestamp**: {format_iso_timestamp()}
**Files Analyzed**: {len(files)}

## Files

"""
    for f in files:
        report += f"- `{f}`\n"

    report += "\n## Sequential Thinking Analysis\n\n"

    for i, thought in enumerate(thoughts, 1):
        report += f"### Thought {i}\n\n"
        if "error" in thought:
            report += f"Error: {thought['error']}\n\n"
        else:
            report += f"{thought.get('thought', 'No content')}\n\n"

    report += """
## Recommendations

1. Review identified patterns for consistency
2. Address any TODO/FIXME comments
3. Consider refactoring large files
4. Ensure proper error handling throughout
5. Maintain consistent documentation

---

*Generated by AutoBot Code Analysis Workflow*
"""

    return report


async def main():
    """Main entry point for code analysis workflow example"""

    # Example: Analyze backend API directory
    directory = "/home/kali/Desktop/AutoBot/backend/api"
    file_pattern = "*.py"

    # Run code analysis workflow
    results = await analyze_codebase(directory, file_pattern)

    # Print summary
    print("\n" + "=" * 60)
    print("ANALYSIS REPORT")
    print("=" * 60)
    print(results.get("report", "No report generated"))

    # Save results
    await ensure_directory_exists("/tmp/autobot")
    output_path = "/tmp/autobot/code_analysis_results.json"

    # Remove report from JSON (already printed)
    results_for_json = {k: v for k, v in results.items() if k != "report"}
    await write_file_safe(output_path, json.dumps(results_for_json, indent=2, default=str))
    print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
