# Redaction boundary — which redactor for which shape of problem

Trigger: adding a redactor, adding a detector to one, or picking which module to
call when something sensitive must not reach a log, an LLM, or a peer.

`#16688` asked which of the parallel redaction implementations is canonical. The
answer is that **there is no single one, and there should not be** — but the
boundary was implicit, so callers picked by whichever module they happened to
know about. This file makes it explicit. The rule is one line:

> **One module owns each *shape* of the problem. No module owns "redaction".**

## The census — eight modules, seven of them deciding

Measured on `origin/main` at 31310392df by
`repo_tests/redaction_concept_census_test.py`, run over every tracked
production source. **The number is seven, not four.** `#16688` names four and
`#17312` measures the same four; the guard found three more that no issue had
counted, plus one more that also declares itself canonical.

A module is *in the census* when it both exposes a `redact`/`scrub`/`mask`
entry point **and** declares a detector of its own — a compiled pattern naming
a secret, a vocabulary of secret nouns, or an enum of secret/PII types.
Calling someone else's redactor does not count, and that distinction is the
whole point: it is what separates the eighth module below from the other seven.

| module | own vocabulary | size | match | shape it owns |
|---|---|---:|---|---|
| `autobot_shared/secret_redaction.py` | `CREDENTIAL_SUFFIXES` | 19 | **suffix** | field names + free-text credentials |
| `autobot_shared/security/redaction.py` | `_SECRET_KEY_FRAGMENTS` | 8 | substring | log lines, mappings, cloud ARNs |
| `autobot-backend/a2a/pii_pipeline.py` | `PIIType` + regex detectors | 14 types | regex | PII types and BLOCK/REDACT/HASH policy |
| `autobot-backend/llm_shared/credential_redaction.py` | `API_KEY_PATTERNS` | 4 patterns | regex | dict / log-record redaction (LLM layer) |
| `autobot-backend/chat_workflow/cot_events.py` | `_SENSITIVE_KEY_FRAGMENTS` | 13 | substring | chain-of-thought event args |
| `autobot-backend/llc/services/portability.py`&nbsp;† | `_SECRET_LIKE_KEYS` | 13 | substring | company-template export |
| `autobot-backend/services/config_revision_service.py` | `_SECRET_SUBSTRINGS` | 5 | substring | config revision snapshots |
| `autobot-backend/security/chat_message_safety.py` | **none — composes** | — | — | the chat entry point |

† The only module carrying no pointer back to this file: it sits on its
grandfathered 936-line size ceiling (#5060), and a docstring note would push it
over. The census guard names it instead.

Six independent answers to one question — *"is this key name sensitive?"* —
with word lists of 19, 13, 13, 8, 5 and (until `#16688`) 8. Which module a
caller imported decides whether `client_secret` or `bearer_token` reaches a
log.

`chat_message_safety.py` is the shape to copy: 114 lines of real redaction
policy on the chat path that declares no detector at all and composes
`pii_pipeline.scrub_outbound` with the shared injection detector.

### What this PR changed, and what it did not

Changed: `credential_redaction.SENSITIVE_KEYS` now derives from
`secret_redaction.CREDENTIAL_SUFFIXES` (a union — dropping to it alone would
have stopped redacting `Authorization`, `auth_header` and `x_auth`), and
`secret_redaction`'s JWT pattern was widened to match `pii_pipeline`'s, which
had been catching tokens it missed.

Not changed: the last three modules in the table. They are pinned by the census
so the count cannot grow, and collapsing them onto this boundary is tracked as
its own issue — three call sites in three unrelated subsystems is a different
review problem from the redaction boundary itself.

## Which one do I call?

| I have… | call | not |
|---|---|---|
| a field name, and want to know if its value is a credential | `secret_redaction.is_credential_field` | a new suffix list |
| an object whose `__repr__` must not leak config | `secret_redaction.RedactedReprMixin` | hand-written `__repr__` |
| free text that may contain a credential | `secret_redaction.redact_content` | a new regex |
| a raw log line, or an extra-vars mapping | `security/redaction.redact_text` / `.redact_mapping` | `redact_content` (it does not mask `Authorization:` headers) |
| a provider exception that may name an AWS account | `security/redaction.redact_provider_error` | a new ARN regex |
| text leaving the process to a peer or an LLM, needing a **policy** (block vs redact vs hash) | `a2a.pii_pipeline.scrub_outbound` | `redact_content` — it has no policy and cannot block |
| a dict or log record in the LLM layer | `llm_shared.credential_redaction.redact_dict` | `redact_mapping` (different normalization) |
| a raw chat message | `security.chat_message_safety.scan_chat_message` | any of the above directly |

## Why two modules in `autobot_shared/` is not (yet) settled

`secret_redaction.py` and `security/redaction.py` both answer "is this name a
credential", and they made **opposite deliberate decisions**, each recorded in
its own file:

* `secret_redaction.is_credential_field` matches by **suffix**, so that
  `tokenizers_parallelism` and `tls_key_path` stay visible — it feeds SSOT
  config's `__repr__`, where over-masking destroys the diagnostic.
* `security/redaction.redact_mapping` matches by **substring**, so that a
  secret under an unanticipated key name is still masked — it feeds log lines
  and ansible extra-vars, where over-masking is free.

On a 10-name sample they disagree on 7: `tokenizers_parallelism`,
`monkey_patch`, `tls_key_path`, `password_hash_algorithm`, `private_ip`,
`passenger_count`, `certainty_score` — all masked by the substring rule, none
by the suffix rule.

Neither is wrong. They encode **different false-positive tolerances justified by
different call sites**, which is the definition of a real boundary rather than a
fork. Merging them would reverse one recorded ruling and silently change
behaviour at the other's call sites, so this PR documents the split instead.
Whether they should converge is tracked separately — see the issue linked from
the census guard.

## Adding a detector

Add it to the module that owns the **shape**, never to the one nearest your
caller:

* a new **credential** pattern or noun → `secret_redaction.py` (reaches
  `credential_redaction` and every `redact_content` caller automatically)
* a new **PII** type → `pii_pipeline.py`, with its policy-table entry
* a new **cloud identifier** → `security/redaction.py`

A detector added anywhere else is an eighth implementation, and
`repo_tests/redaction_concept_census_test.py` fails on it.

## The duplication guard cannot see any of this

`jscpd -k 70 -l 8` over the four modules `#17312` measured finds **zero**
clone lines, and the three this guard added share no text either: they are
forks, not copies, and a fork shares no 8-line run. `MAX_DUP_LINES` therefore
does not move when this boundary is fixed or broken. That is the blind spot
`#17312` describes, and the census guard is the answer to it here — the count of
implementations is pinned even though their text is not similar.
