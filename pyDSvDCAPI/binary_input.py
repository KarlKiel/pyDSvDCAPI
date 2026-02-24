"""Binary input component for vdSD devices.

A :class:`BinaryInput` models one binary (digital) sensor input on a
virtual device.  It owns three property groups visible to the vdSM:

* **binaryInputDescriptions** — read-only hardware characteristics
  (name, type, update interval, …).
* **binaryInputSettings** — writable configuration stored persistently
  (group, sensorFunction).
* **binaryInputStates** — volatile runtime state (value / extendedValue,
  age, error) that is **not** persisted.

State updates
~~~~~~~~~~~~~

The physical device feeds new values into the binary input via
:meth:`BinaryInput.update_value` (for ``bool`` state) or
:meth:`BinaryInput.update_extended_value` (for ``int`` state, e.g.
window handle positions).  When the vdSD is announced and a session
is active, the library automatically pushes a
``VDC_SEND_PUSH_PROPERTY`` notification to the vdSM carrying the
``binaryInputStates`` property change (§7.1.3).

Push throttling
~~~~~~~~~~~~~~~

Two settings control push frequency:

* **minPushInterval** — minimum seconds between consecutive pushes.
  Rapid value changes within this window are coalesced into one
  deferred push.
* **changesOnlyInterval** — minimum seconds between pushes of the
  *same* value.  Hardware re-reports of an unchanged value are
  suppressed within this window.

Alive signalling
~~~~~~~~~~~~~~~~

When :attr:`BinaryInput.alive_sign_interval` is non-zero the library
automatically re-pushes the current state at that interval as a
heartbeat.  If no push (neither from a value change nor from the alive
timer) reaches the vdSM within ``aliveSignInterval`` seconds, the
sensor should be considered out of order.  Timers are started
automatically when the owning vdSD is announced and stopped on vanish
or session disconnect.

Persistence
~~~~~~~~~~~

Only description and settings properties are persisted (via the owning
Vdsd's property tree → Device → Vdc → VdcHost YAML).  The runtime
state is transient by definition.

Usage::

    from pyDSvDCAPI.binary_input import BinaryInput
    from pyDSvDCAPI.enums import BinaryInputType, BinaryInputUsage

    bi = BinaryInput(
        vdsd=my_vdsd,
        ds_index=0,
        sensor_function=BinaryInputType.PRESENCE,
        input_usage=BinaryInputUsage.ROOM_CLIMATE,
        name="PIR Sensor",
    )
    my_vdsd.add_binary_input(bi)

    # Later, when the hardware reports a change:
    await bi.update_value(True, session)
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Optional,
    Union,
)

from pyDSvDCAPI import genericVDC_pb2 as pb
from pyDSvDCAPI.enums import BinaryInputType, BinaryInputUsage, InputError
from pyDSvDCAPI.property_handling import dict_to_elements

if TYPE_CHECKING:
    from pyDSvDCAPI.session import VdcSession
    from pyDSvDCAPI.vdsd import Vdsd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Input type identifiers for the ``inputType`` description property.
INPUT_TYPE_POLL_ONLY: int = 0
INPUT_TYPE_DETECTS_CHANGES: int = 1


# ---------------------------------------------------------------------------
# BinaryInput
# ---------------------------------------------------------------------------


class BinaryInput:
    """One binary (digital) input on a vdSD.

    Parameters
    ----------
    vdsd:
        The owning :class:`~pyDSvDCAPI.vdsd.Vdsd`.
    ds_index:
        Zero-based index among **all** binary inputs of this device.
        Must be unique within the device.
    sensor_function:
        The hardwired / configured sensor function (see
        :class:`~pyDSvDCAPI.enums.BinaryInputType`).
    input_type:
        ``0`` = poll-only, ``1`` = detects changes (default).
    input_usage:
        Usage context beyond the device colour group.
    group:
        dS group number (writable setting, persisted).
    name:
        Human-readable name or label for this input.
    update_interval:
        How fast the physical value is tracked, in seconds.
        ``0.0`` means "on change only" (instantaneous).
    hardwired_function:
        If the physical function is fixed in hardware, set this to the
        matching :class:`BinaryInputType` value.  Defaults to
        ``GENERIC`` (freely configurable).
    alive_sign_interval:
        Maximum seconds between pushes before the sensor is considered
        out of order.  When non-zero the library re-pushes state
        automatically.  ``0.0`` disables alive signalling (default).
    min_push_interval:
        Minimum seconds between consecutive push notifications.
        Rapid value changes within this window are coalesced.  ``0.0``
        disables rate-limiting (default).
    changes_only_interval:
        Minimum seconds between pushes of unchanged values.  ``0.0``
        means every hardware update triggers a push (default).
    """

    def __init__(
        self,
        *,
        vdsd: Vdsd,
        ds_index: int = 0,
        sensor_function: BinaryInputType = BinaryInputType.GENERIC,
        input_type: int = INPUT_TYPE_DETECTS_CHANGES,
        input_usage: BinaryInputUsage = BinaryInputUsage.UNDEFINED,
        group: int = 0,
        name: str = "",
        update_interval: float = 0.0,
        hardwired_function: BinaryInputType = BinaryInputType.GENERIC,
        alive_sign_interval: float = 0.0,
        min_push_interval: float = 0.0,
        changes_only_interval: float = 0.0,
    ) -> None:
        # ---- parent reference ----------------------------------------
        self._vdsd: Vdsd = vdsd

        # ---- description properties (read-only, not persisted) -------
        self._ds_index: int = ds_index
        self._input_type: int = input_type
        self._input_usage: BinaryInputUsage = input_usage
        self._hardwired_function: BinaryInputType = hardwired_function
        self._name: str = name
        self._update_interval: float = update_interval
        self._alive_sign_interval: float = alive_sign_interval

        # ---- settings properties (read/write, persisted) -------------
        self._group: int = group
        self._sensor_function: BinaryInputType = sensor_function
        self._min_push_interval: float = min_push_interval
        self._changes_only_interval: float = changes_only_interval

        # ---- state properties (volatile, NOT persisted) --------------
        self._value: Optional[bool] = None
        self._extended_value: Optional[int] = None
        self._age: Optional[float] = None
        self._error: InputError = InputError.OK
        #: Monotonic timestamp of the last value update (for age calc).
        self._last_update: Optional[float] = None

        # ---- push throttling / alive timer state ---------------------
        self._session: Optional[VdcSession] = None
        self._last_push_time: Optional[float] = None
        self._last_pushed_state: Optional[tuple] = None
        self._alive_timer_handle: Optional[asyncio.TimerHandle] = None
        self._deferred_push_handle: Optional[asyncio.TimerHandle] = None

    # ---- read-only accessors -----------------------------------------

    @property
    def ds_index(self) -> int:
        """Zero-based index (``dsIndex``)."""
        return self._ds_index

    @property
    def input_type(self) -> int:
        """``0`` = poll-only, ``1`` = detects changes."""
        return self._input_type

    @property
    def input_usage(self) -> BinaryInputUsage:
        """Usage context of the input."""
        return self._input_usage

    @property
    def hardwired_function(self) -> BinaryInputType:
        """Hardwired function if not freely configurable."""
        return self._hardwired_function

    @property
    def name(self) -> str:
        """Human-readable label for this input."""
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        self._name = value

    @property
    def update_interval(self) -> float:
        """Physical tracking interval in seconds."""
        return self._update_interval

    @property
    def alive_sign_interval(self) -> float:
        """Maximum expected interval between pushes in seconds.

        If no push happens within this interval, the vdSM may
        consider the sensor out of order.  ``0.0`` means no alive
        signalling.
        """
        return self._alive_sign_interval

    @property
    def vdsd(self) -> Vdsd:
        """The owning :class:`Vdsd`."""
        return self._vdsd

    # ---- settings accessors (writable, persisted) --------------------

    @property
    def group(self) -> int:
        """dS group number (writable, persisted)."""
        return self._group

    @group.setter
    def group(self, value: int) -> None:
        self._group = int(value)
        self._schedule_auto_save()

    @property
    def sensor_function(self) -> BinaryInputType:
        """Configured sensor function (writable, persisted)."""
        return self._sensor_function

    @sensor_function.setter
    def sensor_function(self, value: Union[BinaryInputType, int]) -> None:
        self._sensor_function = BinaryInputType(int(value))
        self._schedule_auto_save()

    @property
    def min_push_interval(self) -> float:
        """Minimum seconds between consecutive pushes (writable, persisted).

        Default ``0.0`` disables rate-limiting.
        """
        return self._min_push_interval

    @min_push_interval.setter
    def min_push_interval(self, value: float) -> None:
        self._min_push_interval = float(value)
        self._schedule_auto_save()

    @property
    def changes_only_interval(self) -> float:
        """Minimum seconds between pushes of unchanged values (writable, persisted).

        Default ``0.0`` means every hardware update triggers a push
        regardless of whether the value changed.
        """
        return self._changes_only_interval

    @changes_only_interval.setter
    def changes_only_interval(self, value: float) -> None:
        self._changes_only_interval = float(value)
        self._schedule_auto_save()

    # ---- state accessors (volatile) ----------------------------------

    @property
    def value(self) -> Optional[bool]:
        """Current boolean value (``None`` = unknown)."""
        return self._value

    @property
    def extended_value(self) -> Optional[int]:
        """Current extended (integer) value (``None`` = unknown).

        When set, this takes precedence over :attr:`value`.
        """
        return self._extended_value

    @property
    def age(self) -> Optional[float]:
        """Seconds since the last value update (``None`` = unknown)."""
        if self._last_update is None:
            return None
        return time.monotonic() - self._last_update

    @property
    def error(self) -> InputError:
        """Current error status."""
        return self._error

    @error.setter
    def error(self, value: Union[InputError, int]) -> None:
        self._error = InputError(int(value))

    # ---- state update (called by the physical device) ----------------

    async def update_value(
        self,
        value: Optional[bool],
        session: Optional[VdcSession] = None,
    ) -> None:
        """Set the boolean value and push a state notification.

        Parameters
        ----------
        value:
            ``True`` = active, ``False`` = inactive, ``None`` = unknown.
        session:
            Active session to send the push notification on.  If
            ``None`` or the vdSD is not announced, the value is stored
            locally but no push is sent.
        """
        self._value = value
        self._extended_value = None  # bool takes precedence
        self._last_update = time.monotonic()
        logger.debug(
            "BinaryInput[%d] '%s' value → %s",
            self._ds_index, self._name, value,
        )
        await self._push_state(session or self._session)

    async def update_extended_value(
        self,
        value: Optional[int],
        session: Optional[VdcSession] = None,
    ) -> None:
        """Set the extended (integer) value and push a state notification.

        Parameters
        ----------
        value:
            Integer state (e.g. window handle position: 0=closed,
            1=open, 2=tilted).  ``None`` = unknown.
        session:
            Active session to send the push notification on.
        """
        self._extended_value = value
        self._value = None  # extended takes precedence
        self._last_update = time.monotonic()
        logger.debug(
            "BinaryInput[%d] '%s' extendedValue → %s",
            self._ds_index, self._name, value,
        )
        await self._push_state(session or self._session)

    async def update_error(
        self,
        error: Union[InputError, int],
        session: Optional[VdcSession] = None,
    ) -> None:
        """Set the error status and push a state notification.

        Parameters
        ----------
        error:
            Updated error code.
        session:
            Active session to send the push notification on.
        """
        self._error = InputError(int(error))
        logger.debug(
            "BinaryInput[%d] '%s' error → %s",
            self._ds_index, self._name, self._error.name,
        )
        await self._push_state(session or self._session)

    # ---- property dicts (for getProperty responses) ------------------

    def get_description_properties(self) -> Dict[str, Any]:
        """Return the ``binaryInputDescriptions[N]`` property dict.

        These are read-only hardware characteristics.
        """
        return {
            "name": self._name,
            "dsIndex": self._ds_index,
            "inputType": self._input_type,
            "inputUsage": int(self._input_usage),
            "sensorFunction": int(self._hardwired_function),
            "updateInterval": self._update_interval,
            "aliveSignInterval": self._alive_sign_interval,
        }

    def get_settings_properties(self) -> Dict[str, Any]:
        """Return the ``binaryInputSettings[N]`` property dict.

        These are read/write, persisted.
        """
        return {
            "group": self._group,
            "sensorFunction": int(self._sensor_function),
            "minPushInterval": self._min_push_interval,
            "changesOnlyInterval": self._changes_only_interval,
        }

    def get_state_properties(self) -> Dict[str, Any]:
        """Return the ``binaryInputStates[N]`` property dict.

        These are read-only volatile state.
        """
        state: Dict[str, Any] = {}

        # Prefer extendedValue over value when set.
        if self._extended_value is not None:
            state["extendedValue"] = self._extended_value
        else:
            state["value"] = self._value  # may be None (NULL)

        state["age"] = self.age  # may be None (NULL)
        state["error"] = int(self._error)
        return state

    # ---- settings mutation (called from vdc_host setProperty) --------

    def apply_settings(self, incoming: Dict[str, Any]) -> None:
        """Apply writable settings from a ``setProperty`` request.

        Parameters
        ----------
        incoming:
            Dict of setting name → value (e.g.
            ``{"group": 2, "sensorFunction": 5}``).
        """
        changed = False
        if "group" in incoming:
            self._group = int(incoming["group"])
            changed = True
        if "sensorFunction" in incoming:
            self._sensor_function = BinaryInputType(
                int(incoming["sensorFunction"])
            )
            changed = True
        if "minPushInterval" in incoming:
            self._min_push_interval = float(
                incoming["minPushInterval"]
            )
            changed = True
        if "changesOnlyInterval" in incoming:
            self._changes_only_interval = float(
                incoming["changesOnlyInterval"]
            )
            changed = True
        if changed:
            logger.debug(
                "BinaryInput[%d] settings updated: group=%d, "
                "sensorFunction=%s",
                self._ds_index, self._group,
                self._sensor_function.name,
            )
            self._schedule_auto_save()

    # ---- persistence -------------------------------------------------

    def get_property_tree(self) -> Dict[str, Any]:
        """Return the persisted representation of this binary input.

        Only description and settings properties are included (state
        is volatile and not persisted).
        """
        return {
            "dsIndex": self._ds_index,
            "name": self._name,
            "inputType": self._input_type,
            "inputUsage": int(self._input_usage),
            "hardwiredFunction": int(self._hardwired_function),
            "updateInterval": self._update_interval,
            "aliveSignInterval": self._alive_sign_interval,
            # Settings (writable)
            "group": self._group,
            "sensorFunction": int(self._sensor_function),
            "minPushInterval": self._min_push_interval,
            "changesOnlyInterval": self._changes_only_interval,
        }

    def _apply_state(self, state: Dict[str, Any]) -> None:
        """Restore from a persisted property tree dict.

        Restores both description and settings properties.  State
        properties are left at their defaults (unknown / OK).
        """
        if "dsIndex" in state:
            self._ds_index = int(state["dsIndex"])
        if "name" in state:
            self._name = state["name"]
        if "inputType" in state:
            self._input_type = int(state["inputType"])
        if "inputUsage" in state:
            self._input_usage = BinaryInputUsage(
                int(state["inputUsage"])
            )
        if "hardwiredFunction" in state:
            self._hardwired_function = BinaryInputType(
                int(state["hardwiredFunction"])
            )
        if "updateInterval" in state:
            self._update_interval = float(state["updateInterval"])
        if "aliveSignInterval" in state:
            self._alive_sign_interval = float(
                state["aliveSignInterval"]
            )
        # Settings
        if "group" in state:
            self._group = int(state["group"])
        if "sensorFunction" in state:
            self._sensor_function = BinaryInputType(
                int(state["sensorFunction"])
            )
        if "minPushInterval" in state:
            self._min_push_interval = float(
                state["minPushInterval"]
            )
        if "changesOnlyInterval" in state:
            self._changes_only_interval = float(
                state["changesOnlyInterval"]
            )

    # ---- push notification -------------------------------------------

    def _current_state_key(self) -> tuple:
        """Return a hashable key representing the current value state.

        Used by ``changesOnlyInterval`` to detect unchanged values.
        """
        return (self._value, self._extended_value)

    async def _push_state(
        self,
        session: Optional[VdcSession],
        *,
        force: bool = False,
    ) -> None:
        """Push current state, respecting throttling.

        Parameters
        ----------
        session:
            Session to push on.  ``None`` → no push.
        force:
            If ``True``, bypass ``minPushInterval`` and
            ``changesOnlyInterval`` throttling (used by the alive
            timer).
        """
        if session is None:
            return
        if not self._vdsd.is_announced:
            logger.debug(
                "BinaryInput[%d]: vdSD not announced — skipping push",
                self._ds_index,
            )
            return

        now = time.monotonic()
        current_key = self._current_state_key()

        if not force and self._last_push_time is not None:
            elapsed = now - self._last_push_time

            # changesOnlyInterval: suppress same-value pushes.
            if (
                self._changes_only_interval > 0
                and current_key == self._last_pushed_state
                and elapsed < self._changes_only_interval
            ):
                logger.debug(
                    "BinaryInput[%d]: same value within "
                    "changesOnlyInterval (%.1fs) — skipping push",
                    self._ds_index,
                    self._changes_only_interval,
                )
                return

            # minPushInterval: rate-limit pushes.
            if (
                self._min_push_interval > 0
                and elapsed < self._min_push_interval
            ):
                delay = self._min_push_interval - elapsed
                logger.debug(
                    "BinaryInput[%d]: within minPushInterval — "
                    "deferring push by %.2fs",
                    self._ds_index, delay,
                )
                self._schedule_deferred_push(session, delay)
                return

        await self._do_push(session)

    async def _do_push(self, session: VdcSession) -> None:
        """Send the ``VDC_SEND_PUSH_PROPERTY`` notification.

        This is the low-level push that always sends, updating
        internal tracking state (last push time, last value key,
        alive timer reschedule).
        """
        state_dict = self.get_state_properties()

        push_tree: Dict[str, Any] = {
            "binaryInputStates": {
                str(self._ds_index): state_dict,
            }
        }

        msg = pb.Message()
        msg.type = pb.VDC_SEND_PUSH_PROPERTY
        msg.vdc_send_push_property.dSUID = str(self._vdsd.dsuid)
        for elem in dict_to_elements(push_tree):
            msg.vdc_send_push_property.properties.append(elem)

        try:
            await session.send_notification(msg)
            self._last_push_time = time.monotonic()
            self._last_pushed_state = self._current_state_key()
            logger.debug(
                "BinaryInput[%d] '%s': pushed state %s for vdSD %s",
                self._ds_index, self._name, state_dict,
                self._vdsd.dsuid,
            )
        except (ConnectionError, OSError) as exc:
            logger.warning(
                "BinaryInput[%d] '%s': failed to push state: %s",
                self._ds_index, self._name, exc,
            )

        # (Re-)schedule the alive timer after every push attempt.
        self._reschedule_alive_timer()

    # ---- deferred push (minPushInterval rate limiting) ---------------

    def _schedule_deferred_push(
        self, session: VdcSession, delay: float
    ) -> None:
        """Schedule a push to fire after *delay* seconds.

        Replaces any previously scheduled deferred push.
        """
        self._cancel_deferred_push()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._deferred_push_handle = loop.call_later(
            delay,
            self._on_deferred_push_fired,
            session,
        )

    def _cancel_deferred_push(self) -> None:
        """Cancel any pending deferred push."""
        if self._deferred_push_handle is not None:
            self._deferred_push_handle.cancel()
            self._deferred_push_handle = None

    def _on_deferred_push_fired(
        self, session: VdcSession
    ) -> None:
        """Callback for :meth:`_schedule_deferred_push`."""
        self._deferred_push_handle = None
        if self._vdsd.is_announced:
            asyncio.ensure_future(self._do_push(session))

    # ---- alive timer (periodic heartbeat push) -----------------------

    def start_alive_timer(self, session: VdcSession) -> None:
        """Begin periodic alive re-pushes.

        Called when the vdSD is announced.  Stores *session* so the
        alive timer can push state autonomously.

        If :attr:`alive_sign_interval` is ``0`` the timer is not
        started (but the session is still stored so that
        ``update_value()`` can push without an explicit session).
        """
        self._session = session
        self._reschedule_alive_timer()

    def stop_alive_timer(self) -> None:
        """Stop periodic alive re-pushes and cancel pending pushes.

        Called when the vdSD vanishes or the session disconnects.
        """
        self._cancel_alive_timer()
        self._cancel_deferred_push()
        self._session = None

    def _reschedule_alive_timer(self) -> None:
        """(Re-)schedule the alive timer.

        After each push the timer is reset so it fires only when
        no other push occurs within :attr:`alive_sign_interval`
        seconds.
        """
        self._cancel_alive_timer()
        interval = self._alive_sign_interval
        if interval <= 0 or self._session is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._alive_timer_handle = loop.call_later(
            interval,
            self._on_alive_timer_fired,
        )

    def _cancel_alive_timer(self) -> None:
        """Cancel the alive timer if running."""
        if self._alive_timer_handle is not None:
            self._alive_timer_handle.cancel()
            self._alive_timer_handle = None

    def _on_alive_timer_fired(self) -> None:
        """Callback: alive interval elapsed without a push."""
        self._alive_timer_handle = None
        session = self._session
        if session is not None and self._vdsd.is_announced:
            logger.debug(
                "BinaryInput[%d] '%s': alive timer fired — "
                "re-pushing state",
                self._ds_index, self._name,
            )
            asyncio.ensure_future(
                self._push_state(session, force=True)
            )

    # ---- auto-save ---------------------------------------------------

    def _schedule_auto_save(self) -> None:
        """Trigger a debounced auto-save up through the Vdsd → Device
        → Vdc → VdcHost chain."""
        device = getattr(self._vdsd, "_device", None)
        if device is not None:
            device._schedule_auto_save()

    # ---- dunder ------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"BinaryInput(ds_index={self._ds_index}, "
            f"name={self._name!r}, "
            f"function={self._sensor_function.name})"
        )
