"""Type stubs for the generated genericVDC protobuf module."""

from typing import Optional

from google.protobuf.descriptor import FileDescriptor
from google.protobuf.internal.containers import RepeatedCompositeFieldContainer, RepeatedScalarFieldContainer
from google.protobuf.message import Message as _Message

DESCRIPTOR: FileDescriptor

# ---------------------------------------------------------------------------
# Enum: Type
# ---------------------------------------------------------------------------

class _Type:
    GENERIC_RESPONSE: int
    VDSM_REQUEST_HELLO: int
    VDC_RESPONSE_HELLO: int
    VDSM_REQUEST_GET_PROPERTY: int
    VDC_RESPONSE_GET_PROPERTY: int
    VDSM_REQUEST_SET_PROPERTY: int
    VDC_RESPONSE_SET_PROPERTY: int
    VDSM_SEND_PING: int
    VDC_SEND_PONG: int
    VDC_SEND_ANNOUNCE_DEVICE: int
    VDC_SEND_VANISH: int
    VDC_SEND_PUSH_PROPERTY: int
    VDSM_SEND_REMOVE: int
    VDSM_SEND_BYE: int
    VDSM_NOTIFICATION_CALL_SCENE: int
    VDSM_NOTIFICATION_SAVE_SCENE: int
    VDSM_NOTIFICATION_UNDO_SCENE: int
    VDSM_NOTIFICATION_SET_LOCAL_PRIO: int
    VDSM_NOTIFICATION_CALL_MIN_SCENE: int
    VDSM_NOTIFICATION_IDENTIFY: int
    VDSM_NOTIFICATION_SET_CONTROL_VALUE: int
    VDSM_NOTIFICATION_DIM_CHANNEL: int
    VDSM_NOTIFICATION_SET_OUTPUT_CHANNEL_VALUE: int
    VDC_SEND_IDENTIFY: int
    VDC_SEND_ANNOUNCE_VDC: int
    VDSM_REQUEST_GENERIC_REQUEST: int

    @staticmethod
    def Name(number: int) -> str: ...
    @staticmethod
    def Value(name: str) -> int: ...

Type: _Type

# Top-level enum constants
GENERIC_RESPONSE: int
VDSM_REQUEST_HELLO: int
VDC_RESPONSE_HELLO: int
VDSM_REQUEST_GET_PROPERTY: int
VDC_RESPONSE_GET_PROPERTY: int
VDSM_REQUEST_SET_PROPERTY: int
VDC_RESPONSE_SET_PROPERTY: int
VDSM_SEND_PING: int
VDC_SEND_PONG: int
VDC_SEND_ANNOUNCE_DEVICE: int
VDC_SEND_VANISH: int
VDC_SEND_PUSH_PROPERTY: int
VDSM_SEND_REMOVE: int
VDSM_SEND_BYE: int
VDSM_NOTIFICATION_CALL_SCENE: int
VDSM_NOTIFICATION_SAVE_SCENE: int
VDSM_NOTIFICATION_UNDO_SCENE: int
VDSM_NOTIFICATION_SET_LOCAL_PRIO: int
VDSM_NOTIFICATION_CALL_MIN_SCENE: int
VDSM_NOTIFICATION_IDENTIFY: int
VDSM_NOTIFICATION_SET_CONTROL_VALUE: int
VDSM_NOTIFICATION_DIM_CHANNEL: int
VDSM_NOTIFICATION_SET_OUTPUT_CHANNEL_VALUE: int
VDC_SEND_IDENTIFY: int
VDC_SEND_ANNOUNCE_VDC: int
VDSM_REQUEST_GENERIC_REQUEST: int

# ---------------------------------------------------------------------------
# Enum: ResultCode
# ---------------------------------------------------------------------------

class _ResultCode:
    ERR_OK: int
    ERR_MESSAGE_UNKNOWN: int
    ERR_INCOMPATIBLE_API: int
    ERR_SERVICE_NOT_AVAILABLE: int
    ERR_INSUFFICIENT_STORAGE: int
    ERR_FORBIDDEN: int
    ERR_NOT_IMPLEMENTED: int
    ERR_NO_CONTENT_FOR_ARRAY: int
    ERR_INVALID_VALUE_TYPE: int
    ERR_MISSING_SUBMESSAGE: int
    ERR_MISSING_DATA: int
    ERR_NOT_FOUND: int
    ERR_NOT_AUTHORIZED: int

    @staticmethod
    def Name(number: int) -> str: ...
    @staticmethod
    def Value(name: str) -> int: ...

ResultCode: _ResultCode

# Top-level enum constants
ERR_OK: int
ERR_MESSAGE_UNKNOWN: int
ERR_INCOMPATIBLE_API: int
ERR_SERVICE_NOT_AVAILABLE: int
ERR_INSUFFICIENT_STORAGE: int
ERR_FORBIDDEN: int
ERR_NOT_IMPLEMENTED: int
ERR_NO_CONTENT_FOR_ARRAY: int
ERR_INVALID_VALUE_TYPE: int
ERR_MISSING_SUBMESSAGE: int
ERR_MISSING_DATA: int
ERR_NOT_FOUND: int
ERR_NOT_AUTHORIZED: int

# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

class vdsm_RequestHello(_Message):
    dSUID: str
    api_version: int
    def __init__(self, *, dSUID: Optional[str] = ..., api_version: Optional[int] = ...) -> None: ...

class vdc_ResponseHello(_Message):
    dSUID: str
    def __init__(self, *, dSUID: Optional[str] = ...) -> None: ...

class vdc_SendAnnounceDevice(_Message):
    dSUID: str
    vdc_dSUID: str
    def __init__(self, *, dSUID: Optional[str] = ..., vdc_dSUID: Optional[str] = ...) -> None: ...

class vdc_SendAnnounceVdc(_Message):
    dSUID: str
    def __init__(self, *, dSUID: Optional[str] = ...) -> None: ...

class vdc_SendVanish(_Message):
    dSUID: str
    def __init__(self, *, dSUID: Optional[str] = ...) -> None: ...

class vdc_SendIdentify(_Message):
    dSUID: str
    def __init__(self, *, dSUID: Optional[str] = ...) -> None: ...

class vdsm_SendBye(_Message):
    dSUID: str
    def __init__(self, *, dSUID: Optional[str] = ...) -> None: ...

class vdsm_SendRemove(_Message):
    dSUID: str
    def __init__(self, *, dSUID: Optional[str] = ...) -> None: ...

class PropertyValue(_Message):
    v_bool: bool
    v_uint64: int
    v_int64: int
    v_double: float
    v_string: str
    v_bytes: bytes
    def __init__(
        self,
        *,
        v_bool: Optional[bool] = ...,
        v_uint64: Optional[int] = ...,
        v_int64: Optional[int] = ...,
        v_double: Optional[float] = ...,
        v_string: Optional[str] = ...,
        v_bytes: Optional[bytes] = ...,
    ) -> None: ...

class PropertyElement(_Message):
    name: str
    @property
    def value(self) -> PropertyValue: ...
    @property
    def elements(self) -> RepeatedCompositeFieldContainer[PropertyElement]: ...
    def __init__(
        self,
        *,
        name: Optional[str] = ...,
        value: Optional[PropertyValue] = ...,
        elements: Optional[list[PropertyElement]] = ...,
    ) -> None: ...

class vdsm_RequestGetProperty(_Message):
    dSUID: str
    @property
    def query(self) -> RepeatedCompositeFieldContainer[PropertyElement]: ...
    def __init__(self, *, dSUID: Optional[str] = ..., query: Optional[list[PropertyElement]] = ...) -> None: ...

class vdc_ResponseGetProperty(_Message):
    @property
    def properties(self) -> RepeatedCompositeFieldContainer[PropertyElement]: ...
    def __init__(self, *, properties: Optional[list[PropertyElement]] = ...) -> None: ...

class vdsm_RequestSetProperty(_Message):
    dSUID: str
    @property
    def properties(self) -> RepeatedCompositeFieldContainer[PropertyElement]: ...
    def __init__(self, *, dSUID: Optional[str] = ..., properties: Optional[list[PropertyElement]] = ...) -> None: ...

class vdsm_RequestGenericRequest(_Message):
    dSUID: str
    methodname: str
    @property
    def params(self) -> RepeatedCompositeFieldContainer[PropertyElement]: ...
    def __init__(
        self,
        *,
        dSUID: Optional[str] = ...,
        methodname: Optional[str] = ...,
        params: Optional[list[PropertyElement]] = ...,
    ) -> None: ...

class vdsm_SendPing(_Message):
    dSUID: str
    def __init__(self, *, dSUID: Optional[str] = ...) -> None: ...

class vdc_SendPong(_Message):
    dSUID: str
    def __init__(self, *, dSUID: Optional[str] = ...) -> None: ...

class vdc_SendPushNotification(_Message):
    dSUID: str
    @property
    def changedproperties(self) -> RepeatedCompositeFieldContainer[PropertyElement]: ...
    @property
    def deviceevents(self) -> RepeatedCompositeFieldContainer[PropertyElement]: ...
    def __init__(
        self,
        *,
        dSUID: Optional[str] = ...,
        changedproperties: Optional[list[PropertyElement]] = ...,
        deviceevents: Optional[list[PropertyElement]] = ...,
    ) -> None: ...

class vdc_SendPushProperty(_Message):
    dSUID: str
    @property
    def properties(self) -> RepeatedCompositeFieldContainer[PropertyElement]: ...
    def __init__(self, *, dSUID: Optional[str] = ..., properties: Optional[list[PropertyElement]] = ...) -> None: ...

class vdsm_NotificationCallScene(_Message):
    @property
    def dSUID(self) -> RepeatedScalarFieldContainer[str]: ...
    scene: int
    force: bool
    group: int
    zone_id: int
    def __init__(
        self,
        *,
        dSUID: Optional[list[str]] = ...,
        scene: Optional[int] = ...,
        force: Optional[bool] = ...,
        group: Optional[int] = ...,
        zone_id: Optional[int] = ...,
    ) -> None: ...

class vdsm_NotificationSaveScene(_Message):
    @property
    def dSUID(self) -> RepeatedScalarFieldContainer[str]: ...
    scene: int
    group: int
    zone_id: int
    def __init__(
        self,
        *,
        dSUID: Optional[list[str]] = ...,
        scene: Optional[int] = ...,
        group: Optional[int] = ...,
        zone_id: Optional[int] = ...,
    ) -> None: ...

class vdsm_NotificationUndoScene(_Message):
    @property
    def dSUID(self) -> RepeatedScalarFieldContainer[str]: ...
    scene: int
    group: int
    zone_id: int
    def __init__(
        self,
        *,
        dSUID: Optional[list[str]] = ...,
        scene: Optional[int] = ...,
        group: Optional[int] = ...,
        zone_id: Optional[int] = ...,
    ) -> None: ...

class vdsm_NotificationSetLocalPrio(_Message):
    @property
    def dSUID(self) -> RepeatedScalarFieldContainer[str]: ...
    scene: int
    group: int
    zone_id: int
    def __init__(
        self,
        *,
        dSUID: Optional[list[str]] = ...,
        scene: Optional[int] = ...,
        group: Optional[int] = ...,
        zone_id: Optional[int] = ...,
    ) -> None: ...

class vdsm_NotificationCallMinScene(_Message):
    @property
    def dSUID(self) -> RepeatedScalarFieldContainer[str]: ...
    scene: int
    group: int
    zone_id: int
    def __init__(
        self,
        *,
        dSUID: Optional[list[str]] = ...,
        scene: Optional[int] = ...,
        group: Optional[int] = ...,
        zone_id: Optional[int] = ...,
    ) -> None: ...

class vdsm_NotificationIdentify(_Message):
    @property
    def dSUID(self) -> RepeatedScalarFieldContainer[str]: ...
    group: int
    zone_id: int
    def __init__(
        self,
        *,
        dSUID: Optional[list[str]] = ...,
        group: Optional[int] = ...,
        zone_id: Optional[int] = ...,
    ) -> None: ...

class vdsm_NotificationSetControlValue(_Message):
    @property
    def dSUID(self) -> RepeatedScalarFieldContainer[str]: ...
    name: str
    value: float
    group: int
    zone_id: int
    def __init__(
        self,
        *,
        dSUID: Optional[list[str]] = ...,
        name: Optional[str] = ...,
        value: Optional[float] = ...,
        group: Optional[int] = ...,
        zone_id: Optional[int] = ...,
    ) -> None: ...

class vdsm_NotificationDimChannel(_Message):
    @property
    def dSUID(self) -> RepeatedScalarFieldContainer[str]: ...
    channel: int
    mode: int
    area: int
    group: int
    zone_id: int
    channelId: str
    def __init__(
        self,
        *,
        dSUID: Optional[list[str]] = ...,
        channel: Optional[int] = ...,
        mode: Optional[int] = ...,
        area: Optional[int] = ...,
        group: Optional[int] = ...,
        zone_id: Optional[int] = ...,
        channelId: Optional[str] = ...,
    ) -> None: ...

class vdsm_NotificationSetOutputChannelValue(_Message):
    @property
    def dSUID(self) -> RepeatedScalarFieldContainer[str]: ...
    apply_now: bool
    channel: int
    value: float
    channelId: str
    def __init__(
        self,
        *,
        dSUID: Optional[list[str]] = ...,
        apply_now: Optional[bool] = ...,
        channel: Optional[int] = ...,
        value: Optional[float] = ...,
        channelId: Optional[str] = ...,
    ) -> None: ...

class GenericResponse(_Message):
    code: int
    description: str
    def __init__(self, *, code: Optional[int] = ..., description: Optional[str] = ...) -> None: ...

class Message(_Message):
    type: int
    message_id: int
    @property
    def generic_response(self) -> GenericResponse: ...
    @property
    def vdsm_request_hello(self) -> vdsm_RequestHello: ...
    @property
    def vdc_response_hello(self) -> vdc_ResponseHello: ...
    @property
    def vdsm_request_get_property(self) -> vdsm_RequestGetProperty: ...
    @property
    def vdc_response_get_property(self) -> vdc_ResponseGetProperty: ...
    @property
    def vdsm_request_set_property(self) -> vdsm_RequestSetProperty: ...
    @property
    def vdsm_request_generic_request(self) -> vdsm_RequestGenericRequest: ...
    @property
    def vdsm_send_ping(self) -> vdsm_SendPing: ...
    @property
    def vdc_send_pong(self) -> vdc_SendPong: ...
    @property
    def vdc_send_announce_device(self) -> vdc_SendAnnounceDevice: ...
    @property
    def vdc_send_vanish(self) -> vdc_SendVanish: ...
    @property
    def vdc_send_push_property(self) -> vdc_SendPushProperty: ...
    @property
    def vdsm_send_remove(self) -> vdsm_SendRemove: ...
    @property
    def vdsm_send_bye(self) -> vdsm_SendBye: ...
    @property
    def vdsm_send_call_scene(self) -> vdsm_NotificationCallScene: ...
    @property
    def vdsm_send_save_scene(self) -> vdsm_NotificationSaveScene: ...
    @property
    def vdsm_send_undo_scene(self) -> vdsm_NotificationUndoScene: ...
    @property
    def vdsm_send_set_local_prio(self) -> vdsm_NotificationSetLocalPrio: ...
    @property
    def vdsm_send_call_min_scene(self) -> vdsm_NotificationCallMinScene: ...
    @property
    def vdsm_send_identify(self) -> vdsm_NotificationIdentify: ...
    @property
    def vdsm_send_set_control_value(self) -> vdsm_NotificationSetControlValue: ...
    @property
    def vdsm_send_dim_channel(self) -> vdsm_NotificationDimChannel: ...
    @property
    def vdsm_send_output_channel_value(self) -> vdsm_NotificationSetOutputChannelValue: ...
    @property
    def vdc_send_identify(self) -> vdc_SendIdentify: ...
    @property
    def vdc_send_announce_vdc(self) -> vdc_SendAnnounceVdc: ...
    def __init__(
        self,
        *,
        type: Optional[int] = ...,
        message_id: Optional[int] = ...,
        generic_response: Optional[GenericResponse] = ...,
        vdsm_request_hello: Optional[vdsm_RequestHello] = ...,
        vdc_response_hello: Optional[vdc_ResponseHello] = ...,
        vdsm_request_get_property: Optional[vdsm_RequestGetProperty] = ...,
        vdc_response_get_property: Optional[vdc_ResponseGetProperty] = ...,
        vdsm_request_set_property: Optional[vdsm_RequestSetProperty] = ...,
        vdsm_request_generic_request: Optional[vdsm_RequestGenericRequest] = ...,
        vdsm_send_ping: Optional[vdsm_SendPing] = ...,
        vdc_send_pong: Optional[vdc_SendPong] = ...,
        vdc_send_announce_device: Optional[vdc_SendAnnounceDevice] = ...,
        vdc_send_vanish: Optional[vdc_SendVanish] = ...,
        vdc_send_push_property: Optional[vdc_SendPushProperty] = ...,
        vdsm_send_remove: Optional[vdsm_SendRemove] = ...,
        vdsm_send_bye: Optional[vdsm_SendBye] = ...,
        vdsm_send_call_scene: Optional[vdsm_NotificationCallScene] = ...,
        vdsm_send_save_scene: Optional[vdsm_NotificationSaveScene] = ...,
        vdsm_send_undo_scene: Optional[vdsm_NotificationUndoScene] = ...,
        vdsm_send_set_local_prio: Optional[vdsm_NotificationSetLocalPrio] = ...,
        vdsm_send_call_min_scene: Optional[vdsm_NotificationCallMinScene] = ...,
        vdsm_send_identify: Optional[vdsm_NotificationIdentify] = ...,
        vdsm_send_set_control_value: Optional[vdsm_NotificationSetControlValue] = ...,
        vdsm_send_dim_channel: Optional[vdsm_NotificationDimChannel] = ...,
        vdsm_send_output_channel_value: Optional[vdsm_NotificationSetOutputChannelValue] = ...,
        vdc_send_identify: Optional[vdc_SendIdentify] = ...,
        vdc_send_announce_vdc: Optional[vdc_SendAnnounceVdc] = ...,
    ) -> None: ...
