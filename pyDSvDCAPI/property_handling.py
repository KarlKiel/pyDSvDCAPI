"""Property handling — query/response helpers for the vDC API.

The vDC API uses a recursive ``PropertyElement`` tree structure for
reading and writing named properties on addressable entities (vDC host,
vDCs, devices).  This module provides utility functions to:

* **Build** ``PropertyElement`` trees from plain Python dicts.
* **Match** incoming property queries against a dict of available
  properties, producing the correctly shaped response tree.
* **Apply** incoming ``setProperty`` elements to a mutable dict of
  entity properties.

PropertyElement structure (protobuf)::

    message PropertyElement {
        optional string name  = 1;
        optional PropertyValue value = 2;
        repeated PropertyElement elements = 3;
    }

Python → protobuf type mapping:

  ========  ======================
  Python    PropertyValue field
  ========  ======================
  ``str``   ``v_string``
  ``int``   ``v_int64``
  ``bool``  ``v_bool``
  ``float`` ``v_double``
  ``bytes`` ``v_bytes``
  ``dict``  nested ``elements``
  ``None``  empty ``PropertyValue`` (explicit NULL)
  ========  ======================
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pyDSvDCAPI import genericVDC_pb2 as pb

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Python value → PropertyValue
# ---------------------------------------------------------------------------

def _to_property_value(value: Any) -> Optional[pb.PropertyValue]:
    """Convert a Python value to a :class:`PropertyValue` protobuf.

    Returns ``None`` when *value* is a ``dict`` (use nested elements
    instead) or an unsupported type.
    """
    if value is None:
        # Explicit NULL — an empty PropertyValue with no fields set.
        return pb.PropertyValue()

    pv = pb.PropertyValue()
    # bool must be checked before int (bool is a subclass of int).
    if isinstance(value, bool):
        pv.v_bool = value
    elif isinstance(value, int):
        pv.v_int64 = value
    elif isinstance(value, float):
        pv.v_double = value
    elif isinstance(value, str):
        pv.v_string = value
    elif isinstance(value, (bytes, bytearray)):
        pv.v_bytes = bytes(value)
    else:
        return None
    return pv


# ---------------------------------------------------------------------------
# dict → PropertyElement list (full expansion)
# ---------------------------------------------------------------------------

def dict_to_elements(
    properties: Dict[str, Any],
) -> List[pb.PropertyElement]:
    """Convert a Python dict to a list of ``PropertyElement`` messages.

    Nested dicts become sub-elements; scalars become values.
    """
    elements: List[pb.PropertyElement] = []
    for key, val in properties.items():
        elem = pb.PropertyElement()
        elem.name = key
        if isinstance(val, dict):
            for sub in dict_to_elements(val):
                elem.elements.append(sub)
        else:
            pv = _to_property_value(val)
            if pv is not None:
                elem.value.CopyFrom(pv)
        elements.append(elem)
    return elements


# ---------------------------------------------------------------------------
# Query matching
# ---------------------------------------------------------------------------

def match_query(
    properties: Dict[str, Any],
    query: Any,
) -> List[pb.PropertyElement]:
    """Match an incoming property *query* against *properties*.

    Parameters
    ----------
    properties:
        Flat or nested dict of property name → value.
    query:
        The ``query`` repeated field from a
        ``vdsm_RequestGetProperty`` message (a sequence of
        ``PropertyElement`` messages).

    Returns
    -------
    list[PropertyElement]
        Response elements matching the query structure, with values
        filled in from *properties*.  Unknown property names are
        silently dropped.  Wildcard queries (empty ``name``) expand
        to all available properties on that level.
    """
    result: List[pb.PropertyElement] = []

    for q_elem in query:
        name = q_elem.name

        if not name:
            # Wildcard — return everything at this level.
            for k, v in properties.items():
                elem = pb.PropertyElement()
                elem.name = k
                if isinstance(v, dict):
                    # If the wildcard has sub-elements, apply them.
                    if len(q_elem.elements) > 0:
                        for sub in match_query(v, q_elem.elements):
                            elem.elements.append(sub)
                    else:
                        # No sub-query → expand all nested elements.
                        for sub in dict_to_elements(v):
                            elem.elements.append(sub)
                else:
                    pv = _to_property_value(v)
                    if pv is not None:
                        elem.value.CopyFrom(pv)
                result.append(elem)
        elif name in properties:
            val = properties[name]
            elem = pb.PropertyElement()
            elem.name = name

            if isinstance(val, dict):
                if len(q_elem.elements) > 0:
                    # Recurse into the nested dict.
                    for sub in match_query(val, q_elem.elements):
                        elem.elements.append(sub)
                else:
                    # No sub-query — return all nested elements.
                    for sub in dict_to_elements(val):
                        elem.elements.append(sub)
            else:
                pv = _to_property_value(val)
                if pv is not None:
                    elem.value.CopyFrom(pv)
            result.append(elem)
        # else: unknown property — silently omit from response.

    return result


# ---------------------------------------------------------------------------
# Building a complete GetProperty response message
# ---------------------------------------------------------------------------

def build_get_property_response(
    request: pb.Message,
    properties: Dict[str, Any],
) -> pb.Message:
    """Build a ``VDC_RESPONSE_GET_PROPERTY`` from a request and dict.

    Parameters
    ----------
    request:
        The incoming ``VDSM_REQUEST_GET_PROPERTY`` message.
    properties:
        Dict of property name → value for the addressed entity.

    Returns
    -------
    Message
        A properly formed ``VDC_RESPONSE_GET_PROPERTY`` correlated
        to the request via ``message_id``.
    """
    query = request.vdsm_request_get_property.query
    matched = match_query(properties, query)

    response = pb.Message()
    response.type = pb.VDC_RESPONSE_GET_PROPERTY
    response.message_id = request.message_id
    for elem in matched:
        response.vdc_response_get_property.properties.append(elem)

    return response


# ---------------------------------------------------------------------------
# setProperty helpers
# ---------------------------------------------------------------------------

def _extract_value(pv: pb.PropertyValue) -> Any:
    """Extract a Python value from a ``PropertyValue`` message.

    Returns ``None`` if no field is set (explicit NULL).
    """
    if pv.HasField("v_bool"):
        return pv.v_bool
    if pv.HasField("v_uint64"):
        return pv.v_uint64
    if pv.HasField("v_int64"):
        return pv.v_int64
    if pv.HasField("v_double"):
        return pv.v_double
    if pv.HasField("v_string"):
        return pv.v_string
    if pv.HasField("v_bytes"):
        return pv.v_bytes
    return None


def elements_to_dict(
    elements: Any,
) -> Dict[str, Any]:
    """Convert a sequence of ``PropertyElement`` messages to a Python dict.

    Nested elements are converted recursively.  This is the inverse of
    :func:`dict_to_elements`.
    """
    result: Dict[str, Any] = {}
    for elem in elements:
        name = elem.name
        if not name:
            continue
        if len(elem.elements) > 0:
            result[name] = elements_to_dict(elem.elements)
        elif elem.HasField("value"):
            result[name] = _extract_value(elem.value)
        else:
            result[name] = None
    return result
