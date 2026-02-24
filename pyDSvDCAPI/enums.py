"""digitalSTROM vDC API enumerations.

This module contains all enum definitions required by the digitalSTROM
vDC API protocol, derived from the official documentation:

- ds-basics.pdf (v1.6, May 2020)
- vDC API specification
- vDC API properties specification
- genericVDC.proto
"""

from enum import IntEnum, unique


# ---------------------------------------------------------------------------
#  Protocol-level enums (from genericVDC.proto)
# ---------------------------------------------------------------------------


@unique
class MessageType(IntEnum):
    """Protobuf message type identifiers (``Type`` enum in genericVDC.proto)."""

    GENERIC_RESPONSE = 1

    VDSM_REQUEST_HELLO = 2
    VDC_RESPONSE_HELLO = 3

    VDSM_REQUEST_GET_PROPERTY = 4
    VDC_RESPONSE_GET_PROPERTY = 5

    VDSM_REQUEST_SET_PROPERTY = 6
    # VDC_RESPONSE_SET_PROPERTY uses GENERIC_RESPONSE (field 7 in proto)

    VDSM_SEND_PING = 8
    VDC_SEND_PONG = 9

    VDC_SEND_ANNOUNCE_DEVICE = 10
    VDC_SEND_VANISH = 11
    VDC_SEND_PUSH_PROPERTY = 12

    VDSM_SEND_REMOVE = 13
    VDSM_SEND_BYE = 14

    VDSM_NOTIFICATION_CALL_SCENE = 15
    VDSM_NOTIFICATION_SAVE_SCENE = 16
    VDSM_NOTIFICATION_UNDO_SCENE = 17
    VDSM_NOTIFICATION_SET_LOCAL_PRIO = 18
    VDSM_NOTIFICATION_CALL_MIN_SCENE = 19
    VDSM_NOTIFICATION_IDENTIFY = 20
    VDSM_NOTIFICATION_SET_CONTROL_VALUE = 21

    VDC_SEND_IDENTIFY = 22
    VDC_SEND_ANNOUNCE_VDC = 23

    VDSM_NOTIFICATION_DIM_CHANNEL = 24
    VDSM_NOTIFICATION_SET_OUTPUT_CHANNEL_VALUE = 25

    VDSM_REQUEST_GENERIC_REQUEST = 26


@unique
class ResultCode(IntEnum):
    """Result codes returned in ``GenericResponse`` messages."""

    ERR_OK = 0
    ERR_MESSAGE_UNKNOWN = 1
    ERR_INCOMPATIBLE_API = 2
    ERR_SERVICE_NOT_AVAILABLE = 3
    ERR_INSUFFICIENT_STORAGE = 4
    ERR_FORBIDDEN = 5
    ERR_NOT_IMPLEMENTED = 6
    ERR_NO_CONTENT_FOR_ARRAY = 7
    ERR_INVALID_VALUE_TYPE = 8
    ERR_MISSING_SUBMESSAGE = 9
    ERR_MISSING_DATA = 10
    ERR_NOT_FOUND = 11
    ERR_NOT_AUTHORIZED = 12


@unique
class ErrorType(IntEnum):
    """Error category sent alongside ``GenericResponse``."""

    FAILED = 0
    OVERLOADED = 1
    DISCONNECTED = 2
    UNIMPLEMENTED = 3


# ---------------------------------------------------------------------------
#  Addressable entity type
# ---------------------------------------------------------------------------


@unique
class EntityType(IntEnum):
    """Type of addressable entity in the vDC host."""

    VDSD = 0
    VDC = 1
    VDC_HOST = 2
    VDSM = 3


# ---------------------------------------------------------------------------
#  Application groups / colours  (ds-basics Table 2)
# ---------------------------------------------------------------------------


@unique
class ColorGroup(IntEnum):
    """digitalSTROM application groups (colour groups).

    Each group has an associated colour and a primary output channel type.
    """

    YELLOW = 1       # Lights
    GREY = 2         # Blinds / Shades
    BLUE_HEATING = 3          # Heating
    CYAN = 4         # Audio
    MAGENTA = 5      # Video
    RED = 6          # Security (not directly group-addressable)
    GREEN = 7        # Access  (not directly group-addressable)
    BLACK = 8        # Joker / Configurable
    BLUE_COOLING = 9          # Cooling
    BLUE_VENTILATION = 10     # Ventilation
    BLUE_WINDOW = 11          # Window
    BLUE_RECIRCULATION = 12   # Recirculation / Fan coil units
    BLUE_TEMPERATURE_CONTROL = 48  # Single room temperature control
    BLUE_APARTMENT_VENTILATION = 64  # Apartment ventilation system
    WHITE = 255      # Single device (no fixed group ID in spec)


# ---------------------------------------------------------------------------
#  Scene numbers  (ds-basics Appendix B)
# ---------------------------------------------------------------------------


@unique
class SceneNumber(IntEnum):
    """All defined digitalSTROM scene command indices (0 – 127).

    Scenes 0–63 are group-related; scenes 64–127 are group-independent.
    """

    # --- Presets 0–4 ---
    PRESET_0 = 0           # Off
    PRESET_1 = 5           # On
    PRESET_2 = 17
    PRESET_3 = 18
    PRESET_4 = 19

    # --- Area 1 ---
    AREA_1_OFF = 1
    AREA_1_ON = 6
    AREA_1_DEC = 42
    AREA_1_INC = 43
    AREA_1_STOP = 52

    # --- Area 2 ---
    AREA_2_OFF = 2
    AREA_2_ON = 7
    AREA_2_DEC = 44
    AREA_2_INC = 45
    AREA_2_STOP = 53

    # --- Area 3 ---
    AREA_3_OFF = 3
    AREA_3_ON = 8
    AREA_3_DEC = 46
    AREA_3_INC = 47
    AREA_3_STOP = 54

    # --- Area 4 ---
    AREA_4_OFF = 4
    AREA_4_ON = 9
    AREA_4_DEC = 48
    AREA_4_INC = 49
    AREA_4_STOP = 55

    # --- Stepping ---
    AREA_STEPPING_CONTINUE = 10
    DECREMENT = 11
    INCREMENT = 12

    # --- Special ---
    MINIMUM = 13
    MAXIMUM = 14
    STOP = 15

    # --- Presets 10–14 ---
    PRESET_10 = 32
    PRESET_11 = 33
    PRESET_12 = 20
    PRESET_13 = 21
    PRESET_14 = 22

    # --- Presets 20–24 ---
    PRESET_20 = 34
    PRESET_21 = 35
    PRESET_22 = 23
    PRESET_23 = 24
    PRESET_24 = 25

    # --- Presets 30–34 ---
    PRESET_30 = 36
    PRESET_31 = 37
    PRESET_32 = 26
    PRESET_33 = 27
    PRESET_34 = 28

    # --- Presets 40–44 ---
    PRESET_40 = 38
    PRESET_41 = 39
    PRESET_42 = 29
    PRESET_43 = 30
    PRESET_44 = 31

    # --- Device / local ---
    AUTO_OFF = 40
    IMPULSE = 41
    DEVICE_OFF = 50
    DEVICE_ON = 51
    SUN_PROTECTION = 56

    # --- Group-independent scenes (64–127) ---
    AUTO_STANDBY = 64
    PANIC = 65
    STANDBY = 67
    DEEP_OFF = 68
    SLEEPING = 69
    WAKEUP = 70
    PRESENT = 71
    ABSENT = 72
    DOOR_BELL = 73
    ALARM_1 = 74
    ZONE_ACTIVE = 75
    FIRE = 76
    ALARM_2 = 83
    ALARM_3 = 84
    ALARM_4 = 85
    WIND = 86
    NO_WIND = 87
    RAIN = 88
    NO_RAIN = 89
    HAIL = 90
    NO_HAIL = 91
    POLLUTION = 92
    BURGLARY = 93


# ---------------------------------------------------------------------------
#  Output channel types  (ds-basics Table 6 / vDC API properties §4.9.4)
# ---------------------------------------------------------------------------


@unique
class OutputChannelType(IntEnum):
    """Standard output channel type identifiers.

    IDs 0–191 are reserved for standard types.
    IDs 192–239 are available for device-specific (proprietary) channels.
    """

    DEFAULT = 0
    BRIGHTNESS = 1
    HUE = 2
    SATURATION = 3
    COLOR_TEMPERATURE = 4
    CIE_X = 5
    CIE_Y = 6

    SHADE_POSITION_OUTSIDE = 11
    SHADE_POSITION_INDOOR = 12
    SHADE_OPENING_ANGLE_OUTSIDE = 13
    SHADE_OPENING_ANGLE_INDOOR = 14
    TRANSPARENCY = 15

    HEATING_POWER = 21
    HEATING_VALVE = 22
    COOLING_CAPACITY = 23
    COOLING_VALVE = 24
    AIR_FLOW_INTENSITY = 25
    AIR_FLOW_DIRECTION = 26
    AIR_FLAP_POSITION = 27
    AIR_LOUVER_POSITION = 28
    AIR_LOUVER_AUTO = 29
    AIR_FLOW_AUTO = 30

    AUDIO_VOLUME = 41
    AUDIO_BASS = 42
    AUDIO_TREBLE = 43
    AUDIO_BALANCE = 44

    WATER_TEMPERATURE = 51
    WATER_FLOW = 52
    POWER_STATE = 53
    WIND_SPEED_RATE = 54
    POWER_LEVEL = 55


# ---------------------------------------------------------------------------
#  Output function / mode  (vDC API properties §4.8)
# ---------------------------------------------------------------------------


@unique
class OutputFunction(IntEnum):
    """Describes the functional type of a device's output."""

    ON_OFF = 0
    DIMMER = 1
    POSITIONAL = 2
    DIMMER_COLOR_TEMP = 3
    FULL_COLOR_DIMMER = 4
    BIPOLAR = 5
    INTERNALLY_CONTROLLED = 6


@unique
class OutputMode(IntEnum):
    """Output operating mode."""

    DISABLED = 0
    BINARY = 1
    GRADUAL = 2
    DEFAULT = 127


# ---------------------------------------------------------------------------
#  Output usage  (vDC API properties §4.8.1)
# ---------------------------------------------------------------------------


@unique
class OutputUsage(IntEnum):
    """Describes the usage context of an output."""

    UNDEFINED = 0
    ROOM = 1
    OUTDOORS = 2
    USER = 3


# ---------------------------------------------------------------------------
#  Sensor types  (ds-basics Table 23 / vDC API properties §4.4.1)
# ---------------------------------------------------------------------------


@unique
class SensorType(IntEnum):
    """Physical sensor type identifiers (vDC API numbering)."""

    NONE = 0
    TEMPERATURE = 1
    HUMIDITY = 2
    ILLUMINATION = 3
    SUPPLY_VOLTAGE = 4
    CO_CONCENTRATION = 5
    RADON_ACTIVITY = 6
    GAS_TYPE = 7
    PARTICLES_PM10 = 8
    PARTICLES_PM2_5 = 9
    PARTICLES_PM1 = 10
    ROOM_OPERATING_PANEL = 11
    FAN_SPEED = 12
    WIND_SPEED = 13
    ACTIVE_POWER = 14
    ELECTRIC_CURRENT = 15
    ENERGY_METER = 16
    APPARENT_POWER = 17
    AIR_PRESSURE = 18
    WIND_DIRECTION = 19
    SOUND_PRESSURE_LEVEL = 20
    PRECIPITATION = 21
    CO2_CONCENTRATION = 22
    WIND_GUST_SPEED = 23
    WIND_GUST_DIRECTION = 24
    GENERATED_ACTIVE_POWER = 25
    GENERATED_ENERGY = 26
    WATER_QUANTITY = 27
    WATER_FLOW_RATE = 28


@unique
class SensorUsage(IntEnum):
    """Usage context of a sensor."""

    UNDEFINED = 0
    ROOM = 1
    OUTDOOR = 2
    USER_INTERACTION = 3
    DEVICE_LEVEL = 4
    DEVICE_LAST_RUN = 5
    DEVICE_AVERAGE = 6


# ---------------------------------------------------------------------------
#  Binary input types  (ds-basics Table 20 / vDC API properties §4.3.2)
# ---------------------------------------------------------------------------


@unique
class BinaryInputType(IntEnum):
    """Binary input sensor function / type identifiers."""

    GENERIC = 0
    PRESENCE = 1
    BRIGHTNESS = 2
    PRESENCE_IN_DARKNESS = 3
    TWILIGHT = 4
    MOTION = 5
    MOTION_IN_DARKNESS = 6
    SMOKE = 7
    WIND = 8
    RAIN = 9
    SUN_RADIATION = 10
    THERMOSTAT = 11
    BATTERY_LOW = 12
    WINDOW_OPEN = 13
    DOOR_OPEN = 14
    WINDOW_TILTED = 15
    GARAGE_DOOR_OPEN = 16
    SUN_PROTECTION = 17
    FROST = 18
    HEATING_SYSTEM_ENABLED = 19
    HEATING_CHANGE_OVER = 20
    INITIALIZATION = 21
    MALFUNCTION = 22
    SERVICE = 23


@unique
class BinaryInputUsage(IntEnum):
    """Usage context of a binary input."""

    UNDEFINED = 0
    ROOM_CLIMATE = 1
    OUTDOOR_CLIMATE = 2
    CLIMATE_SETTING = 3


# ---------------------------------------------------------------------------
#  Button input enums  (ds-basics §10 / vDC API properties §4.2)
# ---------------------------------------------------------------------------


@unique
class ButtonClickType(IntEnum):
    """Click event types generated by pushbutton inputs."""

    TIP_1X = 0
    TIP_2X = 1
    TIP_3X = 2
    TIP_4X = 3
    HOLD_START = 4
    HOLD_REPEAT = 5
    HOLD_END = 6
    CLICK_1X = 7
    CLICK_2X = 8
    CLICK_3X = 9
    SHORT_LONG = 10
    LOCAL_OFF = 11
    LOCAL_ON = 12
    SHORT_SHORT_LONG = 13
    LOCAL_STOP = 14
    LOCAL_DIM = 15
    IDLE = 255


@unique
class ButtonType(IntEnum):
    """Physical button type identifiers."""

    UNDEFINED = 0
    SINGLE_PUSHBUTTON = 1
    TWO_WAY_PUSHBUTTON = 2
    FOUR_WAY_NAVIGATION = 3
    FOUR_WAY_WITH_CENTER = 4
    EIGHT_WAY_WITH_CENTER = 5
    ON_OFF_SWITCH = 6


@unique
class ButtonElementID(IntEnum):
    """Element identifier within a multi-contact button."""

    CENTER = 0
    DOWN = 1
    UP = 2
    LEFT = 3
    RIGHT = 4
    UPPER_LEFT = 5
    LOWER_LEFT = 6
    UPPER_RIGHT = 7
    LOWER_RIGHT = 8


@unique
class ButtonFunction(IntEnum):
    """Logical function / operating mode of a button (LTNUM lower 4 bits)."""

    DEVICE = 0
    AREA_1 = 1
    AREA_2 = 2
    AREA_3 = 3
    AREA_4 = 4
    ROOM = 5
    EXTENDED_1 = 6
    EXTENDED_2 = 7
    EXTENDED_3 = 8
    EXTENDED_4 = 9
    EXTENDED_AREA_1 = 10
    EXTENDED_AREA_2 = 11
    EXTENDED_AREA_3 = 12
    EXTENDED_AREA_4 = 13
    APARTMENT = 14
    APP = 15


@unique
class ButtonMode(IntEnum):
    """Button input mode (LTMODE register)."""

    STANDARD = 0
    TURBO = 1
    PRESENCE = 2
    TWO_WAY_UP_PAIRED_1 = 5
    TWO_WAY_UP_PAIRED_2 = 6
    TWO_WAY_UP_PAIRED_3 = 7
    TWO_WAY_UP_PAIRED_4 = 8
    TWO_WAY_DOWN_PAIRED_1 = 9
    TWO_WAY_DOWN_PAIRED_2 = 10
    TWO_WAY_DOWN_PAIRED_3 = 11
    TWO_WAY_DOWN_PAIRED_4 = 12


@unique
class ButtonGroup(IntEnum):
    """Target group for a button input (LTNUM upper 4 bits)."""

    LIGHT = 1
    BLINDS = 2
    CLIMATE = 3
    AUDIO = 4
    VIDEO = 5
    JOKER = 8


# ---------------------------------------------------------------------------
#  Button input error  (vDC API properties §4.2.3)
# ---------------------------------------------------------------------------


@unique
class InputError(IntEnum):
    """Error status of an input (button, binary, sensor)."""

    OK = 0
    OPEN_CIRCUIT = 1
    SHORT_CIRCUIT = 2
    BUS_CONNECTION = 4
    LOW_BATTERY = 5
    OTHER_ERROR = 6


# ---------------------------------------------------------------------------
#  Output error  (vDC API properties §4.8.3)
# ---------------------------------------------------------------------------


@unique
class OutputError(IntEnum):
    """Error status of an output."""

    OK = 0
    LAMP_BROKEN = 1      # open circuit
    SHORT_CIRCUIT = 2
    OVERLOAD = 3
    BUS_CONNECTION = 4
    LOW_BATTERY = 5
    OTHER_ERROR = 6


# ---------------------------------------------------------------------------
#  Scene effect  (vDC API properties §4.10)
# ---------------------------------------------------------------------------


@unique
class SceneEffect(IntEnum):
    """Transition effect when a scene is invoked."""

    NONE = 0            # immediate
    SMOOTH = 1          # normal transition
    SLOW = 2            # slow transition
    VERY_SLOW = 3       # very slow transition
    ALERT = 4           # blink / alerting


# ---------------------------------------------------------------------------
#  Heating system  (vDC API properties §4.8.2)
# ---------------------------------------------------------------------------


@unique
class HeatingSystemCapability(IntEnum):
    """How the ``heatingLevel`` control value is applied."""

    HEATING_ONLY = 1
    COOLING_ONLY = 2
    HEATING_AND_COOLING = 3


@unique
class HeatingSystemType(IntEnum):
    """Kind of heating/cooling actuator attached."""

    UNDEFINED = 0
    FLOOR_HEATING = 1
    RADIATOR = 2
    WALL_HEATING = 3
    CONVECTOR_PASSIVE = 4
    CONVECTOR_ACTIVE = 5
    FLOOR_HEATING_LOW_ENERGY = 6


# ---------------------------------------------------------------------------
#  Power state channel values  (vDC API properties §4.9.4)
# ---------------------------------------------------------------------------


@unique
class PowerState(IntEnum):
    """Discrete values for the ``powerState`` output channel."""

    OFF = 0
    ON = 1
    FORCED_OFF = 2
    STANDBY = 3


# ---------------------------------------------------------------------------
#  Air flow direction channel values  (vDC API properties §4.9.4)
# ---------------------------------------------------------------------------


@unique
class AirFlowDirection(IntEnum):
    """Discrete values for the ``airFlowDirection`` output channel."""

    BOTH_UNDEFINED = 0
    SUPPLY_IN = 1
    EXHAUST_OUT = 2


# ---------------------------------------------------------------------------
#  Output hardware mode  (ds-basics Table 52)
# ---------------------------------------------------------------------------


@unique
class OutputHardwareMode(IntEnum):
    """Low-level output hardware mode (for reference / device parameters)."""

    DISABLED = 0
    SWITCHED = 16
    RMS_DIMMER = 17
    RMS_DIMMER_CURVE = 18
    PHASE_CONTROL_DIMMER = 19
    PHASE_CONTROL_DIMMER_CURVE = 20
    REVERSE_PHASE_DIMMER = 21
    REVERSE_PHASE_DIMMER_CURVE = 22
    PWM = 23
    PWM_CURVE = 24
    POSITIONING_CONTROL = 33
    RELAY_SWITCHED = 39
    RELAY_WIPED = 40
    RELAY_SAVING = 41
    POSITIONING_UNCALIBRATED = 42


# ---------------------------------------------------------------------------
#  Temperature control scenes  (ds-basics Table 47)
# ---------------------------------------------------------------------------


@unique
class TemperatureControlScene(IntEnum):
    """Scene commands specific to the temperature control application."""

    HEATING_OFF = 0
    HEATING_COMFORT = 1
    HEATING_ECONOMY = 2
    HEATING_NOT_USED = 3
    HEATING_NIGHT = 4
    HEATING_HOLIDAY = 5
    PASSIVE_COOLING_ACTIVE = 6
    PASSIVE_COOLING_INACTIVE = 7
    COOLING_OFF = 9
    COOLING_COMFORT = 10
    COOLING_ECONOMY = 11
    COOLING_NOT_USED = 12
    COOLING_NIGHT = 13
    COOLING_HOLIDAY = 14


# ---------------------------------------------------------------------------
#  Temperature device control scenes  (ds-basics Table 48)
# ---------------------------------------------------------------------------


@unique
class TemperatureDeviceScene(IntEnum):
    """Device-level control scenes for climate devices."""

    POWER_ON = 29
    POWER_OFF = 30
    VALVE_PROTECTION = 31
    FORCE_VALVE_OPEN = 32
    FORCE_VALVE_CLOSE = 33
    FORCE_FAN_MODE = 40
    FORCE_DRY_MODE = 41
    AUTOMATIC_MODE = 42


# ---------------------------------------------------------------------------
#  Ventilation control scenes  (ds-basics Table 49)
# ---------------------------------------------------------------------------


@unique
class VentilationScene(IntEnum):
    """Scene commands specific to ventilation / recirculation."""

    OFF = 0
    STAGE_1 = 5
    STAGE_2 = 17
    STAGE_3 = 18
    STAGE_4 = 19
    BOOST = 6
    NOISE_REDUCTION = 7
    AUTOMATIC_AIR_FLOW = 8
    AUTO_LOUVER_POSITION = 9
