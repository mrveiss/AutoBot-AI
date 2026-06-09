# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Server-side Vega-Lite v5 spec validation for Phase 2 chart cells (MVA-484).

Enforces the security model from the spec (§1.4):
- Only data.values inline data allowed; data.url / data.sequence / data.grapher rejected.
- No HTTP-fetching transform types (fold, lookup with external source).
- config.animation.duration forced to 0.
- executable always false (Phase 3 reserved).
- Optional JSON-Schema conformance check via jsonschema if the library is present.
"""

from __future__ import annotations

import copy
from typing import Any

_VEGALITE_V5_SCHEMA_URI = "https://vega.github.io/schema/vega-lite/v5.json"

_FORBIDDEN_DATA_KEYS = frozenset({"url", "sequence", "grapher", "sphere", "topojson"})

# Transform types that can issue HTTP requests.
_FORBIDDEN_TRANSFORM_TYPES = frozenset({"fold", "lookupsFrom"})


def validate_vegalite_spec(spec: Any) -> dict:
    """
    Validate and sanitize a Vega-Lite v5 spec dict.

    Returns the sanitized spec with config.animation.duration forced to 0.
    Raises ValueError with a human-readable message on any violation.
    """
    if not isinstance(spec, dict):
        raise ValueError("richPayload.spec must be a JSON object.")

    # $schema must identify Vega-Lite v5
    schema_uri = spec.get("$schema", "")
    if not isinstance(schema_uri, str) or "vega-lite/v5" not in schema_uri:
        raise ValueError(
            f"richPayload.spec.$schema must be the Vega-Lite v5 schema URI "
            f"(e.g. '{_VEGALITE_V5_SCHEMA_URI}'). Got: {schema_uri!r}"
        )

    _check_data_sources(spec)
    _check_transforms(spec)

    # Deep-copy so we can safely mutate
    spec = copy.deepcopy(spec)
    _force_animation_off(spec)

    # Optional: full JSON-Schema conformance via jsonschema
    _jsonschema_validate(spec)

    return spec


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _check_data_sources(spec: dict) -> None:
    """Reject any data source that would cause a network fetch."""
    for data_obj in _iter_data_objects(spec):
        if not isinstance(data_obj, dict):
            continue
        forbidden = _FORBIDDEN_DATA_KEYS & data_obj.keys()
        if forbidden:
            key = next(iter(forbidden))
            raise ValueError(
                f"richPayload.spec.data.{key} is not allowed. " "Only inline data (data.values) is permitted."
            )
        # data.values must be a list when present
        if "values" in data_obj and not isinstance(data_obj["values"], list):
            raise ValueError("richPayload.spec.data.values must be an array.")


def _iter_data_objects(spec: dict):
    """Yield all data objects from a spec (top-level and layer/concat/facet children)."""
    if "data" in spec:
        yield spec["data"]
    for key in ("layer", "concat", "hconcat", "vconcat", "spec"):
        child = spec.get(key)
        if isinstance(child, list):
            for item in child:
                if isinstance(item, dict):
                    yield from _iter_data_objects(item)
        elif isinstance(child, dict):
            yield from _iter_data_objects(child)


def _check_transforms(spec: dict) -> None:
    """Reject transform types that can issue HTTP requests."""
    transforms = spec.get("transform", [])
    if not isinstance(transforms, list):
        return
    for t in transforms:
        if not isinstance(t, dict):
            continue
        forbidden = _FORBIDDEN_TRANSFORM_TYPES & t.keys()
        if forbidden:
            key = next(iter(forbidden))
            raise ValueError(
                f"richPayload.spec.transform contains a forbidden transform type '{key}'. "
                "Only inline transforms are permitted."
            )


def _force_animation_off(spec: dict) -> None:
    """Set config.animation.duration = 0 regardless of what the agent emitted."""
    config = spec.setdefault("config", {})
    if not isinstance(config, dict):
        spec["config"] = {}
        config = spec["config"]
    animation = config.setdefault("animation", {})
    if not isinstance(animation, dict):
        config["animation"] = {}
        animation = config["animation"]
    animation["duration"] = 0


def _jsonschema_validate(spec: dict) -> None:
    """
    Validate spec against the bundled Vega-Lite v5 JSON Schema if jsonschema
    is installed. Silently skips when not available (structural checks above are
    the primary gate).
    """
    try:
        import jsonschema

        schema = _load_vegalite_schema()
        if schema is None:
            return
        try:
            jsonschema.validate(instance=spec, schema=schema)
        except jsonschema.ValidationError as exc:
            raise ValueError(f"Vega-Lite v5 schema validation failed: {exc.message}") from exc
    except ImportError:
        pass


def _load_vegalite_schema() -> dict | None:
    """
    Load the bundled Vega-Lite v5 JSON Schema from the resources directory.
    Returns None if the schema file is not present (graceful degradation).
    """
    import json
    import pathlib

    schema_path = pathlib.Path(__file__).parent / "resources" / "vega-lite-v5-schema.json"
    if not schema_path.exists():
        return None
    try:
        return json.loads(schema_path.read_text())
    except Exception:
        return None
