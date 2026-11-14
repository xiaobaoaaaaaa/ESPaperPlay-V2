#!/usr/bin/env python3
"""Derive a local two-board material plan from the immutable r10 assembly export."""
from __future__ import annotations

import csv
import hashlib
import html
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "hardware/devboard-r0/output/manufacturing/r10-review"
OUT = ROOT / "hardware/devboard-r0/output/manufacturing/r10-first-batch"
BOARD = ROOT / "hardware/devboard-r0/ESPaperPlay_Devboard.kicad_pcb"
PCB_COUNT = 5
ASSEMBLY_COUNT = 2


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def natural(ref: str) -> tuple[str, int]:
    prefix = ref.rstrip("0123456789")
    return prefix, int(ref[len(prefix):])


def make_plan() -> dict:
    index = json.loads((SOURCE / "artifact-index.json").read_text())
    assert digest(BOARD) == index["source_board_sha256"], "r10 PCB baseline changed"
    for name, expected in index["sha256"].items():
        assert digest(SOURCE / name) == expected, f"r10 artifact changed: {name}"
    with (SOURCE / "assembly/population.csv").open(newline="") as file:
        population = list(csv.DictReader(file))
    assert len(population) == 240
    assert len({p["reference"] for p in population}) == 240
    groups = defaultdict(list)
    fitted = [p for p in population if p["fitted"] == "true"]
    dnp = sorted((p["reference"] for p in population if p["dnp"] == "true"), key=natural)
    assert len(fitted) == 230
    assert dnp == ["C501", "C502", "J301", "J302", "J303", "R108"]
    for part in fitted:
        key = part["manufacturer"], part["candidate_mpn"], part["footprint"]
        assert all(key), f"Missing candidate identity: {part['reference']}"
        groups[key].append(part)
    items = []
    for (manufacturer, mpn, footprint), parts in sorted(groups.items(), key=lambda g: natural(g[1][0]["reference"])):
        refs = sorted((p["reference"] for p in parts), key=natural)
        base = len(parts) * ASSEMBLY_COUNT
        passive = all(r.startswith(("R", "C")) for r in refs)
        # Optional handling/rework stock, not MOQ or a vendor availability claim.
        spare = max(5, math.ceil(base * .10)) if passive else (0 if refs == ["U301"] else 1)
        notes = []
        if any(r in refs for r in ("C101", "C102", "C103", "C201", "C202", "C601", "C602", "C604", "C607", "C608", "C609", "C610")):
            notes.append("关键MLCC：按关键电容审查落实有效容量；不能仅凭标称容量替代偏压审核")
        if "U801" in refs:
            notes.append("固定Nexperia 74LVC125APW,118；不能直接按同名TI系列代换")
        if "U803" in refs:
            notes.append("核对生命周期、可采购原包装及干燥/回流条件；首测48kHz/64fs")
        if any(r in refs for r in ("J406", "J601")):
            notes.append("实物核对0.5mm间距、接触面、1脚和延长排线通断；回流后手焊")
        if "R101" in refs:
            notes.append("测流断点用金属低阻跳线；不可按普通0603零欧替换")
        if any(r in refs for r in ("R201", "R202")):
            notes.append("保持0.1% / 25ppm反馈精度，不以普通1%替换")
        if "J105" in refs:
            notes.append("J105可焊排针但不得装跳帽；J104也保持开放")
        items.append({
            "id": hashlib.sha256("|".join((manufacturer, mpn, footprint)).encode()).hexdigest()[:12],
            "manufacturer": manufacturer, "candidate_mpn": mpn, "footprint": footprint,
            "references_per_board": refs, "design_values": sorted({p["value"] for p in parts}),
            "quantity_per_board": len(parts), "assembly_boards": ASSEMBLY_COUNT,
            "required_quantity": base, "suggested_optional_spares": spare,
            "suggested_material_quantity": base + spare,
            "inventory_quantity": None, "vendor_moq": None, "unit_price_cny": None,
            "purchase_quantity": None,
            "candidate_status": "NOT_PROCUREMENT_FROZEN",
            "assembly_groups": dict(Counter(p["assembly_group"] for p in parts)),
            "notes": notes,
            "candidate_sources": sorted({s.strip() for p in parts for s in p["candidate_source_raw"].split("|") if s.strip()}),
        })
    assert len(items) == 64
    assert sum(p["quantity_per_board"] for p in items) == 230
    assert sum(p["required_quantity"] for p in items) == 460
    return {
        "schema_version": 1, "date": "2026-11-14", "preparation_revision": "r11",
        "pcb_revision": "r10", "status": "LOCAL_PREPARATION_NOT_ORDERED",
        "user_confirmed": {"pcb_quantity": PCB_COUNT, "assembly_quantity": ASSEMBLY_COUNT,
                           "stencil": "one_frameless_stencil_tape_hinge_manual_alignment"},
        "source_board_sha256": digest(BOARD),
        "source_population": str((SOURCE / "assembly/population.csv").relative_to(ROOT)),
        "source_population_sha256": digest(SOURCE / "assembly/population.csv"),
        "source_artifact_index_sha256": digest(SOURCE / "artifact-index.json"),
        "generator": str(Path(__file__).relative_to(ROOT)), "generator_sha256": digest(Path(__file__)),
        "quantity_policy": "Exact manufacturer + complete candidate MPN + footprint; descriptive values and assembly groups may differ and are retained. No electrical substitutions. Two-board demand; R/C optional spares=max(5,ceil(10% demand)), other groups +1, ESP32 module +0. Counts exclude supplier MOQ and unknown inventory; no net purchase quantity or quote is claimed.",
        "counts": {"procurement_groups": len(items), "fitted_per_board": 230,
                   "required_two_boards": 460, "reflow_two_boards": 406,
                   "hand_solder_two_boards": 54, "dnp_per_board": 6,
                   "optional_spares": sum(p["suggested_optional_spares"] for p in items),
                   "suggested_materials": sum(p["suggested_material_quantity"] for p in items)},
        "dnp_excluded": dnp,
        "external_items": [
            {"item": "2.54mm两针绝缘跳帽", "required_quantity": 4, "optional_spares": 2,
             "notes": "每板只给J202与J502各一个；换档必须断电，J105开放。采购前核对排针配合。"},
            {"item": "已有7.5寸屏幕、GT911及FP24/FP6纯延长件", "required_quantity": 1,
             "notes": "现有一套可逐板复用；不自动计入新购。"},
            {"item": "已选3525腔体8Ω2W扬声器", "required_quantity": 1,
             "notes": "逐板复用；J801为开发端子，线束端接另处理，BTL两端均不接地。"},
            {"item": "755570 4000mAh 1S保护电池及10k NTC", "required_quantity": 0,
             "notes": "第一阶段先不接真实电池；NTC身份/极性未实物核对前保持禁充。后续电池测试另备。"},
            {"item": "合规台架电源/万用表/示波器/显微镜/回流设备及锡膏", "required_quantity": None,
             "notes": "核对已有工具；锡膏合金与回流曲线、MSL处理按实际购入器件/锡膏资料确定。"},
        ],
        "items": items,
    }


def render_html(plan: dict) -> str:
    esc = html.escape
    rows = []
    for item in plan["items"]:
        refs = " / ".join(item["references_per_board"])
        notes = "；".join(item["notes"]) or "核对准确料号、封装及来料状态"
        rows.append("<tr>" + "".join(f"<td>{value}</td>" for value in (
            f"<strong>{esc(item['candidate_mpn'])}</strong><br><small>{esc(item['manufacturer'])}</small>",
            f"{esc(refs)}<br><small>{esc(item['footprint'])}</small>",
            str(item["quantity_per_board"]), str(item["required_quantity"]),
            str(item["suggested_optional_spares"]), str(item["suggested_material_quantity"]),
            esc(notes))) + "</tr>")
    c = plan["counts"]
    return """<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ESPaperPlay r10 · 首批备料</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f6f8;color:#192b39;font:15px/1.65 system-ui,sans-serif}main{max-width:1500px;margin:auto;padding:30px}h1{font-size:28px;margin:0}p{max-width:1000px}a{color:#176894}header,.info{background:white;padding:24px;border-radius:12px;margin-bottom:18px}.meta{color:#536779}.stats{display:flex;gap:14px;flex-wrap:wrap}.stat{padding:14px 24px;background:#eaf3f7;border-radius:8px}.stat b{font-size:28px;display:block}input{font:inherit;padding:10px;width:min(600px,100%);border:1px solid #9aaebb;border-radius:7px}.scroll{overflow:auto;background:white;border-radius:8px}table{width:100%;min-width:1050px;border-collapse:collapse}th,td{padding:13px;text-align:left;border-bottom:1px solid #e0e8ed;vertical-align:top}th{background:#203c50;color:white;white-space:nowrap}td:nth-child(n+3):nth-child(-n+6){text-align:right;font-variant-numeric:tabular-nums}td:first-child{width:19%}td:nth-child(2){width:28%}td:last-child{width:27%}small{font-size:12px;color:#607786;overflow-wrap:anywhere}strong{overflow-wrap:anywhere}button{font:inherit;padding:9px 18px;margin-left:12px;cursor:pointer}.note{border-left:4px solid #cf9a2f;padding-left:16px}footer{padding:20px 0;color:#536779}tr[hidden]{display:none}@media print{body{background:white}main{padding:0}.scroll{overflow:visible}table{min-width:0;font-size:10px}th,td{padding:5px}header,.info{padding:10px}input,button,.filter{display:none}thead{display:table-header-group}tr{break-inside:avoid}tr[hidden]{display:table-row}h1{font-size:22px}}
</style><main><header><div class="meta">2026-11-14 · 准备记录 r11 / PCB 保持 r10</div><h1>首批备料：5 块 PCB，先焊 2 块</h1>
<p>按相同厂商、完整候选料号与封装合并采购行，保留所有位号。库存、单价、最小起订量尚未核实；以下为需求和可选备料，不是采购订单。</p><div class="stats">""" + "".join(
        f'<div class="stat"><b>{n}</b>{label}</div>' for n, label in (
            (64, "种候选物料"), (460, "件装配净需求"),
            (c["optional_spares"], "件可选备料"), (c["suggested_materials"], "件含备料总量"))) + """</div></header>
<section class="info"><p class="note">R108、C501/C502、J301/J302/J303 不装；J105 不装跳帽。先焊一块验证印膏与焊接，再做第二块。关键 MLCC 的有效容量、来料和首板验证仍需按审查记录落实。</p><p>无框钢网，胶带铰链定位；仅使用 r10 独立 DIY 钢网文件。<a href="../r10-review/assembly/assembly-map.html">装配查位图</a> · <a href="../../../review-r11/component-closure.md">物料闭合审查</a> · <a href="../../../review-r11/first-board-checklist.md">首板检查</a> · <a href="procurement-plan.json">完整数据及来源</a> · <a href="README.md">本批准备说明</a></p>
<label class="filter" for="search">搜索料号、位号、厂商或备注：</label><br><input id="search" type="search" placeholder="例如 TPS63802、C202、J105"><button onclick="window.print()">打印全部物料</button><p id="shown" aria-live="polite">显示 64 / 64 种物料</p></section>
<div class="scroll"><table><thead><tr><th>候选料号 / 厂商</th><th>位号 / 封装</th><th>单板</th><th>2板净需</th><th>可选备料</th><th>含备料</th><th>来料与装配备注</th></tr></thead><tbody>""" + "".join(rows) + """</tbody></table></div>
<footer>备料规则：电阻/电容取 max(5，需求量的10%向上取整)；其他每种加1件，ESP32模组不预加。均可按库存调整，未计供应商MOQ。两板另需4个2.54mm跳帽，可备2个；现有屏幕/延长件与扬声器可逐板复用。首测所需仪器、线材和锡膏见完整数据。合计不含DNP、机械孔、跳帽及外接件。</footer></main>
<script>const rows=[...document.querySelectorAll('tbody tr')];document.querySelector('#search').addEventListener('input',e=>{const q=e.target.value.trim().toLowerCase();let n=0;for(const r of rows){r.hidden=!r.textContent.toLowerCase().includes(q);if(!r.hidden)n++;}document.querySelector('#shown').textContent=`显示 ${n} / ${rows.length} 种物料`;});</script></html>"""


def main() -> None:
    plan = make_plan()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "procurement-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
    (OUT / "procurement-plan.html").write_text(render_html(plan))
    print(json.dumps(plan["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
