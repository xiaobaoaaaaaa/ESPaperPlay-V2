Actual native power-path review

Source `PCB-layout.epcb` SHA256 `2a1cffb14d0b4b8e7f7a6841dc08b4b72d591e465cb707a8a4efbf93bb9d6e1e`.

Measured 24/24 paths; R20 screening within review limit for 24/24; 8 project width/neck target deviations. These are trace-only metrics, not manufacturing or thermal release.

| Path | From → to | Min / target width mm | Exposed length mm | Below-target / allowance mm | R20 / review limit mΩ | Review |
|---|---|---:|---:|---:|---:|---|
|usb_before_ptc|J501.A4 → F501.1|0.269 / 0.800|21.018|9.931 / 4.000|15.800 / 30.000|GEOMETRIC_WIDTH_TARGET_DEVIATION|
|usb_protected_to_selector|F501.2 → J502.1|0.800 / 0.800|16.665|0.000 / 3.000|10.260 / 40.000|TRACE_TARGET_METRICS_PASS|
|bench_to_selector|J101.1 → J502.3|0.800 / 0.800|26.132|0.000 / 3.000|16.088 / 60.000|TRACE_TARGET_METRICS_PASS|
|selected_input_to_charger_cap|J502.2 → C101.1|0.800 / 0.800|23.232|0.000 / 3.000|14.303 / 60.000|TRACE_TARGET_METRICS_PASS|
|charger_input_local|C101.1 → U101.13|0.500 / 0.500|0.939|0.000 / 2.000|0.925 / 15.000|TRACE_TARGET_METRICS_PASS|
|charger_output_local|U101.10 → R101.1|0.600 / 0.600|13.143|0.000 / 2.000|10.790 / 30.000|TRACE_TARGET_METRICS_PASS|
|sys_main_converter_feed|R101.2 → C201.1|0.400 / 1.000|9.533|4.807 / 3.000|7.390 / 40.000|GEOMETRIC_WIDTH_TARGET_DEVIATION|
|sys_amplifier_feed|R101.2 → U405.1|0.500 / 0.600|51.644|2.232 / 4.000|27.344 / 80.000|TRACE_TARGET_METRICS_PASS|
|battery_pack_to_link|J102.1 → R102.1|1.000 / 1.000|2.243|0.000 / 3.000|1.105 / 25.000|TRACE_TARGET_METRICS_PASS|
|battery_link_to_charger_cap|R102.2 → C103.1|1.000 / 1.000|14.967|0.000 / 3.000|7.370 / 50.000|TRACE_TARGET_METRICS_PASS|
|charger_battery_local|C103.1 → U101.2|0.600 / 0.600|0.474|0.000 / 2.000|0.389 / 15.000|TRACE_TARGET_METRICS_PASS|
|main_converter_input_local|C201.1 → U201.10|1.000 / 0.600|0.946|0.000 / 2.000|0.466 / 15.000|TRACE_TARGET_METRICS_PASS|
|main_converter_output_local|U201.6 → R203.1|0.600 / 0.600|5.667|0.000 / 2.000|4.653 / 25.000|TRACE_TARGET_METRICS_PASS|
|main_mcu_supply|R203.2 → U301.2|0.719 / 0.800|43.639|43.639 / 4.000|29.765 / 80.000|GEOMETRIC_WIDTH_TARGET_DEVIATION|
|main_epd_switch_feed|R203.2 → U401.1|0.539 / 0.600|72.803|35.020 / 4.000|57.873 / 100.000|GEOMETRIC_WIDTH_TARGET_DEVIATION|
|main_sd_switch_feed|R203.2 → U402.1|0.539 / 0.600|39.044|1.261 / 4.000|27.022 / 100.000|TRACE_TARGET_METRICS_PASS|
|epd_output_to_boost_cap|R402.2 → C603.1|0.470 / 0.600|20.893|3.147 / 3.000|17.786 / 50.000|GEOMETRIC_WIDTH_TARGET_DEVIATION|
|sd_output_to_card|R405.2 → J701.4|0.500 / 0.500|18.095|0.000 / 4.000|17.826 / 60.000|TRACE_TARGET_METRICS_PASS|
|touch_output_to_fpc|R408.2 → J406.2|0.300 / 0.300|20.769|0.000 / 4.000|34.079 / 150.000|TRACE_TARGET_METRICS_PASS|
|mic_output_to_device|R411.2 → U803.3|0.300 / 0.300|23.524|0.000 / 4.000|38.595 / 150.000|TRACE_TARGET_METRICS_PASS|
|amp_output_to_device|R414.2 → U802.2|0.190 / 0.600|14.330|2.367 / 3.000|14.887 / 50.000|TRACE_TARGET_METRICS_PASS|
|usb_a9_to_ptc|J501.A9 → F501.1|0.269 / 0.800|23.223|11.759 / 4.000|17.620 / 30.000|GEOMETRIC_WIDTH_TARGET_DEVIATION|
|usb_b4_to_ptc|J501.B4 → F501.1|0.269 / 0.800|23.223|11.759 / 4.000|17.620 / 30.000|GEOMETRIC_WIDTH_TARGET_DEVIATION|
|usb_b9_to_ptc|J501.B9 → F501.1|0.269 / 0.800|21.018|9.931 / 4.000|15.800 / 30.000|GEOMETRIC_WIDTH_TARGET_DEVIATION|

All limits and terminal IDs are frozen in `power-path-rules.json`; actual positions and copper are read from the specified native snapshots and archive. Source corner geometry comes from the native library rather than rounded API pad rectangles.

35um external copper is a reference calculation unless explicitly overridden with confirmed manufactured copper thickness.
Pad/via/contact resistance, parallel-current distribution and heating are not modeled. R20 is a trace-only lower bound; no current/temperature approval.
Width/neck limits are project targets, not manufacturer DRC minima. Accumulated below-target length never resets at split LINE boundaries.
Native DRC, net equivalence, actual CAM and loaded hardware tests remain separate checks.
