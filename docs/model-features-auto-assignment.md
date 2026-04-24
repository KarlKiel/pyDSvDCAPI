# modelFeatures Auto-Assignment Rules

> Source: `pyDSvDCAPI` library — `Vdsd.derive_model_features()` in `src/pydsvdcapi/vdsd.py`.
> Firmware reference: `dss-configurator-ui-composition.md`.

---

## Overview

`derive_model_features()` inspects the fully configured `Vdsd` object and adds
`modelFeatures` flags to the announcement based on the declared components.
It runs automatically at announcement time unless you called it explicitly
first (in which case your manual additions/removals are preserved).

The features reach the dSS `ModelFeatures` database via `/apartment/getModelFeatures`
(for classic `BusMember_vDC` devices — the Python library's path). The
configurator frontend reads this database to decide which UI panels to show.

---

## Auto-Derived Features — Rule Reference

### Output / Channel Rules

| Trigger | Features added | Notes |
|---|---|---|
| Any output present | `dontcare`, `ledauto` | Universal for all output devices |
| Any channel with type in {1–12, 14–18, 22–24} | `transt` | Transition/fade support |
| `defaultGroup == 2` (GREY/shades) | `shadeprops` | Shade position UI panel |
| `defaultGroup == 2` + `function == POSITIONAL` | `shadeposition` | Shade travel position slider |
| `defaultGroup == 2` + POSITIONAL + channel 9 or 10 present | `shadebladeang`, `motiontimefins` | Venetian blind slat angle + travel timing |
| `defaultGroup ≠ 2` | `outvalue8` | 8-bit output level (light/generic) |
| Both channel types 2 (HUE) + 3 (SAT) present | `outputchannels` | Full-colour RGB/RGBW UI |
| Both channel types 1 (BRIGHTNESS) + 4 (COLOR_TEMP) present | `outputchannels` | Tunable-white CT slider |
| `function` in {DIMMER(1), DIMMER_COLOR_TEMP(3), FULL_COLOR_DIMMER(4)} | `dimtimeconfig`, `outmodeauto`, `dimmodeconfig`, `customtransitiontime` | Advanced dimmer UI: fade-time config, auto-off, dim-mode, per-scene transition time |
| `defaultGroup` in {3, 9, 10, 12, 48} (heating/climate) + `function == ON_OFF` | `heatingoutmode`, `pwmvalue` | Heating valve: PWM mode selector + output mode |
| Channel type 16 (HEATING_POWER) present | `heatingoutmode`, `pwmvalue` | Continuous heating power control (e.g. PWM valve) |
| Any ventilation channel (types 12, 13, 14, 15, 20, 21) present | `ventconfig` | Ventilation speed/flap configuration UI |

### Sensor Rules

| Trigger | Features added | Notes |
|---|---|---|
| Any sensor type in {14, 15, 16, 17} (ACTIVE_POWER, ELECTRIC_CURRENT, ENERGY_METER, APPARENT_POWER) | `consumption` | Energy monitoring UI panel |
| Sensor type 14 (ACTIVE_POWER) | `consumptioneventled` | LED event indicator for consumption threshold |
| Sensor type 16 (ENERGY_METER) | `consumptiontimer` | Consumption timer / run-time UI |
| Sensor type 1 (TEMPERATURE) + `primaryGroup` in {3 (BLUE_CLIMATE), 48 (BLUE_TEMPERATURE_CONTROL)} | `temperatureoffset` | Room temperature offset adjustment UI |

### Binary Input Rules

| Trigger | Features added | Notes |
|---|---|---|
| Any binary input with `group == 8` | `akmsensor`, `akminput`, `akmdelay` | AKM-style terminal block input: sensor function, input mode, delay config |

### Button Rules

| Trigger | Features added | Notes |
|---|---|---|
| Any button present | `pushbutton`, `pushbadvanced` | Base button UI + advanced click-type config |
| Button with `group ≠ 8` | `pushbarea` | Area-scene assignment UI |
| Button with `group ≠ 8` + `supports_local_key_mode == True` | `pushbdevice` | Device-mode assignment UI |
| Button with `group == 8` | `pushbsensor`, `highlevel` | Sensor-mode button + high-level event UI |
| Button with `button_type` in {2, 3, 4, 5} (multi-contact) | `pushbcombined` | Combined up/down/center button assignment UI |
| Any button with `ds_index ≥ 1` | `twowayconfig` | Two-way push-button pairing UI |

### Primary-Group Rules

| Trigger | Features added | Notes |
|---|---|---|
| `primaryGroup == 3` (BLUE_CLIMATE) | `heatingprops`, `heatinggroup` | Heating properties panel + group assignment |
| `primaryGroup == 3` + output present | `valvetype`, `extendedvalvetypes` | Valve type selector + extended valve type options |
| `primaryGroup` in {10, 12, 64, 69} (BLUE_VENTILATION, BLUE_RECIRCULATION, APARTMENT_VENTILATION, APARTMENT_RECIRCULATION) + output present | `fcu`, `ventconfig` | Fan coil unit UI + ventilation config |
| `primaryGroup == 2` (GREY) + output present | `locationconfig` | Location-based wind/sun protection |
| `primaryGroup == 2` + output + channel type 9 or 10 present | `windprotectionconfigblind` | Wind protection for jalousie/blind |
| `primaryGroup == 2` + output + no channel 9/10 | `windprotectionconfigawning` | Wind protection for awning/roller blind |
| `primaryGroup == 8` (BLACK/Joker) | `jokerconfig`, `highlevel` | Joker configuration UI + high-level mode |

### Identification Rule

| Trigger | Features added | Notes |
|---|---|---|
| `on_identify` callback registered | `blink`, `identification`, `blinkconfig` | LED blink on identify + blink configuration UI |

---

## Features That Require Manual Addition

The following features are **never auto-derived** because they depend on
device-specific capabilities that cannot be inferred from the component
configuration alone. Add them with `add_model_feature("featurename")` after
constructing the device.

| Feature | When to use |
|---|---|
| `outmode` | Device supports multiple output operating modes (Yellow/GE dimmer or switch with selectable mode). Most light switches and dimmers have this. |
| `outmodeswitch` | Variant of `outmode` specifically for switch-mode capable dimmers. Add alongside `outmode` for dual-mode (dim+switch) devices. |
| `outmodegeneric` | Generic device with selectable output mode (Joker/Black devices). |
| `outmodetempcontrol` | Device supports temperature-controlled output mode (e.g. UMR200 with thermostat). |
| `leddark` | Device has a "dark LED" (no indicator light) mode. Physical button panels with configurable LED brightness. |
| `extradimmer` | Device has an additional external dimmer output or supports parallel dimmer pairing (UMV relay + dimmer). |
| `umvrelay` | Device has a relay channel as part of a UMV combination. |
| `umroutmode` | UMR200-style device with special output mode selector. |
| `impulseconfig` | Device supports impulse-mode scene configuration (brief output pulse instead of sustained on/off). |
| `outconfigswitch` | Device supports switch-output configuration UI (separate from `outmode`). |
| `jokertempcontrol` | Joker/Black device with integrated temperature-controlled output. |
| `ftwtempcontrolventilationselect` | Display panel (FTW/SK204 style) with combined temperature control and ventilation mode selector. Very hardware-specific. |
| `ftwdisplaysettings` | Display panel with display settings UI (brightness, contrast, etc.). Very hardware-specific. |
| `ftwbacklighttimeout` | Display panel with configurable backlight timeout. Very hardware-specific. |
| `customactivityconfig` | Custom activity/app configuration UI. Requires explicit activity definition. |
| `pushbdisabled` | Device has a physically disabled push-button (button is present but locked out). |

---

## Features That Must NOT Be Set

The following features are **injected by the dSS firmware** for physical hardware
devices. Setting them from a VDC device has no effect and may cause confusion.
Never use `add_model_feature()` with these names.

| Feature | Firmware condition |
|---|---|
| `outmodeenoceanvalve` | Added by `busscanner.cpp` for EnOcean valve devices specifically |
| `apartmentapplication` | Set by `updateModelFeatures()` when `FunctionID` subclass bits[6–8] ∈ {0x07, 0x08, 0x09} |
| `setumr200config` | Set by `updateModelFeatures()` for UMR200 hardware revision ≥ 0x0370 |
| `operationlock` | Set by `updateModelFeatures()` for KL hardware revision ≥ 0x365 |
| `grkl387workaround` | Set by `updateModelFeatures()` for specific KL 0x387 hardware workaround |

---

## Features With No Known Configurator Effect

The following features are defined in the firmware enum but have no documented
UI effect in the current configurator, or are only used for internal dSS-to-dSM
communication. They are present in the complete feature list for completeness.

| Feature | Notes |
|---|---|
| `highlevel` | Controls "high-level event" routing. Auto-derived for group-8 buttons and Joker devices. |
| `heatingprops` | Shows heating-specific property UI for Blue/climate devices. Auto-derived. |
| `heatinggroup` | Allows heating group assignment. Auto-derived for Blue/climate. |

---

## Recommended Feature Sets by Device Type

These examples combine auto-derived and manually-added features for common
virtual device types.

### Yellow — Dimmable Light

```python
device = Vdsd(primary_group=ColorClass.YELLOW, ...)
output = Output(default_group=1, function=OutputFunction.DIMMER)
device.set_output(output)
# Auto-derived: dontcare, ledauto, transt, outvalue8,
#               dimtimeconfig, outmodeauto, dimmodeconfig, customtransitiontime
# Add manually for a switch/dimmer combo:
device.add_model_feature("outmode")
device.add_model_feature("outmodeswitch")
```

### Yellow — RGB Full-Colour Light

```python
device = Vdsd(primary_group=ColorClass.YELLOW, ...)
output = Output(default_group=1, function=OutputFunction.FULL_COLOR_DIMMER)
# channels brightness, hue, sat, colortemp added automatically by Output
# Auto-derived: dontcare, ledauto, transt, outvalue8, outputchannels,
#               dimtimeconfig, outmodeauto, dimmodeconfig, customtransitiontime
```

### Grey — Jalousie / Venetian Blind

```python
device = Vdsd(primary_group=ColorClass.GREY, ...)
output = Output(default_group=2, function=OutputFunction.POSITIONAL)
output.add_channel(OutputChannel(channel_type=OutputChannelType.SHADE_POSITION_OUTSIDE, ...))
output.add_channel(OutputChannel(channel_type=OutputChannelType.SHADE_OPENING_ANGLE_OUTSIDE, ...))
# Auto-derived: dontcare, ledauto, shadeprops, shadeposition, shadebladeang,
#               motiontimefins, locationconfig, windprotectionconfigblind
```

### Grey — Roller Blind / Awning

```python
device = Vdsd(primary_group=ColorClass.GREY, ...)
output = Output(default_group=2, function=OutputFunction.POSITIONAL)
output.add_channel(OutputChannel(channel_type=OutputChannelType.SHADE_POSITION_OUTSIDE, ...))
# No slat channel → awning path
# Auto-derived: dontcare, ledauto, shadeprops, shadeposition,
#               locationconfig, windprotectionconfigawning
```

### Blue — Heating Valve (ON/OFF)

```python
device = Vdsd(primary_group=ColorClass.BLUE_CLIMATE, ...)
output = Output(default_group=3, function=OutputFunction.ON_OFF)
# Auto-derived: dontcare, ledauto, outvalue8, heatingoutmode, pwmvalue,
#               heatingprops, heatinggroup, valvetype, extendedvalvetypes
```

### Blue — Heating Valve (PWM / Continuous)

```python
device = Vdsd(primary_group=ColorClass.BLUE_CLIMATE, ...)
output = Output(default_group=3, function=OutputFunction.POSITIONAL)
output.add_channel(OutputChannel(channel_type=OutputChannelType.HEATING_POWER, ...))
# Auto-derived: dontcare, ledauto, transt, outvalue8, heatingoutmode, pwmvalue,
#               heatingprops, heatinggroup, valvetype, extendedvalvetypes
```

### Blue — Room Temperature Controller (thermostat with sensor)

```python
device = Vdsd(primary_group=ColorClass.BLUE_CLIMATE, ...)
# Temperature sensor declared:
device.add_sensor_input(SensorInput(sensor_type=SensorType.TEMPERATURE, ...))
# Auto-derived: heatingprops, heatinggroup, temperatureoffset
# Add manually for display panel features:
device.add_model_feature("ftwtempcontrolventilationselect")
device.add_model_feature("ftwdisplaysettings")
device.add_model_feature("ftwbacklighttimeout")
```

### Blue — Ventilation / Fan Coil Unit

```python
device = Vdsd(primary_group=ColorClass.BLUE_RECIRCULATION, ...)
output = Output(default_group=12, function=OutputFunction.POSITIONAL)
output.add_channel(OutputChannel(channel_type=OutputChannelType.AIR_FLOW_INTENSITY, ...))
# Auto-derived: dontcare, ledauto, transt, outvalue8, ventconfig, fcu
```

### Black — Joker with Power Meter

```python
device = Vdsd(primary_group=ColorClass.BLACK, ...)
output = Output(default_group=8, function=OutputFunction.ON_OFF)
device.add_sensor_input(SensorInput(sensor_type=SensorType.ACTIVE_POWER, ...))
device.add_sensor_input(SensorInput(sensor_type=SensorType.ENERGY_METER, ...))
# Auto-derived: dontcare, ledauto, outvalue8, consumption,
#               consumptioneventled, consumptiontimer, jokerconfig, highlevel
# Add manually if output mode selection is needed:
device.add_model_feature("outmodegeneric")
```

---

## How Auto-Derivation Interacts with Manual Configuration

```
construct Vdsd + add components
        │
        │   option A: implicit derivation
        ▼
announce()
  └─→ derive_model_features() runs automatically
  └─→ announce sends {derived features}

        │   option B: explicit control
        ▼
derive_model_features()          ← derive from current config
add_model_feature("outmode")     ← add extras
remove_model_feature("ventconfig") ← remove unwanted
        │
        ▼
announce()                       ← uses the modified set; does NOT re-derive
```

Once `derive_model_features()` has been called (explicitly or via
`remove_model_feature()`), the `_features_derived` flag is set and
`announce()` skips automatic derivation. This lets you freely adjust the
derived set before announcement.
