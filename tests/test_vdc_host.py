"""Tests for the VdcHost class."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pyDSvDCAPI.dsuid import DsUid, DsUidNamespace
from pyDSvDCAPI.vdc_host import (
    DEFAULT_VDC_PORT,
    ENTITY_TYPE_VDC_HOST,
    VDC_SERVICE_TYPE,
    VdcHost,
)


# ---------------------------------------------------------------------------
# A fixed MAC for deterministic tests
# ---------------------------------------------------------------------------
TEST_MAC = "AA:BB:CC:DD:EE:FF"


# ---------------------------------------------------------------------------
# Construction & defaults
# ---------------------------------------------------------------------------

class TestConstruction:

    def test_default_port(self):
        host = VdcHost(mac=TEST_MAC)
        assert host.port == DEFAULT_VDC_PORT
        assert host.port == 8444

    def test_custom_port(self):
        host = VdcHost(mac=TEST_MAC, port=9999)
        assert host.port == 9999

    def test_entity_type(self):
        host = VdcHost(mac=TEST_MAC)
        assert host.entity_type == "vDChost"

    def test_mac_stored(self):
        host = VdcHost(mac=TEST_MAC)
        assert host.mac == TEST_MAC

    def test_default_name(self):
        host = VdcHost(mac=TEST_MAC)
        assert "vDC host on" in host.name

    def test_custom_name(self):
        host = VdcHost(mac=TEST_MAC, name="My Gateway")
        assert host.name == "My Gateway"

    def test_default_model(self):
        host = VdcHost(mac=TEST_MAC)
        assert host.model == "pyDSvDCAPI vDC host"

    def test_custom_model(self):
        host = VdcHost(mac=TEST_MAC, model="Custom Model")
        assert host.model == "Custom Model"


# ---------------------------------------------------------------------------
# dSUID derivation
# ---------------------------------------------------------------------------

class TestDsuidDerivation:

    def test_dsuid_derived_from_mac(self):
        host = VdcHost(mac=TEST_MAC)
        expected = DsUid.from_vdc_mac(TEST_MAC)
        assert host.dsuid == expected

    def test_dsuid_deterministic(self):
        h1 = VdcHost(mac=TEST_MAC)
        h2 = VdcHost(mac=TEST_MAC)
        assert h1.dsuid == h2.dsuid

    def test_different_mac_different_dsuid(self):
        h1 = VdcHost(mac="11:22:33:44:55:66")
        h2 = VdcHost(mac="AA:BB:CC:DD:EE:FF")
        assert h1.dsuid != h2.dsuid

    def test_explicit_dsuid_overrides(self):
        custom = DsUid.random()
        host = VdcHost(mac=TEST_MAC, dsuid=custom)
        assert host.dsuid == custom

    def test_dsuid_string_is_34_hex(self):
        host = VdcHost(mac=TEST_MAC)
        assert len(str(host.dsuid)) == 34


# ---------------------------------------------------------------------------
# Auto-derived properties
# ---------------------------------------------------------------------------

class TestDerivedProperties:

    def test_hardware_guid_from_mac(self):
        host = VdcHost(mac=TEST_MAC)
        assert host.hardware_guid == f"macaddress:{TEST_MAC}"

    def test_hardware_guid_explicit(self):
        host = VdcHost(mac=TEST_MAC, hardware_guid="uuid:test-1234")
        assert host.hardware_guid == "uuid:test-1234"

    def test_display_id_matches_dsuid(self):
        host = VdcHost(mac=TEST_MAC)
        assert host.display_id == str(host.dsuid)

    def test_model_uid_deterministic(self):
        h1 = VdcHost(mac=TEST_MAC, model="TestModel")
        h2 = VdcHost(mac=TEST_MAC, model="TestModel")
        assert h1.model_uid == h2.model_uid

    def test_model_uid_differs_for_different_models(self):
        h1 = VdcHost(mac=TEST_MAC, model="ModelA")
        h2 = VdcHost(mac=TEST_MAC, model="ModelB")
        assert h1.model_uid != h2.model_uid

    def test_model_uid_explicit(self):
        host = VdcHost(mac=TEST_MAC, model_uid="custom-uid")
        assert host.model_uid == "custom-uid"


# ---------------------------------------------------------------------------
# Optional properties
# ---------------------------------------------------------------------------

class TestOptionalProperties:

    def test_optional_fields_default_none(self):
        host = VdcHost(mac=TEST_MAC)
        assert host.model_version is None
        assert host.hardware_version is None
        assert host.hardware_model_guid is None
        assert host.vendor_name is None
        assert host.vendor_guid is None
        assert host.oem_guid is None
        assert host.oem_model_guid is None
        assert host.config_url is None
        assert host.device_icon_16 is None
        assert host.device_icon_name is None

    def test_optional_fields_set(self):
        host = VdcHost(
            mac=TEST_MAC,
            model_version="1.2.3",
            hardware_version="rev-B",
            vendor_name="TestCorp",
            config_url="http://192.168.1.1/config",
        )
        assert host.model_version == "1.2.3"
        assert host.hardware_version == "rev-B"
        assert host.vendor_name == "TestCorp"
        assert host.config_url == "http://192.168.1.1/config"


# ---------------------------------------------------------------------------
# Active state
# ---------------------------------------------------------------------------

class TestActiveState:

    def test_default_active(self):
        host = VdcHost(mac=TEST_MAC)
        assert host.active is True

    def test_set_inactive(self):
        host = VdcHost(mac=TEST_MAC)
        host.active = False
        assert host.active is False


# ---------------------------------------------------------------------------
# get_properties()
# ---------------------------------------------------------------------------

class TestGetProperties:

    def test_returns_dict(self):
        host = VdcHost(mac=TEST_MAC, name="Test")
        props = host.get_properties()
        assert isinstance(props, dict)

    def test_contains_required_keys(self):
        host = VdcHost(mac=TEST_MAC)
        props = host.get_properties()
        required = {
            "dSUID", "displayId", "type", "model", "name", "active",
        }
        assert required.issubset(props.keys())

    def test_type_is_vdchost(self):
        host = VdcHost(mac=TEST_MAC)
        assert host.get_properties()["type"] == "vDChost"

    def test_dsuid_in_properties(self):
        host = VdcHost(mac=TEST_MAC)
        props = host.get_properties()
        assert props["dSUID"] == str(host.dsuid)

    def test_name_in_properties(self):
        host = VdcHost(mac=TEST_MAC, name="PropTest")
        assert host.get_properties()["name"] == "PropTest"


# ---------------------------------------------------------------------------
# Auto-detection of MAC (no MAC given)
# ---------------------------------------------------------------------------

class TestAutoMac:

    def test_auto_mac_produces_valid_dsuid(self):
        """When no MAC is given, the host should still produce a valid
        dSUID from the auto-detected MAC."""
        host = VdcHost()
        assert len(str(host.dsuid)) == 34
        assert host.mac  # non-empty


# ---------------------------------------------------------------------------
# DNS-SD announcement (mocked zeroconf)
# ---------------------------------------------------------------------------

class TestAnnouncement:

    @pytest.mark.asyncio
    @patch("pyDSvDCAPI.vdc_host.AsyncZeroconf")
    async def test_announce_registers_service(self, MockAsyncZC):
        mock_zc = MagicMock()
        mock_zc.async_register_service = AsyncMock()
        mock_zc.async_unregister_service = AsyncMock()
        mock_zc.async_close = AsyncMock()
        MockAsyncZC.return_value = mock_zc

        host = VdcHost(mac=TEST_MAC)
        await host.announce()

        assert host.is_announced
        mock_zc.async_register_service.assert_called_once()

        # Inspect the ServiceInfo that was registered
        call_args = mock_zc.async_register_service.call_args
        info = call_args[0][0]
        assert info.type == VDC_SERVICE_TYPE
        assert info.port == DEFAULT_VDC_PORT

        await host.unannounce()

    @pytest.mark.asyncio
    @patch("pyDSvDCAPI.vdc_host.AsyncZeroconf")
    async def test_announce_twice_is_noop(self, MockAsyncZC):
        mock_zc = MagicMock()
        mock_zc.async_register_service = AsyncMock()
        mock_zc.async_unregister_service = AsyncMock()
        mock_zc.async_close = AsyncMock()
        MockAsyncZC.return_value = mock_zc

        host = VdcHost(mac=TEST_MAC)
        await host.announce()
        await host.announce()  # second call should be a no-op

        assert MockAsyncZC.call_count == 1
        assert mock_zc.async_register_service.call_count == 1

        await host.unannounce()

    @pytest.mark.asyncio
    @patch("pyDSvDCAPI.vdc_host.AsyncZeroconf")
    async def test_unannounce(self, MockAsyncZC):
        mock_zc = MagicMock()
        mock_zc.async_register_service = AsyncMock()
        mock_zc.async_unregister_service = AsyncMock()
        mock_zc.async_close = AsyncMock()
        MockAsyncZC.return_value = mock_zc

        host = VdcHost(mac=TEST_MAC)
        await host.announce()
        await host.unannounce()

        assert not host.is_announced
        mock_zc.async_unregister_service.assert_called_once()
        mock_zc.async_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_unannounce_without_announce_is_noop(self):
        host = VdcHost(mac=TEST_MAC)
        await host.unannounce()  # should not raise
        assert not host.is_announced

    @pytest.mark.asyncio
    @patch("pyDSvDCAPI.vdc_host.AsyncZeroconf")
    async def test_service_contains_dsuid_txt(self, MockAsyncZC):
        mock_zc = MagicMock()
        mock_zc.async_register_service = AsyncMock()
        mock_zc.async_unregister_service = AsyncMock()
        mock_zc.async_close = AsyncMock()
        MockAsyncZC.return_value = mock_zc

        host = VdcHost(mac=TEST_MAC)
        await host.announce()

        info = mock_zc.async_register_service.call_args[0][0]
        # ServiceInfo properties should include the dSUID
        assert info.properties[b"dSUID"] == str(host.dsuid).encode("utf-8")

        await host.unannounce()

    @pytest.mark.asyncio
    @patch("pyDSvDCAPI.vdc_host.AsyncZeroconf")
    async def test_custom_port_in_announcement(self, MockAsyncZC):
        mock_zc = MagicMock()
        mock_zc.async_register_service = AsyncMock()
        mock_zc.async_unregister_service = AsyncMock()
        mock_zc.async_close = AsyncMock()
        MockAsyncZC.return_value = mock_zc

        host = VdcHost(mac=TEST_MAC, port=9999)
        await host.announce()

        info = mock_zc.async_register_service.call_args[0][0]
        assert info.port == 9999

        await host.unannounce()

    @pytest.mark.asyncio
    @patch("pyDSvDCAPI.vdc_host.AsyncZeroconf")
    async def test_service_name_uses_host_name(self, MockAsyncZC):
        mock_zc = MagicMock()
        mock_zc.async_register_service = AsyncMock()
        mock_zc.async_unregister_service = AsyncMock()
        mock_zc.async_close = AsyncMock()
        MockAsyncZC.return_value = mock_zc

        host = VdcHost(mac=TEST_MAC, name="My Custom Host")
        await host.announce()

        info = mock_zc.async_register_service.call_args[0][0]
        assert info.name.startswith("My Custom Host on ")

        await host.unannounce()


# ---------------------------------------------------------------------------
# repr
# ---------------------------------------------------------------------------

class TestRepr:

    def test_repr_contains_key_info(self):
        host = VdcHost(mac=TEST_MAC, name="TestHost")
        r = repr(host)
        assert "VdcHost" in r
        assert "TestHost" in r
        assert str(host.port) in r
