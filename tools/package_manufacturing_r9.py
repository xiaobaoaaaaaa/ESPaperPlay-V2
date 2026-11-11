#!/usr/bin/env python3
"""Package already-reviewed r9 files separately; never exports, uploads or orders."""
from pathlib import Path
import hashlib
import json
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "hardware/devboard-r0/output/manufacturing/r9-review"
REVIEW = ROOT / "hardware/devboard-r0/review-r9"
SOURCE = ROOT / "hardware/devboard-r0/ESPaperPlay_Devboard.kicad_pcb"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def archive(target, members):
    with ZipFile(target, "w", compression=ZIP_DEFLATED, compresslevel=9) as z:
        for p, name in sorted(members, key=lambda x: x[1]):
            info = ZipInfo(name, date_time=(2026, 11, 11, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, p.read_bytes())
    with ZipFile(target) as z:
        require(z.testzip() is None, f"ZIP integrity failed: {target}")
        for p, name in members:
            require(z.read(name) == p.read_bytes(), f"ZIP content differs: {name}")


def main():
    cam = json.loads((REVIEW / "cam-readback.json").read_text())
    stencil = json.loads((REVIEW / "stencil-audit.json").read_text())
    assembly = json.loads((BASE / "assembly/assembly-summary.json").read_text())
    source_sha = sha(SOURCE)
    require(source_sha == cam["source_sha256"] == stencil["source_sha256_unchanged"]
            == assembly["source_board_sha256"], "Source differs between reports")
    board = []
    for name, wanted in cam["sha256"].items():
        p = BASE / "board" / name
        require(sha(p) == wanted, f"CAM changed since readback: {name}")
        require("paste" not in name.lower(), "Paste in bare-board export")
        board.append((p, name))
    board.append((BASE / "board/README.md", "README.md"))
    board.append((REVIEW / "special-hole-register.csv", "special-hole-register.csv"))
    candidate = ROOT / stencil["published_candidate"]["file"]
    require(sha(candidate) == stencil["published_candidate"]["sha256"], "Stencil changed since audit")
    for name, detail in assembly["files"].items():
        require(sha(BASE / "assembly" / name) == detail["sha256"], f"Assembly file changed: {name}")
    archive(BASE / "ESPaperPlay-r8-board-r9-REVIEW_ONLY.zip", board)
    archive(BASE / "ESPaperPlay-r8-DIY-stencil-r9-REVIEW_ONLY.zip",
            [(candidate, candidate.name), (BASE / "stencil/README.md", "README.md")])
    files = [p for p in BASE.rglob("*") if p.is_file() and p.name != "artifact-index.json"]
    index = {"status": "REVIEW_ONLY_NOT_RELEASED", "date": "2026-11-11",
             "source_board_sha256": source_sha,
             "coordinate_rules": "See README and assembly/assembly-summary.json; CAM and assembly CSV origins differ intentionally.",
             "sha256": {str(p.relative_to(BASE)): sha(p) for p in sorted(files)}}
    (BASE / "artifact-index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n")
    print(f"PASS: two separate REVIEW_ONLY ZIPs; {len(files)} indexed files")


if __name__ == "__main__":
    main()
