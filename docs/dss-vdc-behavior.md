# dSS VDC Behavior: Firmware-Verified Findings

> Re-verified against `dss-mainline-master` firmware source, April 2026.
> Key files: `src/device-info.cpp`, `src/vdc-db.cpp`, `src/model/busscanner.cpp`,
> `src/model/modelmaintenance.cpp`, `src/model/state.cpp`, `src/model/device.cpp`,
> `src/handler/system_triggers.cpp`, `src/ds485/dsbusinterface.cpp`.
>
> "Existing app add-ons" = **Scene Responder**, **User Defined States**,
> **User Defined Activities**, **Timers**, **Push Manager**, **Presence Simulation**.
> These are JavaScript add-ons that subscribe to dSS C++ events via the property
> tree and event queue — they are **not** present in the C++ source.

---

## 1. `dynamicDefinitions` — role and behavior

`dynamicDefinitions = true` must be set in the VDC's `capabilities` property for the
dSS to query dynamic content live from the device. It is **not** a hard gate that
prevents anything from working — it is a **source selector**:

| Condition | Source used by DeviceInfo |
|---|---|
| `dynamicDefinitions = true` AND device present | Live VDC protobuf queries |
| `dynamicDefinitions = false` OR device absent | vDC-DB (static database by GTIN) |
| Neither present (unknown GTIN, no DB entry, no dynamicDefs) | Empty results |

**Source** (`device-info.cpp:67–90`):
```cpp
m_hasDynamicDefinitions([&] {
  if (!device.isVdcDevice()) return false;
  if (!device.isPresent()) return false;  // absent device → always DB fallback
  switch (m_prefer) {
    case Prefer::none: return dsm->getCapability_HasDynamicDefinitions();
    case Prefer::db:   return false;
    case Prefer::device: return true;
  }
}())
```

Without `dynamicDefinitions = true`, a device still exposes whatever the vDC-DB
defines for its GTIN. The flag does not block events, actions, or states — it only
controls whether the live VDC is queried or the static DB is used as the source.

**Note on device presence:** If the device is not present (`isPresent() == false`),
`m_hasDynamicDefinitions` is forced to `false` and all dynamic queries are suppressed.
Absent VDC devices fall back entirely to the DB.

---

## 2. `primaryGroup = 9` (WHITE / single device) is NOT required

Confirmed. `primaryGroup` controls only which UI surface the device appears on.
It has no relationship to dynamic definition processing.

---

## 3. GTIN and the vDC-DB — what it controls

The vDC-DB (`vdc.db`, an SQLite database created from `/data/vdc-db.sql`) is keyed
exclusively on GTIN. It stores per-GTIN definitions for:

- `callGetStatesBase` → state names + value options
- `callGetEventsBase` → event names + categories
- `callGetPropertiesBase` → property names, types, ranges
- `callGetActionsBase` → action names + parameters
- `callGetStandardActions` → standard action templates
- `callGetSpecBase` → spec/metadata fields
- `hasActionInterface` → boolean: does the GTIN support action invocation?

**Effect of GTIN registration on app add-ons:**

| GTIN status | `initStates()` called | `hasActionInterface` set | States functional | Actions functional |
|---|---|---|---|---|
| Registered in vDC-DB | Yes (DB state slots allocated) | Yes | Yes (via `StateChange` events) | Yes |
| Unknown / custom GTIN | No (no state slots) | No | No | No |
| No GTIN | No | No | No | No |

The "existing app add-ons" are JavaScript components that subscribe to dSS C++ events
(`StateChange`, `DeviceEventEvent`, `DeviceActionEvent`). These events are only raised
when the underlying dSS data model is populated — which requires a registered GTIN for
state slots, or `dynamicDefinitions = true` for live-queried events and actions.

---

## 4. States — how they work and why push alone is insufficient

### 4.1 State slot allocation at scan time

At scan time (`busscanner.cpp:525`):
```cpp
dev->initStates(db->getStatesLegacy(eanString));   // DB lookup by GTIN
```

`Device::initStates()` calls `Apartment::allocateDeviceState()` for each DB-defined
state, creating a `State` object that publishes to `/usr/states/<device-dsuid>.<name>`.
**This is the only place state slots are created.** No state slot → no automation trigger.

If the GTIN is unknown or unregistered, `getStatesLegacy()` returns an empty vector,
`initStates()` does nothing, and no slots exist.

### 4.2 What a VDC push notification actually does

When the VDC sends `VDC_SEND_PUSH_NOTIFICATION` with `deviceStates`:

1. `dsbusinterface.cpp:1103–1127` parses the push into a `VdceModelEvent`
2. `modelmaintenance.cpp:2640–2671` handles `onVdceEvent()`:
   - For each state in the push: calls `Device::setStateValue(name, value)` (`device.cpp:3006`)
   - `setStateValue()` finds the matching `State` in `m_states` and calls `state->setState()`
   - `State::setState()` publishes to the property node **and** pushes a `StateChange` event
     (`state.cpp:450`)
   - Additionally raises a `DeviceStateEvent` (separate raw event, consumed only by event
     logger, not by automation trigger evaluation)
   - Calls `Device::updateStateStatuses()` — updates `m_data->stateStatuses` (the
     Smarthome/REST-API-visible status)
   - Raises a `DeviceEventEvent` for each device event in the push

**The `StateChange` event IS the event that automation triggers (`checkState()` in
`system_triggers.cpp:577`) match against.** It is raised by `State::setState()`.

### 4.3 The dependency: push requires pre-allocated state slots

`Device::setStateValue()` iterates `m_states` (populated by `initStates()`).
If `m_states` is empty (unknown GTIN → `initStates()` not called), `setStateValue()`
silently does nothing. No `StateChange` event is raised. Automation never fires.

**Summary of state propagation:**

```
VDC push → onVdceEvent() → setStateValue(name, value)
                                    │
                    ┌───────────────┴────────────────┐
                    │ m_states has slot for name?     │
                    │                                 │
                   YES                               NO
                    │                                 │
             state.setState()                   silent no-op
                    │
        ┌───────────┴───────────┐
        │                       │
  property tree           StateChange event → automation triggers
  /usr/states/…              (checkState matches "statename" + "value")
```

### 4.4 `dynamicDefinitions = true` enables live state description queries (API only)

When `dynamicDefinitions = true`, `DeviceInfo::getStateDescriptions()` queries
`deviceStateDescriptions` live from the VDC and merges with DB entries. This affects
**only the descriptions returned by the API** (state names and value options shown in
the configurator UI). It does **not** affect runtime state evaluation.

### 4.5 Two parallel state tracking systems

| System | Populated by | Used by | API path |
|---|---|---|---|
| `m_states` + `State` objects | `initStates()` from DB at scan | Automation, event triggers, property tree | `/usr/states/`, `StateChange` events |
| `m_data->stateStatuses` | `setStateStatuses()` / `updateStateStatuses()` | Smarthome API, REST API reads | `/json/device/getInfo` → `operational.states` |
| `m_data->states` (descriptions) | `setStates()` at scan from `deviceInfo.deviceStates()` | Smarthome API state listings | `/smarthome/v1/...` |

VDC push updates `m_data->stateStatuses` and the `State` object (if the slot exists).
Automation uses only the `State` object path.

### 4.6 Conclusion on state functionality

- **Unknown GTIN:** push updates `m_data->stateStatuses` only → visible in Smarthome/JSON
  API but automation never fires (no State slot, no `StateChange` event)
- **Registered GTIN:** push updates both `m_data->stateStatuses` AND the State slot →
  `StateChange` event fires → automation triggers evaluate → **states ARE functional**
- **Name mismatch (VDC state name ≠ DB state name):** `setStateValue()` iterates
  `m_states`; if the name doesn't match any DB-allocated slot, it's a no-op. Automation
  trigger won't fire even with a registered GTIN.

> **The document's prior claim that "VDC states are never functional" was incorrect.**
> States **are** functional when: (a) GTIN is registered in vDC-DB, (b) the pushed state
> name exactly matches a name from `callGetStatesBase` for that GTIN, and (c)
> `dynamicDefinitions = true` (so that `setStates()` is called at scan with the correct
> `deviceStates()` descriptions from the live device, which also includes DB state slots
> via `initStates()`).

---

## 5. Events — how they work

VDC-pushed events follow a clean path:

1. `VDC_SEND_PUSH_NOTIFICATION.deviceevents` → parsed in `dsbusinterface.cpp:1119–1124`
2. `onVdceEvent()` calls `raiseEvent(createDeviceEventEvent(pDevRev, deviceEvent))`
3. `createDeviceEventEvent()` → `Event(EventName::DeviceEventEvent)` with property
   `eventId = <name>` (`event_create.cpp:209–215`)
4. `SystemTrigger::checkDeviceNamedEvent()` matches on `dsuid` + `eventId`
   (`system_triggers.cpp:512–547`)

**Events raised this way reach the automation trigger evaluation regardless of GTIN.**
However, for the existing app add-ons to **display** the event by its human-readable
name (title/label), the GTIN must be registered so the DB provides the description.
Functionally, the event fires either way; it's just unlabelled without a DB entry.

---

## 6. Actions — how they work

Actions are invoked via `Device::callAction()` (`device.cpp:3874`), called from:
- JSON API endpoint `callAction` (`devicerequesthandler.cpp:322`)
- Automation execution via `ds-scenarios.cpp:918` (for device scenario actions)
- Script engine via `action-execute.cpp:508`

For a VDC device, `callAction()` sends a `vdcapi` `SET_PROPERTY` request with the
action ID and parameters to the VDC.

The condition `db->hasActionInterface(eanString)` controls the `hasActions` flag
(`busscanner.cpp:526`), which gates the **Activities tab** in the configurator UI.
Without a registered GTIN, `hasActionInterface()` returns `false`, `hasActions = false`,
and the Activities tab is suppressed. The action invocation path itself does not check
`hasActions` — only the UI does.

`dynamicDefinitions = true` enables live `deviceActionDescriptions` queries for the
action picker UI. Without it, the picker shows only DB-defined actions.
`customActions` and `dynamicActionDescriptions` are always queried live regardless of
`dynamicDefinitions` (see `device-info.cpp:764–796`).

---

## 7. Device properties — access paths

Properties are exposed exclusively via JSON API — there is no automation trigger for
device property changes and no app add-on integration.

Access paths:
- Descriptions: `DeviceInfo::addPropertyDescriptions()` → `/json/device/getInfo`
- Values (live, read): `addOperational()` queries `deviceProperties` live → operational
  section of `getInfo`
- Values (write): `setProperty` API endpoint → `vdcapi` SET_PROPERTY

When `dynamicDefinitions = true`, property descriptions are merged from both the live VDC
and the DB. Without it, only DB-defined properties are shown. Either way, no automation
integration exists.

---

## 8. `vdcDb::update()` — confirmed dead code

`vdcDb::update()` is defined in `vdc-db.cpp:126–137` but **never called** anywhere in
the codebase. The only write path is `vdcDb::recreate()` (`vdc-db.cpp:91–124`), which
is called once at startup from `dss.cpp:279`. The DB is read-only at runtime.

No external API endpoint exposes database updates. The DB is a compiled-in artifact
from `/data/vdc-db.sql` and is not modifiable without firmware replacement.

---

## 9. Summary matrix (firmware-verified)

| Feature domain | `dynamicDefinitions` | Registered GTIN | Automation / app add-ons | Smarthome API | JSON API |
|---|---|---|---|---|---|
| Events (fire trigger) | not required | not required | ✅ fires regardless | ✅ | ✅ |
| Events (named/labelled) | not required | required for label | ✅ labelled only with DB | ✅ | ✅ |
| Actions (invocation) | not required | not required for invoke | ✅ (scenario/script) | ✅ | ✅ |
| Actions (Activities tab UI) | for action picker | required for tab | ✅ tab visible with DB | ✅ | ✅ |
| States (functional) | required (for scan-time setStates call) | **required** (initStates + name match) | ✅ with GTIN + name match | ✅ | ✅ |
| States (display only, unknown GTIN) | — | — | ❌ no StateChange event | ✅ stateStatuses | ✅ |
| Properties | for live descriptions | any | ❌ no automation integration | ❌ | ✅ |

---

## 10. Detailed event/state flow reference

### VDC push notification → automation trigger (states)

```
VDC sends VDC_SEND_PUSH_NOTIFICATION
  │
  └─→ dsbusinterface.cpp:1096–1127   parse into VdceModelEvent{m_states, m_events, m_dynamicActions}
        │
        └─→ modelmaintenance.addModelEvent(pEvent)
              │
              └─→ onVdceEvent() [modelmaintenance.cpp:2640]
                    │
                    ├─→ for each state in push:
                    │     setStateValue(name, value)  [device.cpp:3006]
                    │       └─→ State::setState()     [state.cpp]
                    │             ├─→ update property tree: /usr/states/<name>
                    │             └─→ pushEvent(StateChange)  [state.cpp:450]
                    │                   └─→ SystemTrigger::checkState() evaluates
                    │                         against "state-change" automation rules
                    │
                    ├─→ updateStateStatuses()   → m_data->stateStatuses (REST/Smarthome API)
                    │
                    └─→ for each event in push:
                          raiseEvent(DeviceEventEvent{eventId})  [modelmaintenance.cpp:2663]
                            └─→ SystemTrigger::checkDeviceNamedEvent() evaluates
                                  against "device-named-event" automation rules
```

### Scan-time state slot allocation (pre-requisite)

```
busscanner initializeDeviceFromSpec()
  │
  ├─→ db->getStatesLegacy(GTIN)             ← DB lookup: empty if GTIN unknown
  │     │
  │     └─→ dev->initStates(stateSpecs)     [device.cpp:2954]
  │           └─→ Apartment::allocateDeviceState()
  │                 └─→ State object published to /usr/states/<device>.<statename>
  │                       (StateType_Device → path "/usr/states/")
  │
  └─→ DeviceInfo::deviceStates()            ← reads from DB (or live VDC if dynamicDefs)
        └─→ dev->setStates(...)             ← stores descriptions in m_data->states
                                               (used by Smarthome API listing only)
```
