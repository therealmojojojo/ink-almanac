// EPD power-supply probe — diagnose TPS65186 fault state after a "panel
// frozen on a stale image" incident.
//
// Built via:
//     pio run -e epd_probe -t upload && pio device monitor -e epd_probe
//
// The probe is a one-shot: it runs in setup(), prints everything to serial,
// then sits idle in loop() so the operator can scroll back through the
// output. Re-press RESET to run again.
//
// What it does, in order:
//
//   Stage A  Initialize the Inkplate library so the internal IO expander
//            and the TPS65186 driver are bound. Scan the I2C bus and
//            confirm the PMIC responds at 0x48.
//   Stage B  Dump TPS65186 register state AS FOUND — without poking
//            anything. Includes PWR_GOOD (0x0F), the sticky interrupt
//            registers INT1/INT2 (0x07, 0x08), ENABLE (0x01), TMST_VALUE
//            (0x00, thermal), and REVID (0x10, sanity check).
//   Stage C  Dump MCP23017 GPIO state on the internal expander (0x20).
//            Decodes the WAKEUP/PWRUP/VCOM pin levels — these are how
//            the library controls the PMIC, and a wrong state here can
//            wedge powerUp without any actual silicon fault.
//   Stage D  First recovery attempt: call einkOn() exactly once and
//            report success/failure + the resulting PWR_GOOD byte.
//   Stage E  Soft recovery (matches the #297 hypothesis):
//            einkOff() -> 2 s delay -> einkOn(). Re-dump registers.
//   Stage F  Harder recovery: WAKEUP low for 500 ms via direct expander
//            writes -> WAKEUP high -> einkOn(). Re-dump.
//   Stage G  Hardest software recovery: rewrite UPSEQ0/DWNSEQ0 from
//            scratch (full sequencer re-init) and einkOn(). Re-dump.
//   Stage H  Functional test: if einkOn succeeded at any point, draw a
//            small black rect via partialUpdate(true) and report the
//            returned cycle count. cycles > 0 means the panel really
//            updated, not just that the library lied.
//
// Each stage prints a one-line verdict at the end so the operator can
// skim the output even on a tiny terminal.
//
// The PMIC register decode below is sourced from the TI TPS65186 datasheet
// (Rev. C). Bit positions are TI's; names match the datasheet column
// "Register Description". The Soldered library only #defines a subset;
// we hit the rest via raw Wire.

#if defined(ARDUINO) && defined(EPD_PROBE)

#include <Arduino.h>
#include <Inkplate.h>
#include <Wire.h>

Inkplate display(INKPLATE_3BIT);

// --- Constants -------------------------------------------------------------
// TPS65186 7-bit I2C address.
static constexpr uint8_t kTpsAddr = 0x48;

// MCP23017 internal expander address (per Inkplate10/pins.h).
static constexpr uint8_t kExpAddr = 0x20;

// TPS65186 register map (TI datasheet).
static constexpr uint8_t kRegTmstValue = 0x00;
static constexpr uint8_t kRegEnable    = 0x01;
static constexpr uint8_t kRegVadj      = 0x02;
static constexpr uint8_t kRegVcomL     = 0x03;
static constexpr uint8_t kRegVcomH     = 0x04;
static constexpr uint8_t kRegIntEn1    = 0x05;
static constexpr uint8_t kRegIntEn2    = 0x06;
static constexpr uint8_t kRegInt1      = 0x07;
static constexpr uint8_t kRegInt2      = 0x08;
static constexpr uint8_t kRegUpSeq0    = 0x09;
static constexpr uint8_t kRegUpSeq1    = 0x0A;
static constexpr uint8_t kRegDwnSeq0   = 0x0B;
static constexpr uint8_t kRegDwnSeq1   = 0x0C;
static constexpr uint8_t kRegTmst1     = 0x0D;
static constexpr uint8_t kRegTmst2     = 0x0E;
static constexpr uint8_t kRegPwrGood   = 0x0F;
static constexpr uint8_t kRegRevId     = 0x10;

// PWR_GOOD healthy value (all five rails up: VB / VDDH / VPOS / VNEG / VEE).
static constexpr uint8_t kPwrGoodOk = 0xFA;

// MCP23017 register map (Microchip datasheet, IOCON.BANK=0 default).
static constexpr uint8_t kMcpGpioA   = 0x12;
static constexpr uint8_t kMcpGpioB   = 0x13;
static constexpr uint8_t kMcpIoDirA  = 0x00;
static constexpr uint8_t kMcpIoDirB  = 0x01;

// Pin assignments on the internal expander (per Inkplate10/pins.h).
static constexpr uint8_t kPinWakeup = 3;
static constexpr uint8_t kPinPwrup  = 4;
static constexpr uint8_t kPinVcom   = 5;

// --- Low-level I2C helpers — bypass the library so we see ground truth ----

// Read one byte from `reg` of the device at `addr`. Returns 0xFF on bus
// error. `*ok` (if non-null) is set to false on bus error so the caller
// can distinguish a real 0xFF from a transport error.
static uint8_t readReg(uint8_t addr, uint8_t reg, bool* ok = nullptr) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  uint8_t end_rc = Wire.endTransmission(false);  // repeated start
  if (end_rc != 0) {
    if (ok) *ok = false;
    return 0xFF;
  }
  uint8_t got = Wire.requestFrom(addr, (uint8_t)1);
  if (got != 1 || !Wire.available()) {
    if (ok) *ok = false;
    return 0xFF;
  }
  if (ok) *ok = true;
  return Wire.read();
}

// Write one byte. Returns Wire.endTransmission() status (0 = ACK).
static uint8_t writeReg(uint8_t addr, uint8_t reg, uint8_t val) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  Wire.write(val);
  return Wire.endTransmission();
}

// Single-bit address probe — returns true if the device ACKs its 7-bit addr.
static bool ack(uint8_t addr) {
  Wire.beginTransmission(addr);
  return Wire.endTransmission() == 0;
}

// --- Decode helpers --------------------------------------------------------

static void printByteBits(const char* label, uint8_t v) {
  Serial.printf("  %s = 0x%02X  ( ", label, v);
  for (int i = 7; i >= 0; --i) {
    Serial.print((v >> i) & 1);
    if (i == 4) Serial.print(' ');
  }
  Serial.println(" )");
}

// Print the PWR_GOOD byte plus a human-readable per-rail breakdown. Bit
// names per TI datasheet figure "PWR_GOOD Register".
static void decodePwrGood(uint8_t v, bool bus_ok) {
  if (!bus_ok) {
    Serial.println("  PWR_GOOD: <I2C bus error — chip did not ACK>");
    return;
  }
  printByteBits("PWR_GOOD ", v);
  if (v == kPwrGoodOk) {
    Serial.println("  PWR_GOOD: ALL RAILS GOOD (0xFA — healthy)");
    return;
  }
  // Datasheet: bit7=PG_VPOS, bit6=PG_VEE, bit5=PG_VNEG, bit4=PG_VDDH,
  //            bit3=PG_VB,   bit2..0 reserved.
  Serial.printf("  PWR_GOOD: NOT healthy. Per-rail:%s%s%s%s%s\n",
                (v & 0x80) ? " VPOS:OK" : " VPOS:BAD",
                (v & 0x40) ? " VEE:OK"  : " VEE:BAD",
                (v & 0x20) ? " VNEG:OK" : " VNEG:BAD",
                (v & 0x10) ? " VDDH:OK" : " VDDH:BAD",
                (v & 0x08) ? " VB:OK"   : " VB:BAD");
}

// Sticky interrupt status. A bit set here means that fault was latched at
// some point since INT1 was last read. Reading INT1 CLEARS the latched bits
// — so dump it once and then trust the snapshot, don't re-read.
static void decodeInt1(uint8_t v, bool bus_ok) {
  if (!bus_ok) {
    Serial.println("  INT1: <I2C bus error>");
    return;
  }
  printByteBits("INT1     ", v);
  // Datasheet: bit7=DTX (temp sensor done), bit6=TSD (thermal shutdown),
  //            bit5=HOT (over-temp warn), bit4=TC (temp change),
  //            bit3=UV (under-voltage on any rail), bit2=ACQC (VCOM
  //            acquisition complete), bit1=PRGC (VCOM programming
  //            complete), bit0=reserved.
  if (v == 0) { Serial.println("  INT1: no faults latched"); return; }
  Serial.print("  INT1: latched events:");
  if (v & 0x80) Serial.print(" DTX(temp-done)");
  if (v & 0x40) Serial.print(" TSD(THERMAL_SHUTDOWN)");
  if (v & 0x20) Serial.print(" HOT(over-temp-warn)");
  if (v & 0x10) Serial.print(" TC(temp-change)");
  if (v & 0x08) Serial.print(" UV(UNDER-VOLTAGE)");
  if (v & 0x04) Serial.print(" ACQC(vcom-acquired)");
  if (v & 0x02) Serial.print(" PRGC(vcom-programmed)");
  Serial.println();
}

static void decodeInt2(uint8_t v, bool bus_ok) {
  if (!bus_ok) {
    Serial.println("  INT2: <I2C bus error>");
    return;
  }
  printByteBits("INT2     ", v);
  // Datasheet: bit7..3 = per-rail OC (VB, VDDH, VNEG, VPOS, VEE),
  //            bit2 = EOC (EEPROM operation complete),
  //            bit1 = CC  (CRC check),
  //            bit0 = reserved.
  if (v == 0) { Serial.println("  INT2: no faults latched"); return; }
  Serial.print("  INT2: latched events:");
  if (v & 0x80) Serial.print(" VB_UV/OC");
  if (v & 0x40) Serial.print(" VDDH_UV/OC");
  if (v & 0x20) Serial.print(" VNEG_UV/OC");
  if (v & 0x10) Serial.print(" VPOS_UV/OC");
  if (v & 0x08) Serial.print(" VEE_UV/OC");
  if (v & 0x04) Serial.print(" EOC");
  if (v & 0x02) Serial.print(" CC");
  Serial.println();
}

static void decodeEnable(uint8_t v, bool bus_ok) {
  if (!bus_ok) { Serial.println("  ENABLE: <I2C bus error>"); return; }
  printByteBits("ENABLE   ", v);
  Serial.printf("  ENABLE: rails-bit (0x20) is %s, VCOM-en (0x10) is %s, V_SOURCE-en (0x04) is %s\n",
                (v & 0x20) ? "SET (rails enabled)" : "CLEAR (rails disabled)",
                (v & 0x10) ? "SET" : "CLEAR",
                (v & 0x04) ? "SET" : "CLEAR");
}

static void decodeRevId(uint8_t v, bool bus_ok) {
  if (!bus_ok) { Serial.println("  REVID: <I2C bus error>"); return; }
  Serial.printf("  REVID    = 0x%02X  (TI silicon revision — should be non-zero if chip is alive)\n", v);
}

static void decodeTemp(uint8_t v, bool bus_ok) {
  if (!bus_ok) { Serial.println("  TMST_VALUE: <I2C bus error>"); return; }
  // TMST_VALUE is signed °C (two's complement, -25 to +85 typical).
  int8_t t = (int8_t)v;
  Serial.printf("  TMST_VALUE = 0x%02X  (%d °C — internal die temp; thermal threshold ~80 °C)\n", v, t);
}

// --- Full TPS register dump ----------------------------------------------

static void dumpTps(const char* label) {
  Serial.printf("\n--- TPS65186 register dump: %s ---\n", label);
  if (!ack(kTpsAddr)) {
    Serial.printf("  *** TPS65186 @ 0x%02X did NOT ACK — chip is unreachable. ***\n", kTpsAddr);
    Serial.println("  This means either the I2C bus is wedged, or the chip is");
    Serial.println("  in a power state where it does not respond. Either way the");
    Serial.println("  rest of this dump will be 0xFF.");
    return;
  }
  bool ok;
  uint8_t pg = readReg(kTpsAddr, kRegPwrGood, &ok);  decodePwrGood(pg, ok);
  uint8_t i1 = readReg(kTpsAddr, kRegInt1,    &ok);  decodeInt1(i1, ok);
  uint8_t i2 = readReg(kTpsAddr, kRegInt2,    &ok);  decodeInt2(i2, ok);
  uint8_t en = readReg(kTpsAddr, kRegEnable,  &ok);  decodeEnable(en, ok);
  uint8_t tm = readReg(kTpsAddr, kRegTmstValue, &ok); decodeTemp(tm, ok);
  uint8_t rv = readReg(kTpsAddr, kRegRevId,   &ok);  decodeRevId(rv, ok);
}

static void dumpExpander() {
  Serial.println("\n--- MCP23017 (internal IO expander @ 0x20) ---");
  if (!ack(kExpAddr)) {
    Serial.println("  *** Expander did not ACK — that means I2C bus is wedged.");
    Serial.println("  This would also explain why the TPS reads fail.");
    return;
  }
  bool ok;
  uint8_t gpa = readReg(kExpAddr, kMcpGpioA, &ok);
  if (!ok) { Serial.println("  GPIOA read failed."); return; }
  uint8_t iod = readReg(kExpAddr, kMcpIoDirA, &ok);
  printByteBits("GPIOA    ", gpa);
  printByteBits("IODIRA   ", iod);
  // Inkplate10 pins.h: WAKEUP=3, PWRUP=4, VCOM=5 — all on port A.
  Serial.printf("  Pin states (port A): WAKEUP(%u)=%s  PWRUP(%u)=%s  VCOM(%u)=%s\n",
                kPinWakeup, (gpa & (1 << kPinWakeup)) ? "HIGH" : "LOW",
                kPinPwrup,  (gpa & (1 << kPinPwrup))  ? "HIGH" : "LOW",
                kPinVcom,   (gpa & (1 << kPinVcom))   ? "HIGH" : "LOW");
  Serial.printf("  Pin directions:      WAKEUP=%s PWRUP=%s VCOM=%s  (output expected for all three)\n",
                (iod & (1 << kPinWakeup)) ? "INPUT" : "OUTPUT",
                (iod & (1 << kPinPwrup))  ? "INPUT" : "OUTPUT",
                (iod & (1 << kPinVcom))   ? "INPUT" : "OUTPUT");
}

// --- Recovery primitives that bypass the library --------------------------

static void rawWakeupCycle(uint16_t low_ms) {
  Serial.printf("  driving WAKEUP LOW directly via expander for %u ms...\n", low_ms);
  uint8_t gpa = readReg(kExpAddr, kMcpGpioA);
  uint8_t low_val  = gpa & ~(1 << kPinWakeup);
  uint8_t high_val = gpa |  (1 << kPinWakeup);
  writeReg(kExpAddr, kMcpGpioA, low_val);
  delay(low_ms);
  Serial.println("  driving WAKEUP HIGH...");
  writeReg(kExpAddr, kMcpGpioA, high_val);
  delay(10);  // settle
}

static void rawRewriteSequencer() {
  Serial.println("  rewriting UPSEQ0/UPSEQ1/DWNSEQ0/DWNSEQ1 to library defaults...");
  // Values match TPS65186::begin() in the Soldered library: per-rail 3 ms
  // up-delay, 6 ms down-delay, default rail order.
  writeReg(kTpsAddr, kRegUpSeq0,  0x1B);
  writeReg(kTpsAddr, kRegUpSeq1,  0x00);
  writeReg(kTpsAddr, kRegDwnSeq0, 0x1B);
  writeReg(kTpsAddr, kRegDwnSeq1, 0x00);
}

// --- The actual stages ----------------------------------------------------

// Returns true if the panel was successfully drawn (cycles > 0).
static bool tryDraw() {
  Serial.println("\n--- Functional draw test ---");
  Serial.println("  drawing a black 200×60 rect via partialUpdate(true)...");
  display.setDisplayMode(INKPLATE_1BIT);
  display.fillRect(500, 380, 200, 60, BLACK);
  uint32_t cycles = display.partialUpdate(true);
  Serial.printf("  partialUpdate cycles = %u  -> %s\n",
                (unsigned)cycles,
                cycles > 0 ? "PANEL ACTUALLY UPDATED"
                           : "library bailed (most likely einkOn returned 0 inside)");
  return cycles > 0;
}

// Best-effort einkOn() that reports back the bool *and* the resulting PG byte.
static void tryEinkOn(const char* label) {
  Serial.printf("\n--- %s: einkOn() ---\n", label);
  int rc = display.einkOn();
  Serial.printf("  einkOn() returned %d  (1=PWR_GOOD reached, 0=timed out at 250 ms)\n", rc);
  delay(20);
  dumpTps(label);
}

void setup() {
  Serial.begin(115200);
  delay(800);
  Serial.println();
  Serial.println("========================================================");
  Serial.println("  Inkplate 10 — EPD power-supply probe");
  Serial.printf ("  build %s %s\n", __DATE__, __TIME__);
  Serial.println("  flash, then keep this monitor open for full report");
  Serial.println("========================================================");

  // --------------------------------------------------------------------
  // STAGE A — bring up the library so the IO expander is bound and Wire
  // is initialized at the correct pins.
  // --------------------------------------------------------------------
  Serial.println("\n[A] display.begin() ...");
  display.begin();
  Wire.setClock(100000);
  delay(50);

  Serial.println("[A] I2C bus scan (devices that ACK at 7-bit addr):");
  for (uint8_t a = 0x01; a <= 0x7F; ++a) {
    if (ack(a)) {
      const char* name = "";
      if (a == kTpsAddr) name = " <- TPS65186 (EPD PMIC)";
      else if (a == kExpAddr) name = " <- MCP23017 (internal expander)";
      else if (a == 0x21) name = " <- MCP23017 (external expander)";
      else if (a == 0x50) name = " <- onboard EEPROM";
      Serial.printf("    0x%02X%s\n", a, name);
    }
  }

  // --------------------------------------------------------------------
  // STAGE B & C — register and pin state AS FOUND. Critical: do this
  // BEFORE we poke anything, because reading INT1/INT2 clears their
  // sticky bits.
  // --------------------------------------------------------------------
  dumpTps("STAGE B — as-found, no recovery attempted");
  dumpExpander();

  // --------------------------------------------------------------------
  // STAGE D — first recovery: a plain einkOn() call. If the chip is
  // healthy, this will succeed and we'll see PWR_GOOD = 0xFA.
  // --------------------------------------------------------------------
  tryEinkOn("STAGE D — plain einkOn()");

  // --------------------------------------------------------------------
  // STAGE E — soft recovery (issue #297 hypothesis): einkOff, 2 s, einkOn.
  // --------------------------------------------------------------------
  Serial.println("\n[E] soft recovery: einkOff() -> 2 s -> einkOn() ...");
  display.einkOff();
  delay(2000);
  tryEinkOn("STAGE E — after einkOff/2s/einkOn");

  // --------------------------------------------------------------------
  // STAGE F — WAKEUP-cycle recovery: drop WAKEUP low for 500 ms directly
  // via the expander (the library does not do this on its own), then
  // einkOn(). Per the TPS65186 datasheet, some fault classes clear on
  // WAKEUP de-assertion.
  // --------------------------------------------------------------------
  Serial.println("\n[F] WAKEUP-cycle recovery ...");
  display.einkOff();
  delay(100);
  rawWakeupCycle(500);
  tryEinkOn("STAGE F — after WAKEUP cycle");

  // --------------------------------------------------------------------
  // STAGE G — full sequencer re-init then einkOn.
  // --------------------------------------------------------------------
  Serial.println("\n[G] sequencer re-init then einkOn() ...");
  display.einkOff();
  delay(100);
  rawWakeupCycle(200);
  rawRewriteSequencer();
  tryEinkOn("STAGE G — after sequencer re-init");

  // --------------------------------------------------------------------
  // STAGE H — functional test. Whatever state we're in now, attempt a
  // small partial draw. cycles > 0 confirms the panel actually wrote.
  // --------------------------------------------------------------------
  bool drew = tryDraw();

  // --------------------------------------------------------------------
  // Summary line — easiest to grep for.
  // --------------------------------------------------------------------
  Serial.println();
  Serial.println("========================================================");
  Serial.printf ("  SUMMARY: draw_succeeded=%d  (true = panel is back up)\n",
                 drew ? 1 : 0);
  Serial.println("  If draw_succeeded=1: software recovery works -> firmware fix possible.");
  Serial.println("  If draw_succeeded=0 and INT1/INT2 bits stayed asserted across stages:");
  Serial.println("      hardware fault latch -> physical LiPo removal required.");
  Serial.println("  If draw_succeeded=0 and TPS never ACKed: I2C bus wedged at the chip.");
  Serial.println("========================================================");
}

void loop() {
  // Idle. The diagnostic ran once in setup(). Press RESET to re-run.
  delay(1000);
}

#endif  // ARDUINO && EPD_PROBE
