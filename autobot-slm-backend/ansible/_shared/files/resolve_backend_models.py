#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Which models the backend env should name, given what the model server holds (#19731).

A CPU-only node skips the GPU-class models on purpose, while the env still pointed roles at them.
A server holding none of those models is CPU-only for this purpose, wherever it runs; roles naming one
then use the fallback, a model it does hold (maintainer decision on #19731). Whatever is still absent is
reported, naming the role. An empty answer proves nothing: on a new install the pull may not have run.

Reads JSON from BACKEND_MODEL_INPUT: held, gpu_models, roles ({var: model}), fallback. Prints JSON: remap, missing.
"""

import json
import os

#: The roles the env points at a GPU-class model when left unset, by the template's own defaults.
GPU_TIER_VARS = frozenset({"backend_llm_model", "backend_instruction_model", "backend_system_model"})


def _name(model: str) -> str:
    return model[: -len(":latest")] if model.endswith(":latest") else model


def resolve(held: list, gpu_models: list, roles: dict, fallback: str) -> dict:
    held_names = {_name(m) for m in held}
    gpu_names = {_name(m) for m in gpu_models}
    if not held_names:
        return {"remap": {}, "missing": {}}
    cpu_only = not held_names & gpu_names and _name(fallback) in held_names
    remap = {
        var: fallback
        for var, model in roles.items()
        if cpu_only and (_name(model) in gpu_names or (not model and var in GPU_TIER_VARS))
    }
    final = {var: model for var, model in {**roles, **remap}.items() if model}  # unset: the template's default
    return {"remap": remap, "missing": {v: m for v, m in final.items() if _name(m) not in held_names}}


if __name__ == "__main__":
    print(json.dumps(resolve(**json.loads(os.environ["BACKEND_MODEL_INPUT"]))))
