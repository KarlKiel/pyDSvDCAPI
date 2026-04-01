# Compliance Audit — Open Topics

Audit date: 3 March 2026
Compared against: `vdc-API/` (§1–§7) and `vdc-API-properties/` (§2–§16)
All 1168 tests passing at time of audit.

---

## Errors (semantic mismatches with spec)

### ~~E2~~ — Proto: `setOutputChannelValue` missing fields — DOWNGRADED to INFO

§7.3.9 defines `automatic` (bool), `group` (int), `zone_id` (int) on
`vdsm_NotificationSetOutputChannelValue`. Both the code proto and the
documentation proto are missing all three.

**Assessment (downgraded):** Not a functional compliance gap.

- `group` / `zoneID` are *"informational only, vdSM already creates
  separate calls for every involved device"* — identical to every other
  notification. No functional impact.
- `automatic` signals "switch to internal automatic control logic" — a
  niche capability for devices with built-in autonomous behaviour (e.g.
  HVAC thermostats). Not relevant to the current device model.
- Proto field indices are unknown — neither the code proto nor the
  documentation proto define these fields, so the upstream field numbers
  from plan44's vdSM implementation would be needed to add them safely.
  Wrong indices would silently corrupt wire deserialization.

**No action required.**

### ~~E3~~ — Missing handler: `remove` (§6.3) — RESOLVED

`VDSM_SEND_REMOVE` (type 13) now has a built-in handler in
`_dispatch_message()`. The handler looks up the device, consults an
optional `on_remove` callback (async, returns `True`/`False`), and
responds with `ERR_OK` (removal accepted) or `ERR_FORBIDDEN` (rejected).
When no callback is set, removal is always accepted. Unknown dSUIDs
return `ERR_NOT_FOUND`.

**Resolved in:** `vdc_host.py` — `_handle_remove()` + dispatch entry +
`on_remove` parameter on `start()`.

---

## Warnings (missing optional features / undocumented extensions)

### ~~W1~~ — Missing handler: `dimChannel` (§7.3.5) — RESOLVED

`VDSM_NOTIFICATION_DIM_CHANNEL` (type 24) now has a built-in handler in
`_dispatch_message()`. The handler resolves the target output and
channel (by `channelId` for API v3, channel type int, or default first
channel when `channel=0`), then delegates to
`Output.dim_channel(channel, mode, area)` which invokes the user's
`on_dim_channel` callback.

**Resolved in:** `vdc_host.py` — `_handle_dim_channel()` + dispatch
entry; `output.py` — `DimChannelCallback` type, `on_dim_channel`
property, `dim_channel()` method.

### ~~W2~~ — Missing handler: `identify` (§7.3.7 + §7.4.5) — RESOLVED

The identify feature has two entry points in the protocol, both now
handled:

1. **§7.3.7 — `VDSM_NOTIFICATION_IDENTIFY` (type 20):** A dedicated
   notification targeting **individual devices**. The handler resolves
   each addressed vdSD and calls `Vdsd.identify()`, which invokes the
   user's `on_identify` callback (sync or async). This lets the user
   trigger a blink, beep, or other identification signal on the native
   hardware.

2. **§7.4.5 — GenericRequest `"identify"`:** A generic request
   targeting the **vDC host platform** itself. The handler is built
   into `_handle_generic_request()` and calls the host-level
   `on_identify` callback passed to `VdcHost.start()`.

**Resolved in:**
- `vdsd.py` — `IdentifyCallback` type, `on_identify` property,
  `identify()` method on `Vdsd`
- `vdc_host.py` — `IdentifyCallback` type (host-level),
  `_handle_identify()` for the notification path, `"identify"` case
  in `_handle_generic_request()`, `on_identify` parameter on `start()`

### ~~W3~~ — Missing optional vdSD properties — RESOLVED

§4.1.1 optional properties have been added to `Vdsd`:

- `prog_mode` — optional `bool`, r/w via constructor, persistence, and
  `setProperty` (wire name `progMode`)
- `current_config_id` — optional `str`, r/o via constructor and
  persistence (wire name `currentConfigId`)
- `configurations` — optional `List[str]`, read-only property, persisted
  and restored (wire name `configurations`)

All three default to `None` / empty list so they are fully optional
during construction.

Additionally, keyword-only enforcement (`*`) was added to `DeviceEvent`,
`DeviceState`, and `DeviceProperty` constructors for consistency with
all other entity classes.

**Resolved in:** `vdsd.py` — constructor, `get_properties()`,
`get_property_tree()`, `_apply_state()`; `vdc_host.py` —
`_apply_vdsd_properties()` for `progMode` writes; `device_event.py`,
`device_state.py`, `device_property.py` — keyword-only `*` added.

### W4 — `ButtonClickType.LOCAL_DIM = 15` undocumented

Present in code but not in spec §4.2.3 (spec enumerates 0–14 then jumps
to 255). Value 15 is not documented.

**Decision:** Keep as forward-compatible extension.

### W5 — `ButtonMode.TURBO = 1` undocumented

Present in code but not in spec §4.2.2 (spec lists only 0, 2, 5–12).
Value 1 is not documented.

**Decision:** Keep as forward-compatible extension.

### ~~W6~~ — Scene handlers missing `group` / `zoneID` — RESOLVED

All five scene handlers now extract `group` and `zone_id` from the
protobuf notification and use them for:

1. **Zone/group filtering** — a device is only affected if its
   `zone_id` and `primary_group` (or `output.groups` secondary set)
   match the notification values.  A value of `0` means "not specified"
   and always matches (backward compatible).

2. **Per-group undo tracking** — `Output.call_scene()` and
   `Output.undo_scene()` now accept a `group` parameter.  Undo
   snapshots are stored keyed by group so that different group scene
   calls can be reverted independently.

Affected handlers: `_handle_call_scene`, `_handle_save_scene`,
`_handle_undo_scene`, `_handle_set_local_priority`,
`_handle_call_min_scene`.

Helper method `VdcHost._matches_zone_and_group()` implements the
zone/group matching logic.

**Resolved in:** `vdc_host.py` — all 5 scene handlers +
`_matches_zone_and_group()` helper; `output.py` — `call_scene()` and
`undo_scene()` with per-group undo via `_last_called_scenes` dict and
`_undo_snapshots` dict.

### ~~W7 — Unhandled GenericRequest error code~~ → RESOLVED

~~Unknown GenericRequest methods return `ERR_NOT_FOUND`. Arguably should
return `ERR_NOT_IMPLEMENTED` per §1.2.~~

**Resolution:** Changed to `ERR_NOT_IMPLEMENTED`.

---

## Info (minor or by-design differences)

### I1 — `BinaryInputType.BRIGHTNESS` naming

Spec says "Light" (id=2). Code uses `BRIGHTNESS`. Value is correct;
name differs slightly.

**Decision:** Keep as-is.

### I2 — `controlValues` emitted in vdSD properties

Not a spec-listed vdSD property. Implementation extension for runtime
control values.

**Decision:** Keep as-is.

### I3 — `DeviceProperty.description` extra field

Extra `description` field in description output. Additive, not harmful.

**Decision:** Keep as-is.

### ~~I4 — BinaryInput extra settings~~ → RESOLVED

~~`BinaryInput` exposed three timing parameters not listed in the spec's
§4.3 property tables: `minPushInterval`, `changesOnlyInterval`,
`aliveSignInterval`.~~

**Resolution:** Removed.  The dSS vdSM does not recognise these
properties, so exposing them has no effect.  Push throttling, deferred
push coalescing, and alive timer logic were stripped from
`BinaryInput`.  The `start_alive_timer` / `stop_alive_timer` methods
are retained (for interface compatibility with `SensorInput` /
`ButtonInput`) but now only store/clear the session reference.

### I5 — Code proto vs doc proto divergences

Code proto is newer: has `ErrorType` enum, `errorType` /
`userMessageToBeTranslated` fields in `GenericResponse`, uses
`PushNotification` instead of `PushProperty`. Doc proto omits these.

**Decision:** Irrelevant — the code proto is the authoritative version;
the documentation proto is simply outdated.

### I6 — `ping` always responds with pong

Regardless of entity existence/activity. Spec technically allows
entity-specific behaviour.

**Decision:** Keep as-is.

### ~~I7 — §7.4 configuration methods fall through~~ → RESOLVED

~~`pair`, `authenticate`, `firmwareUpgrade`, `setConfiguration`, `identify`
(via GenericRequest) all fall through to user callback. By design.~~

**Resolution:** Dedicated optional callbacks (`on_pair`, `on_authenticate`,
`on_firmware_upgrade`, `on_set_configuration`) added to `VdcHost.start()`.
Each §7.4 method is dispatched to its callback; returns `ERR_NOT_IMPLEMENTED`
when no callback is registered.  12 tests cover all 4 methods.

---

## Resolved during audit

| ID | Description | Resolution |
|---|---|---|
| E1 | `ButtonMode` UP/DOWN naming inverted vs spec | Fixed — names swapped to match §4.2.2 |
| E3 | Missing `remove` handler (§6.3) | `_handle_remove()` with `on_remove` callback |
| W1 | Missing `dimChannel` handler (§7.3.5) | `_handle_dim_channel()` with `on_dim_channel` callback |
| W2 | Missing `identify` handler (§7.3.7 + §7.4.5) | `_handle_identify()` + GenericRequest `"identify"` with `on_identify` callbacks |
| W3 | Missing optional vdSD properties (§4.1.1) | `progMode`, `currentConfigId`, `configurations` on `Vdsd`; keyword-only `*` on 3 entity classes |
| W6 | Scene handlers missing `group` / `zoneID` | Zone/group filtering + per-group undo tracking in all 5 handlers |
| W7 | Unknown GenericRequest returns wrong error | Changed from `ERR_NOT_FOUND` to `ERR_NOT_IMPLEMENTED` |
| I7 | §7.4 methods fall through to user callback | Dedicated `on_pair`, `on_authenticate`, `on_firmware_upgrade`, `on_set_configuration` callbacks |
| W8 | `DeviceState._update_interval` dead field | Removed from `__slots__` and constructor |
| — | ~80-line temporary wire-level debug block in `vdc_host.py` | Removed |
