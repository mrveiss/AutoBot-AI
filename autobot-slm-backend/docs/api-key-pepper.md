# API-key pepper (#16299, #19120)

SLM API keys are stored as `PBKDF2-HMAC-SHA256(key, salt=pepper)` (#20611; 20000 rounds, a constant in `api_key_service.py`). The pepper is a rotatable
credential, so it lives in the SLM secrets store (`SystemSecret`), not in an env file.

## Setting it

An administrator adds the secret `slm_hmac_api_key_secret` on the SLM page
`/slm/settings/admin/secrets`. The page lists it as "not set" until it exists. Nothing
generates the value for you; pick a long random string and keep it in your own vault.

## Resolution order (`services/api_key_pepper.py`)

1. The secrets store value, if present.
2. Otherwise `SLM_HMAC_API_KEY_SECRET` from the environment, if set: imported into the
   store once (logged as an import, value never logged), then used. Installs that already
   have the variable are migrated by this step; the variable can be removed afterwards.
3. Otherwise unset: creating an API key fails closed and a WARNING names the secret and
   the page. Existing keys keep verifying through the legacy path and are re-hashed with
   the pepper on next use once it is set.

## Rotation (limitation)

The store holds one value and no previous one, so there is no dual-verify window.
Changing `slm_hmac_api_key_secret` makes every key hashed under the old value stop
verifying (the key owner must be issued a new key). Rotate only when that is acceptable.

## Old key formats (#20611)

Only the PBKDF2 digest is accepted. A key stored in any older format (HMAC-SHA256 under the
current or legacy pepper, or bare SHA-256) no longer verifies and must be reissued. Its stored
row is left as it is: removing stored keys is an approval-queue proposal, never automatic.
