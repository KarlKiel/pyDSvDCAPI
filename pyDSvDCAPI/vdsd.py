"""vdSD — virtual digitalSTROM device.

A :class:`Vdsd` is the API-visible unit that the vdSM (and dSS) recognise
as an individual device.  Each Vdsd has its own dSUID and is announced
separately via ``VDC_SEND_ANNOUNCE_DEVICE``.

One physical piece of hardware may be represented by **one or several**
Vdsd instances, depending on the rules laid out in the vDC API
(§5.2 / ``docs/device-splitting-guidelines.md``):

  * Each independent output → separate Vdsd.
  * Different zones / primary groups → separate Vdsd.
  * Buttons, sensors, binary inputs may be combined in one Vdsd.

To model "one physical device → N vdSDs" correctly the library provides
the :class:`Device` wrapper.  A Device holds one or more Vdsd instances
that share the first 16 bytes of their dSUID (byte 17 = sub-device
index).  For the common case of a physical device with only one
function, the Device simply contains one Vdsd.

Lifecycle
~~~~~~~~~

1. Create a :class:`Device` (or use the convenience ``Vdc.create_device``).
2. Attach one or more Vdsd instances via ``device.add_vdsd()``.
3. Configure each Vdsd (primary group, model features, …).
4. When configuration is final, call ``device.announce(session)`` to
   announce **all** contained Vdsd instances to the vdSM.
5. To change structural properties after announcement, call
   ``device.update(session, callback)`` which will vanish/re-announce.

Persistence
~~~~~~~~~~~

Vdsd state is serialised into the Vdc's property tree (and from there
into the VdcHost's YAML file).  On restore, the Vdc re-creates its
Device/Vdsd objects from the persisted data.

Usage example::

    from pyDSvDCAPI import Vdc, Device, Vdsd
    from pyDSvDCAPI.enums import ColorGroup

    vdc = Vdc(host=host, implementation_id="x-acme-light")

    # Single-vdSD device (common case)
    device = Device(vdc=vdc, dsuid=my_dsuid)
    vdsd = Vdsd(device=device, primary_group=ColorGroup.YELLOW,
                name="Kitchen Light")
    device.add_vdsd(vdsd)
    vdc.add_device(device)

    # Multi-vdSD device (e.g. combined light + shade)
    base = DsUid.from_enocean("0512ABCD")
    device2 = Device(vdc=vdc, dsuid=base)
    vdsd_light = Vdsd(device=device2, primary_group=ColorGroup.YELLOW,
                      subdevice_index=0, name="Light")
    vdsd_shade = Vdsd(device=device2, primary_group=ColorGroup.GREY,
                      subdevice_index=1, name="Shade")
    device2.add_vdsd(vdsd_light)
    device2.add_vdsd(vdsd_shade)
    vdc.add_device(device2)
"""

from __future__ import annotations

import logging
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Dict,
    List,
    Optional,
    Set,
)

from pyDSvDCAPI import genericVDC_pb2 as pb
from pyDSvDCAPI.dsuid import DsUid
from pyDSvDCAPI.enums import ColorGroup

if TYPE_CHECKING:
    from pyDSvDCAPI.binary_input import BinaryInput
    from pyDSvDCAPI.session import VdcSession
    from pyDSvDCAPI.vdc import Vdc

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Entity type string for a vdSD (common property ``type``).
ENTITY_TYPE_VDSD: str = "vdSD"


# ---------------------------------------------------------------------------
# Vdsd — one API-visible device
# ---------------------------------------------------------------------------

class Vdsd:
    """A single virtual digitalSTROM device (one dSUID).

    Each Vdsd is a fully addressable entity with its own dSUID,
    announced individually to the vdSM.

    Parameters
    ----------
    device:
        The owning :class:`Device`.  Provides the base dSUID and the
        link to the Vdc for persistence.
    primary_group:
        The dS class (colour) of this device.
    subdevice_index:
        Byte-17 sub-device enumeration within the hardware device.
        For single-vdSD devices, leave at 0.
    name:
        User-facing name (writable by the vdSM via ``setProperty``).
    model:
        Human-readable model description.
    model_version:
        Firmware / version string.
    model_uid:
        Functional model UID.  Derived from *model* when omitted.
    hardware_version:
        Hardware version string.
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
    zone_id:
        dS zone assigned by the vdSM.
    model_features:
        Set of model-feature flag names (e.g. ``{"blink",
        "identification"}``).  See §4.1.1.1 for valid names.
    """

    #: Attribute names whose mutation triggers a debounced auto-save.
    _TRACKED_ATTRS: ClassVar[frozenset] = frozenset({
        "name", "model", "model_version", "model_uid",
        "hardware_version", "hardware_guid", "hardware_model_guid",
        "vendor_name", "vendor_guid", "oem_guid", "oem_model_guid",
        "config_url", "device_icon_name", "device_class",
        "device_class_version", "zone_id",
    })

    # ---- attribute change tracking -----------------------------------

    def __setattr__(self, name: str, value: object) -> None:
        super().__setattr__(name, value)
        if (
            name in self._TRACKED_ATTRS
            and getattr(self, "_auto_save_enabled", False)
        ):
            device = getattr(self, "_device", None)
            if device is not None:
                device._schedule_auto_save()

    # ---- constructor -------------------------------------------------

    def __init__(
        self,
        *,
        device: Device,
        primary_group: ColorGroup = ColorGroup.BLACK,
        subdevice_index: int = 0,
        name: Optional[str] = None,
        model: str = "pyDSvDCAPI vdSD",
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
        zone_id: int = 0,
        model_features: Optional[Set[str]] = None,
    ) -> None:
        # Auto-save must be disabled during construction.
        self._auto_save_enabled: bool = False

        # --- parent reference -----------------------------------------
        self._device: Device = device

        # --- identity -------------------------------------------------
        self._subdevice_index: int = subdevice_index
        self._dsuid: DsUid = device.dsuid.derive_subdevice(
            subdevice_index
        )

        # --- common properties ----------------------------------------
        self.name: str = name or f"Device {subdevice_index}"
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

        # --- vdSD-specific properties ---------------------------------
        self._primary_group: ColorGroup = primary_group
        self.zone_id: int = zone_id
        self._model_features: Set[str] = (
            set(model_features) if model_features else set()
        )

        # --- components -----------------------------------------------
        self._binary_inputs: Dict[int, BinaryInput] = {}

        # --- runtime state --------------------------------------------
        self._active: bool = True
        self._announced: bool = False
        self._session: Optional[VdcSession] = None

        # Enable auto-save now that construction is complete.
        self._auto_save_enabled = True

    # ---- derived / computed helpers ----------------------------------

    @staticmethod
    def _derive_model_uid(model: str) -> str:
        """Derive a deterministic ``modelUID`` from the model name."""
        from pyDSvDCAPI.dsuid import DsUidNamespace
        uid = DsUid.from_name_in_space(model, DsUidNamespace.VDC)
        return str(uid)

    # ---- read-only accessors -----------------------------------------

    @property
    def dsuid(self) -> DsUid:
        """The dSUID of this vdSD (read-only)."""
        return self._dsuid

    @property
    def display_id(self) -> str:
        """Human-readable identification (hex dSUID)."""
        return str(self._dsuid)

    @property
    def entity_type(self) -> str:
        """Entity type string (always ``"vdSD"``)."""
        return ENTITY_TYPE_VDSD

    @property
    def subdevice_index(self) -> int:
        """Sub-device enumeration byte (byte 17)."""
        return self._subdevice_index

    @property
    def primary_group(self) -> ColorGroup:
        """The primary dS class (colour) of this device."""
        return self._primary_group

    @property
    def active(self) -> bool:
        """Whether this vdSD is currently active / operational."""
        return self._active

    @active.setter
    def active(self, value: bool) -> None:
        self._active = bool(value)

    @property
    def model_features(self) -> Set[str]:
        """Set of model-feature flag names (read-only view).

        Modify via :meth:`add_model_feature` /
        :meth:`remove_model_feature`.
        """
        return set(self._model_features)

    @property
    def device(self) -> Device:
        """The owning :class:`Device`."""
        return self._device

    @property
    def is_announced(self) -> bool:
        """``True`` if this vdSD has been announced to the vdSM."""
        return self._announced

    # ---- model features management -----------------------------------

    def add_model_feature(self, feature: str) -> None:
        """Add a model feature flag."""
        self._model_features.add(feature)

    def remove_model_feature(self, feature: str) -> None:
        """Remove a model feature flag (no-op if absent)."""
        self._model_features.discard(feature)

    # ---- binary input management -------------------------------------

    @property
    def binary_inputs(self) -> Dict[int, "BinaryInput"]:
        """All binary inputs keyed by ``dsIndex`` (read-only view)."""
        return dict(self._binary_inputs)

    def add_binary_input(self, bi: "BinaryInput") -> None:
        """Register a :class:`BinaryInput` with this vdSD.

        The input is indexed by its ``dsIndex``.  Adding an input
        with a ``dsIndex`` that already exists replaces the previous
        one.

        Raises
        ------
        ValueError
            If the binary input's owning vdSD is not this instance.
        """
        if bi.vdsd is not self:
            raise ValueError(
                f"BinaryInput belongs to a different vdSD "
                f"(expected {self._dsuid}, got {bi.vdsd.dsuid})"
            )
        self._binary_inputs[bi.ds_index] = bi
        logger.debug(
            "Added BinaryInput[%d] '%s' to vdSD %s",
            bi.ds_index, bi.name, self._dsuid,
        )
        # If already announced, start the alive timer immediately.
        if self._announced and self._session is not None:
            bi.start_alive_timer(self._session)
        self._schedule_auto_save_if_enabled()

    def remove_binary_input(self, ds_index: int) -> Optional["BinaryInput"]:
        """Remove a binary input by ``dsIndex``.

        Returns the removed :class:`BinaryInput` or ``None``.
        """
        bi = self._binary_inputs.pop(ds_index, None)
        if bi is not None:
            self._schedule_auto_save_if_enabled()
        return bi

    def get_binary_input(self, ds_index: int) -> Optional["BinaryInput"]:
        """Look up a binary input by ``dsIndex``."""
        return self._binary_inputs.get(ds_index)

    def _schedule_auto_save_if_enabled(self) -> None:
        """Trigger auto-save if enabled."""
        if self._auto_save_enabled:
            device = getattr(self, "_device", None)
            if device is not None:
                device._schedule_auto_save()

    # ---- property dict (for getProperty responses) -------------------

    def get_properties(self) -> Dict[str, Any]:
        """Return all properties as a flat dictionary.

        Keys match the vDC API property names.
        ``None`` values indicate unset optional properties.
        """
        props: Dict[str, Any] = {
            # Common properties
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
            # vdSD-specific properties
            "primaryGroup": int(self._primary_group),
            "zoneID": self.zone_id,
        }
        # modelFeatures — each enabled feature is a boolean True element.
        if self._model_features:
            props["modelFeatures"] = {
                f: True for f in sorted(self._model_features)
            }
        else:
            props["modelFeatures"] = {}

        # Binary input component properties (§4.3 / §4.1.2).
        if self._binary_inputs:
            props["binaryInputDescriptions"] = {
                str(bi.ds_index): bi.get_description_properties()
                for bi in self._binary_inputs.values()
            }
            props["binaryInputSettings"] = {
                str(bi.ds_index): bi.get_settings_properties()
                for bi in self._binary_inputs.values()
            }
            props["binaryInputStates"] = {
                str(bi.ds_index): bi.get_state_properties()
                for bi in self._binary_inputs.values()
            }

        return props

    # ---- property tree (for YAML persistence) ------------------------

    def get_property_tree(self) -> Dict[str, Any]:
        """Return the vdSD data for inclusion in the Device's persisted
        property tree.

        The structure is::

            subdeviceIndex: 0
            dSUID: "..."
            primaryGroup: 1
            name: "Kitchen Light"
            ...
            modelFeatures:
              - blink
              - identification
            zoneID: 0
        """
        node: Dict[str, Any] = {
            "subdeviceIndex": self._subdevice_index,
            "dSUID": str(self._dsuid),
            "primaryGroup": int(self._primary_group),
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
            "zoneID": self.zone_id,
        }
        if self._model_features:
            node["modelFeatures"] = sorted(self._model_features)

        # Binary inputs (description + settings; state is volatile).
        if self._binary_inputs:
            node["binaryInputs"] = [
                bi.get_property_tree()
                for bi in self._binary_inputs.values()
            ]

        return node

    # ---- state restoration -------------------------------------------

    def _apply_state(self, state: Dict[str, Any]) -> None:
        """Apply a persisted state dict to this vdSD's properties.

        Auto-save is suppressed during restoration.
        """
        prev = self._auto_save_enabled
        self._auto_save_enabled = False
        try:
            if "dSUID" in state:
                self._dsuid = DsUid.from_string(state["dSUID"])
            if "subdeviceIndex" in state:
                self._subdevice_index = int(state["subdeviceIndex"])
            if "primaryGroup" in state:
                self._primary_group = ColorGroup(
                    int(state["primaryGroup"])
                )
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
            if "zoneID" in state:
                self.zone_id = int(state["zoneID"])
            if "modelFeatures" in state:
                self._model_features = set(state["modelFeatures"])

            # Restore binary inputs.
            if "binaryInputs" in state:
                from pyDSvDCAPI.binary_input import BinaryInput
                for bi_state in state["binaryInputs"]:
                    idx = bi_state.get("dsIndex", 0)
                    bi = self._binary_inputs.get(idx)
                    if bi is None:
                        bi = BinaryInput(
                            vdsd=self,
                            ds_index=idx,
                        )
                        self._binary_inputs[idx] = bi
                    bi._apply_state(bi_state)
        finally:
            self._auto_save_enabled = prev

    # ---- announcement ------------------------------------------------

    async def announce(self, session: VdcSession) -> bool:
        """Announce this vdSD to the connected vdSM.

        Sends ``VDC_SEND_ANNOUNCE_DEVICE`` with this vdSD's dSUID
        and the containing vDC's dSUID, then awaits ``GENERIC_RESPONSE``.

        This method should normally be called via :meth:`Device.announce`
        rather than directly, to enforce the "all components defined
        first" contract.

        Returns
        -------
        bool
            ``True`` if the vdSM accepted the announcement.
        """
        vdc = self._device.vdc
        msg = pb.Message()
        msg.type = pb.VDC_SEND_ANNOUNCE_DEVICE
        msg.vdc_send_announce_device.dSUID = str(self._dsuid)
        msg.vdc_send_announce_device.vdc_dSUID = str(vdc.dsuid)

        logger.info(
            "Announcing vdSD '%s' (dSUID %s, vdc %s)",
            self.name, self._dsuid, vdc.dsuid,
        )

        response = await session.send_request(msg)

        code = response.generic_response.code
        if code == pb.ERR_OK:
            self._announced = True
            self._session = session
            # Start alive timers for all binary inputs.
            for bi in self._binary_inputs.values():
                bi.start_alive_timer(session)
            logger.info("vdSD '%s' announced successfully", self.name)
            return True

        description = response.generic_response.description
        logger.warning(
            "vdSD '%s' announcement failed: code=%s description=%s",
            self.name,
            pb.ResultCode.Name(code),
            description,
        )
        self._announced = False
        return False

    async def vanish(self, session: VdcSession) -> None:
        """Notify the vdSM that this vdSD has vanished.

        Sends ``VDC_SEND_VANISH`` as a notification (no response
        expected).  The vdSD is marked as unannounced after sending.
        """
        msg = pb.Message()
        msg.type = pb.VDC_SEND_VANISH
        msg.vdc_send_vanish.dSUID = str(self._dsuid)
        await session.send_notification(msg)
        self._announced = False
        self._session = None
        # Stop alive timers for all binary inputs.
        for bi in self._binary_inputs.values():
            bi.stop_alive_timer()
        logger.info(
            "vdSD '%s' vanished (dSUID %s)", self.name, self._dsuid
        )

    def reset_announcement(self) -> None:
        """Mark this vdSD as unannounced (e.g. on session disconnect)."""
        self._announced = False
        self._session = None
        # Stop alive timers for all binary inputs.
        for bi in self._binary_inputs.values():
            bi.stop_alive_timer()

    # ---- dunder -------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"Vdsd(dsuid={self._dsuid!r}, "
            f"primary_group={self._primary_group!r}, "
            f"name={self.name!r})"
        )


# ---------------------------------------------------------------------------
# Device — physical hardware wrapper
# ---------------------------------------------------------------------------

class Device:
    """Represents a single physical hardware device.

    A Device groups one or more :class:`Vdsd` instances that share the
    same base dSUID (bytes 0-15).  The Device is the unit of
    announcement and update — it ensures that:

    * All contained Vdsd instances are announced or vanished together.
    * Structural changes (adding/removing vdSDs) are done atomically
      via a vanish→modify→re-announce cycle.
    * Persistence is handled centrally through the Vdc/VdcHost chain.

    Parameters
    ----------
    vdc:
        The owning :class:`Vdc`.
    dsuid:
        The base dSUID for this device.  Individual vdSDs will derive
        their dSUIDs from this base using ``derive_subdevice(index)``.
        For single-vdSD devices, the default sub-device index 0 is
        used directly.
    """

    def __init__(self, *, vdc: Vdc, dsuid: DsUid) -> None:
        self._vdc: Vdc = vdc
        # Store the device-level base dSUID (sub-device index 0).
        self._dsuid: DsUid = dsuid.device_base()
        # Ordered list preserving insertion order.
        self._vdsds: Dict[int, Vdsd] = {}  # keyed by subdevice_index
        self._announced: bool = False

    # ---- accessors ---------------------------------------------------

    @property
    def vdc(self) -> Vdc:
        """The owning :class:`Vdc`."""
        return self._vdc

    @property
    def dsuid(self) -> DsUid:
        """The base dSUID (sub-device index 0) for this device."""
        return self._dsuid

    @property
    def vdsds(self) -> Dict[int, Vdsd]:
        """All contained Vdsd instances keyed by sub-device index."""
        return dict(self._vdsds)

    @property
    def is_announced(self) -> bool:
        """``True`` if all vdSDs have been announced."""
        return self._announced

    # ---- auto-save ---------------------------------------------------

    def _schedule_auto_save(self) -> None:
        """Forward auto-save request up through the Vdc → VdcHost chain."""
        self._vdc._schedule_auto_save()

    # ---- vdSD management ---------------------------------------------

    def add_vdsd(self, vdsd: Vdsd) -> None:
        """Register a :class:`Vdsd` with this device.

        The vdSD is indexed by its sub-device index.  Adding a vdSD
        with a sub-device index that already exists replaces the
        previous one.

        Raises
        ------
        RuntimeError
            If the device is currently announced.  Use :meth:`update`
            to change structure after announcement.
        ValueError
            If the vdSD's base dSUID does not match this device.
        """
        if self._announced:
            raise RuntimeError(
                "Cannot add vdSD to an announced device.  "
                "Use device.update() to modify structure after "
                "announcement."
            )
        if not vdsd.dsuid.same_device(self._dsuid):
            raise ValueError(
                f"vdSD dSUID {vdsd.dsuid} does not share the same "
                f"base as device dSUID {self._dsuid}"
            )
        idx = vdsd.subdevice_index
        self._vdsds[idx] = vdsd
        logger.debug(
            "Added vdSD '%s' (sub-device %d) to device %s",
            vdsd.name, idx, self._dsuid,
        )

    def remove_vdsd(self, subdevice_index: int) -> Optional[Vdsd]:
        """Remove a vdSD by sub-device index.

        Returns the removed :class:`Vdsd` or ``None``.

        Raises
        ------
        RuntimeError
            If the device is currently announced.
        """
        if self._announced:
            raise RuntimeError(
                "Cannot remove vdSD from an announced device.  "
                "Use device.update() to modify structure after "
                "announcement."
            )
        return self._vdsds.pop(subdevice_index, None)

    def get_vdsd(self, subdevice_index: int) -> Optional[Vdsd]:
        """Look up a vdSD by sub-device index."""
        return self._vdsds.get(subdevice_index)

    def get_vdsd_by_dsuid(self, dsuid: DsUid) -> Optional[Vdsd]:
        """Look up a vdSD by its full dSUID."""
        dsuid_str = str(dsuid)
        for vdsd in self._vdsds.values():
            if str(vdsd.dsuid) == dsuid_str:
                return vdsd
        return None

    # ---- announcement ------------------------------------------------

    async def announce(self, session: VdcSession) -> int:
        """Announce all contained vdSDs to the vdSM.

        Call this only when all components (inputs, outputs, etc.) of
        every vdSD have been fully defined.  The dSS does not handle
        structural updates gracefully — use :meth:`update` to modify
        an already-announced device.

        Returns
        -------
        int
            Number of vdSDs successfully announced.

        Raises
        ------
        RuntimeError
            If the device has no vdSDs or is already announced.
        """
        if not self._vdsds:
            raise RuntimeError(
                "Cannot announce a device with no vdSDs"
            )
        if self._announced:
            raise RuntimeError(
                "Device is already announced.  "
                "Use device.update() to re-announce after changes."
            )

        count = 0
        for vdsd in self._vdsds.values():
            try:
                ok = await vdsd.announce(session)
                if ok:
                    count += 1
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Failed to announce vdSD '%s'", vdsd.name
                )

        self._announced = count == len(self._vdsds)
        logger.info(
            "Device %s: announced %d/%d vdSDs",
            self._dsuid, count, len(self._vdsds),
        )
        return count

    async def vanish(self, session: VdcSession) -> None:
        """Notify the vdSM that all vdSDs of this device have vanished.

        Sends ``VDC_SEND_VANISH`` for each announced vdSD.
        """
        for vdsd in self._vdsds.values():
            if vdsd.is_announced:
                try:
                    await vdsd.vanish(session)
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "Failed to vanish vdSD '%s'", vdsd.name
                    )
        self._announced = False
        logger.info("Device %s: all vdSDs vanished", self._dsuid)

    async def update(
        self,
        session: VdcSession,
        modify: Callable[[Device], None],
    ) -> int:
        """Vanish, apply structural changes, and re-announce.

        This is the **only** safe way to change normally immutable
        properties or the set of vdSDs after a device has been
        announced.  The dSS cannot handle in-place structural updates,
        so the device must vanish first.

        Parameters
        ----------
        session:
            The active session.
        modify:
            A callback that receives this :class:`Device` with all
            vdSDs in unannounced state.  Add, remove, or reconfigure
            vdSDs inside this callback.

        Returns
        -------
        int
            Number of vdSDs successfully re-announced.

        Example::

            def reconfigure(dev: Device):
                dev.get_vdsd(0).name = "Updated Name"
                dev.add_vdsd(Vdsd(device=dev, subdevice_index=2,
                                  primary_group=ColorGroup.GREY))

            await device.update(session, reconfigure)
        """
        # Step 1: Vanish all currently announced vdSDs.
        if self._announced:
            await self.vanish(session)

        # Step 2: Mark as unannounced to allow structural modifications.
        self._announced = False

        # Step 3: Let the caller modify the device.
        modify(self)

        # Step 4: Re-announce.
        count = await self.announce(session)

        # Step 5: Trigger persistence so the new structure is saved.
        self._vdc._schedule_auto_save()

        return count

    def reset_announcement(self) -> None:
        """Reset announcement state for this device and all vdSDs.

        Called by the vDC when the session ends.
        """
        for vdsd in self._vdsds.values():
            vdsd.reset_announcement()
        self._announced = False

    # ---- persistence -------------------------------------------------

    def get_property_tree(self) -> Dict[str, Any]:
        """Return the Device data for inclusion in the Vdc's persisted
        property tree.

        Structure::

            baseDsUID: "..."
            vdsds:
              - subdeviceIndex: 0
                dSUID: "..."
                ...
              - subdeviceIndex: 2
                dSUID: "..."
                ...
        """
        return {
            "baseDsUID": str(self._dsuid),
            "vdsds": [
                vdsd.get_property_tree()
                for vdsd in self._vdsds.values()
            ],
        }

    def _apply_state(self, state: Dict[str, Any]) -> None:
        """Restore Device state from a persisted dict.

        Creates Vdsd instances for any entries in ``vdsds`` that do
        not already exist.  Existing vdSDs matched by sub-device
        index are updated in-place.
        """
        if "baseDsUID" in state:
            self._dsuid = DsUid.from_string(
                state["baseDsUID"]
            ).device_base()

        for vdsd_state in state.get("vdsds", []):
            idx = vdsd_state.get("subdeviceIndex", 0)
            vdsd = self._vdsds.get(idx)
            if vdsd is None:
                # Create a new Vdsd for this persisted entry.
                primary_group = ColorGroup(
                    vdsd_state.get("primaryGroup", ColorGroup.BLACK)
                )
                vdsd = Vdsd(
                    device=self,
                    subdevice_index=idx,
                    primary_group=primary_group,
                )
                self._vdsds[idx] = vdsd
            vdsd._apply_state(vdsd_state)

    # ---- dunder -------------------------------------------------------

    def __repr__(self) -> str:
        n = len(self._vdsds)
        return (
            f"Device(dsuid={self._dsuid!r}, vdsds={n})"
        )
