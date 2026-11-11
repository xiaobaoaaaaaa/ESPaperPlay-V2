#!/usr/bin/env python3
"""Export r8 bare-board CAM for r9 REVIEW ONLY; independently read back drills/outline.

Requires KiCad CLI/pcbnew 10, gerbonara==1.6.2. --render additionally uses
system PyGObject/Rsvg and pycairo. Does not export paste or authorize fabrication.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import warnings

import pcbnew
from gerbonara import LayerStack
from gerbonara.utils import MM

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "hardware/devboard-r0/ESPaperPlay_Devboard.kicad_pcb"
SOURCE_SHA = "1a4556d866cc1352a2c45b674c94d2f233edf28c3e003bd96c8f6caf1e630681"
OUT = ROOT / "hardware/devboard-r0/output/manufacturing/r9-review"
REVIEW = ROOT / "hardware/devboard-r0/review-r9"
LAYERS = "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,Edge.Cuts"


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def endpoints(a, b):
    return tuple(sorted((tuple(a), tuple(b))))


def mmxy(v):
    return v.x / 1e6, -v.y / 1e6


def native_holes(board):
    holes = []
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            p = mmxy(t.GetPosition())
            holes.append(("plated", t.GetDrillValue() / 1e6, endpoints(p, p), "via"))
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetDrillSize().x == 0:
                continue
            hole = pad.GetEffectiveHoleShape()
            seg = hole.GetSeg()
            kind = "nonplated" if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH else "plated"
            holes.append((kind, hole.GetWidth() / 1e6,
                          endpoints(mmxy(seg.A), mmxy(seg.B)),
                          f"{fp.GetReference()}.{pad.GetNumber()}"))
    return holes


def compare_holes(native, actual):
    remaining = list(native)
    max_error = 0.0
    for kind, dia, ends in actual:
        matches = []
        for i, (nk, nd, ne, ref) in enumerate(remaining):
            err = max(abs(a - b) for p, q in zip(ends, ne) for a, b in zip(p, q))
            if nk == kind and abs(nd - dia) < 1e-6 and err <= 0.000501:
                matches.append((i, err))
        assert len(matches) == 1, f"Drill has {len(matches)} native matches: {(kind, dia, ends)}"
        i, err = matches[0]
        max_error = max(max_error, err)
        remaining.pop(i)
    assert not remaining, f"Missing native drills: {remaining}"
    return max_error


def render_svg(svg, png):
    import cairo
    import gi
    gi.require_version("Rsvg", "2.0")
    from gi.repository import Rsvg
    handle = Rsvg.Handle.new_from_file(str(svg))
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1920, 1320)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(1, 1, 1)
    ctx.paint()
    viewport = Rsvg.Rectangle()
    viewport.x, viewport.y, viewport.width, viewport.height = 0, 0, 1920, 1320
    handle.render_document(ctx, viewport)
    surface.write_to_png(str(png))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--render", action="store_true")
    args = ap.parse_args()
    assert digest(SOURCE) == SOURCE_SHA, "Source changed: re-review before exporting"
    board_dir = OUT / "board"
    board_dir.mkdir(parents=True, exist_ok=True)
    REVIEW.mkdir(parents=True, exist_ok=True)
    commands = [
        ["kicad-cli", "pcb", "export", "gerbers", "--layers", LAYERS,
         "--precision", "6", "--subtract-soldermask", "--check-zones",
         "-o", str(board_dir) + "/", str(SOURCE)],
        ["kicad-cli", "pcb", "export", "drill", "--format", "excellon",
         "--drill-origin", "absolute", "--excellon-units", "mm",
         "--excellon-zeros-format", "decimal", "--excellon-oval-format", "route",
         "--excellon-separate-th", "--generate-map", "--map-format", "svg",
         "--generate-report", "--report-path", str(REVIEW / "drill-report.txt"),
         "-o", str(board_dir) + "/", str(SOURCE)],
    ]
    if not args.verify_only:
        for command in commands:
            subprocess.run(command, check=True, cwd=ROOT)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        cam = LayerStack.open(board_dir)
        expected_layers = {("top", "copper"), ("inner_1", "copper"),
                           ("inner_2", "copper"), ("bottom", "copper"),
                           ("top", "mask"), ("bottom", "mask"),
                           ("top", "silk"), ("bottom", "silk"),
                           ("mechanical", "outline")}
        assert set(cam.graphic_layers) == expected_layers
        assert all(layer.objects for layer in cam.graphic_layers.values())
        board = pcbnew.LoadBoard(str(SOURCE))
        native = native_holes(board)
        actual = []
        for kind, drill in [("plated", cam.drill_pth), ("nonplated", cam.drill_npth)]:
            assert drill is not None
            for o in drill.objects:
                assert o.unit == MM and o.aperture.unit == MM
                a, b = ((o.x1, o.y1), (o.x2, o.y2)) if hasattr(o, "x1") else ((o.x, o.y), (o.x, o.y))
                actual.append((kind, o.aperture.diameter, endpoints(a, b)))
        error = compare_holes(native, actual)
        expected_edges = sorted(endpoints(mmxy(d.GetStart()), mmxy(d.GetEnd()))
                                for d in board.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts)
        actual_edges = sorted(endpoints((d.x1, d.y1), (d.x2, d.y2)) for d in cam.outline.objects)
        assert expected_edges == actual_edges and len(expected_edges) == 4
        if args.render:
            previews = OUT / "previews"
            previews.mkdir(exist_ok=True)
            for side in ("top", "bottom"):
                svg = previews / f"cam-{side}.svg"
                svg.write_text(str(cam.to_pretty_svg(side=side, margin=0)))
                render_svg(svg, previews / f"cam-{side}.png")
        warning_text = sorted(set(str(w.message).replace(str(ROOT) + "/", "") for w in caught))
    assert len(native) == 663
    assert digest(SOURCE) == SOURCE_SHA
    report = {
        "status": "PASS: export readback; REVIEW ONLY, not fabrication release",
        "source_board": str(SOURCE.relative_to(ROOT)), "source_sha256": SOURCE_SHA,
        "kicad": pcbnew.GetBuildVersion(), "parser": "gerbonara 1.6.2",
        "layers": {"/".join(k): len(v.objects) for k, v in cam.graphic_layers.items()},
        "hole_counts": dict(Counter(h[0] for h in native)),
        "hole_inventory": [dict(kind=k, diameter_mm=d, count=n)
                           for (k, d), n in sorted(Counter((h[0], h[1]) for h in native).items())],
        "all_663_drills_bijectively_match_native": True,
        "max_coordinate_error_mm": error, "allowed_export_rounding_mm": 0.000501,
        "plated_slots": sum(k == "plated" and e[0] != e[1] for k, d, e in actual),
        "outline_segments_match_native": True, "board_edge_centerline_size_mm": [160, 110],
        "outline_stroke_bbox_size_mm": list(cam.outline.size()),
        "coordinate_convention": "KiCad absolute X, negative KiCad Y in all CAM; mm. Assembly CSV separately uses board lower-left origin.",
        "commands": [[v.replace(str(ROOT) + "/", "") for v in command] for command in commands],
        "parser_warnings": warning_text,
        "limits": ["Readback checks layer inventory, exact outline centerlines, all drill locations/diameters/plating/slots and parser acceptance.",
                   "It is not an independent copper-netlist DRC or factory CAM/impedance qualification.",
                   "KiCad job bounding box includes 0.05 mm outline stroke; physical profile uses its centerline.",
                   "No paste is included in the bare-board CAM. Use the separately audited DIY stencil variant."],
        "sha256": {p.name: digest(p) for p in sorted(board_dir.iterdir()) if p.is_file()},
    }
    (REVIEW / "cam-readback.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(f"PASS: {len(native)} drills, {len(expected_edges)} profile segments, {len(expected_layers)} layers; source unchanged")


if __name__ == "__main__":
    main()
