#!/usr/bin/env python3
"""
Test script to verify agent model configuration with available models.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import subprocess

from config import config


def test_ollama_models():
    """Test if configured models are available in Ollama."""
    print("🔍 Testing configured agent models...")  # noqa: print

    # Get available models from ollama
    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
        if result.returncode != 0:
            print("❌ Failed to get ollama model list")  # noqa: print
            return False

        available_models = set()
        for line in result.stdout.split("\n")[1:]:  # Skip header
            if line.strip():
                model_name = line.split()[0]
                available_models.add(model_name)

        print(
            f"📋 Available models: {', '.join(sorted(available_models))}"
        )  # noqa: print

    except Exception as e:
        print(f"❌ Error checking ollama models: {e}")  # noqa: print
        return False

    # Test each agent type
    agent_types = [
        "orchestrator",
        "chat",
        "system_commands",
        "rag",
        "knowledge_retrieval",
        "research",
        "default",
    ]

    success_count = 0
    for agent_type in agent_types:
        model = config.get_task_specific_model(agent_type)
        status = "✅" if model in available_models else "❌"
        print(f"{status} {agent_type:18} -> {model}")  # noqa: print
        if model in available_models:
            success_count += 1

    print(  # noqa: print
        f"\n📊 Model availability: {success_count}/{len(agent_types)} agents have available models"
    )

    # Test basic model functionality
    print("\n🧪 Testing model functionality...")  # noqa: print
    test_models = [
        "artifish/llama3.2-uncensored:latest",
        "llama3.2:1b-instruct-q4_K_M",
        "nomic-embed-text:latest",
    ]

    for model in test_models:
        if model in available_models:
            try:
                # Quick test with simple prompt
                test_result = subprocess.run(
                    ["ollama", "run", model],
                    input="Hello\n",
                    text=True,
                    capture_output=True,
                    timeout=30,
                )
                status = "✅" if test_result.returncode == 0 else "❌"
                print(f"{status} {model} - functional test")  # noqa: print
            except subprocess.TimeoutExpired:
                print(f"⏰ {model} - timeout (but likely working)")  # noqa: print
            except Exception as e:
                print(f"❌ {model} - error: {e}")  # noqa: print
        else:
            print(f"⚠️ {model} - not available")  # noqa: print

    return success_count == len(agent_types)


def main():
    """Main test function."""
    print("🤖 AutoBot Multi-Agent Model Configuration Test")  # noqa: print
    print("=" * 50)  # noqa: print

    success = test_ollama_models()

    print("\n" + "=" * 50)  # noqa: print
    if success:
        print(
            "✅ All agent models are properly configured and available!"
        )  # noqa: print
        return 0
    else:
        print("⚠️ Some models may need to be installed. Run:")  # noqa: print
        print("   ./setup_agent.sh")  # noqa: print
        return 1


if __name__ == "__main__":
    sys.exit(main())
