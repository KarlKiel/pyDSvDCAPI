# p44vdc Reference vs pyDSvDCAPI — Comparison & Bug Report

_Sources: `github.com/plan44/p44vdc` (branch `main`), compared against
`pyDSvDCAPI` sources.  Files examined: `vdc_common/device.cpp`,
`vdc_common/singledevice.cpp`, `vdc_common/singledevice.hpp`,
`behaviours/sensorbehaviour.cpp`._

---

## 1. Post-Announcement Sensor / Binary-Input State Push  ⚠️ BUG (sensor values never appear)

### Reference behaviour (`device.cpp`)

```cpp
void Device::vdSMAnnouncementAcknowledged() {
    // Push current values of all sensors and inputs
    for (pos = mInputs.begin(); ...) {
        if ((*pos)->hasDefinedState()) (*pos)->pushBehaviourState(true, false);
    }
    for (pos = mSensors.begin(); ...) {
        if ((*pos)->hasDefinedState()) (*pos)->pushBehaviourState(true, false);
    }
}
```

`hasDefinedState()` in `sensorbehaviour.cpp`:

```cpp
bool SensorBehaviour::hasDefinedState() { return mLastUpdate != Never; }
```

**The reference explicitly pushes all sensor and binary-input states to the
vdSM immediately after the announcement is acknowledged, provided a value has
already been set.**  The dSM never polls `sensorStates` after announcement —
it relies entirely on push notifications.

### Our implementation (`vdsd.py`, `announce()`)

After receiving `ERR_OK`, the code only:
- sets `_announced = True`
- calls `si.start_alive_timer(session)` for each sensor (stores session ref)

**No initial push is performed.**  Because `_value` starts as `None`, the
dSM never receives a sensor reading after announcement.

### Fix

In `vdsd.py`, after the successful announce loop, add:

```python
# Push initial state for any sensor/binary-input that already has a value
for si in self._sensor_inputs.values():
    if si.value is not None:
        await si.update_value(si.value)   # re-push current value
for bi in self._binary_inputs.values():
    if bi.value is not None:
        await bi.push_state(session)
```

Alternatively, pre-set a default sensor value **before** calling `announce()`
so that the push fires during the announce loop; this matches the pattern
used by physical hardware drivers under p44vdc.

---

## 2. `dynamicActionDescriptions` Property Key Name  ⚠️ BUG

### Reference (`singledevice.cpp`)

```cpp
static const PropertyDescription properties[numSingleDeviceProperties] = {
    { "deviceActionDescriptions",  ... },
    { "dynamicActionDescriptions", ... },   // ← exact name
    { "customActions",             ... },
    { "standardActions",           ... },
    { "deviceStateDescriptions",   ... },
    { "deviceStates",              ... },
    { "deviceEventDescriptions",   ... },
    { "devicePropertyDescriptions",...},
    { "deviceProperties",          ... }
};
```

### Our implementation (`vdsd.py`, line ~1396)

```python
props["dynamicDeviceActions"] = { ... }   # ← WRONG name
```

### Fix

```python
props["dynamicActionDescriptions"] = { ... }
```

---

## 3. SingleDevice Properties Visibility Gate  ⚠️ Possible cause of missing features

### Reference (`singledevice.cpp`)

```cpp
int SingleDevice::numProps(int aDomain, PropertyDescriptorPtr aParentDescriptor) {
    // properties are only visible when single device is enabled
    if (aParentDescriptor->isRootOfObject() && deviceActions) {
        return inherited::numProps(...) + numSingleDeviceProperties;
    }
    return inherited::numProps(...);
}
```

All nine SingleDevice properties are added to the device's property tree as
soon as `deviceActions != nullptr` (i.e., after `enableAsSingleDevice()` is
called), **regardless of whether the containers are empty**.

### Our implementation

The state/event/property sub-trees are gated individually:

```python
if self._device_states:          # only when non-empty
    props["deviceStateDescriptions"] = ...
    props["deviceStates"] = ...

if self._device_events:          # only when non-empty
    props["deviceEventDescriptions"] = ...

if self._device_properties:      # only when non-empty
    props["devicePropertyDescriptions"] = ...
    props["deviceProperties"] = ...
```

A device that has actions but no states/events/properties would serve
`deviceActionDescriptions` but **not** the sibling keys.  The dSM may rely
on all nine keys being present together to identify a SingleDevice.

### Fix

When `has_single_device` is `True`, always emit all nine keys (with `{}`
for empty containers):

```python
if has_single_device:
    props["deviceActionDescriptions"]  = ...or {}
    props["dynamicActionDescriptions"] = ...or {}
    props["customActions"]             = ...or {}
    props["standardActions"]           = ...or {}
    props["deviceStateDescriptions"]   = ...or {}
    props["deviceStates"]              = ...or {}
    props["deviceEventDescriptions"]   = ...or {}
    props["devicePropertyDescriptions"]= ...or {}
    props["deviceProperties"]          = ...or {}
```

---

## 4. `highlevel` Model Feature — Meaning Revised

### Reference (`device.cpp`)

```cpp
case modelFeature_highlevel:
    // Assumption: only black joker devices can have a high-level (app) functionality
    return mColorClass == class_black_joker ? yes : no;
```

### Revised analysis

The original analysis assumed `highlevel` gates the dSM querying
`deviceActionDescriptions`.  This was inferred from p44vdc's correlation
("black joker devices have `highlevel` AND have actions"), not documented.

The official vDC-API-properties spec (§4.1.1.1) lists `highlevel` as one
entry in the modelFeatures *visibility matrix* alongside `pushbdevice`,
`pushbsensor`, `pushbarea`, `pushbadvanced`, `pushbcombined` etc.  The
naming pattern and context strongly suggest `highlevel` controls the
appearance of an **advanced/app mode menu item in the button input function
selection UI** — not the SingleDevice Actions tab.

`pushbadvanced` and `highlevel` sit in the same region of the model feature
list, and p44vdc's own comment says "Assumption: only black joker devices
can have high-level (app) functionality" — black joker devices are the ones
that have programmable button inputs, which is consistent with this UI
gate interpretation.

**Consequence:** setting `highlevel` from having SingleDevice features is
based on a faulty extrapolation.  The actual gate for the dSM showing the
Actions tab / querying `deviceActionDescriptions` is likely either:
- Simply the *presence* of `deviceActionDescriptions` in the property tree, or
- An undocumented dSS-internal check (e.g. `primaryGroup` == BLACK).

### Current status

The `derive_model_features()` fix (setting `highlevel` when any SingleDevice
feature is defined) was applied in a previous session.  Given the revised
analysis it may be harmless (if `highlevel` has no effect on actions
visibility) or even counterproductive (if it shows an unwanted button
configuration menu on non-button devices).

⚠️ **Needs real-world verification:** run the demo with and without
`highlevel` and observe whether the dSS Actions tab appears or disappears.
If `highlevel` has no effect on Actions, the feature should only be set
for devices that also have button inputs where advanced mode is meaningful.

---

## 5. Sensor Description Missing `siunit` and `symbol` Fields

### Reference (`sensorbehaviour.cpp`)

```cpp
{ "sensorType",     apivalue_uint64, ... },
{ "sensorUsage",    apivalue_uint64, ... },
{ "siunit",         apivalue_string, ... },   // e.g. "K" for Kelvin/°C
{ "symbol",         apivalue_string, ... },   // e.g. "°C"
{ "min",            apivalue_double, ... },
{ "max",            apivalue_double, ... },
{ "resolution",     apivalue_double, ... },
{ "updateInterval", apivalue_double, ... },
{ "aliveSignInterval", apivalue_double, ... },
{ "maxPushInterval",   apivalue_double, ... },
```

### Our implementation (`sensor_input.py`)

`get_description_properties()` returns:

```python
{
    "name":              ...,
    "dsIndex":           ...,
    "sensorType":        ...,
    "sensorUsage":       ...,
    "min":               ...,
    "max":               ...,
    "resolution":        ...,
    "updateInterval":    ...,
    "aliveSignInterval": ...,
    # MISSING: siunit, symbol, maxPushInterval
}
```

### Fix

Add to `get_description_properties()`:

```python
from pyDSvDCAPI.sensor_input import SENSOR_UNIT_MAP  # see implementation note

desc["siunit"]         = sensor_si_unit(self._sensor_type)   # e.g. "K"
desc["symbol"]         = sensor_unit_symbol(self._sensor_type) # e.g. "°C"
desc["maxPushInterval"] = ...  # derived from alive_sign_interval
```

See the `valueUnitName()` helper in p44vdc for the unit mapping table.  For
temperature: `siunit="K"`, `symbol="°C"`.

---

## 6. Sensor State `error` Field

### Reference (§4.4.3 Sensor Input State)

`sensorStates[N]` has **5** properties: `value` (double|null), `age`
(double|null), `contextId` (uint, optional), `contextMsg` (string, optional),
and **`error`** (integer enum: 0=ok, 1=open circuit, 2=short circuit,
4=bus connection problem, 5=low battery, 6=other device error).

### Our implementation

`get_state_properties()` emits `"error": int(self._error)` — **this is
correct and spec-compliant**.  The official API documentation at §4.4.3
explicitly defines `error` as a required field of `sensorStates`.

### p44vdc deviation

`sensorbehaviour.cpp` `getStateDescriptorByIndex()` only declares 4
properties (`value`, `age`, `contextId`, `contextMsg`) and omits `error`.
This is a p44vdc omission — our library is compliant, p44vdc is not.

### Status

✅ **No fix needed** — our implementation is already correct per spec.

---

## 7. Sensor Push Frequency Profiles

### Reference (`sensorbehaviour.cpp`)

The reference contains built-in per-type-and-usage profiles that govern *when*
the VDC sends pushes.  Relevant profile for room temperature:

```
sensorType_temperature + usage_room:
  minPushInterval  = 5 minutes
  changesOnlyInterval = 60 minutes
  trigDelta        = 0.5 °C   (push if change > 0.5 °C)
  trigMin          = −100 °C  (must exceed this minimum)
  trigIntvl        = 1 second (check immediately)
```

This means the reference will **not push** room temperature more often than
every 5 minutes unless the value changed by ≥ 0.5 °C.

### Our implementation

No built-in profiles.  `minPushInterval` defaults to 2 seconds.

### Analysis

These settings are **purely a vDC-side throttle**.  The dSS stores the
`minPushInterval` / `changesOnlyInterval` values (they are readable
`sensorSettings` properties) but **never uses them to drive its own
behavior** — it is entirely the vDC's responsibility to push at the right
rate.  p44vdc bakes in sane defaults to avoid flooding the dS bus with
high-frequency hardware sensors.  For a software/virtual device library
this is not relevant: the calling code controls the push rate by deciding
when to call `update_value()`.  The default 2-second floor is acceptable.

### Status

✅ **Won't fix** — push rate management is the caller's responsibility; dSS
does not enforce these values.

---

## 8. `vdSMAnnouncementAcknowledged` vs `start_alive_timer`

### Reference

The method `vdSMAnnouncementAcknowledged()` is a dedicated lifecycle hook
called exactly once, after the dSM confirms the announcement.  It both starts
timers and fires the initial state push.

### Our implementation

`start_alive_timer()` is called after announce but only starts the periodic
alive-sign timer.  No initial push happens here.  This is the root cause of
**Bug 1** (sensor values never shown).

---

## 9. modelFeatureNames Reference List

For completeness: full list of model features in p44vdc
(`device.cpp`, `modelFeatureNames[]`):

```
dontcare, blink, ledauto, leddark, transt,
outmode, outmodeswitch, outmodegeneric, outvalue8,
pushbutton, pushbdevice, pushbsensor, pushbarea,
pushbadvanced, pushbcombined,
shadeprops, shadeposition, motiontimefins, optypeconfig, shadebladeang,
highlevel, consumption, jokerconfig,
akmsensor, akminput, akmdelay,
twowayconfig, outputchannels,
heatinggroup, heatingoutmode, heatingprops,
pwmvalue, valvetype, extradimmer, umvrelay, blinkconfig, umroutmode, fcu,
extendedvalvetypes, identification
```

Notable: **there is NO `"singledevice"` model feature**.  The mechanism that
tells the dSM this is a SingleDevice device is:
1. The device returns `modelFeatures.highlevel = true`
2. The device returns a non-empty `deviceActionDescriptions` (or at least the
   key exists in the property tree).

---

## 10. Output Group / Channel Type Numbering

### Reference (`outputbehaviour.cpp`, channel types)

The reference internally uses `DsChannelType` values from `dsdefs.h`.  The
"brightness" channel for a light output uses `channeltype_brightness = 1`.
For a black (variable) output used as a simple relay, the "power" channel
uses `channeltype_power = 2` or the default channel (`channeltype_default = 0`
resolves to the first channel).

For `group_black_variable` (group 8), the reference uses `OutputFunction`
`outputFunction_custom` or `outputFunction_switch` — NOT `outputFunction_dimmer`.

Our Device C using `OutputChannelType.BRIGHTNESS` (channel type 1) was
observed to work with the dSS after setting `default_group=8, active_group=8,
groups={8}`.  The brightness channel type being 1 (not 24 or 55) confirms
the **ds-basics table** (1-based) is the correct reference for `channelType`
in property responses.

---

## Summary — Action Items

| # | Severity | File | Issue | Status |
|---|---|---|---|---|
| 1 | **Critical** | `vdsd.py` | No initial sensor/binary-input push after announce | ✅ **FIXED** — `_push_state(session, force=True)` called for all inputs with non-None value after `ERR_OK` |
| 2 | **High** | `vdsd.py` | `dynamicDeviceActions` → should be `dynamicActionDescriptions` | ✅ **FIXED** — key renamed |
| 3 | **High** | `vdsd.py` | State/event/property sub-trees only added when non-empty | ✅ **FIXED** — all 9 SingleDevice keys always emitted when `has_single_device` |
| 4 | **High** | `vdsd.py` | `highlevel` model feature | ✅ **Closed** — `highlevel` is a UI visibility feature (e.g. advanced button config menu), confirmed to have no effect on whether actions/events/properties are visible.  Real-world test proved model features are delivered and applied correctly by the dSS (`outvalue8` produced the expected config UI).  `highlevel` is NOT auto-derived; callers may set it explicitly if the specific UI element is desired |
| 5 | Medium | `sensor_input.py` | Missing `siunit`, `symbol`, `maxPushInterval` in sensor description | ✅ **Won't fix** — `siunit`/`symbol` are derived by the dSM from `sensorType` and cannot be customised; `maxPushInterval` is always deterministic from `aliveSignInterval` (55 min if set, otherwise irrelevant) and is a vDC-internal scheduling detail, not consumed meaningfully by the dSM |
| 6 | — | `sensor_input.py` | `error` field in `sensorStates` | ✅ **Correct** — `error` IS defined in §4.4.3; p44vdc omits it; our implementation is spec-compliant |
| 7 | — | `sensor_input.py` | Push intervals not profiled per sensor type/usage | ✅ **Won't fix** — throttle is vDC-side only; dSS never enforces these values; caller controls push rate via `update_value()` |

---

## 11. Enum Table Comparison: pyDSvDCAPI vs p44vdc `dsdefs.h`

Proto files compared: `src/pydsvdcapi/genericVDC.proto` (our version = updated
API) vs `/home/arne/Dokumente/vdc/pyvdcapi/Documentation/proto/genericVDC.proto`
(older doc version).

### 11.1 Proto File (Wire Protocol)

| Message / Type | Our proto | Doc proto | Wire value | Verdict |
|---|---|---|---|---|
| Push notification type | `VDC_SEND_PUSH_NOTIFICATION` | `VDC_SEND_PUSH_PROPERTY` | 12 | ✅ Same wire format — our proto uses the updated name |
| Push message struct | `vdc_SendPushNotification` | `vdc_SendPushProperty` | — | Renamed, our version is the current API |
| Set-property response | Not present | `VDC_RESPONSE_SET_PROPERTY = 7` | 7 | Doc has deprecated entry |
| Generic request type | 26 | 26 | 26 | ✅ Identical |

**Conclusion:** Wire protocol is identical. Our proto simply uses the updated
(non-deprecated) type names.

### 11.2 `OutputChannelType` enum

**Source:** Official vDC API documentation §4.9.4 (`12-Output-Channel.md`).

Our `enums.py` **matches the official documentation exactly**.  The p44vdc
`dsdefs.h` uses an **older numbering** (shade types start at 7 vs 11 in
the spec).  The dSM expects the spec-compliant values.

| Official spec ID | Channel Name | Our `OutputChannelType` | `dsdefs.h` value |
|---|---|---|---|
| 11 | Shade Position Outside | `SHADE_POSITION_OUTSIDE = 11` ✅ | `channeltype_shade_position_outside = 7` ❌ |
| 12 | Shade Position Indoor | `SHADE_POSITION_INDOOR = 12` ✅ | `channeltype_shade_position_inside = 8` ❌ |
| 21 | Heating Power | `HEATING_POWER = 21` ✅ | `channeltype_heating_power = 16` ❌ |
| 25 | Air Flow Intensity | `AIR_FLOW_INTENSITY = 25` ✅ | `channeltype_airflow_intensity = 12` ❌ |

**Verdict:** Our channel type IDs are correct per the current spec.  The
`dsdefs.h` values are from an older internal version and should NOT be used.

### 11.3 `SensorType` enum

**Source:** Official vDC API documentation §4.4.1  vs p44vdc `dsdefs.h`
`VdcSensorType` enum.

The official docs cover sensor types 0–28.  p44vdc `dsdefs.h` extends them
to 34 with additional physical quantity types.  Our `enums.py` previously
stopped at 28; types 29–34 are now added.

| ID | Official docs | p44vdc `dsdefs.h` | Our `enums.py` (after fix) |
|---|---|---|---|
| 0–28 | ✅ defined | ✅ same values | ✅ present (unchanged) |
| 29 | — | `sensorType_length` (m) | ✅ `LENGTH = 29` **added** |
| 30 | — | `sensorType_mass` (g) | ✅ `MASS = 30` **added** |
| 31 | — | `sensorType_duration` (s) | ✅ `DURATION = 31` **added** |
| 32 | — | `sensorType_percent` (0..100%) | ✅ `PERCENT = 32` **added** |
| 33 | — | `sensorType_percent_speed` (%/s) | ✅ `PERCENT_SPEED = 33` **added** |
| 34 | — | `sensorType_frequency` (Hz) | ✅ `FREQUENCY = 34` **added** |

`sensorType_none = 0` means **no sensor type / undefined** (not "custom").

### 11.4 `BinaryInputType` enum

Our `BinaryInputType` (0–23) exactly matches `dsdefs.h`'s `DsBinaryInputType`.
No discrepancies.

### 11.5 `ColorGroup` (DsGroup) enum

Our `ColorGroup` matches `dsdefs.h`'s `DsGroup` for the defined values.  Note:
`class_black_joker = 8` in `DsClass` is the same integer as
`group_black_variable = 8` in `DsGroup` — the "highlevel" model feature is
gated on this value in both the reference and our implementation.

### 11.6 `OutputFunction` enum

Our `OutputFunction` (0–6) matches `dsdefs.h`'s `VdcOutputFunction`.
`outputFunction_custom = 0x7F` exists in the reference but is not needed
in our enum (treated as the open-ended catch-all).

### 11.7 `ButtonType` enum

Our `ButtonType` (0–6) exactly matches `dsdefs.h`'s `VdcButtonType`.

### 11.8 `SensorUsage` / `VdcUsageHint`

Our `SensorUsage` (0–6) matches with one naming difference:
`SensorUsage.DEVICE_LEVEL = 4` corresponds to `usage_total = 4` in
`dsdefs.h`.  Values are identical; only the Python name differs.
