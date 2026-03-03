from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor
DISCONNECTED: ErrorType
ERR_FORBIDDEN: ResultCode
ERR_INCOMPATIBLE_API: ResultCode
ERR_INSUFFICIENT_STORAGE: ResultCode
ERR_INVALID_VALUE_TYPE: ResultCode
ERR_MESSAGE_UNKNOWN: ResultCode
ERR_MISSING_DATA: ResultCode
ERR_MISSING_SUBMESSAGE: ResultCode
ERR_NOT_AUTHORIZED: ResultCode
ERR_NOT_FOUND: ResultCode
ERR_NOT_IMPLEMENTED: ResultCode
ERR_NO_CONTENT_FOR_ARRAY: ResultCode
ERR_OK: ResultCode
ERR_SERVICE_NOT_AVAILABLE: ResultCode
FAILED: ErrorType
GENERIC_RESPONSE: Type
OVERLOADED: ErrorType
UNIMPLEMENTED: ErrorType
VDC_RESPONSE_GET_PROPERTY: Type
VDC_RESPONSE_HELLO: Type
VDC_SEND_ANNOUNCE_DEVICE: Type
VDC_SEND_ANNOUNCE_VDC: Type
VDC_SEND_IDENTIFY: Type
VDC_SEND_PONG: Type
VDC_SEND_PUSH_NOTIFICATION: Type
VDC_SEND_VANISH: Type
VDSM_NOTIFICATION_CALL_MIN_SCENE: Type
VDSM_NOTIFICATION_CALL_SCENE: Type
VDSM_NOTIFICATION_DIM_CHANNEL: Type
VDSM_NOTIFICATION_IDENTIFY: Type
VDSM_NOTIFICATION_SAVE_SCENE: Type
VDSM_NOTIFICATION_SET_CONTROL_VALUE: Type
VDSM_NOTIFICATION_SET_LOCAL_PRIO: Type
VDSM_NOTIFICATION_SET_OUTPUT_CHANNEL_VALUE: Type
VDSM_NOTIFICATION_UNDO_SCENE: Type
VDSM_REQUEST_GENERIC_REQUEST: Type
VDSM_REQUEST_GET_PROPERTY: Type
VDSM_REQUEST_HELLO: Type
VDSM_REQUEST_SET_PROPERTY: Type
VDSM_SEND_BYE: Type
VDSM_SEND_PING: Type
VDSM_SEND_REMOVE: Type

class GenericResponse(_message.Message):
    __slots__ = ["code", "description", "errorType", "userMessageToBeTranslated"]
    CODE_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    ERRORTYPE_FIELD_NUMBER: _ClassVar[int]
    USERMESSAGETOBETRANSLATED_FIELD_NUMBER: _ClassVar[int]
    code: ResultCode
    description: str
    errorType: ErrorType
    userMessageToBeTranslated: str
    def __init__(self, code: _Optional[_Union[ResultCode, str]] = ..., description: _Optional[str] = ..., errorType: _Optional[_Union[ErrorType, str]] = ..., userMessageToBeTranslated: _Optional[str] = ...) -> None: ...

class Message(_message.Message):
    __slots__ = ["generic_response", "message_id", "type", "vdc_response_get_property", "vdc_response_hello", "vdc_send_announce_device", "vdc_send_announce_vdc", "vdc_send_identify", "vdc_send_pong", "vdc_send_push_notification", "vdc_send_vanish", "vdsm_request_generic_request", "vdsm_request_get_property", "vdsm_request_hello", "vdsm_request_set_property", "vdsm_send_bye", "vdsm_send_call_min_scene", "vdsm_send_call_scene", "vdsm_send_dim_channel", "vdsm_send_identify", "vdsm_send_output_channel_value", "vdsm_send_ping", "vdsm_send_remove", "vdsm_send_save_scene", "vdsm_send_set_control_value", "vdsm_send_set_local_prio", "vdsm_send_undo_scene"]
    GENERIC_RESPONSE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_ID_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    VDC_RESPONSE_GET_PROPERTY_FIELD_NUMBER: _ClassVar[int]
    VDC_RESPONSE_HELLO_FIELD_NUMBER: _ClassVar[int]
    VDC_SEND_ANNOUNCE_DEVICE_FIELD_NUMBER: _ClassVar[int]
    VDC_SEND_ANNOUNCE_VDC_FIELD_NUMBER: _ClassVar[int]
    VDC_SEND_IDENTIFY_FIELD_NUMBER: _ClassVar[int]
    VDC_SEND_PONG_FIELD_NUMBER: _ClassVar[int]
    VDC_SEND_PUSH_NOTIFICATION_FIELD_NUMBER: _ClassVar[int]
    VDC_SEND_VANISH_FIELD_NUMBER: _ClassVar[int]
    VDSM_REQUEST_GENERIC_REQUEST_FIELD_NUMBER: _ClassVar[int]
    VDSM_REQUEST_GET_PROPERTY_FIELD_NUMBER: _ClassVar[int]
    VDSM_REQUEST_HELLO_FIELD_NUMBER: _ClassVar[int]
    VDSM_REQUEST_SET_PROPERTY_FIELD_NUMBER: _ClassVar[int]
    VDSM_SEND_BYE_FIELD_NUMBER: _ClassVar[int]
    VDSM_SEND_CALL_MIN_SCENE_FIELD_NUMBER: _ClassVar[int]
    VDSM_SEND_CALL_SCENE_FIELD_NUMBER: _ClassVar[int]
    VDSM_SEND_DIM_CHANNEL_FIELD_NUMBER: _ClassVar[int]
    VDSM_SEND_IDENTIFY_FIELD_NUMBER: _ClassVar[int]
    VDSM_SEND_OUTPUT_CHANNEL_VALUE_FIELD_NUMBER: _ClassVar[int]
    VDSM_SEND_PING_FIELD_NUMBER: _ClassVar[int]
    VDSM_SEND_REMOVE_FIELD_NUMBER: _ClassVar[int]
    VDSM_SEND_SAVE_SCENE_FIELD_NUMBER: _ClassVar[int]
    VDSM_SEND_SET_CONTROL_VALUE_FIELD_NUMBER: _ClassVar[int]
    VDSM_SEND_SET_LOCAL_PRIO_FIELD_NUMBER: _ClassVar[int]
    VDSM_SEND_UNDO_SCENE_FIELD_NUMBER: _ClassVar[int]
    generic_response: GenericResponse
    message_id: int
    type: Type
    vdc_response_get_property: vdc_ResponseGetProperty
    vdc_response_hello: vdc_ResponseHello
    vdc_send_announce_device: vdc_SendAnnounceDevice
    vdc_send_announce_vdc: vdc_SendAnnounceVdc
    vdc_send_identify: vdc_SendIdentify
    vdc_send_pong: vdc_SendPong
    vdc_send_push_notification: vdc_SendPushNotification
    vdc_send_vanish: vdc_SendVanish
    vdsm_request_generic_request: vdsm_RequestGenericRequest
    vdsm_request_get_property: vdsm_RequestGetProperty
    vdsm_request_hello: vdsm_RequestHello
    vdsm_request_set_property: vdsm_RequestSetProperty
    vdsm_send_bye: vdsm_SendBye
    vdsm_send_call_min_scene: vdsm_NotificationCallMinScene
    vdsm_send_call_scene: vdsm_NotificationCallScene
    vdsm_send_dim_channel: vdsm_NotificationDimChannel
    vdsm_send_identify: vdsm_NotificationIdentify
    vdsm_send_output_channel_value: vdsm_NotificationSetOutputChannelValue
    vdsm_send_ping: vdsm_SendPing
    vdsm_send_remove: vdsm_SendRemove
    vdsm_send_save_scene: vdsm_NotificationSaveScene
    vdsm_send_set_control_value: vdsm_NotificationSetControlValue
    vdsm_send_set_local_prio: vdsm_NotificationSetLocalPrio
    vdsm_send_undo_scene: vdsm_NotificationUndoScene
    def __init__(self, type: _Optional[_Union[Type, str]] = ..., message_id: _Optional[int] = ..., generic_response: _Optional[_Union[GenericResponse, _Mapping]] = ..., vdsm_request_hello: _Optional[_Union[vdsm_RequestHello, _Mapping]] = ..., vdc_response_hello: _Optional[_Union[vdc_ResponseHello, _Mapping]] = ..., vdsm_request_get_property: _Optional[_Union[vdsm_RequestGetProperty, _Mapping]] = ..., vdc_response_get_property: _Optional[_Union[vdc_ResponseGetProperty, _Mapping]] = ..., vdsm_request_set_property: _Optional[_Union[vdsm_RequestSetProperty, _Mapping]] = ..., vdsm_request_generic_request: _Optional[_Union[vdsm_RequestGenericRequest, _Mapping]] = ..., vdsm_send_ping: _Optional[_Union[vdsm_SendPing, _Mapping]] = ..., vdc_send_pong: _Optional[_Union[vdc_SendPong, _Mapping]] = ..., vdc_send_announce_device: _Optional[_Union[vdc_SendAnnounceDevice, _Mapping]] = ..., vdc_send_vanish: _Optional[_Union[vdc_SendVanish, _Mapping]] = ..., vdc_send_push_notification: _Optional[_Union[vdc_SendPushNotification, _Mapping]] = ..., vdsm_send_remove: _Optional[_Union[vdsm_SendRemove, _Mapping]] = ..., vdsm_send_bye: _Optional[_Union[vdsm_SendBye, _Mapping]] = ..., vdsm_send_call_scene: _Optional[_Union[vdsm_NotificationCallScene, _Mapping]] = ..., vdsm_send_save_scene: _Optional[_Union[vdsm_NotificationSaveScene, _Mapping]] = ..., vdsm_send_undo_scene: _Optional[_Union[vdsm_NotificationUndoScene, _Mapping]] = ..., vdsm_send_set_local_prio: _Optional[_Union[vdsm_NotificationSetLocalPrio, _Mapping]] = ..., vdsm_send_call_min_scene: _Optional[_Union[vdsm_NotificationCallMinScene, _Mapping]] = ..., vdsm_send_identify: _Optional[_Union[vdsm_NotificationIdentify, _Mapping]] = ..., vdsm_send_set_control_value: _Optional[_Union[vdsm_NotificationSetControlValue, _Mapping]] = ..., vdsm_send_dim_channel: _Optional[_Union[vdsm_NotificationDimChannel, _Mapping]] = ..., vdsm_send_output_channel_value: _Optional[_Union[vdsm_NotificationSetOutputChannelValue, _Mapping]] = ..., vdc_send_identify: _Optional[_Union[vdc_SendIdentify, _Mapping]] = ..., vdc_send_announce_vdc: _Optional[_Union[vdc_SendAnnounceVdc, _Mapping]] = ...) -> None: ...

class PropertyElement(_message.Message):
    __slots__ = ["elements", "name", "value"]
    ELEMENTS_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    elements: _containers.RepeatedCompositeFieldContainer[PropertyElement]
    name: str
    value: PropertyValue
    def __init__(self, name: _Optional[str] = ..., value: _Optional[_Union[PropertyValue, _Mapping]] = ..., elements: _Optional[_Iterable[_Union[PropertyElement, _Mapping]]] = ...) -> None: ...

class PropertyValue(_message.Message):
    __slots__ = ["v_bool", "v_bytes", "v_double", "v_int64", "v_string", "v_uint64"]
    V_BOOL_FIELD_NUMBER: _ClassVar[int]
    V_BYTES_FIELD_NUMBER: _ClassVar[int]
    V_DOUBLE_FIELD_NUMBER: _ClassVar[int]
    V_INT64_FIELD_NUMBER: _ClassVar[int]
    V_STRING_FIELD_NUMBER: _ClassVar[int]
    V_UINT64_FIELD_NUMBER: _ClassVar[int]
    v_bool: bool
    v_bytes: bytes
    v_double: float
    v_int64: int
    v_string: str
    v_uint64: int
    def __init__(self, v_bool: bool = ..., v_uint64: _Optional[int] = ..., v_int64: _Optional[int] = ..., v_double: _Optional[float] = ..., v_string: _Optional[str] = ..., v_bytes: _Optional[bytes] = ...) -> None: ...

class vdc_ResponseGetProperty(_message.Message):
    __slots__ = ["properties"]
    PROPERTIES_FIELD_NUMBER: _ClassVar[int]
    properties: _containers.RepeatedCompositeFieldContainer[PropertyElement]
    def __init__(self, properties: _Optional[_Iterable[_Union[PropertyElement, _Mapping]]] = ...) -> None: ...

class vdc_ResponseHello(_message.Message):
    __slots__ = ["dSUID"]
    DSUID_FIELD_NUMBER: _ClassVar[int]
    dSUID: str
    def __init__(self, dSUID: _Optional[str] = ...) -> None: ...

class vdc_SendAnnounceDevice(_message.Message):
    __slots__ = ["dSUID", "vdc_dSUID"]
    DSUID_FIELD_NUMBER: _ClassVar[int]
    VDC_DSUID_FIELD_NUMBER: _ClassVar[int]
    dSUID: str
    vdc_dSUID: str
    def __init__(self, dSUID: _Optional[str] = ..., vdc_dSUID: _Optional[str] = ...) -> None: ...

class vdc_SendAnnounceVdc(_message.Message):
    __slots__ = ["dSUID"]
    DSUID_FIELD_NUMBER: _ClassVar[int]
    dSUID: str
    def __init__(self, dSUID: _Optional[str] = ...) -> None: ...

class vdc_SendIdentify(_message.Message):
    __slots__ = ["dSUID"]
    DSUID_FIELD_NUMBER: _ClassVar[int]
    dSUID: str
    def __init__(self, dSUID: _Optional[str] = ...) -> None: ...

class vdc_SendPong(_message.Message):
    __slots__ = ["dSUID"]
    DSUID_FIELD_NUMBER: _ClassVar[int]
    dSUID: str
    def __init__(self, dSUID: _Optional[str] = ...) -> None: ...

class vdc_SendPushNotification(_message.Message):
    __slots__ = ["changedproperties", "dSUID", "deviceevents"]
    CHANGEDPROPERTIES_FIELD_NUMBER: _ClassVar[int]
    DEVICEEVENTS_FIELD_NUMBER: _ClassVar[int]
    DSUID_FIELD_NUMBER: _ClassVar[int]
    changedproperties: _containers.RepeatedCompositeFieldContainer[PropertyElement]
    dSUID: str
    deviceevents: _containers.RepeatedCompositeFieldContainer[PropertyElement]
    def __init__(self, dSUID: _Optional[str] = ..., changedproperties: _Optional[_Iterable[_Union[PropertyElement, _Mapping]]] = ..., deviceevents: _Optional[_Iterable[_Union[PropertyElement, _Mapping]]] = ...) -> None: ...

class vdc_SendVanish(_message.Message):
    __slots__ = ["dSUID"]
    DSUID_FIELD_NUMBER: _ClassVar[int]
    dSUID: str
    def __init__(self, dSUID: _Optional[str] = ...) -> None: ...

class vdsm_NotificationCallMinScene(_message.Message):
    __slots__ = ["dSUID", "group", "scene", "zone_id"]
    DSUID_FIELD_NUMBER: _ClassVar[int]
    GROUP_FIELD_NUMBER: _ClassVar[int]
    SCENE_FIELD_NUMBER: _ClassVar[int]
    ZONE_ID_FIELD_NUMBER: _ClassVar[int]
    dSUID: _containers.RepeatedScalarFieldContainer[str]
    group: int
    scene: int
    zone_id: int
    def __init__(self, dSUID: _Optional[_Iterable[str]] = ..., scene: _Optional[int] = ..., group: _Optional[int] = ..., zone_id: _Optional[int] = ...) -> None: ...

class vdsm_NotificationCallScene(_message.Message):
    __slots__ = ["dSUID", "force", "group", "scene", "zone_id"]
    DSUID_FIELD_NUMBER: _ClassVar[int]
    FORCE_FIELD_NUMBER: _ClassVar[int]
    GROUP_FIELD_NUMBER: _ClassVar[int]
    SCENE_FIELD_NUMBER: _ClassVar[int]
    ZONE_ID_FIELD_NUMBER: _ClassVar[int]
    dSUID: _containers.RepeatedScalarFieldContainer[str]
    force: bool
    group: int
    scene: int
    zone_id: int
    def __init__(self, dSUID: _Optional[_Iterable[str]] = ..., scene: _Optional[int] = ..., force: bool = ..., group: _Optional[int] = ..., zone_id: _Optional[int] = ...) -> None: ...

class vdsm_NotificationDimChannel(_message.Message):
    __slots__ = ["area", "channel", "channelId", "dSUID", "group", "mode", "zone_id"]
    AREA_FIELD_NUMBER: _ClassVar[int]
    CHANNELID_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_FIELD_NUMBER: _ClassVar[int]
    DSUID_FIELD_NUMBER: _ClassVar[int]
    GROUP_FIELD_NUMBER: _ClassVar[int]
    MODE_FIELD_NUMBER: _ClassVar[int]
    ZONE_ID_FIELD_NUMBER: _ClassVar[int]
    area: int
    channel: int
    channelId: str
    dSUID: _containers.RepeatedScalarFieldContainer[str]
    group: int
    mode: int
    zone_id: int
    def __init__(self, dSUID: _Optional[_Iterable[str]] = ..., channel: _Optional[int] = ..., mode: _Optional[int] = ..., area: _Optional[int] = ..., group: _Optional[int] = ..., zone_id: _Optional[int] = ..., channelId: _Optional[str] = ...) -> None: ...

class vdsm_NotificationIdentify(_message.Message):
    __slots__ = ["dSUID", "group", "zone_id"]
    DSUID_FIELD_NUMBER: _ClassVar[int]
    GROUP_FIELD_NUMBER: _ClassVar[int]
    ZONE_ID_FIELD_NUMBER: _ClassVar[int]
    dSUID: _containers.RepeatedScalarFieldContainer[str]
    group: int
    zone_id: int
    def __init__(self, dSUID: _Optional[_Iterable[str]] = ..., group: _Optional[int] = ..., zone_id: _Optional[int] = ...) -> None: ...

class vdsm_NotificationSaveScene(_message.Message):
    __slots__ = ["dSUID", "group", "scene", "zone_id"]
    DSUID_FIELD_NUMBER: _ClassVar[int]
    GROUP_FIELD_NUMBER: _ClassVar[int]
    SCENE_FIELD_NUMBER: _ClassVar[int]
    ZONE_ID_FIELD_NUMBER: _ClassVar[int]
    dSUID: _containers.RepeatedScalarFieldContainer[str]
    group: int
    scene: int
    zone_id: int
    def __init__(self, dSUID: _Optional[_Iterable[str]] = ..., scene: _Optional[int] = ..., group: _Optional[int] = ..., zone_id: _Optional[int] = ...) -> None: ...

class vdsm_NotificationSetControlValue(_message.Message):
    __slots__ = ["dSUID", "group", "name", "value", "zone_id"]
    DSUID_FIELD_NUMBER: _ClassVar[int]
    GROUP_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    ZONE_ID_FIELD_NUMBER: _ClassVar[int]
    dSUID: _containers.RepeatedScalarFieldContainer[str]
    group: int
    name: str
    value: float
    zone_id: int
    def __init__(self, dSUID: _Optional[_Iterable[str]] = ..., name: _Optional[str] = ..., value: _Optional[float] = ..., group: _Optional[int] = ..., zone_id: _Optional[int] = ...) -> None: ...

class vdsm_NotificationSetLocalPrio(_message.Message):
    __slots__ = ["dSUID", "group", "scene", "zone_id"]
    DSUID_FIELD_NUMBER: _ClassVar[int]
    GROUP_FIELD_NUMBER: _ClassVar[int]
    SCENE_FIELD_NUMBER: _ClassVar[int]
    ZONE_ID_FIELD_NUMBER: _ClassVar[int]
    dSUID: _containers.RepeatedScalarFieldContainer[str]
    group: int
    scene: int
    zone_id: int
    def __init__(self, dSUID: _Optional[_Iterable[str]] = ..., scene: _Optional[int] = ..., group: _Optional[int] = ..., zone_id: _Optional[int] = ...) -> None: ...

class vdsm_NotificationSetOutputChannelValue(_message.Message):
    __slots__ = ["apply_now", "channel", "channelId", "dSUID", "value"]
    APPLY_NOW_FIELD_NUMBER: _ClassVar[int]
    CHANNELID_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_FIELD_NUMBER: _ClassVar[int]
    DSUID_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    apply_now: bool
    channel: int
    channelId: str
    dSUID: _containers.RepeatedScalarFieldContainer[str]
    value: float
    def __init__(self, dSUID: _Optional[_Iterable[str]] = ..., apply_now: bool = ..., channel: _Optional[int] = ..., value: _Optional[float] = ..., channelId: _Optional[str] = ...) -> None: ...

class vdsm_NotificationUndoScene(_message.Message):
    __slots__ = ["dSUID", "group", "scene", "zone_id"]
    DSUID_FIELD_NUMBER: _ClassVar[int]
    GROUP_FIELD_NUMBER: _ClassVar[int]
    SCENE_FIELD_NUMBER: _ClassVar[int]
    ZONE_ID_FIELD_NUMBER: _ClassVar[int]
    dSUID: _containers.RepeatedScalarFieldContainer[str]
    group: int
    scene: int
    zone_id: int
    def __init__(self, dSUID: _Optional[_Iterable[str]] = ..., scene: _Optional[int] = ..., group: _Optional[int] = ..., zone_id: _Optional[int] = ...) -> None: ...

class vdsm_RequestGenericRequest(_message.Message):
    __slots__ = ["dSUID", "methodname", "params"]
    DSUID_FIELD_NUMBER: _ClassVar[int]
    METHODNAME_FIELD_NUMBER: _ClassVar[int]
    PARAMS_FIELD_NUMBER: _ClassVar[int]
    dSUID: str
    methodname: str
    params: _containers.RepeatedCompositeFieldContainer[PropertyElement]
    def __init__(self, dSUID: _Optional[str] = ..., methodname: _Optional[str] = ..., params: _Optional[_Iterable[_Union[PropertyElement, _Mapping]]] = ...) -> None: ...

class vdsm_RequestGetProperty(_message.Message):
    __slots__ = ["dSUID", "query"]
    DSUID_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    dSUID: str
    query: _containers.RepeatedCompositeFieldContainer[PropertyElement]
    def __init__(self, dSUID: _Optional[str] = ..., query: _Optional[_Iterable[_Union[PropertyElement, _Mapping]]] = ...) -> None: ...

class vdsm_RequestHello(_message.Message):
    __slots__ = ["api_version", "dSUID"]
    API_VERSION_FIELD_NUMBER: _ClassVar[int]
    DSUID_FIELD_NUMBER: _ClassVar[int]
    api_version: int
    dSUID: str
    def __init__(self, dSUID: _Optional[str] = ..., api_version: _Optional[int] = ...) -> None: ...

class vdsm_RequestSetProperty(_message.Message):
    __slots__ = ["dSUID", "properties"]
    DSUID_FIELD_NUMBER: _ClassVar[int]
    PROPERTIES_FIELD_NUMBER: _ClassVar[int]
    dSUID: str
    properties: _containers.RepeatedCompositeFieldContainer[PropertyElement]
    def __init__(self, dSUID: _Optional[str] = ..., properties: _Optional[_Iterable[_Union[PropertyElement, _Mapping]]] = ...) -> None: ...

class vdsm_SendBye(_message.Message):
    __slots__ = ["dSUID"]
    DSUID_FIELD_NUMBER: _ClassVar[int]
    dSUID: str
    def __init__(self, dSUID: _Optional[str] = ...) -> None: ...

class vdsm_SendPing(_message.Message):
    __slots__ = ["dSUID"]
    DSUID_FIELD_NUMBER: _ClassVar[int]
    dSUID: str
    def __init__(self, dSUID: _Optional[str] = ...) -> None: ...

class vdsm_SendRemove(_message.Message):
    __slots__ = ["dSUID"]
    DSUID_FIELD_NUMBER: _ClassVar[int]
    dSUID: str
    def __init__(self, dSUID: _Optional[str] = ...) -> None: ...

class Type(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class ResultCode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []

class ErrorType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
