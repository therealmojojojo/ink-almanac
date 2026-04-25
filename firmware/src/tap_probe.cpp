// Tap probe: configure LSM6DS3 INT1 per firmware/docs/gestures.md "Wiring",
// then watch GPIO 36 transitions and print TAP_SRC on each falling edge.
//
// Built via `pio run -e tap_probe -t upload` then read serial.
// Verifies the INT1 → IO36 solder joint, polarity, and open-drain config
// without needing deep sleep.
//
// Expected behavior:
//   * Idle: GPIO 36 = HIGH (held by R41 pull-up to 3V3).
//   * Tap the breakout (or its mounting surface) → INT1 sinks LOW briefly,
//     then releases to high-Z, R41 restores HIGH.
//   * Each falling edge prints TAP_SRC bits so we know which axis fired.

#if defined(ARDUINO) && defined(TAP_PROBE)

#include <Arduino.h>
#include <Inkplate.h>
#include <Wire.h>

Inkplate display(INKPLATE_3BIT);

constexpr uint8_t kAddr = 0x6B;
constexpr uint8_t kInt1Pin = 36;

// LSM6DS3 register addresses (datasheet DM00133076, table 19).
constexpr uint8_t REG_WHO_AM_I    = 0x0F;
constexpr uint8_t REG_TAP_SRC     = 0x1C;
constexpr uint8_t REG_CTRL1_XL    = 0x10;
constexpr uint8_t REG_CTRL3_C     = 0x12;
constexpr uint8_t REG_TAP_CFG     = 0x58;
constexpr uint8_t REG_TAP_THS_6D  = 0x59;
constexpr uint8_t REG_INT_DUR2    = 0x5A;
constexpr uint8_t REG_WAKE_UP_THS = 0x5B;
constexpr uint8_t REG_MD1_CFG     = 0x5E;

static void writeReg(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(kAddr);
  Wire.write(reg);
  Wire.write(val);
  Wire.endTransmission();
}

static uint8_t readReg(uint8_t reg) {
  Wire.beginTransmission(kAddr);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return 0xFF;
  Wire.requestFrom((int)kAddr, 1);
  return Wire.available() ? Wire.read() : 0xFF;
}

void setup() {
  Serial.begin(115200);
  delay(800);
  Serial.println();
  Serial.println("========================================");
  Serial.println("  Inkplate tap-probe (INT1 -> GPIO 36)");
  Serial.printf ("  build: %s %s\n", __DATE__, __TIME__);
  Serial.println("========================================");

  display.begin();
  Wire.setClock(100000);

  uint8_t who = readReg(REG_WHO_AM_I);
  Serial.printf("[tap] WHO_AM_I @ 0x%02X = 0x%02X (expect 0x6C) %s\n",
                kAddr, who, who == 0x6C ? "OK" : "MISMATCH");
  if (who != 0x6C) {
    Serial.println("[tap] sensor not responding; aborting.");
    return;
  }

  // Per gestures.md "Wiring":
  //   CTRL3_C    = 0x34 -> IF_INC | PP_OD (open-drain) | H_LACTIVE (active-low)
  //   CTRL1_XL   = 0x60 -> accel ODR=416Hz, +/-2g (required to power tap engine)
  //   TAP_CFG    = 0x8E -> INTERRUPTS_ENABLE + X/Y/Z tap (bench test allows any
  //                        axis; production firmware narrows to Z-only via 0x82)
  //   TAP_THS_6D = 0x08 -> ~500 mg threshold
  //   INT_DUR2   = 0x7F -> generous DUR/QUIET/SHOCK windows
  //   WAKE_UP_THS= 0x80 -> SINGLE_DOUBLE_TAP=1 (enables double-tap recognition)
  //   MD1_CFG    = 0x48 -> route INT1_SINGLE_TAP | INT1_DOUBLE_TAP to INT1
  writeReg(REG_CTRL3_C,     0x34);
  writeReg(REG_CTRL1_XL,    0x60);
  writeReg(REG_TAP_CFG,     0x8E);
  writeReg(REG_TAP_THS_6D,  0x08);
  writeReg(REG_INT_DUR2,    0x7F);
  writeReg(REG_WAKE_UP_THS, 0x80);
  writeReg(REG_MD1_CFG,     0x48);

  // Read back to confirm writes stuck (not strictly needed but cheap).
  Serial.printf("[tap] CTRL3_C    = 0x%02X (expect 0x34)\n", readReg(REG_CTRL3_C));
  Serial.printf("[tap] TAP_CFG    = 0x%02X (expect 0x8E)\n", readReg(REG_TAP_CFG));
  Serial.printf("[tap] MD1_CFG    = 0x%02X (expect 0x48)\n", readReg(REG_MD1_CFG));

  pinMode(kInt1Pin, INPUT);  // R41 holds it high; no internal pull needed.

  Serial.println();
  Serial.println("[tap] ready. Tap the breakout. Expect:");
  Serial.println("[tap]   idle    -> GPIO36 = 1");
  Serial.println("[tap]   on tap  -> GPIO36 briefly = 0, TAP_SRC bits set");
  Serial.println();

  // Print initial idle state.
  Serial.printf("[tap] idle GPIO36 = %d %s\n",
                digitalRead(kInt1Pin),
                digitalRead(kInt1Pin) == HIGH ? "(HIGH - good, R41 pull-up working)"
                                              : "(LOW - check wiring / polarity)");
}

void loop() {
  static int last = -1;
  static uint32_t last_change_ms = 0;
  int now = digitalRead(kInt1Pin);
  if (now != last) {
    uint32_t t = millis();
    uint32_t since = (last_change_ms > 0) ? (t - last_change_ms) : 0;
    if (now == LOW) {
      uint8_t src = readReg(REG_TAP_SRC);
      Serial.printf("[tap] %lums  GPIO36 -> LOW   TAP_SRC=0x%02X  %s%s%s%s%s%s\n",
                    (unsigned long)t, src,
                    (src & 0x40) ? "TAP_IA "      : "",
                    (src & 0x20) ? "SINGLE "      : "",
                    (src & 0x10) ? "DOUBLE "      : "",
                    (src & 0x08) ? "TAP_SIGN "    : "",
                    (src & 0x04) ? "X "           : "",
                    (src & 0x02) ? "Y "           : "");
    } else {
      Serial.printf("[tap] %lums  GPIO36 -> HIGH  (low pulse was ~%lums)\n",
                    (unsigned long)t, (unsigned long)since);
    }
    last = now;
    last_change_ms = t;
  }
  delay(2);  // INT1 pulse is short (SHOCK duration, tens of ms); 2ms catches it.
}

#endif  // ARDUINO && TAP_PROBE
