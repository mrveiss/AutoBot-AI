#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Demo the research workflow scenarios
"""


def demo_research_workflow():
    """Demo the different research workflow scenarios"""

    print("=== AutoBot Research Workflow Demo ===\n")

    print("Scenario 1: Unknown topic with research enabled")
    print("User: 'tell me about quantum computing in 2024'")
    print(
        "AutoBot: I don't have specific knowledge about this topic in my knowledge base."
    )
    print("         Do you want me to research this topic? (yes/no)")
    print("         If you answer 'no', I'll end this workflow here.")
    print(
        "         If you answer 'yes', I can help research this topic with your guidance."
    )
    print()

    print("Scenario 2: User says 'yes' to research")
    print("User: 'yes'")
    print(
        "AutoBot: Great! I'll help you research this topic. Please provide more details"
    )
    print("         about what specifically you'd like me to look into, or guide me to")
    print("         specific sources you'd like me to check.")
    print()

    print("Scenario 3: User says 'no' to research")
    print("User: 'no'")
    print(
        "AutoBot: Understood. I don't have information about this topic in my knowledge"
    )
    print("         base, so I'll end this workflow here. Feel free to ask me about")
    print("         something else!")
    print()

    print("Scenario 4: Research agent disabled")
    print("User: 'tell me about quantum computing in 2024'")
    print(
        "AutoBot: I don't have specific knowledge about this topic in my knowledge base."
    )
    print("         Currently, the research agent is disabled in settings. I can only")
    print(
        "         provide information from my local knowledge base and documentation files."
    )
    print()

    print("Scenario 5: Research agent unavailable")
    print("User: 'tell me about quantum computing in 2024'")
    print(
        "AutoBot: I don't have specific knowledge about this topic in my knowledge base."
    )
    print("         Currently, the research agent is not available. I can only provide")
    print("         information from my local knowledge base and documentation files.")
    print()

    print("=== Key Features ===")
    print("✅ Simple yes/no dialogue for research requests")
    print("✅ Clear workflow termination when user says 'no'")
    print("✅ Proper handling when research agent disabled/unavailable")
    print("✅ No automatic research execution - user controlled")
    print("✅ Research agent is subordinate to librarian")


if __name__ == "__main__":
    demo_research_workflow()
