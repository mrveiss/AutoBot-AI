# Mobile Device Pairing

Pair your phone or tablet with AutoBot so you can:

- **Receive push notifications** when a long-running agent workflow completes.
- **Continue conversations on mobile** — start on desktop, pick up on your phone.

---

## Supported Platforms

| Platform | Requirement |
|---|---|
| **iOS** | AutoBot mobile app installed (iPhone or iPad) |
| **Android** | AutoBot mobile app installed |
| **PWA** | AutoBot opened in a browser with web notifications enabled (Chrome, Edge, Firefox) |

---

## Setup: Pair Your Device

Pairing takes under a minute and uses a QR code so your credentials never leave your desktop.

### Step 1 — Open device settings on desktop

1. Log in to AutoBot in your desktop browser.
2. Click the **gear icon** (⚙) in the top-right corner to open Settings.
3. Navigate to **Account → Connected Devices**.
4. Click **Pair New Device**.

A QR code appears on screen. It is valid for **5 minutes**.

### Step 2 — Scan the QR code on your mobile device

**iOS / Android app:**

1. Open the AutoBot app on your phone.
2. Tap **Pair with Desktop** in the app's menu.
3. Point your camera at the QR code on the desktop screen.
4. When the code is recognised, tap **Pair** to confirm.

**PWA (browser):**

1. Open AutoBot in your mobile browser.
2. Tap the menu icon → **Pair with Desktop**.
3. Use your phone's camera or the in-browser QR scanner to scan the code.
4. When prompted, allow browser notifications, then tap **Pair**.

### Step 3 — Confirm pairing

After a successful scan, you will see:

- **Desktop:** the device appears in the Connected Devices list with the device name and platform.
- **Mobile:** a confirmation screen shows "Device paired successfully."

The device is now paired. AutoBot will send push notifications to it and can sync conversation state to it.

> **Tip:** Give your device a clear name during pairing (e.g. "iPhone 15 Pro" or "Work Pixel") so you can tell them apart in the device list.

---

## Manage Paired Devices

### View your devices

1. Go to **Settings → Account → Connected Devices**.
2. You will see a list of all active paired devices, each showing:
   - Device name
   - Platform (iOS / Android / PWA)
   - Last active date

Devices inactive for more than 90 days are automatically removed.

### Remove a device

1. In **Connected Devices**, find the device you want to remove.
2. Click the **Remove** (🗑) button next to it.
3. Confirm when prompted.

After removal, AutoBot stops sending push notifications to that device. Any already-delivered notifications remain on the device.

---

## Troubleshooting

### QR code expired

The QR code is valid for 5 minutes. If you see "QR code expired":

1. Click **Regenerate QR Code** on the desktop settings page.
2. A fresh code appears — scan it promptly.

### "Challenge token expired or invalid"

This means the QR code was already used or timed out before the mobile app completed pairing. Generate a new QR code and try again.

### Device does not appear after scanning

- Make sure the AutoBot app is up to date.
- Check that your mobile device has an active internet connection.
- Verify the desktop session is still logged in (the QR code requires an active session).
- If the QR page shows an error, try refreshing and generating a new code.

### Notifications not arriving

- **iOS:** Go to iOS Settings → Notifications → AutoBot and confirm notifications are allowed.
- **Android:** Go to Android Settings → Apps → AutoBot → Notifications and enable them.
- **PWA:** In your browser settings, find Site Settings for your AutoBot URL and ensure notifications are set to **Allow**.
- Confirm the device appears in Connected Devices on desktop (it may have been pruned if inactive >90 days).

### Pairing service unavailable

If you see "Pairing service temporarily unavailable", AutoBot's backend is experiencing a temporary issue. Wait a few minutes and try again. If the problem persists, contact your AutoBot administrator.

### QR scan does not work with PWA

Some mobile browsers restrict camera access. Try:

1. Ensuring the AutoBot PWA is served over HTTPS.
2. Granting camera permissions to the browser when prompted.
3. Using the device's built-in camera app to scan the QR code instead — copy the embedded token and paste it in the pairing screen if supported.

---

## Security Notes

- The QR code does not contain your password or session token — only a short-lived, one-time challenge token.
- The challenge token expires after 5 minutes and cannot be reused.
- Your push notification token is encrypted at rest on the AutoBot server (AES-256-GCM).
- Only you can see and remove your own paired devices.
- Removing a device immediately stops new push notifications to it.

---

## Frequently Asked Questions

**How many devices can I pair?**
There is no hard limit. You can pair multiple phones, tablets, and PWAs simultaneously.

**Can I rename a device after pairing?**
Not currently. Remove the device and re-pair with a new name.

**What happens if I reinstall the app?**
Reinstalling resets the push token. Re-pair the device to restore notifications.

**Can two users share a device?**
No. Each device is paired to one AutoBot user account. If a second user wants notifications on the same phone, they must log in with their own account and pair separately.

**Will pairing drain my battery?**
Push notifications use platform-native delivery (APNs / FCM / Web Push), which is designed to be battery-efficient. AutoBot does not maintain a persistent background connection.
