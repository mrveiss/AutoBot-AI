# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Experiment entrypoint executed inside the Docker container.

The host mounts:
  /experiment  (read-only) — contains train.py and this script
  /output      (writable)  — results JSON written here

Environment variables (set by ExperimentRunner via --env flags):
  AUTOBOT_EXP_MAX_STEPS, AUTOBOT_EXP_LEARNING_RATE, AUTOBOT_EXP_BATCH_SIZE,
  AUTOBOT_EXP_BLOCK_SIZE, AUTOBOT_EXP_N_LAYER, AUTOBOT_EXP_N_HEAD,
  AUTOBOT_EXP_N_EMBD, AUTOBOT_EXP_DROPOUT, AUTOBOT_EXP_WARMUP_STEPS,
  AUTOBOT_EXP_WEIGHT_DECAY, plus any AUTOBOT_EXP_EXTRA_* entries.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys

from autobot_shared.logging_manager import get_logger

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = get_logger(__name__)

_ENV_PREFIX = "AUTOBOT_EXP_"
_EXTRA_PREFIX = "AUTOBOT_EXP_EXTRA_"

_PARAM_MAP = {
    "MAX_STEPS": "max_steps",
    "LEARNING_RATE": "learning_rate",
    "BATCH_SIZE": "batch_size",
    "BLOCK_SIZE": "block_size",
    "N_LAYER": "n_layer",
    "N_HEAD": "n_head",
    "N_EMBD": "n_embd",
    "DROPOUT": "dropout",
    "WARMUP_STEPS": "warmup_steps",
    "WEIGHT_DECAY": "weight_decay",
}


def _build_train_args() -> list[str]:
    """Translate AUTOBOT_EXP_* env vars into train.py CLI flags."""
    args: list[str] = []
    for env_key, flag in _PARAM_MAP.items():
        value = os.environ.get(f"{_ENV_PREFIX}{env_key}")  # ssot-config-exempt: dynamic env var name (f-string)
        if value is not None:
            args.append(f"--{flag}={value}")
    for key, value in os.environ.items():
        if key.startswith(_EXTRA_PREFIX):
            flag = key[len(_EXTRA_PREFIX) :].lower()
            args.append(f"--{flag}={value}")
    return args


def main() -> int:
    """Run train.py and write a results JSON to /output/result.json."""
    train_script = "/experiment/train.py"
    cmd = [sys.executable, train_script] + _build_train_args()
    logger.info("Running: %s", " ".join(cmd))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    output_path = "/output/result.json"
    payload = {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)

    logger.info("Result written to %s (rc=%d)", output_path, result.returncode)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
