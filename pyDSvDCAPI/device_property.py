"""Device property component for vdSD devices (§4.6.3, §4.6.4).

A :class:`DeviceProperty` models one generic device property on a
virtual device.  Unlike states, properties are not limited to a
fixed set of options — they may be of type *numeric*, *enumeration*,
or *string* and carry richer description metadata (type, min/max,
resolution, SI unit, …).

Each property owns two property groups visible to the vdSM:

* **devicePropertyDescriptions** — read-only invariable description
  (``name``, ``type``, ``min``, ``max``, ``resolution``, ``siunit``,
  ``options``, ``default``).  These are persisted.

* **deviceProperties** — read-write current values (``name``,
  ``value``).  Property values **are persisted**, unlike device states.

Value updates
~~~~~~~~~~~~~

The physical device reports changes via
:meth:`DeviceProperty.update_value`.  When the owning vdSD is
announced and a session is active, the library sends a
``VDC_SEND_PUSH_NOTIFICATION`` notification to the vdSM carrying the
``deviceProperties`` payload.

Persistence
~~~~~~~~~~~

Both description properties and current values are persisted (via the
owning Vdsd's property tree).

Usage::

    from pyDSvDCAPI.device_property import DeviceProperty

    prop = DeviceProperty(
        vdsd=my_vdsd,
        ds_index=0,
        name="batteryLevel",
        type="numeric",
        min_value=0.0,
        max_value=100.0,
        resolution=1.0,
        siunit="%",
        default=100.0,
    )
    my_vdsd.add_device_property(prop)

    # Later, when the hardware reports a value:
    await prop.update_value(85.0)
"""

from __future__ import annotations

import logging
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Optional,
    Union,
)

from pyDSvDCAPI import genericVDC_pb2 as pb
from pyDSvDCAPI.property_handling import dict_to_elements

if TYPE_CHECKING:
    from pyDSvDCAPI.session import VdcSession
    from pyDSvDCAPI.vdsd import Vdsd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants — valid property type strings
# ---------------------------------------------------------------------------

#: Numeric property type.
PROPERTY_TYPE_NUMERIC: str = "numeric"
#: Enumeration property type.
PROPERTY_TYPE_ENUMERATION: str = "enumeration"
#: String property type.
PROPERTY_TYPE_STRING: str = "string"

#: Set of all valid property type strings.
VALID_PROPERTY_TYPES = frozenset({
    PROPERTY_TYPE_NUMERIC,
    PROPERTY_TYPE_ENUMERATION,
    PROPERTY_TYPE_STRING,
})


class DeviceProperty:
    """One generic device property on a vdSD (§4.6.3 / §4.6.4).

    Parameters
    ----------
    vdsd:
        The owning :class:`~pyDSvDCAPI.vdsd.Vdsd` instance.
    ds_index:
        Numeric index of this property within the device (position
        in ``devicePropertyDescriptions`` / ``deviceProperties``).
    name:
        Property name (e.g. ``"batteryLevel"``).
    type:
        Data type identifier: ``"numeric"``, ``"enumeration"``, or
        ``"string"``.
    min_value:
        Optional minimum value (numeric only).
    max_value:
        Optional maximum value (numeric only).
    resolution:
        Optional resolution / LSB size (numeric only).
    siunit:
        Optional SI unit string, e.g. ``"°C"`` (numeric only).
    options:
        Optional option key → value mapping (enumeration only).
    default:
        Optional default value (all types).
    description:
        Optional human-readable description.
    """

    __slots__ = (
        "_vdsd",
        "_ds_index",
        "_name",
        "_type",
        "_min_value",
        "_max_value",
        "_resolution",
        "_siunit",
        "_options",
        "_default",
        "_description",
        "_value",
    )

    def __init__(
        self,
        vdsd: Vdsd,
        ds_index: int = 0,
        name: str = "",
        type: str = PROPERTY_TYPE_STRING,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        resolution: Optional[float] = None,
        siunit: Optional[str] = None,
        options: Optional[Dict[Union[int, str], str]] = None,
        default: Optional[Union[float, str]] = None,
        description: Optional[str] = None,
    ) -> None:
        self._vdsd = vdsd
        self._ds_index = ds_index
        self._name = name
        self._type = type
        self._min_value = min_value
        self._max_value = max_value
        self._resolution = resolution
        self._siunit = siunit
        self._options: Optional[Dict[Union[int, str], str]] = (
            dict(options) if options else None
        )
        self._default = default
        self._description = description
        # Current property value (persisted).
        self._value: Optional[Union[float, str]] = None

    # ---- read-only accessors -----------------------------------------

    @property
    def vdsd(self) -> Vdsd:
        """The owning vdSD."""
        return self._vdsd

    @property
    def ds_index(self) -> int:
        """Numeric index within the device."""
        return self._ds_index

    # ---- configurable properties -------------------------------------

    @property
    def name(self) -> str:
        """Property name."""
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        self._name = value

    @property
    def type(self) -> str:
        """Data type identifier (``"numeric"``, ``"enumeration"``, or
        ``"string"``)."""
        return self._type

    @type.setter
    def type(self, value: str) -> None:
        self._type = value

    @property
    def min_value(self) -> Optional[float]:
        """Minimum value (numeric only)."""
        return self._min_value

    @min_value.setter
    def min_value(self, value: Optional[float]) -> None:
        self._min_value = value

    @property
    def max_value(self) -> Optional[float]:
        """Maximum value (numeric only)."""
        return self._max_value

    @max_value.setter
    def max_value(self, value: Optional[float]) -> None:
        self._max_value = value

    @property
    def resolution(self) -> Optional[float]:
        """Resolution / LSB size (numeric only)."""
        return self._resolution

    @resolution.setter
    def resolution(self, value: Optional[float]) -> None:
        self._resolution = value

    @property
    def siunit(self) -> Optional[str]:
        """SI unit string (numeric only)."""
        return self._siunit

    @siunit.setter
    def siunit(self, value: Optional[str]) -> None:
        self._siunit = value

    @property
    def options(self) -> Optional[Dict[Union[int, str], str]]:
        """Option key → value mapping (enumeration only, copy)."""
        return dict(self._options) if self._options is not None else None

    @options.setter
    def options(
        self, value: Optional[Dict[Union[int, str], str]]
    ) -> None:
        self._options = dict(value) if value is not None else None

    @property
    def default(self) -> Optional[Union[float, str]]:
        """Default value."""
        return self._default

    @default.setter
    def default(self, value: Optional[Union[float, str]]) -> None:
        self._default = value

    @property
    def description(self) -> Optional[str]:
        """Optional human-readable description."""
        return self._description

    @description.setter
    def description(self, value: Optional[str]) -> None:
        self._description = value

    # ---- volatile value accessor -------------------------------------

    @property
    def value(self) -> Optional[Union[float, str]]:
        """Current property value (persisted)."""
        return self._value

    @value.setter
    def value(self, v: Optional[Union[float, str]]) -> None:
        self._value = v

    # ---- property dicts ----------------------------------------------

    def get_description_properties(self) -> Dict[str, Any]:
        """Return **devicePropertyDescriptions** properties (§4.6.3).

        Format::

            {"name": "battery", "type": "numeric",
             "min": 0.0, "max": 100.0, ...}

        Keys in the parent dict are numeric string indices
        (``str(ds_index)``), matching the pattern used by sensors
        and buttons.  The ``name`` field identifies the property.

        For enumeration properties, ``options`` maps integer
        option-id strings to labels (e.g. ``{"0": "Auto"}``),
        matching the spec format.
        """
        props: Dict[str, Any] = {
            "name": self._name,
            "type": self._type,
        }
        # Numeric-specific optional fields.
        if self._type == PROPERTY_TYPE_NUMERIC:
            if self._min_value is not None:
                props["min"] = self._min_value
            if self._max_value is not None:
                props["max"] = self._max_value
            if self._resolution is not None:
                props["resolution"] = self._resolution
            if self._siunit is not None:
                props["siunit"] = self._siunit
        # Enumeration-specific: option id → label pairs.
        if self._type == PROPERTY_TYPE_ENUMERATION and self._options:
            props["options"] = {
                str(k): v for k, v in self._options.items()
            }
        # All-type optional fields.
        if self._default is not None:
            props["default"] = self._default
        if self._description is not None:
            props["description"] = self._description
        return props

    def get_value_properties(self) -> Dict[str, Any]:
        """Return **deviceProperties** value (§4.6.4).

        Format::

            {"name": "battery", "value": 85.0}

        Returns a dict with ``name`` and ``value`` fields,
        matching the spec §4.6.4 format.
        """
        return {
            "name": self._name,
            "value": self._value,
        }

    # ---- persistence -------------------------------------------------

    def get_property_tree(self) -> Dict[str, Any]:
        """Return a dict suitable for YAML persistence.

        Both description and current value are persisted.
        """
        node: Dict[str, Any] = {
            "dsIndex": self._ds_index,
            "name": self._name,
            "type": self._type,
        }
        if self._min_value is not None:
            node["minValue"] = self._min_value
        if self._max_value is not None:
            node["maxValue"] = self._max_value
        if self._resolution is not None:
            node["resolution"] = self._resolution
        if self._siunit is not None:
            node["siunit"] = self._siunit
        if self._options is not None:
            node["options"] = {
                str(k): v for k, v in self._options.items()
            }
        if self._default is not None:
            node["default"] = self._default
        if self._description is not None:
            node["description"] = self._description
        # Current value is also persisted.
        if self._value is not None:
            node["value"] = self._value
        return node

    def _apply_state(self, state: Dict[str, Any]) -> None:
        """Restore from a persisted state dict."""
        if "name" in state:
            self._name = state["name"]
        if "type" in state:
            self._type = state["type"]
        if "minValue" in state:
            self._min_value = float(state["minValue"])
        if "maxValue" in state:
            self._max_value = float(state["maxValue"])
        if "resolution" in state:
            self._resolution = float(state["resolution"])
        if "siunit" in state:
            self._siunit = state["siunit"]
        if "options" in state:
            raw = state["options"]
            if isinstance(raw, dict):
                self._options = {
                    _parse_option_key(k): v
                    for k, v in raw.items()
                }
        if "default" in state:
            self._default = state["default"]
        if "description" in state:
            self._description = state.get("description")
        # Restore persisted value.
        if "value" in state:
            self._value = state["value"]

    # ---- push to vdSM ------------------------------------------------

    async def update_value(
        self,
        value: Union[float, int, str],
        session: Optional[VdcSession] = None,
    ) -> None:
        """Update the property value and push the change to the vdSM.

        Parameters
        ----------
        value:
            The new property value.
        session:
            The session to send through.  When ``None``, the owning
            vdSD's current session is used.

        If no active session is available the value is still recorded
        locally, but the push is skipped with a warning.

        For numeric properties the value is stored as ``float``; for
        string and enumeration properties it is stored as ``str``.

        For enumeration properties an integer key is automatically
        resolved to the corresponding text label via the *options*
        dictionary, matching p44-vdc behaviour.
        """
        # Per §4.6.4 all property values are strings on the wire.
        # We keep numeric values as float internally for convenience
        # (min/max checks, arithmetic) but serialise as str.
        if self._type == PROPERTY_TYPE_NUMERIC:
            self._value = float(value)
        elif self._type == PROPERTY_TYPE_ENUMERATION:
            self._value = self._resolve_enum_label(value)
        else:
            self._value = str(value)

        # Trigger auto-save since property values are persisted.
        self._vdsd._schedule_auto_save_if_enabled()

        session = session or self._vdsd._session
        if session is None or not session.is_active:
            logger.warning(
                "DeviceProperty[%d] '%s': cannot push — no active "
                "session for vdSD %s",
                self._ds_index, self._name, self._vdsd.dsuid,
            )
            return

        if not self._vdsd.is_announced:
            logger.debug(
                "DeviceProperty[%d] '%s': vdSD not announced — "
                "skipping push",
                self._ds_index, self._name,
            )
            return

        # Push direct scalar value (p44-vdc compatible).
        push_tree: Dict[str, Any] = {
            "deviceProperties": {
                self._name: self._value,
            }
        }

        msg = pb.Message()
        msg.type = pb.VDC_SEND_PUSH_NOTIFICATION
        msg.vdc_send_push_notification.dSUID = str(self._vdsd.dsuid)
        for elem in dict_to_elements(push_tree):
            msg.vdc_send_push_notification.changedproperties.append(elem)

        try:
            await session.send_notification(msg)
            logger.debug(
                "DeviceProperty[%d] '%s': pushed value '%s' for "
                "vdSD %s",
                self._ds_index, self._name, self._value,
                self._vdsd.dsuid,
            )
        except (ConnectionError, OSError) as exc:
            logger.warning(
                "DeviceProperty[%d] '%s': failed to push: %s",
                self._ds_index, self._name, exc,
            )

    # ---- repr --------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"DeviceProperty(ds_index={self._ds_index!r}, "
            f"name={self._name!r}, type={self._type!r}, "
            f"value={self._value!r})"
        )

    # ---- enum resolution ---------------------------------------------

    def _resolve_enum_label(self, value: Union[float, int, str]) -> str:
        """Resolve *value* to a string label for enumeration properties.

        p44-vdc always sends the text label for enumeration values.
        This method resolves:

        * ``int`` → label via options dictionary (key → label).
        * ``str`` that is an integer literal → lookup as int key.
        * ``str`` that matches an existing label → used directly.
        * fallback → ``str(value)``.
        """
        if self._options:
            # Integer key → label lookup.
            if isinstance(value, int) and not isinstance(value, bool):
                label = self._options.get(value)
                if label is not None:
                    return label
            elif isinstance(value, str):
                # Try as integer key first.
                try:
                    int_key = int(value)
                    label = self._options.get(int_key)
                    if label is not None:
                        return label
                except ValueError:
                    pass
                # Check if value is already a known label.
                if value in self._options.values():
                    return value
        return str(value)


def _parse_option_key(key: Any) -> Union[int, str]:
    """Convert a persisted option key back to int when possible."""
    if isinstance(key, int):
        return key
    try:
        return int(key)
    except (ValueError, TypeError):
        return str(key)
