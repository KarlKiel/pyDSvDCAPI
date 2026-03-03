#!/usr/bin/env python3
"""Multi-variant experiment — which approach creates states/StatusXxx in dSS?

This script creates **5 separate vdSD sub-devices**, each using a
DIFFERENT approach for announcing state information.  After all devices
are announced and the dSS has had time to register them, the script
queries the dSS REST API to check which device(s) have ``states/``
entries in the internal property tree.

Variants
--------

**Device A – Pure §4.6 deviceStates (current API approach)**
    Uses ``deviceStateDescriptions`` + ``deviceStates`` with names like
    ``operatingState``, ``connectivity``.

**Device B – §4.6 deviceStates with Sonos-style "StatusXxx" naming**
    Same mechanism as Device A, but names match the Sonos convention:
    ``StatusOperationMode``, ``StatusMute``, etc.

**Device C – Standard binaryInputs only**
    Uses ``binaryInputDescriptions`` / ``binaryInputSettings`` /
    ``binaryInputStates`` with a PRESENCE and MALFUNCTION sensor types.
    No deviceStates at all.

**Device D – Standard sensorInputs only**
    Uses ``sensorDescriptions`` / ``sensorSettings`` / ``sensorStates``
    with TEMPERATURE and HUMIDITY sensors.  No deviceStates at all.

**Device E – Combined: §4.6 deviceStates + binaryInputs + sensorInputs**
    Uses ALL approaches simultaneously on one device.

After announcing, the script:
1. Waits for dSS connection + 15s for registration.
2. Queries the dSS REST API for each device's property tree.
3. Prints a comparison table showing which approaches created
   ``states/`` entries, ``deviceStates`` entries, etc.
4. Waits for user confirmation, then vanishes all devices.

Usage::

    python examples/experiment_state_approaches.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from pyDSvDCAPI import (
    BinaryInput,
    BinaryInputType,
    BinaryInputUsage,
    ColorGroup,
    Device,
    DeviceEvent,
    DsUid,
    DsUidNamespace,
    Output,
    OutputFunction,
    OutputUsage,
    SensorInput,
    SensorType,
    SensorUsage,
    Vdc,
    VdcCapabilities,
    VdcHost,
    Vdsd,
)
from pyDSvDCAPI.device_property import (
    PROPERTY_TYPE_NUMERIC,
    PROPERTY_TYPE_STRING,
    DeviceProperty,
)
from pyDSvDCAPI.device_state import DeviceState

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

STATE_FILE = Path("/tmp/pyDSvDCAPI_experiment_state.yaml")
PORT = 8444
DSS_HOST = "10.42.10.10"
DSS_PORT = 8080
APP_TOKEN = "23fa753a71fff5c73d75401e525db26a183abbb154d1da07021bee399329222f"

MODEL_NAME = "pyDSvDCAPI State Experiment"
HOST_NAME = "state-experiment-host"
VENDOR = "pyDSvDCAPI"
VDC_IMPLEMENTATION_ID = "x-pyDSvDCAPI-experiment"
VDC_NAME = "State Experiment vDC"
VDC_MODEL = "pyDSvDCAPI-experiment-vdc"

CONNECT_TIMEOUT = 120
# Extra wait after announcement for dSS to fully register devices.
REGISTRATION_WAIT = 20

# ---------------------------------------------------------------------------
# ANSI colour helpers
# ---------------------------------------------------------------------------

RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
GREY = "\033[90m"


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

class ColourFormatter(logging.Formatter):
    LEVEL_COLOURS = {
        logging.DEBUG: GREY,
        logging.INFO: "",
        logging.WARNING: YELLOW,
        logging.ERROR: RED,
        logging.CRITICAL: RED + BOLD,
    }

    def format(self, record: logging.LogRecord) -> str:
        colour = self.LEVEL_COLOURS.get(record.levelno, "")
        ts = self.formatTime(record, "%H:%M:%S")
        msg = record.getMessage()
        return f"{GREY}{ts}{RESET} {colour}{msg}{RESET}"


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ColourFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)


# ---------------------------------------------------------------------------
# dSS REST API helpers
# ---------------------------------------------------------------------------

_ssl_ctx: Optional[ssl.SSLContext] = None


def _get_ssl_ctx() -> ssl.SSLContext:
    global _ssl_ctx
    if _ssl_ctx is None:
        _ssl_ctx = ssl.create_default_context()
        _ssl_ctx.check_hostname = False
        _ssl_ctx.verify_mode = ssl.CERT_NONE
    return _ssl_ctx


def dss_request(path: str, session_token: str) -> Any:
    """Make a GET request to the dSS JSON REST API."""
    url = f"https://{DSS_HOST}:{DSS_PORT}/json{path}"
    if "?" in url:
        url += f"&token={session_token}"
    else:
        url += f"?token={session_token}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10, context=_get_ssl_ctx()) as resp:
        return json.loads(resp.read().decode())


def get_session_token() -> str:
    """Obtain a dSS session token via the application token."""
    data = dss_request(
        f"/system/loginApplication?loginToken={APP_TOKEN}", ""
    )
    # loginApplication returns token at top level for app tokens
    token = data.get("result", {}).get("token", "")
    if not token:
        raise RuntimeError(f"Failed to get session token: {data}")
    return token


def query_device_property(
    session_token: str, dsuid: str, prop_path: str,
) -> Any:
    """Query a device property from the dSS REST API.

    Returns the parsed JSON 'result' dict, or None on error.
    """
    try:
        data = dss_request(
            f"/property/query2?query=/apartment/zones/*(ZoneID=0)"
            f"/devices/*(dSUID={dsuid})/{prop_path}",
            session_token,
        )
        return data.get("result")
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

async def on_message(msg) -> None:
    logger = logging.getLogger("on_message")
    logger.info("%sRX%s  type=%s  msg_id=%s", CYAN, RESET, msg.type, msg.message_id)


async def on_channel_applied(output: Output, updates: dict) -> None:
    logger = logging.getLogger("hw_apply")
    parts = [f"{ch.name}={v:.1f}" for ch, v in updates.items()]
    logger.info("%sAPPLY%s  [%s] %s", GREEN, RESET, output.name, ", ".join(parts))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def wait_for_session(host: VdcHost, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while host.session is None or not host.session.is_active:
        if time.monotonic() > deadline:
            raise TimeoutError(f"No vdSM/dSS connected within {timeout:.0f}s")
        await asyncio.sleep(0.5)
    logging.getLogger("wait").info("Session established with vdSM!")


async def wait_for_user(prompt: str = "Press Enter to continue...") -> None:
    loop = asyncio.get_running_loop()
    print(f"\n{YELLOW}{prompt}{RESET}")
    await loop.run_in_executor(None, sys.stdin.readline)


def banner(text: str) -> None:
    sep = "=" * max(len(text) + 4, 70)
    print(f"\n{BOLD}{GREEN}{sep}{RESET}")
    print(f"{BOLD}{GREEN}  {text}{RESET}")
    print(f"{BOLD}{GREEN}{sep}{RESET}\n")


def section(text: str) -> None:
    print(f"\n{BOLD}{CYAN}--- {text} ---{RESET}\n")


# ---------------------------------------------------------------------------
# Device factory functions
# ---------------------------------------------------------------------------

def make_device_a(device: Device) -> Vdsd:
    """Device A — pure §4.6 deviceStates with normal naming."""
    vdsd = Vdsd(
        device=device,
        subdevice_index=0,
        primary_group=ColorGroup.CYAN,
        name="[A] API deviceStates",
        model="experiment-variant-a",
        model_features={"identification"},
    )
    output = Output(
        vdsd=vdsd,
        function=OutputFunction.DIMMER,
        output_usage=OutputUsage.ROOM,
        name="A Status LED",
        default_group=int(ColorGroup.CYAN),
        variable_ramp=False,
        max_power=2.0,
        push_changes=True,
        groups={int(ColorGroup.CYAN)},
    )
    output.on_channel_applied = on_channel_applied
    vdsd.set_output(output)

    # §4.6 deviceStates with normal names
    st1 = DeviceState(
        vdsd=vdsd, ds_index=0,
        name="operatingState",
        options={0: "Off", 1: "Initializing", 2: "Running", 3: "Error"},
        description="Operating state (normal API naming)",
    )
    st2 = DeviceState(
        vdsd=vdsd, ds_index=1,
        name="connectivity",
        options={0: "Offline", 1: "Online", 2: "Degraded"},
        description="Connectivity status (normal API naming)",
    )
    vdsd.add_device_state(st1)
    vdsd.add_device_state(st2)
    return vdsd


def make_device_b(device: Device) -> Vdsd:
    """Device B — §4.6 deviceStates with Sonos-style "StatusXxx" naming."""
    vdsd = Vdsd(
        device=device,
        subdevice_index=1,
        primary_group=ColorGroup.CYAN,
        name="[B] Sonos-style StatusXxx",
        model="experiment-variant-b",
        model_features={"identification"},
    )
    output = Output(
        vdsd=vdsd,
        function=OutputFunction.DIMMER,
        output_usage=OutputUsage.ROOM,
        name="B Status LED",
        default_group=int(ColorGroup.CYAN),
        variable_ramp=False,
        max_power=2.0,
        push_changes=True,
        groups={int(ColorGroup.CYAN)},
    )
    output.on_channel_applied = on_channel_applied
    vdsd.set_output(output)

    # §4.6 deviceStates with Sonos-style naming
    st1 = DeviceState(
        vdsd=vdsd, ds_index=0,
        name="StatusOperationMode",
        options={0: "Unknown", 1: "Standby", 2: "Playing", 3: "Paused"},
        description="Operation mode status (Sonos-style naming)",
    )
    st2 = DeviceState(
        vdsd=vdsd, ds_index=1,
        name="StatusMute",
        options={0: "Unmuted", 1: "Muted"},
        description="Mute status (Sonos-style naming)",
    )
    st3 = DeviceState(
        vdsd=vdsd, ds_index=2,
        name="StatusInputMode",
        options={0: "Default", 1: "AUX", 2: "Bluetooth", 3: "Streaming"},
        description="Input mode (Sonos-style naming)",
    )
    vdsd.add_device_state(st1)
    vdsd.add_device_state(st2)
    vdsd.add_device_state(st3)
    return vdsd


def make_device_c(device: Device) -> Vdsd:
    """Device C — binaryInputs only (no deviceStates)."""
    vdsd = Vdsd(
        device=device,
        subdevice_index=2,
        primary_group=ColorGroup.BLACK,
        name="[C] BinaryInputs only",
        model="experiment-variant-c",
        model_features={"identification"},
    )
    # No output for this one — pure sensor device.

    bi1 = BinaryInput(
        vdsd=vdsd,
        ds_index=0,
        sensor_function=BinaryInputType.PRESENCE,
        input_usage=BinaryInputUsage.ROOM_CLIMATE,
        name="Presence Sensor",
    )
    bi2 = BinaryInput(
        vdsd=vdsd,
        ds_index=1,
        sensor_function=BinaryInputType.MALFUNCTION,
        input_usage=BinaryInputUsage.UNDEFINED,
        name="Malfunction Indicator",
    )
    bi3 = BinaryInput(
        vdsd=vdsd,
        ds_index=2,
        sensor_function=BinaryInputType.SERVICE,
        input_usage=BinaryInputUsage.UNDEFINED,
        name="Service Required",
    )
    vdsd.add_binary_input(bi1)
    vdsd.add_binary_input(bi2)
    vdsd.add_binary_input(bi3)
    return vdsd


def make_device_d(device: Device) -> Vdsd:
    """Device D — sensorInputs only (no deviceStates)."""
    vdsd = Vdsd(
        device=device,
        subdevice_index=3,
        primary_group=ColorGroup.CYAN,
        name="[D] SensorInputs only",
        model="experiment-variant-d",
        model_features={"identification"},
    )
    # No output.

    si1 = SensorInput(
        vdsd=vdsd,
        ds_index=0,
        sensor_type=SensorType.TEMPERATURE,
        sensor_usage=SensorUsage.ROOM,
        name="Room Temperature",
        min_value=-20.0,
        max_value=60.0,
        resolution=0.1,
    )
    si2 = SensorInput(
        vdsd=vdsd,
        ds_index=1,
        sensor_type=SensorType.HUMIDITY,
        sensor_usage=SensorUsage.ROOM,
        name="Room Humidity",
        min_value=0.0,
        max_value=100.0,
        resolution=1.0,
    )
    vdsd.add_sensor_input(si1)
    vdsd.add_sensor_input(si2)
    return vdsd


def make_device_e(device: Device) -> Vdsd:
    """Device E — combined: deviceStates + binaryInputs + sensorInputs."""
    vdsd = Vdsd(
        device=device,
        subdevice_index=4,
        primary_group=ColorGroup.CYAN,
        name="[E] Combined all approaches",
        model="experiment-variant-e",
        model_features={"identification"},
    )
    output = Output(
        vdsd=vdsd,
        function=OutputFunction.DIMMER,
        output_usage=OutputUsage.ROOM,
        name="E Status LED",
        default_group=int(ColorGroup.CYAN),
        variable_ramp=False,
        max_power=2.0,
        push_changes=True,
        groups={int(ColorGroup.CYAN)},
    )
    output.on_channel_applied = on_channel_applied
    vdsd.set_output(output)

    # §4.6 deviceStates (Sonos-style naming)
    st1 = DeviceState(
        vdsd=vdsd, ds_index=0,
        name="StatusOperationMode",
        options={0: "Off", 1: "Active", 2: "Error"},
        description="Combined device operation mode",
    )
    vdsd.add_device_state(st1)

    # Binary input
    bi1 = BinaryInput(
        vdsd=vdsd,
        ds_index=0,
        sensor_function=BinaryInputType.PRESENCE,
        input_usage=BinaryInputUsage.ROOM_CLIMATE,
        name="Presence Sensor",
    )
    vdsd.add_binary_input(bi1)

    # Sensor input
    si1 = SensorInput(
        vdsd=vdsd,
        ds_index=0,
        sensor_type=SensorType.TEMPERATURE,
        sensor_usage=SensorUsage.ROOM,
        name="Room Temperature",
        min_value=-20.0,
        max_value=60.0,
        resolution=0.1,
    )
    vdsd.add_sensor_input(si1)

    # Device property (for completeness)
    prop1 = DeviceProperty(
        vdsd=vdsd, ds_index=0,
        name="firmwareVersion",
        type=PROPERTY_TYPE_STRING,
        default="1.0.0",
        description="Firmware version",
    )
    vdsd.add_device_property(prop1)

    # Device event (for completeness)
    evt1 = DeviceEvent(
        vdsd=vdsd, ds_index=0,
        name="tamperAlarm",
        description="Case tamper detected",
    )
    vdsd.add_device_event(evt1)

    return vdsd


# ---------------------------------------------------------------------------
# REST API query & result display
# ---------------------------------------------------------------------------

def query_all_devices(
    token: str,
    devices: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Query the dSS REST API for each device's property tree.

    Parameters
    ----------
    token : session token
    devices : dict mapping variant label ("A".."E") to
              {"dsuid": str, "vdsd": Vdsd, "description": str}

    Returns
    -------
    dict mapping variant label to query results dict.
    """
    results: Dict[str, Dict[str, Any]] = {}
    logger = logging.getLogger("rest")

    for label, info in sorted(devices.items()):
        dsuid = info["dsuid"]
        desc = info["description"]
        logger.info(f"Querying Device {label} ({desc}) — dSUID: {dsuid}")

        result: Dict[str, Any] = {"dsuid": dsuid, "description": desc}

        # 1. Query states/* (the Sonos-style internal states)
        states_raw = query_device_property(token, dsuid, "states/*(*)/*(*)")
        result["states_raw"] = states_raw

        # 2. Query deviceStates (the §4.6 API property)
        device_states = query_device_property(token, dsuid, "deviceStates/*(*)/*(*)")
        result["deviceStates_raw"] = device_states

        # 3. Query deviceStateDescriptions
        state_descs = query_device_property(token, dsuid, "deviceStateDescriptions/*(*)/*(*)")
        result["deviceStateDescriptions_raw"] = state_descs

        # 4. Query binaryInputDescriptions
        bi_descs = query_device_property(token, dsuid, "binaryInputDescriptions/*(*)/*(*)")
        result["binaryInputDescriptions_raw"] = bi_descs

        # 5. Query binaryInputStates
        bi_states = query_device_property(token, dsuid, "binaryInputStates/*(*)/*(*)")
        result["binaryInputStates_raw"] = bi_states

        # 6. Query sensorDescriptions
        sensor_descs = query_device_property(token, dsuid, "sensorDescriptions/*(*)/*(*)")
        result["sensorDescriptions_raw"] = sensor_descs

        # 7. Query sensorStates
        sensor_states = query_device_property(token, dsuid, "sensorStates/*(*)/*(*)")
        result["sensorStates_raw"] = sensor_states

        # 8. Query devicePropertyDescriptions
        prop_descs = query_device_property(token, dsuid, "devicePropertyDescriptions/*(*)/*(*)")
        result["devicePropertyDescriptions_raw"] = prop_descs

        # 9. Query deviceProperties
        device_props = query_device_property(token, dsuid, "deviceProperties/*(*)/*(*)")
        result["deviceProperties_raw"] = device_props

        # 10. Query deviceEventDescriptions
        event_descs = query_device_property(token, dsuid, "deviceEventDescriptions/*(*)/*(*)")
        result["deviceEventDescriptions_raw"] = event_descs

        # 11. Query the full top-level property names (shallow)
        top_level = query_device_property(token, dsuid, "*")
        result["top_level"] = top_level

        results[label] = result

    return results


def _count_entries(raw: Any) -> int:
    """Count entries in a REST API response."""
    if raw is None:
        return 0
    if isinstance(raw, dict):
        if "error" in raw:
            return -1
        # The query2 structure nests results
        # Count non-trivially
        return _deep_count(raw)
    return 0


def _deep_count(obj: Any, depth: int = 0) -> int:
    """Count leaf-level property groups in a nested result."""
    if not isinstance(obj, dict):
        return 0 if obj is None else 1
    # Each key at the appropriate depth is one entry
    count = 0
    for v in obj.values():
        if isinstance(v, dict):
            count += _deep_count(v, depth + 1)
        elif isinstance(v, list):
            count += len(v)
        elif v is not None:
            count += 1
    return max(count, len(obj))


def print_results_table(results: Dict[str, Dict[str, Any]]) -> None:
    """Print a formatted comparison table of REST API results."""
    print()
    banner("RESULTS — dSS REST API property tree comparison")

    # Property categories to check
    categories = [
        ("states/*", "states_raw"),
        ("deviceStates", "deviceStates_raw"),
        ("deviceStateDescs", "deviceStateDescriptions_raw"),
        ("binaryInputDescs", "binaryInputDescriptions_raw"),
        ("binaryInputStates", "binaryInputStates_raw"),
        ("sensorDescs", "sensorDescriptions_raw"),
        ("sensorStates", "sensorStates_raw"),
        ("devicePropDescs", "devicePropertyDescriptions_raw"),
        ("deviceProperties", "deviceProperties_raw"),
        ("eventDescs", "deviceEventDescriptions_raw"),
    ]

    # Header
    hdr = f"{'Property':>22s}"
    for label in sorted(results.keys()):
        desc_short = results[label]["description"][:20]
        hdr += f" | {label}: {desc_short:>20s}"
    print(hdr)
    print("-" * len(hdr))

    # Rows
    for cat_name, cat_key in categories:
        row = f"{cat_name:>22s}"
        for label in sorted(results.keys()):
            raw = results[label].get(cat_key)
            if raw is None:
                cell = "—"
            elif isinstance(raw, dict) and "error" in raw:
                cell = "ERR"
            else:
                # Dump raw for visual inspection
                s = json.dumps(raw, indent=None, default=str)
                if len(s) > 20:
                    cell = s[:18] + ".."
                elif s in ("null", "{}", "[]", "0"):
                    cell = "empty"
                else:
                    cell = s
            row += f" | {cell:>24s}"
        print(row)

    print()

    # Detailed dump for each device
    for label in sorted(results.keys()):
        r = results[label]
        section(f"Device {label} — {r['description']} — dSUID: {r['dsuid']}")

        for cat_name, cat_key in categories:
            raw = r.get(cat_key)
            if raw is None:
                print(f"  {cat_name}: (None)")
            elif isinstance(raw, dict) and "error" in raw:
                print(f"  {cat_name}: ERROR — {raw['error']}")
            else:
                formatted = json.dumps(raw, indent=2, default=str)
                # Truncate very long output
                lines = formatted.split("\n")
                if len(lines) > 30:
                    formatted = "\n".join(lines[:30]) + f"\n  ... ({len(lines)-30} more lines)"
                print(f"  {cat_name}:")
                for line in formatted.split("\n"):
                    print(f"    {line}")
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    setup_logging()
    logger = logging.getLogger("experiment")

    banner("Multi-variant State Experiment")
    logger.info("This script tests 5 different approaches for announcing")
    logger.info("device states to see which one(s) create states/StatusXxx")
    logger.info("entries in the dSS internal property tree.")
    print()

    # ---- Cleanup from previous runs ----------------------------------
    if STATE_FILE.exists():
        STATE_FILE.unlink()
        logger.info("Removed leftover state file %s", STATE_FILE)
    bak = STATE_FILE.with_suffix(STATE_FILE.suffix + ".bak")
    if bak.exists():
        bak.unlink()

    # ---- Create VdcHost + Vdc ----------------------------------------
    host = VdcHost(
        port=PORT,
        model=MODEL_NAME,
        name=HOST_NAME,
        vendor_name=VENDOR,
        state_path=STATE_FILE,
    )

    vdc = Vdc(
        host=host,
        implementation_id=VDC_IMPLEMENTATION_ID,
        name=VDC_NAME,
        model=VDC_MODEL,
        capabilities=VdcCapabilities(
            metering=False,
            identification=True,
            dynamic_definitions=True,
        ),
    )
    host.add_vdc(vdc)

    # ---- Create a Device with 5 sub-devices --------------------------
    device_dsuid = DsUid.from_name_in_space(
        "experiment-state-device-1", DsUidNamespace.VDC
    )
    device = Device(vdc=vdc, dsuid=device_dsuid)

    # Create all 5 variants
    vdsd_a = make_device_a(device)
    vdsd_b = make_device_b(device)
    vdsd_c = make_device_c(device)
    vdsd_d = make_device_d(device)
    vdsd_e = make_device_e(device)

    device.add_vdsd(vdsd_a)
    device.add_vdsd(vdsd_b)
    device.add_vdsd(vdsd_c)
    device.add_vdsd(vdsd_d)
    device.add_vdsd(vdsd_e)

    vdc.add_device(device)

    # ---- Log topology ------------------------------------------------
    section("Device topology")
    logger.info("VdcHost: %s  dSUID: %s", host.name, host.dsuid)
    logger.info("vDC:     %s  dSUID: %s", vdc.name, vdc.dsuid)
    logger.info("Device:  dSUID: %s  (%d sub-devices)",
                device.dsuid, len(device.vdsds))

    device_map: Dict[str, Dict[str, Any]] = {}
    labels = {0: "A", 1: "B", 2: "C", 3: "D", 4: "E"}
    descriptions = {
        0: "API deviceStates (normal names)",
        1: "API deviceStates (StatusXxx names)",
        2: "binaryInputs only",
        3: "sensorInputs only",
        4: "Combined: all approaches",
    }

    for idx in sorted(device.vdsds):
        v = device.vdsds[idx]
        label = labels[idx]
        logger.info(
            "  vdSD[%d] = Device %s: '%s'  dSUID=%s",
            idx, label, v.name, v.dsuid,
        )
        logger.info("    States: %d  BinaryInputs: %d  SensorInputs: %d  "
                     "Properties: %d  Events: %d",
                     len(v.device_states), len(v.binary_inputs),
                     len(v.sensor_inputs), len(v.device_properties),
                     len(v.device_events))
        if v.output:
            logger.info("    Output: %s (%s)", v.output.name, v.output.function.name)

        device_map[label] = {
            "dsuid": str(v.dsuid),
            "vdsd": v,
            "description": descriptions[idx],
        }

    # ---- Set initial state values ------------------------------------
    section("Setting initial state values")

    # Device A: set operatingState=Running, connectivity=Online
    vdsd_a.device_states[0].value = 2  # Running
    vdsd_a.device_states[1].value = 1  # Online
    logger.info("Device A: operatingState=Running, connectivity=Online")

    # Device B: set StatusOperationMode=Playing, StatusMute=Unmuted, StatusInputMode=Streaming
    vdsd_b.device_states[0].value = 2  # Playing
    vdsd_b.device_states[1].value = 0  # Unmuted
    vdsd_b.device_states[2].value = 3  # Streaming
    logger.info("Device B: StatusOperationMode=Playing, StatusMute=Unmuted, StatusInputMode=Streaming")

    # Device C: binary inputs (set later via update_value after session)
    logger.info("Device C: binary inputs will be set after session established")

    # Device D: sensor inputs (set later via update_value after session)
    logger.info("Device D: sensor inputs will be set after session established")

    # Device E: combined
    vdsd_e.device_states[0].value = 1  # Active
    logger.info("Device E: StatusOperationMode=Active (binary/sensor set after session)")

    # ---- Start & connect ---------------------------------------------
    section("Starting VdcHost — waiting for vdSM connection")
    logger.info("Listening on port %d …", PORT)

    host.on_message = on_message
    await host.start()

    try:
        await wait_for_session(host, CONNECT_TIMEOUT)
        session = host.session

        # ---- Push initial state values after session -----------------
        section("Pushing initial state values to vdSM")

        # Push device states for A, B, E
        for st in vdsd_a.device_states.values():
            if st.value is not None:
                await st.update_value(st.value, session)
        for st in vdsd_b.device_states.values():
            if st.value is not None:
                await st.update_value(st.value, session)
        for st in vdsd_e.device_states.values():
            if st.value is not None:
                await st.update_value(st.value, session)
        logger.info("Pushed deviceStates for A, B, E")

        # Push binary input values for C and E
        for bi in vdsd_c.binary_inputs.values():
            await bi.update_value(True, session)
        for bi in vdsd_e.binary_inputs.values():
            await bi.update_value(True, session)
        logger.info("Pushed binaryInputStates for C, E")

        # Push sensor values for D and E
        for si in vdsd_d.sensor_inputs.values():
            val = 21.5 if si.sensor_type == SensorType.TEMPERATURE else 55.0
            await si.update_value(val, session)
        for si in vdsd_e.sensor_inputs.values():
            await si.update_value(21.5, session)
        logger.info("Pushed sensorStates for D, E")

        # ---- Wait for dSS to process --------------------------------
        section(f"Waiting {REGISTRATION_WAIT}s for dSS to register devices")
        for remaining in range(REGISTRATION_WAIT, 0, -1):
            if remaining % 5 == 0:
                logger.info("  %ds remaining...", remaining)
            await asyncio.sleep(1)

        # ---- Query dSS REST API --------------------------------------
        banner("Querying dSS REST API")

        try:
            token = get_session_token()
            logger.info("Got dSS session token: %s…", token[:16])
        except Exception as e:
            logger.error("Failed to get session token: %s", e)
            logger.error("Skipping REST API queries.")
            await wait_for_user("Press Enter to vanish devices and exit...")
            return

        results = query_all_devices(token, device_map)
        print_results_table(results)

        # ---- Save raw results to file --------------------------------
        results_file = Path("/tmp/pyDSvDCAPI_experiment_results.json")
        serializable = {}
        for label, r in results.items():
            serializable[label] = {
                k: v for k, v in r.items() if k != "vdsd"
            }
        with open(results_file, "w") as f:
            json.dump(serializable, f, indent=2, default=str)
        logger.info("Raw results saved to %s", results_file)

        # ---- Wait for user to inspect --------------------------------
        await wait_for_user(
            "Inspect results above. Press Enter to vanish all devices and exit..."
        )

    finally:
        # ---- Vanish & cleanup ----------------------------------------
        section("Vanishing all devices and cleaning up")
        session = host.session
        if session and session.is_active:
            for idx in sorted(device.vdsds):
                v = device.vdsds[idx]
                try:
                    await v.vanish(session)
                    logger.info("Vanished vdSD[%d] '%s'", idx, v.name)
                except Exception as e:
                    logger.warning("Failed to vanish vdSD[%d]: %s", idx, e)

        await host.stop()
        logger.info("VdcHost stopped.")

        # Remove state file
        if STATE_FILE.exists():
            STATE_FILE.unlink()
        bak = STATE_FILE.with_suffix(STATE_FILE.suffix + ".bak")
        if bak.exists():
            bak.unlink()
        logger.info("Cleanup complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrupted.{RESET}")
    except Exception as e:
        print(f"\n{RED}FATAL: {e}{RESET}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
