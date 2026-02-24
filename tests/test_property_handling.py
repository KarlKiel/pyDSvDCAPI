"""Tests for the property_handling module."""

from __future__ import annotations

from typing import Any, Dict

import pytest

from pyDSvDCAPI import genericVDC_pb2 as pb
from pyDSvDCAPI.property_handling import (
    build_get_property_response,
    dict_to_elements,
    elements_to_dict,
    match_query,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_PROPERTIES: Dict[str, Any] = {
    "dSUID": "AABB00112233445566778899AABB001122",
    "name": "Test Entity",
    "model": "Test Model v1",
    "active": True,
    "zoneID": 42,
    "configURL": None,
    "capabilities": {
        "metering": False,
        "identification": True,
        "dynamicDefinitions": False,
    },
}


def _make_query(*names: str) -> list:
    """Build a simple flat query with the given property names."""
    return [pb.PropertyElement(name=n) for n in names]


# ---------------------------------------------------------------------------
# dict_to_elements
# ---------------------------------------------------------------------------


class TestDictToElements:

    def test_string_value(self):
        elems = dict_to_elements({"name": "hello"})
        assert len(elems) == 1
        assert elems[0].name == "name"
        assert elems[0].value.v_string == "hello"

    def test_int_value(self):
        elems = dict_to_elements({"zoneID": 7})
        assert len(elems) == 1
        assert elems[0].value.v_uint64 == 7

    def test_negative_int_value(self):
        elems = dict_to_elements({"offset": -3})
        assert len(elems) == 1
        assert elems[0].value.v_int64 == -3

    def test_bool_value(self):
        elems = dict_to_elements({"active": True})
        assert len(elems) == 1
        assert elems[0].value.v_bool is True

    def test_float_value(self):
        elems = dict_to_elements({"temp": 20.5})
        assert len(elems) == 1
        assert elems[0].value.v_double == 20.5

    def test_bytes_value(self):
        elems = dict_to_elements({"icon": b"\x89PNG"})
        assert len(elems) == 1
        assert elems[0].value.v_bytes == b"\x89PNG"

    def test_none_value(self):
        elems = dict_to_elements({"configURL": None})
        assert len(elems) == 1
        assert elems[0].name == "configURL"
        # Empty PropertyValue = explicit NULL.
        pv = elems[0].value
        assert not pv.HasField("v_string")
        assert not pv.HasField("v_bool")

    def test_nested_dict(self):
        elems = dict_to_elements({
            "capabilities": {"metering": True, "identification": False},
        })
        assert len(elems) == 1
        cap = elems[0]
        assert cap.name == "capabilities"
        assert len(cap.elements) == 2
        sub_names = {e.name for e in cap.elements}
        assert sub_names == {"metering", "identification"}

    def test_multiple_keys(self):
        elems = dict_to_elements({"a": "x", "b": 1, "c": True})
        assert len(elems) == 3


# ---------------------------------------------------------------------------
# elements_to_dict (inverse)
# ---------------------------------------------------------------------------


class TestElementsToDict:

    def test_simple_values(self):
        elems = [
            pb.PropertyElement(
                name="name",
                value=pb.PropertyValue(v_string="TestName"),
            ),
            pb.PropertyElement(
                name="zoneID",
                value=pb.PropertyValue(v_int64=42),
            ),
            pb.PropertyElement(
                name="active",
                value=pb.PropertyValue(v_bool=True),
            ),
        ]
        d = elements_to_dict(elems)
        assert d == {"name": "TestName", "zoneID": 42, "active": True}

    def test_nested(self):
        elems = [
            pb.PropertyElement(
                name="caps",
                elements=[
                    pb.PropertyElement(
                        name="metering",
                        value=pb.PropertyValue(v_bool=False),
                    ),
                ],
            ),
        ]
        d = elements_to_dict(elems)
        assert d == {"caps": {"metering": False}}

    def test_empty_name_skipped(self):
        elems = [
            pb.PropertyElement(
                name="", value=pb.PropertyValue(v_string="x")
            ),
        ]
        d = elements_to_dict(elems)
        assert d == {}

    def test_round_trip(self):
        original = {"name": "Test", "zoneID": 5, "active": True}
        elems = dict_to_elements(original)
        restored = elements_to_dict(elems)
        assert restored == original


# ---------------------------------------------------------------------------
# match_query
# ---------------------------------------------------------------------------


class TestMatchQuery:

    def test_specific_property(self):
        result = match_query(SAMPLE_PROPERTIES, _make_query("name"))
        assert len(result) == 1
        assert result[0].name == "name"
        assert result[0].value.v_string == "Test Entity"

    def test_multiple_specific_properties(self):
        result = match_query(
            SAMPLE_PROPERTIES, _make_query("name", "zoneID")
        )
        assert len(result) == 2
        names = {e.name for e in result}
        assert names == {"name", "zoneID"}

    def test_unknown_property_omitted(self):
        result = match_query(
            SAMPLE_PROPERTIES, _make_query("nonexistent")
        )
        assert len(result) == 0

    def test_wildcard_returns_all(self):
        result = match_query(SAMPLE_PROPERTIES, _make_query(""))
        names = {e.name for e in result}
        assert names == set(SAMPLE_PROPERTIES.keys())

    def test_nested_property_direct(self):
        query = [
            pb.PropertyElement(
                name="capabilities",
                elements=[pb.PropertyElement(name="metering")],
            )
        ]
        result = match_query(SAMPLE_PROPERTIES, query)
        assert len(result) == 1
        cap = result[0]
        assert cap.name == "capabilities"
        assert len(cap.elements) == 1
        assert cap.elements[0].name == "metering"
        assert cap.elements[0].value.v_bool is False

    def test_nested_wildcard(self):
        query = [
            pb.PropertyElement(
                name="capabilities",
                elements=[pb.PropertyElement(name="")],
            )
        ]
        result = match_query(SAMPLE_PROPERTIES, query)
        cap = result[0]
        sub_names = {e.name for e in cap.elements}
        assert sub_names == {
            "metering", "identification", "dynamicDefinitions"
        }

    def test_nested_no_sub_query_expands_all(self):
        query = _make_query("capabilities")
        result = match_query(SAMPLE_PROPERTIES, query)
        cap = result[0]
        sub_names = {e.name for e in cap.elements}
        assert sub_names == {
            "metering", "identification", "dynamicDefinitions"
        }

    def test_null_value(self):
        result = match_query(SAMPLE_PROPERTIES, _make_query("configURL"))
        assert len(result) == 1
        pv = result[0].value
        # None should produce an empty PropertyValue.
        assert not pv.HasField("v_string")

    def test_bool_not_confused_with_int(self):
        result = match_query(SAMPLE_PROPERTIES, _make_query("active"))
        assert result[0].value.v_bool is True
        # Should NOT be in v_int64.
        assert not result[0].value.HasField("v_int64")


# ---------------------------------------------------------------------------
# build_get_property_response
# ---------------------------------------------------------------------------


class TestBuildGetPropertyResponse:

    def test_returns_correct_message_type(self):
        req = pb.Message()
        req.type = pb.VDSM_REQUEST_GET_PROPERTY
        req.message_id = 42
        req.vdsm_request_get_property.dSUID = "test"
        q = req.vdsm_request_get_property.query.add()
        q.name = "name"

        resp = build_get_property_response(req, SAMPLE_PROPERTIES)
        assert resp.type == pb.VDC_RESPONSE_GET_PROPERTY
        assert resp.message_id == 42

    def test_response_contains_queried_properties(self):
        req = pb.Message()
        req.type = pb.VDSM_REQUEST_GET_PROPERTY
        req.message_id = 1
        q = req.vdsm_request_get_property.query.add()
        q.name = "name"
        q2 = req.vdsm_request_get_property.query.add()
        q2.name = "model"

        resp = build_get_property_response(req, SAMPLE_PROPERTIES)
        props = resp.vdc_response_get_property.properties
        assert len(props) == 2
        names = {p.name for p in props}
        assert names == {"name", "model"}

    def test_wildcard_query(self):
        req = pb.Message()
        req.type = pb.VDSM_REQUEST_GET_PROPERTY
        req.message_id = 1
        q = req.vdsm_request_get_property.query.add()
        q.name = ""  # wildcard

        resp = build_get_property_response(req, SAMPLE_PROPERTIES)
        props = resp.vdc_response_get_property.properties
        names = {p.name for p in props}
        assert names == set(SAMPLE_PROPERTIES.keys())


# ---------------------------------------------------------------------------
# VdcHost property dispatch integration
# ---------------------------------------------------------------------------


class TestVdcHostPropertyDispatch:
    """Tests for VdcHost._handle_get_property / _handle_set_property."""

    def _make_host(self):
        from pyDSvDCAPI.vdc_host import VdcHost
        host = VdcHost(
            name="Test Host",
            mac="AA:BB:CC:DD:EE:FF",
        )
        host._cancel_auto_save()
        return host

    def test_get_property_host(self):
        host = self._make_host()
        req = pb.Message()
        req.type = pb.VDSM_REQUEST_GET_PROPERTY
        req.message_id = 10
        req.vdsm_request_get_property.dSUID = str(host.dsuid)
        q = req.vdsm_request_get_property.query.add()
        q.name = "name"

        resp = host._handle_get_property(req)
        assert resp.type == pb.VDC_RESPONSE_GET_PROPERTY
        assert resp.message_id == 10
        props = resp.vdc_response_get_property.properties
        assert len(props) == 1
        assert props[0].name == "name"
        assert props[0].value.v_string == "Test Host"

    def test_get_property_vdc(self):
        from pyDSvDCAPI.vdc import Vdc
        host = self._make_host()
        vdc = Vdc(
            host=host,
            implementation_id="x-test-prop",
            name="PropTest vDC",
        )
        host.add_vdc(vdc)
        host._cancel_auto_save()

        req = pb.Message()
        req.type = pb.VDSM_REQUEST_GET_PROPERTY
        req.message_id = 11
        req.vdsm_request_get_property.dSUID = str(vdc.dsuid)
        q = req.vdsm_request_get_property.query.add()
        q.name = "name"

        resp = host._handle_get_property(req)
        assert resp.type == pb.VDC_RESPONSE_GET_PROPERTY
        props = resp.vdc_response_get_property.properties
        assert props[0].value.v_string == "PropTest vDC"

    def test_get_property_unknown_dsuid(self):
        host = self._make_host()
        req = pb.Message()
        req.type = pb.VDSM_REQUEST_GET_PROPERTY
        req.message_id = 12
        req.vdsm_request_get_property.dSUID = "0" * 34

        resp = host._handle_get_property(req)
        assert resp.type == pb.GENERIC_RESPONSE
        assert resp.generic_response.code == pb.ERR_NOT_FOUND

    def test_set_property_host_name(self):
        host = self._make_host()
        req = pb.Message()
        req.type = pb.VDSM_REQUEST_SET_PROPERTY
        req.message_id = 20
        req.vdsm_request_set_property.dSUID = str(host.dsuid)
        p = req.vdsm_request_set_property.properties.add()
        p.name = "name"
        p.value.v_string = "New Host Name"

        resp = host._handle_set_property(req)
        assert resp.generic_response.code == pb.ERR_OK
        assert host.name == "New Host Name"

    def test_set_property_vdc_zone_id(self):
        from pyDSvDCAPI.vdc import Vdc
        host = self._make_host()
        vdc = Vdc(
            host=host,
            implementation_id="x-test-set",
            name="SetTest vDC",
        )
        host.add_vdc(vdc)
        host._cancel_auto_save()

        req = pb.Message()
        req.type = pb.VDSM_REQUEST_SET_PROPERTY
        req.message_id = 21
        req.vdsm_request_set_property.dSUID = str(vdc.dsuid)
        p = req.vdsm_request_set_property.properties.add()
        p.name = "zoneID"
        p.value.v_int64 = 55

        resp = host._handle_set_property(req)
        assert resp.generic_response.code == pb.ERR_OK
        assert vdc.zone_id == 55

    def test_set_property_unknown_dsuid(self):
        host = self._make_host()
        req = pb.Message()
        req.type = pb.VDSM_REQUEST_SET_PROPERTY
        req.message_id = 22
        req.vdsm_request_set_property.dSUID = "0" * 34
        p = req.vdsm_request_set_property.properties.add()
        p.name = "name"
        p.value.v_string = "whatever"

        resp = host._handle_set_property(req)
        assert resp.generic_response.code == pb.ERR_NOT_FOUND

    async def test_dispatch_routes_get_property(self):
        """Test that _dispatch_message routes GET_PROPERTY correctly."""
        host = self._make_host()

        user_called = False

        async def user_handler(session, msg):
            nonlocal user_called
            user_called = True
            return None

        host._on_message = user_handler

        req = pb.Message()
        req.type = pb.VDSM_REQUEST_GET_PROPERTY
        req.message_id = 30
        req.vdsm_request_get_property.dSUID = str(host.dsuid)
        q = req.vdsm_request_get_property.query.add()
        q.name = "model"

        from unittest.mock import MagicMock
        mock_session = MagicMock()

        resp = await host._dispatch_message(mock_session, req)
        assert resp is not None
        assert resp.type == pb.VDC_RESPONSE_GET_PROPERTY
        # User callback should NOT have been called.
        assert user_called is False

    async def test_dispatch_delegates_other_messages(self):
        """Test that unknown message types go to user callback."""
        host = self._make_host()

        received = []

        async def user_handler(session, msg):
            received.append(msg)
            return None

        host._on_message = user_handler

        msg = pb.Message()
        msg.type = pb.VDSM_NOTIFICATION_CALL_SCENE
        msg.message_id = 0

        from unittest.mock import MagicMock
        mock_session = MagicMock()

        await host._dispatch_message(mock_session, msg)
        assert len(received) == 1
