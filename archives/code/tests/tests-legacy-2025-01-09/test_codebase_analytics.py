#!/usr/bin/env python3
"""
Test script for the real codebase analytics system
Tests the actual API endpoints with the AutoBot codebase
"""

import asyncio
import json
import requests
import time
from pathlib import Path

# Configuration
BACKEND_URL = "http://172.16.168.20:8001"  # Main machine backend
CODEBASE_PATH = "/home/kali/Desktop/AutoBot"

async def test_codebase_analytics():
    """Test the codebase analytics API endpoints"""

    print("🔍 Testing AutoBot Codebase Analytics System")
    print("=" * 50)

    # Test 1: Index the codebase
    print("\n1. Testing codebase indexing...")
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/analytics/codebase/index",
            json={"root_path": CODEBASE_PATH},
            timeout=60
        )

        if response.status_code == 200:
            result = response.json()
            print(f"✅ Indexing successful!")
            print(f"   Status: {result.get('status')}")
            print(f"   Files indexed: {result.get('stats', {}).get('total_files', 0)}")
            print(f"   Python files: {result.get('stats', {}).get('python_files', 0)}")
            print(f"   JavaScript files: {result.get('stats', {}).get('javascript_files', 0)}")
            print(f"   Vue files: {result.get('stats', {}).get('vue_files', 0)}")
        else:
            print(f"❌ Indexing failed: {response.status_code}")
            print(f"   Error: {response.text}")
            return False

    except Exception as e:
        print(f"❌ Indexing request failed: {e}")
        return False

    # Test 2: Get codebase stats
    print("\n2. Testing codebase stats...")
    try:
        response = requests.get(f"{BACKEND_URL}/api/analytics/codebase/stats")

        if response.status_code == 200:
            result = response.json()
            print(f"✅ Stats retrieved successfully!")
            print(f"   Total files: {result.get('stats', {}).get('total_files', 0)}")
            print(f"   Total functions: {result.get('stats', {}).get('total_functions', 0)}")
            print(f"   Total classes: {result.get('stats', {}).get('total_classes', 0)}")
            print(f"   Total lines: {result.get('stats', {}).get('total_lines', 0)}")
        else:
            print(f"❌ Stats failed: {response.status_code}")

    except Exception as e:
        print(f"❌ Stats request failed: {e}")

    # Test 3: Get code problems
    print("\n3. Testing code problems analysis...")
    try:
        response = requests.get(f"{BACKEND_URL}/api/analytics/codebase/problems")

        if response.status_code == 200:
            result = response.json()
            print(f"✅ Problems analysis successful!")
            print(f"   Total problems: {result.get('total_count', 0)}")

            problems = result.get('problems', [])
            if problems:
                print(f"   Problem types: {result.get('problem_types', [])}")
                print(f"   Sample problems:")
                for i, problem in enumerate(problems[:3]):
                    print(f"     {i+1}. {problem.get('type')} in {problem.get('file_path')} (line {problem.get('line_number', 'N/A')})")
        else:
            print(f"❌ Problems analysis failed: {response.status_code}")

    except Exception as e:
        print(f"❌ Problems request failed: {e}")

    # Test 4: Get hardcoded values
    print("\n4. Testing hardcoded values detection...")
    try:
        response = requests.get(f"{BACKEND_URL}/api/analytics/codebase/hardcodes")

        if response.status_code == 200:
            result = response.json()
            print(f"✅ Hardcodes analysis successful!")
            print(f"   Total hardcodes: {result.get('total_count', 0)}")

            hardcodes = result.get('hardcodes', [])
            if hardcodes:
                print(f"   Hardcode types: {result.get('hardcode_types', [])}")
                print(f"   Sample hardcodes:")
                for i, hardcode in enumerate(hardcodes[:3]):
                    print(f"     {i+1}. {hardcode.get('type')}: {hardcode.get('value')} in {hardcode.get('file_path')}")
        else:
            print(f"❌ Hardcodes analysis failed: {response.status_code}")

    except Exception as e:
        print(f"❌ Hardcodes request failed: {e}")

    # Test 5: Get code declarations
    print("\n5. Testing code declarations analysis...")
    try:
        response = requests.get(f"{BACKEND_URL}/api/analytics/codebase/declarations")

        if response.status_code == 200:
            result = response.json()
            print(f"✅ Declarations analysis successful!")
            print(f"   Total declarations: {result.get('total_count', 0)}")
            print(f"   Functions: {result.get('functions', 0)}")
            print(f"   Classes: {result.get('classes', 0)}")

            declarations = result.get('declarations', [])
            if declarations:
                print(f"   Sample declarations:")
                for i, decl in enumerate(declarations[:3]):
                    print(f"     {i+1}. {decl.get('type')}: {decl.get('name')} in {decl.get('file_path')}")
        else:
            print(f"❌ Declarations analysis failed: {response.status_code}")

    except Exception as e:
        print(f"❌ Declarations request failed: {e}")

    # Test 6: Get duplicate code
    print("\n6. Testing duplicate code detection...")
    try:
        response = requests.get(f"{BACKEND_URL}/api/analytics/codebase/duplicates")

        if response.status_code == 200:
            result = response.json()
            print(f"✅ Duplicates analysis successful!")
            print(f"   Total duplicates: {result.get('total_count', 0)}")

            duplicates = result.get('duplicates', [])
            if duplicates:
                print(f"   Sample duplicates:")
                for i, dup in enumerate(duplicates[:3]):
                    print(f"     {i+1}. {dup.get('code_snippet', 'Unknown')[:50]}... ({len(dup.get('files', []))} files)")
        else:
            print(f"❌ Duplicates analysis failed: {response.status_code}")

    except Exception as e:
        print(f"❌ Duplicates request failed: {e}")

    print("\n" + "=" * 50)
    print("🎉 Codebase Analytics Test Complete!")
    print("\nNext steps:")
    print("1. Check the frontend at http://172.16.168.21:5173")
    print("2. Navigate to Codebase Analytics")
    print("3. Click 'Index Codebase' and 'Analyze All'")
    print("4. View real analysis results!")

    return True

if __name__ == "__main__":
    print("Starting codebase analytics test...")
    asyncio.run(test_codebase_analytics())
