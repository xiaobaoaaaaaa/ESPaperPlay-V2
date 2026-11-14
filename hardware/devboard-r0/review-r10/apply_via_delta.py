#!/usr/bin/env python3
"""Reproduce the reviewed r10 via/lead edits from the exact r8 baseline.

Only writes a separate scratch PCB. The original r8 board can be recovered
from Git commit 4b77f10; this is not a generator for later manual edits.
Titleblock/revision silk changes made during promotion are intentionally absent.
Requires system KiCad pcbnew; no third-party Python package is needed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import pcbnew as P


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def xy(p):
    return [P.ToMM(p.x), P.ToMM(p.y)]


def pt(p):
    return P.VECTOR2I(P.FromMM(p[0]), P.FromMM(p[1]))


def snapshot(t):
    data = {"uuid": t.m_Uuid.AsString(), "class": t.GetClass(),
            "net": t.GetNetname(), "net_code": t.GetNetCode(),
            "layer": t.GetLayer(), "start_mm": xy(t.GetStart()),
            "end_mm": xy(t.GetEnd()), "locked": t.IsLocked(),
            "width_mm": P.ToMM(t.GetWidth(P.F_Cu) if t.GetClass() == "PCB_VIA" else t.GetWidth())}
    if t.GetClass() == "PCB_VIA":
        data.update(drill_mm=P.ToMM(t.GetDrillValue()), layers=list(t.GetLayerSet().Seq()),
                    tenting_F=t.IsTented(P.F_Mask), tenting_B=t.IsTented(P.B_Mask))
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--delta", type=Path, default=Path(__file__).with_name("r8-to-r10-via-delta.json"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    formal_tree = Path(__file__).resolve().parents[1]
    if source == output or output.suffix != ".kicad_pcb" or output.is_relative_to(formal_tree):
        raise ValueError("Use a separate scratch .kicad_pcb output")
    delta = json.loads(args.delta.read_text())
    if sha(source) != delta["source_board_sha256"]:
        raise ValueError("Source differs from the exact reviewed r8 baseline")
    board = P.LoadBoard(str(source))
    items = {t.m_Uuid.AsString(): t for t in board.GetTracks()}
    for row in delta["changes"]:
        if snapshot(items[row["before"]["uuid"]]) != row["before"]:
            raise ValueError("Native input item differs: " + row["before"]["uuid"])
    for row in delta["changes"]:
        after = row["after"]
        item = items[after["uuid"]]
        if item.GetClass() == "PCB_VIA":
            item.SetPosition(pt(after["start_mm"]))
            item.SetWidth(P.FromMM(after["width_mm"]))
            item.SetDrill(P.FromMM(after["drill_mm"]))
        else:
            item.SetStart(pt(after["start_mm"]))
            item.SetEnd(pt(after["end_mm"]))
        if snapshot(item) != after:
            raise ValueError("Native output item differs: " + after["uuid"])
    board.BuildConnectivity()
    P.ZONE_FILLER(board).Fill(board.Zones())
    output.parent.mkdir(parents=True, exist_ok=True)
    P.SaveBoard(str(output), board)
    if sha(source) != delta["source_board_sha256"]:
        raise ValueError("Input unexpectedly changed")
    print(json.dumps({"changes_applied": len(delta["changes"]),
                      "output_sha256": sha(output), "source_unchanged": True}))


if __name__ == "__main__":
    main()
