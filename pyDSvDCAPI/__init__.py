"""pyDSvDCAPI - Python library for the DSvDC API."""

__version__ = "0.1.0"

from pyDSvDCAPI.enums import (  # noqa: F401 – re-export for convenience
    AirFlowDirection,
    BinaryInputType,
    BinaryInputUsage,
    ButtonClickType,
    ButtonElementID,
    ButtonFunction,
    ButtonGroup,
    ButtonMode,
    ButtonType,
    ColorGroup,
    EntityType,
    ErrorType,
    HeatingSystemCapability,
    HeatingSystemType,
    InputError,
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
    SensorType,
    SensorUsage,
    TemperatureControlScene,
    TemperatureDeviceScene,
    VentilationScene,
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
    MessageCallback,
    SessionState,
    VdcSession,
)

from pyDSvDCAPI.vdc_host import (  # noqa: F401
    AUTO_SAVE_DELAY,
    DEFAULT_VDC_PORT,
    VdcHost,
)

from pyDSvDCAPI.vdc import (  # noqa: F401
    ENTITY_TYPE_VDC,
    Vdc,
    VdcCapabilities,
)

from pyDSvDCAPI.vdsd import (  # noqa: F401
    ENTITY_TYPE_VDSD,
    Device,
    Vdsd,
)

from pyDSvDCAPI.binary_input import BinaryInput  # noqa: F401

from pyDSvDCAPI.sensor_input import SensorInput  # noqa: F401

from pyDSvDCAPI.property_handling import (  # noqa: F401
    build_get_property_response,
    dict_to_elements,
    elements_to_dict,
    match_query,
)
