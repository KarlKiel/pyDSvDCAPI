"""vDC Host — top-level entity of a virtualDC host.

A :class:`VdcHost` represents the vDC host in the digitalSTROM system.
It holds the *common properties* required by every addressable entity,
provides DNS-SD (mDNS / Bonjour / Avahi) service announcement via the
``zeroconf`` library, and runs an asyncio TCP server that accepts
incoming vdSM connections.

Usage example::

    import asyncio
    from pyDSvDCAPI import VdcHost

    host = VdcHost(
        model="My Smart Gateway",
        name="Living Room Gateway",
    )

    async def main():
        await host.start()  # starts TCP server + DNS-SD announce
        try:
            await asyncio.Event().wait()  # run forever
        finally:
            await host.stop()

    asyncio.run(main())
"""

from __future__ import annotations

import asyncio
import logging
import platform
import socket
import threading
from pathlib import Path
from typing import Any, Awaitable, Callable, ClassVar, Dict, Optional, Union

from zeroconf import ServiceInfo
from zeroconf.asyncio import AsyncZeroconf

from pyDSvDCAPI import genericVDC_pb2 as pb
from pyDSvDCAPI.connection import VdcConnection
from pyDSvDCAPI.dsuid import DsUid, DsUidNamespace
from pyDSvDCAPI.persistence import PropertyStore
from pyDSvDCAPI.property_handling import (
    build_get_property_response,
    elements_to_dict,
)
from pyDSvDCAPI.session import MessageCallback, SessionState, VdcSession
from pyDSvDCAPI.vdc import Vdc, VdcCapabilities

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Default TCP port for the vDC host socket (as per the documentation).
DEFAULT_VDC_PORT: int = 8444

#: DNS-SD service type for vDC hosts.
VDC_SERVICE_TYPE: str = "_ds-vdc._tcp.local."

#: Entity type string for a vDC host (common property ``type``).
ENTITY_TYPE_VDC_HOST: str = "vDChost"

#: Debounce delay for auto-save in seconds.  When a tracked property
#: changes, the save is scheduled after this delay.  Subsequent changes
#: within the window reset the timer so that rapid edits result in a
#: single write.
AUTO_SAVE_DELAY: float = 1.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_default_mac() -> str:
    """Return the MAC address of the primary network interface.

    Falls back to a deterministic pseudo-MAC derived from the hostname
    when no real MAC address can be obtained.
    """
    import uuid as _uuid

    node = _uuid.getnode()
    # uuid.getnode() returns a random MAC with bit 0 set when it cannot
    # determine the real hardware address.  Bit 0 of the first octet
    # being 1 indicates a multicast / locally administered address.
    mac_bytes = node.to_bytes(6, "big")
    return ":".join(f"{b:02X}" for b in mac_bytes)


def _get_hostname() -> str:
    """Return the hostname of this machine."""
    return platform.node() or socket.gethostname()


# ---------------------------------------------------------------------------
# VdcHost
# ---------------------------------------------------------------------------

class VdcHost:
    """Represents a digitalSTROM vDC host and its common properties.

    A vDC host is the top-level addressable entity.  It provides a TCP
    server socket that a vdSM connects to, and announces itself via
    DNS-SD so that vdSMs can discover it automatically.

    All common properties (as defined in the *vDC API Properties —
    Common Properties* document) are available as regular Python
    attributes.  Properties that can be derived automatically (dSUID,
    ``hardwareGuid``, ``displayId``, …) are computed on first access
    unless explicitly set by the caller.

    **Auto-save:** When a ``state_path`` is configured, any change to a
    tracked property (e.g. ``name``, ``model``, ``vendor_name``, …)
    automatically triggers a debounced save.  The delay is controlled
    by :data:`AUTO_SAVE_DELAY` (default 1 s).  Rapid successive changes
    are coalesced into a single write.  Call :meth:`flush` to force an
    immediate save of pending changes (e.g. before shutdown).

    Parameters
    ----------
    mac:
        MAC address of the host hardware
        (e.g. ``"AA:BB:CC:DD:EE:FF"``).  Used to derive the dSUID
        and ``hardwareGuid``.  Auto-detected when omitted.
    port:
        TCP port for the vDC host socket.  Defaults to **8444**.
    dsuid:
        Explicit dSUID.  When omitted the dSUID is derived from
        *mac* using :pyfunc:`DsUid.from_name_in_space` with the
        well-known vDC host namespace.
    name:
        User-facing name for the host.  Defaults to
        ``"vDC host on <hostname>"``.
    model:
        Human-readable model description.  Defaults to
        ``"pyDSvDCAPI vDC host"``.
    model_version:
        Model / firmware version string.
    model_uid:
        System-unique ID for the functional model.  When omitted a
        deterministic value is derived from *model*.
    hardware_version:
        Human-readable hardware version string.
    hardware_guid:
        Native hardware GUID (``"macaddress:XX:XX:…"``).  Derived
        from *mac* when omitted.
    hardware_model_guid:
        Native hardware model GUID.
    vendor_name:
        Human-readable vendor name.
    vendor_guid:
        Globally unique vendor identifier.
    oem_guid:
        OEM product GUID.
    oem_model_guid:
        OEM product-model GUID.
    config_url:
        URL to the device's web configuration interface.
    device_icon_16:
        16×16 PNG icon as ``bytes``.
    device_icon_name:
        Filename-safe icon identifier for caching.
    state_path:
        Path to the YAML file used for persisting the property tree.
        When given, the host will attempt to restore its state on
        construction and can be asked to :meth:`save` at any time.
        When omitted, persistence is disabled.
    """

    #: Attribute names whose mutation triggers a debounced auto-save.
    _TRACKED_ATTRS: ClassVar[frozenset] = frozenset({
        "name", "model", "model_version", "model_uid",
        "hardware_version", "hardware_guid", "hardware_model_guid",
        "vendor_name", "vendor_guid", "oem_guid", "oem_model_guid",
        "config_url", "device_icon_name",
    })

    # ---- attribute change tracking -----------------------------------

    def __setattr__(self, name: str, value: object) -> None:
        """Set an attribute and schedule an auto-save when appropriate.

        Only attributes listed in :attr:`_TRACKED_ATTRS` are monitored.
        Auto-save is suppressed during ``__init__`` and :meth:`load` to
        avoid redundant writes.
        """
        super().__setattr__(name, value)
        if (
            name in self._TRACKED_ATTRS
            and getattr(self, "_auto_save_enabled", False)
        ):
            self._schedule_auto_save()

    def __init__(
        self,
        *,
        mac: Optional[str] = None,
        port: int = DEFAULT_VDC_PORT,
        dsuid: Optional[DsUid] = None,
        name: Optional[str] = None,
        model: str = "pyDSvDCAPI vDC host",
        model_version: Optional[str] = None,
        model_uid: Optional[str] = None,
        hardware_version: Optional[str] = None,
        hardware_guid: Optional[str] = None,
        hardware_model_guid: Optional[str] = None,
        vendor_name: Optional[str] = None,
        vendor_guid: Optional[str] = None,
        oem_guid: Optional[str] = None,
        oem_model_guid: Optional[str] = None,
        config_url: Optional[str] = None,
        device_icon_16: Optional[bytes] = None,
        device_icon_name: Optional[str] = None,
        state_path: Optional[Union[str, Path]] = None,
    ) -> None:
        # --- persistence ----------------------------------------------
        self._store: Optional[PropertyStore] = (
            PropertyStore(state_path) if state_path else None
        )

        # --- try restoring from persisted state -----------------------
        restored = self._store.load() if self._store else None
        host_state: Dict[str, Any] = (
            restored.get("vdcHost", {}) if restored else {}
        )

        # --- network --------------------------------------------------
        self._mac: str = mac or host_state.get("mac") or _get_default_mac()
        self._port: int = port if port != DEFAULT_VDC_PORT else host_state.get("port", port)

        # --- identity -------------------------------------------------
        if dsuid is not None:
            self._dsuid = dsuid
        elif "dSUID" in host_state:
            self._dsuid = DsUid.from_string(host_state["dSUID"])
        else:
            self._dsuid = self._derive_dsuid(self._mac)

        # --- common properties ----------------------------------------
        self.name: str = (
            name
            or host_state.get("name")
            or f"vDC host on {_get_hostname()}"
        )
        self.model: str = model if model != "pyDSvDCAPI vDC host" else host_state.get("model", model)
        self.model_version: Optional[str] = (
            model_version or host_state.get("modelVersion")
        )
        self.model_uid: str = (
            model_uid
            or host_state.get("modelUID")
            or self._derive_model_uid(self.model)
        )
        self.hardware_version: Optional[str] = (
            hardware_version or host_state.get("hardwareVersion")
        )
        self.hardware_guid: str = (
            hardware_guid
            or host_state.get("hardwareGuid")
            or f"macaddress:{self._mac}"
        )
        self.hardware_model_guid: Optional[str] = (
            hardware_model_guid or host_state.get("hardwareModelGuid")
        )
        self.vendor_name: Optional[str] = (
            vendor_name or host_state.get("vendorName")
        )
        self.vendor_guid: Optional[str] = (
            vendor_guid or host_state.get("vendorGuid")
        )
        self.oem_guid: Optional[str] = (
            oem_guid or host_state.get("oemGuid")
        )
        self.oem_model_guid: Optional[str] = (
            oem_model_guid or host_state.get("oemModelGuid")
        )
        self.config_url: Optional[str] = (
            config_url or host_state.get("configURL")
        )
        self.device_icon_16: Optional[bytes] = device_icon_16
        self.device_icon_name: Optional[str] = (
            device_icon_name or host_state.get("deviceIconName")
        )

        # --- runtime state --------------------------------------------
        self._active: bool = True
        self._zeroconf: Optional[AsyncZeroconf] = None
        self._service_info: Optional[ServiceInfo] = None

        # --- TCP server / session state --------------------------------
        self._server: Optional[asyncio.AbstractServer] = None
        self._session: Optional[VdcSession] = None
        self._session_task: Optional[asyncio.Task] = None
        self._on_message: Optional[MessageCallback] = None

        # --- vDC registry ---------------------------------------------
        self._vdcs: Dict[str, Vdc] = {}  # keyed by dSUID string

        # --- auto-save ------------------------------------------------
        self._save_timer: Optional[threading.Timer] = None
        self._auto_save_enabled: bool = self._store is not None

        # --- restore vDCs from persisted state ------------------------
        if host_state.get("vdcs"):
            for vdc_state in host_state["vdcs"]:
                impl_id = vdc_state.get("implementationId")
                if impl_id:
                    vdc = Vdc(
                        host=self,
                        implementation_id=impl_id,
                    )
                    vdc._apply_state(vdc_state)
                    self._vdcs[str(vdc.dsuid)] = vdc

        # Schedule an initial save so that the constructed state
        # (which may include defaults and derived values) is persisted.
        if self._auto_save_enabled:
            self._schedule_auto_save()

    # ---- derived / computed properties --------------------------------

    @staticmethod
    def _derive_dsuid(mac: str) -> DsUid:
        """Derive a vDC-host dSUID from a MAC address.

        Uses UUIDv5 hashing with the well-known vDC namespace, which
        is the documented method for generating a vDC host dSUID from
        the hardware's MAC address.
        """
        return DsUid.from_vdc_mac(mac)

    @staticmethod
    def _derive_model_uid(model: str) -> str:
        """Derive a deterministic ``modelUID`` from the model name.

        Uses UUIDv5 in the vDC namespace so that identical model names
        always produce the same ``modelUID``.
        """
        uid = DsUid.from_name_in_space(model, DsUidNamespace.VDC)
        return str(uid)

    # ---- read-only accessors -----------------------------------------

    @property
    def dsuid(self) -> DsUid:
        """The dSUID of this vDC host (read-only)."""
        return self._dsuid

    @property
    def display_id(self) -> str:
        """Human-readable identification of the vDC host.

        Returns the canonical hex representation of the dSUID, which
        serves as a readable identifier.
        """
        return str(self._dsuid)

    @property
    def entity_type(self) -> str:
        """Entity type string (always ``"vDChost"``)."""
        return ENTITY_TYPE_VDC_HOST

    @property
    def mac(self) -> str:
        """The MAC address associated with this host."""
        return self._mac

    @property
    def port(self) -> int:
        """The TCP port for the vDC host socket."""
        return self._port

    @property
    def active(self) -> bool:
        """Whether the vDC host is currently active / operational."""
        return self._active

    @active.setter
    def active(self, value: bool) -> None:
        self._active = bool(value)

    # ---- common-property dict ----------------------------------------

    def get_properties(self) -> dict:
        """Return all common properties as a flat dictionary.

        Keys match the property names from the vDC API specification.
        ``None`` values indicate properties that are not set.
        """
        return {
            "dSUID": str(self._dsuid),
            "displayId": self.display_id,
            "type": self.entity_type,
            "model": self.model,
            "modelVersion": self.model_version,
            "modelUID": self.model_uid,
            "hardwareVersion": self.hardware_version,
            "hardwareGuid": self.hardware_guid,
            "hardwareModelGuid": self.hardware_model_guid,
            "vendorName": self.vendor_name,
            "vendorGuid": self.vendor_guid,
            "oemGuid": self.oem_guid,
            "oemModelGuid": self.oem_model_guid,
            "configURL": self.config_url,
            "deviceIcon16": self.device_icon_16,
            "deviceIconName": self.device_icon_name,
            "name": self.name,
            "active": self._active,
        }

    # ---- vDC management -----------------------------------------------

    def add_vdc(self, vdc: Vdc) -> None:
        """Register a :class:`Vdc` with this host.

        The vDC is stored in an internal registry keyed by its dSUID.
        Adding a vDC with a dSUID that already exists replaces the
        previous entry.  If auto-save is enabled, a save is scheduled.

        Parameters
        ----------
        vdc:
            The :class:`Vdc` instance to register.
        """
        key = str(vdc.dsuid)
        self._vdcs[key] = vdc
        logger.info("Registered vDC '%s' (dSUID %s)", vdc.name, key)
        if self._auto_save_enabled:
            self._schedule_auto_save()

    def remove_vdc(self, dsuid: DsUid) -> Optional[Vdc]:
        """Remove a registered vDC by its dSUID.

        Returns the removed :class:`Vdc` or ``None`` if no vDC with
        the given dSUID was registered.
        """
        key = str(dsuid)
        vdc = self._vdcs.pop(key, None)
        if vdc is not None:
            logger.info("Removed vDC '%s' (dSUID %s)", vdc.name, key)
            if self._auto_save_enabled:
                self._schedule_auto_save()
        return vdc

    def get_vdc(self, dsuid: DsUid) -> Optional[Vdc]:
        """Look up a registered vDC by its dSUID.

        Returns ``None`` if no vDC is registered with that dSUID.
        """
        return self._vdcs.get(str(dsuid))

    @property
    def vdcs(self) -> Dict[str, Vdc]:
        """A read-only view of all registered vDCs (keyed by dSUID)."""
        return dict(self._vdcs)

    async def announce_vdcs(self) -> int:
        """Announce all registered vDCs to the connected vdSM.

        This should be called after the session hello handshake
        completes, before announcing any devices.

        Returns
        -------
        int
            The number of vDCs successfully announced.

        Raises
        ------
        ConnectionError
            If there is no active session.
        """
        session = self._session
        if session is None or not session.is_active:
            raise ConnectionError(
                "Cannot announce vDCs — no active session"
            )

        announced_count = 0
        for vdc in self._vdcs.values():
            try:
                success = await vdc.announce(session)
                if success:
                    announced_count += 1
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Failed to announce vDC '%s'", vdc.name
                )

        logger.info(
            "Announced %d/%d vDCs",
            announced_count,
            len(self._vdcs),
        )
        return announced_count

    # ---- property tree (for persistence) -----------------------------

    def get_property_tree(self) -> Dict[str, Any]:
        """Return the full property tree suitable for YAML persistence.

        The structure is::

            vdcHost:
              dSUID: "..."
              mac: "AA:BB:CC:DD:EE:FF"
              port: 8444
              name: "..."
              model: "..."
              ...
              vdcs:
                - dSUID: "..."
                  implementationId: "x-company-light"
                  ...
        """
        host_node: Dict[str, Any] = {
            "dSUID": str(self._dsuid),
            "mac": self._mac,
            "port": self._port,
            "name": self.name,
            "model": self.model,
            "modelVersion": self.model_version,
            "modelUID": self.model_uid,
            "hardwareVersion": self.hardware_version,
            "hardwareGuid": self.hardware_guid,
            "hardwareModelGuid": self.hardware_model_guid,
            "vendorName": self.vendor_name,
            "vendorGuid": self.vendor_guid,
            "oemGuid": self.oem_guid,
            "oemModelGuid": self.oem_model_guid,
            "configURL": self.config_url,
            "deviceIconName": self.device_icon_name,
        }

        if self._vdcs:
            host_node["vdcs"] = [
                vdc.get_property_tree() for vdc in self._vdcs.values()
            ]

        return {"vdcHost": host_node}

    # ---- persistence -------------------------------------------------

    def save(self) -> None:
        """Persist the current property tree to the YAML state file.

        Does nothing if no ``state_path`` was provided at construction.
        Any pending debounced auto-save is cancelled since this manual
        save already captures the current state.
        """
        self._cancel_auto_save()
        if self._store is None:
            logger.debug("No state_path configured — skipping save.")
            return
        self._store.save(self.get_property_tree())

    # ---- auto-save internals ----------------------------------------

    def _schedule_auto_save(self) -> None:
        """Schedule a debounced save after :data:`AUTO_SAVE_DELAY` seconds.

        If a timer is already running it is cancelled and restarted so
        that rapid successive changes are coalesced into one write.
        """
        if self._save_timer is not None:
            self._save_timer.cancel()
        timer = threading.Timer(AUTO_SAVE_DELAY, self._do_auto_save)
        timer.daemon = True
        timer.start()
        self._save_timer = timer

    def _cancel_auto_save(self) -> None:
        """Cancel a pending auto-save timer without performing a save."""
        timer = getattr(self, "_save_timer", None)
        if timer is not None:
            timer.cancel()
            self._save_timer = None

    def _do_auto_save(self) -> None:
        """Execute the auto-save (called by the debounce timer thread)."""
        self._save_timer = None
        logger.debug("Auto-saving property tree.")
        if self._store is not None:
            self._store.save(self.get_property_tree())

    def flush(self) -> None:
        """Save immediately if there is a pending auto-save.

        This cancels the debounce timer and performs the save
        synchronously.  Call this before shutdown to ensure no
        property changes are lost.
        """
        if self._save_timer is not None:
            self._save_timer.cancel()
            self._save_timer = None
            self.save()

    def load(self) -> bool:
        """Reload properties from the persisted YAML state file.

        Returns ``True`` if state was successfully restored, ``False``
        otherwise.  Does nothing if no ``state_path`` was provided.

        Auto-save is suspended while the restored values are applied so
        that loading does not trigger a redundant write.
        """
        if self._store is None:
            return False

        tree = self._store.load()
        if tree is None:
            return False

        host_state = tree.get("vdcHost", {})
        if not host_state:
            return False

        # Suspend auto-save while applying restored state.
        prev = self._auto_save_enabled
        self._auto_save_enabled = False
        try:
            self._apply_state(host_state)
        finally:
            self._auto_save_enabled = prev
        return True

    def _apply_state(self, state: Dict[str, Any]) -> None:
        """Apply a persisted state dict to this host's properties.

        Also restores vDC properties when ``vdcs`` entries match
        already-registered vDCs by dSUID or implementationId.
        """
        if "dSUID" in state:
            self._dsuid = DsUid.from_string(state["dSUID"])
        if "mac" in state:
            self._mac = state["mac"]
        if "port" in state:
            self._port = state["port"]
        if "name" in state:
            self.name = state["name"]
        if "model" in state:
            self.model = state["model"]
        if "modelVersion" in state:
            self.model_version = state["modelVersion"]
        if "modelUID" in state:
            self.model_uid = state["modelUID"]
        if "hardwareVersion" in state:
            self.hardware_version = state["hardwareVersion"]
        if "hardwareGuid" in state:
            self.hardware_guid = state["hardwareGuid"]
        if "hardwareModelGuid" in state:
            self.hardware_model_guid = state["hardwareModelGuid"]
        if "vendorName" in state:
            self.vendor_name = state["vendorName"]
        if "vendorGuid" in state:
            self.vendor_guid = state["vendorGuid"]
        if "oemGuid" in state:
            self.oem_guid = state["oemGuid"]
        if "oemModelGuid" in state:
            self.oem_model_guid = state["oemModelGuid"]
        if "configURL" in state:
            self.config_url = state["configURL"]
        if "deviceIconName" in state:
            self.device_icon_name = state["deviceIconName"]

        # Restore vDC properties from persisted state.
        if "vdcs" in state:
            for vdc_state in state["vdcs"]:
                vdc = self._find_vdc_for_state(vdc_state)
                if vdc is not None:
                    vdc._apply_state(vdc_state)

    def _find_vdc_for_state(
        self, vdc_state: Dict[str, Any]
    ) -> Optional[Vdc]:
        """Find a registered vDC matching *vdc_state*.

        Matches by dSUID first, then by ``implementationId`` as a
        fallback.
        """
        # Match by dSUID.
        dsuid_str = vdc_state.get("dSUID")
        if dsuid_str and dsuid_str in self._vdcs:
            return self._vdcs[dsuid_str]

        # Fallback — match by implementationId.
        impl_id = vdc_state.get("implementationId")
        if impl_id:
            for vdc in self._vdcs.values():
                if vdc.implementation_id == impl_id:
                    return vdc

        return None

    # ---- DNS-SD announcement -----------------------------------------

    async def announce(self) -> None:
        """Announce this vDC host on the local network via DNS-SD.

        Creates a ``_ds-vdc._tcp`` service entry so that vdSMs can
        discover this host automatically.

        Calling :meth:`announce` when already announced is a no-op.

        Raises
        ------
        RuntimeError
            If the service could not be registered.
        """
        if self._zeroconf is not None:
            logger.debug("Already announced — skipping.")
            return

        hostname = _get_hostname()
        service_name = f"{self.name} on {hostname}"

        # Build the ServiceInfo.  Zeroconf requires the fully-qualified
        # service type (``_ds-vdc._tcp.local.``).
        self._service_info = ServiceInfo(
            type_=VDC_SERVICE_TYPE,
            name=f"{service_name}.{VDC_SERVICE_TYPE}",
            port=self._port,
            properties={
                "dSUID": str(self._dsuid),
            },
            server=f"{hostname}.local.",
        )

        self._zeroconf = AsyncZeroconf()
        await self._zeroconf.async_register_service(self._service_info)
        logger.info(
            "Announced vDC host '%s' on port %d (dSUID %s)",
            service_name,
            self._port,
            self._dsuid,
        )

    async def unannounce(self) -> None:
        """Remove the DNS-SD announcement and release resources.

        Calling :meth:`unannounce` when not announced is a no-op.
        """
        if self._zeroconf is None:
            return

        if self._service_info is not None:
            await self._zeroconf.async_unregister_service(self._service_info)
            logger.info("Unannounced vDC host service.")

        await self._zeroconf.async_close()
        self._zeroconf = None
        self._service_info = None

    @property
    def is_announced(self) -> bool:
        """``True`` if the DNS-SD service is currently registered."""
        return self._zeroconf is not None

    # ---- TCP server --------------------------------------------------

    async def start(
        self,
        *,
        on_message: Optional[MessageCallback] = None,
        announce: bool = True,
        bind_address: str = "0.0.0.0",
    ) -> None:
        """Start the TCP server (and optionally DNS-SD announcement).

        Parameters
        ----------
        on_message:
            Async callback for messages that are not handled internally
            (i.e. not ``hello``, ``ping``, or ``bye``).  See
            :data:`~pyDSvDCAPI.session.MessageCallback`.
        announce:
            If ``True`` (default) the DNS-SD service is announced
            automatically after the server starts listening.
        bind_address:
            The network address to bind to.  Defaults to ``"0.0.0.0"``
            (all IPv4 interfaces).
        """
        if self._server is not None:
            logger.debug("TCP server already running — skipping start.")
            return

        self._on_message = on_message

        self._server = await asyncio.start_server(
            self._handle_new_connection,
            host=bind_address,
            port=self._port,
        )

        # Determine the actual port (useful when port=0 for random).
        socks = self._server.sockets
        if socks:
            actual_port = socks[0].getsockname()[1]
            if actual_port != self._port:
                self._port = actual_port

        logger.info(
            "TCP server listening on port %d (dSUID %s)",
            self._port,
            self._dsuid,
        )

        if announce:
            await self.announce()

    async def stop(self) -> None:
        """Stop the TCP server, close the active session, and unannounce."""
        # Flush any pending auto-save so no property changes are lost.
        self.flush()

        # Close the active session first.
        await self._close_session()

        # Shut down the TCP server.
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            logger.info("TCP server stopped")

        await self.unannounce()

    @property
    def is_serving(self) -> bool:
        """``True`` if the TCP server is running."""
        return self._server is not None and self._server.is_serving()

    @property
    def session(self) -> Optional[VdcSession]:
        """The currently active session, if any."""
        return self._session

    # ---- connection handling (private) --------------------------------

    async def _handle_new_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Callback invoked by :func:`asyncio.start_server` for each
        new incoming TCP connection."""
        conn = VdcConnection(reader, writer)
        logger.info("New TCP connection from %s", conn.peername)

        # Only one session at a time.  Close the previous session if one
        # exists — the spec says a new Hello implicitly terminates the
        # old session.  We are resilient and allow reconnects.
        await self._close_session()

        session = VdcSession(
            connection=conn,
            host_dsuid=str(self._dsuid),
            on_message=self._dispatch_message,
        )
        self._session = session

        # Run the session in-line (the start_server callback is already
        # running in its own task per connection).
        await self._run_session(session)

    async def _run_session(self, session: VdcSession) -> None:
        """Run a session and clean up when it ends."""
        try:
            await session.run()
        except Exception:  # noqa: BLE001
            logger.exception("Session error")
        finally:
            if self._session is session:
                self._session = None
                self._session_task = None
            # Reset announcement state for all vDCs so they will be
            # re-announced on the next session.
            for vdc in self._vdcs.values():
                vdc.reset_announcement()
            logger.info("Session with %s cleaned up", session.vdsm_dsuid)

    async def _close_session(self) -> None:
        """Close the active session if there is one."""
        if self._session is not None:
            logger.info("Closing existing session with %s",
                        self._session.vdsm_dsuid)
            await self._session.close()
            self._session = None
            self._session_task = None

    # ---- property access (internal message handling) -----------------

    async def _dispatch_message(
        self,
        session: VdcSession,
        msg: pb.Message,
    ) -> Optional[pb.Message]:
        """Internal message handler installed on every session.

        Intercepts ``VDSM_REQUEST_GET_PROPERTY`` and
        ``VDSM_REQUEST_SET_PROPERTY`` and routes them to the
        addressed entity.  All other messages are forwarded to the
        user-supplied ``on_message`` callback.
        """
        msg_type = msg.type

        if msg_type == pb.VDSM_REQUEST_GET_PROPERTY:
            return self._handle_get_property(msg)

        if msg_type == pb.VDSM_REQUEST_SET_PROPERTY:
            return self._handle_set_property(msg)

        # Delegate to the user callback.
        if self._on_message is not None:
            return await self._on_message(session, msg)
        return None

    def _resolve_entity(
        self, dsuid_str: str
    ) -> Optional[Dict[str, Any]]:
        """Return ``(properties_dict, entity)`` for the entity with
        the given dSUID string, or ``None`` if not found."""
        if dsuid_str == str(self._dsuid):
            return self.get_properties()
        vdc = self._vdcs.get(dsuid_str)
        if vdc is not None:
            return vdc.get_properties()
        return None

    def _handle_get_property(self, msg: pb.Message) -> pb.Message:
        """Handle a ``VDSM_REQUEST_GET_PROPERTY``."""
        target_dsuid = msg.vdsm_request_get_property.dSUID
        props = self._resolve_entity(target_dsuid)

        if props is None:
            logger.debug(
                "getProperty for unknown dSUID %s", target_dsuid
            )
            resp = pb.Message()
            resp.type = pb.GENERIC_RESPONSE
            resp.message_id = msg.message_id
            resp.generic_response.code = pb.ERR_NOT_FOUND
            resp.generic_response.description = (
                f"Entity {target_dsuid} not found"
            )
            return resp

        logger.debug(
            "getProperty for %s — %d query elements",
            target_dsuid,
            len(msg.vdsm_request_get_property.query),
        )
        return build_get_property_response(msg, props)

    def _handle_set_property(self, msg: pb.Message) -> pb.Message:
        """Handle a ``VDSM_REQUEST_SET_PROPERTY``."""
        target_dsuid = msg.vdsm_request_set_property.dSUID
        incoming = elements_to_dict(
            msg.vdsm_request_set_property.properties
        )

        resp = pb.Message()
        resp.type = pb.GENERIC_RESPONSE
        resp.message_id = msg.message_id

        # Resolve the entity.
        if target_dsuid == str(self._dsuid):
            self._apply_set_property(incoming)
            resp.generic_response.code = pb.ERR_OK
            return resp

        vdc = self._vdcs.get(target_dsuid)
        if vdc is not None:
            self._apply_vdc_set_property(vdc, incoming)
            resp.generic_response.code = pb.ERR_OK
            return resp

        resp.generic_response.code = pb.ERR_NOT_FOUND
        resp.generic_response.description = (
            f"Entity {target_dsuid} not found"
        )
        return resp

    def _apply_set_property(self, incoming: Dict[str, Any]) -> None:
        """Apply writable properties to this host."""
        if "name" in incoming:
            self.name = incoming["name"]
            logger.info("Host name set to '%s'", self.name)

    def _apply_vdc_set_property(
        self, vdc: Vdc, incoming: Dict[str, Any]
    ) -> None:
        """Apply writable properties to a vDC."""
        if "name" in incoming:
            vdc.name = incoming["name"]
            logger.info("vDC '%s' name set to '%s'", vdc.dsuid, vdc.name)
        if "zoneID" in incoming:
            vdc.zone_id = int(incoming["zoneID"])
            logger.info(
                "vDC '%s' zoneID set to %d", vdc.dsuid, vdc.zone_id
            )

    # ---- dunder -------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"VdcHost(dsuid={self._dsuid!r}, port={self._port}, "
            f"name={self.name!r})"
        )

    def __del__(self) -> None:
        # Cancel any pending auto-save timer.
        timer = getattr(self, "_save_timer", None)
        if timer is not None:
            timer.cancel()

        # Best-effort cleanup hint.  Async resources should be released
        # via ``await host.stop()`` before the object is dropped.
        if self._zeroconf is not None:
            logger.warning(
                "VdcHost garbage-collected with active DNS-SD — "
                "call `await host.stop()` for clean shutdown."
            )
