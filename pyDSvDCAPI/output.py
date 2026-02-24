"""Output component for vdSD devices.

A :class:`Output` models the single output of a virtual device.  Each
vdSD may have **at most one** output (enforced by the owning
:class:`~pyDSvDCAPI.vdsd.Vdsd`).  If a physical device has multiple
independent outputs, the vDC must represent it as multiple virtual
devices with separate dSUIDs (see vDC API §4.1.3).

The output owns three property groups visible to the vdSM:

* **outputDescription** — read-only hardware characteristics
  (function, outputUsage, variableRamp, maxPower, …).
* **outputSettings** — writable configuration stored persistently
  (mode, groups, pushChanges, dimming parameters, …).
* **outputState** — volatile runtime state (localPriority, error)
  that is **not** persisted.

Channels
~~~~~~~~

Output channels (brightness, hue, saturation, etc.) are owned by the
output.  Depending on the output's ``function``, standard channels
are auto-created on construction:

* **ON_OFF / DIMMER** → brightness
* **DIMMER_COLOR_TEMP** → brightness + colortemp
* **FULL_COLOR_DIMMER** → brightness + hue + saturation + colortemp
  + cieX + cieY
* **POSITIONAL / BIPOLAR / INTERNALLY_CONTROLLED** → no auto-created
  channels; the integrator must add them via :meth:`add_channel`.

See :mod:`pyDSvDCAPI.output_channel` for details on channel semantics,
bidirectional value flow, ``apply_now`` buffering, and push behaviour.

State model
~~~~~~~~~~~

The output's operational values (brightness level, valve position,
colour values, etc.) live in the *channels*.  The output state itself
only carries ``localPriority`` and ``error``.

When a channel value is changed locally (from the device side) and
``pushChanges`` is enabled, the output pushes the channel state to
the vdSM via ``VDC_SEND_PUSH_PROPERTY``.

Persistence
~~~~~~~~~~~

Only description and settings properties are persisted (via the owning
Vdsd's property tree → Device → Vdc → VdcHost YAML).  The runtime
state (``localPriority``, ``error``) is transient.

Usage::

    from pyDSvDCAPI.output import Output
    from pyDSvDCAPI.enums import OutputFunction, OutputMode, OutputUsage

    output = Output(
        vdsd=my_vdsd,
        function=OutputFunction.DIMMER,
        output_usage=OutputUsage.ROOM,
        name="Dimmable Light",
    )
    my_vdsd.set_output(output)
"""

from __future__ import annotations

import logging
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Coroutine,
    Dict,
    List,
    Optional,
    Set,
    Union,
)

import pyDSvDCAPI.genericVDC_pb2 as pb
from pyDSvDCAPI.enums import (
    HeatingSystemCapability,
    HeatingSystemType,
    OutputChannelType,
    OutputError,
    OutputFunction,
    OutputMode,
    OutputUsage,
)
from pyDSvDCAPI.output_channel import OutputChannel
from pyDSvDCAPI.property_handling import dict_to_elements

if TYPE_CHECKING:
    from pyDSvDCAPI.session import VdcSession
    from pyDSvDCAPI.vdsd import Vdsd

#: Type alias for the channel-applied callback.
#: ``async def callback(output, channel_updates) -> None``
#: where *channel_updates* is a dict ``{OutputChannelType: value}``.
ChannelAppliedCallback = Callable[
    ["Output", Dict[OutputChannelType, float]],
    Coroutine[Any, Any, None],
]


# ---------------------------------------------------------------------------
# Output function → auto-created channel types
# ---------------------------------------------------------------------------

#: Standard channel types auto-created for each output function.
FUNCTION_CHANNELS: Dict[OutputFunction, List[OutputChannelType]] = {
    OutputFunction.ON_OFF: [
        OutputChannelType.BRIGHTNESS,
    ],
    OutputFunction.DIMMER: [
        OutputChannelType.BRIGHTNESS,
    ],
    OutputFunction.DIMMER_COLOR_TEMP: [
        OutputChannelType.BRIGHTNESS,
        OutputChannelType.COLOR_TEMPERATURE,
    ],
    OutputFunction.FULL_COLOR_DIMMER: [
        OutputChannelType.BRIGHTNESS,
        OutputChannelType.HUE,
        OutputChannelType.SATURATION,
        OutputChannelType.COLOR_TEMPERATURE,
        OutputChannelType.CIE_X,
        OutputChannelType.CIE_Y,
    ],
    # POSITIONAL, BIPOLAR, INTERNALLY_CONTROLLED — no auto-created
    # channels.  The integrator must add them via add_channel().
}

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


class Output:
    """The single output of a vdSD.

    Parameters
    ----------
    vdsd:
        The owning :class:`~pyDSvDCAPI.vdsd.Vdsd`.
    function:
        Functional type of the output (on/off, dimmer, positional, …).
    output_usage:
        Usage context (room, outdoors, user).
    name:
        Human-readable name for the output (e.g. matching a hardware
        connector label).
    default_group:
        dS Application ID of the device (colour group for this output).
    variable_ramp:
        Whether variable-speed transitions are supported.
    max_power:
        Maximum output power in Watts (``None`` = undefined).
    active_cooling_mode:
        ``True`` if the device can actively cool (FCU / air-con).
        ``None`` if not applicable.

    Settings (writable, persisted):

    mode:
        Output operating mode (disabled / binary / gradual / default).
    active_group:
        dS Application ID which group to use by default.
    groups:
        Set of integer group IDs (1-63) this output belongs to.
    push_changes:
        Whether locally-generated output changes are pushed.
    on_threshold:
        Minimum brightness (0-100 %) to switch on non-dimmable lamps.
    min_brightness:
        Minimum brightness (0-100 %) the hardware supports.
    dim_time_up:
        Dim-up time in dS 8-bit format.
    dim_time_down:
        Dim-down time in dS 8-bit format.
    dim_time_up_alt1:
        Alternate 1 dim-up time.
    dim_time_down_alt1:
        Alternate 1 dim-down time.
    dim_time_up_alt2:
        Alternate 2 dim-up time.
    dim_time_down_alt2:
        Alternate 2 dim-down time.
    heating_system_capability:
        How ``heatingLevel`` is applied (heating-only / cooling-only /
        heating-and-cooling).  ``None`` if not a climate device.
    heating_system_type:
        Kind of valve / actuator attached.  ``None`` if not a climate
        device.
    """

    def __init__(
        self,
        *,
        vdsd: Vdsd,
        function: Union[OutputFunction, int] = OutputFunction.ON_OFF,
        output_usage: Union[OutputUsage, int] = OutputUsage.UNDEFINED,
        name: str = "",
        default_group: int = 0,
        variable_ramp: bool = False,
        max_power: Optional[float] = None,
        active_cooling_mode: Optional[bool] = None,
        # Settings (writable, persisted)
        mode: Union[OutputMode, int] = OutputMode.DEFAULT,
        active_group: int = 0,
        groups: Optional[Set[int]] = None,
        push_changes: bool = False,
        on_threshold: Optional[float] = None,
        min_brightness: Optional[float] = None,
        dim_time_up: Optional[int] = None,
        dim_time_down: Optional[int] = None,
        dim_time_up_alt1: Optional[int] = None,
        dim_time_down_alt1: Optional[int] = None,
        dim_time_up_alt2: Optional[int] = None,
        dim_time_down_alt2: Optional[int] = None,
        heating_system_capability: Optional[
            Union[HeatingSystemCapability, int]
        ] = None,
        heating_system_type: Optional[
            Union[HeatingSystemType, int]
        ] = None,
    ) -> None:
        # ---- parent reference ----------------------------------------
        self._vdsd: Vdsd = vdsd

        # ---- description properties (read-only, persisted) -----------
        self._function: OutputFunction = OutputFunction(int(function))
        self._output_usage: OutputUsage = OutputUsage(int(output_usage))
        self._name: str = name
        self._default_group: int = default_group
        self._variable_ramp: bool = variable_ramp
        self._max_power: Optional[float] = max_power
        self._active_cooling_mode: Optional[bool] = active_cooling_mode

        # ---- settings properties (read/write, persisted) -------------
        self._mode: OutputMode = OutputMode(int(mode))
        self._active_group: int = active_group
        self._groups: Set[int] = set(groups) if groups else set()
        self._push_changes: bool = push_changes
        self._on_threshold: Optional[float] = on_threshold
        self._min_brightness: Optional[float] = min_brightness
        self._dim_time_up: Optional[int] = dim_time_up
        self._dim_time_down: Optional[int] = dim_time_down
        self._dim_time_up_alt1: Optional[int] = dim_time_up_alt1
        self._dim_time_down_alt1: Optional[int] = dim_time_down_alt1
        self._dim_time_up_alt2: Optional[int] = dim_time_up_alt2
        self._dim_time_down_alt2: Optional[int] = dim_time_down_alt2
        self._heating_system_capability: Optional[
            HeatingSystemCapability
        ] = (
            HeatingSystemCapability(int(heating_system_capability))
            if heating_system_capability is not None
            else None
        )
        self._heating_system_type: Optional[HeatingSystemType] = (
            HeatingSystemType(int(heating_system_type))
            if heating_system_type is not None
            else None
        )

        # ---- state properties (volatile, NOT persisted) --------------
        self._local_priority: bool = False
        self._error: OutputError = OutputError.OK

        # ---- session reference (set on announcement) -----------------
        self._session: Optional[VdcSession] = None

        # ---- channels ------------------------------------------------
        #: Channels keyed by dsIndex.
        self._channels: Dict[int, OutputChannel] = {}
        #: Pending vdSM-side channel value changes (apply_now buffer).
        #: Maps dsIndex → buffered value.
        self._pending_channel_updates: Dict[int, float] = {}
        #: Callback invoked when apply_now triggers hardware apply.
        self._on_channel_applied: Optional[ChannelAppliedCallback] = None

        # Auto-create channels from function.
        self._auto_create_channels()

    # ==================================================================
    # Read-only description accessors
    # ==================================================================

    @property
    def vdsd(self) -> Vdsd:
        """Owning vdSD."""
        return self._vdsd

    @property
    def function(self) -> OutputFunction:
        """Functional type of the output."""
        return self._function

    @property
    def output_usage(self) -> OutputUsage:
        """Usage context of the output."""
        return self._output_usage

    @property
    def name(self) -> str:
        """Human-readable name."""
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        self._name = value
        self._schedule_auto_save()

    @property
    def default_group(self) -> int:
        """dS Application ID (colour group)."""
        return self._default_group

    @property
    def variable_ramp(self) -> bool:
        """Whether variable-speed transitions are supported."""
        return self._variable_ramp

    @property
    def max_power(self) -> Optional[float]:
        """Maximum output power in Watts (``None`` = undefined)."""
        return self._max_power

    @property
    def active_cooling_mode(self) -> Optional[bool]:
        """Whether the device can actively cool."""
        return self._active_cooling_mode

    # ==================================================================
    # Writable settings accessors
    # ==================================================================

    @property
    def mode(self) -> OutputMode:
        """Output operating mode."""
        return self._mode

    @mode.setter
    def mode(self, value: Union[OutputMode, int]) -> None:
        self._mode = OutputMode(int(value))
        self._schedule_auto_save()

    @property
    def active_group(self) -> int:
        """Active dS group."""
        return self._active_group

    @active_group.setter
    def active_group(self, value: int) -> None:
        self._active_group = int(value)
        self._schedule_auto_save()

    @property
    def groups(self) -> Set[int]:
        """Set of group IDs (1-63) this output belongs to."""
        return set(self._groups)

    @groups.setter
    def groups(self, value: Set[int]) -> None:
        self._groups = set(value)
        self._schedule_auto_save()

    def add_group(self, group_id: int) -> None:
        """Add membership in a group (1-63)."""
        self._groups.add(group_id)
        self._schedule_auto_save()

    def remove_group(self, group_id: int) -> None:
        """Remove membership from a group."""
        self._groups.discard(group_id)
        self._schedule_auto_save()

    @property
    def push_changes(self) -> bool:
        """Whether locally-generated output changes are pushed."""
        return self._push_changes

    @push_changes.setter
    def push_changes(self, value: bool) -> None:
        self._push_changes = bool(value)
        self._schedule_auto_save()

    @property
    def on_threshold(self) -> Optional[float]:
        """Minimum brightness to switch on non-dimmable lamps."""
        return self._on_threshold

    @on_threshold.setter
    def on_threshold(self, value: Optional[float]) -> None:
        self._on_threshold = value
        self._schedule_auto_save()

    @property
    def min_brightness(self) -> Optional[float]:
        """Minimum brightness the hardware supports."""
        return self._min_brightness

    @min_brightness.setter
    def min_brightness(self, value: Optional[float]) -> None:
        self._min_brightness = value
        self._schedule_auto_save()

    @property
    def dim_time_up(self) -> Optional[int]:
        """Dim-up time in dS 8-bit format."""
        return self._dim_time_up

    @dim_time_up.setter
    def dim_time_up(self, value: Optional[int]) -> None:
        self._dim_time_up = value
        self._schedule_auto_save()

    @property
    def dim_time_down(self) -> Optional[int]:
        """Dim-down time in dS 8-bit format."""
        return self._dim_time_down

    @dim_time_down.setter
    def dim_time_down(self, value: Optional[int]) -> None:
        self._dim_time_down = value
        self._schedule_auto_save()

    @property
    def dim_time_up_alt1(self) -> Optional[int]:
        """Alternate 1 dim-up time."""
        return self._dim_time_up_alt1

    @dim_time_up_alt1.setter
    def dim_time_up_alt1(self, value: Optional[int]) -> None:
        self._dim_time_up_alt1 = value
        self._schedule_auto_save()

    @property
    def dim_time_down_alt1(self) -> Optional[int]:
        """Alternate 1 dim-down time."""
        return self._dim_time_down_alt1

    @dim_time_down_alt1.setter
    def dim_time_down_alt1(self, value: Optional[int]) -> None:
        self._dim_time_down_alt1 = value
        self._schedule_auto_save()

    @property
    def dim_time_up_alt2(self) -> Optional[int]:
        """Alternate 2 dim-up time."""
        return self._dim_time_up_alt2

    @dim_time_up_alt2.setter
    def dim_time_up_alt2(self, value: Optional[int]) -> None:
        self._dim_time_up_alt2 = value
        self._schedule_auto_save()

    @property
    def dim_time_down_alt2(self) -> Optional[int]:
        """Alternate 2 dim-down time."""
        return self._dim_time_down_alt2

    @dim_time_down_alt2.setter
    def dim_time_down_alt2(self, value: Optional[int]) -> None:
        self._dim_time_down_alt2 = value
        self._schedule_auto_save()

    @property
    def heating_system_capability(
        self,
    ) -> Optional[HeatingSystemCapability]:
        """How ``heatingLevel`` control value is applied."""
        return self._heating_system_capability

    @heating_system_capability.setter
    def heating_system_capability(
        self,
        value: Optional[Union[HeatingSystemCapability, int]],
    ) -> None:
        self._heating_system_capability = (
            HeatingSystemCapability(int(value))
            if value is not None
            else None
        )
        self._schedule_auto_save()

    @property
    def heating_system_type(self) -> Optional[HeatingSystemType]:
        """Kind of valve / actuator attached."""
        return self._heating_system_type

    @heating_system_type.setter
    def heating_system_type(
        self,
        value: Optional[Union[HeatingSystemType, int]],
    ) -> None:
        self._heating_system_type = (
            HeatingSystemType(int(value))
            if value is not None
            else None
        )
        self._schedule_auto_save()

    # ==================================================================
    # State accessors (volatile)
    # ==================================================================

    @property
    def local_priority(self) -> bool:
        """Local priority flag (volatile, not persisted)."""
        return self._local_priority

    @local_priority.setter
    def local_priority(self, value: bool) -> None:
        self._local_priority = bool(value)

    @property
    def error(self) -> OutputError:
        """Output error status (volatile, not persisted)."""
        return self._error

    @error.setter
    def error(self, value: Union[OutputError, int]) -> None:
        self._error = OutputError(int(value))

    # ==================================================================
    # Channel management
    # ==================================================================

    @property
    def channels(self) -> Dict[int, OutputChannel]:
        """All channels, keyed by ``dsIndex`` (read-only view)."""
        return dict(self._channels)

    @property
    def on_channel_applied(self) -> Optional[ChannelAppliedCallback]:
        """Callback invoked when channel values should be applied."""
        return self._on_channel_applied

    @on_channel_applied.setter
    def on_channel_applied(
        self, callback: Optional[ChannelAppliedCallback]
    ) -> None:
        self._on_channel_applied = callback

    def add_channel(
        self,
        channel_type: Union[OutputChannelType, int],
        *,
        ds_index: Optional[int] = None,
        name: Optional[str] = None,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        resolution: Optional[float] = None,
    ) -> OutputChannel:
        """Add a channel to this output.

        Parameters
        ----------
        channel_type:
            Standard or device-specific channel type ID.
        ds_index:
            Zero-based index.  Auto-assigned (next free) if omitted.
        name, min_value, max_value, resolution:
            Override defaults from :data:`CHANNEL_SPECS`.

        Returns
        -------
        OutputChannel
            The newly created channel.

        Raises
        ------
        ValueError
            If *ds_index* is already in use.
        """
        if ds_index is None:
            ds_index = self._next_free_ds_index()
        if ds_index in self._channels:
            raise ValueError(
                f"ds_index {ds_index} already in use by channel "
                f"{self._channels[ds_index]!r}"
            )
        channel = OutputChannel(
            output=self,
            channel_type=channel_type,
            ds_index=ds_index,
            name=name,
            min_value=min_value,
            max_value=max_value,
            resolution=resolution,
        )
        self._channels[ds_index] = channel
        logger.debug(
            "Added channel %s (dsIndex=%d) to output '%s'",
            channel.name, ds_index, self._name,
        )
        self._schedule_auto_save()
        return channel

    def remove_channel(self, ds_index: int) -> Optional[OutputChannel]:
        """Remove a channel by dsIndex.

        Returns the removed :class:`OutputChannel` or ``None``.
        """
        ch = self._channels.pop(ds_index, None)
        if ch is not None:
            self._pending_channel_updates.pop(ds_index, None)
            self._schedule_auto_save()
        return ch

    def get_channel(self, ds_index: int) -> Optional[OutputChannel]:
        """Look up a channel by ``dsIndex``."""
        return self._channels.get(ds_index)

    def get_channel_by_type(
        self, channel_type: Union[OutputChannelType, int]
    ) -> Optional[OutputChannel]:
        """Look up the first channel with the given type."""
        ct = OutputChannelType(int(channel_type))
        for ch in self._channels.values():
            if ch.channel_type == ct:
                return ch
        return None

    def _next_free_ds_index(self) -> int:
        """Return the smallest unused dsIndex."""
        idx = 0
        while idx in self._channels:
            idx += 1
        return idx

    def _auto_create_channels(self) -> None:
        """Create standard channels based on the output function."""
        channel_types = FUNCTION_CHANNELS.get(self._function, [])
        for i, ct in enumerate(channel_types):
            if i not in self._channels:
                # Create channel directly (don't go through
                # add_channel to avoid auto-save during construction).
                self._channels[i] = OutputChannel(
                    output=self,
                    channel_type=ct,
                    ds_index=i,
                )

    # ==================================================================
    # apply_now buffering (§7.3.9)
    # ==================================================================

    def buffer_channel_value(
        self,
        channel: OutputChannel,
        value: float,
    ) -> None:
        """Buffer a channel value change from the vdSM.

        Called by the setOutputChannelValue handler.  The value is
        stored on the channel and in the pending-updates buffer.
        Hardware callback is NOT invoked yet.
        """
        channel.set_value_from_vdsm(value)
        self._pending_channel_updates[channel.ds_index] = (
            channel.value  # type: ignore[arg-type]
        )

    async def apply_pending_channels(self) -> None:
        """Apply all buffered channel value changes to hardware.

        Invoked when ``apply_now=True`` (or omitted) on the final
        ``setOutputChannelValue`` of a batch.  Calls the
        ``on_channel_applied`` callback with a dict of
        ``{OutputChannelType: value}`` and then confirms all pending
        channels.
        """
        if not self._pending_channel_updates:
            return

        # Build the callback argument: {OutputChannelType: value}.
        updates: Dict[OutputChannelType, float] = {}
        for ds_index, value in self._pending_channel_updates.items():
            ch = self._channels.get(ds_index)
            if ch is not None:
                updates[ch.channel_type] = value

        # Invoke the device callback.
        if self._on_channel_applied is not None:
            try:
                await self._on_channel_applied(self, updates)
            except Exception:
                logger.exception(
                    "on_channel_applied callback raised for output "
                    "'%s'", self._name,
                )

        # Confirm all pending channels.
        for ds_index in list(self._pending_channel_updates):
            ch = self._channels.get(ds_index)
            if ch is not None:
                ch.confirm_applied()

        self._pending_channel_updates.clear()

    # ==================================================================
    # Push channel state to vdSM (device → dSS direction)
    # ==================================================================

    async def _push_channel_state(
        self, channel: OutputChannel
    ) -> None:
        """Push a single channel's state to the vdSM.

        Called by :meth:`OutputChannel.update_value` when
        ``pushChanges`` is set.  Sends a
        ``VDC_SEND_PUSH_PROPERTY`` notification with the
        ``channelStates[dsIndex]`` payload.
        """
        session = self._session
        if session is None:
            logger.debug(
                "No active session — skipping push for channel "
                "'%s' on output '%s'",
                channel.name, self._name,
            )
            return

        state_dict = channel.get_state_properties()
        push_tree: Dict[str, Any] = {
            "channelStates": {
                str(channel.ds_index): state_dict,
            }
        }

        msg = pb.Message()
        msg.type = pb.VDC_SEND_PUSH_PROPERTY
        msg.vdc_send_push_property.dSUID = str(self._vdsd.dsuid)
        for elem in dict_to_elements(push_tree):
            msg.vdc_send_push_property.properties.append(elem)

        try:
            await session.send_notification(msg)
            logger.debug(
                "Pushed channelStates[%d] for vdSD %s: %s",
                channel.ds_index, self._vdsd.dsuid, state_dict,
            )
        except (ConnectionError, OSError) as exc:
            logger.warning(
                "Failed to push channelStates[%d] for vdSD %s: %s",
                channel.ds_index, self._vdsd.dsuid, exc,
            )

    # ==================================================================
    # Channel property dicts (for getProperty responses)
    # ==================================================================

    def get_channel_descriptions(self) -> Dict[str, Any]:
        """Return the ``channelDescriptions`` indexed dict."""
        return {
            str(ch.ds_index): ch.get_description_properties()
            for ch in self._channels.values()
        }

    def get_channel_settings(self) -> Dict[str, Any]:
        """Return the ``channelSettings`` indexed dict.

        Currently empty per spec (§4.9.2).
        """
        return {
            str(ch.ds_index): ch.get_settings_properties()
            for ch in self._channels.values()
        }

    def get_channel_states(self) -> Dict[str, Any]:
        """Return the ``channelStates`` indexed dict."""
        return {
            str(ch.ds_index): ch.get_state_properties()
            for ch in self._channels.values()
        }

    # ==================================================================
    # Property dicts (for getProperty responses)
    # ==================================================================

    def get_description_properties(self) -> Dict[str, Any]:
        """Return the ``outputDescription`` property dict.

        Keys match the vDC API property names (§4.8.1).
        """
        desc: Dict[str, Any] = {
            "function": int(self._function),
            "outputUsage": int(self._output_usage),
            "name": self._name,
            "defaultGroup": self._default_group,
            "variableRamp": self._variable_ramp,
        }
        if self._max_power is not None:
            desc["maxPower"] = self._max_power
        if self._active_cooling_mode is not None:
            desc["activeCoolingMode"] = self._active_cooling_mode
        return desc

    def get_settings_properties(self) -> Dict[str, Any]:
        """Return the ``outputSettings`` property dict.

        Keys match the vDC API property names (§4.8.2).
        """
        settings: Dict[str, Any] = {
            "mode": int(self._mode),
            "activeGroup": self._active_group,
            "pushChanges": self._push_changes,
        }

        # Groups — always present; only "true" entries are included.
        settings["groups"] = {
            str(gid): True for gid in sorted(self._groups)
        }

        # Optional light-output settings.
        if self._on_threshold is not None:
            settings["onThreshold"] = self._on_threshold
        if self._min_brightness is not None:
            settings["minBrightness"] = self._min_brightness
        if self._dim_time_up is not None:
            settings["dimTimeUp"] = self._dim_time_up
        if self._dim_time_down is not None:
            settings["dimTimeDown"] = self._dim_time_down
        if self._dim_time_up_alt1 is not None:
            settings["dimTimeUpAlt1"] = self._dim_time_up_alt1
        if self._dim_time_down_alt1 is not None:
            settings["dimTimeDownAlt1"] = self._dim_time_down_alt1
        if self._dim_time_up_alt2 is not None:
            settings["dimTimeUpAlt2"] = self._dim_time_up_alt2
        if self._dim_time_down_alt2 is not None:
            settings["dimTimeDownAlt2"] = self._dim_time_down_alt2

        # Optional climate-control settings.
        if self._heating_system_capability is not None:
            settings["heatingSystemCapability"] = int(
                self._heating_system_capability
            )
        if self._heating_system_type is not None:
            settings["heatingSystemType"] = int(
                self._heating_system_type
            )

        return settings

    def get_state_properties(self) -> Dict[str, Any]:
        """Return the ``outputState`` property dict.

        Keys match the vDC API property names (§4.8.3).
        """
        return {
            "localPriority": self._local_priority,
            "error": int(self._error),
        }

    # ==================================================================
    # Settings mutation (from vdc_host setProperty)
    # ==================================================================

    def apply_settings(self, settings: Dict[str, Any]) -> None:
        """Apply a dict of writable settings.

        Called by :meth:`VdcHost._apply_vdsd_set_property` when the
        vdSM sends a ``VDSM_SEND_SET_PROPERTY`` for
        ``outputSettings``.  Unknown keys are silently ignored.
        """
        if "mode" in settings:
            self._mode = OutputMode(int(settings["mode"]))
        if "activeGroup" in settings:
            self._active_group = int(settings["activeGroup"])
        if "pushChanges" in settings:
            self._push_changes = bool(settings["pushChanges"])
        if "groups" in settings:
            grp_data = settings["groups"]
            if isinstance(grp_data, dict):
                for gid_str, val in grp_data.items():
                    gid = int(gid_str)
                    if val:
                        self._groups.add(gid)
                    else:
                        self._groups.discard(gid)
        if "onThreshold" in settings:
            val = settings["onThreshold"]
            self._on_threshold = float(val) if val is not None else None
        if "minBrightness" in settings:
            val = settings["minBrightness"]
            self._min_brightness = (
                float(val) if val is not None else None
            )
        if "dimTimeUp" in settings:
            val = settings["dimTimeUp"]
            self._dim_time_up = int(val) if val is not None else None
        if "dimTimeDown" in settings:
            val = settings["dimTimeDown"]
            self._dim_time_down = int(val) if val is not None else None
        if "dimTimeUpAlt1" in settings:
            val = settings["dimTimeUpAlt1"]
            self._dim_time_up_alt1 = (
                int(val) if val is not None else None
            )
        if "dimTimeDownAlt1" in settings:
            val = settings["dimTimeDownAlt1"]
            self._dim_time_down_alt1 = (
                int(val) if val is not None else None
            )
        if "dimTimeUpAlt2" in settings:
            val = settings["dimTimeUpAlt2"]
            self._dim_time_up_alt2 = (
                int(val) if val is not None else None
            )
        if "dimTimeDownAlt2" in settings:
            val = settings["dimTimeDownAlt2"]
            self._dim_time_down_alt2 = (
                int(val) if val is not None else None
            )
        if "heatingSystemCapability" in settings:
            val = settings["heatingSystemCapability"]
            self._heating_system_capability = (
                HeatingSystemCapability(int(val))
                if val is not None
                else None
            )
        if "heatingSystemType" in settings:
            val = settings["heatingSystemType"]
            self._heating_system_type = (
                HeatingSystemType(int(val))
                if val is not None
                else None
            )

        self._schedule_auto_save()

    def apply_state(self, state: Dict[str, Any]) -> None:
        """Apply a dict of writable state properties.

        Called by :meth:`VdcHost._apply_vdsd_set_property` when the
        vdSM sends a ``VDSM_SEND_SET_PROPERTY`` for ``outputState``.
        """
        if "localPriority" in state:
            self._local_priority = bool(state["localPriority"])

    # ==================================================================
    # Persistence (property tree)
    # ==================================================================

    def get_property_tree(self) -> Dict[str, Any]:
        """Return a serialisable dict for YAML persistence.

        Includes description + settings + channel descriptions.
        State is volatile and excluded.
        """
        tree: Dict[str, Any] = {
            # Description.
            "function": int(self._function),
            "outputUsage": int(self._output_usage),
            "name": self._name,
            "defaultGroup": self._default_group,
            "variableRamp": self._variable_ramp,
            # Settings.
            "mode": int(self._mode),
            "activeGroup": self._active_group,
            "pushChanges": self._push_changes,
        }

        # Optional description properties.
        if self._max_power is not None:
            tree["maxPower"] = self._max_power
        if self._active_cooling_mode is not None:
            tree["activeCoolingMode"] = self._active_cooling_mode

        # Groups — persist as list of IDs.
        if self._groups:
            tree["groups"] = sorted(self._groups)

        # Optional light settings.
        if self._on_threshold is not None:
            tree["onThreshold"] = self._on_threshold
        if self._min_brightness is not None:
            tree["minBrightness"] = self._min_brightness
        if self._dim_time_up is not None:
            tree["dimTimeUp"] = self._dim_time_up
        if self._dim_time_down is not None:
            tree["dimTimeDown"] = self._dim_time_down
        if self._dim_time_up_alt1 is not None:
            tree["dimTimeUpAlt1"] = self._dim_time_up_alt1
        if self._dim_time_down_alt1 is not None:
            tree["dimTimeDownAlt1"] = self._dim_time_down_alt1
        if self._dim_time_up_alt2 is not None:
            tree["dimTimeUpAlt2"] = self._dim_time_up_alt2
        if self._dim_time_down_alt2 is not None:
            tree["dimTimeDownAlt2"] = self._dim_time_down_alt2

        # Optional climate settings.
        if self._heating_system_capability is not None:
            tree["heatingSystemCapability"] = int(
                self._heating_system_capability
            )
        if self._heating_system_type is not None:
            tree["heatingSystemType"] = int(self._heating_system_type)

        # Channels (description metadata only, not values).
        if self._channels:
            tree["channels"] = [
                ch.get_property_tree()
                for ch in self._channels.values()
            ]

        return tree

    def _apply_state(self, state: Dict[str, Any]) -> None:
        """Restore from a persisted property tree dict.

        Restores description + settings + channel descriptions.
        State is NOT restored (it is volatile).
        """
        # Description properties.
        if "function" in state:
            self._function = OutputFunction(int(state["function"]))
        if "outputUsage" in state:
            self._output_usage = OutputUsage(int(state["outputUsage"]))
        if "name" in state:
            self._name = state["name"]
        if "defaultGroup" in state:
            self._default_group = int(state["defaultGroup"])
        if "variableRamp" in state:
            self._variable_ramp = bool(state["variableRamp"])
        if "maxPower" in state:
            self._max_power = float(state["maxPower"])
        if "activeCoolingMode" in state:
            self._active_cooling_mode = bool(state["activeCoolingMode"])

        # Settings properties.
        if "mode" in state:
            self._mode = OutputMode(int(state["mode"]))
        if "activeGroup" in state:
            self._active_group = int(state["activeGroup"])
        if "pushChanges" in state:
            self._push_changes = bool(state["pushChanges"])
        if "groups" in state:
            grp = state["groups"]
            if isinstance(grp, list):
                self._groups = set(grp)
            elif isinstance(grp, dict):
                # Handle dict format.
                self._groups = {
                    int(k) for k, v in grp.items() if v
                }
        if "onThreshold" in state:
            self._on_threshold = float(state["onThreshold"])
        if "minBrightness" in state:
            self._min_brightness = float(state["minBrightness"])
        if "dimTimeUp" in state:
            self._dim_time_up = int(state["dimTimeUp"])
        if "dimTimeDown" in state:
            self._dim_time_down = int(state["dimTimeDown"])
        if "dimTimeUpAlt1" in state:
            self._dim_time_up_alt1 = int(state["dimTimeUpAlt1"])
        if "dimTimeDownAlt1" in state:
            self._dim_time_down_alt1 = int(state["dimTimeDownAlt1"])
        if "dimTimeUpAlt2" in state:
            self._dim_time_up_alt2 = int(state["dimTimeUpAlt2"])
        if "dimTimeDownAlt2" in state:
            self._dim_time_down_alt2 = int(state["dimTimeDownAlt2"])
        if "heatingSystemCapability" in state:
            self._heating_system_capability = HeatingSystemCapability(
                int(state["heatingSystemCapability"])
            )
        if "heatingSystemType" in state:
            self._heating_system_type = HeatingSystemType(
                int(state["heatingSystemType"])
            )

        # Restore channels.
        if "channels" in state:
            self._channels.clear()
            for ch_state in state["channels"]:
                idx = ch_state.get("dsIndex", 0)
                ch_type = ch_state.get("channelType", 0)
                ch = OutputChannel(
                    output=self,
                    channel_type=ch_type,
                    ds_index=idx,
                )
                ch._apply_state(ch_state)
                self._channels[idx] = ch
        else:
            # If no channels stored, re-auto-create from function.
            self._channels.clear()
            self._auto_create_channels()

    # ==================================================================
    # Session management
    # ==================================================================

    def start_session(self, session: VdcSession) -> None:
        """Store the active session reference.

        Called when the owning vdSD is announced.
        """
        self._session = session

    def stop_session(self) -> None:
        """Clear the session reference.

        Called when the owning vdSD is vanished or the session
        disconnects.
        """
        self._session = None

    # ==================================================================
    # Auto-save helper
    # ==================================================================

    def _schedule_auto_save(self) -> None:
        """Trigger auto-save via the owning vdSD → Device chain."""
        device = getattr(self._vdsd, "_device", None)
        if device is not None:
            device._schedule_auto_save()

    # ==================================================================
    # Dunder
    # ==================================================================

    def __repr__(self) -> str:
        return (
            f"Output(function={self._function.name}, "
            f"mode={self._mode.name}, "
            f"name={self._name!r})"
        )
