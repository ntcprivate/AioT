# Physical checklist - pending, simulator only

1. Disconnect all body electrodes. Identify simulator model/manual, output lead, rate, amplitude and PVC program. Photograph its connection to the module. Record whether reference events can be synchronized.
2. With power OFF, verify the actual module pin labels: OUT -> GPIO34, LO+ -> GPIO27, LO- -> GPIO26; module GND -> ESP32 GND; module supply -> 3V3. Verify simulator input mapping from the module schematic, not wire color. RLD is not GND.
3. Leave OUT disconnected from GPIO34. With the bench powered and no person connected, measure module supply relative to module GND using a DMM; report the value, not just the nominal label. Do not use a 5 V module supply by assumption.
4. Measure OUT DC offset with a DMM. Use a suitable oscilloscope/differential probe to record OUT minimum, maximum and startup transients over the intended simulator program. A DMM average cannot establish waveform extremes. Do not connect an earth-referenced scope ground across an isolation barrier; obtain qualified instrumentation help if the reference is unclear. Report actual values and probe arrangement before connecting OUT to GPIO34.
5. Identify the isolation device/system model and its schematic/specification, including EVERY USB, PC power, simulator, charger and oscilloscope path. A continuity check, battery supply or USB isolator label alone does not establish patient safety. Human testing is outside this prepared simulator capture. Any future human protocol needs qualified electrical-safety review and applicable institutional approval; do not perform improvised leakage/withstand tests yourself.
6. After review, confirm voltage compatibility, no clipping/negative input and wiring, then specify capture duration (suggested 60 seconds). Supply synchronized reference labels if available; otherwise classification accuracy is not measurable.

AD8232 chip supply specification: 2.0-3.5 V (module specifics still require its schematic): https://www.analog.com/en/products/ad8232.html
ESP32 attenuation does not establish GPIO safety or full-range calibrated accuracy: https://docs.espressif.com/projects/esp-idf/en/v5.4.4/esp32/api-reference/peripherals/adc_oneshot.html

No physical item above is marked complete. Return measurements and documentation for review; do not fill template booleans merely to bypass the checks.
