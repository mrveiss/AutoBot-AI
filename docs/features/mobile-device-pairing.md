# Mobile Device Pairing Feature (GH#4463)

## Overview

Full-stack implementation of mobile device pairing for push notifications and offline conversation sync.

## Architecture

### Backend (Complete)

**Database:**
- Table: `desktop_mobile_devices`
- Migration: `20260529_047_desktop_mobile_devices.py`
- Model: `models/mobile_device.py` with AES-256-GCM encryption

**API Endpoints** (`/api/devices`):
- `GET /pair-qr` — Generate QR challenge token (5-minute TTL)
- `POST /pair` — Complete pairing via QR token
- `GET /` — List active paired devices (auto-prunes 90+ day inactive)
- `DELETE /{device_id}` — Unpair device

**Push Integration:**
- Service: `services/push_notification_service.py`
- Sends to both web push subscriptions and mobile devices
- Platform support: iOS (APNs stub), Android (FCM stub), PWA (web push)
- Celery hook for task completion notifications

**Router Registration:**
- Path: `/api/devices`
- Tags: `mobile-devices`, `push-notifications`
- Registered in: `initialization/router_registry/feature_routers.py`

### Frontend (Complete)

**Composable:**
- File: `src/composables/mobile-devices/useMobileDevices.ts`
- Methods: `generateQRCode()`, `fetchDevices()`, `deleteDevice()`
- Reactive state: devices list, current QR challenge, loading, error

**UI Component:**
- File: `src/components/settings/MobileDevicePairingPanel.vue`
- QR code generation with `qrcode` library (v1.5.4)
- Real-time expiry countdown (5 minutes)
- Device list with platform icons (iOS/Android/PWA)
- Delete confirmation dialog

**Settings Integration:**
- New tab: "Mobile Devices" in `SettingsView.vue`
- Icon: `mobile-alt`
- Type: Added to `PreferenceTab` union

## QR Code Payload

```json
{
  "type": "autobot_device_pair",
  "challenge_token": "<token>",
  "api_base": "https://autobot.example.com"
}
```

The mobile app scans this, extracts the token, and calls `POST /api/devices/pair` with:
- `challenge_token` (from QR)
- `device_name` (e.g., "iPhone 14 Pro")
- `device_token` (APNs/FCM push token)
- `platform` (ios/android/pwa)

## Security

1. **Token encryption:** Device tokens encrypted at rest with AES-256-GCM
2. **Challenge TTL:** QR codes expire after 5 minutes (Redis-backed)
3. **One-time use:** Challenge tokens deleted after successful pairing
4. **Device expiry:** Inactive devices (90+ days) auto-pruned on list fetch
5. **Auth required:** All endpoints except `POST /pair` require user auth

## Testing Checklist

- [x] Backend API endpoints load without import errors
- [x] Frontend type-check passes
- [x] Router registered in feature_routers.py
- [x] Migration file exists
- [x] Composable created with type safety
- [x] Panel component integrated into SettingsView
- [ ] Manual test: Generate QR code in UI
- [ ] Manual test: Device list displays correctly
- [ ] Manual test: Delete device works
- [ ] Manual test: QR expiry countdown works
- [ ] E2E test: Full pairing flow with mobile app (requires mobile app implementation)

## Dependencies Added

- `qrcode@1.5.4` — QR code canvas rendering
- `@types/qrcode@1.5.6` — TypeScript definitions

## Future Work (Not in Scope)

1. **APNs integration** — Replace stub in `_send_mobile_push` with `apns2` library
2. **FCM integration** — Replace stub with `firebase-admin` library
3. **Mobile app** — iOS/Android/PWA apps to scan QR and handle push
4. **Conversation sync** — Backend logic to sync session state across devices
5. **Offline queue** — Store messages when device is offline, sync when back online

## Verification Commands

```bash
# Backend router verification (requires running backend)
curl -H "Authorization: Bearer <token>" http://localhost:8001/api/devices

# Frontend build check
cd autobot-frontend && npm run build

# Type check
cd autobot-frontend && npm run type-check
```

## Related Issues

- GH#4463 — Mobile device pairing (this feature)
- GH#4459 — Web push notifications (integrated)
- MVA-2712 — Paperclip task for implementation
