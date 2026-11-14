#!/usr/bin/env python3
"""Reproduce r10 review CAM, DIY stencil, assembly data and separate review ZIPs.

Uses the reviewed r9 geometry/export helpers without modifying historical files.
Requires KiCad 10 pcbnew/CLI and gerbonara 1.6.2, shapely 2.2.0,
matplotlib 3.11.2; --render also needs system Rsvg/pycairo.
The pinned design-baseline.json must match before any files are written.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import sys
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

import pcbnew as P
from shapely.geometry import Point
import export_manufacturing_r9 as cam
import prepare_stencil_r9 as stencil
import export_assembly_r9 as assembly

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "hardware/devboard-r0"
SOURCE = PROJECT / "ESPaperPlay_Devboard.kicad_pcb"
REVIEW = PROJECT / "review-r10"
OUT = PROJECT / "output/manufacturing/r10-review"
WORK = ROOT / "build/dfm-r10/export"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write_json(p, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def check(ok, message):
    if not ok:
        raise ValueError(message)


def label(p):
    return str(p.relative_to(ROOT))


def export_board(config, render):
    cam.SOURCE_SHA, cam.OUT, cam.REVIEW = config["board_sha256"], OUT, REVIEW
    original_argv = sys.argv
    try:
        sys.argv = [__file__] + (["--render"] if render else [])
        cam.main()
    finally:
        sys.argv = original_argv
    # r9's helper inventories the whole output directory, including an existing
    # README on reruns. Keep the r10 CAM manifest limited to actual CAM files.
    suffixes = ["F_Cu.gtl", "In1_Cu.g1", "In2_Cu.g2", "B_Cu.gbl", "F_Mask.gts", "B_Mask.gbs",
                "F_Silkscreen.gto", "B_Silkscreen.gbo", "Edge_Cuts.gm1", "PTH.drl", "NPTH.drl",
                "PTH-drl_map.svg", "NPTH-drl_map.svg", "job.gbrjob"]
    report = json.loads((REVIEW / "cam-readback.json").read_text())
    report["sha256"] = {"ESPaperPlay_Devboard-" + suffix: sha(OUT / "board" / ("ESPaperPlay_Devboard-" + suffix))
                        for suffix in suffixes}
    write_json(REVIEW / "cam-readback.json", report)


def export_stencil(config):
    stencil.SOURCE, stencil.OUT = SOURCE, WORK / "stencil"
    work = stencil.OUT
    stencil.preflight_paths(argparse.Namespace(board=SOURCE, work_dir=work,
                                              review_dir=REVIEW, output_dir=OUT / "stencil"))
    work.mkdir(parents=True, exist_ok=True)
    (OUT / "stencil").mkdir(parents=True, exist_ok=True)
    stencil.plot_board(SOURCE, work / "native-plot")
    original, raw = stencil.report_board(SOURCE, work / "native-plot")
    board = P.LoadBoard(str(SOURCE))
    geometry_before = stencil.snapshot(board)
    refs = {f.GetReference() for f in board.GetFootprints()
            if f.GetAttributes() & P.FP_SMD and not f.IsDNP()} - stencil.MANUAL
    check(len(refs) == 203, "Assembly population changed")
    delta = stencil.derive(board)
    check(stencil.snapshot(board) == geometry_before, "Stencil altered non-paste geometry")
    variant = work / "ESPaperPlay_Devboard_DIY_stencil_candidate.kicad_pcb"
    P.SaveBoard(str(variant), board)
    reopened = P.LoadBoard(str(variant))
    check(stencil.snapshot(reopened) == geometry_before, "Saved variant altered non-paste geometry")
    stencil.plot_board(variant, work / "diy-candidate-plot")
    candidate, result_geom = stencil.report_board(variant, work / "diy-candidate-plot")
    check(set(candidate["layers"]["F.Paste"]["by_ref"]) == refs, "Wrong paste refs")
    check(candidate["layers"]["F.Paste"]["physical_components"] == 636, "Unexpected aperture count")
    check(candidate["layers"]["B.Paste"]["objects"] == 0, "Unexpected back paste")
    check(not candidate["dnp_paste_refs"] and not candidate["drilled_pads_with_paste_layer"], "DNP/PTH paste remains")
    check(candidate["critical"]["U301"]["paste_coverage_percent"] == 0, "U301 EPAD printed")
    check(candidate["layers"]["F.Paste"]["by_ref"]["U301"]["components"] == 40, "U301 perimeter changed")
    check(candidate["layers"]["F.Paste"]["by_ref"]["U803"]["unsupported_islands"] == 0, "Unsupported mic island")
    for side in ["F.Mask", "B.Mask"]:
        check(raw[side][1].symmetric_difference(result_geom[side][1]).area < 1e-9, "Mask changed in stencil variant")
    # Independent actual-Gerber audit over every native via, not only the r9 contact list.
    thermal = set(config["retained_ic_thermal_via_uuids"])
    rows = []
    for via in board.GetTracks():
        if not isinstance(via, P.PCB_VIA):
            continue
        x, y = stencil.xy(via.GetPosition())
        hole = Point(x, y).buffer(P.ToMM(via.GetDrillValue()) / 2, quad_segs=256)
        row = {"uuid": via.m_Uuid.AsString(), "net": via.GetNetname(), "x_mm": x, "y_mm": y,
               "drill_mm": P.ToMM(via.GetDrillValue()), "retained_thermal_via": via.m_Uuid.AsString() in thermal}
        for side in ["F.Mask", "B.Mask"]:
            row[side + "_gap_mm"] = hole.distance(raw[side][1])
            row[side + "_open_fraction"] = hole.intersection(raw[side][1]).area / hole.area
        row["DIY_paste_overlap_mm2"] = hole.intersection(result_geom["F.Paste"][1]).area
        rows.append(row)
    check(len(rows) == 549 and sum(r["retained_thermal_via"] for r in rows) == 11, "Via inventory changed")
    nonthermal = [r for r in rows if not r["retained_thermal_via"]]
    min_gap = min(min(r["F.Mask_gap_mm"], r["B.Mask_gap_mm"]) for r in nonthermal)
    check(min_gap >= .2 - .00001, f"Actual mask margin below project target: {min_gap}")
    check(sum(r["DIY_paste_overlap_mm2"] > 1e-6 for r in rows) == 10, "Thermal paste overlap count changed")
    with (REVIEW / "all-via-mask-clearance.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(sorted(rows, key=lambda r: r["uuid"]))
    stencil.drawings(raw, result_geom)
    paste = OUT / "stencil/ESPaperPlay_Devboard-DIY-F_Paste.gtp"
    shutil.copy2(work / "diy-candidate-plot/ESPaperPlay_Devboard_DIY_stencil_candidate-F_Paste.gtp", paste)
    report = {"status": "ENGINEERING_REVIEW_NOT_FACTORY_RELEASE", "source_sha256_unchanged": sha(SOURCE),
              "protected_geometry_sha256": geometry_before, "delta": delta,
              "original": original, "DIY_candidate": candidate,
              "published_candidate": {"file": label(paste), "sha256": sha(paste), "steel_thickness_mm": .10, "microphone_bridge_mm": .15},
              "assertions": {"source_matches_r10_baseline": True, "source_unchanged": True,
                             "stencil_preserves_copper_mask_drill_routes_and_placement": True,
                             "actual_F_B_mask_unchanged_by_stencil": True, "203_fitted_reflow_refs": True,
                             "636_apertures": True, "DNP_manual_and_through_hole_paste_removed": True,
                             "U301_40_perimeter_and_zero_EPAD": True, "U803_supported_center_island": True,
                             "all_538_nonthermal_native_vias_meet_0_20_mm_mask_target": True},
              "all_native_via_review": {"count": len(rows), "retained_thermal": 11, "nonthermal": 538,
                                        "target_mm": .2, "minimum_actual_mask_gap_mm": min_gap,
                                        "method": "Actual Gerber mask polygons; native circular holes with 1024-edge polygon approximation. Both sides checked.",
                                        "register": "all-via-mask-clearance.csv"},
              "limits": ["0.20 mm mask separation is a project geometry target, not a worst-case manufacturing guarantee.",
                         "11 retained IC vias require the specified resin fill and copper cap; Gerbers alone do not specify actual fill.",
                         "Stencil thickness/bridges require first-board print, reflow and acoustic validation."],
              "sources": stencil.source_inventory()}
    solder_holes = original["holes_intersecting_SMT_copper"]
    check(len(solder_holes) == 23, "Solder-area hole inventory changed")
    check(not original["native_vias_annular_contact_only"], "Annular contact remains")
    candidate_holes = {h["uuid"]: h for h in candidate["holes_intersecting_SMT_copper"]}
    register = []
    for hole in solder_holes:
        register.append({"source_sha256": config["board_sha256"], "uuid": hole["uuid"],
                         "kind": hole["kind"], "x_mm": hole["centre_mm"][0], "y_mm": hole["centre_mm"][1],
                         "drill_mm": hole["drill_mm"][0],
                         "F_Mask_open_fraction": hole["F_Mask_open_hole_fraction"],
                         "B_Mask_open_fraction": hole["B_Mask_open_hole_fraction"],
                         "DIY_paste_overlap_mm2": candidate_holes[hole["uuid"]]["F_Paste_overlap_hole_mm2"],
                         "process": "REQUIRED_RESIN_FILL_PLANARIZE_COPPER_CAP_ENIG" if hole["uuid"] in thermal else "U301_UNPRINTED_OPTIONAL_EPAD_NO_MANDATORY_FILL"})
    with (REVIEW / "special-hole-register.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(register[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(sorted(register, key=lambda r: r["uuid"]))
    for source in report["sources"]:
        if "distribution" in source:
            source["distribution"] = source["distribution"].replace("r9 manufacturing", "r10 manufacturing")
    shutil.copy2(work / "mic-stencil-before-after.png", REVIEW / "stencil-microphone.png")
    write_json(REVIEW / "stencil-audit.json", report)
    check(sha(SOURCE) == config["board_sha256"], "Source changed")
    print(f"PASS stencil: 203 refs, 636 apertures; 538 via minimum mask gap {min_gap:.6f} mm")


def export_assembly(config):
    assembly.FROZEN_SHA256 = config["board_sha256"]
    original_rows = assembly.get_rows
    original_map = assembly.assembly_map
    def rows_for_r10(board):
        rows, geometry = original_rows(board)
        for row in rows:
            for key, value in list(row.items()):
                if isinstance(value, str):
                    row[key] = value.replace("use_reviewed_r9_smd_stencil", "use_reviewed_r10_smd_stencil")
        return rows, geometry
    assembly.get_rows = rows_for_r10
    assembly.assembly_map = lambda rows, h: original_map(rows, h).replace(b"r9", b"r10").replace(b"r8 PCB", b"r10 PCB")
    summary = assembly.export(SOURCE, OUT / "assembly")
    summary["revision"] = "r10-review"
    summary["generator"] = label(Path(__file__).resolve())
    summary["generator_sha256"] = sha(Path(__file__).resolve())
    summary["assembly_rules"]["other_smd"] = "Use the separately reviewed r10 stencil; not print/reflow qualified."
    summary["helper"] = {"file": label(Path(assembly.__file__)), "sha256": sha(Path(assembly.__file__))}
    write_json(OUT / "assembly/assembly-summary.json", summary)
    print("PASS assembly: 203 reflow, 27 hand-solder, 6 DNP")


def package(config):
    c = json.loads((REVIEW / "cam-readback.json").read_text())
    s = json.loads((REVIEW / "stencil-audit.json").read_text())
    a = json.loads((OUT / "assembly/assembly-summary.json").read_text())
    check(c["source_sha256"] == s["source_sha256_unchanged"] == a["source_board_sha256"] == config["board_sha256"], "Sources differ")
    for name, h in c["sha256"].items():
        check(sha(OUT / "board" / name) == h, "CAM changed: " + name)
    check(sha(ROOT / s["published_candidate"]["file"]) == s["published_candidate"]["sha256"], "Paste changed")
    for name, info in a["files"].items():
        check(sha(OUT / "assembly" / name) == info["sha256"], "Assembly changed: " + name)
    thermal_rows = list(csv.DictReader((REVIEW / "thermal-via-fill-spec.csv").open()))
    check(len(thermal_rows) == 11 and {r["uuid"] for r in thermal_rows} == set(config["retained_ic_thermal_via_uuids"]), "Wrong fill scope")
    board = P.LoadBoard(str(SOURCE))
    vias = {v.m_Uuid.AsString(): v for v in board.GetTracks() if isinstance(v, P.PCB_VIA)}
    for row in thermal_rows:
        via = vias[row["uuid"]]
        check(via.GetNetname() == "GND", "Fill target is not GND")
        for key, value in [("x_mm", P.ToMM(via.GetPosition().x)), ("y_mm", P.ToMM(via.GetPosition().y)),
                           ("drill_x_mm", P.ToMM(via.GetDrillValue())), ("drill_y_mm", P.ToMM(via.GetDrillValue()))]:
            check(abs(float(row[key]) - value) < 1e-6, "Fill-table geometry changed: " + row["uuid"])
    board_files = [(OUT / "board" / n, n) for n in c["sha256"]]
    check(not any("paste" in n.lower() for p, n in board_files), "Paste in bare-board package")
    board_files += [(OUT / "board/README.md", "README.md"), (REVIEW / "thermal-via-fill-spec.csv", "thermal-via-fill-spec.csv")]
    bundles = [("ESPaperPlay-r10-board-REVIEW_ONLY.zip", board_files),
               ("ESPaperPlay-r10-DIY-stencil-REVIEW_ONLY.zip",
                [(OUT / "stencil/ESPaperPlay_Devboard-DIY-F_Paste.gtp", "ESPaperPlay_Devboard-DIY-F_Paste.gtp"),
                 (OUT / "stencil/README.md", "README.md")])]
    for name, members in bundles:
        check(len({member for p, member in members}) == len(members), "Duplicate archive member")
        with ZipFile(OUT / name, "w", compression=ZIP_DEFLATED) as z:
            for p, member in members:
                info = ZipInfo(member, (2026, 11, 14, 0, 0, 0))
                info.compress_type, info.external_attr = ZIP_DEFLATED, 0o644 << 16
                z.writestr(info, p.read_bytes())
        with ZipFile(OUT / name) as z:
            check(z.testzip() is None, "ZIP CRC failure")
            for p, member in members:
                check(z.read(member) == p.read_bytes(), "ZIP contents differ")
    files = sorted(p for p in OUT.rglob("*") if p.is_file() and p.name != "artifact-index.json")
    write_json(OUT / "artifact-index.json", {"date": "2026-11-14", "status": "REVIEW_ONLY_NOT_FACTORY_RELEASED",
               "source_board_sha256": config["board_sha256"], "sha256": {str(p.relative_to(OUT)): sha(p) for p in files}})
    print("PASS separate review ZIPs and artifact hashes")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["board", "stencil", "assembly", "package", "all"], default="all")
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    config = json.loads((REVIEW / "design-baseline.json").read_text())
    check(sha(SOURCE) == config["board_sha256"], "PCB differs from reviewed r10 baseline")
    check(sha(SOURCE.with_suffix(".kicad_pro")) == config["project_sha256"], "Project rules changed")
    if args.stage in ("board", "all"): export_board(config, args.render)
    if args.stage in ("stencil", "all"): export_stencil(config)
    if args.stage in ("assembly", "all"): export_assembly(config)
    if args.stage in ("package", "all"): package(config)
    check(sha(SOURCE) == config["board_sha256"], "Source changed during export")


if __name__ == "__main__":
    main()
