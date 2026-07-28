"""BX1 hardware service foundation.

All public services expose ``status()``, ``health()``, ``diagnostics()`` and
``configuration()``.  Hardware-specific I/O is supplied through adapters, so
callers do not need to know whether a service is simulated.
"""

from .digital_twin import DigitalTwin, HardwareServices, create_hardware_services
from .battery import BatteryService
from .battery_monitor import (
    BatteryMeasurement,
    BatteryMonitorBase,
    INA219Monitor,
    INA226Monitor,
    INA228Monitor,
    MockBatteryMonitor,
)
from .battery_state import BatteryState, BatteryStateMachine
from .battery_twin import BatteryDigitalTwin, PowerServices, create_power_services
from .bms import BMSBase, HardwareOnlyBMS, MockBMS, PassiveBMS, SmartBMS
from .capability import Capability, CapabilityRegistry
from .docking import DockInterface
from .event_bus import Event, EventBus, EventType
from .led import (
    CallbackLEDStrip,
    LEDEffect,
    LEDService,
    SimulatedLEDStrip,
)
from .motor import (
    CommandValidator,
    DriveService,
    MotorController,
    MotorState,
    RS485Transport,
)
from .range import (
    DistanceReading,
    DistanceSensorBase,
    FutureToFSensor,
    MockDistanceSensor,
    RangeService,
)
from .power import PowerService, SystemPowerState
from .power_config import DEFAULT_POWER_CONFIGURATION, load_power_configuration
from .state import HardwareState, HardwareStateManager

__all__ = [
    "CallbackLEDStrip",
    "BatteryDigitalTwin",
    "BatteryMeasurement",
    "BatteryMonitorBase",
    "BatteryService",
    "BatteryState",
    "BatteryStateMachine",
    "BMSBase",
    "Capability",
    "CapabilityRegistry",
    "CommandValidator",
    "DigitalTwin",
    "DistanceReading",
    "DistanceSensorBase",
    "DriveService",
    "DockInterface",
    "Event",
    "EventBus",
    "EventType",
    "FutureToFSensor",
    "HardwareServices",
    "HardwareOnlyBMS",
    "HardwareState",
    "HardwareStateManager",
    "INA219Monitor",
    "INA226Monitor",
    "INA228Monitor",
    "LEDEffect",
    "LEDService",
    "MockBatteryMonitor",
    "MockBMS",
    "MockDistanceSensor",
    "MotorController",
    "MotorState",
    "PassiveBMS",
    "PowerService",
    "PowerServices",
    "RS485Transport",
    "RangeService",
    "SimulatedLEDStrip",
    "SmartBMS",
    "SystemPowerState",
    "DEFAULT_POWER_CONFIGURATION",
    "create_hardware_services",
    "create_power_services",
    "load_power_configuration",
]
