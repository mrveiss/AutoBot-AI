# Device JWT Authentication (GH#9493)

Mobile devices paired via QR code receive a long-lived, device-scoped JWT that
authenticates API requests independently from the desktop session. This
document describes the canonical GH#9493 contract (the earlier MVA-3237
`read-only`/`admin` design was retired; see #11648/#11736 for the cleanup).

## Overview

- **Independent authentication**: devices don't need the desktop to stay connected
- **Scoped access**: `read` / `write` scopes prevent privilege escalation
- **Narrow allow-list**: device JWTs authenticate only on `/api/devices/` endpoints
- **Active revocation**: device existence is checked on every validation

Canonical implementation: `autobot-backend/services/device_jwt.py`
(`mint_device_jwt`, `validate_device_jwt`, `VALID_SCOPES`).

## JWT Structure

```json
{
  "aud": "autobot:device",
  "device_id": "<device_id>",
  "user_id": "<user_id>",
  "scope": "read" | "write",
  "exp": 1234567890
}
```

- **aud**: Audience claim, `autobot:device` by default (`DEVICE_JWT_AUDIENCE`)
- **device_id**: Device UUID from `desktop_mobile_devices.id`
- **user_id**: Owner user ID
- **scope**: One of `services.device_jwt.VALID_SCOPES` — `read` or `write`
- **exp**: Expiry timestamp (default 90 days, `DEVICE_JWT_TTL_DAYS`)

## Scopes

| Scope | HTTP methods allowed |
| --- | --- |
| `read` (default) | GET / HEAD / OPTIONS only |
| `write` | All methods, including POST / PUT / PATCH / DELETE |

Newly paired devices are minted `read` tokens (least privilege). Any other
scope value (including the retired `read-only`/`admin`) is rejected by
`mint_device_jwt` and by the `require_device_jwt` dependency factory.

## Authentication Flow

### 1. Device Pairing

```text
Desktop                                Mobile App
   |                                       |
   | GET /api/devices/pair-qr             |
   |<--------------------------------------|
   | {challenge_token, expires_in}        |
   |                                       |
   | Display QR code                       |
   |                                       |
   |                                  Scan QR
   |                                       |
   | POST /api/devices/pair                |
   |   {challenge_token, device_token...} |
   |<--------------------------------------|
   | {device_id, device_jwt}               |
   |-------------------------------------->|
   |                                       |
   |                              Store device_jwt
```

### 2. API Requests

The mobile app sends the device JWT in the `Authorization` header:

```http
GET /api/devices/me
Authorization: Bearer <device_jwt>
```

`get_current_user` accepts device JWTs as a fallback and enforces:

1. Signature + expiry + `aud` claim via `validate_device_jwt`
2. Device still exists in the database (revocation check, 60 s Redis cache)
3. Path allow-list — device JWTs are valid ONLY under `/api/devices/`
4. Scope — `read` tokens are rejected for mutating HTTP methods

### 3. Device-Only Endpoints — `require_device_jwt`

`require_device_jwt` (in `auth_middleware.py`) is a **dependency factory**
for endpoints that accept ONLY device JWTs — user sessions and every other
token type get 401. It delegates to the same canonical validation seam as
`get_current_user` (`validate_device_jwt`, including the revocation check).

```python
from auth_middleware import require_device_jwt

# read scope suffices
@router.get("/me")
async def get_device_identity(
    device_user: dict = Depends(require_device_jwt()),
):
    ...

# mutating endpoint — write scope required (read tokens get 403)
@router.post("/heartbeat")
async def device_heartbeat(
    device_user: dict = Depends(require_device_jwt("write")),
):
    ...
```

An invalid `min_scope` raises `ValueError` at route-definition time.

Production wiring: `GET /api/devices/me` (`api/mobile_devices.py`) — device
token introspection plus a `last_seen_at` heartbeat so actively-used devices
are not pruned by the 90-day inactivity sweep (#11736).

## API Endpoint Authorization

| Endpoint | Method | Auth |
| --- | --- | --- |
| `/api/devices/pair-qr` | GET | User session (QR generation tied to desktop) |
| `/api/devices/pair` | POST | Challenge token (bound to user at QR time) |
| `/api/devices` | GET | User session (list own devices) |
| `/api/devices/me` | GET | Device JWT ONLY (`require_device_jwt()`) |
| `/api/devices/{id}` | DELETE | User session, or write-scoped device JWT |
| Everything else | ALL | Device JWTs rejected (403 outside `/api/devices/`) |

## Configuration

```bash
DEVICE_JWT_SECRET=<64-char-secret>   # falls back to AUTOBOT_JWT_SECRET
DEVICE_JWT_TTL_DAYS=90               # token lifetime
DEVICE_JWT_CACHE_TTL=60              # device-existence cache TTL (seconds)
DEVICE_JWT_AUDIENCE=autobot:device   # expected aud claim
```

## Security Considerations

### Fail-Closed Authorization Model

1. **Narrow allow-list**: device JWTs authenticate only under `/api/devices/`
2. **Method gating**: `read` tokens cannot use mutating HTTP methods
3. **Revocation check**: every validation confirms the device row still exists
4. **Single validation seam**: `get_current_user` and `require_device_jwt`
   both delegate to `services.device_jwt.validate_device_jwt`

### Token Revocation

Deleting a device via `DELETE /api/devices/{id}`:

- Removes the row from `desktop_mobile_devices`
- Invalidates the Redis existence cache (`invalidate_device_cache`), so
  revocation takes effect immediately rather than after the cache TTL
- All subsequent requests with that device's JWT fail validation

### Expiry

Tokens expire after `DEVICE_JWT_TTL_DAYS` (default 90). Separately, devices
inactive for 90+ days are pruned by the device-list sweep; `GET
/api/devices/me` refreshes `last_seen_at` so active devices survive it.

Mobile apps should store the expiry timestamp, prompt re-pairing near expiry,
and handle 401 responses gracefully.

## Testing

- `autobot-backend/tests/integration/test_device_jwt_auth.py` — mint/validate,
  middleware fallback chain, allow-list + scope enforcement,
  `require_device_jwt` dependency (401/403/200)
- `autobot-backend/tests/integration/test_mobile_device_me.py` —
  `GET /api/devices/me` wiring and heartbeat

```bash
pytest autobot-backend/tests/integration/test_device_jwt_auth.py \
       autobot-backend/tests/integration/test_mobile_device_me.py -v
```

## Related Issues

- GH#9493 — canonical device-JWT implementation (scopes, allow-list, revocation)
- GH#4463 — mobile device pairing (QR challenge flow)
- GH#11648 — test-side rewrite to the canonical contract
- GH#11736 — `require_device_jwt` rot fix + production wiring
