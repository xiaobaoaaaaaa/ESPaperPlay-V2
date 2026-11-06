#!/usr/bin/env python3
"""Reproduce the r5 TLV1822/BQ24074 shared-feedback temperature-window review.

Run from any directory; Python 3 + Poppler pdftotext are the only dependencies.
The result is an engineering corner model, not a device qualification claim.
Only files beside this script are written.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PDF = ROOT / "hardware/reference/ntc175-2026-11-04/honeywell-175-103lae-301.pdf"

# Ordered as pullup, hot top/bottom, cold top/bottom, feedback N/C, TS return.
NAMES = ("R_NTC_UP", "R_HOT_TOP", "R_HOT_BOTTOM", "R_COLD_TOP",
         "R_COLD_BOTTOM", "R_FB_NTC", "R_FB_COLD", "R_TS")
NOMINAL = (47000., 100000., 12000., 100000., 33000., 330000., 330000., 10000.)
# Symmetric conservative enclosure of 1% initial tolerance plus 100 ppm/K
# across the largest |T-25 C| within board component temperature -40..85 C.
R_TOL = (1.01 * (1 + 100e-6 * 65)) - 1
# 4 mV full-temperature offset plus a 0.2 mV engineering budget for supply
# variation and input-bias loading. This is a stated model assumption: the
# datasheet offset table is characterized at VS=12 V, VCM=VS/2; its PSRR entry
# and typical curves do not establish a complete guaranteed 5 V error budget.
E_BUDGET = .0042
VIN_OPERATING = (4.75, 5.25)
VIN_EXTENDED = (2.9, 10.8)  # Stress/sensitivity only; board remains a 5 V input.
ITS = (72e-6, 78e-6)
VOL = (0., .25)


def load_rt():
    text = subprocess.check_output(["pdftotext", "-layout", str(PDF), "-"], text=True)
    rows = []
    for line in text.splitlines():
        cols = line.split()
        if len(cols) != 6:
            continue
        try:
            t = int(cols[0])
            rmin, _, rnom, rmax, _ = map(float, cols[1:])
        except ValueError:
            continue
        rows.append((t, rmin * 1000, rnom * 1000, rmax * 1000))
    assert len(rows) == 191 and rows[0][0] == -40 and rows[-1][0] == 150
    assert next(row for row in rows if row[0] == 25) == (25, 9700., 10000., 10300.)
    return rows


RT = load_rt()


def temperature(resistance, curve=2):
    """Linear interpolation of original tabulated R(T), no Beta approximation."""
    for a, b in zip(RT, RT[1:]):
        if a[curve] >= resistance >= b[curve]:
            return a[0] + (a[curve] - resistance) / (a[curve] - b[curve])
    raise ValueError(f"resistance outside table: {resistance}")


def trip(rs, vin, its, error, kind, vlow=None):
    """Solve NTC resistance and all three coupled nodes at a comparator trip.

    N = BAT_NTC, C = COLD_REF, S = CHG_TS.
    C = a + b*S. Normal output S is solved with BQ's current source present;
    fault S is bounded by vlow. Never substitute a fixed 0.75 V for normal S.
    """
    p, ht, hb, ct, cb, fn, fc, ts = rs
    hot = vin * hb / (ht + hb)
    gc = 1 / ct + 1 / cb + 1 / fc
    a, b = vin / ct / gc, 1 / fc / gc
    if vlow is not None:
        s = vlow
        n = hot + error if kind == "hot" else a + b * s + error
    elif kind == "hot":
        n = hot + error
        s = (its + n / fn + a / fc) / (1 / ts + 1 / fn + 1 / fc - b / fc)
    else:
        s = (its + (a + error) / fn + a / fc) / (
            1 / ts + 1 / fn + 1 / fc - b * (1 / fn + 1 / fc))
        n = a + b * s + error
    c = a + b * s
    rntc = n / ((vin - n) / p + (s - n) / fn)
    return {"rntc_ohm": rntc, "ts_v": s, "ntc_v": n, "cold_ref_v": c, "hot_ref_v": hot}


def resistor_corners():
    for signs in itertools.product((-1, 1), repeat=len(NOMINAL)):
        yield tuple(value * (1 + sign * R_TOL) for value, sign in zip(NOMINAL, signs))


def trip_envelope(vins, kind, phase):
    results = []
    lows = (None,) if phase == "suspend" else VOL
    for rs in resistor_corners():
        for v, i, e, low in itertools.product(vins, ITS, (-E_BUDGET, E_BUDGET), lows):
            results.append(trip(rs, v, i, e, kind, low))
    rlo = min(x["rntc_ohm"] for x in results)
    rhi = max(x["rntc_ohm"] for x in results)
    return {
        "corner_count": len(results), "rntc_ohm": [rlo, rhi],
        "temperature_c": [temperature(rhi, 1), temperature(rlo, 3)],
        "ts_v": [min(x["ts_v"] for x in results), max(x["ts_v"] for x in results)],
    }


def hysteresis(vins, kind):
    deltas = []
    for rs in resistor_corners():
        for v, i, e, low in itertools.product(vins, ITS, (-E_BUDGET, E_BUDGET), VOL):
            r1 = trip(rs, v, i, e, kind)["rntc_ohm"]
            r2 = trip(rs, v, i, e, kind, low)["rntc_ohm"]
            # Same components, supply, bias, offset and RT curve for both edges.
            for curve in (1, 2, 3):
                d = temperature(r1, curve) - temperature(r2, curve)
                deltas.append(d if kind == "hot" else -d)
    assert min(deltas) > 0
    return {"same_corner_hysteresis_c": [min(deltas), max(deltas)], "all_positive": True}


def fault_nodes(rs, vin, its, fault, s=None):
    """Solve open/short NTC with outputs either released or held low."""
    p, ht, hb, ct, cb, fn, fc, ts = rs
    gn = 1 / p + 1 / fn
    an, bn = (vin / p / gn, 1 / fn / gn) if fault == "open" else (0., 0.)
    gc = 1 / ct + 1 / cb + 1 / fc
    ac, bc = vin / ct / gc, 1 / fc / gc
    if s is None:
        s = (its + an / fn + ac / fc) / (
            1 / ts + 1 / fn + 1 / fc - bn / fn - bc / fc)
    n, c, h = an + bn * s, ac + bc * s, vin * hb / (ht + hb)
    sink = its - s / ts + (n - s) / fn + (c - s) / fc
    margin = n - c if fault == "open" else h - n
    return margin, sink, n, c, h, s


def fault_envelope():
    answer = {}
    for fault in ("open", "short"):
        margins, sinks = [], []
        for rs in resistor_corners():
            for v, i, low in itertools.product(VIN_EXTENDED, (0., *ITS), (None, *VOL)):
                margin, sink, n, c, h, s = fault_nodes(rs, v, i, fault, low)
                margins.append(margin - E_BUDGET)
                if low is not None:
                    sinks.append(sink)
                assert min(n, c, h) >= 0 and max(n, c, h) <= v
        assert min(margins) > 0 and max(sinks) < .004
        answer[fault] = {"minimum_fault_differential_after_error_v": min(margins),
                         "maximum_output_sink_a": max(sinks), "stable_fault": True}
    return answer


def main():
    report = {"topology": "TLV1822DR dual open-drain outputs tied to BQ24074 TS; 10k TS return; 330k positive feedback to NTC and cold reference",
              "resistors_ohm": dict(zip(NAMES, NOMINAL)),
              "model_assumptions": {"resistor_fractional_bound": R_TOL,
                                    "input_differential_budget_v": E_BUDGET,
                                    "ntc_identity": "Honeywell 175-103LAE-301 curve assumed; actual pack identity unverified",
                                    "rt_source": str(PDF.relative_to(ROOT)),
                                    "nominal_vin_v": 5., "recommended_input": "5 V only",
                                    "timing": "No guaranteed startup timing claim; bench validation required",
                                    "electrical_bounds": "Engineering budget, not full guaranteed characterization over every VIN/VCM; see review.md"}}
    nominal = {}
    for kind in ("cold", "hot"):
        nominal[kind] = {}
        for phase, low in (("suspend", None), ("resume", .1)):
            result = trip(NOMINAL, 5., 75e-6, 0., kind, low)
            nominal[kind][phase] = {**result, "temperature_c": temperature(result["rntc_ohm"])}
            if phase == "resume":
                nominal[kind][phase]["low_output_note"] = "0.1 V is an illustrative clamp, not a datasheet typical value"
        nominal[kind]["resume_temperature_at_low_output_endpoints_c"] = [
            temperature(trip(NOMINAL, 5., 75e-6, 0., kind, low)["rntc_ohm"])
            for low in VOL]
        start = trip(NOMINAL, 5., 0., 0., kind)
        nominal[kind]["bias_off_released_output"] = {
            **start, "temperature_c": temperature(start["rntc_ohm"])}
    report["nominal"] = nominal
    for scope, vins in (("5v_supply_4p75_to_5p25", VIN_OPERATING), ("extended_sensitivity_2p9_to_10p8", VIN_EXTENDED)):
        report[scope] = {}
        for kind in ("cold", "hot"):
            report[scope][kind] = {
                phase: trip_envelope(vins, kind, phase) for phase in ("suspend", "resume")}
            report[scope][kind].update(hysteresis(vins, kind))
    report["sensor_faults"] = fault_envelope()
    ext = report["extended_sensitivity_2p9_to_10p8"]
    assert ext["cold"]["suspend"]["temperature_c"][0] > 10
    assert ext["hot"]["suspend"]["temperature_c"][1] < 45
    assert min(ext[k]["suspend"]["ts_v"][0] for k in ("cold", "hot")) > .33
    assert max(ext[k]["suspend"]["ts_v"][1] for k in ("cold", "hot")) < 2.0
    (HERE / "temperature-window-results.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"nominal": nominal, "extended": ext, "faults": report["sensor_faults"]}, indent=2))


if __name__ == "__main__":
    main()
