# Compliance Audit — Open Topics

Audit date: 3 March 2026
Compared against: `vdc-API/` (§1–§7) and `vdc-API-properties/` (§2–§16)
All 1168 tests passing at time of audit.

---

## Errors (semantic mismatches with spec)

### E2 — Proto: `setOutputChannelValue` missing fields

§7.3.9 defines `automatic` (bool), `group` (int), `zone_id` (int) on
`vdsm_NotificationSetOutputChannelValue`. Both the code proto and the
documentation proto are missing all three. These fields cannot be received
from the vdSM until added to `.proto` and the `_pb2.py` is regenerated.

**Action:** Add the three fields to `genericVDC.proto`, regenerate, and
handle them in `_handle_set_output_channel_value()`.

### E3 — Missing handler: `remove` (§6.3)

`VDSM_SEND_REMOVE` (type 13) has no handler in `_dispatch_message()`.
The vdSM cannot request device removal; no `GENERIC_RESPONSE` is sent.
Should respond with `ERR_OK` or `ERR_FORBIDDEN`.

**Action:** Implement `_handle_remove()` in `vdc_host.py`.

---

## Warnings (missing optional features / undocumented extensions)

### W1 — Missing handler: `dimChannel` (§7.3.5)

`VDSM_NOTIFICATION_DIM_CHANNEL` (type 24) falls through to the user
callback. Core dimming operation has no built-in dispatch.

**Action:** Consider adding a built-in handler that forwards to the
device, similar to `callScene` / `setOutputChannelValue`.

### W2 — Missing handler: `identify` (§7.3.7)

`VDSM_NOTIFICATION_IDENTIFY` (type 20) falls through to the user callback.

**Action:** Consider adding a built-in handler with a user-overridable
callback on the device.

### W3 — Missing optional vdSD properties

§4.1.1 optional properties are completely absent:

- `progMode` — r/w boolean for local programming mode
- `currentConfigId` — r/o string for currently active configuration/profile ID
- `configurations` — r/o list of supported configuration/profile IDs

**Action:** Add these as optional fields on `Vdsd` if target hardware
requires them.

### W4 — `ButtonClickType.LOCAL_DIM = 15` undocumented

Present in code but not in spec §4.2.3 (spec enumerates 0–14 then jumps
to 255). Value 15 is not documented.

**Action:** Decide whether to keep as forward-compatible extension or
remove for strict compliance.

### W5 — `ButtonMode.TURBO = 1` undocumented

Present in code but not in spec §4.2.2 (spec lists only 0, 2, 5–12).
Value 1 is not documented.

**Action:** Decide whether to keep as forward-compatible extension or
remove for strict compliance.

### W6 — Scene handlers missing `group` / `zoneID`

`callScene`, `saveScene`, `undoScene`, `setLocalPriority`, `callSceneMin`
do not extract `group` or `zoneID` from the protobuf message. These are
informational per spec but available in the wire data.

**Action:** Extract and pass through to device callbacks.

### W7 — Unhandled GenericRequest error code

Unknown GenericRequest methods return `ERR_NOT_FOUND`. Arguably should
return `ERR_NOT_IMPLEMENTED` per §1.2.

**Action:** Change to `ERR_NOT_IMPLEMENTED`.

---

## Info (minor or by-design differences)

### I1 — `BinaryInputType.BRIGHTNESS` naming

Spec says "Light" (id=2). Code uses `BRIGHTNESS`. Value is correct;
name differs slightly.

### I2 — `controlValues` emitted in vdSD properties

Not a spec-listed vdSD property. Implementation extension for runtime
control values.

### I3 — `DeviceProperty.description` extra field

Extra `description` field in description output. Additive, not harmful.

### I4 — BinaryInput extra settings

`minPushInterval`, `changesOnlyInterval` (settings) and
`aliveSignInterval` (description) go beyond §4.3. Intentional extensions.

### I5 — Code proto vs doc proto divergences

Code proto is newer: has `ErrorType` enum, `errorType` /
`userMessageToBeTranslated` fields in `GenericResponse`, uses
`PushNotification` instead of `PushProperty`. Doc proto omits these.

### I6 — `ping` always responds with pong

Regardless of entity existence/activity. Spec technically allows
entity-specific behaviour.

### I7 — §7.4 configuration methods fall through

`pair`, `authenticate`, `firmwareUpgrade`, `setConfiguration`, `identify`
(via GenericRequest) all fall through to user callback. By design.

---

## Resolved during audit

| ID | Description | Resolution |
|---|---|---|
| E1 | `ButtonMode` UP/DOWN naming inverted vs spec | Fixed — names swapped to match §4.2.2 |
| W8 | `DeviceState._update_interval` dead field | Removed from `__slots__` and constructor |
| — | ~80-line temporary wire-level debug block in `vdc_host.py` | Removed |
