# dSS Configurator UI Composition — Complete VDC Implementation Guide

Source: `dss-mainline-master` firmware reverse-engineered from `/tmp/dss_src/`

This guide explains **exactly which VDC/VdSD properties control which UI components** in the dSS Configurator (Hardware tab and Activities tab). It is structured as a developer recipe: for each UI element you want to show, you get the required properties and their values.

---

## Table of Contents

1. [How the Configurator Builds the UI](#1-how-the-configurator-builds-the-ui)
2. [Hardware Tab — VDC Entry in "Meters and Controllers"](#2-hardware-tab--vdc-entry-in-meters-and-controllers)
3. [Hardware Tab — Device List by Application Group Color](#3-hardware-tab--device-list-by-application-group-color)
4. [Yellow / GE — Lighting Devices](#4-yellow--ge--lighting-devices)
5. [Grey / GR — Push-Button and Sensor Devices](#5-grey--gr--push-button-and-sensor-devices)
6. [Blue / BL — Heating and Climate Devices](#6-blue--bl--heating-and-climate-devices)
7. [Cyan / TK — Audio Devices](#7-cyan--tk--audio-devices)
8. [Black / SW — Joker Devices](#8-black--sw--joker-devices)
9. [Other Groups](#9-other-groups)
10. [Output Channel UI — Detailed Rules](#10-output-channel-ui--detailed-rules)
11. [Input Configuration UI](#11-input-configuration-ui)
12. [States Properties Events Sensors — Left Panel](#12-states-properties-events-sensors--left-panel)
13. [Activities Tab — Scene Configuration](#13-activities-tab--scene-configuration)
14. [Known VDC Limitations](#14-known-vdc-limitations)
15. [Quick Reference Tables](#15-quick-reference-tables)

---

## 1. How the Configurator Builds the UI

### 1.1 API Call Sequence

The configurator makes these REST calls to construct each panel:

| Call | Endpoint / Method | Purpose |
|---|---|---|
| `GET /json/apartment/getDevices` | — | Initial device list with `functionID`, `modelFeatures`, `binaryInputs`, `sensors`, `outputChannels` |
| `GET /json/apartment/getCircuits` | — | VDC/meter list with `busMemberType`, `VdcConfigURL`, capabilities |
| `GET /json/device/getInfo` | `getInfoStatic` filter | Static descriptions: `spec`, `stateDescriptions`, `eventDescriptions`, `propertyDescriptions`, `sensorDescriptions`, `outputDescriptions`, `actionDescriptions`, `standardActions`, `customActions`, `categories` |
| `GET /json/device/getInfo` | `getInfoOperational` filter | Live values: `channelStates`, `deviceStates`, `deviceProperties`, `sensorStates` |
| `GET /json/device/getOutputChannelSceneValue2` | per scene | Per-channel scene values and `dontCare` flags |
| `GET /json/device/getApartmentScenes` | — | Apartment-level scene actions (VDC devices with `hasActions` only) |

### 1.2 Key Source Files

| File | Role |
|---|---|
| `src/web/handler/jsonhelper.cpp` | `toJSON()` for devices and DSMeters |
| `src/web/handler/devicerequesthandler.cpp` | All `/json/device/*` API methods |
| `src/web/handler/circuitrequesthandler.cpp` | All `/json/circuit/*` API methods |
| `src/device-info.cpp` | Builds `getInfoStatic` / `getInfoOperational` JSON |
| `src/vdc-connection.cpp` | `VdcHelper::getSpec()`, `getVdcSpec()`, `getChannelDesc()`, `getClimateSettings()` |
| `src/backend-vdcs.cpp` | `putVdc()` and `putVdcDevice()` — VDC/device registration |
| `src/model/device.cpp` | `isValveDevice()`, `getDeviceClass()`, `getDeviceType()` |
| `src/model-features.cpp` | Pre-defined model feature sets per device type |
| `src/model/modelconst.h` | Group IDs, Color IDs, BinaryInputType, ModelFeatureId |

---

## 2. Hardware Tab — VDC Entry in "Meters and Controllers"

### 2.1 What Sets VDC Overview Line Fields

The dSS shows one line per registered VDC in the "Meters & Controllers" panel. Fields come from `VdcHelper::getVdcSpec()` — a `getProperty` call using the VDC DSUID as both `_vdsm` and `_device`.

Fields read from VDC and their UI mapping:

```
VDC getProperty response         DSMeter field            Shown in UI
─────────────────────────────────────────────────────────────────────
capabilities.metering          → hasMetering              Energy panel visible
capabilities.identification    → hasBlinking              "Identify" menu item
capabilities.dynamicDefinitions→ hasDynamicDefinitions    Live property queries
modelVersion                   → swVersion                Software version
model                          → hwName                   Hardware model name
hardwareVersion                → hwVersionString          Hardware version
hardwareModelGuid              → VdcHardwareModelGuid     (internal)
implementationId               → VdcImplementationId      (internal)
vendorGuid                     → VdcVendorGuid            (internal)
oemGuid                        → VdcOemGuid               (internal)
oemModelGuid                   → VdcOemModelGuid          (internal)
configURL                      → VdcConfigURL             "Configure" link button
hardwareGuid                   → VdcHardwareGuid          (internal)
modelUID                       → VdcModelUID              (internal)
name                           → DSMeter name             VDC entry name (if empty)
displayId                      → DisplayID                Serial / identifier
```

The resulting `busMemberType` is always **12** (`BusMember_backendVdc`) for all backend VDCs.

### 2.2 "Configure" Link

If `configURL` is non-empty, the configurator shows a "Configure" link that opens in a browser. Use this to link to a web-based VDC configuration page.

### 2.3 Right-Click Menu on VDC Entry

Menu items visible in the configurator right-click context for a VDC:

| Menu Item | Availability | Capability required |
|---|---|---|
| Rename | Always | — |
| Rescan / Reload | Always | — |
| Identify (blink/flash) | `hasBlinking == true` | `capabilities.identification = true` |
| Energy consumption | `hasMetering == true` | `capabilities.metering = true` |
| Configure metering | `hasMetering == true` | `capabilities.metering = true` |
| Firmware update | Always | — |
| Authorize / link account | Always | — |
| Re-register devices | Always | — |
| Remove empty rooms | Always | — |
| Invoke custom method | Always | — |

**Recipe — "Identify" menu item:** Set `capabilities.identification = True` in the VDC hello spec. Implement the `identify` VDC method.

**Recipe — energy metering panel:** Set `capabilities.metering = True`. The VDC must handle `getConsumption` / `getEnergyMeterValue` queries.

---

## 3. Hardware Tab — Device List by Application Group Color

Each device's **display color** in the configurator is determined by `spec.primaryGroup` in the VdSD announcement. This is set in `putVdcDevice()` from `spec.primaryGroup`:

```cpp
modelDevice->addToGroup(spec.primaryGroup);
modelDevice->setActiveGroup(spec.primaryGroup);
```

### 3.1 Group ID to UI Color Mapping

| `primaryGroup` value | Constant | UI color | Application |
|---|---|---|---|
| 0 | GroupIDBroadcast | — | Broadcast |
| **1** | GroupIDYellow | **Yellow** | Lights / dimming |
| **2** | GroupIDGray | **Grey** | Shadow / Blinds / Shading |
| **3** | GroupIDHeating | **Blue** | Heating |
| **4** | GroupIDCyan | **Cyan** | Audio |
| **5** | GroupIDViolet | **Violet** | Video |
| **6** | GroupIDRed | **Red** | Security (deprecated) |
| **7** | GroupIDGreen | **Green** | Access (deprecated) |
| **8** | GroupIDBlack | **Black** | Joker (reassignable) |
| **9** | GroupIDCooling | **Blue** | Cooling |
| **10** | GroupIDVentilation | **Blue** | Ventilation |
| **11** | GroupIDWindow | **Blue** | Window / Shading |
| **12** | GroupIDRecirculation | **Blue** | Recirculation |
| **48** | GroupIDControlTemperature | **Blue** | Temperature set-point |
| **64** | GroupIDApartmentVentilation | **Blue** | Apartment-level ventilation |
| **65** | GroupIDApartmentAwnings | **Grey** | Apartment-level awnings / shading |
| **69** | GroupIDApartmentRecirculation | **Blue** | Apartment-level recirculation |

### 3.2 Device Overview Line Fields (Common to All Groups)

Every device in the list shows these fields (from `jsonhelper.cpp::toJSON(DeviceReference)`):

```
name              ← from spec.name (VdSD property "name")
dSUID             ← from spec.dSUID
DisplayID         ← from spec.displayId (serial number / MAC)
functionID        ← always 0 for VDC devices
productID         ← always 0 for VDC devices
modelFeatures     ← derived feature list
isVdcDevice       ← true
outputMode        ← from OutputMode enum
groups            ← [primaryGroup] + any additional group memberships
buttonInputMode   ← 255 = DEACTIVATED for output-only devices
isPresent         ← true when connected
on                ← current on/off state
VdcConfigURL      ← from spec.configURL  (per-device config link)
VdcHardwareInfo   ← from spec.model
VdcHardwareVersion← from spec.hardwareVersion
hasActions        ← set from OEM EAN database lookup (see §13)
supportedBasicScenes ← bitmask of configurable scenes 0-63
```

> **Note:** `ValveType` only appears in the JSON if `isValveDevice() == true` — which is **never true** for VDC devices (see §14).

---

## 4. Yellow / GE — Lighting Devices

**Set:** `spec.primaryGroup = 1`

### 4.1 Output Variant Selection

| Output variant | `modelFeatures` required | Channels in `channelDescriptions` |
|---|---|---|
| Single brightness slider | `outvalue8` (auto) | BRIGHTNESS (channelType=1) only |
| Dual slider: brightness + CT | `outputchannels` (auto) | BRIGHTNESS (type=1) + COLOR_TEMPERATURE (type=4) |
| Full color picker (RGB wheel) | `outputchannels` (auto) | HUE (type=2) + SATURATION (type=3) |

`outputchannels` is **automatically derived** by `derive_model_features()` when the channel list contains HUE+SATURATION or BRIGHTNESS+COLOR_TEMPERATURE.

### 4.2 "Edit Device Value" Button

The button is visible when `outputchannels` is in `modelFeatures`. It opens a popup that shows:
- Single brightness slider — if only BRIGHTNESS channel
- Dual slider (brightness + CT) — if BRIGHTNESS + COLOR_TEMPERATURE
- Full color picker — if HUE + SATURATION present

**Critical:** All channel states must have `age != null`. If any channel was never applied, the popup silently fails. Always call `confirm_applied()` after `set_value_from_vdsm()` at startup.

### 4.3 Standard Lighting Model Features

| Feature | UI element | How to set |
|---|---|---|
| `transt` | Transition time panel | Auto via `derive_model_features()` |
| `ledauto` | LED mode / auto-detection | Auto via `derive_model_features()` |
| `dontcare` | "Don't care" scene checkbox | Auto via `derive_model_features()` |
| `outvalue8` | 8-bit value slider | Auto via `derive_model_features()` |

---

## 5. Grey / GR — Shadow / Blinds / Shading Devices

**Set:** `spec.primaryGroup = 2`

Grey (Group 2 = `ApplicationType::blinds`) is the **Shadow/Shading** application group in the dS system. Devices in this group appear in the grey color band and show the shading-oriented scene panel. Note: push-button hardware devices (DeviceClass GR) also use grey as a hardware indicator color, but that is a separate concept from `primaryGroup=2`.

### 5.1 Button Input Fields

Button input properties from `toJSON()` drive the input type editor:

| JSON field | Meaning | VDC devices |
|---|---|---|
| `buttonInputMode` | Push-button mode | Set to `DEACTIVATED (255)` by `putVdcDevice()` |
| `buttonInputCount` | Number of button inputs | Set to 0 for VDC |
| `AKMInputProperty` | AKM-specific property | Not used for VDC |
| `buttonActiveGroup` | Group button is assigned to | Set to `primaryGroup` |

For VDC devices, standard "button" functionality is not available. Use **binary inputs** instead.

### 5.2 Binary Inputs

Binary inputs are declared in the VdSD spec (announcement proto) and appear immediately in the device JSON. Each binary input shows a type dropdown and target group selector.

**Announcement fields required:**

```
binaryInputDescriptions:
  "inputName":
    dsIndex:         0           ← 0-based index, must match position
    sensorFunction:  1           ← BinaryInputType enum value
    updateInterval:  0
binaryInputSettings:
  "inputName":
    group:           2           ← target group (which group this input controls)
binaryInputStates:
  "inputName":
    value:           0           ← current state (0=inactive, 1=active)
    error:           0
```

All three arrays (`binaryInputDescriptions`, `binaryInputSettings`, `binaryInputStates`) must have the same IDs in the same order.

**BinaryInputType enum values** (set as `sensorFunction`):

| Value | Name | Typical use |
|---|---|---|
| 0 | AppMode | Application-controlled |
| 1 | Presence | Occupancy detector |
| 2 | RoomBrightness | Daylight sensor |
| 3 | PresenceInDarkness | Presence + darkness |
| 4 | TwilightExternal | External twilight switch |
| 5 | Movement | Motion detector |
| 6 | MovementInDarkness | Motion + darkness |
| 7 | SmokeDetector | Smoke/fire alarm |
| 8 | WindDetector | Wind sensor |
| 9 | RainDetector | Rain sensor |
| 10 | SunRadiation | Solar radiation |
| 11 | RoomThermostat | Temperature threshold |
| 12 | BatteryLow | Battery warning |
| 13 | WindowContact | Window reed contact |
| 14 | DoorContact | Door reed contact |
| 15 | WindowTilt | Tilt sensor |
| 16 | GarageDoorContact | Garage door |
| 17 | SunProtection | Shading trigger |
| 18 | FrostDetector | Frost sensor |
| 19 | HeatingSystem | Heating active indicator |
| 20 | HeatingSystemMode | Heating mode flag |
| 21 | PowerUp | Power-on detection |
| 22 | Malfunction | Fault indicator |
| 23 | Service | Service required |

### 5.3 Sensor Inputs

Sensor inputs are declared via the `sensorDescriptions` VDC property (queried live by the dSS). They appear in the device left panel with current values from `sensorStates`.

**VDC response format (modern v3):**

```
sensorDescriptions:
  "roomTemperature":          ← technical ID
    dsIndex:        0
    sensorType:     65        ← SensorType ID (65 = room temp °C)
    sensorUsage:    0
    min:            -40.0
    max:            85.0
    resolution:     0.1
    updateInterval: 60
```

Current values are pushed via `sensorStates` in `getInfoOperational`.

---

## 6. Blue / BL — Heating and Climate Devices

**Set:** `spec.primaryGroup = 3`

### 6.1 Available UI Elements

| Model feature | UI element shown |
|---|---|
| `heatinggroup` | "Application" dropdown (heating / cooling / ventilation / recirculation) |
| `valvetype` | "Attached terminal device" dropdown (valve type) |
| `heatingoutmode` | Output mode dropdown for heating |
| `pwmvalue` | PWM config panel (*requires `isValveDevice()`* — see §14) |
| `heatingprops` | Heating properties section prerequisite |
| `outvalue8` | Heating output value slider |
| `dontcare` | "Don't care" scene checkbox |

**Set extra features before calling `derive_model_features()`:**

```python
for feat in ["heatinggroup", "heatingoutmode", "heatingprops", "pwmvalue", "valvetype"]:
    vdsd.add_model_feature(feat)
derive_model_features(vdsd, ...)
```

### 6.2 "Edit Climate Device Properties" — Permanently Greyed Out for VDC

This button requires `isValveDevice() == true`. The check:

```cpp
bool Device::isValveDevice() const {
  return (hasOutput() && (
    (!isInternallyControlled() && (getDeviceClass() == DEVICE_CLASS_BL)) ||
    ((getDeviceType() == DEVICE_TYPE_UMR) && (getRevisionID() >= 0x0383)) ||
    ((getDeviceType() == DEVICE_TYPE_UMV) && (getDeviceNumber() == 200)) ||
    ((getDeviceType() == DEVICE_TYPE_ZWS) && (getDeviceNumber() == 205))
  ));
}
```

`getDeviceClass()` uses `m_FunctionID` bits [15:12]. For VDC devices, `m_FunctionID` is always `0` (never set in `putVdcDevice()`). Therefore:

- `getDeviceClass()` → `DEVICE_CLASS_INVALID`
- `isValveDevice()` → always `false`
- `ValveType` → never added to device JSON
- **"Edit climate device properties" → always greyed out for VDC devices**

This is a firmware limitation. Cannot be fixed from the VDC side.

**What still works despite `isValveDevice() == false`:** The `heatinggroup`, `valvetype`, `heatingoutmode`, `heatingprops` model features still show their dropdown UI elements — these are purely feature-driven.

### 6.3 `outputDescription.function` — Internal Use Only

`outputDescription.function` (on the VdSD `outputDescription` property) is read by `VdcHelper::getClimateSettings()` for `activeCoolingMode` but is **not forwarded to the configurator frontend**. It does not directly trigger any UI element. Set `POSITIONAL (2)` for heating valves as required by the API spec.

---

## 7. Cyan / TK — Audio Devices

**Set:** `spec.primaryGroup = 4`

> **Note:** Cyan (Group 4) = `ApplicationType::audio`. Video is a **separate** group: Group 5 = `ApplicationType::video` = **Violet**. See §9 for Violet/video devices.

### 7.1 Output Channels for A/V

Typical channel layout for Cyan devices:

| Channel | ChannelType | dsIndex | Notes |
|---|---|---|---|
| `audioVolume` | AUDIO_VOLUME (5) | **0** | Must be first (primary channel) |
| `powerState` | POWER_STATE (0) | 1 | On/off |
| `videoInputSource` | custom/enum | 2 | Needs `values` for dropdown |
| `videoStation` | custom | 3 | Station/channel number |

**dsIndex=0 must be the primary channel** (`audioVolume` for audio/video devices).

### 7.2 Enum Dropdowns (VIDEO_INPUT_SOURCE and Similar)

For any channel with discrete options, add a `values` sub-element to `channelDescriptions`. The parsing in `device-info.cpp`:

```cpp
for (const auto& value : vdcOutput["values"]) {
    options.push_back({ value.getName(), value.getValueAsString() });
}
// options = { "key": "display_name", ... }
```

So the `values` structure must be:

```
channelDescriptions.videoInputSource:
  dsIndex:     2
  channelType: <VIDEO_INPUT_SOURCE type>
  values:
    "0": "HDMI 1"          ← element name = option key, v_string = display label
    "1": "AV"
    "2": "Component"
```

Result: `outputDescriptions.videoInputSource.options = {"0": "HDMI 1", "1": "AV", "2": "Component"}`

Frontend renders this as a dropdown with the display labels.

### 7.3 Settings Persistence

A/V settings do not persist after power cycle by default. To fix:
1. Set `pushChanges = True` in `outputSettings`
2. On VdSD reconnect/power-on, push current channel states via `pushChannelStateChange`

---

## 8. Black / SW — Joker Devices

**Set:** `spec.primaryGroup = 8`

### 8.1 What is a Joker Device

A joker device has no fixed application group. The configurator shows a group-assignment dropdown allowing the user to reassign the device to any standard application group. The assignment persists in dSS and is communicated back to the VdSD via `setJokerGroup`.

### 8.2 Group Reassignment UI

- The configurator shows an "Application group" selector for black joker devices
- Valid target groups: any `isDefaultGroup()` (1–15) or `isGlobalAppDsGroup()` (64–187)
- API call: `device/setJokerGroup?groupID=<n>`
- After assignment the device adopts the icon color of the target group

### 8.3 Use Case

Use joker devices for generic switches or actuators that the user should be able to assign to any function:

```python
spec.set_primary_group(8)   # GroupIDBlack — joker, user can reassign
```

The VdSD receives `setJokerGroup` via `setProperty` when the user reassigns so it can adapt behavior.

---

## 9. Other Groups

| Group ID | Name | Color | Application |
|---|---|---|---|
| 5 | GroupIDViolet | Violet | Video |
| 6 | GroupIDRed | Red | Security (deprecated) |
| 7 | GroupIDGreen | Green | Access (deprecated) |
| 9 | GroupIDCooling | Blue | Cooling |
| 10 | GroupIDVentilation | Blue | Ventilation |
| 11 | GroupIDWindow | Blue | Window / shading |
| 12 | GroupIDRecirculation | Blue | Recirculation |
| 48 | GroupIDControlTemperature | Blue | Temperature set-point |
| 64 | GroupIDApartmentVentilation | Blue | Apartment-level ventilation |
| 65 | GroupIDApartmentAwnings | Grey | Apartment-level awnings / shading |
| 69 | GroupIDApartmentRecirculation | Blue | Apartment-level recirculation |
| 16–39 | Cluster groups | User-defined | App user groups |

All groups support the standard output channel machinery. Shading/window (Group 11) uses positional channels (types 7 = vertical position, 9 = angle).

---

## 10. Output Channel UI — Detailed Rules

### 10.1 Auto-Derived Model Features from Channel Types

`derive_model_features()` sets model features based on declared output channels:

| Channel combination | Feature added | UI effect |
|---|---|---|
| Any output | `outvalue8`, `transt`, `ledauto`, `dontcare` | Basic slider / transition / LED / scene checkbox |
| BRIGHTNESS (1) + COLOR_TEMPERATURE (4) | `outputchannels` | Dual brightness+CT slider |
| HUE (2) + SATURATION (3) [any order] | `outputchannels` | Full color picker popup |

### 10.2 `outputchannels` Feature — Full Behavior

1. `outputchannels` in `modelFeatures` → "Edit Device Value" button visible
2. Button click → frontend reads `channelStates` via `getInfoOperational`
3. Any channel with `age == null` → popup silently fails (blank popup)
4. Popup renders channels by `outputType` field (= `channelType` from `channelDescriptions`)

**Fix for blank popup:** Call `confirm_applied()` on every channel after `set_value_from_vdsm()`.

### 10.3 `channelDescriptions` Response Structure

```
channelDescriptions:
  "brightness":
    dsIndex:     0         ← required: position
    channelType: 1         ← required: maps to outputType in outputDescriptions
    min:         0.0       ← optional
    max:         100.0
    resolution:  0.1
    values:                ← optional: if present → renders as enum dropdown
      "0": "Off"           ← element name = key, v_string = display label
      "1": "On"
  "colortemp":
    dsIndex:     1
    channelType: 4         ← COLOR_TEMPERATURE: CT slider with BRIGHTNESS present
    min:         2700.0
    max:         6500.0
    resolution:  10.0
```

**channelType values that matter for UI:**

| channelType | Name | UI effect |
|---|---|---|
| 0 | POWER_STATE / UNDEFINED | On/off switch |
| 1 | BRIGHTNESS | Brightness slider |
| 2 | HUE | Color picker (with SAT) |
| 3 | SATURATION | Color picker (with HUE) |
| 4 | COLOR_TEMPERATURE | CT slider (with BRIGHTNESS) |
| 5 | AUDIO_VOLUME | Volume slider |
| 7 | VERTICAL_POSITION | Blind position slider |
| 9 | ANGLE | Blind angle slider |
| 16 | HEATING_POWER | Heating output slider |

### 10.4 Per-Channel Scene Values

The dSS reads and writes per-channel scene values via:
- `getOutputChannelSceneValue2` → queries `scenes.<N>.channels.*` from VdSD
- `setOutputChannelSceneValue2` → writes to `scenes.<N>.channels.*` on VdSD

VdSD must handle `getProperty` and `setProperty` on:
```
scenes:
  "<sceneNum>":
    channels:
      "<channelId>":
        value:    <double>
        dontCare: <bool>
        command:  <string>  ← only for action-type channels
```

### 10.5 `outputDescription.function` — Does Not Affect Frontend UI

This property is read internally for climate settings only. It does **not** control any UI component directly. Set it per API spec for correct heating behavior, but don't expect a UI change.

---

## 11. Input Configuration UI

### 11.1 Binary Inputs

Declared in the VdSD spec announcement (not queried live). All three arrays must be parallel (same IDs, same order, indexed by dsIndex):

```
binaryInputDescriptions:   ← maps id → description
  "inputName":
    dsIndex:        0
    sensorFunction: 1      ← BinaryInputType enum
    updateInterval: 0
binaryInputSettings:        ← maps id → settings
  "inputName":
    group:          2       ← target group for this input
binaryInputStates:          ← maps id → current state
  "inputName":
    value:          0
    error:          0
```

The configurator shows per binary input:
- Input type dropdown (from `inputType` = `sensorFunction` value)
- Target group selector (from `targetGroup` = `binaryInputSettings.group`)

### 11.2 Sensor Inputs

Sensor descriptions are queried live from the VdSD via `sensorDescriptions` property (only if `hasDynamicDefinitions == true`).

**Modern v3 format:**
```
sensorDescriptions:
  "technicalName":            ← ID (element name)
    dsIndex:        0
    sensorType:     65        ← SensorType from ds-api spec §07
    sensorUsage:    0
    min:            -40.0
    max:            85.0
    resolution:     0.1
    updateInterval: 60
```

Current values pushed to dSS via `sensorStates` and displayed in `getInfoOperational.sensors`.

### 11.3 Device States and Properties

**States** — declared in `deviceStateDescriptions`, current value in `deviceStates`:
```
deviceStateDescriptions:
  "powerState":
    value:
      values:
        "on":  true
        "off": true
```

**Properties** — declared in `devicePropertyDescriptions`, current value in `deviceProperties`:
```
devicePropertyDescriptions:
  "targetTemperature":
    type:       "numeric"
    min:        15.0
    max:        30.0
    resolution: 0.5
    siunit:     "°C"
  "fanMode":
    type:   "enumeration"
    values:
      "auto": true
      "low":  true
      "high": true
```

---

## 12. States Properties Events Sensors — Left Panel

In `getInfoStatic`, these JSON sections are built from VDC live queries (if `hasDynamicDefinitions == true`):

| JSON section | VDC property queried | UI location |
|---|---|---|
| `stateDescriptions` | `deviceStateDescriptions` | Left panel: States |
| `propertyDescriptions` | `devicePropertyDescriptions` | Left panel: Properties |
| `eventDescriptions` | `deviceEventDescriptions` | Left panel: Events |
| `sensorDescriptions` | `sensorDescriptions` | Left panel: Sensors |
| `actionDescriptions` | `deviceActionDescriptions` | Left panel: Actions |
| `standardActions` | `standardActions` | Activities tab |
| `customActions` | `customActions` | Activities tab |
| `outputDescriptions` | `channelDescriptions` | Output channel panel |
| `spec` | Various name/model/vendor fields | Hardware info panel |
| `categories` | (database) | Visual grouping |

> **Always set `capabilities.dynamicDefinitions = True`** in the VDC hello spec. Without this, the dSS will not query `deviceStateDescriptions`, `devicePropertyDescriptions`, etc. live from the VdSD, and only database-backed descriptions will be used (requiring a registered OEM GTIN).

### 12.1 Spec Section Fields Shown in Hardware Info Panel

| Spec key | Source field | Displays as |
|---|---|---|
| `name` | `device.getName()` | Device name |
| `model` | `spec.model` | Hardware model |
| `modelVersion` | `spec.modelVersion` | Software version |
| `vendorName` | `spec.vendorName` | Vendor name |
| `vendorId` | `spec.vendorId` | Vendor ID |
| `hardwareGuid` | `spec.hardwareGuid` | Hardware GUID |
| `hardwareModelGuid` | `spec.hardwareModelGuid` | Hardware model GUID |
| `descriptionsGroup` | `spec.descriptionsGroup` | Description group |
| `descriptionsClass` | `spec.descriptionsClass` | Description class |

---

## 13. Activities Tab — Scene Configuration

### 13.1 How the Activities Tab is Populated

For devices **with output** (`hasOutput() && outputMode != 0`):
- Activities tab shows scenes 0–63 (standard) and 64–127 (apartment)
- Per-scene: current channel value and "Don't care" flag per channel
- For VDC devices: values read from VdSD `scenes` property via `getOutputChannelSceneValue2`
- Values written via `setSceneValue` (for simple value) or `setOutputChannelSceneValue2` (per-channel)

### 13.2 `scenes` Property (VdSD-Side)

Implement `scenes` as a readable/writable property tree:

```
scenes:
  "<sceneNum>":
    channels:
      "<channelId>":
        value:    50.0
        dontCare: false
        command:  ""        ← for action-type assignment
```

`getApartmentScenes` reads scenes 64–127 all at once. Requires `isVdcDevice() && hasActions`.

### 13.3 `standardActions` for Apartment Activities

Standard actions become scene presets in the Activities tab:

```
standardActions:
  "std.powerOn":
    title:  "Turn On"        ← display label
    action: "callScene"
    params:
      "sceneID": "5"
```

Names **must** start with `std.` to be recognised as standard actions (vs. legacy descriptions).

### 13.4 `customActions` — User-Defined Actions

Queried via `GET customActions` from VdSD. The user can create/modify/delete custom actions via the configurator. The VdSD must persist them.

### 13.5 `hasActions` Flag

Controls access to `getApartmentScenes` and `setSceneValue(command=...)`. Currently set from the OEM EAN database. For VDC devices without a registered OEM GTIN, `hasActions` is **false**.

Simple scene value configuration (`setSceneValue?value=<n>`) still works without `hasActions`. Only action/command assignment requires it.

### 13.6 `supportedBasicScenes`

Controls which basic scenes (0–63) are configurable in Activities. Default: all. Can be restricted:

```
device/setSupportedBasicScenes?value=[0,5,6,17,18,19,20,21]
```

---

## 14. Known VDC Limitations

### 14.1 `isValveDevice()` Always False

**Impact:** "Edit climate device properties" button permanently greyed out.

**Root cause:** `isValveDevice()` requires `getDeviceClass() == DEVICE_CLASS_BL`, which requires `m_FunctionID` bits [15:12] = 3 (`0x3xxx`). VDC devices always have `m_FunctionID = 0` because `putVdcDevice()` never sets FunctionID.

Path: `putVdcDevice()` → `setVdsdSpec()` only (no `DeviceSpec.FunctionID` is involved). Therefore `getDeviceClass()` → `DEVICE_CLASS_INVALID`.

**What still works:** `heatinggroup`, `valvetype`, `heatingoutmode`, `heatingprops`, `pwmvalue` feature flags still show their dropdown UI elements. Only the "Edit climate device properties" button and `setHeatingGroup` API are blocked.

**Firmware fix required:** Extend `isValveDevice()` to return `true` for VDC devices with `heatingprops` in model features or `primaryGroup == GroupIDHeating`.

### 14.2 `functionID` and `productID` Always Zero

VDC devices always have `functionID=0` and `productID=0` in the JSON. This affects icon selection internally but `modelFeatures` is the primary routing mechanism for UI.

### 14.3 API Calls That Fail for VDC Devices

| API method | Failure condition | Error |
|---|---|---|
| `setHeatingGroup` | `!isValveDevice()` | "Cannot change group for this device" |
| `setValvePwmMode` | `!isValveDevice()` | fails |
| `getValvePwmMode` | `!isValveDevice()` | fails |
| `setValveControlMode` | `!isValveDevice()` | fails |
| `getValveType` | `!isValveDevice()` | fails |
| `setValveType` | `!isValveDevice()` | fails |
| `getApartmentScenes` | `!hasActions` | "Device does not support action configuration" |
| `setSceneValue(command=...)` | `!hasActions` | same |

---

## 15. Quick Reference Tables

### 15.1 VdSD `getProperty` Fields → UI

| VdSD property | Stored as | Shown in UI |
|---|---|---|
| `name` | device name | Device name |
| `displayId` | DisplayID | Serial / identifier |
| `model` | VdcHardwareInfo | Hardware model name |
| `modelVersion` | VdcModelVersion | Firmware version |
| `hardwareVersion` | VdcHardwareVersion | Hardware version |
| `configURL` | VdcConfigURL | "Configure" link |
| `vendorName` | spec.vendorName | Vendor info |
| `vendorId` | spec.vendorId | Vendor ID |
| `descriptionsGroup` | spec.descriptionsGroup | Device group tag |
| `descriptionsClass` | spec.descriptionsClass | Device class tag |
| `modelFeatures.*: true` | modelFeatures[] | All feature-driven UI |

### 15.2 VDC Hello Spec Fields → VDC Entry UI

| VDC property | Shown in UI |
|---|---|
| `name` | VDC entry name |
| `model` | Hardware model |
| `modelVersion` | Software version |
| `configURL` | "Configure" link on VDC entry |
| `capabilities.identification = true` | "Identify" right-click menu item |
| `capabilities.metering = true` | Energy metering panel |
| `capabilities.dynamicDefinitions = true` | Live VdSD property queries |

### 15.3 Model Feature → UI Element

| Model feature | UI element | Auto-derived? |
|---|---|---|
| `dontcare` | "Don't care" scene checkbox | Yes |
| `outvalue8` | 8-bit output value slider | Yes |
| `transt` | Transition time config | Yes |
| `ledauto` | LED mode panel | Yes |
| `outputchannels` | "Edit Device Value" + multi-channel popup | Yes (HUE+SAT or B+CT) |
| `heatinggroup` | Heating application dropdown | Manual (`add_model_feature`) |
| `valvetype` | Attached terminal device dropdown | Manual |
| `heatingoutmode` | Heating output mode dropdown | Manual |
| `heatingprops` | Heating properties section | Manual |
| `pwmvalue` | PWM panel (blocked by `isValveDevice` for VDC) | Manual |

### 15.4 Steering the Configurator UI — Recipe by Desired Outcome

| Desired UI | Required configuration |
|---|---|
| Yellow lighting device | `spec.primaryGroup = 1` |
| Grey push-button / sensor device | `spec.primaryGroup = 2` |
| Blue heating device | `spec.primaryGroup = 3` |
| Cyan A/V device | `spec.primaryGroup = 4` |
| Black joker (user-reassignable) | `spec.primaryGroup = 8` |
| Single brightness slider | BRIGHTNESS channel (type 1) only |
| Dual brightness + CT sliders | BRIGHTNESS (type 1) + COLOR_TEMPERATURE (type 4) |
| Full color picker (RGB wheel) | HUE (type 2) + SATURATION (type 3) |
| Heating application dropdown | `add_model_feature("heatinggroup")` before `derive_model_features()` |
| Heating output mode dropdown | `add_model_feature("heatingoutmode")` |
| Attached terminal device dropdown | `add_model_feature("valvetype")` |
| Enum dropdown for any channel | `values` sub-elements in `channelDescriptions.<channelId>` |
| "Configure" link on VDC entry | `configURL` non-empty in VDC hello spec |
| "Configure" link on device | `configURL` non-empty in VdSD spec |
| "Identify" right-click on VDC | `capabilities.identification = True` |
| Energy metering panel on VDC | `capabilities.metering = True` |
| Live property queries enabled | `capabilities.dynamicDefinitions = True` |
| State dropdown left panel | `deviceStateDescriptions.<id>.value.values.*` |
| Property field left panel | `devicePropertyDescriptions.<id>` with type/range |
| Sensor value display | `sensorDescriptions.<id>` with sensorType/range |
| Binary input with type and group | `binaryInputDescriptions` + `binaryInputSettings` in VdSD spec |
| Scene values persist after power cycle | `pushChanges = True` + push channel states on connect |
| Standard action presets in Activities | `standardActions.<id>` with `std.` name prefix |
| "Edit Device Value" works (not blank) | `confirm_applied()` on all channels at init |
