# Redaction boundary — which redactor for which shape of problem

Trigger: adding a redactor, adding a detector to one, or picking which module to
call when something sensitive must not reach a log, an LLM, or a peer.

`#16688` asked which of the parallel redaction implementations is canonical.
`#17336` and `#17337` answered it: **one module owns "is this name a credential"
-- `autobot_shared/secret_redaction.py` -- with one shared vocabulary and two
named matching policies.** The one-line rule:

> **One module owns the credential vocabulary. Callers choose a `MatchPolicy`,
> never a word list.**

## The census -- three modules, down from seven

Measured by `repo_tests/redaction_concept_census_test.py` over every tracked
production source. A module is *in the census* when it both exposes a
`redact`/`scrub`/`mask` entry point **and** declares a detector of its own -- a
compiled pattern naming a secret, a vocabulary of secret nouns, or an enum of
secret/PII types. Calling someone else's redactor does not count.

| module | own vocabulary | match | shape it owns | census |
|---|---|---|---|---|
| `autobot_shared/secret_redaction.py` (+ its vocabulary sibling `secret_redaction_vocabulary.py`) | `CREDENTIAL_SUFFIXES` + `AUTHORIZATION_TERMS` + `BROAD_ONLY_STEMS` | `MatchPolicy.PRECISE` / `BROAD` | field names, mappings, log lines, free-text credentials | in |
| `autobot-backend/a2a/pii_pipeline.py` | `PIIType` + regex detectors | regex | PII types and BLOCK/REDACT/HASH policy | in |
| `autobot-backend/llm_shared/credential_redaction.py` | `API_KEY_PATTERNS` | regex | dict / log-record redaction (LLM layer); keys via `BROAD` | in |
| `autobot_shared/security/redaction.py` | none | -- | AWS ARN identifiers, log-value neutralisation; re-exports `redact_text` / `redact_mapping` | out (#17336) |
| `autobot-backend/chat_workflow/cot_events.py` | none | `BROAD` | chain-of-thought event args | out (#17337) |
| `autobot-backend/llc/services/portability.py` | none | `PRECISE` | company-template export | out (#17337) |
| `autobot-backend/services/config_revision_service.py` | none | `BROAD` | config revision snapshots | out (#17337) |
| `autobot-backend/security/chat_message_safety.py` | none -- composes | -- | the chat entry point | out (composes) |

`chat_message_safety.py` is the shape to copy: real redaction policy that
declares no detector at all and composes the canonical ones.

## The rule: one module, two named policies

`secret_redaction.MatchPolicy` is the precision/recall split, kept as a
*parameter of one implementation* rather than as two modules that each claimed
to be canonical:

| policy | matches | location suffixes (`_path`, `_file`, `_dir`, `_id`) | use when |
|---|---|---|---|
| `PRECISE` (default) | name equals a noun, or ends with `_<noun>` | exempt | over-masking destroys a diagnostic or breaks a round-trip: config `__repr__`, URL query params, template export |
| `BROAD` | a noun appears anywhere in the lowercased name with `_`/`-` stripped | not exempt (`tls_key_path` is masked) | over-masking is free and a leak is not: log lines, ansible extra-vars, event payloads, stored snapshots |

Why two: `tokenizers_parallelism` and `tls_key_path` must stay readable in
SSOT config's `__repr__`; a secret under an unanticipated key name must still
be masked in a log line. Both are right at their own call sites.

A **count or limit of a credential noun** (`secret_redaction.is_quantity_field`:
`max_`/`min_`/`num_`/`total_`/`input_`/`output_`/`prompt_`/`completion_`/`cached_` +
a *plural* noun, or a name ending `_count`/`_limit`/`_len`/`_length`/`_size` whose
stem ends in a noun) is a number, not a credential -- but **only the template
export and the API config readout** act on that. Both pass
`exempt_counts=True` to `is_credential_entry`: `portability._scrub_adapter_config`,
because without it `max_tokens=4096` became `{{MAX_TOKENS}}` and no longer imported as a
number; and `redact_nested` for `GET /api/llm/config` and `GET /api/llm/current` (#18193),
because main returned those trees unredacted, so masking `max_tokens` would be a new
change for the settings UI that reads it (nothing leaves an existing caller's masked
set). Every other caller keeps masking it exactly as its retired matcher did (`max_tokens=4096` is masked by
`cot_events`, `config_revision`, `redact_mapping`, `redact_dict`, `redact_value`):
the owner decision on `#17336` and `#17337` AC2 say no key leaves the masked set.

The value check applies everywhere: under a quantity-shaped name, a value that is
not a real int/float (a JWT, `sk-...`, a **digit string** -- PIN-shaped --, a bool,
a list, a dict) is masked by both policies. `is_credential_field(name)` is the
name-only vocabulary check, for callers with no value; every value-bearing caller
uses `is_credential_entry`, and
`repo_tests/credential_field_name_only_17336_test.py` fails on any new
`is_credential_field` reference outside its reviewed value-free allowlist.
`max_token_secret`, `max_password` and `token_count_secret` are not quantity names
and stay masked.


**One recursive mapping redactor (#18205).** `redact_nested` is the only one. `redact_dict` composes it with
`exempt_counts=False` (it always masked `max_tokens`, so no name leaves its masked set) and
`extra_scan=redact_string` (its own `API_KEY_PATTERNS`, including the 32+ character generic key, run over every
string left unmasked; `replay_service._redact_sensitive` / `_redact_log_dict`, `safe_repr` and
`CredentialRedactionFilter` all depend on that). **Disclosure fix:** `redact_dict` used to reveal
`value[:4]...value[-4:]` of a credential string and `***` for other types; it now returns the fixed-width
`REDACTED_PLACEHOLDER` for both, because eight characters of a key are a disclosure. `redact_api_key` (used by
`redact_string`'s `API_KEY_PATTERNS` matches inside free text, so `CredentialRedactionFilter` and `safe_repr`)
returns the same placeholder, so no `llm_shared` path reveals any part of a key. Behaviour that
changed: tuples and sets are now walked (the old walk skipped them), and `None`/`""` under a credential name
is returned as-is (nothing to hide) instead of `***`.

**One placeholder per purpose (#19337).** `autobot_shared.secret_redaction` holds both spellings: `REDACTED_PLACEHOLDER`
(`**********`) replaces a redacted *value* (dict fields, events, stored snapshots), and `LOG_MASK` (`***`) replaces a
secret scrubbed out of free *text* (log lines, error messages, output). A new redactor imports one of them and never
spells its own; `repo_tests/redaction_placeholder_one_home_19337_test.py` counts the spellings left outside the home
under a down-only pin (the remaining display masks are listed on #19337). Config revisions stored before #19337 keep
`***REDACTED***`; nothing compares it, so old rows are left as they are.

**Behaviour that changed in `redact_nested` / `redact_dict` (#18205).**
- A URL under a credential name is masked whole by `redact_dict` (`mask_credential_urls=True`, so its masked set
  never shrinks against base: `webhook_secret_url`, `token_url`, `auth_url` all `**********`). `redact_nested`'s
  default masks whole too, except under a plain endpoint name (`token_url`, `auth_url`, `oauth_token_endpoint`,
  `authorization_url`, `db_dsn`): every name part is one of `ENDPOINT_NAME_WORDS`, so the URL keeps its host and
  loses userinfo and credential query params. `webhook_secret_url`, `api_key_url` and `signed_token_url` are
  masked whole.
- Leaves of type `datetime`, `date`, `time`, `timedelta`, `UUID` and `Decimal` pass through under an ordinary
  name (replay snapshots carry them; base passed them). Under a credential name they are masked. Any other
  type, `bytes` included, still fails closed.

**Whole-token nouns (#18194).** `pin` and `passcode` are credentials too, but `pin` is also a verb and
a prefix (`pin_memory`, `pinned_revision`, `spinner`, `opinion`), so they are not suffix or substring
nouns. `secret_redaction_vocabulary.WHOLE_TOKEN_NOUNS` is consulted by BOTH policies: the name is split
on `_ - .` and camelCase, and it matches when its last tokens are `pin`, `pin code`, `pincode`, `pin hash|digest|salt` or `passcode`
(`pin`, `user_pin`, `pinCode`, `card.pin`, `pin_hash`, `passcode` masked; `pin_length`, `pin_memory`,
`pinned_revision`, `spinner`, `opinion`, `pinyin` unmasked). Never add them to `BROAD_FRAGMENTS`: it is
substring-matched and feeds `credential_redaction.SENSITIVE_KEYS`.
**Consequence of the owner's whole-word ruling, not a bug:** `gpio_pin`, `led_pin` and `version_pin` ARE masked,
because their last token is `pin` (pinned by `test_a_pin_in_any_other_sense_is_masked_too_by_the_whole_word_ruling`). The vocabulary and matcher live in
`secret_redaction_vocabulary.py` (split from `secret_redaction.py` for the 600-line ceiling); it is the same
canonical module, re-exported, and the census guard treats the pair as one home.

**File names (#19339).** Whether a FILE name holds a secret is judged by
`secret_redaction_vocabulary.is_credential_file_stem` (re-exported by `secret_redaction`), which reuses `PRECISE`
on each word-aligned prefix of the stem and on the same prefix with its last separator removed
(`pass_word` -> `password`). `autobot_shared/secret_file_names.py` keeps only the file globs and calls it; it declares
no nouns. `AMBIGUOUS_FILE_NOUNS` (`seed_data.sql`, `salt_states.sls`) and `FILE_COMPOUND_NOUNS` (`apikeys.json`) are
file-only tables, not field vocabulary: never consult them for a field name.

`BROAD` is a superset of `PRECISE` by construction (same nouns, plus
`AUTHORIZATION_TERMS` and `BROAD_ONLY_STEMS`, which would over-mask as
suffixes: `use_auth` is a flag, `is_private` is not a secret).

### Which caller uses which policy

Recorded at `#17336` / `#17337` so that no site silently changed policy.

| caller | before | after |
|---|---|---|
| `RedactedReprMixin` (SSOT config, pki, slm config, tracing config) | suffix | `PRECISE` |
| `redact_url_credentials` query params | suffix | `PRECISE` |
| `redact_mapping` (slm `code_sync` extra-vars) | substring, 8 fragments | `BROAD` |
| `redact_nested` (`GET /api/llm/config` and `/current` response bodies, #18193) | none (new caller) | `BROAD`, `exempt_counts=True` |
| `redact_text` (slm `monitoring`, bedrock errors) | text regex | same regex, moved into `secret_redaction` |
| `credential_redaction.redact_dict` | normalized substring | `BROAD`, `exempt_counts=False`: a thin composition over `redact_nested` (#18205) |
| `cot_events._is_sensitive` | own 13-fragment substring | `BROAD` |
| `portability._scrub_adapter_config` | own 12-name exact match | `PRECISE` (`exempt_counts`; `False`/`None`/`True` kept except `True` under the 12 names) |
| `config_revision_service._is_secret_key` | own 5-fragment substring | `BROAD` |

Every migration only **widened** the masked set. Measured per caller over
`autobot_shared/redaction_corpus_17336.txt` (3,403 names) against a frozen copy of
what `origin/main` masked at that caller
(`secret_redaction_policy_17336_test.py::test_no_name_leaves_the_masked_set_at_any_caller`,
values int, float, digit string, JWT and `True`):

| caller | masked on main | here: int | digit string | JWT | `True` | removed |
|---|---|---|---|---|---|---|
| `redact_value` / `RedactedReprMixin` / URL query (`PRECISE`) | 1132 | 1143 | 1404 | 1404 | 1404 | 0 |
| `redact_mapping` (`BROAD`) | 1984 | 2449 | 2449 | 2449 | 2449 | 0 |
| `credential_redaction.redact_dict` (`BROAD`) | 2384 | 2449 | 2449 | 2449 | 2449 | 0 |
| `cot_events` (`BROAD`) | 1831 | 2449 | 2449 | 2449 | 2449 | 0 |
| `config_revision_service` (`BROAD`) | 1590 | 2449 | 2449 | 2449 | 2449 | 0 |
| `portability` export (`PRECISE`, `exempt_counts`) | 14 | 1052 | 1404 | 1404 | 14 | 0 |

The export layer (`llc/services/portability_export_names.py`, the one owner of the rule) keeps `False`/`None`
and a `True` under any name outside main's 12 exact names (`verify_cert: true` round-trips). A `True`
under one of the 12 is still a placeholder (#18196, #17337 AC2), so the `True` column is 14 masked and
no cell removes anything.


## Which one do I call?

| I have... | call | not |
|---|---|---|
| a field name AND its value, and want to know if the value is a credential | `secret_redaction.is_credential_entry(name, value, MatchPolicy.X)` | a new noun list; the name-only `is_credential_field` |
| an object whose `__repr__` must not leak config | `secret_redaction.RedactedReprMixin` | hand-written `__repr__` |
| free text that may contain a credential | `secret_redaction.redact_content` | a new regex |
| a nested dict/list that leaves in an API response body (credentials at any depth, URL userinfo) | `secret_redaction.redact_nested` (`BROAD`; masks like `redact_value`, copies, keeps non-credential values and types) | `redact_mapping` (flat, `***`), a per-route key list |
| a bare `user:password@host[:port]` value (no `scheme://`) | applied by `redact_value` and `redact_nested` through `secret_redaction.redact_schemeless_userinfo` (#18206): whole-value only, so emails, `host:port`, `mailto:` and prose are unchanged. Not applied in `redact_text`/`redact_content`: free text has no value boundary, and `note:bob@example.com` would read as userinfo | a per-field regex |
| a raw log line, or an extra-vars mapping | `secret_redaction.redact_text` / `.redact_mapping` | `redact_content` (it does not mask `Authorization:` headers) |
| a provider exception that may name an AWS account | `security/redaction.redact_provider_error` | a new ARN regex |
| text leaving the process to a peer or an LLM, needing a **policy** (block vs redact vs hash) | `a2a.pii_pipeline.scrub_outbound` | `redact_content` -- it has no policy and cannot block |
| a dict or log record in the LLM layer | `llm_shared.credential_redaction.redact_dict` (composes `redact_nested`; adds the `API_KEY_PATTERNS` content scan) | `redact_mapping` |
| a raw chat message | `security.chat_message_safety.scan_chat_message` | any of the above directly |

### Scheme-less userinfo inventory (#18206)

Config fields that can hold a `user:pass@host` value (verified by grep, `file:line`; no value is copied here):

* `autobot_shared/ssot_config.py`: `database_url` (:1627), `redis_url` (:1801), `custom_endpoint` (:334),
  `ollama_gpu_endpoint` (:338), `jaeger_endpoint` (:1695).
* `autobot-slm-backend/config.py`: `database_url` (:206), `slm_users_database_url` (:212),
  `autobot_users_database_url` (:218), `redis_url` (:271, env `SLM_REDIS_URL`).
* `.env.example`: `AUTOBOT_REDIS_URL` (:153), `CELERY_BROKER_URL` (:367, commented out).
* Ansible templates: `{{ db_env_prefix }}_DATABASE_URL` and the per-database `*_DATABASE_URL`
  (`autobot-slm-backend/ansible/roles/postgresql/templates/db-credentials.env.j2:21,23`);
  `AUTOBOT_REDIS_URL` (`autobot-slm-backend/ansible/roles/backend/templates/backend.env.j2:34,37`).
* Proxy settings: none found (`grep -rniE "(https?_proxy|proxy_url)"` over `autobot_shared/`, `config/`,
  `.env.example`, `autobot-slm-backend/config.py` and `autobot-slm-backend/ansible/`).

Every one is documented and templated in `scheme://` form, which `redact_url_userinfo` already handles. No parser
accepts the scheme-less form: SQLAlchemy `make_url` raises `ArgumentError` and `redis.Redis.from_url` raises
`ValueError` on `user:pass@host`. The scheme-less rule is therefore defence in depth for a value pasted into a
free-form field, not a form these settings take.

## Adding a detector

Add it to the module that owns the **shape**, never to the one nearest your
caller:

* a new **credential** noun -> `secret_redaction.CREDENTIAL_SUFFIXES` (reaches
  every policy, `credential_redaction` and every caller above automatically); an
  authorization-style term -> `AUTHORIZATION_TERMS`; a substring-only stem ->
  `BROAD_ONLY_STEMS`
* a new **PII** type -> `pii_pipeline.py`, with its policy-table entry
* a new **cloud identifier** -> `security/redaction.py`

A new matching *rule* is a new `MatchPolicy` member, not a new function. The
census fails on a new detector; `test_credential_matcher_has_exactly_one_home`
fails on a second `is_credential_field` / `redact_mapping`; and
`test_no_new_private_key_name_vocabulary` fails on a new list of credential key
names outside its shrink-only baseline.

### Known remaining vocabularies

The vocabulary guard found 18 further modules that list credential key names
outside the canonical one (HTTP-header deny-lists, env-var allow-lists,
`services/audit_logger.py`, `llc/services/template.py`, `config/async_ops.py`,
...). They are pinned in `_VOCABULARY_BASELINE`, which may only shrink; most are
not redaction, and each needs its own policy decision.

## The duplication guard cannot see any of this

`jscpd -k 70 -l 8` finds **zero** clone lines across these modules: they were
forks, not copies, and a fork shares no 8-line run. `MAX_DUP_LINES` does not
move when this boundary is fixed or broken (`#17312`). The census and the two
guards above are the answer: they count implementations of a concept, not
duplicated text.
