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
FROZEN_LEGACY_KEYS_SHA256 = (
    "7ecbbf5a24a455625f68f40f297758173297fa673580c2e67ad9ae43ecf3d54e"  # pragma: allowlist secret
)


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
        "1ba53c9c3dd2dff0ba71a8b942318082315e6f04",  # pragma: allowlist secret
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
        "1ba53c9c3dd2dff0ba71a8b942318082315e6f04",  # pragma: allowlist secret
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
        "a5c01e694764bcf09315443c6476e283e6f77906",  # pragma: allowlist secret
    ): (
        "backend_secret_key default literal 'change-me-in-production' -- "
        "one of #16299's named guessable defaults. Moving to the "
        "generate-or-reuse pattern roles/postgresql/tasks/databases.yml "
        "already uses for the DB password (#16299)."
    ),
    (
        "repo_tests/ansible_generated_secrets_16299_test.py",
        "Secret Keyword",
        "a5c01e694764bcf09315443c6476e283e6f77906",  # pragma: allowlist secret
    ): (
        "Same literal 'change-me-in-production' as the backend/defaults/main.yml "
        "entry above (identical hash) -- this test asserts the align-guard clause "
        "quotes that exact literal, so the guard fires only against the known "
        "shipped default and never against an operator's own override (#17129)."
    ),
    (
        "autobot-slm-backend/ansible/roles/slm_manager/tasks/main.yml",
        "Secret Keyword",
        "d033e22ae348aeb5660fc2140aec35850c4da997",  # pragma: allowlist secret
    ): (
        "grafana_admin_password generate-or-reuse guard compares against the "
        "literal 'admin' (monitoring role's own shipped default), not a real "
        "credential -- the guard exists so an operator-set password is never "
        "silently regenerated (#17129)."
    ),
    (
        "repo_tests/ansible_generated_secrets_16299_test.py",
        "Secret Keyword",
        "d033e22ae348aeb5660fc2140aec35850c4da997",  # pragma: allowlist secret
    ): (
        "Same literal 'admin' as the slm_manager/tasks/main.yml entry above "
        "(identical hash) -- this test asserts the generate-or-reuse guard "
        "clause quotes that exact literal, statically (#17129)."
    ),
    (
        "autobot-slm-backend/ansible/roles/backend/defaults/main.yml",
        "Secret Keyword",
        "2a440124839a727bdffd380853a93a09212783e8",  # pragma: allowlist secret
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
        "d033e22ae348aeb5660fc2140aec35850c4da997",  # pragma: allowlist secret
    ): (
        "grafana_admin_password default literal 'admin' -- #16299's named "
        "Grafana default. Moving to generate-or-reuse (#16299)."
    ),
    (
        "autobot-backend/api/vnc_handshake_bridge_test.py",
        "Hex High Entropy String",
        "d782ccb6785b5e3cef91a149f946a38cea88fb81",  # pragma: allowlist secret
    ): (
        'the test fixture byte literal `b"1234567890ABCDEF"` -- a 16-byte RFB '  # pragma: allowlist secret
        "frame-reassembly payload (digits + hex letters), not a secret. "
        "Re-hashed and confirmed against the baseline's hashed_secret (#17096)."
    ),
    (
        "autobot-backend/tests/migrations/test_orphan_secret_repair.py",
        "Secret Keyword",
        "665b1e3851eefefa3fb878654292f16597d25155",  # pragma: allowlist secret
    ): (
        'the literal `secret_type="api_key"` -- an enum-style type label the '  # pragma: allowlist secret
        "'Secret Keyword' heuristic matches on the `secret_type` field name, "
        "not a secret value. Re-hashed and confirmed (#17096)."
    ),
    (
        "autobot-slm-backend/ansible/roles/vnc/tasks/register-vnc-password.yml",
        "Secret Keyword",
        "d5ab78d646b6f314df50654a6e03ecba9b684662",  # pragma: allowlist secret
    ): (
        "the literal `secret_type: vnc_password` -- the same enum-style "
        "field-name false positive as test_orphan_secret_repair.py's "
        "`secret_type`, here naming what kind of secret the task registers, "
        'not its value (`value: "{{ vnc_password_result.stdout }}"` is the '
        "actual password, a Jinja expression with no literal to flag). "
        "Re-hashed and confirmed (#17096)."
    ),
    # #13708/#16771 content-redaction feature (merged after the above): every
    # entry below is a synthetic, deliberately-fake credential in a test that
    # exercises the redaction machinery itself, or an illustrative comment
    # documenting the credential SHAPE that machinery matches -- re-hashed and
    # confirmed against the baseline's own hashed_secret for each (#17096).
    # Values are described, not quoted verbatim, so this file does not itself
    # reproduce a secret-shaped literal.
    (
        "autobot-backend/knowledge/connectors/content_extraction_test.py",
        "Secret Keyword",
        "ccff80b45596a033326d7d752630354fcfc07a7f",  # pragma: allowlist secret
    ): ("line 73's fake `_PASSWORD_SHAPED` fixture, proving extracted document text is redacted before indexing."),
    (
        "autobot-backend/llc/tests/test_replay.py",
        "Secret Keyword",
        "d0422de28f09f6db00bb3d5e2e4b5f3319b703fa",  # pragma: allowlist secret
    ): ("line 580's fake api_key fixture asserting replay redacts it (line 588)."),
    (
        "autobot-backend/llm_shared/tests/test_credential_redaction.py",
        "Base64 High Entropy String",
        "48cbefb36880934b2caaf8c73c7d473fb57389d6",  # pragma: allowlist secret
    ): ("line 24's fake API-key-shaped text fixture for test_redact_string."),
    (
        "autobot-backend/llm_shared/tests/test_credential_redaction.py",
        "Secret Keyword",
        "192f7ad3497a1742d5dff94c0c7115f90de787b8",  # pragma: allowlist secret
    ): ("line 33's fake api_key dict-value fixture for test_redact_dict_simple."),
    (
        "autobot-backend/llm_shared/tests/test_credential_redaction.py",
        "Secret Keyword",
        "cb2a10760c32ea66c7322bd147527e460ccd7790",  # pragma: allowlist secret
    ): ("line 49's fake nested api_key dict-value fixture for test_redact_dict_nested."),
    (
        "autobot-backend/llm_shared/tests/test_credential_redaction.py",
        "Secret Keyword",
        "00cafd126182e8a9e7c01bb2f0dfd00496be724f",  # pragma: allowlist secret
    ): (
        "one of lines 63-67's five fake dict-value fixtures (test_redact_dict_variations), proving every "
        "sensitive key-name variant -- api_key/apiKey/api-key/bearer_token/password -- is redacted."
    ),
    (
        "autobot-backend/llm_shared/tests/test_credential_redaction.py",
        "Secret Keyword",
        "c636e8e238fd7af97e2e500f8c6f0f4c0bedafb0",  # pragma: allowlist secret
    ): (
        "one of lines 63-67's five fake dict-value fixtures (test_redact_dict_variations) -- same test as "
        "the entry above."
    ),
    (
        "autobot-backend/llm_shared/tests/test_credential_redaction.py",
        "Secret Keyword",
        "08175ec631c367891f55c615fb8d710a1001362b",  # pragma: allowlist secret
    ): (
        "one of lines 63-67's five fake dict-value fixtures (test_redact_dict_variations) -- same test as "
        "the two entries above."
    ),
    (
        "autobot-backend/llm_shared/tests/test_credential_redaction.py",
        "Secret Keyword",
        "c33081e4f816fb9b2b9e81008254e5e4e1d9942c",  # pragma: allowlist secret
    ): ("line 83's fake api_key dict-value fixture for test_safe_repr."),
    (
        "autobot-backend/llm_shared/tests/test_credential_redaction.py",
        "Basic Auth Credentials",
        "9b2628a7a9d2683aea301f13f0f366437b0200a8",  # pragma: allowlist secret
    ): ("line 124's fake basic-auth connection-string fixture for test_redact_string_catches_a_basic_auth_url."),
    (
        "autobot_shared/secret_redaction.py",
        "Basic Auth Credentials",
        "1a91d62f7ca67399625a4368a6ab5d4a3baa6073",  # pragma: allowlist secret
    ): (
        "line 27's docstring example of a database URL's userinfo shape -- illustrates why "
        "database_url/redis_url are redacted at the userinfo only, not a real credential."
    ),
    (
        "autobot_shared/secret_redaction.py",
        "Basic Auth Credentials",
        "5baa61e4c9b93f3f0682250b6cf8331b7ee68fd8",  # pragma: allowlist secret
    ): ("the comment above `_BASIC_AUTH_URL_RE` documenting its matched shape, not a credential."),
    (
        "autobot_shared/secret_redaction_test.py",
        "Base64 High Entropy String",
        "18fdf21db6a592dac66e4bcefad19d6b8d0428f4",  # pragma: allowlist secret
    ): (
        "one of lines 30-47's constructed credential-shaped fixtures (provider-token-shaped constants "
        "built via string concatenation specifically so no literal-looking secret sits in source)."
    ),
    (
        "autobot_shared/secret_redaction_test.py",
        "Base64 High Entropy String",
        "57a52faeaafd478fd9527b1ede01f458c42342e3",  # pragma: allowlist secret
    ): ("one of lines 30-47's constructed credential-shaped fixtures -- same file/mechanism as the entry above."),
    (
        "autobot_shared/secret_redaction_test.py",
        "Base64 High Entropy String",
        "8c98e5c29e7bcb5cd07e007a5962734f632fd8de",  # pragma: allowlist secret
    ): ("one of lines 30-47's constructed credential-shaped fixtures -- same file/mechanism as the two entries above."),
    (
        "autobot_shared/secret_redaction_test.py",
        "Basic Auth Credentials",
        "9b2628a7a9d2683aea301f13f0f366437b0200a8",  # pragma: allowlist secret
    ): (
        "line 58's fake basic-auth connection-string fixture (same literal, same hash, as "
        "test_credential_redaction.py's line 124 -- both test the same basic-auth-URL detection)."
    ),
    (
        "autobot_shared/secret_redaction_test.py",
        "Hex High Entropy String",
        "d17f9b8dad106518f4a99222bfa0a316c004e252",  # pragma: allowlist secret
    ): (
        'line 109\'s `_FALSE_POSITIVES` commit-SHA fixture (`"commit_sha"`), split via string '
        "concatenation, proving scan_content_for_credentials does NOT flag ordinary commit-SHA-shaped "
        "text -- not the PEM fixture; correcting an earlier mislabel in this entry (review)."
    ),
    # #13708's redaction-feature test files (carried by #17102 into #17108):
    # 7 of the 8 files below share one local fixture, an OpenAI-key-shaped
    # literal (same value as autobot_shared/secret_redaction_test.py's own
    # _OPENAI_SHAPED constant) assigned to a local `_SECRET`/`secret` name,
    # flagged twice each (Base64 High Entropy String + Secret Keyword) --
    # verified per file at its own flagged line, not assumed from the others.
    (
        "autobot-backend/api/knowledge_upload_redaction_test.py",
        "Base64 High Entropy String",
        "18fdf21db6a592dac66e4bcefad19d6b8d0428f4",  # pragma: allowlist secret
    ): ("line 25's local `_SECRET` fixture (see the module note above SPECIFIC_REASONS)."),
    (
        "autobot-backend/api/knowledge_upload_redaction_test.py",
        "Secret Keyword",
        "7ce6ed3727ece51d2219f2bdc7f6db3594dc4d7f",  # pragma: allowlist secret
    ): ("line 25's local `_SECRET` fixture -- same line as the entry above, second plugin match."),
    (
        "autobot-backend/knowledge/bulk_restore_redaction_test.py",
        "Base64 High Entropy String",
        "18fdf21db6a592dac66e4bcefad19d6b8d0428f4",  # pragma: allowlist secret
    ): ("line 22's local `_SECRET` fixture (see the module note above SPECIFIC_REASONS)."),
    (
        "autobot-backend/knowledge/bulk_restore_redaction_test.py",
        "Secret Keyword",
        "7ce6ed3727ece51d2219f2bdc7f6db3594dc4d7f",  # pragma: allowlist secret
    ): ("line 22's local `_SECRET` fixture -- same line as the entry above, second plugin match."),
    (
        "autobot-backend/knowledge/connectors/gdrive_test.py",
        "Base64 High Entropy String",
        "18fdf21db6a592dac66e4bcefad19d6b8d0428f4",  # pragma: allowlist secret
    ): ("line 259's local `secret` fixture (see the module note above SPECIFIC_REASONS)."),
    (
        "autobot-backend/knowledge/connectors/gdrive_test.py",
        "Secret Keyword",
        "7ce6ed3727ece51d2219f2bdc7f6db3594dc4d7f",  # pragma: allowlist secret
    ): ("line 259's local `secret` fixture -- same line as the entry above, second plugin match."),
    (
        "autobot-backend/knowledge/connectors/onedrive_test.py",
        "Base64 High Entropy String",
        "18fdf21db6a592dac66e4bcefad19d6b8d0428f4",  # pragma: allowlist secret
    ): ("line 250's local `secret` fixture (see the module note above SPECIFIC_REASONS)."),
    (
        "autobot-backend/knowledge/connectors/onedrive_test.py",
        "Secret Keyword",
        "7ce6ed3727ece51d2219f2bdc7f6db3594dc4d7f",  # pragma: allowlist secret
    ): ("line 250's local `secret` fixture -- same line as the entry above, second plugin match."),
    (
        "autobot-backend/knowledge/pipeline/runner_test.py",
        "Base64 High Entropy String",
        "18fdf21db6a592dac66e4bcefad19d6b8d0428f4",  # pragma: allowlist secret
    ): ("line 167's local `secret` fixture (see the module note above SPECIFIC_REASONS)."),
    (
        "autobot-backend/knowledge/pipeline/runner_test.py",
        "Secret Keyword",
        "7ce6ed3727ece51d2219f2bdc7f6db3594dc4d7f",  # pragma: allowlist secret
    ): ("line 167's local `secret` fixture -- same line as the entry above, second plugin match."),
    (
        "autobot-backend/knowledge/versioning_redaction_16985_test.py",
        "Base64 High Entropy String",
        "18fdf21db6a592dac66e4bcefad19d6b8d0428f4",  # pragma: allowlist secret
    ): ("line 21's local `_SECRET` fixture (see the module note above SPECIFIC_REASONS)."),
    (
        "autobot-backend/knowledge/versioning_redaction_16985_test.py",
        "Secret Keyword",
        "7ce6ed3727ece51d2219f2bdc7f6db3594dc4d7f",  # pragma: allowlist secret
    ): ("line 21's local `_SECRET` fixture -- same line as the entry above, second plugin match."),
    (
        "autobot-backend/tests/knowledge/test_facts_redaction_16985.py",
        "Base64 High Entropy String",
        "18fdf21db6a592dac66e4bcefad19d6b8d0428f4",  # pragma: allowlist secret
    ): ("line 23's local `_SECRET` fixture (see the module note above SPECIFIC_REASONS)."),
    (
        "autobot-backend/tests/knowledge/test_facts_redaction_16985.py",
        "Secret Keyword",
        "7ce6ed3727ece51d2219f2bdc7f6db3594dc4d7f",  # pragma: allowlist secret
    ): ("line 23's local `_SECRET` fixture -- same line as the entry above, second plugin match."),
    # store_fact_sanitize_16770_test.py: 3 test functions, each a fake
    # credential-bearing URL proving add_url_to_knowledge's metadata fields
    # (source/source_url/url) are redacted -- #13708 round 4's own named gap.
    (
        "autobot-backend/knowledge/store_fact_sanitize_16770_test.py",
        "Secret Keyword",
        "57d40f23cf6cb173ee25dde2b72251a6d90b8521",  # pragma: allowlist secret
    ): (
        "line 184's fake `?api_key=sk-...` query-string fixture for "
        "test_a_credential_bearing_source_url_is_redacted."
    ),
    (
        "autobot-backend/knowledge/store_fact_sanitize_16770_test.py",
        "Secret Keyword",
        "c7b9112565446bcfff5788d3f3df8d7c0b06aed8",  # pragma: allowlist secret
    ): (
        "line 194's fake `user:hunter2@` basic-auth URL fixture for "
        "test_basic_auth_userinfo_in_source_url_is_redacted."
    ),
    (
        "autobot-backend/knowledge/store_fact_sanitize_16770_test.py",
        "Basic Auth Credentials",
        "f3bbbd66a63d4bf1747940578ec3d0103530e21d",  # pragma: allowlist secret
    ): (
        "line 194's fake `user:hunter2@` basic-auth URL fixture -- same line as the entry "
        "above, second plugin match. Independently re-hashed plain SHA1('hunter2') and confirmed."
    ),
    (
        "autobot-backend/knowledge/store_fact_sanitize_16770_test.py",
        "Secret Keyword",
        "ebf1b4b932ed9187ba915cf0cdd8e4fff883932c",  # pragma: allowlist secret
    ): (
        "line 204's fake `user:hunter2@` basic-auth URL fixture (the source_url/url field-name "
        "variant) for test_source_url_and_url_fields_are_also_redacted."
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
