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
| `autobot_shared/secret_redaction.py` | `CREDENTIAL_SUFFIXES` + `AUTHORIZATION_TERMS` + `BROAD_ONLY_STEMS` | `MatchPolicy.PRECISE` / `BROAD` | field names, mappings, log lines, free-text credentials | in |
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

Both policies first exempt a **count or limit of a credential noun**
(`secret_redaction.is_quantity_field`): `max_`/`min_`/`num_`/`total_`/`input_`/
`output_`/`prompt_`/`completion_`/`cached_` + a *plural* noun (`max_tokens`,
`num_api_keys`), or a name ending `_count`/`_limit`/`_len`/`_length`/`_size` whose
stem ends in a noun (`token_count`, `key_length`). Without it `max_tokens=4096`
became `{{MAX_TOKENS}}` in exported templates. The exemption is **value-aware**: `is_credential_entry(name, value, policy)` keeps a
quantity name unmasked only when its value is a number (not bool) or a pure-digit
string; a JWT, `sk-...`, list or dict under `token_count` stays masked, by both
policies. `is_credential_field(name)` is the name-only classification, for callers
with no value. Every value-bearing caller uses `is_credential_entry`. The mask-set
delta is reproducible from the repo: `autobot_shared/redaction_corpus_17336.txt`
plus `secret_redaction_policy_17336_test.py`. The rule is deliberately tight:
`max_token_secret`, `max_password` and `token_count_secret` stay masked.

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
| `redact_text` (slm `monitoring`, bedrock errors) | text regex | same regex, moved into `secret_redaction` |
| `credential_redaction.redact_dict` | normalized substring | `BROAD` |
| `cot_events._is_sensitive` | own 13-fragment substring | `BROAD` |
| `portability._scrub_adapter_config` | own 12-name exact match | `PRECISE` |
| `config_revision_service._is_secret_key` | own 5-fragment substring | `BROAD` |

Every migration only **widened** the masked set; the before/after comparison
over a corpus of ~1,950 field names (both modules' literals, every string passed
to a redactor in tests, the 10-name sample from `#17336`) found 0 removals.

## Which one do I call?

| I have... | call | not |
|---|---|---|
| a field name, and want to know if its value is a credential | `secret_redaction.is_credential_field(name, MatchPolicy.X)` | a new noun list |
| an object whose `__repr__` must not leak config | `secret_redaction.RedactedReprMixin` | hand-written `__repr__` |
| free text that may contain a credential | `secret_redaction.redact_content` | a new regex |
| a raw log line, or an extra-vars mapping | `secret_redaction.redact_text` / `.redact_mapping` | `redact_content` (it does not mask `Authorization:` headers) |
| a provider exception that may name an AWS account | `security/redaction.redact_provider_error` | a new ARN regex |
| text leaving the process to a peer or an LLM, needing a **policy** (block vs redact vs hash) | `a2a.pii_pipeline.scrub_outbound` | `redact_content` -- it has no policy and cannot block |
| a dict or log record in the LLM layer | `llm_shared.credential_redaction.redact_dict` | `redact_mapping` |
| a raw chat message | `security.chat_message_safety.scan_chat_message` | any of the above directly |

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
