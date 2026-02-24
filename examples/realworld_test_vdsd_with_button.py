#!/usr/bin/env python3
"""Real-world integration demo: vDC host + vDC + vdSD with ButtonInput.

This script demonstrates the full lifecycle of a vDC host with an
announced vDC and a **vdSD device carrying button inputs** against a
real digitalSTROM system (dSS / vdSM).

It extends the basic ``realworld_test_vdsd.py`` demo by:

* Configuring the device with two physical pushbuttons of different
  types:

  - **Button 0** — a two-way rocker (``TWO_WAY_PUSHBUTTON``), which
    uses the **clickType** state mode.  Simulated presses are fed
    through the built-in :class:`ClickDetector` state machine, which
    resolves timing patterns into ``ButtonClickType`` events
    (single/double/triple click, hold start/repeat/end, combos).

  - **Button 1** — a single push-button (``SINGLE_PUSHBUTTON``),
    which uses the **actionId** state mode for **direct scene calls**.
    Instead of resolving click patterns, this button calls scenes
    directly via :meth:`ButtonInput.update_action`.

    **SAFETY:** All action IDs used in this demo are fake mock
    values (65 000+) that do **not** correspond to any real
    digitalSTROM scene.  No real automation will be triggered.

* Running a background task that **mocks periodic button
  interactions** (press/release sequences for button 0, direct
  action calls for button 1) so that push notifications can be
  observed live.

  **Phase 1 — Fresh start**

  1. Create a VdcHost, a Vdc, a Device with a single Vdsd.
  2. Add button inputs: a 2-element rocker (dsIndex 0+1) and a
     single push-button (dsIndex 2).
  3. Announce via DNS-SD, wait for the vdSM handshake.
  4. Announce the vDC, then announce the device/vdSD.
  5. Start a background task that simulates button interactions —
     observe push notifications, ClickDetector state transitions,
     and direct scene calls in the log output.
  6. Verify auto-save has persisted state.
  7. Wait for the user to press Enter, then shut down.

  **Phase 2 — Restart from persistence**

  1. Spin up a new VdcHost from the auto-persisted YAML.
  2. Verify that vDC, Device, Vdsd **and ButtonInput settings** are
     all restored correctly.
  3. Wait for the vdSM to reconnect and complete Hello.
  4. Re-announce the vDC and device/vdSD.
  5. Resume mock button interactions.
  6. Wait for the user to press Enter to proceed.

  **Phase 3 — Vanish, shutdown & cleanup**

  1. Stop mock interactions.
  2. Vanish the device/vdSD from the vdSM (per §6.3).
  3. Shut down and delete all persistence artefacts.

Run from the project root::

    python examples/realworld_test_vdsd_with_button.py
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
    ButtonInput,
    create_button_group,
    Device,
    Vdc,
    VdcCapabilities,
    VdcHost,
    Vdsd,
)
from pyDSvDCAPI.dsuid import DsUid, DsUidNamespace  # noqa: E402
from pyDSvDCAPI.enums import (  # noqa: E402
    ActionMode,
    ButtonClickType,
    ButtonElementID,
    ButtonFunction,
    ButtonMode,
    ButtonType,
    ColorGroup,
)
from pyDSvDCAPI import genericVDC_pb2 as pb  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

#: Persistence file (separate from the other demos).
STATE_FILE = Path("/tmp/pyDSvDCAPI_btn_demo_state.yaml")

#: TCP port (digitalSTROM standard).
PORT = 8444

#: Host identity.
MODEL_NAME = "pyDSvDCAPI Demo Gateway (Button)"
HOST_NAME = "pyDSvDCAPI ButtonInput Demo Host"
VENDOR = "pyDSvDCAPI"

#: vDC identity.
VDC_IMPLEMENTATION_ID = "x-pyDSvDCAPI-demo-btn"
VDC_NAME = "Demo ButtonInput vDC"
VDC_MODEL = "pyDSvDCAPI Demo Button Controller v1"

#: vdSD identity.
VDSD_NAME = "Demo Button Device"
VDSD_MODEL = "pyDSvDCAPI Virtual Button v1"
VDSD_PRIMARY_GROUP = ColorGroup.YELLOW  # Light group — typical for switches

#: Maximum seconds to wait for a vdSM connection.
CONNECT_TIMEOUT = 120

#: Interval (seconds) between mock button interactions.
MOCK_INTERACTION_INTERVAL = 3.0

#: Fake action IDs for the actionId button.
#: These are deliberately in the 65 000+ range — far above any real
#: digitalSTROM scene number — so **no real automation is triggered**.
MOCK_ACTION_IDS = [65001, 65002, 65003, 65004, 65005]

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
# Mock button interaction simulator
# ---------------------------------------------------------------------------

class MockButtonSimulator:
    """Simulate button interactions in the background.

    For the **rocker** (clickType mode) buttons, simulates
    press/release sequences with varying timing to exercise the
    ClickDetector state machine:
    - Quick taps → single/double/triple clicks
    - Long presses → hold start / hold end

    For the **actionId** button, calls :meth:`ButtonInput.update_action`
    with fake scene IDs (65 000+) and random action modes.
    No real digitalSTROM scene will be triggered.
    """

    def __init__(
        self,
        rocker_buttons: list[ButtonInput],
        action_button: ButtonInput,
        interval: float,
    ):
        self._rocker_buttons = rocker_buttons
        self._action_button = action_button
        self._interval = interval
        self._task: asyncio.Task | None = None
        self._log = logging.getLogger("demo.mock")

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.ensure_future(self._run())
        self._log.info(
            "Mock button simulator started (interval=%.1fs, "
            "%d rocker element(s) + 1 action button)",
            self._interval,
            len(self._rocker_buttons),
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
        self._log.info("Mock button simulator stopped.")

    async def _run(self) -> None:
        """Alternate between rocker interactions and action calls."""
        cycle = 0
        try:
            while True:
                if cycle % 2 == 0:
                    # Rocker interaction — alternate between elements
                    await self._simulate_rocker(cycle)
                else:
                    # Action button — direct scene call
                    await self._simulate_action(cycle)
                cycle += 1
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            raise

    async def _simulate_rocker(self, cycle: int) -> None:
        """Simulate a press/release pattern on a rocker element."""
        # Pick one element (alternate Down/Up).
        idx = cycle % len(self._rocker_buttons)
        btn = self._rocker_buttons[idx]

        # Choose an interaction pattern.
        pattern = cycle % 4
        if pattern == 0:
            # Quick single tap.
            self._log.info(
                "%s  [%d] '%s' — single tap",
                MAGENTA + "MOCK" + RESET,
                btn.ds_index,
                btn.name,
            )
            btn.press()
            await asyncio.sleep(0.05)
            btn.release()
        elif pattern == 1:
            # Double tap.
            self._log.info(
                "%s  [%d] '%s' — double tap",
                MAGENTA + "MOCK" + RESET,
                btn.ds_index,
                btn.name,
            )
            for _ in range(2):
                btn.press()
                await asyncio.sleep(0.05)
                btn.release()
                await asyncio.sleep(0.05)
        elif pattern == 2:
            # Long press (hold).
            self._log.info(
                "%s  [%d] '%s' — long press (hold ~0.5s)",
                MAGENTA + "MOCK" + RESET,
                btn.ds_index,
                btn.name,
            )
            btn.press()
            await asyncio.sleep(0.5)
            btn.release()
        else:
            # Triple tap.
            self._log.info(
                "%s  [%d] '%s' — triple tap",
                MAGENTA + "MOCK" + RESET,
                btn.ds_index,
                btn.name,
            )
            for _ in range(3):
                btn.press()
                await asyncio.sleep(0.05)
                btn.release()
                await asyncio.sleep(0.05)

    async def _simulate_action(self, cycle: int) -> None:
        """Call a fake scene on the action button."""
        action_id = random.choice(MOCK_ACTION_IDS)
        mode = random.choice(list(ActionMode))
        self._log.info(
            "%s  [%d] '%s' — actionId=%d  actionMode=%s  (MOCK — no real scene!)",
            MAGENTA + "MOCK" + RESET,
            self._action_button.ds_index,
            self._action_button.name,
            action_id,
            mode.name,
        )
        await self._action_button.update_action(
            action_id=action_id,
            action_mode=mode,
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
    banner("PHASE 1: Fresh VdcHost + vDC + vdSD + ButtonInputs")

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

    # Create a Device and a single Vdsd.
    device_dsuid = DsUid.from_name_in_space(
        "demo-btn-device-1", DsUidNamespace.VDC
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

    # ------------------------------------------------------------------
    # Button 0 — Two-way rocker (clickType mode)
    # ------------------------------------------------------------------
    # create_button_group produces two elements:
    #   dsIndex 0 = Down  (ButtonElementID.DOWN)
    #   dsIndex 1 = Up    (ButtonElementID.UP)
    #
    # The ClickDetector resolves press/release timing into
    # ButtonClickType events (CLICK_1X, CLICK_2X, HOLD_START, etc.)
    # which are pushed as buttonInputStates with `clickType` + `value`.
    rocker_buttons = create_button_group(
        vdsd,
        button_id=0,
        button_type=ButtonType.TWO_WAY_PUSHBUTTON,
        start_index=0,
        name_prefix="Rocker",
        group=1,  # group 1 = Yellow / Light
        function=ButtonFunction.DEVICE,
        mode=ButtonMode.STANDARD,
        supports_local_key_mode=True,
        click_detector_config={
            "tip_timeout": 0.25,
            "multi_click_window": 0.30,
            "hold_repeat_interval": 1.0,
        },
    )
    for btn in rocker_buttons:
        vdsd.add_button_input(btn)

    # ------------------------------------------------------------------
    # Button 1 — Single push-button (actionId mode)
    # ------------------------------------------------------------------
    # This button calls scenes directly via update_action().  No
    # ClickDetector is used.  The push notification carries `actionId`
    # and `actionMode` instead of `clickType` and `value`.
    #
    # SAFETY: All action IDs are fake (65 000+) — no real scene
    # will be triggered on the connected digitalSTROM system.
    action_button = ButtonInput(
        vdsd=vdsd,
        ds_index=2,
        name="Scene Trigger",
        button_id=1,
        button_type=ButtonType.SINGLE_PUSHBUTTON,
        button_element_id=ButtonElementID.CENTER,
        group=1,
        function=ButtonFunction.DEVICE,
        mode=ButtonMode.STANDARD,
    )
    vdsd.add_button_input(action_button)

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
    logger.info("  ButtonInputs: %d", len(vdsd.button_inputs))
    logger.info("")
    for btn in rocker_buttons:
        logger.info(
            "  ButtonInput[%d] '%s' (clickType mode):", btn.ds_index, btn.name
        )
        logger.info("    buttonType:      %s", btn.button_type.name)
        logger.info("    buttonElementID: %s", btn.button_element_id.name)
        logger.info("    buttonID:        %s", btn.button_id)
        logger.info("    group:           %d", btn.group)
        logger.info("    function:        %s", btn.function.name)
        logger.info("    mode:            %s", btn.mode.name)
        logger.info("    supportsLocal:   %s", btn.supports_local_key_mode)
    logger.info(
        "  ButtonInput[%d] '%s' (actionId mode — MOCK scene IDs only!):",
        action_button.ds_index,
        action_button.name,
    )
    logger.info("    buttonType:      %s", action_button.button_type.name)
    logger.info("    buttonElementID: %s", action_button.button_element_id.name)
    logger.info("    buttonID:        %s", action_button.button_id)
    logger.info("    group:           %d", action_button.group)
    logger.info("    function:        %s", action_button.function.name)
    logger.info("    mode:            %s", action_button.mode.name)
    logger.info(
        "    MOCK action IDs: %s (no real scenes!)", MOCK_ACTION_IDS
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
    # Remember button input settings for persistence verification.
    original_btn0_group = rocker_buttons[0].group
    original_btn0_function = rocker_buttons[0].function
    original_btn0_mode = rocker_buttons[0].mode
    original_btn0_type = rocker_buttons[0].button_type
    original_btn1_group = rocker_buttons[1].group
    original_btn1_function = rocker_buttons[1].function
    original_btn2_group = action_button.group
    original_btn2_function = action_button.function
    original_btn2_type = action_button.button_type

    # ------------------------------------------------------------------
    # Start mock button interactions.
    # ------------------------------------------------------------------
    logger.info("")
    logger.info(
        "Starting mock button simulator (every %.1fs)...",
        MOCK_INTERACTION_INTERVAL,
    )
    logger.info(
        "Watch for: ClickDetector state transitions (rocker), "
        "direct actionId calls (scene trigger — MOCK only!)."
    )
    logger.info(
        "%sIMPORTANT: All action IDs are fake (65000+). "
        "No real scenes are called!%s",
        YELLOW,
        RESET,
    )
    mocker = MockButtonSimulator(
        rocker_buttons, action_button, MOCK_INTERACTION_INTERVAL
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
    await wait_for_user(
        ">>> vDC + vdSD + ButtonInputs announced, mock interactions running.\n"
        ">>> Rocker: ClickDetector → single/double/triple click, hold.\n"
        ">>> Scene Trigger: actionId calls (MOCK IDs — no real scenes!).\n"
        ">>> Press Enter to shut down and proceed to Phase 2..."
    )

    # Stop mock interactions before shutdown.
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
    logger.info("  ButtonInputs: %d", len(restored_vdsd.button_inputs))

    assert str(restored_vdsd.dsuid) == original_vdsd_dsuid, (
        f"vdSD dSUID mismatch! "
        f"{restored_vdsd.dsuid} != {original_vdsd_dsuid}"
    )
    assert restored_vdsd.name == original_vdsd_name
    assert restored_vdsd.primary_group == VDSD_PRIMARY_GROUP
    assert restored_vdsd.model_features == {"blink", "identification"}
    logger.info("vdSD identity verified — dSUID, name, group, features match.")

    # ------------------------------------------------------------------
    # Verify ButtonInput persistence (description + settings).
    # ------------------------------------------------------------------
    assert len(restored_vdsd.button_inputs) == 3, (
        f"Expected 3 button inputs, got {len(restored_vdsd.button_inputs)}"
    )
    restored_btn0 = restored_vdsd.get_button_input(0)
    restored_btn1 = restored_vdsd.get_button_input(1)
    restored_btn2 = restored_vdsd.get_button_input(2)
    assert restored_btn0 is not None, "ButtonInput[0] not restored"
    assert restored_btn1 is not None, "ButtonInput[1] not restored"
    assert restored_btn2 is not None, "ButtonInput[2] not restored"

    logger.info("")
    logger.info("ButtonInput[0] restored (Rocker Down):")
    logger.info("  name:            %s", restored_btn0.name)
    logger.info("  buttonType:      %s", restored_btn0.button_type.name)
    logger.info("  buttonElementID: %s", restored_btn0.button_element_id.name)
    logger.info("  buttonID:        %s", restored_btn0.button_id)
    logger.info("  group:           %d", restored_btn0.group)
    logger.info("  function:        %s", restored_btn0.function.name)
    logger.info("  mode:            %s", restored_btn0.mode.name)

    assert restored_btn0.group == original_btn0_group, (
        f"Btn[0] group mismatch: {restored_btn0.group} != {original_btn0_group}"
    )
    assert restored_btn0.function == original_btn0_function
    assert restored_btn0.mode == original_btn0_mode
    assert restored_btn0.button_type == original_btn0_type
    logger.info("ButtonInput[0] settings verified — all match original.")

    logger.info("")
    logger.info("ButtonInput[1] restored (Rocker Up):")
    logger.info("  name:            %s", restored_btn1.name)
    logger.info("  buttonType:      %s", restored_btn1.button_type.name)
    logger.info("  buttonElementID: %s", restored_btn1.button_element_id.name)
    logger.info("  buttonID:        %s", restored_btn1.button_id)
    logger.info("  group:           %d", restored_btn1.group)
    logger.info("  function:        %s", restored_btn1.function.name)

    assert restored_btn1.group == original_btn1_group
    assert restored_btn1.function == original_btn1_function
    logger.info("ButtonInput[1] settings verified — all match original.")

    logger.info("")
    logger.info("ButtonInput[2] restored (Scene Trigger):")
    logger.info("  name:            %s", restored_btn2.name)
    logger.info("  buttonType:      %s", restored_btn2.button_type.name)
    logger.info("  buttonElementID: %s", restored_btn2.button_element_id.name)
    logger.info("  buttonID:        %s", restored_btn2.button_id)
    logger.info("  group:           %d", restored_btn2.group)
    logger.info("  function:        %s", restored_btn2.function.name)

    assert restored_btn2.group == original_btn2_group
    assert restored_btn2.function == original_btn2_function
    assert restored_btn2.button_type == original_btn2_type
    logger.info("ButtonInput[2] settings verified — all match original.")

    # State is volatile — not restored.
    logger.info("")
    logger.info(
        "Note: ButtonInput state (value/clickType/actionId/age/error) "
        "is volatile and correctly NOT restored from persistence."
    )
    assert restored_btn0.value is None
    assert restored_btn0.click_type == ButtonClickType.IDLE
    assert restored_btn2.action_id is None

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

    # Resume mock button interactions with the restored inputs.
    logger.info("")
    logger.info("Resuming mock button interactions with restored ButtonInputs...")
    mocker2 = MockButtonSimulator(
        [restored_btn0, restored_btn1],
        restored_btn2,
        MOCK_INTERACTION_INTERVAL,
    )
    mocker2.start()

    # Keep connection alive — wait for user to terminate.
    await wait_for_user(
        ">>> Restored vDC + vdSD + ButtonInputs re-announced, "
        "mock interactions running.\n"
        ">>> Rocker: ClickDetector → click/hold events.\n"
        ">>> Scene Trigger: actionId calls (MOCK IDs — no real scenes!).\n"
        ">>> Press Enter to vanish device and perform final shutdown..."
    )

    # Stop mock interactions.
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
    logger.info("  Phase 1: Created host + vDC + device/vdSD with 3 ButtonInputs,")
    logger.info("           2-way rocker (clickType via ClickDetector) + 1 scene trigger (actionId),")
    logger.info("           announced all, ran mock button interactions,")
    logger.info("           auto-save persisted state (no explicit save)")
    logger.info("  Phase 2: Restored from auto-saved YAML,")
    logger.info("           verified ButtonInput settings persistence,")
    logger.info("           re-announced all, resumed mock interactions")
    logger.info("  Phase 3: Vanished vdSD (§6.3), vDC stays (§5) → shutdown")
    logger.info("           → all artefacts cleaned up")
    logger.info("")
    logger.info(
        "%sNote: All actionId calls used fake IDs (65000+). "
        "No real digitalSTROM scenes were triggered.%s",
        YELLOW,
        RESET,
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrupted by user.{RESET}")
