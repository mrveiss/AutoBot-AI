# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reasons for ``repo_tests/secrets_baseline_reasons_guard_test.py`` (#16299 AC5).

A ``.secrets.baseline`` entry is a (filename, type, hashed_secret) triple --
stable across a line-only move (#16353: the baseline carries no line number).
Every entry the baseline holds needs a tracked reason; an exemption you
cannot read is an accident, not a decision
(``docs/developer/RATCHET_BASELINES.md`` rule 1).

The baseline was sampled at AC5's introduction (1,360 entries; 91% "Secret
Keyword", the overwhelming majority test fixtures, CI-only credentials, and
demo values already marked inline `# noqa`/`# nosec` -- not real guessable
production defaults) and found too large for a genuine per-entry manual
review in one slice. The owner ruled a **declared boundary**, not a
comprehensive one:

- The 5 entries matching #16299's own named guessable defaults get a real,
  specific, individually-reviewed reason (``SPECIFIC_REASONS`` below) --
  cross-checked by independently re-hashing each literal (plain SHA1, no
  salt -- matches detect-secrets' "Secret Keyword" hasher empirically) and
  confirming it against the baseline's own ``hashed_secret``, not asserted
  from the filename alone.
- Every other entry present in the baseline at this guard's introduction is
  in ``secrets_baseline_legacy_keys.json`` (kept out of this ``.py`` file --
  1,355 entries would blow the 600-line file-size ratchet), one disclosed,
  generic reason (``LEGACY_REASON``) -- not silently allowed, explicitly
  deferred to #17034 (the full-audit follow-up, v0.9.0).

The legacy set is frozen, not derived from the live baseline at test time: a
baseline entry NOT in that JSON file may not carry ``LEGACY_REASON`` -- that
is the guard's actual boundary enforcement (rule 2: a test must fail when the
boundary moves). A new entry added after this file was written must get its
own real reason in ``SPECIFIC_REASONS``, or the guard fails; it cannot
silently borrow the legacy label.

A count ceiling alone does not enforce this: swapping one legitimate legacy
entry out of the JSON file for a fabricated one, keeping the total at 1,355,
would pass a "does not grow" check while silently laundering a new,
unreviewed entry under the legacy label. ``FROZEN_LEGACY_KEYS_SHA256`` pins
the exact CONTENT (a hash over the canonicalised set, not the count), so ANY
edit -- add, remove, or swap -- must also update this constant, which is a
visible, deliberate act in the diff. #17034 does not need to touch this file
at all: a legacy entry it individually reviews moves to ``SPECIFIC_REASONS``
instead (the guard's membership check is an OR of both sets, so an entry
present in both is harmless) -- this file is permanently frozen from here.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Tuple

BaselineKey = Tuple[str, str, str]

#: sha256 over the canonicalised (sorted, deterministically JSON-dumped) content
#: of secrets_baseline_legacy_keys.json as frozen at #16299's introduction --
#: pins the exact SET, not just its size (see the module docstring for why a
#: count alone is not enough). Computed once; never re-derive it FROM the live
#: file to "fix" a mismatch -- a mismatch means the file changed and that
#: change needs its own review, the same as any other ratchet-baseline edit.
FROZEN_LEGACY_KEYS_SHA256 = "7ecbbf5a24a455625f68f40f297758173297fa673580c2e67ad9ae43ecf3d54e"


def content_hash(keys: frozenset[BaselineKey]) -> str:
    """The same canonicalisation used to compute FROZEN_LEGACY_KEYS_SHA256."""
    canonical = json.dumps(sorted(keys), sort_keys=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


#: The sentinel legacy-boundary reason. A baseline key may carry this ONLY
#: when it is also a member of load_legacy_keys() below -- enforced by the
#: guard, not by convention.
LEGACY_REASON = (
    "legacy entry predating #16299's baseline-reasons guard -- unreviewed, pending the full-audit follow-up (#17034)"
)

#: (filename, type, hashed_secret) -> a real, specific reason. Cross-checked
#: against an independent plain-SHA1 re-hash of each literal at authoring
#: time (see the module docstring).
SPECIFIC_REASONS: dict[BaselineKey, str] = {
    (
        ".env.docker",
        "Secret Keyword",
        "1ba53c9c3dd2dff0ba71a8b942318082315e6f04",
    ): (
        "GRAFANA_ADMIN_PASSWORD default literal 'autobot' -- one of #16299's "
        "named guessable defaults, tracked there for a generate-on-first-run "
        "fix (owner ruling 2026-09-17). Not silently allowed: baselined here "
        "only because the pre-commit hook blocks every .env* edit and the "
        "fix needs the owner to apply Decision 2's protect-files.sh patch "
        "first (see #16299)."
    ),
    (
        "docker/.env.docker",
        "Secret Keyword",
        "1ba53c9c3dd2dff0ba71a8b942318082315e6f04",
    ): (
        "AUTOBOT_DB_PASSWORD default literal 'autobot' -- the same #16299 "
        "named default as .env.docker's GRAFANA_ADMIN_PASSWORD (identical "
        "literal, hence identical hashed_secret). Tracked for "
        "generate-on-first-run; existing installs deliberately keep their "
        "current password per the owner's 2026-09-17 ruling."
    ),
    (
        "autobot-slm-backend/ansible/roles/backend/defaults/main.yml",
        "Secret Keyword",
        "a5c01e694764bcf09315443c6476e283e6f77906",
    ): (
        "backend_secret_key default literal 'change-me-in-production' -- "
        "one of #16299's named guessable defaults. Moving to the "
        "generate-or-reuse pattern roles/postgresql/tasks/databases.yml "
        "already uses for the DB password (#16299)."
    ),
    (
        "autobot-slm-backend/ansible/roles/backend/defaults/main.yml",
        "Secret Keyword",
        "2a440124839a727bdffd380853a93a09212783e8",
    ): (
        "backend_jwt_secret default literal "
        "'autobot-jwt-secret-change-in-production-minimum-32-chars' -- the "
        "other #16299-named default in this file. Already overridden by "
        "SLM_SECRET_KEY when an SLM secrets file is present (#10400); this "
        "default is the standalone-backend fallback path."
    ),
    (
        "autobot-slm-backend/ansible/roles/monitoring/defaults/main.yml",
        "Secret Keyword",
        "d033e22ae348aeb5660fc2140aec35850c4da997",
    ): (
        "grafana_admin_password default literal 'admin' -- #16299's named "
        "Grafana default. Moving to generate-or-reuse (#16299)."
    ),
    # Pinned HuggingFace model revision SHAs and weight-integrity SHA-256
    # digests added by #17087. Both are public identifiers (a git commit SHA
    # on a public HF repo; a checksum whose whole purpose is to be published
    # and compared against) that read as high-entropy hex to the plugin --
    # not secrets by any definition. Each key verified against the actual
    # source string (SHA1 of the literal recomputed and matched to the
    # recorded hashed_secret) before being added here.
    (
        "autobot_shared/pinned_model_registry.py",
        "Hex High Entropy String",
        "b19500dc665817dc424db9a65828621e2bdc89e5",
    ): "pinned revision SHA for 'openai/clip-vit-base-patch32' in `_REGISTRY`, not a secret (#17087).",
    (
        "autobot_shared/pinned_model_registry.py",
        "Hex High Entropy String",
        "19e879c0f9a39f27cf0c07a180747746033a4bd9",
    ): (
        "weight-integrity digest for 'openai/clip-vit-base-patch32' "
        "(pytorch_model.bin) in `_REGISTRY`, not a secret (#17087)."
    ),
    (
        "autobot_shared/pinned_model_registry.py",
        "Hex High Entropy String",
        "75aec676732429ae9a41587261cb01f506a80597",
    ): "pinned revision SHA for 'facebook/wav2vec2-base-960h' in `_REGISTRY`, not a secret (#17087).",
    (
        "autobot_shared/pinned_model_registry.py",
        "Hex High Entropy String",
        "b28418e88f385715a247f0f1616fca1f8cfbfc54",
    ): (
        "weight-integrity digest for 'facebook/wav2vec2-base-960h' "
        "(model.safetensors) in `_REGISTRY`, not a secret (#17087)."
    ),
    (
        "autobot_shared/pinned_model_registry.py",
        "Hex High Entropy String",
        "0602352c490c245314434fa45e354c5b1ea1907b",
    ): "pinned revision SHA for 'openai/whisper-base' in `_REGISTRY`, not a secret (#17087).",
    (
        "autobot_shared/pinned_model_registry.py",
        "Hex High Entropy String",
        "2d1af225089b0708828cd666cd238bbad39640cb",
    ): (
        "weight-integrity digest for 'openai/whisper-base' "
        "(model.safetensors) in `_REGISTRY`, not a secret (#17087)."
    ),
    (
        "autobot_shared/pinned_model_registry.py",
        "Hex High Entropy String",
        "3f3266f3bef50e168052af035a150dac927afe95",  # pragma: allowlist secret
    ): "pinned revision SHA for 'Salesforce/blip2-opt-2.7b' in `_REGISTRY`, not a secret (#17087).",
    (
        "autobot_shared/pinned_model_registry.py",
        "Hex High Entropy String",
        "d18d3efcc2c358ce28fde89b0f15faf7241251f4",  # pragma: allowlist secret
    ): (
        "weight-integrity digest for 'Salesforce/blip2-opt-2.7b' "
        "(model-00001-of-00002.safetensors) in `_REGISTRY`, not a secret (#17087)."
    ),
    (
        "autobot_shared/pinned_model_registry.py",
        "Hex High Entropy String",
        "51c8959773bedd159f21db0e1f75fdc5c69c8bd2",  # pragma: allowlist secret
    ): (
        "weight-integrity digest for 'Salesforce/blip2-opt-2.7b' "
        "(model-00002-of-00002.safetensors) in `_REGISTRY`, not a secret (#17087)."
    ),
    (
        "autobot_shared/pinned_model_registry.py",
        "Hex High Entropy String",
        "2b1d5b4ba121bc95c61f96351c51a71c045c432d",  # pragma: allowlist secret
    ): "pinned revision SHA for 'microsoft/codebert-base' in `_REGISTRY`, not a secret (#17087).",
    (
        "autobot_shared/pinned_model_registry.py",
        "Hex High Entropy String",
        "a70ea28494ddee898e0ee2474dba8691533bbefd",  # pragma: allowlist secret
    ): (
        "weight-integrity digest for 'microsoft/codebert-base' "
        "(pytorch_model.bin) in `_REGISTRY`, not a secret (#17087)."
    ),
    (
        "autobot-npu-worker/resources/windows-npu-worker/app/worker_settings.py",
        "Hex High Entropy String",
        "38f2c4945e06a5ef36f69a0dafb3af9f6664544b",  # pragma: allowlist secret
    ): "pinned revision SHA for 'nomic-ai/nomic-embed-text-v1' in `SUPPORTED_MODELS`, not a secret (#17087).",
    (
        "autobot-npu-worker/resources/windows-npu-worker/app/worker_settings.py",
        "Hex High Entropy String",
        "08df4a98376e596d4425e0cf47b2878e95e70b32",  # pragma: allowlist secret
    ): (
        "weight-integrity digest for 'nomic-ai/nomic-embed-text-v1' "
        "(model.safetensors) in `SUPPORTED_MODELS`, not a secret (#17087)."
    ),
    (
        "autobot-npu-worker/resources/windows-npu-worker/app/worker_settings.py",
        "Hex High Entropy String",
        "a379bdf0b2ab75ccbb6dfa3cef700a18be26a130",  # pragma: allowlist secret
    ): (
        "weight-integrity digest for 'nomic-ai/nomic-embed-text-v1' "
        "(pytorch_model.bin) in `SUPPORTED_MODELS`, not a secret (#17087)."
    ),
    (
        "autobot-npu-worker/resources/windows-npu-worker/app/worker_settings.py",
        "Hex High Entropy String",
        "00d9f4e0808dbd6a8c3d74873c6f71efe1e68d89",  # pragma: allowlist secret
    ): (
        "pinned revision SHA for 'sentence-transformers/all-MiniLM-L6-v2' in "
        "`SUPPORTED_MODELS`, not a secret (#17087)."
    ),
    (
        "autobot-npu-worker/resources/windows-npu-worker/app/worker_settings.py",
        "Hex High Entropy String",
        "76cb94008a639874ff55514a76ad1f5d879e3130",  # pragma: allowlist secret
    ): (
        "weight-integrity digest for 'sentence-transformers/all-MiniLM-L6-v2' "
        "(model.safetensors) in `SUPPORTED_MODELS`, not a secret (#17087)."
    ),
    (
        "autobot-npu-worker/resources/windows-npu-worker/app/worker_settings.py",
        "Hex High Entropy String",
        "1f85d74639de5baf0508312c1384fb61483eca13",  # pragma: allowlist secret
    ): (
        "weight-integrity digest for 'sentence-transformers/all-MiniLM-L6-v2' "
        "(pytorch_model.bin) in `SUPPORTED_MODELS`, not a secret (#17087)."
    ),
    (
        "autobot-npu-worker/resources/windows-npu-worker/app/worker_settings.py",
        "Hex High Entropy String",
        "3377979d2e7b9f5aa625e21f007d97acda28b4ed",  # pragma: allowlist secret
    ): "pinned revision SHA for 'BAAI/bge-small-en-v1.5' in `SUPPORTED_MODELS`, not a secret (#17087).",
    (
        "autobot-npu-worker/resources/windows-npu-worker/app/worker_settings.py",
        "Hex High Entropy String",
        "de99df5fffc19b352c225ea134f5fc267b4c7ad9",  # pragma: allowlist secret
    ): (
        "weight-integrity digest for 'BAAI/bge-small-en-v1.5' "
        "(model.safetensors) in `SUPPORTED_MODELS`, not a secret (#17087)."
    ),
    (
        "autobot-npu-worker/resources/windows-npu-worker/app/worker_settings.py",
        "Hex High Entropy String",
        "741dd5ef2a9ce09b44a21d1c513adab3395afdb3",  # pragma: allowlist secret
    ): (
        "weight-integrity digest for 'BAAI/bge-small-en-v1.5' "
        "(pytorch_model.bin) in `SUPPORTED_MODELS`, not a secret (#17087)."
    ),
    (
        "autobot_shared/pinned_model_registry_test.py",
        "Hex High Entropy String",
        "b19500dc665817dc424db9a65828621e2bdc89e5",
    ): (
        "test fixture `_REVISION` reuses `_REGISTRY`'s 'openai/clip-vit-base-patch32' "
        "revision SHA, not a secret (#17087)."
    ),
}

_LEGACY_KEYS_PATH = Path(__file__).with_name("secrets_baseline_legacy_keys.json")


def load_legacy_keys() -> frozenset[BaselineKey]:
    """The frozen (filename, type, hashed_secret) triples exempted under LEGACY_REASON.

    Loaded from JSON, not inlined, so this module stays well under the
    600-line file-size ratchet -- the set has 1,355 entries.
    """
    with _LEGACY_KEYS_PATH.open(encoding="utf-8") as fh:
        return frozenset(tuple(entry) for entry in json.load(fh))
