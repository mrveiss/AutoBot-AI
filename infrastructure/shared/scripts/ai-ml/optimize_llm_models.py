#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot LLM Model Optimization Script
Automatically installs missing models and optimizes configurations for RTX 4070 + Intel NPU
"""

import asyncio
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class LLMModelOptimizer:
    """Optimize LLM model configuration for AutoBot"""

    def __init__(self):
        """Initialize LLM optimizer with default paths and state containers."""
        self.autobot_root = Path("/home/kali/Desktop/AutoBot")
        self.installed_models = {}
        self.missing_models = []
        self.optimization_results = {}
        # Async lock for thread-safe access to shared state
        self._state_lock = asyncio.Lock()

    async def run_optimization(self):
        """Run complete LLM model optimization"""
        logger.info("🚀 Starting AutoBot LLM Model Optimization")

        # Step 1: Analyze current state
        await self.analyze_current_models()

        # Step 2: Install missing critical models
        await self.install_missing_models()

        # Step 3: Update configurations
        await self.update_configurations()

        # Step 4: Optimize for hardware
        await self.optimize_for_hardware()

        # Step 5: Validate changes
        await self.validate_optimization()

        # Step 6: Generate report
        await self.generate_optimization_report()

        logger.info("✅ LLM Model Optimization Complete!")

    async def analyze_current_models(self):
        """Analyze currently installed models (thread-safe)"""
        logger.info("📊 Analyzing current model inventory...")

        try:
            # Get installed Ollama models (Issue #479: Use async subprocess)
            process = await asyncio.create_subprocess_exec(
                "ollama",
                "list",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                raise subprocess.CalledProcessError(
                    process.returncode, "ollama list", stderr.decode()
                )

            # Create result-like object for compatibility
            class Result:
                def __init__(self, stdout_bytes):
                    self.stdout = stdout_bytes.decode()

            result = Result(stdout)

            # Parse ollama list output
            parsed_models = {}
            lines = result.stdout.strip().split("\n")[1:]  # Skip header
            for line in lines:
                if line.strip():
                    parts = line.split()
                    model_name = parts[0]
                    model_size = parts[2] if len(parts) > 2 else "Unknown"
                    parsed_models[model_name] = {
                        "size": model_size,
                        "status": "installed",
                    }

            # Thread-safe update of shared state
            async with self._state_lock:
                self.installed_models.update(parsed_models)
                installed_count = len(self.installed_models)

            logger.info("Found %s installed models", installed_count)

            # Identify missing critical models
            critical_models = [
                "tinyllama:latest",
                "phi3:3.8b",
                "codellama:7b-instruct",
                "qwen2.5:7b",
                "mistral:7b-instruct",
            ]

            # Thread-safe check and update of missing models
            async with self._state_lock:
                for model in critical_models:
                    if model not in self.installed_models:
                        self.missing_models.append(model)
                missing_count = len(self.missing_models)
                missing_list = list(self.missing_models)

            if missing_count > 0:
                logger.warning(
                    "❌ Missing %s critical models: %s", missing_count, missing_list
                )
            else:
                logger.info("✅ All critical models are installed")

        except subprocess.CalledProcessError as e:
            logger.error("Failed to analyze models: %s", e)
            raise

    async def install_missing_models(self):
        """Install missing critical models (thread-safe)"""
        # Thread-safe read of missing models
        async with self._state_lock:
            models_to_install = list(self.missing_models)

        if not models_to_install:
            logger.info("✅ No missing models to install")
            return

        logger.info("📦 Installing %s missing models...", len(models_to_install))

        # Model installation priority and rationale
        model_priority = {
            "tinyllama:latest": {
                "priority": 1,
                "reason": "Critical: Referenced in orchestrator.py",
                "size_estimate": "637MB",
            },
            "phi3:3.8b": {
                "priority": 2,
                "reason": "Fast inference, good for classification",
                "size_estimate": "2.2GB",
            },
            "codellama:7b-instruct": {
                "priority": 3,
                "reason": "Specialized code analysis and generation",
                "size_estimate": "3.8GB",
            },
            "qwen2.5:7b": {
                "priority": 4,
                "reason": "Enhanced reasoning capabilities",
                "size_estimate": "4.1GB",
            },
            "mistral:7b-instruct": {
                "priority": 5,
                "reason": "Alternative high-quality model",
                "size_estimate": "4.1GB",
            },
        }

        # Sort by priority (use local copy)
        sorted_models = sorted(
            models_to_install,
            key=lambda x: model_priority.get(x, {}).get("priority", 999),
        )

        installation_results = {}

        for model in sorted_models:
            model_info = model_priority.get(model, {})
            logger.info("📥 Installing %s (%s)", model, model_info.get("reason", "N/A"))

            try:
                # Install model with timeout
                start_time = time.time()
                process = await asyncio.create_subprocess_exec(
                    "ollama",
                    "pull",
                    model,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=1800  # 30 minute timeout
                )

                if process.returncode == 0:
                    install_time = time.time() - start_time
                    logger.info(
                        "✅ Successfully installed %s in %.1fs", model, install_time
                    )
                    installation_results[model] = {
                        "status": "success",
                        "install_time": install_time,
                        "size": model_info.get("size_estimate", "Unknown"),
                    }
                else:
                    logger.error("❌ Failed to install %s: %s", model, stderr.decode())
                    installation_results[model] = {
                        "status": "failed",
                        "error": stderr.decode(),
                    }

            except asyncio.TimeoutError:
                logger.error("❌ Installation of %s timed out", model)
                installation_results[model] = {
                    "status": "timeout",
                    "error": "Installation timed out after 30 minutes",
                }
            except Exception as e:
                logger.error("❌ Error installing %s: %s", model, e)
                installation_results[model] = {"status": "error", "error": str(e)}

        # Thread-safe update of optimization results
        async with self._state_lock:
            self.optimization_results["installations"] = installation_results

    async def update_configurations(self):
        """Update configuration files with optimized model selections"""
        logger.info("⚙️ Updating configuration files...")

        # Configuration updates
        config_updates = {
            "src/orchestrator.py": [
                {
                    "find": 'llm_config.get("ollama", {}).get("model", "tinyllama:latest")',
                    "replace": 'llm_config.get("ollama", {}).get("model", "artifish/llama3.2-uncensored:latest")',
                    "line_context": "orchestrator_llm_model",
                }
            ],
            "src/config.py": [
                {
                    "find": '"orchestrator": os.getenv("AUTOBOT_ORCHESTRATOR_MODEL", "llama3.2:3b")',
                    "replace": '"orchestrator": os.getenv("AUTOBOT_ORCHESTRATOR_MODEL", "artifish/llama3.2-uncensored:latest")',
                    "line_context": "models configuration",
                },
                {
                    "find": '"classification": os.getenv("AUTOBOT_CLASSIFICATION_MODEL", "gemma2:2b")',
                    "replace": '"classification": os.getenv("AUTOBOT_CLASSIFICATION_MODEL", "gemma3:1b")',
                    "line_context": "models configuration",
                },
            ],
            "backend/utils/connection_utils.py": [
                {
                    "find": '"deepseek-r1:14b"',
                    "replace": '"artifish/llama3.2-uncensored:latest"',
                    "line_context": "AUTOBOT_DEFAULT_LLM_MODEL default",
                }
            ],
        }

        update_results = {}

        for file_path, updates in config_updates.items():
            full_path = self.autobot_root / file_path
            if not full_path.exists():
                logger.warning("⚠️ Configuration file not found: %s", file_path)
                continue

            logger.info("📝 Updating %s", file_path)

            try:
                # Read current content
                with open(full_path, "r") as f:
                    content = f.read()

                original_content = content
                changes_made = 0

                for update in updates:
                    if update["find"] in content:
                        content = content.replace(update["find"], update["replace"])
                        changes_made += 1
                        logger.info("✅ Updated %s", update["line_context"])
                    else:
                        logger.warning(
                            "⚠️ Pattern not found: %s", update["line_context"]
                        )

                # Write updated content if changes were made
                if changes_made > 0:
                    # Create backup
                    backup_path = full_path.with_suffix(f"{full_path.suffix}.backup")
                    with open(backup_path, "w") as f:
                        f.write(original_content)

                    # Write updated content
                    with open(full_path, "w") as f:
                        f.write(content)

                    update_results[file_path] = {
                        "status": "updated",
                        "changes": changes_made,
                        "backup": str(backup_path),
                    }
                    logger.info("✅ Updated %s with %s changes", file_path, changes_made)
                else:
                    update_results[file_path] = {"status": "no_changes", "changes": 0}

            except Exception as e:
                logger.error("❌ Failed to update %s: %s", file_path, e)
                update_results[file_path] = {"status": "error", "error": str(e)}

        # Thread-safe update of optimization results
        async with self._state_lock:
            self.optimization_results["config_updates"] = update_results

    async def optimize_for_hardware(self):
        """Create hardware-specific optimization configuration"""
        logger.info("🏗️ Creating hardware-specific optimization...")

        # RTX 4070 + Intel NPU optimized configuration
        hardware_config = {
            "gpu_optimization": {
                "device_id": 0,
                "memory_limit_mb": 10000,  # Leave 2GB for system
                "concurrent_models": 2,
                "model_rotation": True,
                "preferred_models": [
                    "wizard-vicuna-uncensored:13b",  # 7.4GB - Research
                    "dolphin-llama3:8b",  # 4.7GB - Analysis
                    "artifish/llama3.2-uncensored:latest",  # 2.2GB - Orchestrator
                    "llama3.2:3b-instruct-q4_K_M",  # 2GB - Chat
                ],
            },
            "npu_optimization": {
                "enabled": True,
                "target_models": [
                    "gemma3:270m",  # Ultra-fast tasks
                    "gemma3:1b",  # Fast general tasks
                    "nomic-embed-text:latest",  # Embeddings
                ],
                "optimization_flags": [
                    "int8_quantization",
                    "dynamic_batching",
                    "memory_pooling",
                ],
            },
            "model_routing": {
                "classification": {
                    "model": "gemma3:1b",
                    "device": "npu",
                    "priority": "speed",
                },
                "chat": {
                    "model": "llama3.2:3b-instruct-q4_K_M",
                    "device": "gpu",
                    "priority": "balanced",
                },
                "research": {
                    "model": "wizard-vicuna-uncensored:13b",
                    "device": "gpu",
                    "priority": "quality",
                },
                "rag": {
                    "model": "dolphin-llama3:8b",
                    "device": "gpu",
                    "priority": "reasoning",
                },
                "code": {
                    "model": "codellama:7b-instruct",
                    "device": "gpu",
                    "priority": "specialized",
                },
                "system_commands": {
                    "model": "gemma3:270m",
                    "device": "npu",
                    "priority": "speed",
                },
            },
        }

        # Save hardware configuration
        config_path = self.autobot_root / "config" / "hardware_optimization.yaml"
        config_path.parent.mkdir(exist_ok=True)

        try:
            import yaml

            with open(config_path, "w") as f:
                yaml.dump(hardware_config, f, default_flow_style=False, indent=2)

            logger.info("✅ Hardware optimization config saved to %s", config_path)
            async with self._state_lock:
                self.optimization_results["hardware_config"] = str(config_path)

        except ImportError:
            # Fallback to JSON if PyYAML not available
            config_path = config_path.with_suffix(".json")
            with open(config_path, "w") as f:
                json.dump(hardware_config, f, indent=2)

            logger.info(
                "✅ Hardware optimization config saved to %s (JSON format)", config_path
            )
            async with self._state_lock:
                self.optimization_results["hardware_config"] = str(config_path)

    async def validate_optimization(self):
        """Validate that optimizations are working"""
        logger.info("🔍 Validating optimization results...")

        validation_results = {}

        # Check if models are accessible
        critical_models = [
            "artifish/llama3.2-uncensored:latest",
            "gemma3:1b",
            "nomic-embed-text:latest",
        ]

        for model in critical_models:
            try:
                # Test model with simple prompt
                process = await asyncio.create_subprocess_exec(
                    "ollama",
                    "run",
                    model,
                    "Hello, respond with 'OK'",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=30
                )

                if process.returncode == 0 and "OK" in stdout.decode().upper():
                    validation_results[model] = {
                        "status": "success",
                        "response_time": "< 30s",
                    }
                    logger.info("✅ Model %s validation successful", model)
                else:
                    validation_results[model] = {
                        "status": "failed",
                        "error": stderr.decode(),
                    }
                    logger.warning("⚠️ Model %s validation failed", model)

            except asyncio.TimeoutError:
                validation_results[model] = {
                    "status": "timeout",
                    "error": "Validation timed out",
                }
                logger.warning("⚠️ Model %s validation timed out", model)
            except Exception as e:
                validation_results[model] = {"status": "error", "error": str(e)}
                logger.error("❌ Model %s validation error: %s", model, e)

        # Thread-safe update of optimization results
        async with self._state_lock:
            self.optimization_results["validation"] = validation_results

    async def generate_optimization_report(self):
        """Generate comprehensive optimization report (thread-safe)"""
        logger.info("📊 Generating optimization report...")

        # Thread-safe read of optimization results
        async with self._state_lock:
            results_copy = dict(self.optimization_results)

        # Create detailed report
        report = {
            "optimization_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "autobot_version": "Phase 5",
            "hardware_target": "RTX 4070 + Intel NPU",
            "summary": {
                "models_installed": len(results_copy.get("installations", {})),
                "configs_updated": len(results_copy.get("config_updates", {})),
                "validation_success": len(
                    [
                        v
                        for v in results_copy.get("validation", {}).values()
                        if v.get("status") == "success"
                    ]
                ),
            },
            "details": results_copy,
            "recommendations": {
                "immediate_actions": [
                    "Restart AutoBot services to apply configuration changes",
                    "Monitor model performance with new configurations",
                    "Check GPU memory usage during concurrent model loading",
                ],
                "next_steps": [
                    "Implement dynamic model loading based on workload",
                    "Configure NPU acceleration for small models",
                    "Set up model performance monitoring",
                ],
            },
        }

        # Save report
        report_path = (
            self.autobot_root
            / "analysis"
            / "ai-ml"
            / f"llm_optimization_report_{int(time.time())}.json"
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)

        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        logger.info("📄 Optimization report saved to %s", report_path)

        # Print summary
        print("\n" + "=" * 60)
        print("🎯 AutoBot LLM Model Optimization Summary")
        print("=" * 60)
        print(f"✅ Models Installed: {report['summary']['models_installed']}")
        print(f"✅ Configs Updated: {report['summary']['configs_updated']}")
        print(f"✅ Validations Passed: {report['summary']['validation_success']}")
        print(f"📄 Full Report: {report_path}")
        print("=" * 60)

        return report_path


async def main():
    """Main optimization function"""
    optimizer = LLMModelOptimizer()

    try:
        await optimizer.run_optimization()
        print("\n🚀 LLM Model Optimization completed successfully!")
        print("🔄 Please restart AutoBot services to apply changes:")
        print("   bash run_autobot.sh --dev --no-build")

    except KeyboardInterrupt:
        print("\n⏹️ Optimization cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Optimization failed: {e}")
        logger.exception("Optimization failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
