#!/usr/bin/env python3
"""Query the dSS JSON API to dump Sonos device property trees.

This script fetches deviceStateDescriptions, deviceStates,
devicePropertyDescriptions, deviceProperties, and
deviceEventDescriptions from Sonos devices connected to the dSS,
so we can see the exact structure the dSS expects.
"""

import json
import ssl
import sys
import urllib.request

DSS_HOST = "10.42.10.10"
DSS_PORT = 8080
APP_TOKEN = "23fa753a71fff5c73d75401e525db26a183abbb154d1da07021bee399329222f"

# Disable SSL verification for self-signed dSS cert
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def dss_get(path: str, params: dict = None) -> dict:
    """Make a GET request to the dSS JSON API."""
    url = f"https://{DSS_HOST}:{DSS_PORT}/json/{path}"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url += f"?{qs}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, context=ctx) as resp:
        return json.loads(resp.read().decode())


def main():
    # Step 1: Login with application token
    print("=== Logging in to dSS ===")
    result = dss_get("system/loginApplication", {"loginToken": APP_TOKEN})
    print(f"Login result: {json.dumps(result, indent=2)}")

    if result.get("ok") is not True:
        print("Login failed!")
        sys.exit(1)

    token = result.get("result", {}).get("token")
    if not token:
        print("No session token received!")
        sys.exit(1)
    print(f"Session token: {token}")

    # Step 2: Get all zones and devices
    print("\n=== Getting apartment structure ===")
    structure = dss_get("apartment/getStructure", {"token": token})
    if not structure.get("ok"):
        print(f"Failed: {json.dumps(structure, indent=2)}")
        sys.exit(1)

    # Find Sonos devices
    sonos_devices = []
    zones = structure.get("result", {}).get("apartment", {}).get("zones", [])
    for zone in zones:
        for group in zone.get("groups", []):
            for dev in group.get("devices", []):
                name = dev.get("name", "")
                if "sonos" in name.lower() or "sono" in name.lower():
                    sonos_devices.append(dev)

    # Also search in the flat device list
    all_devices = []
    for zone in zones:
        for dev in zone.get("devices", []):
            all_devices.append(dev)
            name = dev.get("name", "")
            hw_info = dev.get("hwInfo", "")
            if ("sonos" in name.lower() or "sonos" in hw_info.lower()
                    or "sono" in name.lower()):
                if dev not in sonos_devices:
                    sonos_devices.append(dev)

    if not sonos_devices:
        print("No Sonos devices found by name. Listing ALL devices:")
        for dev in all_devices:
            dsuid = dev.get("id", dev.get("dSUID", "?"))
            name = dev.get("name", "?")
            hw = dev.get("hwInfo", "?")
            print(f"  {name:40s}  dSUID={dsuid}  hw={hw}")
        print("\nTrying to find devices with 'vdc' or non-dS hardware...")
        # Show all device names so user can identify
        sys.exit(0)

    print(f"\nFound {len(sonos_devices)} Sonos device(s):")
    for dev in sonos_devices:
        dsuid = dev.get("id", dev.get("dSUID", "?"))
        name = dev.get("name", "?")
        print(f"  {name}  dSUID={dsuid}")

    # Step 3: For each Sonos device, query the detailed properties
    props_to_query = [
        "deviceStateDescriptions",
        "deviceStates",
        "devicePropertyDescriptions",
        "deviceProperties",
        "deviceEventDescriptions",
    ]

    for dev in sonos_devices[:3]:  # Limit to first 3
        dsuid = dev.get("id", dev.get("dSUID", "?"))
        name = dev.get("name", "?")
        print(f"\n{'='*70}")
        print(f"Device: {name}")
        print(f"dSUID:  {dsuid}")
        print(f"{'='*70}")

        for prop_name in props_to_query:
            print(f"\n--- {prop_name} ---")
            try:
                result = dss_get("property/query2", {
                    "token": token,
                    "query": f"/apartment/zones/*(ZoneID)/devices/*(*)/properties/{prop_name}/*(*)",
                })
                # Filter for this device
                if result.get("ok"):
                    # The query2 result is complex, let's try a simpler approach
                    pass
            except Exception as e:
                print(f"  query2 failed: {e}")

            # Try direct property get for this device
            try:
                result = dss_get("device/getProperty", {
                    "token": token,
                    "dsuid": dsuid,
                    "name": prop_name,
                })
                if result.get("ok"):
                    print(json.dumps(result.get("result", {}), indent=2))
                else:
                    print(f"  Not available or error: {result.get('message', '?')}")
            except Exception as e:
                print(f"  Error: {e}")

    # Step 4: Also try the property/query approach for raw tree
    print(f"\n{'='*70}")
    print("=== Raw property tree query for first Sonos device ===")
    print(f"{'='*70}")

    if sonos_devices:
        dsuid = sonos_devices[0].get("id", sonos_devices[0].get("dSUID", "?"))
        # Try getting the full property subtree
        for prop_name in props_to_query:
            print(f"\n--- property/getProperty({prop_name}) raw ---")
            try:
                result = dss_get("device/getProperty", {
                    "token": token,
                    "dsuid": dsuid,
                    "name": prop_name,
                    "offset": "0",
                })
                print(json.dumps(result, indent=2))
            except Exception as e:
                print(f"  Error: {e}")

    # Step 5: Also try to query our demo device the same way (if still connected)
    print(f"\n{'='*70}")
    print("=== Checking our demo devices ===")
    print(f"{'='*70}")

    for dev in all_devices:
        name = dev.get("name", "")
        if "demo" in name.lower() or "state" in name.lower():
            dsuid = dev.get("id", dev.get("dSUID", "?"))
            print(f"\nOur device: {name}  dSUID={dsuid}")
            for prop_name in props_to_query:
                print(f"\n--- {prop_name} ---")
                try:
                    result = dss_get("device/getProperty", {
                        "token": token,
                        "dsuid": dsuid,
                        "name": prop_name,
                    })
                    if result.get("ok"):
                        print(json.dumps(result.get("result", {}), indent=2))
                    else:
                        print(f"  {result.get('message', '?')}")
                except Exception as e:
                    print(f"  Error: {e}")

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
