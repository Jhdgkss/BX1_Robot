#!/usr/bin/env python3
"""Generate UNO Q MCU hardware constants from config/hardware_config.json.

Run after changing LED, head-servo or RS485 drive hardware settings:

    python tools/generate_mcu_hardware_config.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "hardware_config.json"
HEADER_PATH = ROOT / "mcu" / "bx1_led_mcu" / "bx1_hardware_config.h"


def tenths(value: float) -> int:
    return int(round(float(value) * 10.0))


def main() -> None:
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    leds = data["leds"]
    head = data["head"]
    neck = head["neck"]
    pulse = head["pulse"]
    mixer = neck["mixer"]
    drive = data["drive"]
    uart = drive["uart"]
    balance = drive.get("balance", {})
    imu = data.get("future_hardware", {}).get("imu", {})
    pitch_axis_code = {"x": 0, "y": 1, "z": 2}.get(str(balance.get("pitch_axis", "y")).lower(), 1)
    work_mode_code = {"SR_OPEN": 3, "SR_CLOSE": 4, "SR_VFOC": 5}.get(
        str(balance.get("drive_work_mode", "SR_OPEN")).upper(), 3
    )

    content = f'''// AUTO-GENERATED FILE - DO NOT EDIT DIRECTLY.
// Source: config/hardware_config.json
// Generator: tools/generate_mcu_hardware_config.py

#pragma once

#include <Arduino.h>

static constexpr uint8_t BX1_LED_PIN = {int(leds["data_pin"])};
static constexpr uint16_t BX1_LED_COUNT = {int(leds["count"])};
static constexpr uint16_t BX1_MOUTH_LED_INDEX = {int(leds["mouth"]["mcu_index"])};
static constexpr uint8_t BX1_LED_DEFAULT_BRIGHTNESS = {int(leds["default_global_brightness_0_255"])};

static constexpr uint8_t BX1_HEAD_YAW_PIN = {int(head["pan"]["pin"])};
static constexpr uint8_t BX1_HEAD_LEFT_PIN = {int(neck["left_servo"]["pin"])};
static constexpr uint8_t BX1_HEAD_RIGHT_PIN = {int(neck["right_servo"]["pin"])};

static constexpr int BX1_SERVO_CENTRE_US = {int(pulse["center_us"])};
static constexpr int BX1_SERVO_US_PER_DEG = {int(pulse["us_per_deg"])};

static constexpr int BX1_PAN_MIN_TENTHS = {tenths(head["pan"]["min_deg"])};
static constexpr int BX1_PAN_MAX_TENTHS = {tenths(head["pan"]["max_deg"])};
static constexpr int BX1_PITCH_MIN_TENTHS = {tenths(neck["pitch"]["min_deg"])};
static constexpr int BX1_PITCH_MAX_TENTHS = {tenths(neck["pitch"]["max_deg"])};
static constexpr int BX1_ROLL_MIN_TENTHS = {tenths(neck["roll"]["min_deg"])};
static constexpr int BX1_ROLL_MAX_TENTHS = {tenths(neck["roll"]["max_deg"])};
static constexpr int BX1_GIMBAL_OUTPUT_LIMIT_TENTHS = {tenths(mixer["physical_output_limit_deg"])};

static constexpr int BX1_LEFT_PITCH_SIGN = {int(mixer["left_pitch_sign"])};
static constexpr int BX1_RIGHT_PITCH_SIGN = {int(mixer["right_pitch_sign"])};
static constexpr int BX1_LEFT_ROLL_SIGN = {int(mixer["left_roll_sign"])};
static constexpr int BX1_RIGHT_ROLL_SIGN = {int(mixer["right_roll_sign"])};

// RS485 wheel bus: Serial1 uses UNO Q hardware UART D0/RX and D1/TX.
static constexpr bool BX1_DRIVE_ENABLED = {str(bool(drive.get("enabled", False))).lower()};
static constexpr uint8_t BX1_RS485_RX_PIN = {int(uart["rx_pin"])};
static constexpr uint8_t BX1_RS485_TX_PIN = {int(uart["tx_pin"])};
static constexpr uint8_t BX1_RS485_DIR_PIN = {int(uart["direction_pin"])};
static constexpr uint32_t BX1_RS485_BAUD = {int(uart["baud"])}UL;
static constexpr uint16_t BX1_RS485_RESPONSE_TIMEOUT_MS = {int(uart.get("response_timeout_ms", 1000))};
static constexpr uint32_t BX1_DRIVE_CALIBRATION_TIMEOUT_MS = {int(uart.get("calibration_timeout_ms", 30000))}UL;
static constexpr uint16_t BX1_RS485_TX_SETTLE_US = {int(uart.get("tx_settle_us", 20))};
static constexpr uint16_t BX1_RS485_TX_TO_RX_TURNAROUND_US = {int(uart.get("tx_to_rx_turnaround_us", 100))};
static constexpr uint16_t BX1_RS485_RX_SETTLE_US = {int(uart.get("rx_settle_us", 50))};

// Wheel identity / logical robot-forward mapping.
static constexpr uint8_t BX1_LEFT_MOTOR_ADDRESS = {int(drive["left_motor"]["address"])};
static constexpr uint8_t BX1_RIGHT_MOTOR_ADDRESS = {int(drive["right_motor"]["address"])};
static constexpr uint8_t BX1_LEFT_FORWARD_DIRECTION = {int(drive["left_motor"]["forward_direction"])};
static constexpr uint8_t BX1_RIGHT_FORWARD_DIRECTION = {int(drive["right_motor"]["forward_direction"])};

// Modulino Movement / balance controller. Startup is always disarmed.
static constexpr bool BX1_IMU_ENABLED = {str(bool(imu.get("enabled", False))).lower()};
static constexpr bool BX1_BALANCE_ENABLED = {str(bool(balance.get("enabled", False))).lower()};
static constexpr bool BX1_BALANCE_AXIS_MAPPING_CONFIRMED = {str(bool(balance.get("axis_mapping_confirmed", False))).lower()};
static constexpr uint16_t BX1_BALANCE_UPDATE_HZ = {int(balance.get("update_hz", 100))};
static constexpr uint32_t BX1_BALANCE_PERIOD_US = 1000000UL / BX1_BALANCE_UPDATE_HZ;
static constexpr int BX1_BALANCE_PITCH_AXIS = {pitch_axis_code}; // 0=X, 1=Y, 2=Z
static constexpr int BX1_BALANCE_SENSOR_SIGN = {int(balance.get("sensor_sign", 1))};
static constexpr int BX1_BALANCE_DEFAULT_OUTPUT_SIGN = {int(balance.get("output_sign", 1))};
static constexpr int BX1_BALANCE_COMPLEMENTARY_ALPHA_MILLI = {int(round(float(balance.get("complementary_gyro_weight", 0.98)) * 1000.0))};
static constexpr int BX1_BALANCE_DEFAULT_KP_MILLI = {int(round(float(balance.get("kp_rpm_per_deg", 8.0)) * 1000.0))};
static constexpr int BX1_BALANCE_DEFAULT_KD_MILLI = {int(round(float(balance.get("kd_rpm_per_dps", 0.25)) * 1000.0))};
static constexpr int BX1_BALANCE_DEFAULT_MAX_RPM = {int(balance.get("max_output_rpm", 120))};
static constexpr int BX1_BALANCE_MOTOR_ACCELERATION = {int(balance.get("motor_acceleration", 2))};
static constexpr int BX1_BALANCE_DRIVE_MODE_CODE = {work_mode_code}; // 3=SR_OPEN, 4=SR_CLOSE, 5=SR_vFOC
static constexpr int BX1_BALANCE_DRIVE_CURRENT_MA = {int(balance.get("drive_current_ma", 1800))};
static constexpr bool BX1_BALANCE_RESONANCE_AVOIDANCE = {str(bool(balance.get("resonance_avoidance_enabled", False))).lower()};
static constexpr int BX1_BALANCE_RESONANCE_LOW_RPM = {int(balance.get("resonance_low_rpm", 3))};
static constexpr int BX1_BALANCE_RESONANCE_HIGH_RPM = {int(balance.get("resonance_high_rpm", 5))};
static constexpr int BX1_BALANCE_RESONANCE_ESCAPE_RPM = {int(balance.get("resonance_escape_rpm", 6))};
static constexpr int BX1_BALANCE_COMMAND_CHANGE_RPM = {int(balance.get("motor_command_change_rpm", 2))};
static constexpr uint32_t BX1_BALANCE_COMMAND_KEEPALIVE_MS = {int(balance.get("motor_command_keepalive_ms", 100))}UL;
static constexpr int BX1_BALANCE_ARM_WINDOW_MDEG = {int(round(float(balance.get("arm_window_deg", 5.0)) * 1000.0))};
static constexpr int BX1_BALANCE_FALL_ANGLE_MDEG = {int(round(float(balance.get("fall_angle_deg", 25.0)) * 1000.0))};
static constexpr uint32_t BX1_BALANCE_IMU_TIMEOUT_MS = {int(balance.get("imu_timeout_ms", 75))}UL;
'''

    HEADER_PATH.write_text(content, encoding="utf-8")
    print(f"Generated {HEADER_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
