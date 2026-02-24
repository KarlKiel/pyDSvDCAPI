#!/usr/bin/env python3
"""Real-world integration demo for pyDSvDCAPI.

This script demonstrates a full lifecycle with a real digitalSTROM
system (dSS / vdSM) on the local network:

  1. Create a VdcHost with derived properties (dSUID from host MAC).
  2. Announce the service via DNS-SD so the dSS discovers it.
  3. Wait for the vdSM to connect and complete the Hello handshake.
  4. Handle 3 ping/pong keep-alive exchanges.
  5. Shut down the host and persist the property tree.
  6. Spin up a new VdcHost from the persisted properties, confirm
     identity, wait for the vdSM to reconnect and complete Hello.
  7. Handle 3 more ping/pong exchanges on the restored instance.
  8. Shut down completely and delete the persistence files.

Run from the project root::

    python examples/realworld_demo.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure the package is importable when running from the repo root.
# ---------------------------------------------------------------------------
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from pyDSvDCAPI import VdcHost, SessionState  # noqa: E402
from pyDSvDCAPI import genericVDC_pb2 as pb  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

#: Persistence file — lives in /tmp so it's cleaned up automatically.
STATE_FILE = Path("/tmp/pyDSvDCAPI_demo_state.yaml")

#: TCP port.  Using the DS-standard 8444.
PORT = 8444

#: Fixed model strings.
MODEL_NAME = "pyDSvDCAPI Demo Gateway"
HOST_NAME = "pyDSvDCAPI Demo Host"
VENDOR = "pyDSvDCAPI"

#: Number of ping/pong exchanges to wait for before shutdown.
PINGS_BEFORE_SHUTDOWN = 3

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
# Message callback — logs everything the vdSM sends us
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
    # For requests that expect a response, send a GenericResponse OK.
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


async def wait_for_pings(host: VdcHost, count: int, timeout: float) -> None:
    """Block until *count* ping/pong exchanges have occurred."""
    logger = logging.getLogger("demo")
    logger.info("Waiting for %d ping/pong exchanges...", count)
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        s = host.session
        if s is None or not s.is_active:
            raise ConnectionError("Session ended while waiting for pings")
        if s.ping_count >= count:
            logger.info(
                "Reached %d ping/pong exchanges — proceeding.",
                s.ping_count,
            )
            return
        await asyncio.sleep(0.5)
    raise TimeoutError(f"Did not reach {count} pings within {timeout}s")


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
    banner("PHASE 1: Fresh VdcHost start")

    host = VdcHost(
        port=PORT,
        model=MODEL_NAME,
        name=HOST_NAME,
        vendor_name=VENDOR,
        state_path=STATE_FILE,
    )

    logger.info("VdcHost created:")
    logger.info("  MAC:      %s", host.mac)
    logger.info("  dSUID:    %s", host.dsuid)
    logger.info("  Name:     %s", host.name)
    logger.info("  Model:    %s", host.model)
    logger.info("  Port:     %d", host.port)
    logger.info("  Persist:  %s", STATE_FILE)

    # Start TCP server + DNS-SD announcement.
    # (No manual save needed — auto-save persists property changes.)
    await host.start(on_message=on_message)
    logger.info("TCP server started — service announced via DNS-SD")
    logger.info("Waiting for dSS / vdSM to discover and connect...")

    try:
        await wait_for_session(host, CONNECT_TIMEOUT)
    except TimeoutError as exc:
        logger.error(str(exc))
        await host.stop()
        return

    # Wait for 3 ping/pong exchanges.
    try:
        await wait_for_pings(host, PINGS_BEFORE_SHUTDOWN, timeout=300)
    except (TimeoutError, ConnectionError) as exc:
        logger.error("Ping/pong wait failed: %s", exc)
        await host.stop()
        return

    # Remember identity for verification.
    original_dsuid = str(host.dsuid)
    original_mac = host.mac

    # Stop the host.
    banner("PHASE 1: Shutting down")
    await host.stop()
    logger.info("VdcHost stopped (TCP server + DNS-SD removed).")

    # Small pause so the vdSM notices the disconnect.
    logger.info("Pausing 5s before restart...")
    await asyncio.sleep(5)

    # ==================================================================
    # PHASE 2 — Restart from persisted state
    # ==================================================================
    banner("PHASE 2: Restart from persistence")

    host2 = VdcHost(
        port=PORT,
        state_path=STATE_FILE,
    )

    logger.info("VdcHost restored from %s:", STATE_FILE)
    logger.info("  MAC:      %s", host2.mac)
    logger.info("  dSUID:    %s", host2.dsuid)
    logger.info("  Name:     %s", host2.name)
    logger.info("  Model:    %s", host2.model)

    # Verify identity is preserved.
    assert str(host2.dsuid) == original_dsuid, (
        f"dSUID mismatch! {host2.dsuid} != {original_dsuid}"
    )
    assert host2.mac == original_mac, (
        f"MAC mismatch! {host2.mac} != {original_mac}"
    )
    logger.info("Identity verified — dSUID and MAC match original.")

    # Start again.
    await host2.start(on_message=on_message)
    logger.info("TCP server restarted — waiting for vdSM to reconnect...")

    try:
        await wait_for_session(host2, CONNECT_TIMEOUT)
    except TimeoutError as exc:
        logger.error(str(exc))
        await host2.stop()
        return

    # Wait for 3 more pings.
    try:
        await wait_for_pings(host2, PINGS_BEFORE_SHUTDOWN, timeout=300)
    except (TimeoutError, ConnectionError) as exc:
        logger.error("Ping/pong wait (phase 2) failed: %s", exc)
        await host2.stop()
        return

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
