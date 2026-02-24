"""vDC — virtual Device Connector entity.

A :class:`Vdc` represents a logical virtual Device Connector in the
digitalSTROM system.  A vDC host (:class:`~pyDSvDCAPI.vdc_host.VdcHost`)
manages one or more vDCs, each of which in turn manages a set of
virtual dS devices (vdSDs).

Each vDC has the *common properties* shared by all addressable entities,
plus **vDC-specific** properties:

* **capabilities** — metering, identification, dynamicDefinitions
* **zoneID** — default dS zone assigned by the vdSM
* **implementationId** — unique identifier for the vDC implementation

Auto-save
~~~~~~~~~

When the owning :class:`VdcHost` has persistence enabled, any mutation
of a *tracked* property on the Vdc triggers a debounced auto-save on the
host.  The Vdc does **not** maintain its own persistence store — it
delegates entirely to its parent.

Announcement
~~~~~~~~~~~~

After the vDC session with a vdSM is established the host must announce
every registered vDC with :meth:`Vdc.announce`.  This sends a
``VDC_SEND_ANNOUNCE_VDC`` protobuf request carrying the vDC's dSUID and
waits for a ``GENERIC_RESPONSE``.

Usage example::

    from pyDSvDCAPI import VdcHost, Vdc

    host = VdcHost(name="My Gateway", state_path="state.yaml")
    vdc = Vdc(
        host=host,
        implementation_id="x-mycompany-light",
        name="Light Controller",
        model="Light vDC v1",
    )
    host.add_vdc(vdc)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Dict, Optional

from pyDSvDCAPI import genericVDC_pb2 as pb
from pyDSvDCAPI.dsuid import DsUid, DsUidNamespace

if TYPE_CHECKING:
    from pyDSvDCAPI.session import VdcSession
    from pyDSvDCAPI.vdc_host import VdcHost

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Entity type string for a vDC (common property ``type``).
ENTITY_TYPE_VDC: str = "vDC"


# ---------------------------------------------------------------------------
# Capabilities helper
# ---------------------------------------------------------------------------

@dataclass
class VdcCapabilities:
    """Boolean capability flags for a vDC.

    Each flag maps directly to the documented vDC capabilities:

    * **metering** — the vDC provides metering data.
    * **identification** — the vDC can identify itself (e.g. blink a LED).
    * **dynamic_definitions** — the vDC supports dynamic device
      definitions such as ``propertyDescriptions`` and
      ``actionDescriptions``.
    """

    metering: bool = False
    identification: bool = False
    dynamic_definitions: bool = False

    def to_dict(self) -> Dict[str, bool]:
        """Return the capabilities as a ``{name: bool}`` dictionary."""
        return {
            "metering": self.metering,
            "identification": self.identification,
            "dynamicDefinitions": self.dynamic_definitions,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> VdcCapabilities:
        """Create a :class:`VdcCapabilities` from a persisted dictionary."""
        return cls(
            metering=bool(data.get("metering", False)),
            identification=bool(data.get("identification", False)),
            dynamic_definitions=bool(data.get("dynamicDefinitions", False)),
        )


# ---------------------------------------------------------------------------
# Vdc
# ---------------------------------------------------------------------------

class Vdc:
    """Represents a logical virtual Device Connector.

    Parameters
    ----------
    host:
        The owning :class:`VdcHost`.  Used for triggering persistence
        and obtaining the active session for announcement.
    implementation_id:
        Unique identifier for this vDC implementation.  Non-digitalSTROM
        vDCs must use an ``"x-company-"`` prefix.  Used together with
        the host dSUID to derive the vDC's own dSUID when *dsuid* is not
        provided.
    dsuid:
        Explicit dSUID.  When omitted the dSUID is derived from
        *implementation_id* using :meth:`DsUid.from_name_in_space`
        with the well-known ``VDC`` namespace.
    name:
        User-facing name of this vDC.
    model:
        Human-readable model description.
    model_version:
        Firmware / version string.
    model_uid:
        System-unique ID for the functional model.  Derived
        deterministically from *model* when omitted.
    hardware_version:
        Human-readable hardware version string.
    hardware_guid:
        Native hardware GUID in ``schema:id`` format.
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
        URL to the web configuration interface.
    device_icon_16:
        16×16 PNG icon as ``bytes``.
    device_icon_name:
        Filename-safe icon identifier for caching.
    device_class:
        digitalSTROM device class profile name.
    device_class_version:
        Revision number of the device class profile.
    capabilities:
        :class:`VdcCapabilities` flags.
    zone_id:
        Default dS zone ID assigned by the vdSM.
    """

    #: Attribute names whose mutation triggers a debounced auto-save
    #: on the parent :class:`VdcHost`.
    _TRACKED_ATTRS: ClassVar[frozenset] = frozenset({
        "name", "model", "model_version", "model_uid",
        "hardware_version", "hardware_guid", "hardware_model_guid",
        "vendor_name", "vendor_guid", "oem_guid", "oem_model_guid",
        "config_url", "device_icon_name", "device_class",
        "device_class_version", "zone_id",
    })

    # ---- attribute change tracking -----------------------------------

    def __setattr__(self, name: str, value: object) -> None:
        """Set an attribute and schedule an auto-save on the host.

        Only attributes listed in :attr:`_TRACKED_ATTRS` are monitored.
        Auto-save is suppressed while ``_auto_save_enabled`` is ``False``
        (during ``__init__`` and state restoration).
        """
        super().__setattr__(name, value)
        if (
            name in self._TRACKED_ATTRS
            and getattr(self, "_auto_save_enabled", False)
        ):
            host = getattr(self, "_host", None)
            if host is not None:
                host._schedule_auto_save()

    # ---- constructor -------------------------------------------------

    def __init__(
        self,
        *,
        host: VdcHost,
        implementation_id: str,
        dsuid: Optional[DsUid] = None,
        name: Optional[str] = None,
        model: str = "pyDSvDCAPI vDC",
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
        device_class: Optional[str] = None,
        device_class_version: Optional[str] = None,
        capabilities: Optional[VdcCapabilities] = None,
        zone_id: int = 0,
    ) -> None:
        # Auto-save must be disabled during construction.
        self._auto_save_enabled: bool = False

        # --- parent reference -----------------------------------------
        self._host: VdcHost = host

        # --- identity -------------------------------------------------
        self._implementation_id: str = implementation_id

        if dsuid is not None:
            self._dsuid: DsUid = dsuid
        else:
            self._dsuid = self._derive_dsuid(implementation_id)

        # --- common properties ----------------------------------------
        self.name: str = name or implementation_id
        self.model: str = model
        self.model_version: Optional[str] = model_version
        self.model_uid: str = (
            model_uid or self._derive_model_uid(self.model)
        )
        self.hardware_version: Optional[str] = hardware_version
        self.hardware_guid: Optional[str] = hardware_guid
        self.hardware_model_guid: Optional[str] = hardware_model_guid
        self.vendor_name: Optional[str] = vendor_name
        self.vendor_guid: Optional[str] = vendor_guid
        self.oem_guid: Optional[str] = oem_guid
        self.oem_model_guid: Optional[str] = oem_model_guid
        self.config_url: Optional[str] = config_url
        self.device_icon_16: Optional[bytes] = device_icon_16
        self.device_icon_name: Optional[str] = device_icon_name
        self.device_class: Optional[str] = device_class
        self.device_class_version: Optional[str] = device_class_version

        # --- vDC-specific properties ----------------------------------
        self._capabilities: VdcCapabilities = (
            capabilities or VdcCapabilities()
        )
        self.zone_id: int = zone_id

        # --- runtime state --------------------------------------------
        self._active: bool = True
        self._announced: bool = False

        # Enable auto-save now that construction is complete.
        self._auto_save_enabled = True

    # ---- derived / computed properties --------------------------------

    @staticmethod
    def _derive_dsuid(implementation_id: str) -> DsUid:
        """Derive a vDC dSUID from *implementation_id*.

        Uses UUIDv5 hashing with the well-known VDC namespace so that
        the same implementation ID always produces the same dSUID.
        """
        return DsUid.from_name_in_space(
            implementation_id, DsUidNamespace.VDC
        )

    @staticmethod
    def _derive_model_uid(model: str) -> str:
        """Derive a deterministic ``modelUID`` from the model name."""
        uid = DsUid.from_name_in_space(model, DsUidNamespace.VDC)
        return str(uid)

    # ---- read-only accessors -----------------------------------------

    @property
    def dsuid(self) -> DsUid:
        """The dSUID of this vDC (read-only)."""
        return self._dsuid

    @property
    def display_id(self) -> str:
        """Human-readable identification (hex dSUID)."""
        return str(self._dsuid)

    @property
    def entity_type(self) -> str:
        """Entity type string (always ``"vDC"``)."""
        return ENTITY_TYPE_VDC

    @property
    def implementation_id(self) -> str:
        """The unique implementation identifier (read-only)."""
        return self._implementation_id

    @property
    def active(self) -> bool:
        """Whether this vDC is currently active / operational."""
        return self._active

    @active.setter
    def active(self, value: bool) -> None:
        self._active = bool(value)

    @property
    def capabilities(self) -> VdcCapabilities:
        """Capability flags (read-only structure).

        To modify, replace the entire object::

            vdc.capabilities = VdcCapabilities(metering=True)
        """
        return self._capabilities

    @capabilities.setter
    def capabilities(self, value: VdcCapabilities) -> None:
        self._capabilities = value
        if getattr(self, "_auto_save_enabled", False):
            host = getattr(self, "_host", None)
            if host is not None:
                host._schedule_auto_save()

    @property
    def host(self) -> VdcHost:
        """The owning :class:`VdcHost` (read-only)."""
        return self._host

    @property
    def is_announced(self) -> bool:
        """``True`` if this vDC has been announced to the vdSM."""
        return self._announced

    # ---- common-property dict ----------------------------------------

    def get_properties(self) -> Dict[str, Any]:
        """Return all properties as a flat dictionary.

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
            "deviceClass": self.device_class,
            "deviceClassVersion": self.device_class_version,
            "active": self._active,
            "implementationId": self._implementation_id,
            "capabilities": self._capabilities.to_dict(),
            "zoneID": self.zone_id,
        }

    # ---- property tree (for persistence) -----------------------------

    def get_property_tree(self) -> Dict[str, Any]:
        """Return the vDC data suitable for inclusion in the host's
        YAML property tree.

        The structure is::

            dSUID: "..."
            implementationId: "x-company-light"
            name: "Light Controller"
            model: "Light vDC v1"
            ...
            capabilities:
              metering: false
              identification: false
              dynamicDefinitions: false
            zoneID: 0
        """
        node: Dict[str, Any] = {
            "dSUID": str(self._dsuid),
            "implementationId": self._implementation_id,
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
            "deviceClass": self.device_class,
            "deviceClassVersion": self.device_class_version,
            "capabilities": self._capabilities.to_dict(),
            "zoneID": self.zone_id,
        }
        return node

    # ---- state restoration -------------------------------------------

    def _apply_state(self, state: Dict[str, Any]) -> None:
        """Apply a persisted state dict to this vDC's properties.

        Auto-save is suppressed during restoration to avoid triggering
        a redundant write.
        """
        prev = self._auto_save_enabled
        self._auto_save_enabled = False
        try:
            if "dSUID" in state:
                self._dsuid = DsUid.from_string(state["dSUID"])
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
            if "deviceClass" in state:
                self.device_class = state["deviceClass"]
            if "deviceClassVersion" in state:
                self.device_class_version = state["deviceClassVersion"]
            if "capabilities" in state:
                self._capabilities = VdcCapabilities.from_dict(
                    state["capabilities"]
                )
            if "zoneID" in state:
                self.zone_id = state["zoneID"]
        finally:
            self._auto_save_enabled = prev

    # ---- announcement ------------------------------------------------

    async def announce(self, session: VdcSession) -> bool:
        """Announce this vDC to the connected vdSM.

        Sends a ``VDC_SEND_ANNOUNCE_VDC`` protobuf request with this
        vDC's dSUID and awaits a ``GENERIC_RESPONSE``.

        Parameters
        ----------
        session:
            The active :class:`VdcSession` to use for sending the
            announcement.

        Returns
        -------
        bool
            ``True`` if the vdSM accepted the announcement
            (``ERR_OK``), ``False`` otherwise.

        Raises
        ------
        ConnectionError
            If the session is not in the ``ACTIVE`` state.
        asyncio.TimeoutError
            If the vdSM does not respond within the request timeout.
        """
        msg = pb.Message()
        msg.type = pb.VDC_SEND_ANNOUNCE_VDC
        msg.vdc_send_announce_vdc.dSUID = str(self._dsuid)

        logger.info(
            "Announcing vDC '%s' (dSUID %s)", self.name, self._dsuid
        )

        response = await session.send_request(msg)

        code = response.generic_response.code
        if code == pb.ERR_OK:
            self._announced = True
            logger.info(
                "vDC '%s' announced successfully", self.name
            )
            return True

        description = response.generic_response.description
        logger.warning(
            "vDC '%s' announcement failed: code=%s description=%s",
            self.name,
            pb.ResultCode.Name(code),
            description,
        )
        self._announced = False
        return False

    def reset_announcement(self) -> None:
        """Reset the announcement state (e.g. on session disconnect).

        Called by the host when the session ends to mark all vDCs as
        unannounced so they will be re-announced on the next session.
        """
        self._announced = False

    # ---- dunder -------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"Vdc(dsuid={self._dsuid!r}, "
            f"implementation_id={self._implementation_id!r}, "
            f"name={self.name!r})"
        )
