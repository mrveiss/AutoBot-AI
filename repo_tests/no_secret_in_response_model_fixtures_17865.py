# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Fixture trees for the response-model secret guard (#17865).

Separated because the guard file crossed the 600-line ceiling and the ceiling
is split, not raised. It also keeps the detector and the evidence apart: a
change to what the guard DOES and a change to what it is TESTED against are
now different diffs, so one cannot quietly accompany the other.

Each entry is `(name, {path: source}, expect_hit)` and every positive is
paired with a clean twin differing by one token, so a fixture cannot pass by
being structurally unlike the thing it contrasts with.
"""

from __future__ import annotations

#: (name, files, expect_hit) — driven through `_build_index` + `_violations`.
DETECTOR_FIXTURES = [
    (
        # THE #17865 SHAPE: secret inherited from a parent in ANOTHER module.
        "inherited-across-modules",
        {
            "autobot-slm-backend/models/s.py": (
                "class Cfg(BaseModel):\n    llm_model: str | None = None\n"
                "class CfgWithKey(Cfg):\n    llm_api_key: str | None = None\n"
            ),
            "autobot-slm-backend/api/r.py": ("@router.get('/x', response_model=CfgWithKey)\ndef h(): ...\n"),
        },
        True,
    ),
    (
        # The same route returning the PARENT is clean.
        "inherited-across-modules-clean",
        {
            "autobot-slm-backend/models/s.py": (
                "class Cfg(BaseModel):\n    llm_model: str | None = None\n"
                "class CfgWithKey(Cfg):\n    llm_api_key: str | None = None\n"
            ),
            "autobot-slm-backend/api/r.py": "@router.get('/x', response_model=Cfg)\ndef h(): ...\n",
        },
        False,
    ),
    (
        # NESTING, not inheritance: reached through a field annotation.
        "nested-model",
        {
            "autobot-slm-backend/models/s.py": (
                "class Provider(BaseModel):\n    api_key: str | None = None\n"
                "class Outer(BaseModel):\n    providers: list[Provider] = []\n"
            ),
            "autobot-slm-backend/api/r.py": "@router.get('/x', response_model=Outer)\ndef h(): ...\n",
        },
        True,
    ),
    (
        # A GENERIC SUBSCRIPT -- invisible to an ast.Name-only reader.
        "generic-subscript",
        {
            "autobot-slm-backend/models/s.py": "class Data(BaseModel):\n    api_key: str | None = None\n",
            "autobot-slm-backend/api/r.py": ("@router.post('/x', response_model=DataResponse[Data])\ndef h(): ...\n"),
        },
        True,
    ),
    (
        "generic-subscript-clean",
        {
            "autobot-slm-backend/models/s.py": "class Data(BaseModel):\n    api_key_ref: str | None = None\n",
            "autobot-slm-backend/api/r.py": ("@router.post('/x', response_model=DataResponse[Data])\ndef h(): ...\n"),
        },
        False,
    ),
    (
        # SAME CLASS NAME IN TWO MODULES. `_build_index` keys by bare name, so
        # the previous version would have let the clean `Cfg` (parsed second,
        # since files are walked in sorted order) OVERWRITE the one carrying the
        # secret -- and the route would have been reported clean. Merging keeps
        # the field. I claimed that in a commit message and had no test for it
        # until CodeRabbit asked (#17865).
        "same-name-collision-across-modules",
        {
            "autobot-slm-backend/models/a_secret.py": ("class Cfg(BaseModel):\n    api_key: str | None = None\n"),
            "autobot-slm-backend/models/b_clean.py": ("class Cfg(BaseModel):\n    llm_model: str | None = None\n"),
            "autobot-slm-backend/api/r.py": "@router.get('/x', response_model=Cfg)\ndef h(): ...\n",
        },
        True,
    ),
    (
        # The same two-module shape with NO secret anywhere stays clean, so the
        # case above cannot be passing merely because collisions are reported.
        "same-name-collision-clean",
        {
            "autobot-slm-backend/models/a_secret.py": ("class Cfg(BaseModel):\n    api_key_ref: str | None = None\n"),
            "autobot-slm-backend/models/b_clean.py": ("class Cfg(BaseModel):\n    llm_model: str | None = None\n"),
            "autobot-slm-backend/api/r.py": "@router.get('/x', response_model=Cfg)\ndef h(): ...\n",
        },
        False,
    ),
    (
        # response_model_exclude, the shape #17846 uses. The FIELD SURVIVES on
        # the model -- only the wire drops it -- so a syntactic guard reports
        # this as a leak unless it reads the exclusion.
        "excluded-nested-is-clean",
        {
            "autobot-slm-backend/models/s.py": (
                "class Provider(BaseModel):\n    api_key: str | None = None\n"
                "class Outer(BaseModel):\n    providers: list[Provider] = []\n"
            ),
            "autobot-slm-backend/api/r.py": (
                "@router.get('/x', response_model=Outer, "
                "response_model_exclude={'providers': {'__all__': {'api_key'}}})\ndef h(): ...\n"
            ),
        },
        False,
    ),
    (
        # THE REGRESSION THAT MATTERS: the same route with the exclusion
        # REMOVED must newly fail. Without this pair the feature could be
        # suppressing everything and still look correct.
        "exclusion-dropped-is-reported",
        {
            "autobot-slm-backend/models/s.py": (
                "class Provider(BaseModel):\n    api_key: str | None = None\n"
                "class Outer(BaseModel):\n    providers: list[Provider] = []\n"
            ),
            "autobot-slm-backend/api/r.py": "@router.get('/x', response_model=Outer)\ndef h(): ...\n",
        },
        True,
    ),
    (
        # The exclusion given as a module-level constant, which is how
        # #17846 writes it (`_NO_PROVIDER_KEYS`) -- the name must resolve.
        "excluded-via-module-constant-is-clean",
        {
            "autobot-slm-backend/models/s.py": (
                "class Provider(BaseModel):\n    api_key: str | None = None\n"
                "class Outer(BaseModel):\n    providers: list[Provider] = []\n"
            ),
            "autobot-slm-backend/api/r.py": (
                "_NO_KEYS = {'providers': {'__all__': {'api_key'}}}\n"
                "@router.get('/x', response_model=Outer, response_model_exclude=_NO_KEYS)\ndef h(): ...\n"
            ),
        },
        False,
    ),
    (
        # Excluding a DIFFERENT field must not launder the secret.
        "excluding-the-wrong-field-still-reports",
        {
            "autobot-slm-backend/models/s.py": (
                "class Provider(BaseModel):\n    api_key: str | None = None\n"
                "class Outer(BaseModel):\n    providers: list[Provider] = []\n"
            ),
            "autobot-slm-backend/api/r.py": (
                "@router.get('/x', response_model=Outer, "
                "response_model_exclude={'providers': {'__all__': {'name'}}})\ndef h(): ...\n"
            ),
        },
        True,
    ),
    (
        # A waived model REUSED on a different route must still be reported.
        "waiver-does-not-follow-the-model",
        {
            "autobot-slm-backend/models/s.py": ("class MFASetupResponse(BaseModel):\n    secret: str | None = None\n"),
            "autobot-slm-backend/api/r.py": (
                "@router.get('/elsewhere', response_model=MFASetupResponse)\ndef h(): ...\n"
            ),
        },
        True,
    ),
    (
        # ...while the waived route itself stays clean.
        "waiver-applies-to-its-own-route",
        {
            "autobot-slm-backend/models/s.py": ("class MFASetupResponse(BaseModel):\n    secret: str | None = None\n"),
            "autobot-slm-backend/api/r.py": ("@router.post('/setup', response_model=MFASetupResponse)\ndef h(): ...\n"),
        },
        False,
    ),
]
