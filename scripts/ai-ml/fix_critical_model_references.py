#!/usr/bin/env python3
"""
Quick Fix Script for Critical Model References
Fixes immediate issues with missing model references in AutoBot codebase
"""

import os
import re
import shutil
from pathlib import Path

def backup_file(file_path):
    """Create backup of file before modification"""
    backup_path = f"{file_path}.backup"
    shutil.copy2(file_path, backup_path)
    print(f"✅ Created backup: {backup_path}")
    return backup_path

def fix_connection_utils():
    """Fix deepseek-r1:14b references in connection_utils.py"""
    file_path = "/home/kali/Desktop/AutoBot/backend/utils/connection_utils.py"

    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return False

    print(f"🔧 Fixing {file_path}")
    backup_file(file_path)

    with open(file_path, 'r') as f:
        content = f.read()

    # Replace deepseek-r1:14b with available model
    original_content = content
    content = content.replace(
        'os.getenv("AUTOBOT_OLLAMA_MODEL", "deepseek-r1:14b")',
        'os.getenv("AUTOBOT_OLLAMA_MODEL", "artifish/llama3.2-uncensored:latest")'
    )

    if content != original_content:
        with open(file_path, 'w') as f:
            f.write(content)
        print("✅ Fixed deepseek-r1:14b references")
        return True
    else:
        print("⚠️ No changes needed")
        return False

def fix_langchain_orchestrator():
    """Fix phi:2.7b reference in langchain_agent_orchestrator.py"""
    file_path = "/home/kali/Desktop/AutoBot/src/langchain_agent_orchestrator.py"

    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return False

    print(f"🔧 Fixing {file_path}")
    backup_file(file_path)

    with open(file_path, 'r') as f:
        content = f.read()

    # Replace phi:2.7b with available model
    original_content = content
    content = content.replace(
        'llm_model = "phi:2.7b"',
        'llm_model = "llama3.2:1b-instruct-q4_K_M"'
    )

    if content != original_content:
        with open(file_path, 'w') as f:
            f.write(content)
        print("✅ Fixed phi:2.7b reference")
        return True
    else:
        print("⚠️ No changes needed")
        return False

def fix_config_py():
    """Fix model configurations in config.py"""
    file_path = "/home/kali/Desktop/AutoBot/src/config.py"

    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return False

    print(f"🔧 Fixing {file_path}")
    backup_file(file_path)

    with open(file_path, 'r') as f:
        content = f.read()

    original_content = content

    # Fix orchestrator model default
    content = content.replace(
        '"orchestrator": os.getenv("AUTOBOT_ORCHESTRATOR_MODEL", "llama3.2:3b")',
        '"orchestrator": os.getenv("AUTOBOT_ORCHESTRATOR_MODEL", "artifish/llama3.2-uncensored:latest")'
    )

    # Optimize classification model
    content = content.replace(
        '"classification": os.getenv("AUTOBOT_CLASSIFICATION_MODEL", "gemma2:2b")',
        '"classification": os.getenv("AUTOBOT_CLASSIFICATION_MODEL", "gemma3:1b")'
    )

    if content != original_content:
        with open(file_path, 'w') as f:
            f.write(content)
        print("✅ Fixed config.py model references")
        return True
    else:
        print("⚠️ No changes needed in config.py")
        return False

def fix_vllm_provider():
    """Add fallback for missing vLLM models"""
    file_path = "/home/kali/Desktop/AutoBot/src/llm_providers/vllm_provider.py"

    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return False

    print(f"🔧 Fixing {file_path}")
    backup_file(file_path)

    with open(file_path, 'r') as f:
        content = f.read()

    # Add fallback check for missing models
    fallback_code = '''
    # Check if model is available, use fallback if not
    try:
        # Test if model is available
        import subprocess
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
        available_models = [line.split()[0] for line in result.stdout.split('\\n')[1:] if line.strip()]

        if self.model_name not in available_models:
            # Use fallback model
            fallback_models = ["llama3.2:3b-instruct-q4_K_M", "llama3.2:1b-instruct-q4_K_M"]
            for fallback in fallback_models:
                if fallback in available_models:
                    logger.warning(f"Model {self.model_name} not found, using fallback: {fallback}")
                    self.model_name = fallback
                    break
    except Exception as e:
        logger.warning(f"Could not check model availability: {e}")
'''

    # Insert fallback check after model initialization
    if "def __init__" in content and "self.model_name = config" in content:
        # Find the line with model_name assignment
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if "self.model_name = config" in line:
                # Insert fallback code after this line
                lines.insert(i + 1, fallback_code)
                break

        new_content = '\n'.join(lines)

        with open(file_path, 'w') as f:
            f.write(new_content)
        print("✅ Added model fallback logic to vLLM provider")
        return True
    else:
        print("⚠️ Could not add fallback logic to vLLM provider")
        return False

def install_missing_models():
    """Install critical missing models"""
    critical_models = [
        "tinyllama:latest",
        "phi3:3.8b",
        "codellama:7b-instruct"
    ]

    print("📦 Installing critical missing models...")

    for model in critical_models:
        print(f"Installing {model}...")
        try:
            import subprocess
            result = subprocess.run(
                ["ollama", "pull", model],
                capture_output=True,
                text=True,
                timeout=1800  # 30 minute timeout
            )

            if result.returncode == 0:
                print(f"✅ Successfully installed {model}")
            else:
                print(f"❌ Failed to install {model}: {result.stderr}")

        except subprocess.TimeoutExpired:
            print(f"⏱️ Installation of {model} timed out")
        except Exception as e:
            print(f"❌ Error installing {model}: {e}")

def verify_fixes():
    """Verify that the fixes are working"""
    print("\n🔍 Verifying fixes...")

    # Check if files were modified
    modified_files = [
        "/home/kali/Desktop/AutoBot/src/orchestrator.py",
        "/home/kali/Desktop/AutoBot/backend/utils/connection_utils.py",
        "/home/kali/Desktop/AutoBot/src/config.py"
    ]

    for file_path in modified_files:
        if os.path.exists(file_path):
            print(f"✅ {file_path} exists")

            # Check for backup
            backup_path = f"{file_path}.backup"
            if os.path.exists(backup_path):
                print(f"✅ Backup exists: {backup_path}")
            else:
                print(f"⚠️ No backup found for {file_path}")
        else:
            print(f"❌ {file_path} not found")

    # Test ollama connection
    try:
        import subprocess
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ Ollama is responding")

            # Check for key models
            available_models = [line.split()[0] for line in result.stdout.split('\n')[1:] if line.strip()]
            key_models = ["artifish/llama3.2-uncensored:latest", "llama3.2:1b-instruct-q4_K_M", "nomic-embed-text:latest"]

            for model in key_models:
                if model in available_models:
                    print(f"✅ Key model available: {model}")
                else:
                    print(f"⚠️ Key model missing: {model}")
        else:
            print("❌ Ollama is not responding")

    except Exception as e:
        print(f"❌ Error checking Ollama: {e}")

def main():
    """Main function to apply all fixes"""
    print("🚀 AutoBot LLM Model Critical Fixes")
    print("=" * 50)

    fixes_applied = 0

    # Apply critical fixes
    if fix_connection_utils():
        fixes_applied += 1

    if fix_langchain_orchestrator():
        fixes_applied += 1

    if fix_config_py():
        fixes_applied += 1

    if fix_vllm_provider():
        fixes_applied += 1

    # Install missing models (optional, can be time-consuming)
    install_choice = input("\n📦 Install missing models? (y/N): ").lower().strip()
    if install_choice == 'y':
        install_missing_models()

    # Verify fixes
    verify_fixes()

    print(f"\n✅ Applied {fixes_applied} fixes")
    print("\n🔄 Next steps:")
    print("1. Restart AutoBot services: bash run_autobot.sh --dev --no-build")
    print("2. Test model functionality")
    print("3. Monitor logs for any remaining model errors")
    print("4. Run full optimization script: python scripts/ai-ml/optimize_llm_models.py")

if __name__ == "__main__":
    main()