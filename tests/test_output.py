"""Tests for the Output component."""

from __future__ import annotations

from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest

from pyDSvDCAPI.dsuid import DsUid, DsUidNamespace
from pyDSvDCAPI.enums import (
    ColorGroup,
    HeatingSystemCapability,
    HeatingSystemType,
    OutputError,
    OutputFunction,
    OutputMode,
    OutputUsage,
)
from pyDSvDCAPI.output import Output
from pyDSvDCAPI.session import VdcSession
from pyDSvDCAPI.vdc import Vdc
from pyDSvDCAPI.vdc_host import VdcHost
from pyDSvDCAPI.vdsd import Device, Vdsd


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_host(**kwargs: Any) -> VdcHost:
    kw: dict[str, Any] = {"name": "Test Host", "mac": "AA:BB:CC:DD:EE:FF"}
    kw.update(kwargs)
    host = VdcHost(**kw)
    host._cancel_auto_save()
    return host


def _make_vdc(host: VdcHost, **kwargs: Any) -> Vdc:
    defaults: dict[str, Any] = {
        "host": host,
        "implementation_id": "x-test-output",
        "name": "Test Output vDC",
        "model": "Test Output v1",
    }
    defaults.update(kwargs)
    return Vdc(**defaults)


def _base_dsuid() -> DsUid:
    return DsUid.from_name_in_space("output-test-device", DsUidNamespace.VDC)


def _make_device(vdc: Vdc, dsuid: Optional[DsUid] = None) -> Device:
    return Device(vdc=vdc, dsuid=dsuid or _base_dsuid())


def _make_vdsd(device: Device, **kwargs: Any) -> Vdsd:
    defaults: dict[str, Any] = {
        "device": device,
        "primary_group": ColorGroup.YELLOW,
        "name": "Output Test vdSD",
    }
    defaults.update(kwargs)
    return Vdsd(**defaults)


def _make_output(vdsd: Vdsd, **kwargs: Any) -> Output:
    defaults: dict[str, Any] = {
        "vdsd": vdsd,
        "function": OutputFunction.DIMMER,
        "output_usage": OutputUsage.ROOM,
        "name": "Test Dimmer",
    }
    defaults.update(kwargs)
    return Output(**defaults)


def _make_mock_session() -> MagicMock:
    session = MagicMock(spec=VdcSession)
    session.is_active = True
    return session


def _make_stack(**kwargs: Any):
    """Create a full host→vdc→device→vdsd stack, return (host, vdc, device, vdsd)."""
    host = _make_host()
    vdc = _make_vdc(host)
    device = _make_device(vdc)
    vdsd = _make_vdsd(device, **kwargs)
    device.add_vdsd(vdsd)
    vdc.add_device(device)
    host.add_vdc(vdc)
    return host, vdc, device, vdsd


# ===========================================================================
# Construction and defaults
# ===========================================================================


class TestOutputConstruction:
    """Tests for Output creation and default values."""

    def test_default_construction(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)

        assert out.function == OutputFunction.DIMMER
        assert out.output_usage == OutputUsage.ROOM
        assert out.name == "Test Dimmer"
        assert out.default_group == 0
        assert out.variable_ramp is False
        assert out.max_power is None
        assert out.active_cooling_mode is None
        assert out.vdsd is vdsd

    def test_default_settings(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)

        assert out.mode == OutputMode.DEFAULT
        assert out.active_group == 0
        assert out.groups == set()
        assert out.push_changes is False
        assert out.on_threshold is None
        assert out.min_brightness is None
        assert out.dim_time_up is None
        assert out.dim_time_down is None
        assert out.dim_time_up_alt1 is None
        assert out.dim_time_down_alt1 is None
        assert out.dim_time_up_alt2 is None
        assert out.dim_time_down_alt2 is None
        assert out.heating_system_capability is None
        assert out.heating_system_type is None

    def test_default_state(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)

        assert out.local_priority is False
        assert out.error == OutputError.OK

    def test_custom_construction(self):
        host, vdc, device, vdsd = _make_stack()
        out = Output(
            vdsd=vdsd,
            function=OutputFunction.FULL_COLOR_DIMMER,
            output_usage=OutputUsage.OUTDOORS,
            name="RGB Flood",
            default_group=1,
            variable_ramp=True,
            max_power=120.0,
            active_cooling_mode=False,
            mode=OutputMode.GRADUAL,
            active_group=1,
            groups={1, 4, 8},
            push_changes=True,
            on_threshold=50.0,
            min_brightness=10.0,
            dim_time_up=100,
            dim_time_down=80,
            dim_time_up_alt1=150,
            dim_time_down_alt1=120,
            dim_time_up_alt2=200,
            dim_time_down_alt2=180,
            heating_system_capability=HeatingSystemCapability.HEATING_AND_COOLING,
            heating_system_type=HeatingSystemType.FLOOR_HEATING,
        )

        assert out.function == OutputFunction.FULL_COLOR_DIMMER
        assert out.output_usage == OutputUsage.OUTDOORS
        assert out.name == "RGB Flood"
        assert out.default_group == 1
        assert out.variable_ramp is True
        assert out.max_power == 120.0
        assert out.active_cooling_mode is False
        assert out.mode == OutputMode.GRADUAL
        assert out.active_group == 1
        assert out.groups == {1, 4, 8}
        assert out.push_changes is True
        assert out.on_threshold == 50.0
        assert out.min_brightness == 10.0
        assert out.dim_time_up == 100
        assert out.dim_time_down == 80
        assert out.dim_time_up_alt1 == 150
        assert out.dim_time_down_alt1 == 120
        assert out.dim_time_up_alt2 == 200
        assert out.dim_time_down_alt2 == 180
        assert out.heating_system_capability == HeatingSystemCapability.HEATING_AND_COOLING
        assert out.heating_system_type == HeatingSystemType.FLOOR_HEATING

    def test_construction_with_int_enums(self):
        host, vdc, device, vdsd = _make_stack()
        out = Output(
            vdsd=vdsd,
            function=1,  # DIMMER
            output_usage=2,  # OUTDOORS
            mode=2,  # GRADUAL
            heating_system_capability=1,  # HEATING_ONLY
            heating_system_type=3,  # WALL_HEATING
        )

        assert out.function == OutputFunction.DIMMER
        assert out.output_usage == OutputUsage.OUTDOORS
        assert out.mode == OutputMode.GRADUAL
        assert out.heating_system_capability == HeatingSystemCapability.HEATING_ONLY
        assert out.heating_system_type == HeatingSystemType.WALL_HEATING

    def test_all_output_functions(self):
        host, vdc, device, vdsd = _make_stack()
        for func in OutputFunction:
            out = Output(vdsd=vdsd, function=func)
            assert out.function == func

    def test_all_output_modes(self):
        host, vdc, device, vdsd = _make_stack()
        for mode in OutputMode:
            out = Output(vdsd=vdsd, mode=mode)
            assert out.mode == mode

    def test_all_output_usages(self):
        host, vdc, device, vdsd = _make_stack()
        for usage in OutputUsage:
            out = Output(vdsd=vdsd, output_usage=usage)
            assert out.output_usage == usage


# ===========================================================================
# Repr
# ===========================================================================


class TestOutputRepr:
    """Test __repr__."""

    def test_repr(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        r = repr(out)
        assert "Output(" in r
        assert "DIMMER" in r
        assert "Test Dimmer" in r


# ===========================================================================
# Settings mutators
# ===========================================================================


class TestOutputSettingsMutators:
    """Test writable settings via property setters."""

    def test_mode_setter(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.mode = OutputMode.BINARY
        assert out.mode == OutputMode.BINARY

    def test_mode_setter_int(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.mode = 2
        assert out.mode == OutputMode.GRADUAL

    def test_active_group_setter(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.active_group = 5
        assert out.active_group == 5

    def test_groups_setter(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.groups = {1, 3, 5}
        assert out.groups == {1, 3, 5}

    def test_groups_returns_copy(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd, groups={1, 2})
        g = out.groups
        g.add(99)
        assert 99 not in out.groups

    def test_add_group(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.add_group(7)
        out.add_group(12)
        assert out.groups == {7, 12}

    def test_remove_group(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd, groups={1, 2, 3})
        out.remove_group(2)
        assert out.groups == {1, 3}

    def test_remove_group_absent(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd, groups={1})
        out.remove_group(99)
        assert out.groups == {1}

    def test_push_changes_setter(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.push_changes = True
        assert out.push_changes is True

    def test_on_threshold_setter(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.on_threshold = 33.5
        assert out.on_threshold == 33.5

    def test_on_threshold_reset(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd, on_threshold=50.0)
        out.on_threshold = None
        assert out.on_threshold is None

    def test_min_brightness_setter(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.min_brightness = 5.0
        assert out.min_brightness == 5.0

    def test_dim_time_setters(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.dim_time_up = 100
        out.dim_time_down = 80
        out.dim_time_up_alt1 = 150
        out.dim_time_down_alt1 = 120
        out.dim_time_up_alt2 = 200
        out.dim_time_down_alt2 = 180
        assert out.dim_time_up == 100
        assert out.dim_time_down == 80
        assert out.dim_time_up_alt1 == 150
        assert out.dim_time_down_alt1 == 120
        assert out.dim_time_up_alt2 == 200
        assert out.dim_time_down_alt2 == 180

    def test_dim_time_reset(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd, dim_time_up=100)
        out.dim_time_up = None
        assert out.dim_time_up is None

    def test_heating_system_capability_setter(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.heating_system_capability = HeatingSystemCapability.COOLING_ONLY
        assert out.heating_system_capability == HeatingSystemCapability.COOLING_ONLY

    def test_heating_system_capability_setter_int(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.heating_system_capability = 3
        assert out.heating_system_capability == HeatingSystemCapability.HEATING_AND_COOLING

    def test_heating_system_capability_reset(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(
            vdsd,
            heating_system_capability=HeatingSystemCapability.HEATING_ONLY,
        )
        out.heating_system_capability = None
        assert out.heating_system_capability is None

    def test_heating_system_type_setter(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.heating_system_type = HeatingSystemType.FLOOR_HEATING
        assert out.heating_system_type == HeatingSystemType.FLOOR_HEATING

    def test_heating_system_type_setter_int(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.heating_system_type = 4
        assert out.heating_system_type == HeatingSystemType.CONVECTOR_PASSIVE

    def test_heating_system_type_reset(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(
            vdsd,
            heating_system_type=HeatingSystemType.RADIATOR,
        )
        out.heating_system_type = None
        assert out.heating_system_type is None

    def test_name_setter(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.name = "New Name"
        assert out.name == "New Name"


# ===========================================================================
# State mutators
# ===========================================================================


class TestOutputStateMutators:
    """Test volatile state property setters."""

    def test_local_priority_setter(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.local_priority = True
        assert out.local_priority is True

    def test_error_setter(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.error = OutputError.LAMP_BROKEN
        assert out.error == OutputError.LAMP_BROKEN

    def test_error_setter_int(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.error = 3
        assert out.error == OutputError.OVERLOAD

    def test_all_error_values(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        for err in OutputError:
            out.error = err
            assert out.error == err


# ===========================================================================
# Description properties dict
# ===========================================================================


class TestOutputDescriptionProperties:
    """Test get_description_properties()."""

    def test_minimal(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        desc = out.get_description_properties()

        assert desc["function"] == int(OutputFunction.DIMMER)
        assert desc["outputUsage"] == int(OutputUsage.ROOM)
        assert desc["name"] == "Test Dimmer"
        assert desc["defaultGroup"] == 0
        assert desc["variableRamp"] is False
        assert "maxPower" not in desc
        assert "activeCoolingMode" not in desc

    def test_with_optional_fields(self):
        host, vdc, device, vdsd = _make_stack()
        out = Output(
            vdsd=vdsd,
            function=OutputFunction.POSITIONAL,
            max_power=240.5,
            active_cooling_mode=True,
            variable_ramp=True,
            default_group=8,
        )
        desc = out.get_description_properties()

        assert desc["maxPower"] == 240.5
        assert desc["activeCoolingMode"] is True
        assert desc["variableRamp"] is True
        assert desc["defaultGroup"] == 8


# ===========================================================================
# Settings properties dict
# ===========================================================================


class TestOutputSettingsProperties:
    """Test get_settings_properties()."""

    def test_minimal(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        settings = out.get_settings_properties()

        assert settings["mode"] == int(OutputMode.DEFAULT)
        assert settings["activeGroup"] == 0
        assert settings["pushChanges"] is False
        assert settings["groups"] == {}
        assert "onThreshold" not in settings
        assert "minBrightness" not in settings

    def test_with_groups(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd, groups={1, 3, 5})
        settings = out.get_settings_properties()

        assert "groups" in settings
        assert settings["groups"] == {"1": True, "3": True, "5": True}

    def test_with_all_optional_fields(self):
        host, vdc, device, vdsd = _make_stack()
        out = Output(
            vdsd=vdsd,
            function=OutputFunction.DIMMER,
            mode=OutputMode.GRADUAL,
            active_group=2,
            push_changes=True,
            on_threshold=50.0,
            min_brightness=5.0,
            dim_time_up=100,
            dim_time_down=80,
            dim_time_up_alt1=150,
            dim_time_down_alt1=120,
            dim_time_up_alt2=200,
            dim_time_down_alt2=180,
            heating_system_capability=HeatingSystemCapability.HEATING_AND_COOLING,
            heating_system_type=HeatingSystemType.RADIATOR,
        )
        settings = out.get_settings_properties()

        assert settings["mode"] == int(OutputMode.GRADUAL)
        assert settings["activeGroup"] == 2
        assert settings["pushChanges"] is True
        assert settings["onThreshold"] == 50.0
        assert settings["minBrightness"] == 5.0
        assert settings["dimTimeUp"] == 100
        assert settings["dimTimeDown"] == 80
        assert settings["dimTimeUpAlt1"] == 150
        assert settings["dimTimeDownAlt1"] == 120
        assert settings["dimTimeUpAlt2"] == 200
        assert settings["dimTimeDownAlt2"] == 180
        assert settings["heatingSystemCapability"] == int(
            HeatingSystemCapability.HEATING_AND_COOLING
        )
        assert settings["heatingSystemType"] == int(
            HeatingSystemType.RADIATOR
        )


# ===========================================================================
# State properties dict
# ===========================================================================


class TestOutputStateProperties:
    """Test get_state_properties()."""

    def test_defaults(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        state = out.get_state_properties()

        assert state["localPriority"] is False
        assert state["error"] == int(OutputError.OK)

    def test_after_mutation(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.local_priority = True
        out.error = OutputError.SHORT_CIRCUIT

        state = out.get_state_properties()
        assert state["localPriority"] is True
        assert state["error"] == int(OutputError.SHORT_CIRCUIT)


# ===========================================================================
# apply_settings
# ===========================================================================


class TestOutputApplySettings:
    """Test apply_settings() from vdSM setProperty."""

    def test_apply_mode(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.apply_settings({"mode": 1})
        assert out.mode == OutputMode.BINARY

    def test_apply_active_group(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.apply_settings({"activeGroup": 5})
        assert out.active_group == 5

    def test_apply_push_changes(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.apply_settings({"pushChanges": True})
        assert out.push_changes is True

    def test_apply_groups_add(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.apply_settings({"groups": {"1": True, "3": True, "5": True}})
        assert out.groups == {1, 3, 5}

    def test_apply_groups_remove(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd, groups={1, 2, 3})
        out.apply_settings({"groups": {"2": False}})
        assert out.groups == {1, 3}

    def test_apply_groups_mixed(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd, groups={1, 2})
        out.apply_settings({"groups": {"2": False, "5": True}})
        assert out.groups == {1, 5}

    def test_apply_on_threshold(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.apply_settings({"onThreshold": 42.0})
        assert out.on_threshold == 42.0

    def test_apply_on_threshold_none(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd, on_threshold=50.0)
        out.apply_settings({"onThreshold": None})
        assert out.on_threshold is None

    def test_apply_min_brightness(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.apply_settings({"minBrightness": 8.0})
        assert out.min_brightness == 8.0

    def test_apply_dim_times(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.apply_settings({
            "dimTimeUp": 100,
            "dimTimeDown": 80,
            "dimTimeUpAlt1": 150,
            "dimTimeDownAlt1": 120,
            "dimTimeUpAlt2": 200,
            "dimTimeDownAlt2": 180,
        })
        assert out.dim_time_up == 100
        assert out.dim_time_down == 80
        assert out.dim_time_up_alt1 == 150
        assert out.dim_time_down_alt1 == 120
        assert out.dim_time_up_alt2 == 200
        assert out.dim_time_down_alt2 == 180

    def test_apply_dim_time_reset(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd, dim_time_up=100)
        out.apply_settings({"dimTimeUp": None})
        assert out.dim_time_up is None

    def test_apply_heating_system_capability(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.apply_settings({"heatingSystemCapability": 2})
        assert out.heating_system_capability == HeatingSystemCapability.COOLING_ONLY

    def test_apply_heating_system_capability_reset(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(
            vdsd,
            heating_system_capability=HeatingSystemCapability.HEATING_ONLY,
        )
        out.apply_settings({"heatingSystemCapability": None})
        assert out.heating_system_capability is None

    def test_apply_heating_system_type(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.apply_settings({"heatingSystemType": 5})
        assert out.heating_system_type == HeatingSystemType.CONVECTOR_ACTIVE

    def test_apply_heating_system_type_reset(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(
            vdsd,
            heating_system_type=HeatingSystemType.RADIATOR,
        )
        out.apply_settings({"heatingSystemType": None})
        assert out.heating_system_type is None

    def test_apply_unknown_keys_ignored(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.apply_settings({"unknownKey": 42, "mode": 1})
        assert out.mode == OutputMode.BINARY

    def test_apply_empty_dict(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.apply_settings({})
        assert out.mode == OutputMode.DEFAULT

    def test_apply_multiple_settings_at_once(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.apply_settings({
            "mode": 2,
            "activeGroup": 3,
            "pushChanges": True,
            "onThreshold": 30.0,
            "minBrightness": 5.0,
        })
        assert out.mode == OutputMode.GRADUAL
        assert out.active_group == 3
        assert out.push_changes is True
        assert out.on_threshold == 30.0
        assert out.min_brightness == 5.0


# ===========================================================================
# apply_state
# ===========================================================================


class TestOutputApplyState:
    """Test apply_state() from vdSM setProperty."""

    def test_apply_local_priority(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.apply_state({"localPriority": True})
        assert out.local_priority is True

    def test_apply_state_ignores_error(self):
        """error is read-only from the vdSM perspective."""
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.apply_state({"error": 3})
        # error should NOT be changed by apply_state
        assert out.error == OutputError.OK

    def test_apply_state_empty(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.apply_state({})
        assert out.local_priority is False


# ===========================================================================
# Property tree (persistence)
# ===========================================================================


class TestOutputPropertyTree:
    """Test get_property_tree() and _apply_state() round-trip."""

    def test_minimal_tree(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        tree = out.get_property_tree()

        assert tree["function"] == int(OutputFunction.DIMMER)
        assert tree["outputUsage"] == int(OutputUsage.ROOM)
        assert tree["name"] == "Test Dimmer"
        assert tree["defaultGroup"] == 0
        assert tree["variableRamp"] is False
        assert tree["mode"] == int(OutputMode.DEFAULT)
        assert tree["activeGroup"] == 0
        assert tree["pushChanges"] is False
        assert "maxPower" not in tree
        assert "activeCoolingMode" not in tree
        assert "groups" not in tree

    def test_full_tree(self):
        host, vdc, device, vdsd = _make_stack()
        out = Output(
            vdsd=vdsd,
            function=OutputFunction.FULL_COLOR_DIMMER,
            output_usage=OutputUsage.USER,
            name="Full Colour",
            default_group=1,
            variable_ramp=True,
            max_power=300.0,
            active_cooling_mode=True,
            mode=OutputMode.GRADUAL,
            active_group=2,
            groups={1, 4, 8},
            push_changes=True,
            on_threshold=50.0,
            min_brightness=10.0,
            dim_time_up=100,
            dim_time_down=80,
            dim_time_up_alt1=150,
            dim_time_down_alt1=120,
            dim_time_up_alt2=200,
            dim_time_down_alt2=180,
            heating_system_capability=HeatingSystemCapability.HEATING_AND_COOLING,
            heating_system_type=HeatingSystemType.FLOOR_HEATING,
        )
        tree = out.get_property_tree()

        assert tree["function"] == int(OutputFunction.FULL_COLOR_DIMMER)
        assert tree["outputUsage"] == int(OutputUsage.USER)
        assert tree["name"] == "Full Colour"
        assert tree["defaultGroup"] == 1
        assert tree["variableRamp"] is True
        assert tree["maxPower"] == 300.0
        assert tree["activeCoolingMode"] is True
        assert tree["mode"] == int(OutputMode.GRADUAL)
        assert tree["activeGroup"] == 2
        assert tree["groups"] == [1, 4, 8]
        assert tree["pushChanges"] is True
        assert tree["onThreshold"] == 50.0
        assert tree["minBrightness"] == 10.0
        assert tree["dimTimeUp"] == 100
        assert tree["dimTimeDown"] == 80
        assert tree["dimTimeUpAlt1"] == 150
        assert tree["dimTimeDownAlt1"] == 120
        assert tree["dimTimeUpAlt2"] == 200
        assert tree["dimTimeDownAlt2"] == 180
        assert tree["heatingSystemCapability"] == int(
            HeatingSystemCapability.HEATING_AND_COOLING
        )
        assert tree["heatingSystemType"] == int(
            HeatingSystemType.FLOOR_HEATING
        )

    def test_state_not_in_tree(self):
        """Volatile state must NOT appear in the property tree."""
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        out.local_priority = True
        out.error = OutputError.SHORT_CIRCUIT
        tree = out.get_property_tree()

        assert "localPriority" not in tree
        assert "error" not in tree

    def test_round_trip(self):
        """Serialize → _apply_state → verify all properties match."""
        host, vdc, device, vdsd = _make_stack()
        original = Output(
            vdsd=vdsd,
            function=OutputFunction.DIMMER_COLOR_TEMP,
            output_usage=OutputUsage.OUTDOORS,
            name="Colour Temp",
            default_group=3,
            variable_ramp=True,
            max_power=60.0,
            active_cooling_mode=False,
            mode=OutputMode.GRADUAL,
            active_group=3,
            groups={2, 7, 15},
            push_changes=True,
            on_threshold=25.0,
            min_brightness=3.0,
            dim_time_up=50,
            dim_time_down=40,
            dim_time_up_alt1=75,
            dim_time_down_alt1=60,
            dim_time_up_alt2=100,
            dim_time_down_alt2=90,
            heating_system_capability=HeatingSystemCapability.COOLING_ONLY,
            heating_system_type=HeatingSystemType.CONVECTOR_ACTIVE,
        )
        tree = original.get_property_tree()

        # Restore into a fresh Output.
        restored = Output(vdsd=vdsd)
        restored._apply_state(tree)

        assert restored.function == original.function
        assert restored.output_usage == original.output_usage
        assert restored.name == original.name
        assert restored.default_group == original.default_group
        assert restored.variable_ramp == original.variable_ramp
        assert restored.max_power == original.max_power
        assert restored.active_cooling_mode == original.active_cooling_mode
        assert restored.mode == original.mode
        assert restored.active_group == original.active_group
        assert restored.groups == original.groups
        assert restored.push_changes == original.push_changes
        assert restored.on_threshold == original.on_threshold
        assert restored.min_brightness == original.min_brightness
        assert restored.dim_time_up == original.dim_time_up
        assert restored.dim_time_down == original.dim_time_down
        assert restored.dim_time_up_alt1 == original.dim_time_up_alt1
        assert restored.dim_time_down_alt1 == original.dim_time_down_alt1
        assert restored.dim_time_up_alt2 == original.dim_time_up_alt2
        assert restored.dim_time_down_alt2 == original.dim_time_down_alt2
        assert restored.heating_system_capability == original.heating_system_capability
        assert restored.heating_system_type == original.heating_system_type

    def test_groups_sorted_in_persistence(self):
        """Verify groups are stored as sorted list for determinism."""
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd, groups={30, 5, 15, 1})
        tree = out.get_property_tree()
        assert tree["groups"] == [1, 5, 15, 30]

    def test_apply_state_groups_from_dict(self):
        """_apply_state also handles groups in dict format."""
        host, vdc, device, vdsd = _make_stack()
        out = Output(vdsd=vdsd)
        out._apply_state({"groups": {"1": True, "5": True, "10": False}})
        assert out.groups == {1, 5}

    def test_apply_state_partial(self):
        """_apply_state with a subset of keys only modifies those."""
        host, vdc, device, vdsd = _make_stack()
        out = Output(
            vdsd=vdsd,
            function=OutputFunction.DIMMER,
            name="Original",
            mode=OutputMode.GRADUAL,
        )
        out._apply_state({"name": "Changed"})
        assert out.name == "Changed"
        assert out.function == OutputFunction.DIMMER
        assert out.mode == OutputMode.GRADUAL


# ===========================================================================
# Vdsd integration
# ===========================================================================


class TestVdsdOutputIntegration:
    """Test Output integration with Vdsd."""

    def test_set_output(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        vdsd.set_output(out)
        assert vdsd.output is out

    def test_set_output_replaces(self):
        host, vdc, device, vdsd = _make_stack()
        out1 = _make_output(vdsd, name="First")
        out2 = _make_output(vdsd, name="Second")
        vdsd.set_output(out1)
        vdsd.set_output(out2)
        assert vdsd.output is out2

    def test_set_output_wrong_vdsd(self):
        host, vdc, device, vdsd = _make_stack()
        other_device = Device(
            vdc=vdc,
            dsuid=DsUid.from_name_in_space("other", DsUidNamespace.VDC),
        )
        other_vdsd = Vdsd(device=other_device, name="Other")
        other_device.add_vdsd(other_vdsd)

        out = Output(vdsd=other_vdsd)
        with pytest.raises(ValueError, match="different vdSD"):
            vdsd.set_output(out)

    def test_remove_output(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        vdsd.set_output(out)
        removed = vdsd.remove_output()
        assert removed is out
        assert vdsd.output is None

    def test_remove_output_none(self):
        host, vdc, device, vdsd = _make_stack()
        assert vdsd.remove_output() is None

    def test_output_none_by_default(self):
        host, vdc, device, vdsd = _make_stack()
        assert vdsd.output is None

    def test_output_in_get_properties(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        vdsd.set_output(out)
        props = vdsd.get_properties()

        assert "outputDescription" in props
        assert "outputSettings" in props
        assert "outputState" in props
        assert props["outputDescription"]["function"] == int(OutputFunction.DIMMER)

    def test_no_output_in_get_properties(self):
        host, vdc, device, vdsd = _make_stack()
        props = vdsd.get_properties()

        assert "outputDescription" not in props
        assert "outputSettings" not in props
        assert "outputState" not in props

    def test_output_in_property_tree(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        vdsd.set_output(out)
        tree = vdsd.get_property_tree()

        assert "output" in tree
        assert tree["output"]["function"] == int(OutputFunction.DIMMER)
        assert tree["output"]["name"] == "Test Dimmer"

    def test_no_output_in_property_tree(self):
        host, vdc, device, vdsd = _make_stack()
        tree = vdsd.get_property_tree()
        assert "output" not in tree

    def test_output_restore_from_state(self):
        """Persist via property tree → restore via _apply_state."""
        host, vdc, device, vdsd = _make_stack()
        out = Output(
            vdsd=vdsd,
            function=OutputFunction.POSITIONAL,
            name="Blind Motor",
            mode=OutputMode.GRADUAL,
            active_group=9,
            groups={9},
        )
        vdsd.set_output(out)

        tree = vdsd.get_property_tree()

        # Restore into a fresh vdSD.
        host2, vdc2, device2, vdsd2 = _make_stack()
        vdsd2._apply_state(tree)

        assert vdsd2.output is not None
        assert vdsd2.output.function == OutputFunction.POSITIONAL
        assert vdsd2.output.name == "Blind Motor"
        assert vdsd2.output.mode == OutputMode.GRADUAL
        assert vdsd2.output.active_group == 9
        assert vdsd2.output.groups == {9}

    def test_output_restore_merges_with_existing(self):
        """If output already exists, _apply_state updates it."""
        host, vdc, device, vdsd = _make_stack()
        existing = Output(vdsd=vdsd, name="Existing")
        vdsd.set_output(existing)

        vdsd._apply_state({
            "output": {
                "function": int(OutputFunction.BIPOLAR),
                "name": "Updated",
            }
        })

        # Should be the same object, updated.
        assert vdsd.output is existing
        assert vdsd.output.name == "Updated"
        assert vdsd.output.function == OutputFunction.BIPOLAR


# ===========================================================================
# Session management
# ===========================================================================


class TestOutputSessionManagement:
    """Test start_session / stop_session."""

    def test_start_session(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        session = _make_mock_session()
        out.start_session(session)
        assert out._session is session

    def test_stop_session(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        session = _make_mock_session()
        out.start_session(session)
        out.stop_session()
        assert out._session is None

    def test_set_output_while_announced(self):
        """Setting output on an already-announced vdSD starts session."""
        host, vdc, device, vdsd = _make_stack()
        session = _make_mock_session()
        # Simulate announced state.
        vdsd._announced = True
        vdsd._session = session

        out = _make_output(vdsd)
        vdsd.set_output(out)
        assert out._session is session

    def test_remove_output_stops_session(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        session = _make_mock_session()
        out.start_session(session)
        vdsd.set_output(out)
        vdsd.remove_output()
        assert out._session is None


# ===========================================================================
# VdcHost setProperty integration
# ===========================================================================


class TestVdcHostOutputSetProperty:
    """Test VdcHost._apply_vdsd_set_property for outputSettings/outputState."""

    def test_apply_output_settings(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        vdsd.set_output(out)

        host._apply_vdsd_set_property(vdsd, {
            "outputSettings": {"mode": 2, "pushChanges": True},
        })

        assert out.mode == OutputMode.GRADUAL
        assert out.push_changes is True

    def test_apply_output_state(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        vdsd.set_output(out)

        host._apply_vdsd_set_property(vdsd, {
            "outputState": {"localPriority": True},
        })

        assert out.local_priority is True

    def test_apply_output_settings_no_output(self):
        """Settings for non-existing output should not crash."""
        host, vdc, device, vdsd = _make_stack()
        host._apply_vdsd_set_property(vdsd, {
            "outputSettings": {"mode": 1},
        })

    def test_apply_output_state_no_output(self):
        """State for non-existing output should not crash."""
        host, vdc, device, vdsd = _make_stack()
        host._apply_vdsd_set_property(vdsd, {
            "outputState": {"localPriority": True},
        })

    def test_apply_output_settings_not_dict(self):
        """Non-dict outputSettings should be silently ignored."""
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        vdsd.set_output(out)
        host._apply_vdsd_set_property(vdsd, {
            "outputSettings": "invalid",
        })
        assert out.mode == OutputMode.DEFAULT

    def test_apply_output_state_not_dict(self):
        """Non-dict outputState should be silently ignored."""
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        vdsd.set_output(out)
        host._apply_vdsd_set_property(vdsd, {
            "outputState": "invalid",
        })
        assert out.local_priority is False

    def test_mixed_set_property(self):
        """Verify output + other settings applied together."""
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        vdsd.set_output(out)

        host._apply_vdsd_set_property(vdsd, {
            "name": "Renamed",
            "zoneID": 42,
            "outputSettings": {"mode": 1},
            "outputState": {"localPriority": True},
        })

        assert vdsd.name == "Renamed"
        assert vdsd.zone_id == 42
        assert out.mode == OutputMode.BINARY
        assert out.local_priority is True


# ===========================================================================
# Auto-save trigger
# ===========================================================================


class TestOutputAutoSave:
    """Verify that settings changes trigger auto-save via the Device chain."""

    def _setup(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        vdsd.set_output(out)
        return host, vdc, device, vdsd, out

    def test_mode_triggers_auto_save(self):
        host, vdc, device, vdsd, out = self._setup()
        device._schedule_auto_save = MagicMock()
        out.mode = OutputMode.BINARY
        device._schedule_auto_save.assert_called()

    def test_active_group_triggers_auto_save(self):
        host, vdc, device, vdsd, out = self._setup()
        device._schedule_auto_save = MagicMock()
        out.active_group = 5
        device._schedule_auto_save.assert_called()

    def test_groups_setter_triggers_auto_save(self):
        host, vdc, device, vdsd, out = self._setup()
        device._schedule_auto_save = MagicMock()
        out.groups = {1, 2, 3}
        device._schedule_auto_save.assert_called()

    def test_add_group_triggers_auto_save(self):
        host, vdc, device, vdsd, out = self._setup()
        device._schedule_auto_save = MagicMock()
        out.add_group(7)
        device._schedule_auto_save.assert_called()

    def test_remove_group_triggers_auto_save(self):
        host, vdc, device, vdsd, out = self._setup()
        device._schedule_auto_save = MagicMock()
        out.remove_group(7)
        device._schedule_auto_save.assert_called()

    def test_push_changes_triggers_auto_save(self):
        host, vdc, device, vdsd, out = self._setup()
        device._schedule_auto_save = MagicMock()
        out.push_changes = True
        device._schedule_auto_save.assert_called()

    def test_name_triggers_auto_save(self):
        host, vdc, device, vdsd, out = self._setup()
        device._schedule_auto_save = MagicMock()
        out.name = "New Name"
        device._schedule_auto_save.assert_called()

    def test_on_threshold_triggers_auto_save(self):
        host, vdc, device, vdsd, out = self._setup()
        device._schedule_auto_save = MagicMock()
        out.on_threshold = 50.0
        device._schedule_auto_save.assert_called()

    def test_min_brightness_triggers_auto_save(self):
        host, vdc, device, vdsd, out = self._setup()
        device._schedule_auto_save = MagicMock()
        out.min_brightness = 5.0
        device._schedule_auto_save.assert_called()

    def test_dim_time_triggers_auto_save(self):
        host, vdc, device, vdsd, out = self._setup()
        device._schedule_auto_save = MagicMock()
        out.dim_time_up = 100
        device._schedule_auto_save.assert_called()

    def test_heating_capability_triggers_auto_save(self):
        host, vdc, device, vdsd, out = self._setup()
        device._schedule_auto_save = MagicMock()
        out.heating_system_capability = HeatingSystemCapability.HEATING_ONLY
        device._schedule_auto_save.assert_called()

    def test_heating_type_triggers_auto_save(self):
        host, vdc, device, vdsd, out = self._setup()
        device._schedule_auto_save = MagicMock()
        out.heating_system_type = HeatingSystemType.RADIATOR
        device._schedule_auto_save.assert_called()

    def test_apply_settings_triggers_auto_save(self):
        host, vdc, device, vdsd, out = self._setup()
        device._schedule_auto_save = MagicMock()
        out.apply_settings({"mode": 2})
        device._schedule_auto_save.assert_called()

    def test_state_does_not_trigger_auto_save(self):
        """Volatile state changes must NOT trigger auto-save."""
        host, vdc, device, vdsd, out = self._setup()
        device._schedule_auto_save = MagicMock()
        out.local_priority = True
        out.error = OutputError.OVERLOAD
        device._schedule_auto_save.assert_not_called()


# ===========================================================================
# __init__.py export
# ===========================================================================


class TestOutputExport:
    """Verify Output is accessible from the top-level package."""

    def test_import_output(self):
        from pyDSvDCAPI import Output
        assert Output is not None

    def test_output_is_same_class(self):
        from pyDSvDCAPI import Output as PkgOutput
        assert PkgOutput is Output


# ===========================================================================
# Edge cases
# ===========================================================================


class TestOutputEdgeCases:
    """Edge cases and boundary conditions."""

    def test_empty_groups_returns_empty_dict(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        settings = out.get_settings_properties()
        assert settings["groups"] == {}

    def test_empty_groups_not_in_tree(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd)
        tree = out.get_property_tree()
        assert "groups" not in tree

    def test_groups_sorted_in_tree(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd, groups={10, 3, 7, 1})
        tree = out.get_property_tree()
        assert tree["groups"] == [1, 3, 7, 10]

    def test_groups_sorted_in_settings(self):
        host, vdc, device, vdsd = _make_stack()
        out = _make_output(vdsd, groups={10, 3, 7, 1})
        settings = out.get_settings_properties()
        keys = list(settings["groups"].keys())
        assert keys == ["1", "3", "7", "10"]

    def test_on_off_output(self):
        """Basic on/off output (relay, socket)."""
        host, vdc, device, vdsd = _make_stack()
        out = Output(
            vdsd=vdsd,
            function=OutputFunction.ON_OFF,
            mode=OutputMode.BINARY,
            name="Relay",
        )
        assert out.function == OutputFunction.ON_OFF
        assert out.mode == OutputMode.BINARY

    def test_bipolar_output(self):
        """Bipolar output (e.g. ventilation direction)."""
        host, vdc, device, vdsd = _make_stack()
        out = Output(
            vdsd=vdsd,
            function=OutputFunction.BIPOLAR,
            name="Ventilation",
        )
        assert out.function == OutputFunction.BIPOLAR

    def test_internally_controlled_output(self):
        host, vdc, device, vdsd = _make_stack()
        out = Output(
            vdsd=vdsd,
            function=OutputFunction.INTERNALLY_CONTROLLED,
            name="Auto",
        )
        assert out.function == OutputFunction.INTERNALLY_CONTROLLED

    def test_climate_output(self):
        """Climate control output with heating settings."""
        host, vdc, device, vdsd = _make_stack()
        out = Output(
            vdsd=vdsd,
            function=OutputFunction.ON_OFF,
            name="FCU Valve",
            heating_system_capability=HeatingSystemCapability.HEATING_AND_COOLING,
            heating_system_type=HeatingSystemType.CONVECTOR_PASSIVE,
            active_cooling_mode=True,
        )
        desc = out.get_description_properties()
        settings = out.get_settings_properties()

        assert desc["activeCoolingMode"] is True
        assert settings["heatingSystemCapability"] == int(
            HeatingSystemCapability.HEATING_AND_COOLING
        )
        assert settings["heatingSystemType"] == int(
            HeatingSystemType.CONVECTOR_PASSIVE
        )

    def test_full_round_trip_through_vdsd(self):
        """Complete persistence round-trip through the vdSD."""
        host, vdc, device, vdsd = _make_stack()
        out = Output(
            vdsd=vdsd,
            function=OutputFunction.DIMMER,
            output_usage=OutputUsage.ROOM,
            name="Living Room Dimmer",
            default_group=1,
            mode=OutputMode.GRADUAL,
            active_group=1,
            groups={1},
            push_changes=True,
            dim_time_up=50,
            dim_time_down=40,
        )
        vdsd.set_output(out)

        # Persist.
        tree = vdsd.get_property_tree()

        # Restore.
        host2, vdc2, device2, vdsd2 = _make_stack()
        vdsd2._apply_state(tree)

        assert vdsd2.output is not None
        r = vdsd2.output
        assert r.function == OutputFunction.DIMMER
        assert r.output_usage == OutputUsage.ROOM
        assert r.name == "Living Room Dimmer"
        assert r.default_group == 1
        assert r.mode == OutputMode.GRADUAL
        assert r.active_group == 1
        assert r.groups == {1}
        assert r.push_changes is True
        assert r.dim_time_up == 50
        assert r.dim_time_down == 40
        # Volatile state should be defaults.
        assert r.local_priority is False
        assert r.error == OutputError.OK
