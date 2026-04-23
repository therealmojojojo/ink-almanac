// Sensor probe: scan easyC/I2C bus, identify attached devices, sample any PIR
// over a 30-second window so the operator can confirm wake events fire.
//
// Built via `pio run -e sensor_probe -t upload` then `pio device monitor`.
// No HA dependency — pure serial diagnostic.

#if defined(ARDUINO) && defined(SENSOR_PROBE)

#include <Arduino.h>
#include <Inkplate.h>
#include <Wire.h>

Inkplate display(INKPLATE_3BIT);

// LSM6DSO / LSM6DSOX WHO_AM_I register (0x0F) returns 0x6C (DSO) or 0x6C (DSOX).
// Primary I2C address 0x6A (SA0=GND), alternate 0x6B (SA0=VDD).
static constexpr uint8_t kLsmReg_WhoAmI = 0x0F;
static constexpr uint8_t kLsmWhoAmIExpected = 0x6C;

struct I2cHit {
  uint8_t addr;
  const char* guess;
};

static const char* guessDevice(uint8_t addr) {
  switch (addr) {
    case 0x22: return "Inkplate IO expander (internal)";
    case 0x23: return "BH1750 light sensor";
    case 0x29: return "VL53L0X / TSL2591";
    case 0x39: return "APDS-9960 / TSL2561";
    case 0x3C: case 0x3D: return "SSD1306 OLED";
    case 0x40: return "INA219 / HTU21 / Si7021";
    case 0x44: case 0x45: return "SHT3x temp/humidity";
    case 0x48: case 0x49: case 0x4A: case 0x4B: return "ADS1x15 / TMP102";
    case 0x50: return "EEPROM (Inkplate internal)";
    case 0x5A: return "MLX90614 IR / MPR121 touch";
    case 0x5C: return "AM2320";
    case 0x62: return "AK9753 digital-output PIR (I2C)";
    case 0x63: return "AK9754 PIR variant";
    case 0x68: case 0x69: return "MPU6050 / DS3231 / ICM-20948";
    case 0x6A: case 0x6B: return "LSM6DS* IMU (LSM6DSO / LSM6DSOX / LSM6DSL)";
    case 0x76: case 0x77: return "BME280 / BMP280 / BME680";
    default: return "unknown";
  }
}

static uint8_t readReg(uint8_t addr, uint8_t reg) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return 0xFF;
  Wire.requestFrom((int)addr, 1);
  return Wire.available() ? Wire.read() : 0xFF;
}

void setup() {
  Serial.begin(115200);
  delay(800);
  Serial.println();
  Serial.println("========================================");
  Serial.println("  Inkplate sensor probe (easyC / I2C) v3");
  Serial.printf ("  build: %s %s\n", __DATE__, __TIME__);
  Serial.println("========================================");

  display.begin();  // initializes Wire for easyC at default pins
  Wire.setClock(100000);

  // --- Pass 0: explicitly probe every AK9753 variant address ------------
  // AK9753 datasheet says factory-default is 0x64; variants exist at 0x62,
  // 0x63, 0x65. Write-then-read WIA1 (0x00): healthy part returns 0x48.
  Serial.println("[probe] explicit AK9753 check @ 0x62, 0x63, 0x64, 0x65:");
  for (uint8_t addr : {0x62, 0x63, 0x64, 0x65}) {
    Wire.beginTransmission(addr);
    uint8_t end_rc = Wire.endTransmission();
    Serial.printf("[probe]   0x%02X: endTransmission=%u %s\n",
                  addr, end_rc,
                  end_rc == 0 ? "(ACK)" :
                  end_rc == 2 ? "(NACK on addr — no device)" :
                  end_rc == 3 ? "(NACK on data)" :
                  end_rc == 5 ? "(timeout)" : "(err)");
    if (end_rc == 0) {
      uint8_t wia1 = readReg(addr, 0x00);
      Serial.printf("[probe]   0x%02X WIA1=0x%02X (AK9753 expects 0x48)\n", addr, wia1);
    }
  }

  // --- Pass 1: scan the whole 7-bit address range -----------------------
  Serial.println("[probe] full-range scan 0x01..0x7F...");
  I2cHit hits[32];
  size_t n = 0;
  for (uint8_t addr = 0x01; addr <= 0x7F && n < 32; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      hits[n++] = {addr, guessDevice(addr)};
      Serial.printf("[probe]   found 0x%02X — %s\n", addr, guessDevice(addr));
    }
  }
  if (n == 0) {
    Serial.println("[probe]   NO devices responded. Check easyC cable orientation and power.");
  }

  // --- Pass 2: identify any LSM6DS* by WHO_AM_I + enable the accelerometer.
  // The accel is OFF at power-on; OUTX_*_A returns 0 until CTRL1_XL is set.
  for (uint8_t addr : {0x6A, 0x6B}) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() != 0) continue;
    uint8_t who = readReg(addr, kLsmReg_WhoAmI);
    Serial.printf("[probe] LSM6DS* @ 0x%02X: WHO_AM_I=0x%02X (expected 0x%02X) → %s\n",
                  addr, who, kLsmWhoAmIExpected,
                  who == kLsmWhoAmIExpected ? "OK ✓" : "MISMATCH");
    if (who == kLsmWhoAmIExpected) {
      // CTRL1_XL (0x10) = 0x60 → accel ODR 416 Hz, ±2 g, LPF1.
      Wire.beginTransmission(addr);
      Wire.write(0x10);
      Wire.write(0x60);
      if (Wire.endTransmission() == 0) {
        Serial.println("[probe]   accel enabled (416 Hz, ±2 g)");
      }
    }
  }

  // --- Pass 3: sample AK9753 status register if present -----------------
  for (uint8_t addr : {0x62, 0x63, 0x64}) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() != 0) continue;
    uint8_t who = readReg(addr, 0x00);  // AK975x WIA1 register
    Serial.printf("[probe] AK975x? @ 0x%02X: WIA1=0x%02X (AK9753 returns 0x48)\n", addr, who);
  }

  Serial.println();
  Serial.println("[probe] sampling all detected devices every 500ms — move in front of");
  Serial.println("[probe] the PIR and tap/rotate the IMU to see values change.");
  Serial.println();
}

void loop() {
  // Poll LSM6DSO accelerometer raw output to prove the IMU is alive.
  for (uint8_t addr : {0x6A, 0x6B}) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() != 0) continue;
    uint8_t who = readReg(addr, kLsmReg_WhoAmI);
    if (who != kLsmWhoAmIExpected) continue;
    // OUTX_L_A = 0x28 — accelerometer low byte
    int16_t ax = (int16_t)(readReg(addr, 0x29) << 8 | readReg(addr, 0x28));
    int16_t ay = (int16_t)(readReg(addr, 0x2B) << 8 | readReg(addr, 0x2A));
    int16_t az = (int16_t)(readReg(addr, 0x2D) << 8 | readReg(addr, 0x2C));
    Serial.printf("[imu  @0x%02X] ax=%6d ay=%6d az=%6d\n", addr, ax, ay, az);
  }

  // Poll AK9753 IR channels (IR1..IR4 at 0x04..0x0B, little-endian).
  for (uint8_t addr : {0x62, 0x63}) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() != 0) continue;
    int16_t ir1 = (int16_t)(readReg(addr, 0x05) << 8 | readReg(addr, 0x04));
    int16_t ir2 = (int16_t)(readReg(addr, 0x07) << 8 | readReg(addr, 0x06));
    int16_t ir3 = (int16_t)(readReg(addr, 0x09) << 8 | readReg(addr, 0x08));
    int16_t ir4 = (int16_t)(readReg(addr, 0x0B) << 8 | readReg(addr, 0x0A));
    Serial.printf("[pir  @0x%02X] ir1=%6d ir2=%6d ir3=%6d ir4=%6d\n", addr, ir1, ir2, ir3, ir4);
  }

  delay(500);
}

#endif  // ARDUINO && SENSOR_PROBE
