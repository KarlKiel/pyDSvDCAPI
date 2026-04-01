"""
example_vdc.py
VDC host implementation and device binding logic for the real-world mock demo.
"""
import asyncio
import logging
from pyDSvDCAPI.vdc_host import VdcHost
from pyDSvDCAPI.vdc import Vdc
from pyDSvDCAPI.vdsd import Vdsd
from pyDSvDCAPI.dsuid import DsUid
from pyDSvDCAPI.enums import *

# For demo: import mock device API
from examples.gpt.mock_devices import (
    ComplexMockDevice,
    ButtonMockDevice,
    BinaryInputMockDevice,
    SensorMockDevice,
    OutputMockDevice,
)

logging.basicConfig(level=logging.INFO)

class ExampleVdcDemo:
    def __init__(self):
        self.host = VdcHost()
        self.vdc = Vdc(self.host)
        self.mock_devices = []
        self._setup_devices()

    def _setup_devices(self):
        # Complex device (two Vdsds)
        complex = ComplexMockDevice()
        self.mock_devices.append(complex)
        for vdsd in complex.vdsds:
            self.vdc.add_vdsd(vdsd)
            vdsd.bind_to_native(complex)
        # Other devices
        button = ButtonMockDevice()
        self.mock_devices.append(button)
        self.vdc.add_vdsd(button.vdsd)
        button.vdsd.bind_to_native(button)
        binary = BinaryInputMockDevice()
        self.mock_devices.append(binary)
        self.vdc.add_vdsd(binary.vdsd)
        binary.vdsd.bind_to_native(binary)
        sensor = SensorMockDevice()
        self.mock_devices.append(sensor)
        self.vdc.add_vdsd(sensor.vdsd)
        sensor.vdsd.bind_to_native(sensor)
        output = OutputMockDevice()
        self.mock_devices.append(output)
        self.vdc.add_vdsd(output.vdsd)
        output.vdsd.bind_to_native(output)

    async def run(self):
        await self.host.announce()
        print("VDC host announced. Devices are ready.")
        # Start mock device simulation
        for dev in self.mock_devices:
            asyncio.create_task(dev.simulate())
        # Main loop: user interaction
        await self._main_menu()

    async def _main_menu(self):
        phase = 1
        while True:
            print(f"\n--- Phase {phase} ---")
            print("[1] Close & restore procedure")
            print("[2] Regular shutdown")
            choice = input("Choose action: ").strip()
            if choice == "1":
                print("Simulating close & restore...")
                # Simulate close/restore logic here
                phase += 1
                if phase > 2:
                    print("Demo complete.")
                    break
            elif choice == "2":
                print("Regular shutdown. Exiting.")
                break
            else:
                print("Invalid choice. Try again.")

if __name__ == "__main__":
    asyncio.run(ExampleVdcDemo().run())
