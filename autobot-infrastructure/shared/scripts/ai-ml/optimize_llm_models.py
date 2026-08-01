#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
from typing import Any

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SSOT model constants — loaded from agents.yaml (#2584)
# All model name strings MUST come from this block; never hardcode elsewhere.
# Source of truth: autobot-infrastructure/shared/config/agents.yaml
# ---------------------------------------------------------------------------
_AGENTS_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "agents.yaml"


def _load_agents_config() -> dict[str, Any]:
    """Load agents.yaml; return empty dict on any error so defaults still apply."""
    try:
        import yaml  # PyYAML — always available in the AutoBot environment

        with open(_AGENTS_CONFIG_PATH, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception as exc:  # pragma: no cover
        logger.warning("Could not load agents.yaml (%s); using built-in defaults", exc)
        return {}


def _get_model(role: str, fallback: str) -> str:
    """Return the model name for *role* from agents.yaml, or *fallback*."""
    cfg = _load_agents_config()
    return cfg.get("llm", {}).get("models", {}).get(role, fallback) or fallback


# Per-role model names — single source of truth for this script (#2584)
# These resolve at import time against the live agents.yaml.
# llm.default_model sits one level above llm.models; retrieve it separately.
_DEFAULT_MODEL = _load_agents_config().get("llm", {}).get("default_model", "qwen3.5:9b")
_ROUTING_MODEL = _get_model("orchestrator", "llama3.2:1b")
_CLASSIFICATION_MODEL = _get_model("classification", "gemma2:2b")
_RAG_MODEL = _get_model("rag", "mistral:7b-instruct")
_CHAT_MODEL = _get_model("chat", "qwen3.5:9b")
_CODE_MODEL = _get_model("npu_code_search", "phi3:mini")
_EMBEDDING_MODEL = "nomic-embed-text:latest"  # embeddings.model in agents.yaml

# Critical models that must be installed (derived from SSOT roles above)
_CRITICAL_MODELS = [
    _ROUTING_MODEL,
    _CLASSIFICATION_MODEL,
    _CODE_MODEL,
    _RAG_MODEL,
    _DEFAULT_MODEL,
]

# Model installation priority and rationale
_MODEL_PRIORITY = {
    _ROUTING_MODEL: {
        "priority": 1,
        "reason": "Routing tier — orchestrator, fast intent dispatch",
        "size_estimate": "~700MB",
    },
    _CLASSIFICATION_MODEL: {
        "priority": 2,
        "reason": "Classification tier — intent detection",
        "size_estimate": "~2.5GB",
    },
    _CODE_MODEL: {
        "priority": 3,
        "reason": "Quality tier — code search and NPU analysis",
        "size_estimate": "~5GB",
    },
    _RAG_MODEL: {
        "priority": 4,
        "reason": "Quality tier — RAG and knowledge retrieval",
        "size_estimate": "~5GB",
    },
    _DEFAULT_MODEL: {
        "priority": 5,
        "reason": "Default quality model — tool use and general tasks",
        "size_estimate": "~5GB",
    },
}


class LLMModelOptimizer:
    """Optimize LLM model configuration for AutoBot"""

    def __init__(self):
        """Initialize LLM optimizer with default paths and state containers."""
        self.autobot_root = Path("${AUTOBOT_PROJECT_ROOT:-/opt/autobot/code_source}")
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
            "ollama",
            "list",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, "ollama list", stderr.decode())

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
                "ollama",
                "pull",
                model,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=1800)

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
        """Return the file-to-updates mapping for configuration patches.

        All model name strings are derived from SSOT constants at the top of this
        module (loaded from agents.yaml) — never hardcoded here (#2584).
        """
        return {
            "src/orchestrator.py": [
                {
                    "find": 'llm_config.get("ollama", {}).get("model", "tinyllama:latest")',
                    "replace": f'llm_config.get("ollama", {{}}).get("model", "{_ROUTING_MODEL}")',
                    "line_context": "orchestrator_llm_model",
                }
            ],
            "src/config.py": [
                {
                    "find": f'"orchestrator": os.getenv("AUTOBOT_ORCHESTRATOR_MODEL", "llama3.2:1b")',
                    "replace": f'"orchestrator": os.getenv("AUTOBOT_ORCHESTRATOR_MODEL", "{_ROUTING_MODEL}")',
                    "line_context": "models configuration — orchestrator",
                },
                {
                    "find": f'"classification": os.getenv("AUTOBOT_CLASSIFICATION_MODEL", "gemma2:2b")',
                    "replace": f'"classification": os.getenv("AUTOBOT_CLASSIFICATION_MODEL", "{_CLASSIFICATION_MODEL}")',
                    "line_context": "models configuration — classification",
                },
            ],
            "backend/utils/connection_utils.py": [
                {
                    "find": '"qwen3.5:9b"',
                    "replace": f'"{_DEFAULT_MODEL}"',
                    "line_context": "AUTOBOT_DEFAULT_LLM_MODEL default",
                }
            ],
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
        """Build RTX 4070 + Intel NPU optimization config.

        Model names are derived from SSOT constants loaded from agents.yaml (#2584).
        """
        return {
            "gpu_optimization": {
                "device_id": 0,
                "memory_limit_mb": 10000,
                "concurrent_models": 2,
                "model_rotation": True,
                "preferred_models": [
                    _DEFAULT_MODEL,
                    _RAG_MODEL,
                    _CHAT_MODEL,
                    _ROUTING_MODEL,
                ],
            },
            "npu_optimization": {
                "enabled": True,
                "target_models": [_CLASSIFICATION_MODEL, _EMBEDDING_MODEL],
                "optimization_flags": [
                    "int8_quantization",
                    "dynamic_batching",
                    "memory_pooling",
                ],
            },
            "model_routing": {
                "classification": {
                    "model": _CLASSIFICATION_MODEL,
                    "device": "npu",
                    "priority": "speed",
                },
                "chat": {"model": _CHAT_MODEL, "device": "gpu", "priority": "balanced"},
                "research": {
                    "model": _DEFAULT_MODEL,
                    "device": "gpu",
                    "priority": "quality",
                },
                "rag": {"model": _RAG_MODEL, "device": "gpu", "priority": "reasoning"},
                "code": {
                    "model": _CODE_MODEL,
                    "device": "gpu",
                    "priority": "specialized",
                },
                "system_commands": {
                    "model": _CLASSIFICATION_MODEL,
                    "device": "npu",
                    "priority": "speed",
                },
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
        """Validate that optimizations are working.

        Model names are derived from SSOT constants loaded from agents.yaml (#2584).
        """
        logger.info("Validating optimization results...")
        results = {}
        models = [
            _DEFAULT_MODEL,
            _CLASSIFICATION_MODEL,
            _EMBEDDING_MODEL,
        ]

        for model in models:
            try:
                process = await asyncio.create_subprocess_exec(
                    "ollama",
                    "run",
                    model,
                    "Hello, respond with 'OK'",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)

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
                    1 for v in results.get("validation", {}).values() if v.get("status") == "success"
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
        report_path = self.autobot_root / "analysis" / "ai-ml" / f"llm_optimization_report_{int(time.time())}.json"
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
