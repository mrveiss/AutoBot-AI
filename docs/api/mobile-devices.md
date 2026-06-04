# Mobile Devices API

> Related: GH [#4463](https://github.com/mrveiss/AutoBot-AI/issues/4463) — Mobile Device Pairing for Push and Offline Sync

The Mobile Devices API lets users pair mobile devices with their AutoBot account. Paired devices receive push notifications and can sync conversation state across desktop and mobile.

**Base path:** `/api/devices`

**Authentication:** All endpoints require a valid session token in the `Authorization: Bearer <token>` header, except `POST /pair` which uses the QR challenge token for authentication.

---

## Endpoints

### GET /api/devices/pair-qr

Generate a time-limited QR challenge token. The desktop displays this as a QR code; the mobile app scans it to initiate pairing.

**Authentication:** Session token required.

**Response `200 OK`:**

```json
{
  "challenge_token": "abc123...xyz789",
  "expires_in_seconds": 300
}
```

| Field | Type | Description |
|---|---|---|
| `challenge_token` | string | Short-lived token to embed in the QR code. One-time use, 5-minute TTL. |
| `expires_in_seconds` | integer | Always `300`. |

**Example:**

```bash
curl -X GET https://your-autobot.example.com/api/devices/pair-qr \
  -H "Authorization: Bearer $SESSION_TOKEN"
```

**Error responses:**

| Status | Detail | Cause |
|---|---|---|
| `401 Unauthorized` | `User identity missing` | Session token missing or user not resolved |
| `503 Service Unavailable` | `Pairing service temporarily unavailable` | Redis unavailable |

---

### POST /api/devices/pair

Complete device pairing using the challenge token from the QR code. Called by the mobile app after scanning the QR code.

**Authentication:** No session token required — the challenge token authenticates the request and binds the device to the correct user.

**Request body:**

```json
{
  "challenge_token": "abc123...xyz789",
  "device_name": "iPhone 15 Pro",
  "device_token": "<APNs / FCM / web-push token>",
  "platform": "ios"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `challenge_token` | string | Yes | Token obtained from QR code scan |
| `device_name` | string | Yes | Human-readable name for the device (1–255 characters) |
| `device_token` | string | Yes | Platform push token: APNs (iOS), FCM (Android), or Web Push subscription (PWA) (1–512 characters) |
| `platform` | string | Yes | One of: `ios`, `android`, `pwa` |

**Response `201 Created`:**

```json
{
  "device_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Device paired successfully"
}
```

**Example (iOS):**

```bash
curl -X POST https://your-autobot.example.com/api/devices/pair \
  -H "Content-Type: application/json" \
  -d '{
    "challenge_token": "abc123...xyz789",
    "device_name": "iPhone 15 Pro",
    "device_token": "<APNs device token>",
    "platform": "ios"
  }'
```

**Example (Android):**

```bash
curl -X POST https://your-autobot.example.com/api/devices/pair \
  -H "Content-Type: application/json" \
  -d '{
    "challenge_token": "abc123...xyz789",
    "device_name": "Pixel 8",
    "device_token": "<FCM registration token>",
    "platform": "android"
  }'
```

**Example (PWA):**

```bash
curl -X POST https://your-autobot.example.com/api/devices/pair \
  -H "Content-Type: application/json" \
  -d '{
    "challenge_token": "abc123...xyz789",
    "device_name": "Chrome on Laptop",
    "device_token": "{\"endpoint\":\"https://...\",\"keys\":{\"p256dh\":\"...\",\"auth\":\"...\"}}",
    "platform": "pwa"
  }'
```

**Error responses:**

| Status | Detail | Cause |
|---|---|---|
| `400 Bad Request` | `Challenge token expired or invalid` | Token not found in Redis — expired (>5 min) or already used |
| `503 Service Unavailable` | `Pairing service temporarily unavailable` | Redis unavailable |

---

### GET /api/devices

List all active paired devices for the current user.

**Authentication:** Session token required.

**Note:** This endpoint automatically prunes devices inactive for more than 90 days. There is no separate cleanup call needed.

**Response `200 OK`:**

```json
{
  "devices": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "device_name": "iPhone 15 Pro",
      "platform": "ios",
      "last_seen_at": "2026-06-01T14:32:00+00:00",
      "created_at": "2026-01-15T10:00:00+00:00"
    },
    {
      "id": "660e8400-e29b-41d4-a716-446655441111",
      "device_name": "Pixel 8",
      "platform": "android",
      "last_seen_at": "2026-05-28T09:15:00+00:00",
      "created_at": "2026-02-20T08:30:00+00:00"
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `id` | UUID | Device identifier — use this when unpairing |
| `device_name` | string | Human-readable name set during pairing |
| `platform` | string | `ios`, `android`, or `pwa` |
| `last_seen_at` | ISO 8601 string or `null` | Last time the device was active; `null` if never seen after pairing |
| `created_at` | ISO 8601 string | When the device was paired |

**Example:**

```bash
curl -X GET https://your-autobot.example.com/api/devices \
  -H "Authorization: Bearer $SESSION_TOKEN"
```

---

### DELETE /api/devices/{device_id}

Unpair and remove a mobile device. Users can only delete their own devices.

**Authentication:** Session token required.

**Path parameter:**

| Parameter | Type | Description |
|---|---|---|
| `device_id` | UUID | The device's `id` from `GET /api/devices` |

**Response:** `204 No Content`

**Example:**

```bash
curl -X DELETE \
  https://your-autobot.example.com/api/devices/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer $SESSION_TOKEN"
```

**Error responses:**

| Status | Detail | Cause |
|---|---|---|
| `404 Not Found` | `Device not found` | Device does not exist or belongs to a different user |

---

## Pairing Flow

The full QR pairing sequence requires two separate actors — the desktop (authenticated session) and the mobile app (no session, uses challenge token):

```
Desktop                           Backend                      Mobile App
  │                                  │                              │
  │── GET /api/devices/pair-qr ─────►│                              │
  │◄─ { challenge_token, 300s } ─────│                              │
  │                                  │                              │
  │  [Display QR code]               │                              │
  │                                  │◄──── [QR scan] ─────────────│
  │                                  │                              │
  │                                  │◄── POST /api/devices/pair ───│
  │                                  │    { challenge_token,        │
  │                                  │      device_name,            │
  │                                  │      device_token,           │
  │                                  │      platform }              │
  │                                  │                              │
  │                                  │── validate token in Redis ──►│
  │                                  │── delete token (one-time) ──►│
  │                                  │── store encrypted device ───►│
  │                                  │                              │
  │                                  │──── { device_id, msg } ─────►│
  │                                  │                              │
```

**Key security properties:**
- The QR code never contains user credentials — only a short-lived challenge token.
- The token is bound to the user's `user_id` server-side (in Redis), not encoded in the QR.
- Tokens expire after 5 minutes and are deleted on first use — replay is impossible.
- Device push tokens are encrypted at rest using AES-256-GCM.

---

## Data Model

The `desktop_mobile_devices` table stores paired devices:

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | Auto-generated |
| `user_id` | String(64) | Indexed; ties device to a user |
| `device_name` | String(255) | Human-readable label |
| `device_token` | Text | AES-256-GCM encrypted push token |
| `platform` | String(16) | `ios` / `android` / `pwa` |
| `last_seen_at` | DateTime (UTC) | Updated when a notification is sent |
| `created_at` | DateTime (UTC) | Set at pairing time |

### Platform token formats

| Platform | Token type | Format |
|---|---|---|
| `ios` | APNs device token | Hex string |
| `android` | FCM registration token | Base64 string |
| `pwa` | Web Push subscription | JSON string: `{"endpoint": "...", "keys": {"p256dh": "...", "auth": "..."}}` |

---

## Device Lifecycle

- **Paired** — device added via `POST /pair`; push notifications enabled.
- **Active** — device has `last_seen_at` within the last 90 days.
- **Pruned** — `GET /devices` automatically deletes devices inactive for more than 90 days. A background Celery task (`cleanup_stale_mobile_devices`) also prunes stale devices from inactive users' accounts.

---

## Source Files

| File | Description |
|---|---|
| `autobot-backend/api/mobile_devices.py` | API router and endpoint handlers |
| `autobot-backend/models/mobile_device.py` | SQLAlchemy model and token encryption |
| `autobot-backend/tasks/mobile_device_tasks.py` | Celery cleanup task |

> **Note:** As of GH [#4463](https://github.com/mrveiss/AutoBot-AI/issues/4463), the router is implemented but not yet registered in `main.py` or `feature_routers.py`. The Alembic migration for `desktop_mobile_devices` is also pending. See the architecture document for full implementation status.
