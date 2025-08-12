#!/usr/bin/env python3
"""
AutoBot Classification Management Utility
Manage workflow classification keywords and rules in Redis
"""

import sys
import json
from pathlib import Path

# Add AutoBot to Python path
sys.path.append(str(Path(__file__).parent))

from src.workflow_classifier import WorkflowClassifier


def main():
    classifier = WorkflowClassifier()
    
    print("🤖 AutoBot Classification Management")
    print("=" * 50)
    
    # Show current statistics
    stats = classifier.get_classification_stats()
    print("📊 Current Statistics:")
    print(f"   Categories: {stats.get('total_categories', 0)}")
    print(f"   Keywords: {stats.get('total_keywords', 0)}")
    print(f"   Rules: {stats.get('total_rules', 0)}")
    print()
    
    # Show categories and keywords
    print("📝 Categories and Keywords:")
    for category, count in stats.get('categories', {}).items():
        keywords = classifier.get_keywords(category)
        print(f"   {category}: {keywords}")
    print()
    
    # Interactive management
    while True:
        print("Actions:")
        print("1. Add keywords to category")
        print("2. Test message classification")
        print("3. Show statistics")
        print("4. Add security keywords")
        print("5. Exit")
        
        choice = input("\nChoice (1-5): ").strip()
        
        if choice == "1":
            category = input("Enter category: ").strip()
            keywords_input = input("Enter keywords (comma-separated): ").strip()
            if category and keywords_input:
                keywords = [kw.strip() for kw in keywords_input.split(",")]
                classifier.add_keywords(category, keywords)
                print(f"✅ Added {len(keywords)} keywords to {category}")
        
        elif choice == "2":
            message = input("Enter message to classify: ").strip()
            if message:
                complexity = classifier.classify_request(message)
                print(f"📋 Classification: {complexity.value}")
        
        elif choice == "3":
            stats = classifier.get_classification_stats()
            print(json.dumps(stats, indent=2))
        
        elif choice == "4":
            # Add common security keywords
            security_keywords = [
                "pentest", "vulnerability", "malware", "threat", "attack",
                "breach", "intrusion", "forensics", "hardening", "compliance"
            ]
            classifier.add_keywords("security", security_keywords)
            
            network_keywords = [
                "subnet", "vlan", "dns", "dhcp", "proxy", "gateway",
                "switch", "hub", "wireless", "ethernet"
            ]
            classifier.add_keywords("network", network_keywords)
            
            print("✅ Added extended security and network keywords")
        
        elif choice == "5":
            print("👋 Goodbye!")
            break
        
        else:
            print("❌ Invalid choice")
        
        print()


if __name__ == "__main__":
    main()