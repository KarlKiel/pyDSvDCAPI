#!/usr/bin/env python3
"""Real-world integration demo: vDC host + vDC announcement.

This script demonstrates the full lifecycle of a vDC host with an
announced vDC against a real digitalSTROM system (dSS / vdSM):

  **Phase 1 — Fresh start**

  1. Create a VdcHost and a Vdc with derived properties.
  2. Announce the service via DNS-SD so the dSS discovers it.
  3. Wait for the vdSM to connect and complete the Hello handshake.
  4. Announce the vDC to the vdSM via ``announcevdc``.
  5. Keep the connection alive (ping/pong).
  6. Wait for the user to press Enter to proceed.
  7. Persist state and shut down.

  **Phase 2 — Restart from persistence**

  1. Spin up a new VdcHost from the persisted YAML.
  2. Re-register the vDC (restored from persistence).
  3. Wait for the vdSM to reconnect and complete Hello.
  4. Re-announce the vDC.
  5. Keep the connection alive.
  6. Wait for the user to press Enter to proceed.
  7. Clean shutdown, delete persistence files.

Run from the project root::

    python examples/realworld_test_vdc.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure the package is importable when running from the repo root.
# ---------------------------------------------------------------------------
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from pyDSvDCAPI import (  # noqa: E402
    Vdc,
    VdcCapabilities,
    VdcHost,
    SessionState,
)
from pyDSvDCAPI import genericVDC_pb2 as pb  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

#: Persistence file.
STATE_FILE = Path("/tmp/pyDSvDCAPI_vdc_demo_state.yaml")

#: TCP port (digitalSTROM standard).
PORT = 8444

#: Host identity.
MODEL_NAME = "pyDSvDCAPI Demo Gateway"
HOST_NAME = "pyDSvDCAPI vDC Demo Host"
VENDOR = "pyDSvDCAPI"

#: vDC identity.
VDC_IMPLEMENTATION_ID = "x-pyDSvDCAPI-demo-light"
VDC_NAME = "Demo Light vDC"
VDC_MODEL = "pyDSvDCAPI Demo Light Controller v1"

#: Maximum seconds to wait for a vdSM connection.
CONNECT_TIMEOUT = 120

# ---------------------------------------------------------------------------
# Logging — colourful, timestamped, to stdout
# ---------------------------------------------------------------------------

BOLD = "\033[1m"
GREEN = "\033[32m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
RED = "\033[31m"
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
    logger = logging.getLogger("demo.callback")
    logger.info(
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
    logger = logging.getLogger("demo")
    logger.info(
        "Waiting up to %ds for vdSM to connect (port %d)...",
        int(timeout),
        host.port,
    )
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        s = host.session
        if s is not None and s.is_active:
            logger.info(
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
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    setup_logging()
    logger = logging.getLogger("demo")

    # ==================================================================
    # PHASE 1 — Fresh start
    # ==================================================================
    banner("PHASE 1: Fresh VdcHost + vDC start")

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
    logger.info("  Caps:     %s", vdc.capabilities.to_dict())

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
    announced = await host.announce_vdcs()
    if announced == 0:
        logger.error("vDC announcement failed — aborting.")
        await host.stop()
        return
    logger.info("vDC announced successfully (%d/%d).", announced, len(host.vdcs))

    # Remember identity for verification in phase 2.
    original_host_dsuid = str(host.dsuid)
    original_host_mac = host.mac
    original_vdc_dsuid = str(vdc.dsuid)

    # Keep connection alive — wait for user to terminate.
    await wait_for_user(
        ">>> Connection active. Press Enter to shut down and proceed to Phase 2..."
    )

    # ------------------------------------------------------------------
    banner("PHASE 1: Shutting down")
    await host.stop()
    logger.info("VdcHost stopped (TCP server + DNS-SD removed).")
    logger.info("State persisted to %s", STATE_FILE)

    # Verify persistence file exists.
    assert STATE_FILE.exists(), f"State file not found: {STATE_FILE}"
    logger.info("Persistence file verified.")

    # Small pause so the vdSM notices the disconnect.
    logger.info("Pausing 5s before restart...")
    await asyncio.sleep(5)

    # ==================================================================
    # PHASE 2 — Restart from persisted state
    # ==================================================================
    banner("PHASE 2: Restart from persistence")

    # Create a new host — constructor restores vDCs from YAML.
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

    # Verify vDC was restored from persistence.
    assert len(host2.vdcs) == 1, f"Expected 1 vDC, got {len(host2.vdcs)}"
    restored_vdc = list(host2.vdcs.values())[0]
    logger.info("")
    logger.info("vDC restored from persistence:")
    logger.info("  dSUID:    %s", restored_vdc.dsuid)
    logger.info("  Name:     %s", restored_vdc.name)
    logger.info("  Model:    %s", restored_vdc.model)
    logger.info("  ImplId:   %s", restored_vdc.implementation_id)
    logger.info("  Caps:     %s", restored_vdc.capabilities.to_dict())

    assert str(restored_vdc.dsuid) == original_vdc_dsuid, (
        f"vDC dSUID mismatch! {restored_vdc.dsuid} != {original_vdc_dsuid}"
    )
    assert restored_vdc.implementation_id == VDC_IMPLEMENTATION_ID
    assert restored_vdc.name == VDC_NAME
    logger.info("vDC identity verified — dSUID and properties match.")

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
    announced = await host2.announce_vdcs()
    if announced == 0:
        logger.error("vDC re-announcement failed — aborting.")
        await host2.stop()
        return
    logger.info("vDC re-announced successfully (%d/%d).", announced, len(host2.vdcs))

    # Keep connection alive — wait for user to terminate.
    await wait_for_user(
        ">>> Connection active. Press Enter to perform final shutdown and cleanup..."
    )

    # ==================================================================
    # PHASE 3 — Final shutdown & cleanup
    # ==================================================================
    banner("PHASE 3: Final shutdown & cleanup")

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


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrupted by user.{RESET}")
