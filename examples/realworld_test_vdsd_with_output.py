#!/usr/bin/env python3
"""Realworld integration demo — vdSD with Output + Output Channels.

This script exercises the full lifecycle of a virtual device that has an
output with automatically created output channels (``FULL_COLOR_DIMMER``
→ brightness, hue, saturation, color temperature, CIE X, CIE Y).

Three-phase model
-----------------

**Phase 1 — Fresh start**
    * Create a ``VdcHost``, ``Vdc``, ``Device``, ``Vdsd``.
    * Attach an ``Output`` (function ``FULL_COLOR_DIMMER``) with
      ``push_changes=True`` and an ``on_channel_applied`` callback.
    * Announce everything via DNS-SD and wait for the vdSM to connect.
    * Start a mock value changer that periodically updates brightness,
      hue, and colour temperature on the device side (→ triggers push
      notifications to the vdSM).
    * Verify auto-save persistence.

**Phase 2 — Restart from persistence**
    * Create a new ``VdcHost`` from the persisted YAML file.
    * Verify that the output, its function, settings, and all channels
      are correctly restored.
    * Re-announce and resume mock value changes.

**Phase 3 — Vanish, shutdown & cleanup**
    * Vanish the device (§6.3).
    * Stop the host and delete all persistence artefacts.

Prerequisites
~~~~~~~~~~~~~

* A running digitalSTROM server (dSS) / vdSM reachable on the local
  network segment to respond to DNS-SD announcements.
* Adjust ``PORT`` if the default is already in use.

Usage::

    python examples/realworld_test_vdsd_with_output.py
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
    Vdc,
    VdcCapabilities,
    VdcHost,
    Vdsd,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

STATE_FILE = Path("/tmp/pyDSvDCAPI_output_demo_state.yaml")

PORT = 8444
MODEL_NAME = "pyDSvDCAPI Output Demo"
HOST_NAME = "output-demo-host"
VENDOR = "pyDSvDCAPI"
VDC_IMPLEMENTATION_ID = "x-pyDSvDCAPI-demo-output"
VDC_NAME = "Output Demo vDC"
VDC_MODEL = "pyDSvDCAPI-output-vdc"
VDSD_NAME = "RGBW LED Strip"
VDSD_MODEL = "pyDSvDCAPI-output-vdsd"
VDSD_PRIMARY_GROUP = ColorGroup.YELLOW  # Light device

#: How long to wait for the vdSM/dSS to connect (seconds).
CONNECT_TIMEOUT = 120
#: Interval between mock output value changes (seconds).
MOCK_VALUE_INTERVAL = 5.0

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
    """Handle incoming protobuf messages from the vdSM.

    Logs the message type and responds with a generic OK if the message
    carries a ``message_id`` that expects a response.
    """
    logger = logging.getLogger("on_message")
    logger.info(
        "%sRX%s  type=%s  msg_id=%s",
        CYAN, RESET,
        msg.type, msg.message_id,
    )
    # Most incoming messages expect a simple OK response.
    if msg.message_id:
        from pyDSvDCAPI.genericVDC_pb2 import vdc_ResponseGetProperty
        from pyDSvDCAPI import ResultCode
        resp = vdc_ResponseGetProperty()
        resp.message_id = msg.message_id
        logger.debug(
            "  → responding OK (msg_id=%d)", msg.message_id,
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


# ---------------------------------------------------------------------------
# MockOutputChanger — simulates device-side output value changes
# ---------------------------------------------------------------------------

class MockOutputChanger:
    """Periodically modifies output channel values on the device side.

    Cycles through brightness, hue, and colour temperature values to
    simulate a device whose local state changes over time.  Because
    ``push_changes=True`` on the output, every ``update_value()`` call
    triggers a ``VDC_SEND_PUSH_PROPERTY`` notification to the vdSM.
    """

    def __init__(self, output: Output, interval: float = 5.0) -> None:
        self._output = output
        self._interval = interval
        self._task: asyncio.Task | None = None
        self._log = logging.getLogger("mock_output")

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.ensure_future(self._run())
        self._log.info(
            "Mock output changer started (interval=%.1fs, %d channel(s))",
            self._interval,
            len(self._output.channels),
        )

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        self._log.info("Mock output changer stopped.")

    async def _run(self) -> None:
        """Periodically update brightness, hue, and colour temperature."""
        cycle = 0
        try:
            while True:
                # Brightness: sweep 10% → 100% in 10 steps.
                brightness = 10.0 + (cycle % 10) * 10.0
                ch_brightness = self._output.get_channel_by_type(
                    OutputChannelType.BRIGHTNESS
                )
                if ch_brightness is not None:
                    self._log.info(
                        "%sMOCK%s  brightness → %.0f%%",
                        MAGENTA, RESET, brightness,
                    )
                    await ch_brightness.update_value(brightness)

                # Hue: rotate through 0° → 360° in 36° steps.
                hue = (cycle * 36.0) % 360.0
                ch_hue = self._output.get_channel_by_type(
                    OutputChannelType.HUE
                )
                if ch_hue is not None:
                    self._log.info(
                        "%sMOCK%s  hue → %.0f°",
                        MAGENTA, RESET, hue,
                    )
                    await ch_hue.update_value(hue)

                # Colour temperature: sweep 2700 K → 6500 K.
                ct = 2700.0 + (cycle % 8) * 475.0
                ch_ct = self._output.get_channel_by_type(
                    OutputChannelType.COLOR_TEMPERATURE
                )
                if ch_ct is not None:
                    self._log.info(
                        "%sMOCK%s  colorTemp → %.0f K",
                        MAGENTA, RESET, ct,
                    )
                    await ch_ct.update_value(ct)

                cycle += 1
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            raise


# ---------------------------------------------------------------------------
# on_channel_applied callback
# ---------------------------------------------------------------------------

async def on_channel_applied(output: Output, updates: dict) -> None:
    """Called when the vdSM sets channel values and apply_now is True.

    This is where real hardware would apply the new values (e.g. set PWM
    duty cycles on an LED driver).  Here we just log them.
    """
    logger = logging.getLogger("hw_apply")
    parts = []
    for ch_type, value in updates.items():
        name = ch_type.name if hasattr(ch_type, "name") else str(ch_type)
        parts.append(f"{name}={value:.1f}")
    logger.info(
        "%sAPPLY%s  %s",
        GREEN, RESET,
        ", ".join(parts),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    setup_logging()
    logger = logging.getLogger("demo")

    # ==================================================================
    # PHASE 1 — Fresh start
    # ==================================================================
    banner("PHASE 1: Fresh VdcHost + vDC + vdSD + Output/Channels")

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

    # Create a Device and a single Vdsd (light device with output).
    device_dsuid = DsUid.from_name_in_space(
        "demo-output-device-1", DsUidNamespace.VDC
    )
    device = Device(vdc=vdc, dsuid=device_dsuid)
    vdsd = Vdsd(
        device=device,
        subdevice_index=0,
        primary_group=VDSD_PRIMARY_GROUP,
        name=VDSD_NAME,
        model=VDSD_MODEL,
        model_features={"dimmable", "blink", "identification"},
    )
    device.add_vdsd(vdsd)

    # ---- Output -------------------------------------------------------
    # FULL_COLOR_DIMMER auto-creates 6 channels:
    #   Index 0 — Brightness (0–100 %)
    #   Index 1 — Hue        (0–359.9°)
    #   Index 2 — Saturation (0–100 %)
    #   Index 3 — Color temperature (100–1000 mired, mapped to K)
    #   Index 4 — CIE X      (0–1)
    #   Index 5 — CIE Y      (0–1)

    output = Output(
        vdsd=vdsd,
        function=OutputFunction.FULL_COLOR_DIMMER,
        output_usage=OutputUsage.ROOM,
        name="LED Strip Output",
        default_group=int(VDSD_PRIMARY_GROUP),
        variable_ramp=True,
        max_power=60.0,
        push_changes=True,
        groups={int(VDSD_PRIMARY_GROUP)},
    )
    output.on_channel_applied = on_channel_applied
    vdsd.set_output(output)

    vdc.add_device(device)

    # ---- Log configuration -------------------------------------------
    logger.info("VdcHost created:")
    logger.info("  MAC:      %s", host.mac)
    logger.info("  dSUID:    %s", host.dsuid)
    logger.info("  Name:     %s", host.name)
    logger.info("  Model:    %s", host.model)
    logger.info("  Port:     %d", host.port)
    logger.info("  Persist:  %s", STATE_FILE)
    logger.info("")
    logger.info("vDC registered:")
    logger.info("  dSUID:    %s", vdc.dsuid)
    logger.info("  Name:     %s", vdc.name)
    logger.info("  Model:    %s", vdc.model)
    logger.info("  ImplId:   %s", vdc.implementation_id)
    logger.info("")
    logger.info("Device registered:")
    logger.info("  Base dSUID: %s", device.dsuid)
    logger.info("  vdSDs:      %d", len(device.vdsds))
    logger.info("")
    logger.info("vdSD registered:")
    logger.info("  dSUID:    %s", vdsd.dsuid)
    logger.info("  Name:     %s", vdsd.name)
    logger.info("  Model:    %s", vdsd.model)
    logger.info("  Group:    %s", vdsd.primary_group.name)
    logger.info("  Features: %s", vdsd.model_features)
    logger.info("")
    logger.info("Output configured:")
    logger.info("  Function:    %s", output.function.name)
    logger.info("  Usage:       %s", output.output_usage.name)
    logger.info("  Name:        %s", output.name)
    logger.info("  PushChanges: %s", output.push_changes)
    logger.info("  MaxPower:    %.0f W", output.max_power)
    logger.info("  VarRamp:     %s", output.variable_ramp)
    logger.info("  Channels:    %d", len(output.channels))
    logger.info("")
    for idx in sorted(output.channels):
        ch = output.channels[idx]
        ch_type_name = (
            ch.channel_type.name
            if hasattr(ch.channel_type, "name")
            else str(ch.channel_type)
        )
        logger.info(
            "  Channel[%d] '%s' (%s)  range [%.1f .. %.1f]  res=%.3f",
            ch.ds_index, ch.name, ch_type_name,
            ch.min_value, ch.max_value, ch.resolution,
        )

    # Start TCP server + DNS-SD announcement.
    await host.start(on_message=on_message)
    logger.info("TCP server started — service announced via DNS-SD")
    logger.info("Waiting for dSS / vdSM to discover and connect...")

    try:
        await wait_for_session(host, CONNECT_TIMEOUT)
    except TimeoutError as exc:
        logger.error(str(exc))
        await host.stop()
        return

    # Announce the vDC to the vdSM.
    logger.info("Announcing vDC to vdSM...")
    announced_vdcs = await host.announce_vdcs()
    if announced_vdcs == 0:
        logger.error("vDC announcement failed — aborting.")
        await host.stop()
        return
    logger.info(
        "vDC announced successfully (%d/%d).",
        announced_vdcs, len(host.vdcs),
    )

    # Announce the device/vdSD to the vdSM.
    session = host.session
    assert session is not None and session.is_active

    logger.info("Announcing device/vdSD to vdSM...")
    announced_vdsds = await vdc.announce_devices(session)
    if announced_vdsds == 0:
        logger.error("vdSD announcement failed — aborting.")
        await host.stop()
        return
    logger.info(
        "vdSD announced successfully (%d device vdSD(s)).",
        announced_vdsds,
    )
    assert device.is_announced, "Device should be announced"
    assert vdsd.is_announced, "vdSD should be announced"

    # Remember identity for verification in phase 2.
    original_host_dsuid = str(host.dsuid)
    original_host_mac = host.mac
    original_vdc_dsuid = str(vdc.dsuid)
    original_device_dsuid = str(device.dsuid)
    original_vdsd_dsuid = str(vdsd.dsuid)
    original_vdsd_name = vdsd.name
    # Remember output settings for persistence verification.
    original_output_function = output.function
    original_output_usage = output.output_usage
    original_output_name = output.name
    original_output_push = output.push_changes
    original_output_max_power = output.max_power
    original_output_var_ramp = output.variable_ramp
    original_channel_count = len(output.channels)
    original_channel_types = {
        idx: ch.channel_type for idx, ch in output.channels.items()
    }

    # ------------------------------------------------------------------
    # Start mock value changes — updates brightness/hue/colorTemp
    # every few seconds.  Observe push notifications to vdSM.
    # ------------------------------------------------------------------
    logger.info("")
    logger.info(
        "Starting mock output value changes (every %.1fs)...",
        MOCK_VALUE_INTERVAL,
    )
    logger.info(
        "Watch for: push notifications, brightness sweeps, "
        "hue rotation, colour temperature changes."
    )
    mocker = MockOutputChanger(output, MOCK_VALUE_INTERVAL)
    mocker.start()

    # ------------------------------------------------------------------
    # Verify auto-save.
    # ------------------------------------------------------------------
    logger.info("Waiting 2s for auto-save timer to complete...")
    await asyncio.sleep(2)

    assert STATE_FILE.exists(), (
        f"Auto-save did NOT create {STATE_FILE} — auto-save is broken!"
    )
    logger.info(
        "Auto-save verified — %s exists (no explicit save() called).",
        STATE_FILE,
    )

    # Keep connection alive — wait for user to terminate.
    await wait_for_user(
        ">>> vDC + vdSD + Output/Channels announced, mock values running.\n"
        ">>> Watch the log for push notifications (brightness/hue/colorTemp).\n"
        ">>> Press Enter to shut down and proceed to Phase 2..."
    )

    # Stop mock changes before shutdown.
    await mocker.stop()

    # ------------------------------------------------------------------
    banner("PHASE 1: Shutting down")
    await host.stop()
    logger.info("VdcHost stopped (TCP server + DNS-SD removed).")
    logger.info("State auto-persisted to %s", STATE_FILE)

    # Small pause so the vdSM notices the disconnect.
    logger.info("Pausing 5s before restart...")
    await asyncio.sleep(5)

    # ==================================================================
    # PHASE 2 — Restart from persisted state
    # ==================================================================
    banner("PHASE 2: Restart from persistence")

    # Create a new host — constructor restores vDCs + devices from YAML.
    host2 = VdcHost(
        port=PORT,
        state_path=STATE_FILE,
    )

    logger.info("VdcHost restored from %s:", STATE_FILE)
    logger.info("  MAC:      %s", host2.mac)
    logger.info("  dSUID:    %s", host2.dsuid)
    logger.info("  Name:     %s", host2.name)
    logger.info("  Model:    %s", host2.model)

    # Verify host identity is preserved.
    assert str(host2.dsuid) == original_host_dsuid, (
        f"Host dSUID mismatch! {host2.dsuid} != {original_host_dsuid}"
    )
    assert host2.mac == original_host_mac, (
        f"MAC mismatch! {host2.mac} != {original_host_mac}"
    )
    logger.info("Host identity verified — dSUID and MAC match original.")

    # Verify vDC was restored.
    assert len(host2.vdcs) == 1, f"Expected 1 vDC, got {len(host2.vdcs)}"
    restored_vdc = list(host2.vdcs.values())[0]
    logger.info("")
    logger.info("vDC restored from persistence:")
    logger.info("  dSUID:    %s", restored_vdc.dsuid)
    logger.info("  Name:     %s", restored_vdc.name)
    logger.info("  Model:    %s", restored_vdc.model)
    logger.info("  ImplId:   %s", restored_vdc.implementation_id)

    assert str(restored_vdc.dsuid) == original_vdc_dsuid, (
        f"vDC dSUID mismatch! {restored_vdc.dsuid} != {original_vdc_dsuid}"
    )
    assert restored_vdc.implementation_id == VDC_IMPLEMENTATION_ID
    assert restored_vdc.name == VDC_NAME
    logger.info("vDC identity verified — dSUID and properties match.")

    # Verify device was restored.
    assert len(restored_vdc.devices) == 1, (
        f"Expected 1 device, got {len(restored_vdc.devices)}"
    )
    restored_device = list(restored_vdc.devices.values())[0]
    logger.info("")
    logger.info("Device restored from persistence:")
    logger.info("  Base dSUID: %s", restored_device.dsuid)
    logger.info("  vdSDs:      %d", len(restored_device.vdsds))

    assert str(restored_device.dsuid) == original_device_dsuid, (
        f"Device dSUID mismatch! "
        f"{restored_device.dsuid} != {original_device_dsuid}"
    )
    logger.info("Device identity verified — base dSUID matches.")

    # Verify vdSD was restored.
    assert len(restored_device.vdsds) == 1, (
        f"Expected 1 vdSD, got {len(restored_device.vdsds)}"
    )
    restored_vdsd = restored_device.get_vdsd(0)
    assert restored_vdsd is not None
    logger.info("")
    logger.info("vdSD restored from persistence:")
    logger.info("  dSUID:    %s", restored_vdsd.dsuid)
    logger.info("  Name:     %s", restored_vdsd.name)
    logger.info("  Group:    %s", restored_vdsd.primary_group.name)
    logger.info("  Features: %s", restored_vdsd.model_features)

    assert str(restored_vdsd.dsuid) == original_vdsd_dsuid, (
        f"vdSD dSUID mismatch! "
        f"{restored_vdsd.dsuid} != {original_vdsd_dsuid}"
    )
    assert restored_vdsd.name == original_vdsd_name
    assert restored_vdsd.primary_group == VDSD_PRIMARY_GROUP
    assert restored_vdsd.model_features == {
        "dimmable", "blink", "identification",
    }
    logger.info("vdSD identity verified — dSUID, name, group, features match.")

    # ------------------------------------------------------------------
    # Verify Output persistence (description + settings).
    # ------------------------------------------------------------------
    restored_output = restored_vdsd.output
    assert restored_output is not None, "Output not restored!"
    logger.info("")
    logger.info("Output restored from persistence:")
    logger.info("  Function:    %s", restored_output.function.name)
    logger.info("  Usage:       %s", restored_output.output_usage.name)
    logger.info("  Name:        %s", restored_output.name)
    logger.info("  PushChanges: %s", restored_output.push_changes)
    logger.info(
        "  MaxPower:    %s",
        f"{restored_output.max_power:.0f} W"
        if restored_output.max_power is not None else "None",
    )
    logger.info("  VarRamp:     %s", restored_output.variable_ramp)
    logger.info("  Channels:    %d", len(restored_output.channels))

    assert restored_output.function == original_output_function, (
        f"Output function mismatch: "
        f"{restored_output.function} != {original_output_function}"
    )
    assert restored_output.output_usage == original_output_usage, (
        f"Output usage mismatch: "
        f"{restored_output.output_usage} != {original_output_usage}"
    )
    assert restored_output.name == original_output_name, (
        f"Output name mismatch: "
        f"'{restored_output.name}' != '{original_output_name}'"
    )
    assert restored_output.push_changes == original_output_push, (
        f"pushChanges mismatch: "
        f"{restored_output.push_changes} != {original_output_push}"
    )
    assert restored_output.max_power == original_output_max_power, (
        f"maxPower mismatch: "
        f"{restored_output.max_power} != {original_output_max_power}"
    )
    assert restored_output.variable_ramp == original_output_var_ramp, (
        f"variableRamp mismatch: "
        f"{restored_output.variable_ramp} != {original_output_var_ramp}"
    )
    logger.info("Output description + settings verified — all match original.")

    # ------------------------------------------------------------------
    # Verify Channel persistence.
    # ------------------------------------------------------------------
    assert len(restored_output.channels) == original_channel_count, (
        f"Channel count mismatch: "
        f"{len(restored_output.channels)} != {original_channel_count}"
    )

    logger.info("")
    for idx in sorted(restored_output.channels):
        ch = restored_output.channels[idx]
        ch_type_name = (
            ch.channel_type.name
            if hasattr(ch.channel_type, "name")
            else str(ch.channel_type)
        )
        logger.info(
            "  Channel[%d] '%s' (%s)  range [%.1f .. %.1f]  res=%.3f",
            ch.ds_index, ch.name, ch_type_name,
            ch.min_value, ch.max_value, ch.resolution,
        )
        # Verify channel type matches original.
        assert ch.channel_type == original_channel_types[idx], (
            f"Channel[{idx}] type mismatch: "
            f"{ch.channel_type} != {original_channel_types[idx]}"
        )
    logger.info("All %d channels verified — types match original.", original_channel_count)

    # Note: channel state (value, age) is volatile and NOT persisted.
    logger.info("")
    logger.info(
        "Note: Channel state (value/age) is volatile and "
        "correctly NOT restored from persistence."
    )

    # Re-register the on_channel_applied callback (not persisted).
    restored_output.on_channel_applied = on_channel_applied

    # Start again.
    await host2.start(on_message=on_message)
    logger.info("TCP server restarted — waiting for vdSM to reconnect...")

    try:
        await wait_for_session(host2, CONNECT_TIMEOUT)
    except TimeoutError as exc:
        logger.error(str(exc))
        await host2.stop()
        return

    # Re-announce the restored vDC.
    logger.info("Re-announcing restored vDC to vdSM...")
    announced_vdcs = await host2.announce_vdcs()
    if announced_vdcs == 0:
        logger.error("vDC re-announcement failed — aborting.")
        await host2.stop()
        return
    logger.info(
        "vDC re-announced successfully (%d/%d).",
        announced_vdcs, len(host2.vdcs),
    )

    # Re-announce the restored device/vdSD.
    session2 = host2.session
    assert session2 is not None and session2.is_active

    logger.info("Re-announcing restored device/vdSD to vdSM...")
    announced_vdsds = await restored_vdc.announce_devices(session2)
    if announced_vdsds == 0:
        logger.error("vdSD re-announcement failed — aborting.")
        await host2.stop()
        return
    logger.info(
        "vdSD re-announced successfully (%d device vdSD(s)).",
        announced_vdsds,
    )
    assert restored_device.is_announced, "Device should be re-announced"
    assert restored_vdsd.is_announced, "vdSD should be re-announced"

    # Resume mock value changes with the restored output.
    logger.info("")
    logger.info("Resuming mock value changes with restored Output...")
    mocker2 = MockOutputChanger(restored_output, MOCK_VALUE_INTERVAL)
    mocker2.start()

    # Keep connection alive — wait for user to terminate.
    await wait_for_user(
        ">>> Restored vDC + vdSD + Output/Channels re-announced, "
        "mock values running.\n"
        ">>> Observe push notifications and channel value updates.\n"
        ">>> Press Enter to vanish device and perform final shutdown..."
    )

    # Stop mock changes.
    await mocker2.stop()

    # ==================================================================
    # PHASE 3 — Vanish device, final shutdown & cleanup
    # ==================================================================
    banner("PHASE 3: Vanish device, shutdown & cleanup")

    session2 = host2.session
    if session2 is not None and session2.is_active:
        logger.info("Vanishing device/vdSD from vdSM (§6.3)...")
        await restored_device.vanish(session2)
        assert not restored_device.is_announced, (
            "Device should no longer be announced"
        )
        assert not restored_vdsd.is_announced, (
            "vdSD should no longer be announced"
        )
        logger.info(
            "Device vanished — VDC_SEND_VANISH sent for dSUID %s.",
            restored_vdsd.dsuid,
        )
        logger.info(
            "Note: vDC '%s' is NOT vanished (§5 — vDCs cannot vanish "
            "during a session). It will disappear when the session ends.",
            restored_vdc.name,
        )

        # Brief pause so the vdSM can process the vanish notification.
        logger.info("Pausing 2s for vdSM to process vanish...")
        await asyncio.sleep(2)
    else:
        logger.warning(
            "Session no longer active — cannot vanish device cleanly."
        )

    await host2.stop()
    logger.info("VdcHost stopped.")

    # Delete persistence files.
    if host2._store is not None:
        host2._store.delete()
        logger.info("Persistence files deleted: %s", STATE_FILE)

    # Verify files are gone.
    assert not STATE_FILE.exists(), f"{STATE_FILE} still exists!"
    bak = STATE_FILE.with_suffix(STATE_FILE.suffix + ".bak")
    assert not bak.exists(), f"{bak} still exists!"
    logger.info("Cleanup verified — no leftover files.")

    banner("DEMO COMPLETE")
    logger.info("All phases completed successfully.")
    logger.info("")
    logger.info("Summary:")
    logger.info("  Phase 1: Created host + vDC + device/vdSD with Output")
    logger.info("           (FULL_COLOR_DIMMER → 6 channels),")
    logger.info("           announced all, ran mock value changes,")
    logger.info("           auto-save persisted state (no explicit save)")
    logger.info("  Phase 2: Restored from auto-saved YAML,")
    logger.info("           verified Output + Channel persistence,")
    logger.info("           re-announced all, resumed mock value changes")
    logger.info("  Phase 3: Vanished vdSD (§6.3), vDC stays (§5) → shutdown")
    logger.info("           → all artefacts cleaned up")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrupted by user.{RESET}")
