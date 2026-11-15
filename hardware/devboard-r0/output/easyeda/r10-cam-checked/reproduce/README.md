# 复现说明

本目录脚本只读检查，不连接或修改嘉立创客户端。现场严格DRC结果保存在`../review/final-drc.json`，不能由离线脚本重新执行；若编辑工程，必须重新铺铜、执行严格DRC并导出。

环境：本次使用KiCad 10.0.8的系统`pcbnew`、Python 3.15、gerbonara 1.6.3、shapely 2.2.0；预览另需cairosvg 2.9.1。可用带`--system-site-packages`的虚拟环境安装后三项，不必改全局Python。

以下从仓库根目录执行，`TASK_PY`改为能导入上述库的Python。`TASK_CAM`是本目录上一级；`TASK_TMP`是可重建的检查目录。脚本通过参数接收路径，报告里旧build路径只作输入来源记录。

```sh
TASK_PY=python3
TASK_CAM=hardware/devboard-r0/output/easyeda/r10-cam-checked
TASK_TMP=build/easyeda-cam-recheck
mkdir -p "$TASK_TMP/inputs" "$TASK_TMP/final" "$TASK_TMP/source" "$TASK_TMP/previous" "$TASK_TMP/stencil" "$TASK_TMP/reports"
unzip -q "$TASK_CAM/snapshots.zip" -d "$TASK_TMP/inputs"
unzip -q "$TASK_CAM/Gerber-full-audit-only.zip" -d "$TASK_TMP/final"
unzip -q hardware/devboard-r0/output/manufacturing/r10-review/ESPaperPlay-r10-board-REVIEW_ONLY.zip -d "$TASK_TMP/source"
unzip -q hardware/devboard-r0/output/easyeda/r10-checked/Gerber-migration-review-only.zip -d "$TASK_TMP/previous"
unzip -q "$TASK_CAM/ESPaperPlay-r10-DIY-stencil-REVIEW_ONLY.zip" -d "$TASK_TMP/stencil"
```

主要检查（复现报告应写入临时目录，避免覆盖归档证据）：

```sh
"$TASK_PY" "$TASK_CAM/reproduce/audit_export_snapshot_cam.py" "$TASK_CAM/ESPaperPlay-V2-r10-CAM-final.epro2" --pcb-source "$TASK_TMP/inputs/final-pcb-source.txt" --paste-repair "$TASK_TMP/inputs/paste-layer-repair.json" --report "$TASK_TMP/reports/archive.json"
"$TASK_PY" "$TASK_CAM/reproduce/footprints/audit_footprints.py" --board hardware/devboard-r0/ESPaperPlay_Devboard.kicad_pcb --source "$TASK_TMP/inputs/final-pcb-source.txt" --footprints "$TASK_TMP/inputs/final-footprint-sources.json" --npth-repairs "$TASK_TMP/inputs/npth-repair-requests.json" --output "$TASK_TMP/reports/pads.json"
"$TASK_PY" "$TASK_CAM/reproduce/footprints/audit_mask_flash.py" --eda-dir "$TASK_TMP/final" --kicad-dir "$TASK_TMP/source" --pad-audit "$TASK_TMP/reports/pads.json" --output "$TASK_TMP/reports/mask.json"
"$TASK_PY" "$TASK_CAM/reproduce/footprints/audit_npth.py" --eda-dir "$TASK_TMP/final" --pad-audit "$TASK_TMP/reports/pads.json" --output "$TASK_TMP/reports/npth.json"
"$TASK_PY" "$TASK_CAM/reproduce/footprints/audit_copper_pad_flash.py" --eda-dir "$TASK_TMP/final" --kicad-dir "$TASK_TMP/source" --pad-audit "$TASK_TMP/reports/pads.json" --output "$TASK_TMP/reports/pad-copper.json"
"$TASK_PY" "$TASK_CAM/reproduce/footprints/audit_u803_ring.py" --eda-dir "$TASK_TMP/final" --kicad-dir "$TASK_TMP/source" --cache "$TASK_TMP/cache" --output "$TASK_TMP/reports/u803.json"
"$TASK_PY" "$TASK_CAM/reproduce/drills/compare_repaired_inner.py" --board hardware/devboard-r0/ESPaperPlay_Devboard.kicad_pcb --source-dir "$TASK_TMP/source" --previous-eda-dir "$TASK_TMP/previous" --eda-dir "$TASK_TMP/final" --cache "$TASK_TMP/cache" --output "$TASK_TMP/reports/inner.json"
"$TASK_PY" "$TASK_CAM/reproduce/drills/audit_inner_repairs.py" --source-footprints "$TASK_TMP/inputs/before-footprint-sources.json" --current-footprints "$TASK_TMP/inputs/final-footprint-sources.json" --pcb-source "$TASK_TMP/inputs/final-pcb-source.txt" --thermal-requests "$TASK_TMP/inputs/thermal-repair-requests.json" --pour-requests "$TASK_TMP/inputs/pour-neck-repair-requests.json" --comparison-report "$TASK_TMP/reports/inner.json" --witnesses "$TASK_TMP/inputs/narrow-neck-witnesses.json" --output "$TASK_TMP/reports/inner-closure.json"
"$TASK_PY" "$TASK_CAM/reproduce/audit_outer_cam.py" --source-dir "$TASK_TMP/source" --eda-dir "$TASK_TMP/final" --cache "$TASK_TMP/cache" --pcb-source "$TASK_TMP/inputs/final-pcb-source.txt" --fill-cap-csv "$TASK_TMP/inputs/final-fill-cap-map.csv" --report "$TASK_TMP/reports/outer.json"
```

完整锡膏/装配审查可用`paste/audit_paste_assembly_final.py`，参数见`--help`：原通用F.Paste/B.Paste已放入`snapshots.zip`；专用钢网在独立钢网ZIP；装配CSV位于原r10制造资料的`assembly/population.csv`。最终证据还包含`repaired1`完整几何检查与最终操作不变量链：`compare_paste_operations.py --before ... --after ... --ignore-zero-length-region-edges --report ...`只去除同一点之间的零长度直边，零坐标容差。丝印比较不传该选项。

原生源差异由`audit_source_changes.py`记录；`audit_final_netlists_cam.py`的`--allowed-cam-delta`只接受绑定到同一对源哈希的明确FILL/POUR修复。完整命令参数可用各脚本`--help`查看。新增板级FILL用于恢复U403铜端帽，不是新增过孔或网络。

`verify_bundle.py`是轻量归档检查：核对哈希、ZIP成员、实际文件一致性和报告状态；它不替代上面的几何计算。所有脚本复现的是本次已列明范围，不代表通用格式解析器或工厂验收工具。
