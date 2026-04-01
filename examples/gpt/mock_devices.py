"""
mock_devices.py
Mock native device classes for real-world VDC demo.
"""
import asyncio
import random
import logging
from pydsvdcapi.enums import *
from pydsvdcapi.vdsd import Vdsd
from pydsvdcapi.dsuid import DsUid

logging.basicConfig(level=logging.INFO)

class ComplexMockDevice:
    def __init__(self):
        # Vdsd 1: two-way button, binary sensor, sensor, 2 props, 2 states, action, output
        self.vdsd1 = Vdsd(dsuid=DsUid.generate(), name="ComplexDev-1")
        self.button_state = False
        self.binary_sensor = False
        self.sensor_value = 0.0
        self.device_properties = {"prop1": 0, "prop2": 1}
        self.device_states = {"state1": "idle", "state2": "active"}
        self.output_value = 0
        # Vdsd 2: single button, 2 binary inputs, 2 sensors, custom/dynamic action, 2 props, 2 states, 2 events
        self.vdsd2 = Vdsd(dsuid=DsUid.generate(), name="ComplexDev-2")
        self.button2_state = False
        self.binary_inputs = [False, True]
        self.sensors = [22.5, 18.0]
        self.device2_properties = {"propA": 5, "propB": 7}
        self.device2_states = {"stateA": "ready", "stateB": "error"}
        self.events = []
        self.vdsds = [self.vdsd1, self.vdsd2]
    async def simulate(self):
        while True:
            # Simulate device-side changes
            self.button_state = not self.button_state
            self.binary_sensor = bool(random.getrandbits(1))
            self.sensor_value = random.uniform(0, 100)
            self.output_value = random.randint(0, 255)
            self.button2_state = not self.button2_state
            self.binary_inputs = [bool(random.getrandbits(1)), bool(random.getrandbits(1))]
            self.sensors = [random.uniform(10, 30), random.uniform(10, 30)]
            self.events.append(f"event-{random.randint(1,100)}")
            logging.info(f"[ComplexMockDevice] Updated states: {self.__dict__}")
            await asyncio.sleep(2)
    def on_vdc_action(self, action_name, *args):
        print(f"[ComplexMockDevice] VDC requested action: {action_name} args={args}")
    def on_vdc_property_change(self, prop, value):
        print(f"[ComplexMockDevice] VDC changed property {prop} to {value}")
    def on_vdc_state_change(self, state, value):
        print(f"[ComplexMockDevice] VDC changed state {state} to {value}")
    def on_vdc_output_change(self, value):
        print(f"[ComplexMockDevice] VDC changed output to {value}")
    def bind_to_native(self, vdsd):
        # Example: bind VDC callbacks to native methods
        vdsd.on_action = self.on_vdc_action
        vdsd.on_property_change = self.on_vdc_property_change
        vdsd.on_state_change = self.on_vdc_state_change
        vdsd.on_output_change = self.on_vdc_output_change

class ButtonMockDevice:
    def __init__(self):
        self.vdsd = Vdsd(dsuid=DsUid.generate(), name="ButtonDev")
        self.button_state = 0
    async def simulate(self):
        while True:
            self.button_state = (self.button_state + 1) % 4
            logging.info(f"[ButtonMockDevice] Button state: {self.button_state}")
            await asyncio.sleep(1)
    def on_vdc_action(self, action_name, *args):
        print(f"[ButtonMockDevice] VDC requested action: {action_name} args={args}")
    def bind_to_native(self, vdsd):
        vdsd.on_action = self.on_vdc_action

class BinaryInputMockDevice:
    def __init__(self):
        self.vdsd = Vdsd(dsuid=DsUid.generate(), name="BinaryInputDev")
        self.value = False
    async def simulate(self):
        while True:
            self.value = not self.value
            logging.info(f"[BinaryInputMockDevice] Value: {self.value}")
            await asyncio.sleep(3)
    def on_vdc_property_change(self, prop, value):
        print(f"[BinaryInputMockDevice] VDC changed property {prop} to {value}")
    def bind_to_native(self, vdsd):
        vdsd.on_property_change = self.on_vdc_property_change

class SensorMockDevice:
    def __init__(self):
        self.vdsd = Vdsd(dsuid=DsUid.generate(), name="SensorDev")
        self.value = 0.0
    async def simulate(self):
        while True:
            self.value = random.uniform(0, 100)
            logging.info(f"[SensorMockDevice] Value: {self.value}")
            await asyncio.sleep(2)
    def on_vdc_state_change(self, state, value):
        print(f"[SensorMockDevice] VDC changed state {state} to {value}")
    def bind_to_native(self, vdsd):
        vdsd.on_state_change = self.on_vdc_state_change

class OutputMockDevice:
    def __init__(self):
        self.vdsd = Vdsd(dsuid=DsUid.generate(), name="OutputDev")
        self.brightness = 0
        self.colortemp = 2700
    async def simulate(self):
        while True:
            self.brightness = random.randint(0, 100)
            self.colortemp = random.choice([2700, 3000, 4000, 6500])
            logging.info(f"[OutputMockDevice] Brightness: {self.brightness}, Colortemp: {self.colortemp}")
            await asyncio.sleep(2)
    def on_vdc_output_change(self, value):
        print(f"[OutputMockDevice] VDC changed output to {value}")
    def bind_to_native(self, vdsd):
        vdsd.on_output_change = self.on_vdc_output_change
