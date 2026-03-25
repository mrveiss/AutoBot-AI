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

# Critical models that must be installed
_CRITICAL_MODELS = [
    "tinyllama:latest",
    "phi3:3.8b",
    "codellama:7b-instruct",
    "qwen2.5:7b",
    "qwen3.5:9b",
]

# Model installation priority and rationale
_MODEL_PRIORITY = {
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
    "qwen3.5:9b": {
        "priority": 5,
        "reason": "Default LLM — tool use and general tasks",
        "size_estimate": "4.1GB",
    },
}


class LLMModelOptimizer:
    """Optimize LLM model configuration for AutoBot"""

    def __init__(self):
        """Initialize LLM optimizer with default paths and state containers."""
        self.autobot_root = Path("/home/kali/Desktop/AutoBot")
        self.installed_models = {}
        self.missing_models = []
        self.optimization_results = {}
        self._state_lock = asyncio.Lock()

    async def run_optimization(self):
        """Run complete LLM model optimization pipeline."""
        logger.info("Starting AutoBot LLM Model Optimization")
        await self.analyze_current_models()
        await self.install_missing_models()
        await self.update_configurations()
        await self.optimize_for_hardware()
        await self.validate_optimization()
        await self.generate_optimization_report()
        logger.info("LLM Model Optimization Complete!")

    # -- analyze_current_models decomposition (#2410) --

    async def _fetch_ollama_models(self) -> dict:
        """Fetch installed models from Ollama. Returns {name: {size, status}}."""
        process = await asyncio.create_subprocess_exec(
            "ollama", "list",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise subprocess.CalledProcessError(
                process.returncode, "ollama list", stderr.decode()
            )

        parsed = {}
        for line in stdout.decode().strip().split("\n")[1:]:
            if line.strip():
                parts = line.split()
                parsed[parts[0]] = {
                    "size": parts[2] if len(parts) > 2 else "Unknown",
                    "status": "installed",
                }
        return parsed

    async def _identify_missing_models(self) -> list:
        """Check critical models against installed set. Returns missing list."""
        async with self._state_lock:
            missing = [m for m in _CRITICAL_MODELS if m not in self.installed_models]
            self.missing_models = missing
            return list(missing)

    async def analyze_current_models(self):
        """Analyze currently installed models (thread-safe)."""
        logger.info("Analyzing current model inventory...")

        try:
            parsed = await self._fetch_ollama_models()
            async with self._state_lock:
                self.installed_models.update(parsed)
                count = len(self.installed_models)
            logger.info("Found %s installed models", count)

            missing = await self._identify_missing_models()
            if missing:
                logger.warning("Missing %s critical models: %s", len(missing), missing)
            else:
                logger.info("All critical models are installed")
        except subprocess.CalledProcessError as e:
            logger.error("Failed to analyze models: %s", e)
            raise

    # -- install_missing_models decomposition (#2410) --

    async def _pull_single_model(self, model: str) -> dict:
        """Pull a single model via Ollama. Returns result dict."""
        info = _MODEL_PRIORITY.get(model, {})
        logger.info("Installing %s (%s)", model, info.get("reason", "N/A"))

        try:
            start = time.time()
            process = await asyncio.create_subprocess_exec(
                "ollama", "pull", model,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=1800
            )

            if process.returncode == 0:
                elapsed = time.time() - start
                logger.info("Installed %s in %.1fs", model, elapsed)
                return {
                    "status": "success",
                    "install_time": elapsed,
                    "size": info.get("size_estimate", "Unknown"),
                }

            logger.error("Failed to install %s: %s", model, stderr.decode())
            return {"status": "failed", "error": stderr.decode()}

        except asyncio.TimeoutError:
            logger.error("Installation of %s timed out", model)
            return {"status": "timeout", "error": "Timed out after 30 minutes"}
        except Exception as e:
            logger.error("Error installing %s: %s", model, e)
            return {"status": "error", "error": str(e)}

    async def install_missing_models(self):
        """Install missing critical models (thread-safe)."""
        async with self._state_lock:
            to_install = list(self.missing_models)

        if not to_install:
            logger.info("No missing models to install")
            return

        logger.info("Installing %s missing models...", len(to_install))
        sorted_models = sorted(
            to_install,
            key=lambda x: _MODEL_PRIORITY.get(x, {}).get("priority", 999),
        )

        results = {}
        for model in sorted_models:
            results[model] = await self._pull_single_model(model)

        async with self._state_lock:
            self.optimization_results["installations"] = results

    # -- update_configurations decomposition (#2410) --

    def _get_config_updates(self) -> dict:
        """Return the file-to-updates mapping for configuration patches."""
        return {
            "src/orchestrator.py": [{
                "find": 'llm_config.get("ollama", {}).get("model", "tinyllama:latest")',
                "replace": 'llm_config.get("ollama", {}).get("model", "artifish/llama3.2-uncensored:latest")',
                "line_context": "orchestrator_llm_model",
            }],
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
            "backend/utils/connection_utils.py": [{
                "find": '"deepseek-r1:14b"',
                "replace": '"artifish/llama3.2-uncensored:latest"',
                "line_context": "AUTOBOT_DEFAULT_LLM_MODEL default",
            }],
        }

    def _apply_file_updates(self, full_path: Path, updates: list) -> dict:
        """Apply find/replace updates to a single file. Returns result dict."""
        try:
            with open(full_path, encoding="utf-8") as f:
                content = f.read()

            original = content
            changes = 0
            for update in updates:
                if update["find"] in content:
                    content = content.replace(update["find"], update["replace"])
                    changes += 1
                    logger.info("Updated %s", update["line_context"])
                else:
                    logger.warning("Pattern not found: %s", update["line_context"])

            if changes > 0:
                backup = full_path.with_suffix(f"{full_path.suffix}.backup")
                with open(backup, "w", encoding="utf-8") as f:
                    f.write(original)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)
                return {"status": "updated", "changes": changes, "backup": str(backup)}

            return {"status": "no_changes", "changes": 0}
        except Exception as e:
            logger.error("Failed to update %s: %s", full_path, e)
            return {"status": "error", "error": str(e)}

    async def update_configurations(self):
        """Update configuration files with optimized model selections."""
        logger.info("Updating configuration files...")
        updates_map = self._get_config_updates()
        results = {}

        for file_path, updates in updates_map.items():
            full_path = self.autobot_root / file_path
            if not full_path.exists():
                logger.warning("Configuration file not found: %s", file_path)
                continue
            logger.info("Updating %s", file_path)
            results[file_path] = self._apply_file_updates(full_path, updates)

        async with self._state_lock:
            self.optimization_results["config_updates"] = results

    # -- optimize_for_hardware decomposition (#2410) --

    def _build_hardware_config(self) -> dict:
        """Build RTX 4070 + Intel NPU optimization config."""
        return {
            "gpu_optimization": {
                "device_id": 0,
                "memory_limit_mb": 10000,
                "concurrent_models": 2,
                "model_rotation": True,
                "preferred_models": [
                    "wizard-vicuna-uncensored:13b",
                    "dolphin-llama3:8b",
                    "artifish/llama3.2-uncensored:latest",
                    "llama3.2:3b-instruct-q4_K_M",
                ],
            },
            "npu_optimization": {
                "enabled": True,
                "target_models": ["gemma3:270m", "gemma3:1b", "nomic-embed-text:latest"],
                "optimization_flags": ["int8_quantization", "dynamic_batching", "memory_pooling"],
            },
            "model_routing": {
                "classification": {"model": "gemma3:1b", "device": "npu", "priority": "speed"},
                "chat": {"model": "llama3.2:3b-instruct-q4_K_M", "device": "gpu", "priority": "balanced"},
                "research": {"model": "wizard-vicuna-uncensored:13b", "device": "gpu", "priority": "quality"},
                "rag": {"model": "dolphin-llama3:8b", "device": "gpu", "priority": "reasoning"},
                "code": {"model": "codellama:7b-instruct", "device": "gpu", "priority": "specialized"},
                "system_commands": {"model": "gemma3:270m", "device": "npu", "priority": "speed"},
            },
        }

    def _save_config_file(self, config: dict, config_path: Path) -> str:
        """Save config as YAML (fallback JSON). Returns saved path."""
        config_path.parent.mkdir(exist_ok=True)
        try:
            import yaml

            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f, default_flow_style=False, indent=2)
            return str(config_path)
        except ImportError:
            json_path = config_path.with_suffix(".json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            logger.info("Saved as JSON (PyYAML unavailable): %s", json_path)
            return str(json_path)

    async def optimize_for_hardware(self):
        """Create hardware-specific optimization configuration."""
        logger.info("Creating hardware-specific optimization...")
        config = self._build_hardware_config()
        path = self.autobot_root / "config" / "hardware_optimization.yaml"
        saved = self._save_config_file(config, path)
        logger.info("Hardware optimization config saved to %s", saved)
        async with self._state_lock:
            self.optimization_results["hardware_config"] = saved

    async def validate_optimization(self):
        """Validate that optimizations are working."""
        logger.info("Validating optimization results...")
        results = {}
        models = [
            "artifish/llama3.2-uncensored:latest",
            "gemma3:1b",
            "nomic-embed-text:latest",
        ]

        for model in models:
            try:
                process = await asyncio.create_subprocess_exec(
                    "ollama", "run", model, "Hello, respond with 'OK'",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=30
                )

                if process.returncode == 0 and "OK" in stdout.decode().upper():
                    results[model] = {"status": "success", "response_time": "< 30s"}
                    logger.info("Model %s validation successful", model)
                else:
                    results[model] = {"status": "failed", "error": stderr.decode()}
                    logger.warning("Model %s validation failed", model)
            except asyncio.TimeoutError:
                results[model] = {"status": "timeout", "error": "Validation timed out"}
                logger.warning("Model %s validation timed out", model)
            except Exception as e:
                results[model] = {"status": "error", "error": str(e)}
                logger.error("Model %s validation error: %s", model, e)

        async with self._state_lock:
            self.optimization_results["validation"] = results

    # -- generate_optimization_report decomposition (#2410) --

    def _build_report(self, results: dict) -> dict:
        """Build the optimization report dict from collected results."""
        return {
            "optimization_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "autobot_version": "Phase 5",
            "hardware_target": "RTX 4070 + Intel NPU",
            "summary": {
                "models_installed": len(results.get("installations", {})),
                "configs_updated": len(results.get("config_updates", {})),
                "validation_success": sum(
                    1 for v in results.get("validation", {}).values()
                    if v.get("status") == "success"
                ),
            },
            "details": results,
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

    async def generate_optimization_report(self):
        """Generate comprehensive optimization report (thread-safe)."""
        logger.info("Generating optimization report...")

        async with self._state_lock:
            results_copy = dict(self.optimization_results)

        report = self._build_report(results_copy)
        report_path = (
            self.autobot_root / "analysis" / "ai-ml"
            / f"llm_optimization_report_{int(time.time())}.json"
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        logger.info("Optimization report saved to %s", report_path)
        s = report["summary"]
        print(f"\n{'=' * 60}")
        print("AutoBot LLM Model Optimization Summary")
        print(f"{'=' * 60}")
        print(f"Models Installed: {s['models_installed']}")
        print(f"Configs Updated: {s['configs_updated']}")
        print(f"Validations Passed: {s['validation_success']}")
        print(f"Full Report: {report_path}")
        print(f"{'=' * 60}")

        return report_path


async def main():
    """Main optimization function"""
    optimizer = LLMModelOptimizer()

    try:
        await optimizer.run_optimization()
        print("\nLLM Model Optimization completed successfully!")
        print("Please restart AutoBot services to apply changes:")
        print("   scripts/start-services.sh start")

    except KeyboardInterrupt:
        print("\nOptimization cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nOptimization failed: {e}")
        logger.exception("Optimization failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
