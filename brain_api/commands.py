"""Central command policy for optional BX1 Brain modules."""

API_ID = "bx1.brain.v1"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8775

ROBOT_COMMANDS = {
    "balance.status",
    "balance.get_parameters",
    "balance.disarm",
    "balance.clear_fault",
    "drive.status",
    "drive.set_motion",
    "drive.forward",
    "drive.reverse",
    "drive.left",
    "drive.right",
    "drive.hold",
    "drive.stop",
    "drive.estop",
    "head.center",
    "head.set_pose",
    "head.move_relative",
    "head.get_state",
    "led.set_mode",
    "led.set_all",
    "led.set_pixel",
    "led.set_mouth_level",
}

LOCAL_COMMANDS = {
    "brain.status",
    "brain.commands",
    "led.task",
}
