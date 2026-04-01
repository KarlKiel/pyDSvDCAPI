#!/usr/bin/env python3
"""Minimal test to capture wire-level protobuf exchanges for states."""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path

from pydsvdcapi import (
    ColorGroup,
    Device,
    DsUid,
    DsUidNamespace,
    Output,
    OutputFunction,
    OutputUsage,
    Vdc,
    VdcCapabilities,
    VdcHost,
    Vdsd,
)
from pydsvdcapi.device_state import DeviceState
from pydsvdcapi.device_property import (
    PROPERTY_TYPE_NUMERIC,
    PROPERTY_TYPE_STRING,
    DeviceProperty,
)
from pydsvdcapi.device_event import DeviceEvent

STATE_FILE = Path("/tmp/pydsvdcapi_wire_debug_state.yaml")
PORT = 8444
CONNECT_TIMEOUT = 120

def setup_logging():
    handler = logging.StreamHandler(sys.stdout)
    fmt = logging.Formatter("%(asctime)s %(name)-20s %(levelname)-5s %(message)s", "%H:%M:%S")
    handler.setFormatter(fmt)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)


async def on_message(msg):
    logger = logging.getLogger("on_message")
    logger.info("RX type=%s msg_id=%s", msg.type, msg.message_id)


async def on_channel_applied(output, updates):
    pass


async def wait_for_session(host, timeout):
    deadline = time.monotonic() + timeout
    while host.session is None or not host.session.is_active:
        if time.monotonic() > deadline:
            raise TimeoutError(f"No vdSM connected within {timeout}s")
        await asyncio.sleep(0.5)
    logging.getLogger("wait").info("Session established!")


async def main():
    setup_logging()
    logger = logging.getLogger("wire_debug")

    # Clean up
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    bak = STATE_FILE.with_suffix(STATE_FILE.suffix + ".bak")
    if bak.exists():
        bak.unlink()

    # Create minimal setup
    host = VdcHost(
        port=PORT, model="Wire Debug", name="wire-debug-host",
        vendor_name="test", state_path=STATE_FILE,
    )
    vdc = Vdc(
        host=host, implementation_id="x-wire-debug",
        name="Debug vDC", model="debug-vdc",
        capabilities=VdcCapabilities(
            metering=False, identification=True,
            dynamic_definitions=True,
        ),
    )
    host.add_vdc(vdc)

    device_dsuid = DsUid.from_name_in_space("wire-debug-device-FRESH-v7-int-values", DsUidNamespace.VDC)
    device = Device(vdc=vdc, dsuid=device_dsuid)

    # ONE vdSD with ONE state, ONE property, ONE event
    vdsd = Vdsd(
        device=device, subdevice_index=0,
        primary_group=ColorGroup.CYAN,
        name="Wire Debug Device",
        model="debug-device",
        model_features={"identification"},
    )
    output = Output(
        vdsd=vdsd, function=OutputFunction.DIMMER,
        output_usage=OutputUsage.ROOM, name="Debug Output",
        default_group=int(ColorGroup.CYAN), variable_ramp=False,
        max_power=2.0, push_changes=True,
        groups={int(ColorGroup.CYAN)},
    )
    output.on_channel_applied = on_channel_applied
    vdsd.set_output(output)

    # ONE device state
    state1 = DeviceState(
        vdsd=vdsd, ds_index=0,
        name="operatingState",
        options={0: "Off", 1: "Initializing", 2: "Running", 3: "Shutdown"},
        description="Current operating state",
    )
    vdsd.add_device_state(state1)
    state1.value = 2  # Running

    # ONE device property
    prop1 = DeviceProperty(
        vdsd=vdsd, ds_index=0,
        name="batteryLevel",
        type=PROPERTY_TYPE_NUMERIC,
        min_value=0.0, max_value=100.0,
        resolution=1.0, siunit="%",
        default=100.0,
        description="Battery level",
    )
    vdsd.add_device_property(prop1)
    prop1.value = 87.0

    # ONE device event
    evt1 = DeviceEvent(
        vdsd=vdsd, ds_index=0,
        name="tamperAlarm",
        description="Tamper detected",
    )
    vdsd.add_device_event(evt1)

    device.add_vdsd(vdsd)
    vdc.add_device(device)

    # Print what our properties dict looks like
    import json
    props = vdsd.get_properties()
    for key in ["deviceStateDescriptions", "deviceStates",
                "devicePropertyDescriptions", "deviceProperties",
                "deviceEventDescriptions"]:
        if key in props:
            logger.info("OUR PROPS %s = %s", key, json.dumps(props[key], indent=2, default=str))

    # Also print the full protobuf response
    from pydsvdcapi import genericVDC_pb2 as pb
    from pydsvdcapi.property_handling import dict_to_elements
    logger.info("=== FULL PROTOBUF WIRE FORMAT ===")
    for key in ["deviceStateDescriptions", "deviceStates",
                "devicePropertyDescriptions", "deviceProperties",
                "deviceEventDescriptions"]:
        if key in props:
            tree = {key: props[key]}
            elems = dict_to_elements(tree)
            for e in elems:
                logger.info("PROTOBUF %s:\n%s", key, e)

    # Start and connect
    logger.info("Starting VdcHost on port %d ...", PORT)
    host.on_message = on_message
    await host.start()

    logger.info("Waiting for vdSM connection (timeout=%ds) ...", CONNECT_TIMEOUT)
    try:
        await wait_for_session(host, CONNECT_TIMEOUT)
    except TimeoutError:
        logger.error("No vdSM connection — shutting down")
        await host.stop()
        return

    logger.info("Connected! Announcing vDCs and devices...")
    
    # Announce vDCs
    announced_vdcs = await host.announce_vdcs()
    logger.info("vDC announced: %d", announced_vdcs)
    
    # Announce devices
    session = host.session
    announced = await vdc.announce_devices(session)
    logger.info("Devices announced: %d", announced)
    
    logger.info("Waiting 30s for property queries to arrive...")
    await asyncio.sleep(30)

    logger.info("Done. Shutting down.")
    await host.stop()


if __name__ == "__main__":
    asyncio.run(main())
