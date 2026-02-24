#!/usr/bin/env python3
"""Real-world integration demo: vDC host + vDC + vdSD with SensorInput.

This script demonstrates the full lifecycle of a vDC host with an
announced vDC and a **vdSD device carrying analogue sensor inputs**
against a real digitalSTROM system (dSS / vdSM).

It extends the basic ``realworld_test_vdsd.py`` demo by:

* Configuring the device with two :class:`SensorInput` components
  (a temperature sensor and a humidity sensor).
* Running a background task that **mocks periodic value changes**
  so that the push-throttling (``minPushInterval``,
  ``changesOnlyInterval``) and alive-timer (``aliveSignInterval``)
  behaviour can be observed live.
* Extending the wait-for-user timeouts so there is ample time to
  inspect notification behaviour in the dSS web UI.

  **Phase 1 — Fresh start**

  1. Create a VdcHost, a Vdc, a Device with a single Vdsd.
  2. Add two SensorInput instances (temperature + humidity).
  3. Announce via DNS-SD, wait for the vdSM handshake.
  4. Announce the vDC, then announce the device/vdSD.
  5. Start a background task that generates mock sensor readings
     every few seconds — observe push notifications, throttling
     and alive-timer heartbeats in the log output.
  6. Verify auto-save has persisted state.
  7. Wait for the user to press Enter, then shut down.

  **Phase 2 — Restart from persistence**

  1. Spin up a new VdcHost from the auto-persisted YAML.
  2. Verify that vDC, Device, Vdsd **and SensorInput settings** are
     all restored correctly.
  3. Wait for the vdSM to reconnect and complete Hello.
  4. Re-announce the vDC and device/vdSD.
  5. Resume mock value changes.
  6. Wait for the user to press Enter to proceed.

  **Phase 3 — Vanish, shutdown & cleanup**

  1. Stop mock value changes.
  2. Vanish the device/vdSD from the vdSM (per §6.3).
  3. Shut down and delete all persistence artefacts.

Run from the project root::

    python examples/realworld_test_vdsd_with_sensor.py
"""

from __future__ import annotations

import asyncio
import logging
import random
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure the package is importable when running from the repo root.
# ---------------------------------------------------------------------------
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from pyDSvDCAPI import (  # noqa: E402
    Device,
    SensorInput,
    Vdc,
    VdcCapabilities,
    VdcHost,
    Vdsd,
)
from pyDSvDCAPI.dsuid import DsUid, DsUidNamespace  # noqa: E402
from pyDSvDCAPI.enums import (  # noqa: E402
    ColorGroup,
    SensorType,
    SensorUsage,
)
from pyDSvDCAPI import genericVDC_pb2 as pb  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

#: Persistence file (separate from the basic demo).
STATE_FILE = Path("/tmp/pyDSvDCAPI_sensor_demo_state.yaml")

#: TCP port (digitalSTROM standard).
PORT = 8444

#: Host identity.
MODEL_NAME = "pyDSvDCAPI Demo Gateway (Sensor)"
HOST_NAME = "pyDSvDCAPI SensorInput Demo Host"
VENDOR = "pyDSvDCAPI"

#: vDC identity.
VDC_IMPLEMENTATION_ID = "x-pyDSvDCAPI-demo-sensor"
VDC_NAME = "Demo SensorInput vDC"
VDC_MODEL = "pyDSvDCAPI Demo Sensor Controller v1"

#: vdSD identity.
VDSD_NAME = "Demo Sensor Device"
VDSD_MODEL = "pyDSvDCAPI Virtual Sensor v1"
VDSD_PRIMARY_GROUP = ColorGroup.BLACK  # Joker / sensor

#: Maximum seconds to wait for a vdSM connection.
CONNECT_TIMEOUT = 120

#: Interval (seconds) between mock value updates.
#: Set well below minPushInterval (2 s default for sensors) so that
#: the rate-limiting coalescing behaviour becomes clearly visible.
MOCK_VALUE_INTERVAL = 0.5

# ---------------------------------------------------------------------------
# Logging — colourful, timestamped, to stdout
# ---------------------------------------------------------------------------

BOLD = "\033[1m"
GREEN = "\033[32m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
RESET = "\033[0m"


class ColourFormatter(logging.Formatter):
    LEVEL_COLOURS = {
        logging.DEBUG: CYAN,
        logging.INFO: GREEN,
        logging.WARNING: YELLOW,
        logging.ERROR: RED,
        logging.CRITICAL: RED + BOLD,
    }

    def format(self, record: logging.LogRecord) -> str:
        colour = self.LEVEL_COLOURS.get(record.levelno, "")
        ts = self.formatTime(record, "%H:%M:%S")
        return (
            f"{BOLD}{ts}{RESET} "
            f"{colour}{record.levelname:<8s}{RESET} "
            f"{record.name}: {record.getMessage()}"
        )


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ColourFormatter())
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()
    root.addHandler(handler)
    # Suppress noisy zeroconf internals.
    logging.getLogger("zeroconf").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Message callback — logs everything the vdSM sends and responds OK
# ---------------------------------------------------------------------------

async def on_message(session, msg: pb.Message):
    """Handle messages that are not hello/ping/bye."""
    type_name = pb.Type.Name(msg.type)
    log = logging.getLogger("demo.callback")
    log.info(
        "Received %s (msg_id=%d) from vdSM %s",
        type_name,
        msg.message_id,
        session.vdsm_dsuid,
    )
    # Respond with OK to all requests.
    if msg.message_id > 0:
        resp = pb.Message()
        resp.type = pb.GENERIC_RESPONSE
        resp.message_id = msg.message_id
        resp.generic_response.code = pb.ERR_OK
        return resp
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def wait_for_session(host: VdcHost, timeout: float) -> None:
    """Block until the vdSM connects and completes the Hello handshake."""
    log = logging.getLogger("demo")
    log.info(
        "Waiting up to %ds for vdSM to connect (port %d)...",
        int(timeout),
        host.port,
    )
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        s = host.session
        if s is not None and s.is_active:
            log.info(
                "Session established with vdSM %s (API v%d)",
                s.vdsm_dsuid,
                s.api_version,
            )
            return
        await asyncio.sleep(0.25)
    raise TimeoutError(
        f"No vdSM connected within {timeout}s — is a dSS on this network?"
    )


async def wait_for_user(prompt: str) -> None:
    """Wait for the user to press Enter without blocking the event loop."""
    loop = asyncio.get_event_loop()
    print()
    print(f"{BOLD}{YELLOW}{prompt}{RESET}")
    await loop.run_in_executor(None, sys.stdin.readline)


def banner(text: str) -> None:
    """Print a prominent banner to the console."""
    width = 60
    print()
    print(f"{BOLD}{CYAN}{'=' * width}{RESET}")
    print(f"{BOLD}{CYAN} {text.center(width - 2)} {RESET}")
    print(f"{BOLD}{CYAN}{'=' * width}{RESET}")
    print()


# ---------------------------------------------------------------------------
# Mock value changer — runs in the background
# ---------------------------------------------------------------------------

class MockValueChanger:
    """Generate realistic sensor readings periodically in the background.

    Temperature drifts slowly around a base value (e.g. 21 °C),
    and humidity fluctuates around 55 %.  This lets us observe push
    notifications, minPushInterval throttling, changesOnlyInterval
    suppression, and alive-timer heartbeats in real time.
    """

    def __init__(
        self,
        sensor_inputs: list[SensorInput],
        interval: float,
    ):
        self._inputs = sensor_inputs
        self._interval = interval
        self._task: asyncio.Task | None = None
        self._log = logging.getLogger("demo.mock")
        # Base values for each sensor (indexed by ds_index).
        self._base_values: dict[int, float] = {}

    def start(self) -> None:
        """Start the background mock loop."""
        if self._task is not None:
            return
        # Initialise base values.
        for si in self._inputs:
            mid = (si.min_value + si.max_value) / 2.0
            self._base_values[si.ds_index] = mid
        self._task = asyncio.ensure_future(self._run())
        self._log.info(
            "Mock value changer started (interval=%.1fs, %d sensor(s))",
            self._interval,
            len(self._inputs),
        )

    async def stop(self) -> None:
        """Stop the background mock loop."""
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        self._log.info("Mock value changer stopped.")

    async def _run(self) -> None:
        """Periodically update each sensor with a drifting value."""
        cycle = 0
        try:
            while True:
                for si in self._inputs:
                    # Random walk: drift ±0.5 around the base value,
                    # clamped to [min, max].
                    base = self._base_values[si.ds_index]
                    drift = random.uniform(-0.5, 0.5)
                    new_val = max(
                        si.min_value,
                        min(si.max_value, base + drift),
                    )
                    # Round to sensor resolution.
                    if si.resolution > 0:
                        new_val = round(
                            new_val / si.resolution
                        ) * si.resolution
                        new_val = round(new_val, 4)  # avoid float artefacts
                    self._base_values[si.ds_index] = new_val

                    self._log.info(
                        "%s  [%d] '%s' → %.2f",
                        MAGENTA + "MOCK" + RESET,
                        si.ds_index,
                        si.name,
                        new_val,
                    )
                    await si.update_value(new_val)
                cycle += 1
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            raise


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    setup_logging()
    logger = logging.getLogger("demo")

    # ==================================================================
    # PHASE 1 — Fresh start
    # ==================================================================
    banner("PHASE 1: Fresh VdcHost + vDC + vdSD + SensorInputs")

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

    # Create a Device and a single Vdsd (sensor device).
    device_dsuid = DsUid.from_name_in_space(
        "demo-sensor-device-1", DsUidNamespace.VDC
    )
    device = Device(vdc=vdc, dsuid=device_dsuid)
    vdsd = Vdsd(
        device=device,
        subdevice_index=0,
        primary_group=VDSD_PRIMARY_GROUP,
        name=VDSD_NAME,
        model=VDSD_MODEL,
        model_features={"blink", "identification"},
    )
    device.add_vdsd(vdsd)

    # Add two sensor inputs: temperature & humidity.
    #
    # Sensor 0 — Temperature (°C)
    #   range:                -20 .. 60 °C, resolution 0.1 °C
    #   alive_sign_interval = 15 s  → heartbeat re-push if nothing else happens
    #   min_push_interval   =  2 s  → coalesce rapid pushes within 2 s (default)
    #   changes_only_interval = 5 s → suppress same-value re-pushes for 5 s
    #
    # Sensor 1 — Humidity (%)
    #   range:                0 .. 100 %, resolution 1 %
    #   alive_sign_interval = 20 s
    #   min_push_interval   =  3 s
    #   changes_only_interval = 0 s → every change is pushed (no suppression)
    si_temperature = SensorInput(
        vdsd=vdsd,
        ds_index=0,
        sensor_type=SensorType.TEMPERATURE,
        sensor_usage=SensorUsage.ROOM,
        name="Room Temperature",
        min_value=-20.0,
        max_value=60.0,
        resolution=0.1,
        update_interval=5.0,
        alive_sign_interval=15.0,
        min_push_interval=2.0,
        changes_only_interval=5.0,
    )
    si_humidity = SensorInput(
        vdsd=vdsd,
        ds_index=1,
        sensor_type=SensorType.HUMIDITY,
        sensor_usage=SensorUsage.ROOM,
        name="Room Humidity",
        min_value=0.0,
        max_value=100.0,
        resolution=1.0,
        update_interval=10.0,
        alive_sign_interval=20.0,
        min_push_interval=3.0,
        changes_only_interval=0.0,
    )
    vdsd.add_sensor_input(si_temperature)
    vdsd.add_sensor_input(si_humidity)

    vdc.add_device(device)

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
    logger.info("  SensorInputs: %d", len(vdsd.sensor_inputs))
    logger.info("")
    for si in [si_temperature, si_humidity]:
        logger.info("  SensorInput[%d] '%s':", si.ds_index, si.name)
        logger.info("    sensorType:          %s", si.sensor_type.name)
        logger.info("    sensorUsage:         %s", si.sensor_usage.name)
        logger.info("    range:               %.1f .. %.1f", si.min_value, si.max_value)
        logger.info("    resolution:          %.2f", si.resolution)
        logger.info("    updateInterval:      %.1fs", si.update_interval)
        logger.info("    aliveSignInterval:   %.1fs", si.alive_sign_interval)
        logger.info("    minPushInterval:     %.1fs", si.min_push_interval)
        logger.info("    changesOnlyInterval: %.1fs", si.changes_only_interval)

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
    # Remember sensor input settings for persistence verification.
    original_si0_group = si_temperature.group
    original_si0_type = si_temperature.sensor_type
    original_si0_min_push = si_temperature.min_push_interval
    original_si0_changes_only = si_temperature.changes_only_interval
    original_si1_group = si_humidity.group
    original_si1_type = si_humidity.sensor_type
    original_si1_min_push = si_humidity.min_push_interval
    original_si1_changes_only = si_humidity.changes_only_interval

    # ------------------------------------------------------------------
    # Start mock value changes — updates each sensor every few seconds.
    # Observe push notifications, throttling, and alive-timer behaviour.
    # ------------------------------------------------------------------
    logger.info("")
    logger.info("Starting mock value changes (every %.1fs)...", MOCK_VALUE_INTERVAL)
    logger.info(
        "Watch for: push notifications, minPushInterval coalescing, "
        "changesOnlyInterval suppression, and aliveSignInterval heartbeats."
    )
    mocker = MockValueChanger(
        [si_temperature, si_humidity], MOCK_VALUE_INTERVAL
    )
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
    # Extended timeout so the user can observe notification behaviour.
    await wait_for_user(
        ">>> vDC + vdSD + SensorInputs announced, mock values running.\n"
        ">>> Watch the log for push notifications and alive-timer heartbeats.\n"
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
    logger.info("  SensorInputs: %d", len(restored_vdsd.sensor_inputs))

    assert str(restored_vdsd.dsuid) == original_vdsd_dsuid, (
        f"vdSD dSUID mismatch! "
        f"{restored_vdsd.dsuid} != {original_vdsd_dsuid}"
    )
    assert restored_vdsd.name == original_vdsd_name
    assert restored_vdsd.primary_group == VDSD_PRIMARY_GROUP
    assert restored_vdsd.model_features == {"blink", "identification"}
    logger.info("vdSD identity verified — dSUID, name, group, features match.")

    # ------------------------------------------------------------------
    # Verify SensorInput persistence (description + settings).
    # ------------------------------------------------------------------
    assert len(restored_vdsd.sensor_inputs) == 2, (
        f"Expected 2 sensor inputs, got {len(restored_vdsd.sensor_inputs)}"
    )
    restored_si0 = restored_vdsd.get_sensor_input(0)
    restored_si1 = restored_vdsd.get_sensor_input(1)
    assert restored_si0 is not None, "SensorInput[0] not restored"
    assert restored_si1 is not None, "SensorInput[1] not restored"

    logger.info("")
    logger.info("SensorInput[0] restored from persistence:")
    logger.info("  name:                %s", restored_si0.name)
    logger.info("  sensorType:          %s", restored_si0.sensor_type.name)
    logger.info("  sensorUsage:         %s", restored_si0.sensor_usage.name)
    logger.info("  range:               %.1f .. %.1f", restored_si0.min_value, restored_si0.max_value)
    logger.info("  resolution:          %.2f", restored_si0.resolution)
    logger.info("  aliveSignInterval:   %.1fs", restored_si0.alive_sign_interval)
    logger.info("  group:               %d", restored_si0.group)
    logger.info("  minPushInterval:     %.1fs", restored_si0.min_push_interval)
    logger.info("  changesOnlyInterval: %.1fs", restored_si0.changes_only_interval)

    # Verify settings survived persistence round-trip.
    assert restored_si0.group == original_si0_group, (
        f"SI[0] group mismatch: {restored_si0.group} != {original_si0_group}"
    )
    assert restored_si0.sensor_type == original_si0_type, (
        f"SI[0] sensorType mismatch: "
        f"{restored_si0.sensor_type} != {original_si0_type}"
    )
    assert restored_si0.min_push_interval == original_si0_min_push, (
        f"SI[0] minPushInterval mismatch: "
        f"{restored_si0.min_push_interval} != {original_si0_min_push}"
    )
    assert restored_si0.changes_only_interval == original_si0_changes_only, (
        f"SI[0] changesOnlyInterval mismatch: "
        f"{restored_si0.changes_only_interval} != {original_si0_changes_only}"
    )
    logger.info("SensorInput[0] settings verified — all match original.")

    logger.info("")
    logger.info("SensorInput[1] restored from persistence:")
    logger.info("  name:                %s", restored_si1.name)
    logger.info("  sensorType:          %s", restored_si1.sensor_type.name)
    logger.info("  sensorUsage:         %s", restored_si1.sensor_usage.name)
    logger.info("  range:               %.1f .. %.1f", restored_si1.min_value, restored_si1.max_value)
    logger.info("  resolution:          %.2f", restored_si1.resolution)
    logger.info("  aliveSignInterval:   %.1fs", restored_si1.alive_sign_interval)
    logger.info("  group:               %d", restored_si1.group)
    logger.info("  minPushInterval:     %.1fs", restored_si1.min_push_interval)
    logger.info("  changesOnlyInterval: %.1fs", restored_si1.changes_only_interval)

    assert restored_si1.group == original_si1_group
    assert restored_si1.sensor_type == original_si1_type
    assert restored_si1.min_push_interval == original_si1_min_push
    assert restored_si1.changes_only_interval == original_si1_changes_only
    logger.info("SensorInput[1] settings verified — all match original.")

    # Note: state properties (value, age, contextId, contextMsg, error)
    # are volatile and NOT persisted — they should be None/OK after restore.
    logger.info("")
    logger.info(
        "Note: SensorInput state (value/age/context/error) is volatile "
        "and correctly NOT restored from persistence."
    )

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

    # Resume mock value changes with the restored sensor inputs.
    logger.info("")
    logger.info("Resuming mock value changes with restored SensorInputs...")
    mocker2 = MockValueChanger(
        [restored_si0, restored_si1], MOCK_VALUE_INTERVAL
    )
    mocker2.start()

    # Keep connection alive — wait for user to terminate.
    await wait_for_user(
        ">>> Restored vDC + vdSD + SensorInputs re-announced, "
        "mock values running.\n"
        ">>> Observe alive-timer heartbeats and push notifications.\n"
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
    logger.info("  Phase 1: Created host + vDC + device/vdSD with 2 SensorInputs,")
    logger.info("           announced all, ran mock sensor readings,")
    logger.info("           auto-save persisted state (no explicit save)")
    logger.info("  Phase 2: Restored from auto-saved YAML,")
    logger.info("           verified SensorInput settings persistence,")
    logger.info("           re-announced all, resumed mock sensor readings")
    logger.info("  Phase 3: Vanished vdSD (§6.3), vDC stays (§5) → shutdown")
    logger.info("           → all artefacts cleaned up")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrupted by user.{RESET}")
