# AD8232 lead-off review - 2026-11-06

Mapping fixed: AD8232 LO+ to GPIO27, LO- to GPIO26, OUT remains GPIO34
(ADC1 channel6). The previous plus/minus labels in main.cpp were reversed.
There are no other LO GPIO definitions in integrated firmware source.

## Electrical interpretation and evidence

Source: [Analog Devices AD8232 Rev.D datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/AD8232.pdf),
pin descriptions on page8 and lead-off circuits on pages20-21.

- DC mode (AC/DC pin LOW): LOD+ HIGH indicates +IN disconnected; LOD- HIGH
  indicates -IN disconnected. The specified DC circuit uses three electrodes
  and a valid RLD/common-mode return. Its analog-input pull resistors are
  distinct from ESP32 GPIO pull resistors.
- AC mode (AC/DC pin HIGH): LOD+ indicates disconnection of either input;
  LOD- stays LOW. The firmware cannot determine module AC/DC selection from
  the two LO outputs. Startup log explicitly says chip_ac_dc_mode=NOT_READ.
- ESP32 GPIO26/27 remain INPUT, with internal pull-up and pull-down disabled
  and interrupts disabled. These are driven AD8232 logic outputs when the
  module is powered and properly connected. No pull-down was added to mask
  a genuine HIGH. A disconnected/unpowered module output can float; LOW by
  itself never establishes a valid electrode connection or ECG.

Available drawing D:\diagram (1).json was read without modification. It is a
Wokwi potentiometer-to-GPIO34 simulation with a lead button on GPIO33; neither
GPIO26 nor GPIO27 is wired. It contains no real AD8232 circuit or AC/DC strap.
It therefore cannot verify the actual module internals or real lead wiring.
The corrected mapping follows the physical wiring explicitly supplied by the
user. Check the actual module schematic/AC/DC strap before interpreting which
electrode a HIGH identifies.

Confirmed software cause: plus/minus mapping reversed. This explains reversed
individual labels, **not** lo_any=256. Boolean OR is invariant to swapping its
inputs. The code counts one event whenever either raw level is HIGH for that
sample. lo_any=256 means OR was HIGH on all256 sampled pairs (if snapshot
integrity is OK); it does not necessarily mean one specific pin stayed HIGH.
For example plus_high=128/minus_high=128/both_high=0 can also yield256.

Stable actual_hz=250 measures scheduling/read intervals, independently of
electrode validity. With no connected simulator/electrodes, asserted lead-off
is expected for a properly configured lead-off circuit. The existing aggregate
log alone cannot distinguish that from floating/miswired GPIO, missing common
ground, wrong power/SDN/mode, or an invalid simulator common-mode return. No
physical cause for the old aggregate count is claimed as proven here.

## Changes and log semantics

- main/main.cpp: corrected mapping, startup config log, diagnostic snapshot
  collection, independent frozen-buffer recomputation and validation, one
  AD8232_LEADS line per printed ADC summary.
- main/lead_off.h: shared wiring constants, active-HIGH OR and diagnostic
  counting/consistency checks.
- tests/lead_off_test.cpp: truth table, all65536 eight-sample sequences,
  swap invariance, immutable copies and corrupt raw/count rejection.
- README.md and debug/lead_off_review.json: current report/build links.

Existing Sample layout, ISR, ADC read, timestamps, 4000us timer and256 samples
are retained. Summary gains diagnostic fields covered by its existing checksum
and value-copy queue. The logger formats both lines under the existing console
lock and suppresses both during operator trace. No print/GPIO reads were added
in ISR; logger never reads live pins. The extra Serial volume and timing must
still be checked on board. Each emitted diagnostic line has line_fnv1a covering
the content before its checksum suffix, matching ADC_BUFFER convention.

Example format only, not a measured board result:

```text
AD8232_CONFIG lo_plus_gpio=27 lo_minus_gpio=26 adc_gpio=34 mode=INPUT pull_up=DISABLED pull_down=DISABLED lead_off_active=HIGH chip_ac_dc_mode=NOT_READ
AD8232_LEADS id=2 lo_plus_gpio=27 lo_minus_gpio=26 raw_scope=LAST_SAMPLE lo_plus_raw=1 lo_minus_raw=0 lead_off=1 lo_any=256 lo_plus_high=256 lo_minus_high=0 lo_both_high=0 samples=256 integrity=OK line_fnv1a=<checksum>
```

lo_plus_raw/lo_minus_raw are the last sampled raw levels of that completed
buffer, not a new GPIO read at print time. lead_off is their OR (0/1). lo_any
is the count over the whole buffer, retained in ADC_BUFFER as before.
lo_plus_high/lo_minus_high/lo_both_high are the corresponding counts over256.
Identity checked: lo_any = plus_high + minus_high - both_high. All counts and
last raw levels are recomputed from the same frozen buffer, and malformed
snapshots print integrity=FAILED plus the existing ADC_WARNING. It is valid
for lead_off=0 at the last sample while lo_any>0 earlier in the buffer.

Every asserted per-sample OR still reaches pipeline_observe and LEADS_OFF /
SIGNAL_INVALID. Any affected block is still rejected by pipeline_offer. There
is no bypass, forced LOW, or "lo_any=0 means valid ECG" assumption. The CNN,
golden test, Conv arithmetic fix, threshold0.52, LED23, buzzer25, FSM/latch,
and live-disabled config are unchanged (protected-source hashes verified).

## Bench verification without any connection to a person

1. Confirm 3.3V/GND and continuity: module LO+ to GPIO27, LO- to GPIO26, OUT
   to GPIO34; check SDN/module enable and actual AC/DC configuration. With
   module powered, measure LO levels relative to shared GND at BOTH module
   header and ESP32 pin using a voltmeter/logic analyzer, and compare raw logs.
   A HIGH at the module but LOW at ESP32 points to wiring/level trouble; correct
   raw levels but wrong labels would point to mapping. Do not infer mode solely
   from which output happens to be LOW.
2. Connect only a suitable isolated ECG simulator's electrode outputs to the
   module's matching input terminals and reference/RL connection according to
   their actual pinout/manual. Start with a nominal 1mV,60bpm simulator signal
   if supported. DC detection requires a suitable third-lead/common-mode return.
   After settling, both LO outputs should deassert when the circuit/simulator
   meets its specified connection conditions. Inspect lo_any=0 and signal rails;
   this is a bench signal, not validated real ECG or PVC recognition.
3. In DC mode, disconnect only the simulator terminal for +IN: expect GPIO27
   /lo_plus_raw HIGH and SIGNAL_INVALID. Reconnect and wait for settling; then
   disconnect -IN: expect GPIO26/lo_minus_raw HIGH. In AC mode, either disconnect
   instead asserts LOD+/GPIO27, while LOD-/GPIO26 stays LOW. On return, FSM may
   require its existing good-sample recovery interval; it is not changed here.
4. Disconnect both simulator signal leads; expect the appropriate lead-off
   indication for the module circuit and no acceptance of that block. Compare
   both counters to explain any all256 assertion. If a valid attached simulator
   still gives256, check electrical levels, power/ground, connector pinout,
   AC/DC strap, input bias/common mode and SDN before blaming firmware timing.
5. A function generator connected directly to GPIO34 tests ADC timing ONLY.
   Disconnect AD8232 OUT first to avoid connecting two outputs together, use
   common ground and a bounded0..3.3V waveform (e.g.1.65V offset,0.2V peak).
   This does not establish a conduction path at AD8232 inputs and does not
   clear INVALID_LEADS. Keep its actual LO outputs connected; never force them
   LOW or drive against them to obtain a valid status.
6. Throughout, check ADC_BUFFER integrity, actual_hz, late, missed_est,
   adc_errors, and self-test/FSM behavior. Do not enable AI-live, change the
   threshold or classify simulator waveforms as validated N/PVC.

## Verification performed here

Host lead-off test PASS;14 strict trace tests PASS; existing C++ encoder and
signal guard tests PASS. ESP-IDF5.4.4 build/link/partition check PASS; detailed
binary size, SHA and protected-source checks are in lead_off_review.json and
lead_off_build.log. No board execution, flash or reset in this task. Physical
lead-off levels and sampling performance of this revision remain unmeasured.

To rerun the new logic test from this project:

```powershell
g++ -std=c++17 -Wall -Wextra -Werror -I main tests/lead_off_test.cpp -o tests/lead_off_test.exe
.\tests\lead_off_test.exe
```
