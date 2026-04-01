"""pyDSvDCAPI - Python library for the DSvDC API."""

__version__ = "0.1.0"

from pyDSvDCAPI.enums import (  # noqa: F401 – re-export for convenience
    ActionMode,
    AirFlowDirection,
    ApartmentScene,
    ApartmentTemperatureMode,
    ApartmentVentilationLevel,
    AudioDeviceScene,
    AudioScene,
    AwningScene,
    BinaryInputType,
    BinaryInputUsage,
    ButtonClickType,
    ButtonElementID,
    ButtonFunction,
    ButtonGroup,
    ButtonMode,
    ButtonType,
    ClimateDeviceScene,
    ColorGroup,
    DeviceScene,
    EntityType,
    ErrorType,
    HeatingSystemCapability,
    HeatingSystemType,
    InputError,
    LightScene,
    MessageType,
    OutputChannelType,
    OutputError,
    OutputFunction,
    OutputHardwareMode,
    OutputMode,
    OutputUsage,
    PowerState,
    ResultCode,
    SceneEffect,
    SceneNumber,
    SceneScope,
    SensorType,
    SensorUsage,
    ShadeScene,
    TemperatureControlScene,
    TemperatureDeviceScene,
    VentilationScene,
    ZoneScene,
    ZoneTemperatureMode,
)

from pyDSvDCAPI.dsuid import (  # noqa: F401
    DSUID_BYTES,
    DsUid,
    DsUidNamespace,
    DsUidType,
)

from pyDSvDCAPI.connection import (  # noqa: F401
    MAX_MESSAGE_LENGTH,
    VdcConnection,
)

from pyDSvDCAPI.persistence import PropertyStore  # noqa: F401

from pyDSvDCAPI.session import (  # noqa: F401
    SUPPORTED_API_VERSION,
    HelloCallback,
    MessageCallback,
    SessionState,
    VdcSession,
)

from pyDSvDCAPI.vdc_host import (  # noqa: F401
    AUTO_SAVE_DELAY,
    AuthenticateCallback,
    DEFAULT_VDC_PORT,
    FirmwareUpgradeCallback,
    IdentifyCallback,
    PairCallback,
    RemoveCallback,
    SetConfigurationCallback,
    VdcHost,
)

from pyDSvDCAPI.vdc import (  # noqa: F401
    ENTITY_TYPE_VDC,
    Vdc,
    VdcCapabilities,
)

from pyDSvDCAPI.vdsd import (  # noqa: F401
    ControlValueCallback,
    ENTITY_TYPE_VDSD,
    Device,
    IdentifyCallback as DeviceIdentifyCallback,
    InvokeActionCallback,
    Vdsd,
)

from pyDSvDCAPI.actions import (  # noqa: F401
    ActionParameter,
    CustomAction,
    DeviceActionDescription,
    DynamicAction,
    StandardAction,
)

from pyDSvDCAPI.binary_input import BinaryInput  # noqa: F401

from pyDSvDCAPI.button_input import (  # noqa: F401
    BUTTON_TYPE_ELEMENTS,
    ButtonInput,
    ClickDetector,
    create_button_group,
    get_required_elements,
)

from pyDSvDCAPI.sensor_input import SensorInput  # noqa: F401

from pyDSvDCAPI.device_event import DeviceEvent  # noqa: F401

from pyDSvDCAPI.device_state import DeviceState  # noqa: F401

from pyDSvDCAPI.device_property import (  # noqa: F401
    PROPERTY_TYPE_ENUMERATION,
    PROPERTY_TYPE_NUMERIC,
    PROPERTY_TYPE_STRING,
    VALID_PROPERTY_TYPES,
    DeviceProperty,
)

from pyDSvDCAPI.output import (  # noqa: F401
    DimChannelCallback,
    FUNCTION_CHANNELS,
    Output,
)

from pyDSvDCAPI.output_channel import (  # noqa: F401
    CHANNEL_SPECS,
    ChannelSpec,
    OutputChannel,
    get_channel_spec,
)

from pyDSvDCAPI.property_handling import (  # noqa: F401
    NO_VALUE,
    build_get_property_response,
    dict_to_elements,
    elements_to_dict,
    expand_setproperty_wildcards,
    match_query,
)

from pyDSvDCAPI.device_template import (  # noqa: F401
    AnnouncementNotReadyError,
    DeviceTemplate,
    TemplateNotConfiguredError,
)
