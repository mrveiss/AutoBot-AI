#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Which models the backend env should name, given what the model server holds (#19731).

A CPU-only node skips the GPU-class models on purpose, while the env still pointed roles at them.
A server holding none of those models is CPU-only for this purpose, wherever it runs; roles naming one
then use the fallback, a model it does hold (maintainer decision on #19731). Whatever is still absent is
reported, naming the role. An empty answer proves nothing: on a new install the pull may not have run.

Reads JSON from BACKEND_MODEL_INPUT: tags_reply, gpu_models, roles ({var: model}), fallback.
Prints JSON: remap, moved ([var, from, to]), missing. A reply it cannot read changes nothing.
"""

import json
import os

#: The roles the env points at a GPU-class model when left unset, by the template's own defaults.
GPU_TIER_VARS = frozenset({"backend_llm_model", "backend_instruction_model", "backend_system_model"})


def _name(model: str) -> str:
    return model[: -len(":latest")] if model.endswith(":latest") else model


def _held_models(tags_reply) -> list:
    """The model names in the server's reply; empty for anything that is not the expected shape.

    Ansible's templating turns a reply that looks like JSON into a mapping on the way here, so both arrive.
    """
    try:
        models = (json.loads(tags_reply) if isinstance(tags_reply, str) else tags_reply)["models"]
        return [model["name"] for model in models]
    except (ValueError, KeyError, TypeError):
        return []


def resolve_backend_models(tags_reply, gpu_models: list, roles: dict, fallback: str) -> dict:
    held_names = {_name(m) for m in _held_models(tags_reply)}
    gpu_names = {_name(m) for m in gpu_models}
    if not held_names:
        return {"remap": {}, "moved": [], "missing": {}}
    cpu_only = not held_names & gpu_names and _name(fallback) in held_names
    remap = {
        var: fallback
        for var, model in roles.items()
        if cpu_only and (_name(model) in gpu_names or (not model and var in GPU_TIER_VARS))
    }
    final = {var: model for var, model in {**roles, **remap}.items() if model}  # unset: the template's default
    return {
        "remap": remap,
        "moved": [[var, roles[var] or "(template default)", to] for var, to in remap.items()],
        "missing": {v: m for v, m in final.items() if _name(m) not in held_names},
    }


if __name__ == "__main__":
    print(json.dumps(resolve_backend_models(**json.loads(os.environ["BACKEND_MODEL_INPUT"]))))
