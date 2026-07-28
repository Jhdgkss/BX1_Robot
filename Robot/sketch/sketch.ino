/*
  Robot Brain UNO Q Body MCU Bridge Sketch v10.39

  Purpose:
  - Read Arduino Modulino Movement IMU.
  - Expose body telemetry to the UNO Q Linux/Python side via Arduino Bridge.
  - Receive bounded action packets from the Brain App via Python and apply safe local outputs.

  Safety:
  - Wheel drive is a safe stub by default until the real motor driver protocol is confirmed.
  - The RPC handler only stores the requested action; actual hardware updates are applied in loop().
*/

#include <Arduino.h>
#include <Arduino_RouterBridge.h>
#include <Wire.h>
#include <Arduino_LSM6DSOX.h>
#include <math.h>

#define BX1_FIRMWARE_VERSION "10.39"
#define BX1_PROTOCOL_VERSION "bx1.mcu.v1"
#define BX1_BUILD_ID __DATE__ " " __TIME__

// ---------------- User hardware mapping ----------------
// These are safe defaults. The Python web page can send a runtime
// configure_hardware packet with the actual pins you choose.
// -1 means disabled.
#define HEAD_YAW_SERVO_PIN          -1   // rotation / yaw
#define HEAD_GIMBAL_LEFT_SERVO_PIN  -1   // left push-pull linkage servo
#define HEAD_GIMBAL_RIGHT_SERVO_PIN -1   // right push-pull linkage servo
#define BUZZER_PIN           -1
#define ESTOP_INPUT_PIN      -1

// Keep false until the actual drive hardware is wired and tested.
#define BX1_ENABLE_DRIVE_OUTPUTS 0

// Addressable RGB LEDs. Install the Adafruit NeoPixel library before enabling.
// The runtime web map can set eyes/mouth pins/counts after boot.
#define BX1_USE_NEOPIXEL 1
#if BX1_USE_NEOPIXEL
#include <Adafruit_NeoPixel.h>
Adafruit_NeoPixel eyesPixels;
Adafruit_NeoPixel mouthPixels;
#endif

#include <Arduino_HardwareServo.h>
HardwareServo yawServo;
HardwareServo gimbalLeftServo;
HardwareServo gimbalRightServo;

int headYawPin = HEAD_YAW_SERVO_PIN;
int headGimbalLeftPin = HEAD_GIMBAL_LEFT_SERVO_PIN;
int headGimbalRightPin = HEAD_GIMBAL_RIGHT_SERVO_PIN;
bool yawServoAttached = false;
bool gimbalLeftServoAttached = false;
bool gimbalRightServoAttached = false;

// Quiet-servo mode: standard hobby servos can buzz while continuously holding a
// mechanically loaded position. BX1 can release PWM after the requested pose has
// settled, then automatically reattach on the next movement command. This is
// configurable because a head that relies on active holding may need it disabled.
bool servoQuietReleaseEnabled = true;
unsigned long servoReleaseAfterMs = 1200UL;
int servoPulseDeadbandUs = 4;
unsigned long lastServoMotionMs = 0UL;
bool servoOutputsReleased = false;
unsigned long servoReleaseCount = 0UL;

float yawMinDeg = -75.0f;
float yawMaxDeg = 75.0f;
float yawHomeDeg = 0.0f;
bool yawInvert = false;

// Physical servo command ranges. These are relative linkage command degrees,
// not the logical head pitch/roll angles.
float gimbalLeftMinDeg = -35.0f;
float gimbalLeftMaxDeg = 35.0f;
float gimbalLeftHomeDeg = 0.0f;
bool gimbalLeftInvert = false;
float gimbalRightMinDeg = -35.0f;
float gimbalRightMaxDeg = 35.0f;
float gimbalRightHomeDeg = 0.0f;
bool gimbalRightInvert = false;

// Logical head limits and mixer. The linkage image shows two side servos
// pushing/pulling opposite ends of one gimbal. Pitch and roll therefore share
// both servos rather than using one servo per axis.
float logicalPitchMinDeg = -10.0f;
float logicalPitchMaxDeg = 10.0f;
float logicalPitchHomeDeg = 0.0f;
float logicalRollMinDeg = -10.0f;
float logicalRollMaxDeg = 10.0f;
float logicalRollHomeDeg = 0.0f;
float pitchMixGain = 1.0f;
float rollMixGain = 1.0f;
int leftPitchSign = 1;
int rightPitchSign = -1;
int leftRollSign = 1;
int rightRollSign = 1;

int eyesLedPin = -1;
int eyesLedCount = 24;
bool eyesLedReady = false;
int mouthLedPin = -1;
int mouthLedCount = 8;
bool mouthLedReady = false;

// v10: one shared addressable LED bus with logical zones. Web UI uses human-friendly LED addresses.
Adafruit_NeoPixel bodyPixels;
int bodyLedPin = -1;
int bodyLedCount = 100;
bool bodyLedReady = false;
float bodyLedBrightnessLimit = 0.20f;
int zoneMouthStart = -1, zoneMouthEnd = -1;
int zoneLeftEyeStart = -1, zoneLeftEyeEnd = -1;
int zoneRightEyeStart = -1, zoneRightEyeEnd = -1;
int zoneChestStart = -1, zoneChestEnd = -1;
int zoneStatusStart = -1, zoneStatusEnd = -1;

// ---------------- IMU ----------------
// The UNO Q Qwiic connector is on Wire1. The previous sketch used the global
// IMU object, which is constructed on the default Wire bus and therefore could
// not see the external Modulino Movement. Arduino's Modulino wrapper ultimately
// constructs the same LSM6DSOX class with Wire1 and address 0x6A. Keeping the
// direct class here avoids pulling unrelated Modulino dependencies into the
// safety-critical bridge shim while using the correct Qwiic bus.
static constexpr uint8_t BX1_MOVEMENT_ADDRESS_PRIMARY = 0x6A;
static constexpr uint8_t BX1_MOVEMENT_ADDRESS_SECONDARY = 0x6B;
LSM6DSOXClass movementImu6A(Wire1, BX1_MOVEMENT_ADDRESS_PRIMARY);
LSM6DSOXClass movementImu6B(Wire1, BX1_MOVEMENT_ADDRESS_SECONDARY);
LSM6DSOXClass* movementImu = nullptr;
bool hardwareInitStarted = false;
bool hardwareInitComplete = false;
bool imuOk = false;
String imuError = "not_started";
String imuSource = "Modulino Movement / LSM6DSOX";
String imuBus = "Wire1/Qwiic";
String imuAddress = "not_detected";
float ax = 0.0f;
float ay = 0.0f;
float az = 0.0f;
float gyroRoll = 0.0f;
float gyroPitch = 0.0f;
float gyroYaw = 0.0f;
float pitchDeg = 0.0f;
float rollDeg = 0.0f;
unsigned long lastImuInitAttemptMs = 0;
unsigned long imuReadFailures = 0;

// ---------------- Command state ----------------
String pendingActionJson = "";
bool actionPending = false;
String serialBridgeBuffer = "";
bool estopLatched = false;
String modeText = "booting";
String lastActionType = "none";
String lastLedColour = "off";
String lastLedZone = "none";
float lastLedBrightness = 0.0f;
float lastLedEffectiveBrightness = 0.0f;
unsigned long ledCommandCount = 0;
float lastHeadYawDeg = 0.0f;
float lastHeadPitchDeg = 0.0f;
float lastHeadRollDeg = 0.0f;
float lastGimbalLeftDeg = 0.0f;
float lastGimbalRightDeg = 0.0f;
int lastYawPulseUs = 1500;
int lastGimbalLeftPulseUs = 1500;
int lastGimbalRightPulseUs = 1500;
String lastServoAttachError = "";
float lastLinearMps = 0.0f;
float lastAngularDps = 0.0f;
unsigned long driveUntilMs = 0;
unsigned long lastImuUpdateMs = 0;
unsigned long lastCommandMs = 0;
unsigned long heartbeatSequence = 0;
bool maintenanceMode = false;

// ---------------- Helpers ----------------
float clampf(float value, float lo, float hi) {
  if (value < lo) return lo;
  if (value > hi) return hi;
  return value;
}

String jsonEscape(const String &input) {
  String out = "";
  for (unsigned int i = 0; i < input.length(); i++) {
    char c = input.charAt(i);
    if (c == '\\' || c == '"') {
      out += '\\';
      out += c;
    } else if (c == '\n') {
      out += "\\n";
    } else if (c == '\r') {
      out += "\\r";
    } else {
      out += c;
    }
  }
  return out;
}

void applyLedToTarget(const String &target, const String &colour, float brightness);
void applyLedToZone(const String &zone, const String &colour, float brightness);
int servoDegToUs(float deg, float lo, float hi, bool invertAxis);
void applyHeadPose(float yawDeg, float pitchDegCommand, float rollDegCommand);

float extractJsonFloat(const String &json, const String &key, float defaultValue) {
  String marker = "\"" + key + "\":";
  int idx = json.indexOf(marker);
  if (idx < 0) return defaultValue;
  idx += marker.length();
  int end = idx;
  while (end < (int)json.length()) {
    char c = json.charAt(end);
    if ((c >= '0' && c <= '9') || c == '-' || c == '+' || c == '.') {
      end++;
    } else {
      break;
    }
  }
  if (end <= idx) return defaultValue;
  return json.substring(idx, end).toFloat();
}

String extractJsonString(const String &json, const String &key, const String &defaultValue) {
  String marker = "\"" + key + "\":\"";
  int idx = json.indexOf(marker);
  if (idx < 0) return defaultValue;
  idx += marker.length();
  int end = json.indexOf("\"", idx);
  if (end < 0) return defaultValue;
  return json.substring(idx, end);
}

bool i2cAddressPresent(TwoWire &wire, uint8_t address) {
  wire.beginTransmission(address);
  return wire.endTransmission() == 0;
}

String bx1_i2c_scan() {
  // Read-only diagnostic: never writes a device register or touches actuators.
  Wire1.begin();
  Wire1.setClock(100000);
  String json = "{\"ok\":true,\"bus\":\"Wire1/Qwiic\",\"devices\":[";
  bool first = true;
  for (uint8_t address = 1; address < 127; address++) {
    if (!i2cAddressPresent(Wire1, address)) continue;
    if (!first) json += ",";
    json += "\"0x";
    if (address < 16) json += "0";
    json += String(address, HEX);
    json += "\"";
    first = false;
  }
  json += "]}";
  return json;
}

bool initialiseMovementImu() {
  lastImuInitAttemptMs = millis();

  // Bridge is already online before this function is called. Probe the bus
  // before entering the sensor library so a missing/unpowered Qwiic module
  // can never prevent RouterBridge RPC registration.
  Wire1.begin();
  Wire1.setClock(100000);

  uint8_t detectedAddress = 0;
  if (i2cAddressPresent(Wire1, BX1_MOVEMENT_ADDRESS_PRIMARY)) {
    detectedAddress = BX1_MOVEMENT_ADDRESS_PRIMARY;
    movementImu = &movementImu6A;
  } else if (i2cAddressPresent(Wire1, BX1_MOVEMENT_ADDRESS_SECONDARY)) {
    detectedAddress = BX1_MOVEMENT_ADDRESS_SECONDARY;
    movementImu = &movementImu6B;
  } else {
    movementImu = nullptr;
    imuOk = false;
    imuAddress = "not_detected";
    imuError = "Modulino Movement not found on UNO Q Wire1/Qwiic at 0x6A or 0x6B. Bridge remains online; check Qwiic power, cable orientation, seating and I2C pull-ups.";
    if (!maintenanceMode) modeText = "ready_no_imu";
    return false;
  }

  imuAddress = detectedAddress == BX1_MOVEMENT_ADDRESS_PRIMARY ? "0x6A" : "0x6B";
  if (movementImu != nullptr && movementImu->begin()) {
    imuOk = true;
    imuError = "";
    imuReadFailures = 0;
    if (!maintenanceMode) modeText = "ready";
    return true;
  }

  imuOk = false;
  imuError = String("LSM6DSOX responded on ") + imuAddress + " but sensor initialisation failed. Bridge remains online.";
  if (!maintenanceMode) modeText = "ready_no_imu";
  return false;
}

void updateImu() {
  if (!imuOk) {
    // Allow the module to be connected after boot without repeatedly hammering I2C.
    if (millis() - lastImuInitAttemptMs >= 5000UL) initialiseMovementImu();
    return;
  }

  bool gotAccel = false;
  bool gotGyro = false;

  if (movementImu != nullptr && movementImu->accelerationAvailable()) {
    if (movementImu->readAcceleration(ax, ay, az)) gotAccel = true;
  }

  if (movementImu != nullptr && movementImu->gyroscopeAvailable()) {
    float gx = 0.0f;
    float gy = 0.0f;
    float gz = 0.0f;
    if (movementImu->readGyroscope(gx, gy, gz)) {
      gyroRoll = gx;
      gyroPitch = gy;
      gyroYaw = gz;
      gotGyro = true;
    }
  }

  if (gotAccel) {
    // Basic accelerometer tilt estimate for telemetry and body awareness.
    pitchDeg = atan2(-ax, sqrt((ay * ay) + (az * az))) * 57.2957795f;
    rollDeg = atan2(ay, az) * 57.2957795f;
  }

  if (gotAccel || gotGyro) {
    lastImuUpdateMs = millis();
    imuReadFailures = 0;
    imuError = "";
  } else {
    imuReadFailures++;
    if (imuReadFailures > 250) {
      imuOk = false;
      imuError = "Modulino Movement stopped returning data; waiting to retry Wire1/Qwiic.";
      if (!maintenanceMode) modeText = "ready_no_imu";
    }
  }
}

bool safetyOk() {
  bool fallen = fabs(pitchDeg) > 45.0f || fabs(rollDeg) > 45.0f;
  bool estopInput = false;
#if ESTOP_INPUT_PIN >= 0
  estopInput = digitalRead(ESTOP_INPUT_PIN) == LOW;
#endif
  return !fallen && !estopLatched && !estopInput;
}


void configureServo(HardwareServo &servo, bool &attached, int &currentPin, int newPin) {
  if (newPin < 0) {
    if (attached) servo.detach();
    attached = false;
    currentPin = -1;
    return;
  }
  if (!attached || currentPin != newPin) {
    if (attached) servo.detach();
    currentPin = newPin;
    servo.attach(currentPin);
    attached = servo.attached();
    if (!attached) {
      lastServoAttachError = String("HardwareServo attach failed on D") + String(currentPin);
      modeText = "servo_attach_failed";
    } else {
      lastServoAttachError = "";
    }
  }
}


bool commandServoPulse(
    HardwareServo &servo, bool &attached, int &currentPin,
    int pulseUs, int &lastPulseUs, bool forceWrite) {
  if (currentPin < 0) return false;
  pulseUs = constrain(pulseUs, 900, 2100);
  bool wasAttached = attached;
  configureServo(servo, attached, currentPin, currentPin);
  if (!attached) return false;
  int delta = abs(pulseUs - lastPulseUs);
  if (forceWrite || !wasAttached || delta >= servoPulseDeadbandUs) {
    servo.writeMicroseconds(pulseUs);
    lastPulseUs = pulseUs;
    lastServoMotionMs = millis();
  }
  servoOutputsReleased = false;
  return true;
}

void releaseHeadServosIfQuiet() {
  if (!servoQuietReleaseEnabled || servoReleaseAfterMs == 0UL || lastServoMotionMs == 0UL) return;
  if ((unsigned long)(millis() - lastServoMotionMs) < servoReleaseAfterMs) return;
  bool releasedAny = false;
  if (yawServoAttached) { yawServo.detach(); yawServoAttached = false; releasedAny = true; }
  if (gimbalLeftServoAttached) { gimbalLeftServo.detach(); gimbalLeftServoAttached = false; releasedAny = true; }
  if (gimbalRightServoAttached) { gimbalRightServo.detach(); gimbalRightServoAttached = false; releasedAny = true; }
  if (releasedAny) {
    servoOutputsReleased = true;
    servoReleaseCount++;
  }
}

#if BX1_USE_NEOPIXEL
void configurePixels(Adafruit_NeoPixel &pixels, bool &ready, int &currentPin, int &currentCount, int newPin, int newCount) {
  if (newPin < 0 || newCount <= 0) {
    if (ready) {
      pixels.clear();
      pixels.show();
    }
    ready = false;
    currentPin = -1;
    currentCount = max(1, newCount);
    return;
  }
  currentPin = newPin;
  currentCount = max(1, newCount);
  pixels.updateType(NEO_GRB + NEO_KHZ800);
  pixels.updateLength((uint16_t)currentCount);
  pixels.setPin(currentPin);
  pixels.begin();
  pixels.clear();
  pixels.show();
  ready = true;
}
#endif


bool configureLedBusDirect(int pin, int count, float brightnessLimit) {
#if BX1_USE_NEOPIXEL
  bodyLedBrightnessLimit = clampf(brightnessLimit, 0.0f, 1.0f);
  configurePixels(bodyPixels, bodyLedReady, bodyLedPin, bodyLedCount, pin, count);
  // Keep legacy status fields aligned with the shared bus.
  eyesLedPin = bodyLedPin;
  mouthLedPin = bodyLedPin;
  eyesLedCount = bodyLedCount;
  mouthLedCount = bodyLedCount;
  modeText = "led_bus_configured";
  return (pin < 0) || bodyLedReady;
#else
  modeText = "neopixel_disabled";
  return pin < 0;
#endif
}

bool configureLedZoneDirect(const String &zone, int startLed, int endLed) {
  if (startLed < 0 || endLed < 0 || endLed < startLed) {
    startLed = -1;
    endLed = -1;
  }
  if (zone == "mouth") {
    zoneMouthStart = startLed;
    zoneMouthEnd = endLed;
  } else if (zone == "left_eye") {
    zoneLeftEyeStart = startLed;
    zoneLeftEyeEnd = endLed;
  } else if (zone == "right_eye") {
    zoneRightEyeStart = startLed;
    zoneRightEyeEnd = endLed;
  } else if (zone == "chest") {
    zoneChestStart = startLed;
    zoneChestEnd = endLed;
  } else if (zone == "status") {
    zoneStatusStart = startLed;
    zoneStatusEnd = endLed;
  } else {
    modeText = "bad_led_zone";
    return false;
  }
  modeText = "led_zone_configured";
  return true;
}

bool configureServoDirect(const String &servoName, int pin, float minDeg, float homeDeg, float maxDeg, int invertFlag) {
  if (maxDeg < minDeg) {
    float t = maxDeg;
    maxDeg = minDeg;
    minDeg = t;
  }
  homeDeg = clampf(homeDeg, minDeg, maxDeg);
  bool inv = invertFlag != 0;

  if (servoName == "head_yaw" || servoName == "yaw") {
    yawMinDeg = minDeg;
    yawMaxDeg = maxDeg;
    yawHomeDeg = homeDeg;
    yawInvert = inv;
    configureServo(yawServo, yawServoAttached, headYawPin, pin);
    commandServoPulse(yawServo, yawServoAttached, headYawPin,
                      servoDegToUs(yawHomeDeg, yawMinDeg, yawMaxDeg, yawInvert),
                      lastYawPulseUs, true);
  } else if (servoName == "gimbal_left" || servoName == "head_gimbal_left" || servoName == "head_pitch" || servoName == "pitch") {
    gimbalLeftMinDeg = minDeg;
    gimbalLeftMaxDeg = maxDeg;
    gimbalLeftHomeDeg = homeDeg;
    gimbalLeftInvert = inv;
    configureServo(gimbalLeftServo, gimbalLeftServoAttached, headGimbalLeftPin, pin);
    commandServoPulse(gimbalLeftServo, gimbalLeftServoAttached, headGimbalLeftPin,
                      servoDegToUs(gimbalLeftHomeDeg, gimbalLeftMinDeg, gimbalLeftMaxDeg, gimbalLeftInvert),
                      lastGimbalLeftPulseUs, true);
  } else if (servoName == "gimbal_right" || servoName == "head_gimbal_right" || servoName == "head_roll" || servoName == "roll") {
    gimbalRightMinDeg = minDeg;
    gimbalRightMaxDeg = maxDeg;
    gimbalRightHomeDeg = homeDeg;
    gimbalRightInvert = inv;
    configureServo(gimbalRightServo, gimbalRightServoAttached, headGimbalRightPin, pin);
    commandServoPulse(gimbalRightServo, gimbalRightServoAttached, headGimbalRightPin,
                      servoDegToUs(gimbalRightHomeDeg, gimbalRightMinDeg, gimbalRightMaxDeg, gimbalRightInvert),
                      lastGimbalRightPulseUs, true);
  } else {
    modeText = "bad_servo";
    return false;
  }

  modeText = "servo_configured";
  return true;
}

bool bx1_config_led_bus(int pin, int count, float brightnessLimit) {
  return configureLedBusDirect(pin, count, brightnessLimit);
}

bool bx1_config_led_zone(String zone, int startLed, int endLed) {
  return configureLedZoneDirect(zone, startLed, endLed);
}

bool bx1_config_servo(String servoName, int pin, float minDeg, float homeDeg, float maxDeg, int invertFlag) {
  return configureServoDirect(servoName, pin, minDeg, homeDeg, maxDeg, invertFlag);
}

bool bx1_config_head_limits(float pitchMin, float pitchHome, float pitchMax, float rollMin, float rollHome, float rollMax) {
  if (pitchMax < pitchMin) { float t = pitchMax; pitchMax = pitchMin; pitchMin = t; }
  if (rollMax < rollMin) { float t = rollMax; rollMax = rollMin; rollMin = t; }
  logicalPitchMinDeg = pitchMin;
  logicalPitchMaxDeg = pitchMax;
  logicalPitchHomeDeg = clampf(pitchHome, pitchMin, pitchMax);
  logicalRollMinDeg = rollMin;
  logicalRollMaxDeg = rollMax;
  logicalRollHomeDeg = clampf(rollHome, rollMin, rollMax);
  modeText = "head_limits_configured";
  return true;
}

bool bx1_config_head_mix(float pitchGain, float rollGain, int lp, int rp, int lr, int rr) {
  pitchMixGain = clampf(pitchGain, 0.05f, 5.0f);
  rollMixGain = clampf(rollGain, 0.05f, 5.0f);
  leftPitchSign = lp >= 0 ? 1 : -1;
  rightPitchSign = rp >= 0 ? 1 : -1;
  leftRollSign = lr >= 0 ? 1 : -1;
  rightRollSign = rr >= 0 ? 1 : -1;
  modeText = "head_mixer_configured";
  return true;
}


bool bx1_config_servo_quiet(int enabledFlag, int releaseAfterMs, int deadbandUs) {
  servoQuietReleaseEnabled = enabledFlag != 0;
  servoReleaseAfterMs = (unsigned long)constrain(releaseAfterMs, 250, 10000);
  servoPulseDeadbandUs = constrain(deadbandUs, 0, 30);
  if (!servoQuietReleaseEnabled) {
    commandServoPulse(yawServo, yawServoAttached, headYawPin, lastYawPulseUs, lastYawPulseUs, true);
    commandServoPulse(gimbalLeftServo, gimbalLeftServoAttached, headGimbalLeftPin, lastGimbalLeftPulseUs, lastGimbalLeftPulseUs, true);
    commandServoPulse(gimbalRightServo, gimbalRightServoAttached, headGimbalRightPin, lastGimbalRightPulseUs, lastGimbalRightPulseUs, true);
  } else if (lastServoMotionMs == 0UL) {
    lastServoMotionMs = millis();
  }
  modeText = "servo_quiet_configured";
  return true;
}

bool bx1_config_done() {
  // Home is a logical head pose. The mixer converts pitch/roll to both linkage servos.
  applyHeadPose(yawHomeDeg, logicalPitchHomeDeg, logicalRollHomeDeg);

  // A visible harmless confirmation pulse if the LED bus is ready.
#if BX1_USE_NEOPIXEL
  if (bodyLedReady && zoneMouthStart > 0) {
    applyLedToZone("mouth", "cyan", min(0.15f, bodyLedBrightnessLimit));
  }
#endif
  modeText = "hardware_configured_home";
  return true;
}


void configureHardwareFromJson(const String &json) {
  int yawPin = (int)extractJsonFloat(json, "head_yaw_pin", headYawPin);
  int leftPin = (int)extractJsonFloat(json, "head_gimbal_left_pin", extractJsonFloat(json, "head_pitch_pin", headGimbalLeftPin));
  int rightPin = (int)extractJsonFloat(json, "head_gimbal_right_pin", extractJsonFloat(json, "head_roll_pin", headGimbalRightPin));
  configureServo(yawServo, yawServoAttached, headYawPin, yawPin);
  configureServo(gimbalLeftServo, gimbalLeftServoAttached, headGimbalLeftPin, leftPin);
  configureServo(gimbalRightServo, gimbalRightServoAttached, headGimbalRightPin, rightPin);

  yawMinDeg = extractJsonFloat(json, "head_yaw_min_deg", yawMinDeg);
  yawMaxDeg = extractJsonFloat(json, "head_yaw_max_deg", yawMaxDeg);
  yawHomeDeg = extractJsonFloat(json, "head_yaw_home_deg", yawHomeDeg);
  yawInvert = extractJsonFloat(json, "head_yaw_invert", yawInvert ? 1.0f : 0.0f) > 0.5f;

  gimbalLeftMinDeg = extractJsonFloat(json, "head_gimbal_left_min_deg", gimbalLeftMinDeg);
  gimbalLeftMaxDeg = extractJsonFloat(json, "head_gimbal_left_max_deg", gimbalLeftMaxDeg);
  gimbalLeftHomeDeg = extractJsonFloat(json, "head_gimbal_left_home_deg", gimbalLeftHomeDeg);
  gimbalLeftInvert = extractJsonFloat(json, "head_gimbal_left_invert", gimbalLeftInvert ? 1.0f : 0.0f) > 0.5f;
  gimbalRightMinDeg = extractJsonFloat(json, "head_gimbal_right_min_deg", gimbalRightMinDeg);
  gimbalRightMaxDeg = extractJsonFloat(json, "head_gimbal_right_max_deg", gimbalRightMaxDeg);
  gimbalRightHomeDeg = extractJsonFloat(json, "head_gimbal_right_home_deg", gimbalRightHomeDeg);
  gimbalRightInvert = extractJsonFloat(json, "head_gimbal_right_invert", gimbalRightInvert ? 1.0f : 0.0f) > 0.5f;

  logicalPitchMinDeg = extractJsonFloat(json, "head_pitch_min_deg", logicalPitchMinDeg);
  logicalPitchMaxDeg = extractJsonFloat(json, "head_pitch_max_deg", logicalPitchMaxDeg);
  logicalPitchHomeDeg = extractJsonFloat(json, "head_pitch_home_deg", logicalPitchHomeDeg);
  logicalRollMinDeg = extractJsonFloat(json, "head_roll_min_deg", logicalRollMinDeg);
  logicalRollMaxDeg = extractJsonFloat(json, "head_roll_max_deg", logicalRollMaxDeg);
  logicalRollHomeDeg = extractJsonFloat(json, "head_roll_home_deg", logicalRollHomeDeg);
  pitchMixGain = clampf(extractJsonFloat(json, "head_pitch_gain", pitchMixGain), 0.05f, 5.0f);
  rollMixGain = clampf(extractJsonFloat(json, "head_roll_gain", rollMixGain), 0.05f, 5.0f);
  leftPitchSign = extractJsonFloat(json, "head_left_pitch_sign", leftPitchSign) >= 0 ? 1 : -1;
  rightPitchSign = extractJsonFloat(json, "head_right_pitch_sign", rightPitchSign) >= 0 ? 1 : -1;
  leftRollSign = extractJsonFloat(json, "head_left_roll_sign", leftRollSign) >= 0 ? 1 : -1;
  rightRollSign = extractJsonFloat(json, "head_right_roll_sign", rightRollSign) >= 0 ? 1 : -1;
  servoQuietReleaseEnabled = extractJsonFloat(json, "servo_quiet_release_enabled", servoQuietReleaseEnabled ? 1.0f : 0.0f) > 0.5f;
  servoReleaseAfterMs = (unsigned long)constrain((int)extractJsonFloat(json, "servo_release_after_ms", (float)servoReleaseAfterMs), 250, 10000);
  servoPulseDeadbandUs = constrain((int)extractJsonFloat(json, "servo_pulse_deadband_us", (float)servoPulseDeadbandUs), 0, 30);

  if (yawMaxDeg < yawMinDeg) { float t = yawMaxDeg; yawMaxDeg = yawMinDeg; yawMinDeg = t; }
  if (gimbalLeftMaxDeg < gimbalLeftMinDeg) { float t = gimbalLeftMaxDeg; gimbalLeftMaxDeg = gimbalLeftMinDeg; gimbalLeftMinDeg = t; }
  if (gimbalRightMaxDeg < gimbalRightMinDeg) { float t = gimbalRightMaxDeg; gimbalRightMaxDeg = gimbalRightMinDeg; gimbalRightMinDeg = t; }
  if (logicalPitchMaxDeg < logicalPitchMinDeg) { float t = logicalPitchMaxDeg; logicalPitchMaxDeg = logicalPitchMinDeg; logicalPitchMinDeg = t; }
  if (logicalRollMaxDeg < logicalRollMinDeg) { float t = logicalRollMaxDeg; logicalRollMaxDeg = logicalRollMinDeg; logicalRollMinDeg = t; }
  yawHomeDeg = clampf(yawHomeDeg, yawMinDeg, yawMaxDeg);
  gimbalLeftHomeDeg = clampf(gimbalLeftHomeDeg, gimbalLeftMinDeg, gimbalLeftMaxDeg);
  gimbalRightHomeDeg = clampf(gimbalRightHomeDeg, gimbalRightMinDeg, gimbalRightMaxDeg);
  logicalPitchHomeDeg = clampf(logicalPitchHomeDeg, logicalPitchMinDeg, logicalPitchMaxDeg);
  logicalRollHomeDeg = clampf(logicalRollHomeDeg, logicalRollMinDeg, logicalRollMaxDeg);

#if BX1_USE_NEOPIXEL
  int bodyPin = (int)extractJsonFloat(json, "led_bus_pin", bodyLedPin);
  int bodyCount = (int)extractJsonFloat(json, "led_bus_count", bodyLedCount);
  bodyLedBrightnessLimit = clampf(extractJsonFloat(json, "led_bus_brightness_limit", bodyLedBrightnessLimit), 0.0f, 1.0f);
  configurePixels(bodyPixels, bodyLedReady, bodyLedPin, bodyLedCount, bodyPin, bodyCount);
  zoneMouthStart = (int)extractJsonFloat(json, "zone_mouth_start", zoneMouthStart);
  zoneMouthEnd = (int)extractJsonFloat(json, "zone_mouth_end", zoneMouthEnd);
  zoneLeftEyeStart = (int)extractJsonFloat(json, "zone_left_eye_start", zoneLeftEyeStart);
  zoneLeftEyeEnd = (int)extractJsonFloat(json, "zone_left_eye_end", zoneLeftEyeEnd);
  zoneRightEyeStart = (int)extractJsonFloat(json, "zone_right_eye_start", zoneRightEyeStart);
  zoneRightEyeEnd = (int)extractJsonFloat(json, "zone_right_eye_end", zoneRightEyeEnd);
  zoneChestStart = (int)extractJsonFloat(json, "zone_chest_start", zoneChestStart);
  zoneChestEnd = (int)extractJsonFloat(json, "zone_chest_end", zoneChestEnd);
  zoneStatusStart = (int)extractJsonFloat(json, "zone_status_start", zoneStatusStart);
  zoneStatusEnd = (int)extractJsonFloat(json, "zone_status_end", zoneStatusEnd);

  int eyePin = (int)extractJsonFloat(json, "eyes_led_pin", eyesLedPin);
  int eyeCount = (int)extractJsonFloat(json, "eyes_led_count", eyesLedCount);
  int mouthPin = (int)extractJsonFloat(json, "mouth_led_pin", mouthLedPin);
  int mouthCount = (int)extractJsonFloat(json, "mouth_led_count", mouthLedCount);
  configurePixels(eyesPixels, eyesLedReady, eyesLedPin, eyesLedCount, eyePin, eyeCount);
  configurePixels(mouthPixels, mouthLedReady, mouthLedPin, mouthLedCount, mouthPin, mouthCount);
#endif

  modeText = "hardware_configured";
}

void stopMotion() {
  lastLinearMps = 0.0f;
  lastAngularDps = 0.0f;
  driveUntilMs = 0;
  modeText = "stopped";
#if BX1_ENABLE_DRIVE_OUTPUTS
  // TODO: add real stepper/RS485/driver stop command here.
#endif
}

int servoDegToUs(float deg, float lo, float hi, bool invertAxis) {
  // Servo positions are offsets from the 1500 us neutral pulse. The configured
  // min/max values are genuine travel limits; they must not be stretched across
  // the servo's entire 900..2100 us electrical range. This keeps a ±3 degree
  // bench test physically small instead of turning it into a large horn movement.
  deg = clampf(deg, lo, hi);
  if (invertAxis) deg = -deg;
  int pulseUs = (int)(1500.0f + (deg * 10.0f));
  if (pulseUs < 900) pulseUs = 900;
  if (pulseUs > 2100) pulseUs = 2100;
  return pulseUs;
}

void applyHeadPose(float yawDeg, float pitchDegCommand, float rollDegCommand) {
  lastHeadYawDeg = clampf(yawDeg, yawMinDeg, yawMaxDeg);
  lastHeadPitchDeg = clampf(pitchDegCommand, logicalPitchMinDeg, logicalPitchMaxDeg);
  lastHeadRollDeg = clampf(rollDegCommand, logicalRollMinDeg, logicalRollMaxDeg);

  // Default push-pull geometry: pitch moves the mirrored servos oppositely;
  // roll moves them together. All four signs and both gains are configurable.
  lastGimbalLeftDeg = gimbalLeftHomeDeg
      + (lastHeadPitchDeg * pitchMixGain * (float)leftPitchSign)
      + (lastHeadRollDeg * rollMixGain * (float)leftRollSign);
  lastGimbalRightDeg = gimbalRightHomeDeg
      + (lastHeadPitchDeg * pitchMixGain * (float)rightPitchSign)
      + (lastHeadRollDeg * rollMixGain * (float)rightRollSign);
  lastGimbalLeftDeg = clampf(lastGimbalLeftDeg, gimbalLeftMinDeg, gimbalLeftMaxDeg);
  lastGimbalRightDeg = clampf(lastGimbalRightDeg, gimbalRightMinDeg, gimbalRightMaxDeg);

  int yawPulseUs = servoDegToUs(lastHeadYawDeg, yawMinDeg, yawMaxDeg, yawInvert);
  int leftPulseUs = servoDegToUs(lastGimbalLeftDeg, gimbalLeftMinDeg, gimbalLeftMaxDeg, gimbalLeftInvert);
  int rightPulseUs = servoDegToUs(lastGimbalRightDeg, gimbalRightMinDeg, gimbalRightMaxDeg, gimbalRightInvert);

  commandServoPulse(yawServo, yawServoAttached, headYawPin, yawPulseUs, lastYawPulseUs, false);
  commandServoPulse(gimbalLeftServo, gimbalLeftServoAttached, headGimbalLeftPin, leftPulseUs, lastGimbalLeftPulseUs, false);
  commandServoPulse(gimbalRightServo, gimbalRightServoAttached, headGimbalRightPin, rightPulseUs, lastGimbalRightPulseUs, false);

  modeText = "head_pose_mixed";
}

bool bx1_set_head_pose(float yawDeg, float pitchDegCommand, float rollDegCommand) {
  lastActionType = "set_head_pose_rpc";
  lastCommandMs = millis();
  applyHeadPose(yawDeg, pitchDegCommand, rollDegCommand);
  return yawServoAttached || gimbalLeftServoAttached || gimbalRightServoAttached;
}

bool bx1_test_servo_us(String servoName, int pulseUs) {
  pulseUs = constrain(pulseUs, 1100, 1900);
  lastActionType = "test_servo_us";
  lastCommandMs = millis();
  if (servoName == "head_yaw" || servoName == "yaw") {
    if (!commandServoPulse(yawServo, yawServoAttached, headYawPin, pulseUs, lastYawPulseUs, true)) return false;
  } else if (servoName == "gimbal_left" || servoName == "left") {
    if (!commandServoPulse(gimbalLeftServo, gimbalLeftServoAttached, headGimbalLeftPin, pulseUs, lastGimbalLeftPulseUs, true)) return false;
  } else if (servoName == "gimbal_right" || servoName == "right") {
    if (!commandServoPulse(gimbalRightServo, gimbalRightServoAttached, headGimbalRightPin, pulseUs, lastGimbalRightPulseUs, true)) return false;
  } else {
    return false;
  }
  modeText = "servo_pulse_test";
  return true;
}


int hexNibble(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return 10 + c - 'a';
  if (c >= 'A' && c <= 'F') return 10 + c - 'A';
  return -1;
}

uint32_t colourToPixel(Adafruit_NeoPixel &pixels, const String &colour, float brightness) {
  float scale = clampf(brightness, 0.0f, 1.0f);
  if (colour.length() == 7 && colour.charAt(0) == '#') {
    int n[6];
    for (int i = 0; i < 6; i++) { n[i] = hexNibble(colour.charAt(i + 1)); if (n[i] < 0) return pixels.Color(0, 0, 0); }
    uint8_t r = (uint8_t)((n[0] * 16 + n[1]) * scale);
    uint8_t g = (uint8_t)((n[2] * 16 + n[3]) * scale);
    uint8_t b = (uint8_t)((n[4] * 16 + n[5]) * scale);
    return pixels.Color(r, g, b);
  }
  uint8_t b = (uint8_t)(scale * 255.0f);
  if (colour == "red") return pixels.Color(b, 0, 0);
  if (colour == "green") return pixels.Color(0, b, 0);
  if (colour == "blue") return pixels.Color(0, 0, b);
  if (colour == "white") return pixels.Color(b, b, b);
  if (colour == "amber" || colour == "yellow" || colour == "orange") return pixels.Color(b, b / 2, 0);
  if (colour == "purple") return pixels.Color(b / 2, 0, b);
  if (colour == "cyan") return pixels.Color(0, b, b);
  if (colour == "pink" || colour == "magenta") return pixels.Color(b, 0, b / 2);
  if (colour == "soft_white") return pixels.Color(b, b, max((int)b / 3, 0));
  return pixels.Color(0, 0, 0);
}

void setBodyLedRange(int humanStart, int humanEnd, uint32_t colour) {
#if BX1_USE_NEOPIXEL
  if (!bodyLedReady || humanStart < 1 || humanEnd < humanStart) return;
  int startIdx = constrain(humanStart - 1, 0, bodyLedCount - 1);
  int endIdx = constrain(humanEnd - 1, 0, bodyLedCount - 1);
  for (int i = startIdx; i <= endIdx; i++) bodyPixels.setPixelColor(i, colour);
#endif
}


void applyBodyLedRgbRange(int humanStart, int humanEnd, int red, int green, int blue, float brightness) {
#if BX1_USE_NEOPIXEL
  if (!bodyLedReady) return;
  red = constrain(red, 0, 255);
  green = constrain(green, 0, 255);
  blue = constrain(blue, 0, 255);
  brightness = min(clampf(brightness, 0.0f, 1.0f), bodyLedBrightnessLimit);
  uint8_t r = (uint8_t)((float)red * brightness);
  uint8_t g = (uint8_t)((float)green * brightness);
  uint8_t b = (uint8_t)((float)blue * brightness);
  uint32_t c = bodyPixels.Color(r, g, b);
  setBodyLedRange(humanStart, humanEnd, c);
  bodyPixels.show();
  modeText = "led_range_rgb";
#endif
}


void applyLedToZone(const String &zone, const String &colour, float brightness) {
  lastLedColour = colour;
  lastLedZone = zone;
  lastLedBrightness = clampf(brightness, 0.0f, 1.0f);
  lastLedEffectiveBrightness = lastLedBrightness;
  ledCommandCount++;
#if BX1_USE_NEOPIXEL
  if (bodyLedReady) {
    brightness = min(lastLedBrightness, bodyLedBrightnessLimit);
    lastLedEffectiveBrightness = brightness;
    uint32_t c = colourToPixel(bodyPixels, colour, brightness);
    if (zone == "all" || zone == "body") {
      for (int i = 0; i < bodyLedCount; i++) bodyPixels.setPixelColor(i, c);
    } else if (zone == "mouth") {
      setBodyLedRange(zoneMouthStart, zoneMouthEnd, c);
    } else if (zone == "left_eye") {
      setBodyLedRange(zoneLeftEyeStart, zoneLeftEyeEnd, c);
    } else if (zone == "right_eye") {
      setBodyLedRange(zoneRightEyeStart, zoneRightEyeEnd, c);
    } else if (zone == "eyes" || zone == "eye") {
      setBodyLedRange(zoneLeftEyeStart, zoneLeftEyeEnd, c);
      setBodyLedRange(zoneRightEyeStart, zoneRightEyeEnd, c);
    } else if (zone == "chest") {
      setBodyLedRange(zoneChestStart, zoneChestEnd, c);
    } else if (zone == "status") {
      setBodyLedRange(zoneStatusStart, zoneStatusEnd, c);
    }
    bodyPixels.show();
    modeText = "led_zone";
    return;
  }
#endif
  // Fall back to old separate mouth/eyes objects if v10 bus is not configured.
  applyLedToTarget(zone, colour, brightness);
}

void applyLedToTarget(const String &target, const String &colour, float brightness) {
  lastLedColour = colour;
  lastLedZone = target;
  lastLedBrightness = clampf(brightness, 0.0f, 1.0f);
  lastLedEffectiveBrightness = lastLedBrightness;
  ledCommandCount++;
#if BX1_USE_NEOPIXEL
  uint32_t c = colourToPixel(eyesPixels, colour, lastLedEffectiveBrightness);

  if ((target == "mouth" || target == "all") && mouthLedReady) {
    for (int i = 0; i < mouthLedCount; i++) mouthPixels.setPixelColor(i, c);
    mouthPixels.show();
  }
  if ((target == "eyes" || target == "eye" || target == "all" || target.length() == 0) && eyesLedReady) {
    for (int i = 0; i < eyesLedCount; i++) eyesPixels.setPixelColor(i, c);
    eyesPixels.show();
  }
#endif
  modeText = "led";
}

void applyEyeLed(const String &colour, float brightness) {
  applyLedToTarget("eyes", colour, brightness);
}

void playToneAck(float durationS) {
#if BUZZER_PIN >= 0
  tone(BUZZER_PIN, 1200, (unsigned long)(durationS * 1000.0f));
#endif
  modeText = "tone";
}

void applyDrive(float linearMps, float angularDps, float durationS) {
  if (!safetyOk()) {
    stopMotion();
    modeText = "drive_blocked";
    return;
  }
  lastLinearMps = clampf(linearMps, -0.25f, 0.25f);
  lastAngularDps = clampf(angularDps, -60.0f, 60.0f);
  durationS = clampf(durationS, 0.05f, 1.5f);
  driveUntilMs = millis() + (unsigned long)(durationS * 1000.0f);
  modeText = "drive_stub";
#if BX1_ENABLE_DRIVE_OUTPUTS
  // TODO: replace this with your real motor protocol.
  // For closed-loop RS485 steppers, this is where target speed/position packets would be sent.
#endif
}

bool bx1_set_led_zone(String zone, String colour, float brightness) {
  lastActionType = "set_led_zone_rpc";
  lastCommandMs = millis();
  applyLedToZone(zone, colour, brightness);
  return bodyLedReady || mouthLedReady || eyesLedReady;
}


void processActionJson(const String &json) {
  String type = extractJsonString(json, "type", "");
  lastActionType = type;
  lastCommandMs = millis();
  if (maintenanceMode && type == "drive") {
    stopMotion();
    modeText = "maintenance_drive_blocked";
    return;
  }

  if (type == "stop_motion") {
    stopMotion();
    return;
  }

  if (type == "configure_hardware" || type == "configure_hardware_v2") {
    configureHardwareFromJson(json);
    return;
  }

  if (type == "set_head_pose") {
    float yaw = extractJsonFloat(json, "yaw_deg", lastHeadYawDeg);
    float pitch = extractJsonFloat(json, "pitch_deg", lastHeadPitchDeg);
    float roll = extractJsonFloat(json, "roll_deg", extractJsonFloat(json, "tilt_deg", lastHeadRollDeg));
    applyHeadPose(yaw, pitch, roll);
    return;
  }


  if (type == "set_led_range" || type == "set_led_pixel" || type == "paint_led") {
    int startLed = (int)extractJsonFloat(json, "start_led", extractJsonFloat(json, "led", 1));
    int endLed = (int)extractJsonFloat(json, "end_led", startLed);
    int red = (int)extractJsonFloat(json, "r", extractJsonFloat(json, "red", 0));
    int green = (int)extractJsonFloat(json, "g", extractJsonFloat(json, "green", 0));
    int blue = (int)extractJsonFloat(json, "b", extractJsonFloat(json, "blue", 0));
    float brightness = extractJsonFloat(json, "brightness", 0.25f);
    applyBodyLedRgbRange(startLed, endLed, red, green, blue, brightness);
    return;
  }

  if (type == "set_led_zone") {
    String zone = extractJsonString(json, "zone", "mouth");
    String colour = extractJsonString(json, "colour", extractJsonString(json, "color", "off"));
    float brightness = extractJsonFloat(json, "brightness", 0.4f);
    applyLedToZone(zone, colour, brightness);
    String secondary = extractJsonString(json, "secondary_zone", "");
    if (secondary.length() > 0) applyLedToZone(secondary, colour, brightness);
    return;
  }

  if (type == "set_eye_led" || type == "set_led" || type == "set_device_led") {
    String target = extractJsonString(json, "target", extractJsonString(json, "device", "eyes"));
    String colour = extractJsonString(json, "colour", extractJsonString(json, "color", "off"));
    float brightness = extractJsonFloat(json, "brightness", 0.4f);
    applyLedToTarget(target, colour, brightness);
    return;
  }

  if (type == "play_tone") {
    float duration = extractJsonFloat(json, "duration_s", 0.25f);
    playToneAck(duration);
    return;
  }

  if (type == "drive") {
    float linear = extractJsonFloat(json, "linear_mps", 0.0f);
    float angular = extractJsonFloat(json, "angular_dps", 0.0f);
    float duration = extractJsonFloat(json, "duration_s", 0.5f);
    applyDrive(linear, angular, duration);
    return;
  }

  modeText = "unknown_action";
}

// ---------------- Bridge RPC functions ----------------
String bx1_get_status() {
  bool ok = safetyOk();
  bool fallen = fabs(pitchDeg) > 45.0f || fabs(rollDeg) > 45.0f;
  String json = "{";
  json += "\"mcu_ok\":true,";
  json += "\"firmware_version\":\"" + String(BX1_FIRMWARE_VERSION) + "\",";
  json += "\"protocol_version\":\"" + String(BX1_PROTOCOL_VERSION) + "\",";
  json += "\"build_id\":\"" + jsonEscape(String(BX1_BUILD_ID)) + "\",";
  json += "\"heartbeat_sequence\":" + String(heartbeatSequence) + ",";
  json += "\"maintenance_mode\":" + String(maintenanceMode ? "true" : "false") + ",";
  json += "\"drive_outputs_enabled\":" + String(BX1_ENABLE_DRIVE_OUTPUTS ? "true" : "false") + ",";
  json += "\"imu_ok\":" + String(imuOk ? "true" : "false") + ",";
  json += "\"imu_error\":\"" + jsonEscape(imuError) + "\",";
  json += "\"imu_source\":\"" + jsonEscape(imuSource) + "\",";
  json += "\"imu_bus\":\"" + jsonEscape(imuBus) + "\",";
  json += "\"imu_address\":\"" + jsonEscape(imuAddress) + "\",";
  json += "\"imu_read_failures\":" + String(imuReadFailures) + ",";
  json += "\"imu_last_update_age_ms\":" + String(lastImuUpdateMs == 0 ? 0 : millis() - lastImuUpdateMs) + ",";
  json += "\"control_owner\":\"linux_python\",";
  json += "\"mcu_runtime\":\"arduino_router_shim\",";
  json += "\"hardware_init_started\":" + String(hardwareInitStarted ? "true" : "false") + ",";
  json += "\"hardware_init_complete\":" + String(hardwareInitComplete ? "true" : "false") + ",";
  json += "\"safety_ok\":" + String(ok ? "true" : "false") + ",";
  json += "\"fallen\":" + String(fallen ? "true" : "false") + ",";
  json += "\"estop\":" + String(estopLatched ? "true" : "false") + ",";
  json += "\"mode\":\"" + jsonEscape(modeText) + "\",";
  json += "\"pitch_deg\":" + String(pitchDeg, 2) + ",";
  json += "\"roll_deg\":" + String(rollDeg, 2) + ",";
  json += "\"accel_g\":{";
  json += "\"x\":" + String(ax, 4) + ",";
  json += "\"y\":" + String(ay, 4) + ",";
  json += "\"z\":" + String(az, 4) + "},";
  json += "\"gyro_dps\":{";
  json += "\"roll\":" + String(gyroRoll, 2) + ",";
  json += "\"pitch\":" + String(gyroPitch, 2) + ",";
  json += "\"yaw\":" + String(gyroYaw, 2) + "},";
  json += "\"last_action\":\"" + jsonEscape(lastActionType) + "\",";
  json += "\"head_yaw_deg\":" + String(lastHeadYawDeg, 1) + ",";
  json += "\"head_pitch_deg\":" + String(lastHeadPitchDeg, 1) + ",";
  json += "\"head_roll_deg\":" + String(lastHeadRollDeg, 1) + ",";
  json += "\"head_servo_pins\":{\"yaw\":" + String(headYawPin) + ",\"gimbal_left\":" + String(headGimbalLeftPin) + ",\"gimbal_right\":" + String(headGimbalRightPin) + ",\"pitch\":" + String(headGimbalLeftPin) + ",\"roll\":" + String(headGimbalRightPin) + "},";
  json += "\"head_servo_attached\":{\"yaw\":" + String(yawServoAttached ? "true" : "false") + ",\"gimbal_left\":" + String(gimbalLeftServoAttached ? "true" : "false") + ",\"gimbal_right\":" + String(gimbalRightServoAttached ? "true" : "false") + "},";
  json += "\"head_servo_pulse_us\":{\"yaw\":" + String(lastYawPulseUs) + ",\"gimbal_left\":" + String(lastGimbalLeftPulseUs) + ",\"gimbal_right\":" + String(lastGimbalRightPulseUs) + "},";
  json += "\"head_servo_attach_error\":\"" + jsonEscape(lastServoAttachError) + "\",";
  json += "\"servo_quiet\":{";
  json += "\"enabled\":" + String(servoQuietReleaseEnabled ? "true" : "false") + ",";
  json += "\"release_after_ms\":" + String(servoReleaseAfterMs) + ",";
  json += "\"pulse_deadband_us\":" + String(servoPulseDeadbandUs) + ",";
  json += "\"released\":" + String(servoOutputsReleased ? "true" : "false") + ",";
  json += "\"release_count\":" + String(servoReleaseCount) + ",";
  json += "\"last_motion_age_ms\":" + String(lastServoMotionMs == 0UL ? 0UL : millis() - lastServoMotionMs) + "},";
  json += "\"head_gimbal_targets_deg\":{\"left\":" + String(lastGimbalLeftDeg, 1) + ",\"right\":" + String(lastGimbalRightDeg, 1) + "},";
  json += "\"head_mixer\":{\"pitch_gain\":" + String(pitchMixGain, 3) + ",\"roll_gain\":" + String(rollMixGain, 3) + ",\"left_pitch_sign\":" + String(leftPitchSign) + ",\"right_pitch_sign\":" + String(rightPitchSign) + ",\"left_roll_sign\":" + String(leftRollSign) + ",\"right_roll_sign\":" + String(rightRollSign) + "},";
  json += "\"led_pins\":{\"eyes\":" + String(eyesLedPin) + ",\"mouth\":" + String(mouthLedPin) + ",\"bus\":" + String(bodyLedPin) + "},";
  json += "\"led_bus\":{\"pin\":" + String(bodyLedPin) + ",\"count\":" + String(bodyLedCount) + ",\"ready\":" + String(bodyLedReady ? "true" : "false") + ",\"brightness_limit\":" + String(bodyLedBrightnessLimit, 3) + "},";
  json += "\"eye_colour\":\"" + jsonEscape(lastLedColour) + "\",";
  json += "\"last_led_zone\":\"" + jsonEscape(lastLedZone) + "\",";
  json += "\"last_led_brightness\":" + String(lastLedBrightness, 3) + ",";
  json += "\"last_led_effective_brightness\":" + String(lastLedEffectiveBrightness, 3) + ",";
  json += "\"led_command_count\":" + String(ledCommandCount) + ",";
  json += "\"drive_linear_mps\":" + String(lastLinearMps, 3) + ",";
  json += "\"drive_angular_dps\":" + String(lastAngularDps, 2) + ",";
  json += "\"last_command_age_ms\":" + String(lastCommandMs == 0 ? 0 : millis() - lastCommandMs) + ",";
  json += "\"loop_period_ms\":20,";
  json += "\"uptime_ms\":" + String(millis());
  json += "}";
  return json;
}

bool bx1_set_command(String actionJson) {
  pendingActionJson = actionJson;
  actionPending = true;
  return true;
}

bool bx1_set_estop(bool enabled) {
  estopLatched = enabled;
  if (enabled) stopMotion();
  return true;
}

String bx1_ping() {
  return String("BX1_PONG:") + String(heartbeatSequence);
}

bool bx1_set_maintenance_mode(bool enabled) {
  maintenanceMode = enabled;
  if (enabled) {
    stopMotion();
    modeText = "maintenance";
  } else {
    modeText = imuOk ? "ready" : "ready_no_imu";
  }
  return true;
}


void processSerialBridge() {
  while (Serial.available() > 0) {
    char ch = (char)Serial.read();
    if (ch == '\r') continue;
    if (ch == '\n') {
      String line = serialBridgeBuffer;
      serialBridgeBuffer = "";
      line.trim();
      if (line.length() == 0) continue;

      if (line == "BX1_STATUS") {
        Serial.print("BX1_STATUS:");
        Serial.println(bx1_get_status());
        continue;
      }

      if (line.startsWith("BX1_ACTION:")) {
        String action = line.substring(String("BX1_ACTION:").length());
        processActionJson(action);
        Serial.println("BX1_OK:1");
        continue;
      }

      if (line.startsWith("BX1_ESTOP:")) {
        String val = line.substring(String("BX1_ESTOP:").length());
        val.trim();
        estopLatched = (val == "1" || val == "true" || val == "on");
        if (estopLatched) stopMotion();
        Serial.println("BX1_OK:1");
        continue;
      }

      // Convenience: allow a raw JSON action line from quick terminal tests.
      if (line.startsWith("{")) {
        processActionJson(line);
        Serial.println("BX1_OK:1");
        continue;
      }

      Serial.print("BX1_ERR:unknown_serial_command:");
      Serial.println(line);
    } else {
      serialBridgeBuffer += ch;
      if (serialBridgeBuffer.length() > 1200) {
        serialBridgeBuffer = "";
        Serial.println("BX1_ERR:serial_line_too_long");
      }
    }
  }
}

void setup() {
  // RouterBridge must be the first subsystem brought online. Hardware
  // discovery is intentionally deferred to loop() so a missing IMU, servo
  // library problem or LED configuration can never hide the MCU from Linux.
  Bridge.begin();
  Bridge.provide("bx1_get_status", bx1_get_status);
  Bridge.provide("bx1_set_command", bx1_set_command);
  Bridge.provide("bx1_set_estop", bx1_set_estop);
  Bridge.provide("bx1_ping", bx1_ping);
  Bridge.provide("bx1_set_maintenance_mode", bx1_set_maintenance_mode);
  Bridge.provide("bx1_config_led_bus", bx1_config_led_bus);
  Bridge.provide("bx1_config_led_zone", bx1_config_led_zone);
  Bridge.provide("bx1_config_servo", bx1_config_servo);
  Bridge.provide("bx1_config_head_limits", bx1_config_head_limits);
  Bridge.provide("bx1_config_head_mix", bx1_config_head_mix);
  Bridge.provide("bx1_config_servo_quiet", bx1_config_servo_quiet);
  Bridge.provide("bx1_config_done", bx1_config_done);
  Bridge.provide("bx1_set_head_pose", bx1_set_head_pose);
  Bridge.provide("bx1_test_servo_us", bx1_test_servo_us);
  Bridge.provide("bx1_set_led_zone", bx1_set_led_zone);
  Bridge.provide("bx1_i2c_scan", bx1_i2c_scan);

  modeText = "bridge_ready";
  Serial.begin(115200);
#if ESTOP_INPUT_PIN >= 0
  pinMode(ESTOP_INPUT_PIN, INPUT_PULLUP);
#endif
#if BUZZER_PIN >= 0
  pinMode(BUZZER_PIN, OUTPUT);
#endif
}

void initialiseHardwareAfterBridge() {
  if (hardwareInitComplete || hardwareInitStarted) return;
  hardwareInitStarted = true;
  modeText = "hardware_initialising";

  configureServo(yawServo, yawServoAttached, headYawPin, HEAD_YAW_SERVO_PIN);
  configureServo(gimbalLeftServo, gimbalLeftServoAttached, headGimbalLeftPin, HEAD_GIMBAL_LEFT_SERVO_PIN);
  configureServo(gimbalRightServo, gimbalRightServoAttached, headGimbalRightPin, HEAD_GIMBAL_RIGHT_SERVO_PIN);
#if BX1_USE_NEOPIXEL
  configurePixels(eyesPixels, eyesLedReady, eyesLedPin, eyesLedCount, -1, eyesLedCount);
  configurePixels(mouthPixels, mouthLedReady, mouthLedPin, mouthLedCount, -1, mouthLedCount);
  configurePixels(bodyPixels, bodyLedReady, bodyLedPin, bodyLedCount, -1, bodyLedCount);
#endif

  initialiseMovementImu();
  hardwareInitComplete = true;
  if (!maintenanceMode) modeText = imuOk ? "ready" : "ready_no_imu";
}

void loop() {
  heartbeatSequence++;

  // Give RouterBridge time to register and answer Linux before touching I2C.
  if (!hardwareInitComplete && millis() >= 1000UL) initialiseHardwareAfterBridge();

  processSerialBridge();
  updateImu();

  if (actionPending) {
    noInterrupts();
    String action = pendingActionJson;
    actionPending = false;
    interrupts();
    processActionJson(action);
  }

  if (driveUntilMs > 0 && millis() > driveUntilMs) {
    stopMotion();
  }

  if (!safetyOk() && driveUntilMs > 0) {
    stopMotion();
    modeText = "safety_stop";
  }

  releaseHeadServosIfQuiet();
  delay(20); // 50 Hz body service loop
}
