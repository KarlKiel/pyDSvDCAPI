"""Tests for the Device and Vdsd classes."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from pyDSvDCAPI import genericVDC_pb2 as pb
from pyDSvDCAPI.dsuid import DsUid, DsUidNamespace
from pyDSvDCAPI.enums import ColorGroup
from pyDSvDCAPI.session import VdcSession
from pyDSvDCAPI.vdc import Vdc
from pyDSvDCAPI.vdc_host import VdcHost
from pyDSvDCAPI.vdsd import ENTITY_TYPE_VDSD, Device, Vdsd


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_host(tmp_path: Optional[Path] = None, **kwargs: Any) -> VdcHost:
    kw: dict[str, Any] = {"name": "Test Host", "mac": "AA:BB:CC:DD:EE:FF"}
    if tmp_path is not None:
        kw["state_path"] = str(tmp_path / "state.yaml")
    kw.update(kwargs)
    host = VdcHost(**kw)
    host._cancel_auto_save()
    return host


def _make_vdc(host: VdcHost, **kwargs: Any) -> Vdc:
    defaults: dict[str, Any] = {
        "host": host,
        "implementation_id": "x-test-light",
        "name": "Test Light vDC",
        "model": "Test Light v1",
    }
    defaults.update(kwargs)
    return Vdc(**defaults)


def _base_dsuid() -> DsUid:
    return DsUid.from_name_in_space("test-device-1", DsUidNamespace.VDC)


def _make_device(vdc: Vdc, dsuid: Optional[DsUid] = None) -> Device:
    return Device(vdc=vdc, dsuid=dsuid or _base_dsuid())


def _make_vdsd(
    device: Device,
    subdevice_index: int = 0,
    primary_group: ColorGroup = ColorGroup.YELLOW,
    **kwargs: Any,
) -> Vdsd:
    defaults: dict[str, Any] = {
        "device": device,
        "subdevice_index": subdevice_index,
        "primary_group": primary_group,
        "name": f"Test vdSD {subdevice_index}",
    }
    defaults.update(kwargs)
    return Vdsd(**defaults)


def _make_mock_session(
    response_code: int = 0,
) -> VdcSession:
    session = MagicMock(spec=VdcSession)
    session.is_active = True

    response = pb.Message()
    response.type = pb.GENERIC_RESPONSE
    response.generic_response.code = response_code

    session.send_request = AsyncMock(return_value=response)
    session.send_notification = AsyncMock()
    return session


# ===========================================================================
# Vdsd — construction and properties
# ===========================================================================


class TestVdsdConstruction:
    """Tests for Vdsd creation and default values."""

    def test_default_construction(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(device)

        assert vdsd.entity_type == ENTITY_TYPE_VDSD
        assert vdsd.entity_type == "vdSD"
        assert vdsd.subdevice_index == 0
        assert vdsd.primary_group == ColorGroup.YELLOW
        assert vdsd.name == "Test vdSD 0"
        assert vdsd.zone_id == 0
        assert vdsd.is_announced is False
        assert vdsd.active is True
        assert vdsd.device is device

    def test_dsuid_derived_from_device(self):
        host = _make_host()
        vdc = _make_vdc(host)
        base = _base_dsuid()
        device = _make_device(vdc, base)
        vdsd = _make_vdsd(device, subdevice_index=3)

        expected = base.derive_subdevice(3)
        assert vdsd.dsuid == expected
        assert vdsd.dsuid.subdevice_index == 3

    def test_dsuid_subdevice_zero(self):
        host = _make_host()
        vdc = _make_vdc(host)
        base = _base_dsuid()
        device = _make_device(vdc, base)
        vdsd = _make_vdsd(device, subdevice_index=0)

        assert vdsd.dsuid == base.device_base()

    def test_display_id_is_hex_dsuid(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(device)

        assert vdsd.display_id == str(vdsd.dsuid)
        assert len(vdsd.display_id) == 34

    def test_model_uid_derived(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(device, model="Custom Model X")

        assert vdsd.model_uid is not None
        assert len(vdsd.model_uid) == 34  # full dSUID hex

    def test_explicit_model_uid(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(device, model_uid="my-uid-123")

        assert vdsd.model_uid == "my-uid-123"

    def test_optional_properties(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(
            device,
            hardware_version="hw-1.0",
            hardware_guid="macaddress:AABBCCDDEEFF",
            vendor_name="TestVendor",
            config_url="http://device.local",
            device_icon_16=b"\x89PNG",
            device_icon_name="icon-light",
            device_class="dS-FD",
            device_class_version="1",
        )

        assert vdsd.hardware_version == "hw-1.0"
        assert vdsd.hardware_guid == "macaddress:AABBCCDDEEFF"
        assert vdsd.vendor_name == "TestVendor"
        assert vdsd.config_url == "http://device.local"
        assert vdsd.device_icon_16 == b"\x89PNG"
        assert vdsd.device_icon_name == "icon-light"
        assert vdsd.device_class == "dS-FD"
        assert vdsd.device_class_version == "1"

    def test_primary_group_black_default(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = Vdsd(device=device)

        assert vdsd.primary_group == ColorGroup.BLACK


# ===========================================================================
# Vdsd — model features
# ===========================================================================


class TestVdsdModelFeatures:

    def test_empty_by_default(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(device)

        assert vdsd.model_features == set()

    def test_initial_features(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(
            device,
            model_features={"blink", "identification"},
        )

        assert vdsd.model_features == {"blink", "identification"}

    def test_add_feature(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(device)

        vdsd.add_model_feature("blink")
        assert "blink" in vdsd.model_features

    def test_remove_feature(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(device, model_features={"blink", "dontcare"})

        vdsd.remove_model_feature("blink")
        assert "blink" not in vdsd.model_features
        assert "dontcare" in vdsd.model_features

    def test_remove_nonexistent_is_noop(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(device)

        vdsd.remove_model_feature("nonexistent")  # should not raise

    def test_model_features_defensive_copy(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(device, model_features={"blink"})

        features = vdsd.model_features
        features.add("hacked")
        assert "hacked" not in vdsd.model_features


# ===========================================================================
# Vdsd — get_properties
# ===========================================================================


class TestVdsdGetProperties:

    def test_common_properties(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(device)

        props = vdsd.get_properties()
        assert props["type"] == "vdSD"
        assert props["dSUID"] == str(vdsd.dsuid)
        assert props["displayId"] == str(vdsd.dsuid)
        assert props["name"] == "Test vdSD 0"
        assert props["active"] is True

    def test_vdsd_specific_properties(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(
            device,
            primary_group=ColorGroup.GREY,
            zone_id=42,
            model_features={"shadeprops", "shadeposition"},
        )

        props = vdsd.get_properties()
        assert props["primaryGroup"] == int(ColorGroup.GREY)
        assert props["zoneID"] == 42
        assert props["modelFeatures"] == {
            "shadeposition": True,
            "shadeprops": True,
        }

    def test_empty_model_features(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(device)

        props = vdsd.get_properties()
        assert props["modelFeatures"] == {}


# ===========================================================================
# Vdsd — property tree (persistence)
# ===========================================================================


class TestVdsdPropertyTree:

    def test_structure(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(
            device,
            primary_group=ColorGroup.YELLOW,
            model_features={"blink"},
        )

        tree = vdsd.get_property_tree()
        assert tree["subdeviceIndex"] == 0
        assert tree["dSUID"] == str(vdsd.dsuid)
        assert tree["primaryGroup"] == int(ColorGroup.YELLOW)
        assert tree["modelFeatures"] == ["blink"]
        assert tree["name"] == "Test vdSD 0"

    def test_no_icon_bytes_in_tree(self):
        """Binary icon data should not be persisted to YAML."""
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(device, device_icon_16=b"\x89PNG")

        tree = vdsd.get_property_tree()
        assert "deviceIcon16" not in tree


# ===========================================================================
# Vdsd — state restoration
# ===========================================================================


class TestVdsdApplyState:

    def test_restore_basic_properties(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(device)

        state = {
            "name": "Restored Name",
            "zoneID": 99,
            "primaryGroup": int(ColorGroup.GREY),
            "modelFeatures": ["blink", "shadeprops"],
        }
        vdsd._apply_state(state)

        assert vdsd.name == "Restored Name"
        assert vdsd.zone_id == 99
        assert vdsd.primary_group == ColorGroup.GREY
        assert vdsd.model_features == {"blink", "shadeprops"}

    def test_restore_dsuid(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(device)

        new_dsuid = DsUid.random()
        vdsd._apply_state({"dSUID": str(new_dsuid)})
        assert vdsd.dsuid == new_dsuid

    def test_restore_preserves_unmentioned(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(device, vendor_name="OriginalVendor")

        vdsd._apply_state({"name": "Updated"})
        assert vdsd.name == "Updated"
        assert vdsd.vendor_name == "OriginalVendor"


# ===========================================================================
# Vdsd — auto-save
# ===========================================================================


class TestVdsdAutoSave:

    def test_tracked_attr_triggers_auto_save(self, tmp_path):
        host = _make_host(tmp_path)
        vdc = _make_vdc(host)
        host.add_vdc(vdc)
        host._cancel_auto_save()

        device = _make_device(vdc)
        vdsd = _make_vdsd(device)
        device.add_vdsd(vdsd)
        vdc.add_device(device)
        host._cancel_auto_save()

        # Mutate a tracked attribute.
        vdsd.name = "Changed"
        assert host._save_timer is not None
        host._cancel_auto_save()

    def test_untracked_attr_no_auto_save(self, tmp_path):
        host = _make_host(tmp_path)
        vdc = _make_vdc(host)
        host.add_vdc(vdc)
        host._cancel_auto_save()

        device = _make_device(vdc)
        vdsd = _make_vdsd(device)
        device.add_vdsd(vdsd)
        vdc.add_device(device)
        host._cancel_auto_save()

        vdsd._active = False  # not tracked
        assert host._save_timer is None


# ===========================================================================
# Device — construction and accessors
# ===========================================================================


class TestDeviceConstruction:

    def test_base_dsuid(self):
        host = _make_host()
        vdc = _make_vdc(host)
        base = DsUid.random(subdevice_index=5)
        device = Device(vdc=vdc, dsuid=base)

        # Device stores device_base (index 0)
        assert device.dsuid == base.device_base()
        assert device.dsuid.subdevice_index == 0

    def test_vdc_reference(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)

        assert device.vdc is vdc

    def test_no_vdsds_initially(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)

        assert device.vdsds == {}
        assert device.is_announced is False


# ===========================================================================
# Device — vdSD management
# ===========================================================================


class TestDeviceVdsdManagement:

    def test_add_vdsd(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(device, subdevice_index=0)

        device.add_vdsd(vdsd)
        assert device.vdsds == {0: vdsd}

    def test_add_multiple_vdsds(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        v0 = _make_vdsd(device, subdevice_index=0)
        v1 = _make_vdsd(device, subdevice_index=1)
        v2 = _make_vdsd(device, subdevice_index=2)

        device.add_vdsd(v0)
        device.add_vdsd(v1)
        device.add_vdsd(v2)

        assert len(device.vdsds) == 3
        assert device.get_vdsd(1) is v1

    def test_add_vdsd_wrong_base_raises(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        other_base = DsUid.random()
        bad_vdsd = Vdsd(
            device=Device(vdc=vdc, dsuid=other_base),
            subdevice_index=0,
        )
        # The bad_vdsd has a different base dSUID.
        with pytest.raises(ValueError, match="does not share"):
            device.add_vdsd(bad_vdsd)

    def test_add_replaces_same_index(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        v0a = _make_vdsd(device, subdevice_index=0, name="first")
        v0b = _make_vdsd(device, subdevice_index=0, name="second")

        device.add_vdsd(v0a)
        device.add_vdsd(v0b)
        assert device.get_vdsd(0).name == "second"  # type: ignore[union-attr]

    def test_remove_vdsd(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(device, subdevice_index=0)
        device.add_vdsd(vdsd)

        removed = device.remove_vdsd(0)
        assert removed is vdsd
        assert device.vdsds == {}

    def test_remove_nonexistent(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)

        assert device.remove_vdsd(99) is None

    def test_get_vdsd_by_dsuid(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        v0 = _make_vdsd(device, subdevice_index=0)
        v2 = _make_vdsd(device, subdevice_index=2)
        device.add_vdsd(v0)
        device.add_vdsd(v2)

        found = device.get_vdsd_by_dsuid(v2.dsuid)
        assert found is v2

    def test_get_vdsd_by_dsuid_not_found(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)

        assert device.get_vdsd_by_dsuid(DsUid.random()) is None


# ===========================================================================
# Device — announcement
# ===========================================================================


class TestDeviceAnnouncement:

    async def test_announce_single_vdsd(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(device, subdevice_index=0)
        device.add_vdsd(vdsd)

        session = _make_mock_session(pb.ERR_OK)
        count = await device.announce(session)

        assert count == 1
        assert vdsd.is_announced is True
        assert device.is_announced is True
        session.send_request.assert_called_once()  # type: ignore[union-attr]

    async def test_announce_multi_vdsd(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        v0 = _make_vdsd(device, subdevice_index=0)
        v1 = _make_vdsd(device, subdevice_index=1)
        device.add_vdsd(v0)
        device.add_vdsd(v1)

        session = _make_mock_session(pb.ERR_OK)
        count = await device.announce(session)

        assert count == 2
        assert v0.is_announced is True
        assert v1.is_announced is True
        assert device.is_announced is True

    async def test_announce_sends_correct_protobuf(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(device, subdevice_index=0)
        device.add_vdsd(vdsd)

        session = _make_mock_session(pb.ERR_OK)
        await device.announce(session)

        msg = session.send_request.call_args[0][0]  # type: ignore[union-attr]
        assert msg.type == pb.VDC_SEND_ANNOUNCE_DEVICE
        assert msg.vdc_send_announce_device.dSUID == str(vdsd.dsuid)
        assert msg.vdc_send_announce_device.vdc_dSUID == str(vdc.dsuid)

    async def test_announce_failure(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(device, subdevice_index=0)
        device.add_vdsd(vdsd)

        session = _make_mock_session(pb.ERR_INSUFFICIENT_STORAGE)
        count = await device.announce(session)

        assert count == 0
        assert vdsd.is_announced is False
        assert device.is_announced is False

    async def test_announce_empty_device_raises(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        session = _make_mock_session()

        with pytest.raises(RuntimeError, match="no vdSDs"):
            await device.announce(session)

    async def test_announce_already_announced_raises(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(device, subdevice_index=0)
        device.add_vdsd(vdsd)

        session = _make_mock_session(pb.ERR_OK)
        await device.announce(session)

        with pytest.raises(RuntimeError, match="already announced"):
            await device.announce(session)

    async def test_add_vdsd_to_announced_device_raises(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(device, subdevice_index=0)
        device.add_vdsd(vdsd)

        session = _make_mock_session(pb.ERR_OK)
        await device.announce(session)

        new_vdsd = _make_vdsd(device, subdevice_index=1)
        with pytest.raises(RuntimeError, match="announced device"):
            device.add_vdsd(new_vdsd)

    async def test_remove_vdsd_from_announced_device_raises(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(device, subdevice_index=0)
        device.add_vdsd(vdsd)

        session = _make_mock_session(pb.ERR_OK)
        await device.announce(session)

        with pytest.raises(RuntimeError, match="announced device"):
            device.remove_vdsd(0)


# ===========================================================================
# Device — vanish
# ===========================================================================


class TestDeviceVanish:

    async def test_vanish(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        v0 = _make_vdsd(device, subdevice_index=0)
        v1 = _make_vdsd(device, subdevice_index=1)
        device.add_vdsd(v0)
        device.add_vdsd(v1)

        session = _make_mock_session(pb.ERR_OK)
        await device.announce(session)
        assert device.is_announced is True

        await device.vanish(session)
        assert device.is_announced is False
        assert v0.is_announced is False
        assert v1.is_announced is False

    async def test_vanish_sends_correct_protobuf(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(device, subdevice_index=0)
        device.add_vdsd(vdsd)

        session = _make_mock_session(pb.ERR_OK)
        await device.announce(session)
        await device.vanish(session)

        # send_notification should have been called for VDC_SEND_VANISH
        session.send_notification.assert_called_once()  # type: ignore[union-attr]
        msg = session.send_notification.call_args[0][0]  # type: ignore[union-attr]
        assert msg.type == pb.VDC_SEND_VANISH
        assert msg.vdc_send_vanish.dSUID == str(vdsd.dsuid)


# ===========================================================================
# Device — update (vanish + modify + re-announce)
# ===========================================================================


class TestDeviceUpdate:

    async def test_update_changes_name(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(device, subdevice_index=0, name="Original")
        device.add_vdsd(vdsd)

        session = _make_mock_session(pb.ERR_OK)
        await device.announce(session)

        def modify(dev: Device) -> None:
            dev.get_vdsd(0).name = "Updated"  # type: ignore[union-attr]

        count = await device.update(session, modify)
        assert count == 1
        assert vdsd.name == "Updated"
        assert device.is_announced is True

    async def test_update_adds_vdsd(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        v0 = _make_vdsd(device, subdevice_index=0)
        device.add_vdsd(v0)

        session = _make_mock_session(pb.ERR_OK)
        await device.announce(session)

        def modify(dev: Device) -> None:
            v2 = _make_vdsd(dev, subdevice_index=2, name="Added vdSD")
            dev.add_vdsd(v2)

        count = await device.update(session, modify)
        assert count == 2  # both v0 and v2 re-announced
        assert len(device.vdsds) == 2

    async def test_update_vanishes_before_modify(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(device, subdevice_index=0)
        device.add_vdsd(vdsd)

        session = _make_mock_session(pb.ERR_OK)
        await device.announce(session)

        announced_during_modify = []

        def modify(dev: Device) -> None:
            announced_during_modify.append(dev.is_announced)

        await device.update(session, modify)
        assert announced_during_modify == [False]


# ===========================================================================
# Device — reset_announcement
# ===========================================================================


class TestDeviceResetAnnouncement:

    async def test_reset_all(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        v0 = _make_vdsd(device, subdevice_index=0)
        v1 = _make_vdsd(device, subdevice_index=1)
        device.add_vdsd(v0)
        device.add_vdsd(v1)

        session = _make_mock_session(pb.ERR_OK)
        await device.announce(session)

        device.reset_announcement()
        assert device.is_announced is False
        assert v0.is_announced is False
        assert v1.is_announced is False


# ===========================================================================
# Device — persistence
# ===========================================================================


class TestDevicePropertyTree:

    def test_tree_structure(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        v0 = _make_vdsd(device, subdevice_index=0, name="Light")
        v2 = _make_vdsd(
            device, subdevice_index=2, name="Shade",
            primary_group=ColorGroup.GREY,
        )
        device.add_vdsd(v0)
        device.add_vdsd(v2)

        tree = device.get_property_tree()
        assert tree["baseDsUID"] == str(device.dsuid)
        assert len(tree["vdsds"]) == 2
        assert tree["vdsds"][0]["subdeviceIndex"] == 0
        assert tree["vdsds"][1]["subdeviceIndex"] == 2


class TestDeviceApplyState:

    def test_restore_creates_vdsds(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)

        state = {
            "baseDsUID": str(device.dsuid),
            "vdsds": [
                {
                    "subdeviceIndex": 0,
                    "primaryGroup": int(ColorGroup.YELLOW),
                    "name": "Restored Light",
                    "zoneID": 10,
                },
                {
                    "subdeviceIndex": 2,
                    "primaryGroup": int(ColorGroup.GREY),
                    "name": "Restored Shade",
                    "zoneID": 20,
                },
            ],
        }
        device._apply_state(state)

        assert len(device.vdsds) == 2
        assert device.get_vdsd(0).name == "Restored Light"  # type: ignore[union-attr]
        assert device.get_vdsd(2).name == "Restored Shade"  # type: ignore[union-attr]
        assert device.get_vdsd(0).zone_id == 10  # type: ignore[union-attr]

    def test_restore_updates_existing(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(device, subdevice_index=0)
        device.add_vdsd(vdsd)

        device._apply_state({
            "vdsds": [{"subdeviceIndex": 0, "name": "Updated Name"}],
        })
        assert vdsd.name == "Updated Name"


# ===========================================================================
# Vdc — device integration
# ===========================================================================


class TestVdcDeviceIntegration:

    def test_add_device(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        v0 = _make_vdsd(device, subdevice_index=0)
        device.add_vdsd(v0)

        vdc.add_device(device)
        assert str(device.dsuid) in vdc.devices

    def test_remove_device(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        v0 = _make_vdsd(device, subdevice_index=0)
        device.add_vdsd(v0)
        vdc.add_device(device)

        removed = vdc.remove_device(device.dsuid)
        assert removed is device
        assert vdc.devices == {}

    def test_get_device(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdc.add_device(device)

        found = vdc.get_device(device.dsuid)
        assert found is device

    def test_get_vdsd_by_dsuid(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        v0 = _make_vdsd(device, subdevice_index=0)
        v2 = _make_vdsd(device, subdevice_index=2)
        device.add_vdsd(v0)
        device.add_vdsd(v2)
        vdc.add_device(device)

        found = vdc.get_vdsd_by_dsuid(v2.dsuid)
        assert found is v2

    def test_get_vdsd_by_dsuid_not_found(self):
        host = _make_host()
        vdc = _make_vdc(host)

        assert vdc.get_vdsd_by_dsuid(DsUid.random()) is None

    async def test_announce_devices(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        v0 = _make_vdsd(device, subdevice_index=0)
        device.add_vdsd(v0)
        vdc.add_device(device)

        session = _make_mock_session(pb.ERR_OK)
        total = await vdc.announce_devices(session)

        assert total == 1
        assert v0.is_announced is True


# ===========================================================================
# Vdc — persistence round-trip with devices
# ===========================================================================


class TestVdcPersistenceWithDevices:

    def test_property_tree_includes_devices(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        v0 = _make_vdsd(device, subdevice_index=0, name="Light")
        device.add_vdsd(v0)
        vdc.add_device(device)

        tree = vdc.get_property_tree()
        assert "devices" in tree
        assert len(tree["devices"]) == 1
        assert tree["devices"][0]["baseDsUID"] == str(device.dsuid)

    def test_property_tree_no_devices_key_when_empty(self):
        host = _make_host()
        vdc = _make_vdc(host)

        tree = vdc.get_property_tree()
        assert "devices" not in tree

    def test_apply_state_restores_devices(self):
        host = _make_host()
        vdc = _make_vdc(host)

        base = _base_dsuid()
        state = {
            "devices": [{
                "baseDsUID": str(base.device_base()),
                "vdsds": [{
                    "subdeviceIndex": 0,
                    "primaryGroup": int(ColorGroup.YELLOW),
                    "name": "Persisted Light",
                    "zoneID": 42,
                }],
            }],
        }
        vdc._apply_state(state)

        assert len(vdc.devices) == 1
        device = list(vdc.devices.values())[0]
        assert device.get_vdsd(0).name == "Persisted Light"  # type: ignore[union-attr]

    def test_full_persistence_roundtrip(self, tmp_path):
        """Save and reload via VdcHost YAML persistence."""
        host = _make_host(tmp_path)
        vdc = _make_vdc(host)
        host.add_vdc(vdc)
        host._cancel_auto_save()

        base = _base_dsuid()
        device = Device(vdc=vdc, dsuid=base)
        v0 = Vdsd(
            device=device, subdevice_index=0,
            primary_group=ColorGroup.YELLOW,
            name="Kitchen Light",
            model="Light v1",
            zone_id=5,
            model_features={"blink", "identification"},
        )
        v2 = Vdsd(
            device=device, subdevice_index=2,
            primary_group=ColorGroup.GREY,
            name="Kitchen Shade",
            model="Shade v1",
            zone_id=5,
        )
        device.add_vdsd(v0)
        device.add_vdsd(v2)
        vdc.add_device(device)

        # Save.
        host.save()

        # Verify YAML has device data.
        state_path = tmp_path / "state.yaml"
        data = yaml.safe_load(state_path.read_text())
        vdc_data = data["vdcHost"]["vdcs"][0]
        assert "devices" in vdc_data
        assert len(vdc_data["devices"]) == 1
        assert len(vdc_data["devices"][0]["vdsds"]) == 2

        # Reload into a fresh host.
        host2 = VdcHost(
            name="Test Host",
            mac="AA:BB:CC:DD:EE:FF",
            state_path=str(state_path),
        )
        host2._cancel_auto_save()

        # The vDC and devices should be restored.
        vdc2 = host2.get_vdc(vdc.dsuid)
        assert vdc2 is not None

        assert len(vdc2.devices) == 1
        dev2 = list(vdc2.devices.values())[0]
        assert dev2.dsuid == base.device_base()
        assert len(dev2.vdsds) == 2

        r0 = dev2.get_vdsd(0)
        r2 = dev2.get_vdsd(2)
        assert r0 is not None
        assert r2 is not None
        assert r0.name == "Kitchen Light"
        assert r0.primary_group == ColorGroup.YELLOW
        assert r0.zone_id == 5
        assert r0.model_features == {"blink", "identification"}
        assert r2.name == "Kitchen Shade"
        assert r2.primary_group == ColorGroup.GREY


# ===========================================================================
# Vdc — reset_announcement cascades to devices
# ===========================================================================


class TestVdcResetCascade:

    async def test_reset_cascades(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(device, subdevice_index=0)
        device.add_vdsd(vdsd)
        vdc.add_device(device)

        # Simulate announcement.
        session = _make_mock_session(pb.ERR_OK)
        await device.announce(session)
        assert vdsd.is_announced is True

        vdc.reset_announcement()
        assert vdc.is_announced is False
        assert device.is_announced is False
        assert vdsd.is_announced is False


# ===========================================================================
# VdcHost — property dispatch for vdSD entities
# ===========================================================================


class TestVdcHostVdsdPropertyDispatch:

    def test_resolve_vdsd_entity(self):
        host = _make_host()
        vdc = _make_vdc(host)
        host.add_vdc(vdc)
        host._cancel_auto_save()

        device = _make_device(vdc)
        vdsd = _make_vdsd(device, subdevice_index=0)
        device.add_vdsd(vdsd)
        vdc.add_device(device)
        host._cancel_auto_save()

        props = host._resolve_entity(str(vdsd.dsuid))
        assert props is not None
        assert props["type"] == "vdSD"
        assert props["dSUID"] == str(vdsd.dsuid)

    def test_resolve_unknown_returns_none(self):
        host = _make_host()
        assert host._resolve_entity("FF" * 17) is None

    def test_get_property_for_vdsd(self):
        host = _make_host()
        vdc = _make_vdc(host)
        host.add_vdc(vdc)
        host._cancel_auto_save()

        device = _make_device(vdc)
        vdsd = _make_vdsd(
            device, subdevice_index=0,
            primary_group=ColorGroup.YELLOW,
            name="Test Light",
        )
        device.add_vdsd(vdsd)
        vdc.add_device(device)
        host._cancel_auto_save()

        # Build a getProperty request for the vdSD.
        req = pb.Message()
        req.type = pb.VDSM_REQUEST_GET_PROPERTY
        req.message_id = 100
        req.vdsm_request_get_property.dSUID = str(vdsd.dsuid)
        # Wildcard query.
        req.vdsm_request_get_property.query.add()

        resp = host._handle_get_property(req)
        assert resp.type == pb.VDC_RESPONSE_GET_PROPERTY

    def test_set_property_name_for_vdsd(self):
        host = _make_host()
        vdc = _make_vdc(host)
        host.add_vdc(vdc)
        host._cancel_auto_save()

        device = _make_device(vdc)
        vdsd = _make_vdsd(device, subdevice_index=0, name="Original")
        device.add_vdsd(vdsd)
        vdc.add_device(device)
        host._cancel_auto_save()

        # Build a setProperty request.
        req = pb.Message()
        req.type = pb.VDSM_REQUEST_SET_PROPERTY
        req.message_id = 200
        req.vdsm_request_set_property.dSUID = str(vdsd.dsuid)
        elem = req.vdsm_request_set_property.properties.add()
        elem.name = "name"
        elem.value.v_string = "New Name"

        resp = host._handle_set_property(req)
        assert resp.generic_response.code == pb.ERR_OK
        assert vdsd.name == "New Name"

    def test_set_property_zone_for_vdsd(self):
        host = _make_host()
        vdc = _make_vdc(host)
        host.add_vdc(vdc)
        host._cancel_auto_save()

        device = _make_device(vdc)
        vdsd = _make_vdsd(device, subdevice_index=0)
        device.add_vdsd(vdsd)
        vdc.add_device(device)
        host._cancel_auto_save()

        req = pb.Message()
        req.type = pb.VDSM_REQUEST_SET_PROPERTY
        req.message_id = 201
        req.vdsm_request_set_property.dSUID = str(vdsd.dsuid)
        elem = req.vdsm_request_set_property.properties.add()
        elem.name = "zoneID"
        elem.value.v_uint64 = 42

        resp = host._handle_set_property(req)
        assert resp.generic_response.code == pb.ERR_OK
        assert vdsd.zone_id == 42


# ===========================================================================
# Multi-vdSD device — dSUID relationships
# ===========================================================================


class TestMultiVdsdDsuid:
    """Verifies that multi-vdSD devices correctly share base dSUIDs."""

    def test_siblings_same_device(self):
        host = _make_host()
        vdc = _make_vdc(host)
        base = DsUid.from_enocean("0512ABCD")
        device = Device(vdc=vdc, dsuid=base)

        v0 = Vdsd(device=device, subdevice_index=0,
                   primary_group=ColorGroup.YELLOW)
        v2 = Vdsd(device=device, subdevice_index=2,
                   primary_group=ColorGroup.GREY)
        device.add_vdsd(v0)
        device.add_vdsd(v2)

        assert v0.dsuid.same_device(v2.dsuid)
        assert v0.dsuid != v2.dsuid
        assert v0.dsuid.subdevice_index == 0
        assert v2.dsuid.subdevice_index == 2

    def test_device_base_matches(self):
        host = _make_host()
        vdc = _make_vdc(host)
        base = DsUid.from_enocean("0512ABCD")
        device = Device(vdc=vdc, dsuid=base)
        v0 = Vdsd(device=device, subdevice_index=0)
        v3 = Vdsd(device=device, subdevice_index=3)

        assert v0.dsuid.device_base() == device.dsuid
        assert v3.dsuid.device_base() == device.dsuid

    def test_separate_devices_different_base(self):
        host = _make_host()
        vdc = _make_vdc(host)

        d1 = Device(vdc=vdc, dsuid=DsUid.random())
        d2 = Device(vdc=vdc, dsuid=DsUid.random())

        v1 = Vdsd(device=d1, subdevice_index=0)
        v2 = Vdsd(device=d2, subdevice_index=0)

        assert not v1.dsuid.same_device(v2.dsuid)


# ===========================================================================
# repr
# ===========================================================================


class TestRepr:

    def test_vdsd_repr(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        vdsd = _make_vdsd(device, name="MyDevice")

        r = repr(vdsd)
        assert "Vdsd" in r
        assert "MyDevice" in r

    def test_device_repr(self):
        host = _make_host()
        vdc = _make_vdc(host)
        device = _make_device(vdc)
        v0 = _make_vdsd(device, subdevice_index=0)
        device.add_vdsd(v0)

        r = repr(device)
        assert "Device" in r
        assert "vdsds=1" in r
