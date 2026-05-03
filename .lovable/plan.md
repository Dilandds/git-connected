## Goal
Redesign the License Activation dialog to be minimal and Lemon Squeezy–native: **a single license key field**. Drop the work email field, drop the "Manage Seats" button, and clean up the layout to feel like a focused first-run activation screen.

Seat allocation / per-user identity is deferred — the machine fingerprint (already in `core/machine_id.py`) handles seat enforcement on its own via Lemon Squeezy's `activation_limit`.

## New Layout

```text
┌──────────────────────────────────────────┐
│           [ ECTOFORM icon ]              │
│                                          │
│           Activate ECTOFORM              │
│   Enter your license key to get started  │
│                                          │
│   ┌────────────────────────────────────┐ │
│   │ XXXX-XXXX-XXXX-XXXX                │ │
│   └────────────────────────────────────┘ │
│                                          │
│   [    Activate this device         ]    │
│                                          │
│   ─── status / error message here ───    │
│                                          │
│   Don't have a key?  Buy a subscription  │
│   Need help?         Contact support     │
│                                          │
│                              Cancel      │
└──────────────────────────────────────────┘
```

## Concrete changes — `ui/license_dialog.py`

1. **Window**
   - Title: `Activate ECTOFORM`.
   - Size: ~460×420, fixed-feel (not the current 560×360 minimum).

2. **Header**
   - App icon centered (~56px) using `get_app_window_icon()`.
   - H1 "Activate ECTOFORM" (16pt bold).
   - One-line subtitle: "Enter your license key to activate this device."
   - Drop the "company seat is tied to a user identity" line.

3. **Single input**
   - Remove `QFormLayout`, remove `self.user_input` entirely.
   - Keep only `self.key_input`, label above it: "License key".
   - Placeholder `XXXX-XXXX-XXXX-XXXX`, monospace font, auto-uppercase on input.
   - Full width, 44px height.

4. **Primary action**
   - One full-width button: **"Activate this device"**.
   - While validating, button text becomes "Activating…" and is disabled (replaces the separate `QProgressBar`).
   - Remove `QProgressBar` entirely.

5. **Inline status**
   - Single status label under the button. Red on error, green on success, secondary color while idle/empty.
   - Replace the modal `QMessageBox.information` success popup with: show success inline for ~800ms, then `accept()`. Less interruptive.
   - Keep `QMessageBox.warning` for hard failures (clearer than inline only).

6. **Footer links**
   - Replace the row of three big primary buttons with two small flat text buttons:
     - "Don't have a key? **Buy a subscription**" → `get_buy_url()`
     - "Need help? **Contact support**" → `get_support_url()`
   - **Remove "Manage Seats" entirely** (admin-only action, doesn't belong in end-user activation).
   - Style: `flat=True`, transparent background, primary-color text.

7. **Cancel**
   - Move Cancel to a small, low-emphasis text-style button bottom-right (not a primary blue button next to Activate).

8. **Validation logic (`validate_license` / `on_validation_complete`)**
   - Drop the `user_identifier` requirement check.
   - Pass empty string `""` (or hostname) to `LicenseValidationThread` for `user_identifier` so backend signature doesn't change. `core/license_validator.activate_subscription` already accepts an empty user but currently rejects it — see "Backend tweak" below.

## Backend tweak — `core/license_validator.py`

`activate_subscription()` currently does:
```python
if not user_identifier:
    return False, None, "Work email or user ID is required"
```
Change this to fall back to the machine fingerprint as the identifier when none is provided:
```python
if not user_identifier:
    user_identifier = machine_fingerprint
```
This keeps the existing API/payload shape (`user_identifier` still sent to the server) and unblocks the single-field UI without seat tracking changes.

No changes needed to the legacy Gist path — it already works without an email.

## Files to edit
- `ui/license_dialog.py` — rewrite `init_ui`, simplify `validate_license` and `on_validation_complete`, drop `user_input` / `manage_button` / `progress_bar`.
- `core/license_validator.py` — relax the empty-`user_identifier` guard in `activate_subscription`.

## Out of scope (deferred)
- Seat allocation UI / admin "Manage Seats" entry (will live in a future Settings/Account menu, not first-run dialog).
- Per-user email identity (revisit when introducing real login).
