#!/usr/bin/env python3
"""Export the r9 manual-assembly review package from the frozen native r8 PCB.

Requires the existing system KiCad pcbnew module and Python standard library.
The source board is read-only. CSV positions use the physical board lower-left
origin; rotations retain KiCad's native footprint angle, NOT feeder rotation.
Candidate MPNs are not a procurement release. This is not a PCBA upload format.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import html
import io
import json
from pathlib import Path
import re

import pcbnew as P

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "hardware/devboard-r0/ESPaperPlay_Devboard.kicad_pcb"
OUTPUT = ROOT / "hardware/devboard-r0/output/manufacturing/r9-review/assembly"
FROZEN_SHA256 = "1a4556d866cc1352a2c45b674c94d2f233edf28c3e003bd96c8f6caf1e630681"
EXPECTED_DNP = {"C501", "C502", "J301", "J302", "J303", "R108"}
HAND_SMD = {"J406", "J501", "J601", "J701"}
MECHANICAL = {"H1", "H2", "H3", "H4"}
HAND_THT = {
    "J101", "J102", "J103", "J104", "J105", "J201", "J202", "J203",
    "J204", "J205", "J206", "J401", "J402", "J403", "J404", "J405",
    "J502", "J801", "SW301", "SW302", "SW303", "SW304", "SW305",
}
GROUP_COUNTS = {
    "top_smd_reflow": 203,
    "post_reflow_smd_connector_hand_solder": 4,
    "post_reflow_tht_hand_solder": 23,
    "do_not_populate": 6,
    "mechanical_hole_only": 4,
}
ROTATION_NOTE = "native_KiCad_angle_not_feeder_rotation"
CANDIDATE_STATUS = "candidate_not_procurement_frozen"
POSITION_COLUMNS = [
    "reference", "value", "footprint", "side", "x_mm_from_board_lower_left",
    "y_mm_from_board_lower_left", "kicad_rotation_deg", "rotation_convention",
    "kicad_x_mm", "kicad_y_mm", "assembly_group", "stencil_rule",
    "manufacturer", "candidate_mpn", "candidate_status", "dnp",
]
POPULATION_COLUMNS = POSITION_COLUMNS + [
    "fitted", "excluded_from_bom", "excluded_from_position_files",
    "footprint_uuid", "bom_review_raw", "bom_review_record_raw",
    "design_note_raw", "candidate_source_raw", "assembly_note",
]
BOM_COLUMNS = [
    "references", "quantity", "value", "footprint", "manufacturer",
    "candidate_mpn", "candidate_status", "assembly_group", "stencil_rule",
    "bom_review_raw", "candidate_source_raw",
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    # Explicit failures still enforce invariants when Python is run with -O.
    if not condition:
        raise ValueError(message)


def natural(reference: str) -> tuple:
    return tuple(int(x) if x.isdigit() else x for x in re.split(r"(\d+)", reference))


def mm(value: int) -> float:
    return round(P.ToMM(value), 6)


def number(value: float) -> str:
    # Fixed precision avoids incidental platform-specific float formatting.
    return f"{value:.6f}"


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def csv_bytes(rows: list[dict], columns: list[str]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def get_rows(board: P.BOARD) -> tuple[list[dict], dict]:
    polygon = P.SHAPE_POLY_SET()
    require(board.GetBoardPolygonOutlines(polygon, False), "Invalid board outline")
    require(polygon.OutlineCount() == 1 and polygon.HoleCount(0) == 0,
            "Expected one outer board contour with no outline cutouts")
    contour = polygon.COutline(0)
    points = [contour.CPoint(i) for i in range(contour.PointCount())]
    extent = [mm(min(p.x for p in points)), mm(min(p.y for p in points)),
              mm(max(p.x for p in points)), mm(max(p.y for p in points))]
    require(extent == [50.0, 50.0, 210.0, 160.0], f"Unexpected board extent: {extent}")
    left, bottom = extent[0], extent[3]
    footprints = list(board.GetFootprints())
    refs = [f.GetReference() for f in footprints]
    require(len(refs) == len(set(refs)) == 240, "Expected 240 unique native footprints")
    require({f.GetReference() for f in footprints if f.IsDNP()} == EXPECTED_DNP,
            "DNP set differs from the frozen assembly rules")
    rows = []
    for footprint in sorted(footprints, key=lambda f: natural(f.GetReference())):
        ref = footprint.GetReference()
        fields = dict(footprint.GetFieldsText())
        attrs = footprint.GetAttributes()
        require(footprint.GetLayer() == P.F_Cu, f"Unexpected assembly side: {ref}")
        dnp = footprint.IsDNP()
        note = ""
        if dnp:
            group, stencil = "do_not_populate", "no_paste_no_population"
            note = "Do not fit; omit all stencil apertures."
        elif ref in MECHANICAL:
            group, stencil = "mechanical_hole_only", "no_paste_mechanical_hole"
            require(footprint.IsExcludedFromBOM() and footprint.IsExcludedFromPosFiles(),
                    f"Mechanical hole must be excluded from BOM/positions: {ref}")
        elif ref in HAND_SMD:
            require(bool(attrs & P.FP_SMD), f"Expected SMD connector: {ref}")
            group, stencil = "post_reflow_smd_connector_hand_solder", "no_paste_hand_solder_all_pads"
            note = "Fitted SMD connector; hand-solder after reflow, including shell/retention pads."
            if ref == "J501":
                note += " USB4105-GF-A short shell stakes require top-side joint/slot wetting inspection."
        elif attrs & P.FP_THROUGH_HOLE:
            require(ref in HAND_THT, f"Unreviewed through-hole part: {ref}")
            group, stencil = "post_reflow_tht_hand_solder", "no_paste_tht_hand_solder"
        else:
            require(bool(attrs & P.FP_SMD), f"Unclassified assembly technology: {ref}")
            group, stencil = "top_smd_reflow", "use_reviewed_r9_smd_stencil"
            if ref == "U301":
                stencil = "module_perimeter_only_epad_no_paste"
                note = "Module is fitted; reflow perimeter contacts, leave optional EPAD unprinted; verify thermal performance."
        fitted = not dnp and ref not in MECHANICAL
        require(not fitted or not footprint.IsExcludedFromBOM(),
                f"Fitted electrical part unexpectedly excluded from BOM: {ref}")
        require(not fitted or fields.get("Candidate_MPN", ""),
                f"Fitted component has no native candidate MPN: {ref}")
        x, y = mm(footprint.GetPosition().x), mm(footprint.GetPosition().y)
        rows.append({
            "reference": ref,
            "value": footprint.GetValue(),
            "footprint": footprint.GetFPIDAsString(),
            "side": board.GetLayerName(footprint.GetLayer()),
            "x_mm_from_board_lower_left": number(x - left),
            "y_mm_from_board_lower_left": number(bottom - y),
            "kicad_rotation_deg": number(footprint.GetOrientationDegrees()),
            "rotation_convention": ROTATION_NOTE,
            "kicad_x_mm": number(x), "kicad_y_mm": number(y),
            "assembly_group": group, "stencil_rule": stencil,
            "manufacturer": fields.get("Manufacturer", ""),
            "candidate_mpn": fields.get("Candidate_MPN", ""),
            "candidate_status": CANDIDATE_STATUS if ref not in MECHANICAL else "not_a_component",
            "dnp": str(dnp).lower(), "fitted": str(fitted).lower(),
            "excluded_from_bom": str(footprint.IsExcludedFromBOM()).lower(),
            "excluded_from_position_files": str(footprint.IsExcludedFromPosFiles()).lower(),
            "footprint_uuid": footprint.m_Uuid.AsString(),
            "bom_review_raw": fields.get("BOM_Review", ""),
            "bom_review_record_raw": fields.get("BOM_Review_Record", ""),
            "design_note_raw": fields.get("Design_Note", ""),
            "candidate_source_raw": fields.get("Candidate_Source", ""),
            "assembly_note": note,
        })
    counts = dict(Counter(row["assembly_group"] for row in rows))
    require(counts == GROUP_COUNTS, f"Unexpected assembly group counts: {counts}")
    require({r["reference"] for r in rows if r["assembly_group"] == "post_reflow_tht_hand_solder"} == HAND_THT,
            "Through-hole assembly set differs")
    require(sum(r["fitted"] == "true" for r in rows) == 230, "Fitted component count differs")
    return rows, {"board_extent_kicad_mm": extent, "counts": counts}


def make_bom(rows: list[dict]) -> list[dict]:
    key_columns = [column for column in BOM_COLUMNS if column not in {"references", "quantity"}]
    groups = defaultdict(list)
    for row in rows:
        if row["fitted"] == "true":
            groups[tuple(row[column] for column in key_columns)].append(row["reference"])
    bom = []
    for key, refs in groups.items():
        item = dict(zip(key_columns, key))
        refs.sort(key=natural)
        item.update(references=";".join(refs), quantity=len(refs))
        bom.append(item)
    bom.sort(key=lambda row: natural(row["references"].split(";")[0]))
    require(sum(row["quantity"] for row in bom) == 230, "Grouped BOM quantity differs")
    return bom


def assembly_map(rows: list[dict], source_hash: str) -> bytes:
    """Self-contained offline reference finder, drawn from the same CSV rows.

    Native data is escaped for its destination: HTML/XML text and attributes,
    or JSON within a script data block. Browser detail panels use textContent.
    No network request, external package, evaluated native field or innerHTML.
    """
    classes = {
        "top_smd_reflow": "reflow",
        "post_reflow_smd_connector_hand_solder": "hand-smd",
        "post_reflow_tht_hand_solder": "hand-tht",
        "do_not_populate": "dnp",
        "mechanical_hole_only": "hole",
    }
    points = []
    for row in rows:
        ref = html.escape(row["reference"], quote=True)
        x, y = number(float(row["kicad_x_mm"])), number(float(row["kicad_y_mm"]))
        label = html.escape(row["reference"] + " / " + row["value"])
        kind = classes[row["assembly_group"]]
        radius = "1.6" if kind == "hole" else "0.62"
        points.append(
            f'<g class="part {kind}" data-ref="{ref}" tabindex="0" role="button" '
            f'aria-label="{ref}" transform="translate({x} {y})">'
            f'<title>{label}</title><circle class="hit" r="1.2"/>'
            f'<circle class="anchor" r="{radius}"/>'
            f'<text class="ref-label" x="1" y="-1.1">{ref}</text></g>'
        )
    grid = [f'<path d="M{x} 50V160"/>' for x in range(60, 210, 10)]
    grid += [f'<path d="M50 {y}H210"/>' for y in range(60, 160, 10)]
    embedded = json.dumps({"source_board_sha256": source_hash, "rows": rows}, ensure_ascii=False, separators=(",", ":"))
    embedded = (embedded.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
                .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))
    template = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ESPaperPlay r9 · 装配查位</title>
<style>
:root{font-family:system-ui,-apple-system,"Noto Sans CJK SC",sans-serif;color:#182b38;background:#f3f6f8;line-height:1.5}
*{box-sizing:border-box}body{margin:0;padding:24px}main{max-width:1440px;margin:auto}
h1{font-size:25px;margin:0 0 6px}h2{font-size:17px;margin:0 0 12px}p{margin:7px 0}.muted{color:#586a77;font-size:13px}
header{margin-bottom:18px}.notice{background:#fff8dc;border-left:4px solid #cb9b28;padding:10px 14px;margin:12px 0}
.toolbar,.legend{display:flex;flex-wrap:wrap;align-items:center;gap:12px}.toolbar{padding:14px;background:#fff;border:1px solid #d7e0e6;border-radius:10px;margin-bottom:12px}
input[type=search]{width:280px;max-width:100%}input,select,button{font:inherit}input[type=search],select,button{border:1px solid #b8c7d1;border-radius:6px;padding:7px 10px;background:#fff;color:inherit}
button{cursor:pointer}button:hover{background:#ecf3f7}button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #a5c5e6;outline-offset:2px}
.layout{display:grid;grid-template-columns:minmax(0,1fr) 350px;gap:16px}.panel{background:#fff;border:1px solid #d7e0e6;border-radius:10px;padding:14px;min-width:0}
.map-scroll{width:100%;max-height:78vh;overflow:auto;background:#fbfcfd;border:1px solid #e1e7ec;border-radius:6px;margin:12px 0}
svg{display:block;width:100%;min-width:720px;height:auto;overflow:visible}.board{fill:#fff;stroke:#31505b;stroke-width:.35}.grid{stroke:#dce7eb;stroke-width:.12;pointer-events:none}
.part{cursor:pointer}.part .anchor{stroke:#fff;stroke-width:.15;fill:#2477bd}.part .hit{fill:transparent;stroke:none}.part.hand-smd .anchor{fill:#b44b12}.part.hand-tht .anchor{fill:#d99116}.part.dnp .anchor{fill:#9da8af;stroke:#596772;stroke-width:.14}.part.hole .anchor{fill:#fff;stroke:#596772;stroke-width:.25}
.ref-label{display:none;font-size:1.6px;font-weight:600;fill:#243a48;paint-order:stroke;stroke:#fff;stroke-width:.65;pointer-events:none}.show-labels .ref-label{display:block}
.part:hover .ref-label,.part:focus .ref-label,.part.selected .ref-label{display:block;font-size:2.2px;fill:#9d1549}.part.selected .anchor{fill:#d71962;stroke:#5c1639;stroke-width:.3}.part.selected .hit{stroke:#d71962;stroke-width:.3;fill:#ffdeeb;opacity:.6}
.part.hidden{display:none}.axis-label{font-size:2.1px;fill:#48606e;pointer-events:none}.legend{font-size:12px}.legend span::before{content:"";display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px;background:var(--swatch)}
.meta{overflow-wrap:anywhere}.meta dt{font-size:12px;color:#586a77;margin-top:9px}.meta dd{font-size:14px;margin:0}.selected-ref{font-size:26px;font-weight:700;color:#9d1549}
.result-list{display:grid;gap:5px;max-height:290px;overflow:auto;margin-top:9px}.result-item{text-align:left;display:flex;justify-content:space-between;gap:8px;font-size:12px;padding:6px 8px}.result-item strong{font-size:13px}.result-item.selected{border-color:#d71962;background:#fff1f6}.result-item span{max-width:215px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.results{border-top:1px solid #e1e7ec;margin-top:16px;padding-top:12px}footer{font-size:12px;color:#586a77;margin-top:16px;overflow-wrap:anywhere}a{color:#185f97}.detail-placeholder{padding:18px 0;color:#586a77}
@media(max-width:1000px){body{padding:14px}.layout{grid-template-columns:minmax(0,1fr)}.result-list{max-height:230px}.map-scroll{max-height:65vh}}
@media print{.toolbar,.results,.map-controls{display:none}.layout{display:block}svg{min-width:0!important;width:100%!important}.map-scroll{max-height:none;overflow:visible}body{padding:0}.panel{break-inside:avoid}.notice{display:block}}
</style>
</head>
<body><main>
<header><h1>ESPaperPlay r9 · 装配查位</h1>
<p class="muted">240 位号 · 203 回流 · 27 后手焊 · 6 DNP · 4 安装孔｜元件面顶视图</p>
<p class="notice">用于查找封装锚点，<strong>不是 1:1 装配定位模板，也不是贴片机文件</strong>。候选料号尚未采购冻结；角度保留 KiCad 原生定义。</p></header>
<section class="toolbar" aria-label="查位与筛选">
<label for="search">搜索 <input id="search" type="search" placeholder="位号 / 型号，例如 J601、R108" autocomplete="off"></label>
<label for="filter">工序 <select id="filter"><option value="all">全部 240</option><option value="reflow">回流 203</option><option value="hand">后手焊 27</option><option value="hand-smd">SMD 接口手焊 4</option><option value="hand-tht">THT 手焊 23</option><option value="dnp">DNP 6</option><option value="hole">安装孔 4</option></select></label>
<button id="clear" type="button">清除条件</button><span id="count" class="muted" role="status" aria-live="polite"></span>
</section>
<div class="layout"><section class="panel" aria-label="PCB 定位图">
<div class="toolbar map-controls"><label for="zoom">缩放 <input id="zoom" type="range" min="100" max="250" step="25" value="100"></label><output id="zoom-value" for="zoom">100%</output><label><input id="labels" type="checkbox"> 显示全部位号</label></div>
<div class="legend"><span style="--swatch:#2477bd">回流</span><span style="--swatch:#b44b12">SMD 接口手焊</span><span style="--swatch:#d99116">THT 手焊</span><span style="--swatch:#9da8af">DNP</span><span style="--swatch:#596772">安装孔</span></div>
<div class="map-scroll"><svg id="board-map" xmlns="http://www.w3.org/2000/svg" viewBox="45 44 170 122" role="img" aria-label="ESPaperPlay 顶层封装锚点图，板框160乘110毫米">
<title>PCB 顶视图：KiCad X 向右，Y 向下，点击位号查看装配信息</title>
<rect class="board" x="50" y="50" width="160" height="110"/>
<g class="grid">__GRID__</g>
<text class="axis-label" x="50" y="47">TOP / 元件面 · KiCad X → Y ↓</text><text class="axis-label" x="210" y="47" text-anchor="end">160 × 110 mm</text>
<text class="axis-label" x="50" y="164">CSV 原点：板左下 (0, 0)；KiCad (50, 160)</text>
<g id="parts">__POINTS__</g></svg></div>
<p class="muted">点为原生封装锚点，不一定是元件几何中心。网格 10 mm；实际焊盘、器件外形及针 1 标记请对照正式 PCB。点击地图或右侧位号查看详情。</p>
</section><aside class="panel" aria-label="位号详情与匹配清单">
<h2>位号详情</h2><div id="details" aria-live="polite"><p class="detail-placeholder">点选地图或下方清单中的位号。</p></div>
<div class="results"><h2>匹配清单</h2><div id="result-list" class="result-list"></div></div>
</aside></div>
<footer>来源：冻结 r8 PCB SHA-256 <span>__HASH__</span>。全部数据嵌入本文件，可离线打开。<a href="population.csv">完整 population.csv</a> · <a href="hand-solder.csv">手焊清单</a> · <a href="dnp.csv">DNP 清单</a><br>本图不替代钢网、机械尺寸、焊点及首次上电检查；U301 外围回流，中心 EPAD 按本次工艺不印膏。</footer>
</main>
<script id="assembly-data" type="application/json">__DATA__</script>
<script>
"use strict";
const dataset = JSON.parse(document.getElementById("assembly-data").textContent);
const rows = dataset.rows;
const groups = {
  top_smd_reflow: ["reflow", "回流"],
  post_reflow_smd_connector_hand_solder: ["hand-smd", "SMD 接口后手焊"],
  post_reflow_tht_hand_solder: ["hand-tht", "THT 后手焊"],
  do_not_populate: ["dnp", "DNP · 不装且不印膏"],
  mechanical_hole_only: ["hole", "安装孔 · 不装元件"]
};
const search = document.getElementById("search"), filter = document.getElementById("filter");
const partNodes = new Map(Array.from(document.querySelectorAll(".part")).map(node => [node.dataset.ref, node]));
const list = document.getElementById("result-list"), details = document.getElementById("details");
let selected = null;
function matches(row) {
  const category = groups[row.assembly_group][0], wanted = filter.value;
  const allowed = wanted === "all" || category === wanted || (wanted === "hand" && category.startsWith("hand-"));
  const query = search.value.trim().toUpperCase();
  const haystack = [row.reference, row.value, row.candidate_mpn, row.manufacturer].join(" ").toUpperCase();
  return allowed && (!query || haystack.includes(query));
}
function field(dl, title, value) {
  const dt = document.createElement("dt"), dd = document.createElement("dd");
  dt.textContent = title; dd.textContent = value || "—"; dl.append(dt, dd);
}
function showDetails(row) {
  details.replaceChildren();
  if (!row) {
    const p = document.createElement("p"); p.className = "detail-placeholder";
    p.textContent = "点选地图或下方清单中的位号。"; details.append(p); return;
  }
  const ref = document.createElement("div"); ref.className = "selected-ref"; ref.textContent = row.reference;
  const dl = document.createElement("dl"); dl.className = "meta";
  field(dl, "装配工序", groups[row.assembly_group][1]);
  field(dl, "数值 / 名称", row.value);
  field(dl, "Candidate_MPN（原生候选，未采购冻结）", row.candidate_mpn);
  field(dl, "制造商", row.manufacturer);
  field(dl, "封装", row.footprint);
  field(dl, "KiCad 原生角度（不是供料角度）", Number(row.kicad_rotation_deg) + "°");
  field(dl, "顶视图 KiCad 锚点 X, Y", Number(row.kicad_x_mm) + ", " + Number(row.kicad_y_mm) + " mm");
  field(dl, "CSV 板左下坐标 X, Y", Number(row.x_mm_from_board_lower_left) + ", " + Number(row.y_mm_from_board_lower_left) + " mm");
  field(dl, "原生 DNP / 所在面", row.dnp + " / " + row.side);
  field(dl, "钢网规则", row.stencil_rule);
  if (row.assembly_note) field(dl, "本次装配注记", row.assembly_note);
  details.append(ref, dl);
}
function choose(reference) {
  selected = reference;
  for (const [ref, node] of partNodes) node.classList.toggle("selected", ref === selected);
  for (const button of list.children) button.classList.toggle("selected", button.dataset.ref === selected);
  showDetails(rows.find(row => row.reference === reference));
}
function render() {
  const visible = rows.filter(matches), refs = new Set(visible.map(row => row.reference));
  if (!refs.has(selected)) selected = null;
  for (const [ref, node] of partNodes) {
    node.classList.toggle("hidden", !refs.has(ref));
    node.classList.toggle("selected", ref === selected);
    node.setAttribute("tabindex", refs.has(ref) ? "0" : "-1");
  }
  document.getElementById("count").textContent = "显示 " + visible.length + " / " + rows.length + " 个位号";
  list.replaceChildren();
  for (const row of visible) {
    const button = document.createElement("button"), ref = document.createElement("strong"), value = document.createElement("span");
    button.type = "button"; button.className = "result-item"; button.dataset.ref = row.reference;
    button.classList.toggle("selected", row.reference === selected);
    ref.textContent = row.reference; value.textContent = row.candidate_mpn || row.value;
    button.title = row.reference + " / " + groups[row.assembly_group][1] + " / " + row.value;
    button.append(ref, value); button.addEventListener("click", () => choose(row.reference)); list.append(button);
  }
  showDetails(selected ? rows.find(row => row.reference === selected) : null);
}
for (const [ref, node] of partNodes) {
  node.addEventListener("click", () => choose(ref));
  node.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); choose(ref); } });
}
search.addEventListener("input", render); filter.addEventListener("change", render);
document.getElementById("clear").addEventListener("click", () => { search.value = ""; filter.value = "all"; render(); });
document.getElementById("labels").addEventListener("change", event => document.getElementById("parts").classList.toggle("show-labels", event.target.checked));
document.getElementById("zoom").addEventListener("input", event => {
  document.getElementById("board-map").style.width = event.target.value + "%";
  document.getElementById("zoom-value").textContent = event.target.value + "%";
});
render();
</script>
</body></html>
'''
    result = (template.replace("__GRID__", "".join(grid)).replace("__POINTS__", "".join(points))
              .replace("__HASH__", html.escape(source_hash, quote=True)).replace("__DATA__", embedded))
    return result.encode("utf-8")


def export(board_path: Path, output: Path) -> dict:
    source_hash = digest(board_path)
    require(source_hash == FROZEN_SHA256,
            f"Source PCB SHA differs from reviewed r8: {source_hash}; no output generated")
    board = P.LoadBoard(str(board_path))
    require(board is not None, "Cannot load native PCB")
    rows, geometry = get_rows(board)
    reflow = [row for row in rows if row["assembly_group"] == "top_smd_reflow"]
    hand = [row for row in rows if row["assembly_group"].startswith("post_reflow_")]
    dnp = [row for row in rows if row["dnp"] == "true"]
    bom = make_bom(rows)
    files = {
        "population.csv": csv_bytes(rows, POPULATION_COLUMNS),
        "reflow-positions.csv": csv_bytes(reflow, POSITION_COLUMNS),
        "hand-solder.csv": csv_bytes(hand, POPULATION_COLUMNS),
        "bom-fitted.csv": csv_bytes(bom, BOM_COLUMNS),
        "dnp.csv": csv_bytes(dnp, POPULATION_COLUMNS),
        "assembly-map.html": assembly_map(rows, source_hash),
    }
    require(digest(board_path) == source_hash, "Source PCB changed during native read")
    summary = {
        "schema_version": 1, "revision": "r9-review", "status": "REVIEW_ONLY_NOT_PROCUREMENT_FROZEN",
        "source_board": relative(board_path), "source_board_sha256": source_hash,
        "source_unchanged_after_native_read": True,
        "generator": relative(Path(__file__)), "generator_sha256": digest(Path(__file__)),
        "native_reader": f"KiCad pcbnew {P.GetBuildVersion()}",
        "scope": "User-assembled stencil reflow plus connector/header hand soldering; no external PCBA upload format.",
        "candidate_mpn_status": "All MPNs are copied from native Candidate_MPN fields; not procurement-frozen or stock-verified.",
        "coordinates": {
            "origin": "physical_board_lower_left", "origin_in_kicad_mm": [50.0, 160.0],
            "x_mm": "KiCadX - 50", "y_mm": "160 - KiCadY", "positive_axes": "X right, Y up",
            "position_reference": "native footprint anchor, not necessarily package centroid",
            "rotation": "unmodified native KiCad footprint angle; not feeder orientation or vendor PnP convention",
            "side": "F.Cu for all electrical parts", "board_extent_kicad_mm": geometry["board_extent_kicad_mm"],
        },
        "counts": {"population_rows": len(rows), "electrical_references": 236, "fitted_electrical_references": 230,
                   "reflow_position_rows": len(reflow), "hand_solder_rows": len(hand), "bom_group_rows": len(bom),
                   "bom_total_quantity": sum(row["quantity"] for row in bom), "dnp_rows": len(dnp),
                   "by_assembly_group": geometry["counts"]},
        "groups": {group: [row["reference"] for row in rows if row["assembly_group"] == group]
                   for group in GROUP_COUNTS},
        "assembly_rules": {
            "dnp": "No fitting and no stencil apertures; native DNP alone does not suppress plotted paste.",
            "manual_smd_connectors": "J406/J501/J601/J701 fitted after reflow by hand; omit all signal and shell apertures.",
            "tht": "Headers, terminal blocks and switches fitted after reflow by hand; no paste.",
            "u301": "Fitted module; perimeter contacts reflow, optional central EPAD unprinted; thermal validation remains.",
            "other_smd": "Use the separately reviewed r9 stencil; this exporter does not generate or qualify paste geometry.",
            "native_metadata": "BOM_Review/Design_Note fields are preserved verbatim, including historical candidate cautions.",
        },
        "assembly_map": {
            "file": "assembly-map.html", "embedded_rows": len(rows), "network_dependencies": 0,
            "coordinates": "Native KiCad top-view X right, Y down; SVG uses native footprint anchors.",
            "interaction": "Offline reference/MPN search, assembly-group filtering, click/keyboard details, label toggle and zoom.",
            "limitations": "Anchor lookup only, not a 1:1 assembly template, footprint-body drawing, pin-1 drawing or PnP file.",
        },
        "files": {name: {"sha256": hashlib.sha256(data).hexdigest(), "encoding": "UTF-8", "line_ending": "LF"}
                  for name, data in files.items()},
    }
    # All board/profile assertions above complete before any output is replaced.
    output.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (output / name).write_bytes(data)
    (output / "assembly-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    require(digest(board_path) == source_hash, "Source PCB changed during export")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", type=Path, default=BOARD, help="Must match the frozen reviewed r8 SHA-256")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    try:
        result = export(args.board.resolve(), args.output.resolve())
    except (ValueError, OSError) as error:
        parser.exit(2, f"Assembly export refused: {error}\n")
    print(json.dumps({"output": relative(args.output), "source_board_sha256": result["source_board_sha256"],
                      "counts": result["counts"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
