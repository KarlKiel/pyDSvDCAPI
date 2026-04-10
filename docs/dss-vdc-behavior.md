# dSS VDC Behavior: Empirically Verified Findings

> Established through matrix testing (7-device and 9-device announce, April 2026).  
> "Existing app add-ons" refers to the following, all of which were tested:
> **Scene Responder**, **User Defined States**, **User Defined Activities**,
> **Timers**, **Push Manager**, and **Presence Simulation**.

---

## 1. `dynamicDefinitions` is mandatory for custom features

The VDC **must** be configured with `dynamicDefinitions = true` in its
capabilities to use any custom dynamic elements (states, events, properties,
actions) at all. Without it, none of those elements are visible or usable —
regardless of GTIN or `primaryGroup`.

---

## 2. `primaryGroup = 9` (WHITE / single device) is NOT required

Marking a vdSD as a "single device" (`primaryGroup = ColorClass.WHITE`, value
9) is **not** required for dynamic definitions to work. The `primaryGroup`
setting controls only which UI surface the device appears on; it has no effect
on whether dynamic states, events, properties, or actions are processed.

---

## 3. GTIN registered in the vDC-DB is required for existing app add-on visibility

Dynamic definitions are only surfaced to the existing dSS app add-ons when the
device reports a **GTIN that is registered in the dSS VDC-DB**. Devices
announcing no GTIN or an unknown/custom GTIN are invisible to all existing app
add-ons.

| Device GTIN            | Existing app add-on visibility |
|------------------------|--------------------------------|
| Registered in vDC-DB   | ✅ Visible                      |
| Unknown / custom GTIN  | ❌ Not visible                  |
| No GTIN                | ❌ Not visible                  |

---

## 4. Events and actions are functional in existing app add-ons

For devices with a registered GTIN, **VDC-defined events and actions** are
correctly available and functional in all existing dSS app add-ons. Both were
tested and confirmed working in: **Scene Responder**, **User Defined States**,
**User Defined Activities**, **Timers**, **Push Manager**, and **Presence
Simulation**.

---

## 5. VDC-defined states are NOT functional in existing app add-ons (confirmed)

VDC-defined device states are **never functional** in any existing dSS app
add-on, regardless of GTIN or whether the VDC-defined state names exactly
match the DB-defined names for the used GTIN.

Two test cases confirmed:

1. **Custom state names** (e.g. `pyVDC_State`) with a registered GTIN — states
   are visible in the condition picker but never evaluate correctly.
2. **Exact DB state name match** (e.g. `dummyState` with GTIN `1234567890123`,
   options `d`/`mm`/`u`/`y` matching the DB definition verbatim) — state
   changes pushed by the VDC are **not recognised** by the app add-ons.

The root cause is that `initStates()` writes state slots to `/usr/states/`
exclusively from the `callGetStatesBase` pre-built DB table at scan time.
VDC protobuf push notifications update `m_data->states` (visible in the
Hardware tab status column), but this is **completely separate** from
`/usr/states/`. Automation evaluation reads only `/usr/states/` — so no
VDC state push, regardless of name match, will ever cause an automation
condition to fire.

---

## 6. Devices with no or unknown GTIN: API access only

States and actions of devices reporting no GTIN or an unregistered GTIN are
**not available in any existing dSS app add-on**, but they remain accessible
via:

- **Smarthome API** — states and actions readable/invocable
- **JSON API** — states and actions readable/invocable

---

## 7. Device properties are JSON API only

VDC-defined device properties (type numeric, string, or enumeration) are
**only accessible and changeable via the JSON API**. They do not appear in any
existing dSS app add-on, regardless of GTIN or `dynamicDefinitions`.

---

## 8. No external API to add vDC-DB entries

There is currently **no externally available API** to register new GTINs or
add entries to the vDC-DB at runtime. The DB is a static resource compiled
into the firmware image. The only known write path is the internal developer
tool `update-vdc-db.sh`, which fetches a replacement DB from
`http://db.aizo.net/vdc-db2.php` during firmware build. No runtime write path
exists in the dSS C++ codebase (`vdcDb::update()` is dead code and is never
called).

---

## Summary matrix

| Feature domain           | `dynamicDefinitions` | Registered GTIN | Existing app add-ons | Smarthome API | JSON API |
|--------------------------|----------------------|-----------------|----------------------|---------------|----------|
| Events                   | required             | required        | ✅ functional (tested) | ✅           | ✅       |
| Actions                  | required             | required        | ✅ functional (tested) | ✅           | ✅       |
| States (display)         | required             | required        | ⚠️ displayed only (tested) | ✅      | ✅       |
| States (exact DB names)  | required             | required        | ❌ not functional (tested) | ✅      | ✅       |
| States (no/custom GTIN)  | required             | —               | ❌                    | ✅            | ✅       |
| Properties               | required             | any             | ❌                    | ❌            | ✅       |
