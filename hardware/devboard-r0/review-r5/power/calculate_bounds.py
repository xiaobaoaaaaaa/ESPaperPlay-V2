"""Calculate r5 charger candidate limits; no bench or pack qualification implied.

Run from any directory with Python 3. The only generated file is the adjacent
charge-bounds.json. Constants below are design inputs or cited datasheet limits;
reported bounds are computed rather than transcribed from the r4 report.
"""
from pathlib import Path
import json

HERE = Path(__file__).resolve().parent
T_REF_C = 25
R_TEMPERATURE_C = (-40, 85)
R_TOLERANCE = 0.01
R_TCR_PER_C = 100e-6
CAPACITY_AH = 4.0
MAX_DESIGN_CHARGE_C_RATE = 0.2
TERMINATION_REFERENCE_C_RATE = 0.01

# TI SLUS810N, section 8.5, guaranteed only under its stated test conditions.
KISET = (797, 890, 975)             # A ohm
KPRECHG = (70, 88, 106)             # A ohm
KILIM = (1500, 1610, 1720)          # A ohm, 500 mA to 1.5 A range
KITERM_NORMAL = (0.0225, 0.0300, 0.0375)  # A
KITERM_USB100 = (0.008, 0.0100, 0.012)    # A
KTMR = (36, 48, 60)                # s/kohm


def resistor(ref, nominal_ohm, mpn):
    delta_c = max(abs(t - T_REF_C) for t in R_TEMPERATURE_C)
    low = (1 - R_TOLERANCE) * (1 - R_TCR_PER_C * delta_c)
    high = (1 + R_TOLERANCE) * (1 + R_TCR_PER_C * delta_c)
    return {
        "ref": ref, "nominal_ohm": nominal_ohm,
        "min_ohm": nominal_ohm * low, "max_ohm": nominal_ohm * high,
        "min_factor": low, "max_factor": high, "candidate_mpn": mpn,
    }


def inverse_current(k, r):
    return {"min_a": k[0] / r["max_ohm"],
            "typ_a": k[1] / r["nominal_ohm"],
            "max_a": k[2] / r["min_ohm"]}


def ratio_current(k, numerator, denominator):
    # Independent resistor corners: equal nominal values do not cancel tolerance.
    return {"min_a": k[0] * numerator["min_ohm"] / denominator["max_ohm"],
            "typ_a": k[1] * numerator["nominal_ohm"] / denominator["nominal_ohm"],
            "max_a": k[2] * numerator["max_ohm"] / denominator["min_ohm"]}


def timer_hours(r, multiplier):
    return {f"{name}_h": multiplier * k * r[key] / 1000 / 3600
            for name, k, key in zip(("min", "typ", "max"), KTMR,
                                    ("min_ohm", "nominal_ohm", "max_ohm"))}


rs = {
    "iset": resistor("R104", 1270, "CRCW06031K27FKEA"),
    "iterm": resistor("R113", 1270, "CRCW06031K27FKEA"),
    "timer": resistor("R105", 68000, "CRCW060368K0FKEA"),
    "ilim": resistor("R103", 1620, "CRCW06031K62FKEA"),
}
charge = inverse_current(KISET, rs["iset"])
precharge = inverse_current(KPRECHG, rs["iset"])
normal_term = ratio_current(KITERM_NORMAL, rs["iterm"], rs["iset"])
usb100_term = ratio_current(KITERM_USB100, rs["iterm"], rs["iset"])
input_limit = inverse_current(KILIM, rs["ilim"])
fast_timer = timer_hours(rs["timer"], 10)
precharge_timer = timer_hours(rs["timer"], 1)
current_ceiling_a = CAPACITY_AH * MAX_DESIGN_CHARGE_C_RATE
termination_ceiling_a = CAPACITY_AH * TERMINATION_REFERENCE_C_RATE
thermal_inputs = [
    ("5V_low_battery_light_system", 5.0, 3.0, 4.3, 0.1),
    ("5V25_at_low_fast_charge_transition", 5.25, 2.9, 4.3, 0.1),
    ("5V_near_CV_upper_current_envelope", 5.0, 4.2, 4.3, 0.1),
]
thermal_cases = []
for label, vin, vbat, vsys, isys in thermal_inputs:
    p_charge = (vin - vbat) * charge["max_a"]
    p_system = (vin - vsys) * isys
    thermal_cases.append({
        "case": label, "assumed_vin_v": vin, "assumed_vbat_v": vbat,
        "assumed_sys_v": vsys, "assumed_system_a": isys,
        "charge_current_envelope_a": charge["max_a"],
        "charge_path_w": p_charge, "system_path_w": p_system,
        "estimated_path_dissipation_w": p_charge + p_system,
    })

checks = {
    "charge_upper_below_0p2C": charge["max_a"] < current_ceiling_a,
    "normal_iterm_upper_below_0p01C": normal_term["max_a"] < termination_ceiling_a,
    "iset_resistance_within_TI_range": 590 <= rs["iset"]["min_ohm"]
        and rs["iset"]["max_ohm"] <= 8900,
    "iterm_resistance_within_TI_range": 0 <= rs["iterm"]["min_ohm"]
        and rs["iterm"]["max_ohm"] < 15000,
    "timer_resistance_within_TI_range": 18000 < rs["timer"]["min_ohm"]
        and rs["timer"]["max_ohm"] < 72000,
    "ilim_resistance_within_TI_range": 1100 <= rs["ilim"]["min_ohm"]
        and rs["ilim"]["max_ohm"] <= 8000,
    "normal_iterm_within_half_fast_charge": normal_term["max_a"] < charge["min_a"] / 2,
    "positive_current_budget_before_system_and_IC": input_limit["min_a"] > charge["max_a"],
}
assert all(checks.values()), checks

report = {
    "date": "2026-11-04", "revision": "r5",
    "scope": "Calculated charger candidate limits, not hardware measurements or production release.",
    "sources": [
        {"url": "https://www.ti.com/lit/ds/symlink/bq24074.pdf",
         "revision": "SLUS810N", "local_path": "hardware/reference/power/bq24074.pdf",
         "sections": "8.3/8.5;9.3.4;9.3.5.1/2/6/8;10.2.2.2",
         "facts": "KISET/KPRECHG/KILIM/KITERM/KTMR limits, resistor ranges, DPPM and dynamic timers."},
        {"url": "https://www.vishay.com/docs/20035/dcrcwe3.pdf",
         "revision": "14-Apr-2026", "sections": "pp1-3:0603/E96,1%,100ppm/K,ordering code",
         "facts": "CRCW resistor candidates, package and tolerance/TCR; stock not checked."},
        {"url": "https://www.zoncell.com/product/lp1s-ntc/",
         "local_path": "hardware/reference/zoncell-2026-11-04/product-3002.json",
         "facts": "Ordinary family4.2V:0.2C fast charge;below20C max0.2C;standard termination below0.01C;10..45C charging.",
         "qualification": "Family design basis applied to selected4Ah pack; not a pack qualification sheet."},
    ],
    "resistor_model": {
        "initial_tolerance_fraction": R_TOLERANCE, "tcr_ppm_per_c": R_TCR_PER_C * 1e6,
        "body_temperature_c": list(R_TEMPERATURE_C), "reference_temperature_c": T_REF_C,
        "aging_and_solder_drift_included": False,
        "qualification": "Multiplicative independent initial-tolerance/TCR corners, same model as r4. No BQ operation at negative junction temperature is implied.",
    },
    "resistors": rs,
    "TI_factors": {"KISET_Aohm_min_typ_max": KISET, "KPRECHG_Aohm_min_typ_max": KPRECHG,
                   "KILIM_Aohm_min_typ_max": KILIM, "KITERM_normal_A_min_typ_max": KITERM_NORMAL,
                   "KITERM_USB100_A_min_typ_max": KITERM_USB100, "KTMR_s_per_kohm_min_typ_max": KTMR},
    "charge": {**charge, "capacity_ah": CAPACITY_AH,
        "typ_c_rate": charge["typ_a"] / CAPACITY_AH,
        "max_c_rate": charge["max_a"] / CAPACITY_AH,
        "design_upper_a": current_ceiling_a,
        "headroom_to_design_upper_a": current_ceiling_a - charge["max_a"],
        "qualification": "Set current, conditional on VIN/input capacity and inactive thermal/DPPM loops; sustained real current not measured."},
    "precharge": precharge,
    "termination": {"normal_USB500_or_ILIM": normal_term, "USB100": usb100_term,
        "design_normal_upper_a": termination_ceiling_a,
        "qualification": "ExternalR113 replaces the floating pin's10% threshold. In DPPM/VIN-DPM/thermal regulation termination detection is disabled by the IC."},
    "timers": {"fast_charge": fast_timer, "precharge": precharge_timer,
        "ideal_capacity_over_typ_current_h": CAPACITY_AH / charge["typ_a"],
        "ideal_capacity_over_min_current_h": CAPACITY_AH / charge["min_a"],
        "full_charge_before_min_timer_guaranteed": False,
        "qualification": "Nominal timer9.07h is retained. Capacity/current excludes CV taper and precharge; dynamic slowing in DPPM/VIN-DPM/thermal regulation extends wall time. Partial-charge timeout is acceptable; never disable the timer or automatically toggleCE/input to clear a fault.",
        "temperature_gate_note": "CE toggling resets timers; any external automatic temperature gating viaCE needs a retained session/fault policy. TS faults suspend timers under the IC's rules."},
    "input": {**input_limit,
        "unmeasured_bypass_allocation_a": 0.005,
        "allocated_total_input_upper_a": input_limit["max_a"] + 0.005,
        "remaining_at_min_ilim_max_charge_before_SYS_and_IC_a": input_limit["min_a"] - charge["max_a"],
        "qualification": "R103 unchanged; worst remaining0.13A is before IC operating current and SYS load. DefaultUSB100 unchanged; higher mode requires a known capable source. DPPM may reduce or stop charging under load."},
    "thermal": {"formula": "(VIN-VBAT)*ICHG + (VIN-SYS)*ISYS", "cases": thermal_cases,
        "measured": False,
        "qualification": "Engineering operating-point estimates, excluding bias losses. Voltages and SYS load are assumptions, not simultaneous worst-case proof. CV case uses an upper current envelope, not claimed CV current. Exposed-pad copper/vias and board thermal tests required; datasheet44.5C/W is not the actual PCB thermal resistance."},
    "application_temperature_boundaries": {
        "BQ_electrical_table_junction_c": [0, 125],
        "battery_family_charge_c": [10, 45],
        "intended_narrow_temperature_window_c": [15, 40],
        "initial_controlled_test_environment_c": [20, 30],
        "qualification": "This script does not qualify NTC window limits. Honeywell175-103LAE-301 is a user-authorized design assumption, not confirmed pack identity. Separate window-circuit worst-case review must keep battery charging inside10..45C; resistor temperature range is not battery permission.",
    },
    "checks": checks,
}
(HERE / "charge-bounds.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"charge_a": charge, "termination_normal_a": normal_term,
                  "termination_USB100_a": usb100_term, "timer_h": fast_timer,
                  "input_a": input_limit,
                  "remaining_before_SYS_and_IC_a": report["input"]["remaining_at_min_ilim_max_charge_before_SYS_and_IC_a"],
                  "thermal_path_w": [c["estimated_path_dissipation_w"] for c in thermal_cases],
                  "checks_passed": len(checks)}, indent=2))
