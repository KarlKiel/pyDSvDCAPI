#!/usr/bin/env python3
"""Realworld integration demo — vdSD scene handling verification.

This script exercises the scene lifecycle for two virtual devices from
different dS colour groups (Yellow/Light and Grey/Shade) and verifies
that standard default scenes are correctly initialised, that
``callScene`` / ``saveScene`` modify the outputs as expected, and that
scene configurations survive a persistence restart.

Three-phase model
-----------------

**Phase 1 — Fresh start & scene verification**
    * Create a ``VdcHost``, ``Vdc``, ``Device`` with **two** ``Vdsd``
      sub-devices:
      - vdSD 0: Light (Yellow) — ``DIMMER`` output (brightness)
      - vdSD 1: Shade (Grey) — ``POSITIONAL`` output
        (shade position + shade angle, manually added)
    * Verify standard default scene table:
      - Off-scenes (PRESET_0) default to channel min values
      - On-scenes  (PRESET_1) default to channel max values
      - Non-standard scenes (PRESET_2) default to ``dontCare=True``
    * Simulate ``callScene`` for PRESET_0 (off) and PRESET_1 (on),
      verifying that channel values change accordingly.
    * Simulate ``callScene`` for a dontCare scene → no change.
    * Set custom channel values on both devices, then ``saveScene``
      into PRESET_2 — verifying that the scene captures the output
      state and clears ``dontCare``.
    * Modify a standard scene (PRESET_1) via ``saveScene`` with
      non-default values, verifying the override is stored.
    * Announce everything, keep connection alive, verify auto-save.

**Phase 2 — Restart from persistence**
    * Create a new ``VdcHost`` from the persisted YAML.
    * Verify that both vdSDs, their outputs, channels, and the entire
      scene table are restored — including:
      - The modified PRESET_1 (non-default brightness)
      - The user-saved PRESET_2 (custom values, dontCare=False)
      - Unmodified standard scenes still at their defaults
    * ``callScene`` for the modified PRESET_1 → verify custom value.
    * ``callScene`` for the saved PRESET_2 → verify custom values.
    * Re-announce and keep connection alive.

**Phase 3 — Vanish, shutdown & cleanup**
    * Vanish the device.
    * Stop the host and delete all persistence artefacts.

Prerequisites
~~~~~~~~~~~~~

* A running digitalSTROM server (dSS) / vdSM reachable on the local
  network segment to respond to DNS-SD announcements.
* Adjust ``PORT`` if the default is already in use.

Usage::

    python examples/realworld_test_vdsd_with_scenes.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path

from pyDSvDCAPI import (
    ColorGroup,
    Device,
    DsUid,
    DsUidNamespace,
    Output,
    OutputChannelType,
    OutputFunction,
    OutputUsage,
    SceneEffect,
    SceneNumber,
    Vdc,
    VdcCapabilities,
    VdcHost,
    Vdsd,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

STATE_FILE = Path("/tmp/pyDSvDCAPI_scene_demo_state.yaml")

PORT = 8444
MODEL_NAME = "pyDSvDCAPI Scene Demo"
HOST_NAME = "scene-demo-host"
VENDOR = "pyDSvDCAPI"
VDC_IMPLEMENTATION_ID = "x-pyDSvDCAPI-demo-scenes"
VDC_NAME = "Scene Demo vDC"
VDC_MODEL = "pyDSvDCAPI-scene-vdc"

# Device 1: Light (Yellow group) — DIMMER → brightness channel.
VDSD_LIGHT_NAME = "Demo Dimmable Light"
VDSD_LIGHT_MODEL = "pyDSvDCAPI-scene-light"
VDSD_LIGHT_GROUP = ColorGroup.YELLOW

# Device 2: Shade (Grey group) — POSITIONAL → shade position + angle.
VDSD_SHADE_NAME = "Demo Roller Shade"
VDSD_SHADE_MODEL = "pyDSvDCAPI-scene-shade"
VDSD_SHADE_GROUP = ColorGroup.GREY

#: How long to wait for the vdSM/dSS to connect (seconds).
CONNECT_TIMEOUT = 120

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
    """Minimal colour formatter for console output."""

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
# on_message callback — required by VdcHost.start()
# ---------------------------------------------------------------------------

async def on_message(msg) -> None:
    """Log unhandled incoming protobuf messages from the vdSM."""
    logger = logging.getLogger("on_message")
    logger.info(
        "%sRX%s  type=%s  msg_id=%s",
        CYAN, RESET,
        msg.type, msg.message_id,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def wait_for_session(host: VdcHost, timeout: float) -> None:
    """Block until the VdcHost has an active session or *timeout* elapses."""
    logger = logging.getLogger("wait")
    deadline = time.monotonic() + timeout
    while host.session is None or not host.session.is_active:
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"No vdSM/dSS connected within {timeout:.0f}s — aborting."
            )
        await asyncio.sleep(0.5)
    logger.info("Session established with vdSM!")


async def wait_for_user(prompt: str = "Press Enter to continue...") -> None:
    """Non-blocking wait for the user to press Enter."""
    loop = asyncio.get_running_loop()
    print(f"\n{YELLOW}{prompt}{RESET}")
    await loop.run_in_executor(None, sys.stdin.readline)


def banner(text: str) -> None:
    width = max(len(text) + 4, 60)
    sep = "=" * width
    print(f"\n{BOLD}{GREEN}{sep}{RESET}")
    print(f"{BOLD}{GREEN}  {text}{RESET}")
    print(f"{BOLD}{GREEN}{sep}{RESET}\n")


def section(text: str) -> None:
    """Print a minor section heading."""
    print(f"\n{BOLD}{CYAN}--- {text} ---{RESET}\n")


# ---------------------------------------------------------------------------
# on_channel_applied callback
# ---------------------------------------------------------------------------

async def on_channel_applied(output: Output, updates: dict) -> None:
    """Called when channel values are applied.  Logs for visibility."""
    logger = logging.getLogger("hw_apply")
    parts = []
    for ch_type, value in updates.items():
        name = ch_type.name if hasattr(ch_type, "name") else str(ch_type)
        parts.append(f"{name}={value:.1f}")
    logger.info(
        "%sAPPLY%s  [%s] %s",
        GREEN, RESET,
        output.name,
        ", ".join(parts),
    )


# ---------------------------------------------------------------------------
# Scene inspection helpers
# ---------------------------------------------------------------------------

def log_scene(logger, output: Output, scene_nr: int, label: str) -> None:
    """Log one scene entry for an output in a readable format."""
    entry = output.get_scene(scene_nr)
    if entry is None:
        logger.info("  Scene %d (%s): NOT IN TABLE", scene_nr, label)
        return
    dc = entry["dontCare"]
    ilp = entry["ignoreLocalPriority"]
    eff = SceneEffect(entry["effect"]).name
    ch_parts = []
    for idx in sorted(entry.get("channels", {})):
        ch_val = entry["channels"][idx]
        v = ch_val["value"]
        v_str = f"{v:.1f}" if v is not None else "None"
        dc_ch = "DC" if ch_val["dontCare"] else ""
        ch_parts.append(f"ch{idx}={v_str}{dc_ch}")
    ch_str = ", ".join(ch_parts) if ch_parts else "(no channels)"
    logger.info(
        "  Scene %3d (%s): dontCare=%s  ignoreLP=%s  "
        "effect=%s  | %s",
        scene_nr, label, dc, ilp, eff, ch_str,
    )


def log_channel_values(logger, output: Output, prefix: str = "") -> None:
    """Log current channel values for an output."""
    parts = []
    for idx in sorted(output.channels):
        ch = output.channels[idx]
        v = ch.value
        v_str = f"{v:.1f}" if v is not None else "None"
        parts.append(f"ch{idx}({ch.channel_type.name})={v_str}")
    logger.info("%s%s", prefix, ", ".join(parts))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    setup_logging()
    logger = logging.getLogger("demo")

    # ==================================================================
    # PHASE 1 — Fresh start & scene verification
    # ==================================================================
    banner("PHASE 1: Fresh start — two devices, scene verification")

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
            dynamic_definitions=False,
        ),
    )
    host.add_vdc(vdc)

    # ---- Device with two vdSDs (sub-devices) -------------------------
    device_dsuid = DsUid.from_name_in_space(
        "demo-scene-device-1", DsUidNamespace.VDC
    )
    device = Device(vdc=vdc, dsuid=device_dsuid)

    # vdSD 0: Light (Yellow) — DIMMER → auto-creates brightness channel
    vdsd_light = Vdsd(
        device=device,
        subdevice_index=0,
        primary_group=VDSD_LIGHT_GROUP,
        name=VDSD_LIGHT_NAME,
        model=VDSD_LIGHT_MODEL,
        model_features={"dimmable", "blink", "identification"},
    )
    output_light = Output(
        vdsd=vdsd_light,
        function=OutputFunction.DIMMER,
        output_usage=OutputUsage.ROOM,
        name="Dimmer Light Output",
        default_group=int(VDSD_LIGHT_GROUP),
        variable_ramp=True,
        max_power=60.0,
        push_changes=True,
        groups={int(VDSD_LIGHT_GROUP)},
    )
    output_light.on_channel_applied = on_channel_applied
    vdsd_light.set_output(output_light)
    device.add_vdsd(vdsd_light)

    # vdSD 1: Shade (Grey) — POSITIONAL → manually add channels
    vdsd_shade = Vdsd(
        device=device,
        subdevice_index=1,
        primary_group=VDSD_SHADE_GROUP,
        name=VDSD_SHADE_NAME,
        model=VDSD_SHADE_MODEL,
        model_features={"identification"},
    )
    output_shade = Output(
        vdsd=vdsd_shade,
        function=OutputFunction.POSITIONAL,
        output_usage=OutputUsage.ROOM,
        name="Shade Output",
        default_group=int(VDSD_SHADE_GROUP),
        variable_ramp=False,
        max_power=10.0,
        push_changes=True,
        groups={int(VDSD_SHADE_GROUP)},
    )
    output_shade.on_channel_applied = on_channel_applied
    # Manually add shade channels (POSITIONAL has no auto-channels).
    output_shade.add_channel(OutputChannelType.SHADE_POSITION_OUTSIDE)
    output_shade.add_channel(OutputChannelType.SHADE_POSITION_INDOOR)
    vdsd_shade.set_output(output_shade)
    device.add_vdsd(vdsd_shade)

    vdc.add_device(device)

    # ---- Log device topology -----------------------------------------
    logger.info("VdcHost: %s  dSUID: %s", host.name, host.dsuid)
    logger.info("vDC:     %s  dSUID: %s", vdc.name, vdc.dsuid)
    logger.info("")
    logger.info(
        "Device:  dSUID: %s  (%d sub-devices)",
        device.dsuid, len(device.vdsds),
    )
    for idx in sorted(device.vdsds):
        v = device.vdsds[idx]
        logger.info(
            "  vdSD[%d] '%s'  group=%s  dSUID=%s",
            idx, v.name, v.primary_group.name, v.dsuid,
        )
        out = v.output
        if out is not None:
            logger.info(
                "    Output: function=%s  channels=%d",
                out.function.name, len(out.channels),
            )
            for ci in sorted(out.channels):
                ch = out.channels[ci]
                logger.info(
                    "      ch[%d] %s  range=[%.1f .. %.1f]",
                    ci, ch.channel_type.name, ch.min_value, ch.max_value,
                )

    # ==================================================================
    # PHASE 1a — Verify default scene table
    # ==================================================================
    section("Verifying default scene table")

    # Key scene numbers for inspection.
    S_OFF = int(SceneNumber.PRESET_0)       # 0  — standard off
    S_ON = int(SceneNumber.PRESET_1)        # 5  — standard on
    S_DC = int(SceneNumber.PRESET_2)        # 17 — defaults to dontCare
    S_AREA1_ON = int(SceneNumber.AREA_1_ON) # 33 — area 1 on
    # NOTE: We deliberately avoid PANIC / FIRE / ALARM scenes in this
    # demo — calling or even referencing them in a live dS system can
    # trigger system-wide alarm behaviour on other real devices.

    for name, out in [("Light", output_light), ("Shade", output_shade)]:
        logger.info("")
        logger.info("%s: %s — %d scenes in table", name, out.name,
                    len(out._scenes))
        log_scene(logger, out, S_OFF, "PRESET_0/Off")
        log_scene(logger, out, S_ON, "PRESET_1/On")
        log_scene(logger, out, S_DC, "PRESET_2")
        log_scene(logger, out, S_AREA1_ON, "AREA_1_ON")

    # Verify off-scene defaults.
    logger.info("")
    logger.info("Checking: PRESET_0 (off) defaults to min values...")
    for name, out in [("Light", output_light), ("Shade", output_shade)]:
        entry = out.get_scene(S_OFF)
        assert entry is not None, f"{name}: PRESET_0 missing"
        assert entry["dontCare"] is False, f"{name}: PRESET_0 should not be dontCare"
        for idx, ch_val in entry["channels"].items():
            ch = out.channels[idx]
            assert ch_val["value"] == ch.min_value, (
                f"{name} ch{idx}: PRESET_0 value {ch_val['value']} "
                f"!= min {ch.min_value}"
            )
            assert ch_val["dontCare"] is False
    logger.info("  %sPASS%s — all channels at min for both devices.", GREEN, RESET)

    # Verify on-scene defaults.
    logger.info("Checking: PRESET_1 (on) defaults to max values...")
    for name, out in [("Light", output_light), ("Shade", output_shade)]:
        entry = out.get_scene(S_ON)
        assert entry is not None, f"{name}: PRESET_1 missing"
        assert entry["dontCare"] is False
        assert entry["effect"] == int(SceneEffect.SMOOTH)
        for idx, ch_val in entry["channels"].items():
            ch = out.channels[idx]
            assert ch_val["value"] == ch.max_value, (
                f"{name} ch{idx}: PRESET_1 value {ch_val['value']} "
                f"!= max {ch.max_value}"
            )
    logger.info("  %sPASS%s — all channels at max for both devices.", GREEN, RESET)

    # Verify non-standard scene defaults to dontCare.
    logger.info("Checking: PRESET_2 defaults to dontCare=True...")
    for name, out in [("Light", output_light), ("Shade", output_shade)]:
        entry = out.get_scene(S_DC)
        assert entry is not None
        assert entry["dontCare"] is True, (
            f"{name}: PRESET_2 should default to dontCare"
        )
    logger.info("  %sPASS%s — PRESET_2 is dontCare on both devices.", GREEN, RESET)

    # Verify AREA_1_ON is an on-scene with ignoreLocalPriority=False
    # (safe to inspect — area scenes only affect the device itself).
    logger.info("Checking: AREA_1_ON has effect=SMOOTH, ignoreLP=False...")
    for name, out in [("Light", output_light), ("Shade", output_shade)]:
        entry = out.get_scene(S_AREA1_ON)
        assert entry is not None
        assert entry["dontCare"] is False, (
            f"{name}: AREA_1_ON should not be dontCare"
        )
        assert entry["ignoreLocalPriority"] is False, (
            f"{name}: AREA_1_ON should not ignoreLP"
        )
        assert entry["effect"] == int(SceneEffect.SMOOTH)
    logger.info("  %sPASS%s — AREA_1_ON verified.", GREEN, RESET)

    # ==================================================================
    # PHASE 1b — callScene tests
    # ==================================================================
    section("Testing callScene behaviour")

    # --- callScene PRESET_1 (on) → channels should go to max ---------
    logger.info("callScene PRESET_1 (on) on Light...")
    output_light.call_scene(S_ON)
    log_channel_values(logger, output_light, "  Light after ON:  ")
    ch_brightness = output_light.get_channel(0)
    assert ch_brightness.value == 100.0, (
        f"Expected brightness=100, got {ch_brightness.value}"
    )
    logger.info("  %sPASS%s — brightness = 100.0", GREEN, RESET)

    logger.info("callScene PRESET_1 (on) on Shade...")
    output_shade.call_scene(S_ON)
    log_channel_values(logger, output_shade, "  Shade after ON:  ")
    ch_pos = output_shade.get_channel(0)
    ch_angle = output_shade.get_channel(1)
    assert ch_pos.value == 100.0, (
        f"Expected shade_position=100, got {ch_pos.value}"
    )
    logger.info("  %sPASS%s — shade position = 100.0", GREEN, RESET)

    # --- callScene PRESET_0 (off) → channels should go to min --------
    logger.info("")
    logger.info("callScene PRESET_0 (off) on Light...")
    output_light.call_scene(S_OFF)
    log_channel_values(logger, output_light, "  Light after OFF: ")
    assert ch_brightness.value == 0.0, (
        f"Expected brightness=0, got {ch_brightness.value}"
    )
    logger.info("  %sPASS%s — brightness = 0.0", GREEN, RESET)

    logger.info("callScene PRESET_0 (off) on Shade...")
    output_shade.call_scene(S_OFF)
    log_channel_values(logger, output_shade, "  Shade after OFF: ")
    assert ch_pos.value == 0.0, (
        f"Expected shade_position=0, got {ch_pos.value}"
    )
    logger.info("  %sPASS%s — shade position = 0.0", GREEN, RESET)

    # --- callScene on a dontCare scene → no change --------------------
    logger.info("")
    logger.info("Preparing: set known values before dontCare test...")
    ch_brightness.set_value_from_vdsm(42.0)
    ch_brightness.confirm_applied()
    ch_pos.set_value_from_vdsm(55.0)
    ch_pos.confirm_applied()
    log_channel_values(logger, output_light, "  Light before:    ")
    log_channel_values(logger, output_shade, "  Shade before:    ")

    logger.info("callScene PRESET_2 (dontCare) on both devices...")
    output_light.call_scene(S_DC)
    output_shade.call_scene(S_DC)
    log_channel_values(logger, output_light, "  Light after:     ")
    log_channel_values(logger, output_shade, "  Shade after:     ")
    assert ch_brightness.value == 42.0, "dontCare scene should not change value"
    assert ch_pos.value == 55.0, "dontCare scene should not change value"
    logger.info("  %sPASS%s — dontCare scenes correctly ignored.", GREEN, RESET)

    # ==================================================================
    # PHASE 1c — saveScene tests
    # ==================================================================
    section("Testing saveScene behaviour")

    # --- Save custom values into PRESET_2 (was dontCare) --------------
    logger.info("Setting custom values: Light=73%%, Shade pos=30%%, angle=45%%")
    ch_brightness.set_value_from_vdsm(73.0)
    ch_brightness.confirm_applied()
    ch_pos.set_value_from_vdsm(30.0)
    ch_pos.confirm_applied()
    ch_angle.set_value_from_vdsm(45.0)
    ch_angle.confirm_applied()
    log_channel_values(logger, output_light, "  Light: ")
    log_channel_values(logger, output_shade, "  Shade: ")

    logger.info("saveScene PRESET_2 on both devices...")
    output_light.save_scene(S_DC)
    output_shade.save_scene(S_DC)

    # Verify scene was updated.
    entry_light = output_light.get_scene(S_DC)
    entry_shade = output_shade.get_scene(S_DC)
    assert entry_light["dontCare"] is False, "save should clear dontCare"
    assert entry_shade["dontCare"] is False, "save should clear dontCare"
    assert entry_light["channels"][0]["value"] == 73.0
    assert entry_shade["channels"][0]["value"] == 30.0
    assert entry_shade["channels"][1]["value"] == 45.0
    logger.info("  %sPASS%s — PRESET_2 saved with custom values, dontCare cleared.",
                GREEN, RESET)
    log_scene(logger, output_light, S_DC, "PRESET_2 (Light)")
    log_scene(logger, output_shade, S_DC, "PRESET_2 (Shade)")

    # --- Modify standard PRESET_1 to a non-default value --------------
    logger.info("")
    logger.info("Modifying standard PRESET_1: Light=85%%, Shade pos=60%%")
    ch_brightness.set_value_from_vdsm(85.0)
    ch_brightness.confirm_applied()
    ch_pos.set_value_from_vdsm(60.0)
    ch_pos.confirm_applied()
    ch_angle.set_value_from_vdsm(20.0)
    ch_angle.confirm_applied()

    logger.info("saveScene PRESET_1 on both devices...")
    output_light.save_scene(S_ON)
    output_shade.save_scene(S_ON)

    entry_light_on = output_light.get_scene(S_ON)
    entry_shade_on = output_shade.get_scene(S_ON)
    assert entry_light_on["channels"][0]["value"] == 85.0, (
        f"Expected 85.0, got {entry_light_on['channels'][0]['value']}"
    )
    assert entry_shade_on["channels"][0]["value"] == 60.0
    assert entry_shade_on["channels"][1]["value"] == 20.0
    logger.info("  %sPASS%s — PRESET_1 overridden with custom values.", GREEN, RESET)
    log_scene(logger, output_light, S_ON, "PRESET_1 (Light)")
    log_scene(logger, output_shade, S_ON, "PRESET_1 (Shade)")

    # ==================================================================
    # PHASE 1d — Verify callScene uses saved values
    # ==================================================================
    section("Verifying callScene uses saved values")

    # Reset to known values first.
    ch_brightness.set_value_from_vdsm(0.0)
    ch_brightness.confirm_applied()
    ch_pos.set_value_from_vdsm(0.0)
    ch_pos.confirm_applied()
    ch_angle.set_value_from_vdsm(0.0)
    ch_angle.confirm_applied()
    logger.info("Reset all channels to 0.")

    logger.info("callScene PRESET_1 (modified) on Light...")
    output_light.call_scene(S_ON)
    log_channel_values(logger, output_light, "  Light: ")
    assert ch_brightness.value == 85.0, (
        f"Expected 85.0 from modified scene, got {ch_brightness.value}"
    )
    logger.info("  %sPASS%s — Light brightness = 85.0 (custom PRESET_1)", GREEN, RESET)

    logger.info("callScene PRESET_1 (modified) on Shade...")
    output_shade.call_scene(S_ON)
    log_channel_values(logger, output_shade, "  Shade: ")
    assert ch_pos.value == 60.0
    assert ch_angle.value == 20.0
    logger.info("  %sPASS%s — Shade pos=60.0, angle=20.0 (custom PRESET_1)", GREEN, RESET)

    logger.info("")
    logger.info("callScene PRESET_2 (user-saved) on both devices...")
    output_light.call_scene(S_DC)
    output_shade.call_scene(S_DC)
    log_channel_values(logger, output_light, "  Light: ")
    log_channel_values(logger, output_shade, "  Shade: ")
    assert ch_brightness.value == 73.0
    assert ch_pos.value == 30.0
    assert ch_angle.value == 45.0
    logger.info(
        "  %sPASS%s — PRESET_2 values correctly applied from save.",
        GREEN, RESET,
    )

    # Remember values for phase 2 comparison.
    saved_preset1_light = 85.0
    saved_preset1_shade_pos = 60.0
    saved_preset1_shade_angle = 20.0
    saved_preset2_light = 73.0
    saved_preset2_shade_pos = 30.0
    saved_preset2_shade_angle = 45.0

    # ---- Announce everything for real-world test ---------------------
    section("Announcing to vdSM")

    await host.start(on_message=on_message)
    logger.info("TCP server started — waiting for vdSM to connect...")

    try:
        await wait_for_session(host, CONNECT_TIMEOUT)
    except TimeoutError as exc:
        logger.error(str(exc))
        await host.stop()
        return

    logger.info("Announcing vDC...")
    announced_vdcs = await host.announce_vdcs()
    if announced_vdcs == 0:
        logger.error("vDC announcement failed — aborting.")
        await host.stop()
        return
    logger.info("vDC announced (%d/%d).", announced_vdcs, len(host.vdcs))

    session = host.session
    assert session is not None and session.is_active

    logger.info("Announcing device with %d vdSD(s)...", len(device.vdsds))
    announced = await vdc.announce_devices(session)
    if announced == 0:
        logger.error("Device announcement failed — aborting.")
        await host.stop()
        return
    logger.info("Device announced (%d vdSD(s)).", announced)

    # Remember identities for phase 2.
    original_host_dsuid = str(host.dsuid)
    original_vdc_dsuid = str(vdc.dsuid)
    original_device_dsuid = str(device.dsuid)
    original_light_dsuid = str(vdsd_light.dsuid)
    original_shade_dsuid = str(vdsd_shade.dsuid)

    # ---- Verify auto-save ----
    logger.info("Waiting 2s for auto-save...")
    await asyncio.sleep(2)
    assert STATE_FILE.exists(), (
        f"Auto-save did NOT create {STATE_FILE}!"
    )
    logger.info("Auto-save verified — %s exists.", STATE_FILE)

    await wait_for_user(
        ">>> Phase 1 complete: devices announced, scenes verified.\n"
        ">>> The vdSM can now send callScene/saveScene/undoScene.\n"
        ">>> Press Enter to shut down and proceed to Phase 2..."
    )

    # ---- Shut down phase 1 -------------------------------------------
    banner("PHASE 1: Shutting down")
    await host.stop()
    logger.info("VdcHost stopped.  State persisted to %s", STATE_FILE)
    logger.info("Pausing 5s before restart...")
    await asyncio.sleep(5)

    # ==================================================================
    # PHASE 2 — Restart from persistence
    # ==================================================================
    banner("PHASE 2: Restart from persistence — scene verification")

    host2 = VdcHost(
        port=PORT,
        state_path=STATE_FILE,
    )

    logger.info("VdcHost restored from %s:", STATE_FILE)
    logger.info("  dSUID: %s", host2.dsuid)
    assert str(host2.dsuid) == original_host_dsuid
    logger.info("  %sPASS%s — host dSUID preserved.", GREEN, RESET)

    # ---- Verify vDC --------------------------------------------------
    assert len(host2.vdcs) == 1
    r_vdc = list(host2.vdcs.values())[0]
    assert str(r_vdc.dsuid) == original_vdc_dsuid
    logger.info("vDC restored: %s  dSUID: %s", r_vdc.name, r_vdc.dsuid)

    # ---- Verify device -----------------------------------------------
    assert len(r_vdc.devices) == 1
    r_device = list(r_vdc.devices.values())[0]
    assert str(r_device.dsuid) == original_device_dsuid
    assert len(r_device.vdsds) == 2, (
        f"Expected 2 vdSDs, got {len(r_device.vdsds)}"
    )
    logger.info(
        "Device restored: dSUID=%s  vdSDs=%d",
        r_device.dsuid, len(r_device.vdsds),
    )

    # ---- Verify vdSDs ------------------------------------------------
    r_light = r_device.get_vdsd(0)
    r_shade = r_device.get_vdsd(1)
    assert r_light is not None, "Light vdSD not restored"
    assert r_shade is not None, "Shade vdSD not restored"
    assert str(r_light.dsuid) == original_light_dsuid
    assert str(r_shade.dsuid) == original_shade_dsuid
    assert r_light.primary_group == VDSD_LIGHT_GROUP
    assert r_shade.primary_group == VDSD_SHADE_GROUP
    logger.info("  vdSD[0] '%s' group=%s  %sPASS%s",
                r_light.name, r_light.primary_group.name, GREEN, RESET)
    logger.info("  vdSD[1] '%s' group=%s  %sPASS%s",
                r_shade.name, r_shade.primary_group.name, GREEN, RESET)

    # ---- Verify outputs and channels ---------------------------------
    r_out_light = r_light.output
    r_out_shade = r_shade.output
    assert r_out_light is not None, "Light output not restored"
    assert r_out_shade is not None, "Shade output not restored"
    assert r_out_light.function == OutputFunction.DIMMER
    assert r_out_shade.function == OutputFunction.POSITIONAL
    assert len(r_out_light.channels) == 1  # brightness
    assert len(r_out_shade.channels) == 2  # shade_pos + shade_angle
    logger.info("  Light output: function=%s  channels=%d  %sPASS%s",
                r_out_light.function.name, len(r_out_light.channels),
                GREEN, RESET)
    logger.info("  Shade output: function=%s  channels=%d  %sPASS%s",
                r_out_shade.function.name, len(r_out_shade.channels),
                GREEN, RESET)

    # ---- Verify scene persistence ------------------------------------
    section("Verifying scene persistence after restart")

    # 1) Standard off scene should still be at defaults.
    logger.info("Checking PRESET_0 (off) is still at defaults...")
    for name, out in [("Light", r_out_light), ("Shade", r_out_shade)]:
        entry = out.get_scene(S_OFF)
        assert entry is not None
        assert entry["dontCare"] is False
        for idx, ch_val in entry["channels"].items():
            ch = out.channels[idx]
            assert ch_val["value"] == ch.min_value, (
                f"{name} ch{idx}: off scene value "
                f"{ch_val['value']} != min {ch.min_value}"
            )
    logger.info("  %sPASS%s — PRESET_0 at min defaults.", GREEN, RESET)

    # 2) Modified PRESET_1 should have the custom values.
    logger.info("Checking PRESET_1 (on) was persisted with custom values...")
    entry = r_out_light.get_scene(S_ON)
    assert entry is not None
    assert entry["channels"][0]["value"] == saved_preset1_light, (
        f"Light PRESET_1 brightness: expected {saved_preset1_light}, "
        f"got {entry['channels'][0]['value']}"
    )
    entry = r_out_shade.get_scene(S_ON)
    assert entry is not None
    assert entry["channels"][0]["value"] == saved_preset1_shade_pos
    assert entry["channels"][1]["value"] == saved_preset1_shade_angle
    logger.info("  %sPASS%s — PRESET_1 custom values preserved.", GREEN, RESET)
    log_scene(logger, r_out_light, S_ON, "PRESET_1 Light (restored)")
    log_scene(logger, r_out_shade, S_ON, "PRESET_1 Shade (restored)")

    # 3) User-saved PRESET_2 should have custom values & dontCare=False.
    logger.info("Checking PRESET_2 was persisted (user-saved, dontCare=False)...")
    entry = r_out_light.get_scene(S_DC)
    assert entry is not None
    assert entry["dontCare"] is False
    assert entry["channels"][0]["value"] == saved_preset2_light
    entry = r_out_shade.get_scene(S_DC)
    assert entry is not None
    assert entry["dontCare"] is False
    assert entry["channels"][0]["value"] == saved_preset2_shade_pos
    assert entry["channels"][1]["value"] == saved_preset2_shade_angle
    logger.info("  %sPASS%s — PRESET_2 custom values & dontCare=False preserved.",
                GREEN, RESET)
    log_scene(logger, r_out_light, S_DC, "PRESET_2 Light (restored)")
    log_scene(logger, r_out_shade, S_DC, "PRESET_2 Shade (restored)")

    # ---- callScene on restored outputs with saved scenes -------------
    section("Calling restored scenes — verifying output changes")

    logger.info("callScene PRESET_1 (custom) on restored Light...")
    r_out_light.call_scene(S_ON)
    r_ch_brightness = r_out_light.get_channel(0)
    log_channel_values(logger, r_out_light, "  Light: ")
    assert r_ch_brightness.value == saved_preset1_light, (
        f"Expected {saved_preset1_light}, got {r_ch_brightness.value}"
    )
    logger.info(
        "  %sPASS%s — restored Light brightness = %.1f",
        GREEN, RESET, saved_preset1_light,
    )

    logger.info("callScene PRESET_1 (custom) on restored Shade...")
    r_out_shade.call_scene(S_ON)
    r_ch_pos = r_out_shade.get_channel(0)
    r_ch_angle = r_out_shade.get_channel(1)
    log_channel_values(logger, r_out_shade, "  Shade: ")
    assert r_ch_pos.value == saved_preset1_shade_pos
    assert r_ch_angle.value == saved_preset1_shade_angle
    logger.info(
        "  %sPASS%s — restored Shade pos=%.1f, angle=%.1f",
        GREEN, RESET,
        saved_preset1_shade_pos, saved_preset1_shade_angle,
    )

    logger.info("")
    logger.info("callScene PRESET_2 (user-saved) on both restored devices...")
    r_out_light.call_scene(S_DC)
    r_out_shade.call_scene(S_DC)
    log_channel_values(logger, r_out_light, "  Light: ")
    log_channel_values(logger, r_out_shade, "  Shade: ")
    assert r_ch_brightness.value == saved_preset2_light
    assert r_ch_pos.value == saved_preset2_shade_pos
    assert r_ch_angle.value == saved_preset2_shade_angle
    logger.info(
        "  %sPASS%s — restored PRESET_2 values applied correctly.",
        GREEN, RESET,
    )

    # ---- Re-announce -------------------------------------------------
    section("Re-announcing to vdSM")

    # Re-register callbacks (not persisted).
    r_out_light.on_channel_applied = on_channel_applied
    r_out_shade.on_channel_applied = on_channel_applied

    await host2.start(on_message=on_message)
    logger.info("TCP server restarted — waiting for vdSM...")

    try:
        await wait_for_session(host2, CONNECT_TIMEOUT)
    except TimeoutError as exc:
        logger.error(str(exc))
        await host2.stop()
        return

    announced_vdcs = await host2.announce_vdcs()
    logger.info("vDC re-announced (%d/%d).", announced_vdcs, len(host2.vdcs))

    session2 = host2.session
    assert session2 is not None and session2.is_active
    announced = await r_vdc.announce_devices(session2)
    logger.info("Device re-announced (%d vdSD(s)).", announced)

    await wait_for_user(
        ">>> Phase 2 complete: persistence verified, scenes work.\n"
        ">>> The vdSM can send scene commands to the restored devices.\n"
        ">>> Press Enter to vanish and clean up..."
    )

    # ==================================================================
    # PHASE 3 — Vanish, shutdown & cleanup
    # ==================================================================
    banner("PHASE 3: Vanish, shutdown & cleanup")

    session2 = host2.session
    if session2 is not None and session2.is_active:
        logger.info("Vanishing device from vdSM...")
        await r_device.vanish(session2)
        assert not r_device.is_announced
        logger.info("Device vanished.")
        await asyncio.sleep(2)
    else:
        logger.warning("Session not active — cannot vanish cleanly.")

    await host2.stop()
    logger.info("VdcHost stopped.")

    # Delete persistence files.
    if host2._store is not None:
        host2._store.delete()
        logger.info("Persistence files deleted.")

    assert not STATE_FILE.exists(), f"{STATE_FILE} still exists!"
    bak = STATE_FILE.with_suffix(STATE_FILE.suffix + ".bak")
    assert not bak.exists(), f"{bak} still exists!"
    logger.info("Cleanup verified — no leftover files.")

    banner("SCENE DEMO COMPLETE")
    logger.info("All phases completed successfully.")
    logger.info("")
    logger.info("Summary:")
    logger.info("  Phase 1: Created 2 vdSDs (Light/Yellow + Shade/Grey)")
    logger.info("           Verified default scene table (off/on/dontCare/area)")
    logger.info("           Tested callScene PRESET_0/1/2 behaviour")
    logger.info("           Saved custom values into PRESET_2 (new scene)")
    logger.info("           Modified PRESET_1 (standard → custom)")
    logger.info("           Verified callScene with saved values")
    logger.info("  Phase 2: Restored from YAML persistence")
    logger.info("           Verified PRESET_0 (off) still at defaults")
    logger.info("           Verified PRESET_1 (on) custom values preserved")
    logger.info("           Verified PRESET_2 (user-saved) preserved")
    logger.info("           Called both scenes on restored outputs — OK")
    logger.info("  Phase 3: Vanished device, cleaned up")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrupted by user.{RESET}")
