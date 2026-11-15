# 99 mm KiCad 复核工具

## 当前 r13：U101 普通热孔与钢网

`check_u101_r13.py` 独立读取 PCB、本地库及实际 Gerber / Excellon，比较 r12 Git 基线；所有 KiCad CLI 命令在临时项目副本执行，不回写正式 `.kicad_pro`。依赖 KiCad 10、Python `pcbnew`、Shapely、Gerbonara；局部预览另需 CairoSVG。

```sh
python hardware/devboard-99/tools/check_u101_r13.py \
  --board hardware/devboard-99/ESPaperPlay_99.kicad_pcb \
  --report-dir hardware/devboard-99/review-r13 \
  --work-dir build/pcb-99/r13-recheck \
  --baseline-revision 63ced99 \
  --paste-design rounded-hole-keepouts \
  --paste-span 1.55 --keepout-half-square 0.105 \
  --keepout-radius 0.25500680039330276 \
  --hole-offset 0.63 --mask-margin 0.02 \
  --registration-limit 0.03 --edge-error-limit 0.02
```

默认 `.kicad_pro` hash 为本次修改前用户已修正工程名称后的版本；若今后有授权的工程设置修改，应重新审查并显式更新预期 hash，不应绕过保护。检查的 PASS 只证明当前修订范围内的 CAD、电气保持、导出及指定包络的几何结果。实际孔径/孔位含义、阻焊对位、印刷和热性能的边界见 [r13 报告](../review-r13/README.md)。报告目录内的 CAM 仅用于审查，禁止用于未布线板的生产。

## 历史 r12：布局基线

依赖 KiCad 10 的 `kicad-cli`、Python `pcbnew`、Shapely；图像渲染另用 CairoSVG。当前验证环境为 KiCad 10.0.8。命令从仓库根目录执行。

```sh
kicad-cli sch export netlist --format kicadxml \
  --output hardware/devboard-99/review-r12/netlist.xml \
  hardware/devboard-99/ESPaperPlay_99.kicad_sch
kicad-cli pcb drc --format json --schematic-parity \
  --output hardware/devboard-99/review-r12/native-drc.json \
  hardware/devboard-99/ESPaperPlay_99.kicad_pcb
kicad-cli sch erc --format json \
  --output hardware/devboard-99/review-r12/native-erc.json \
  hardware/devboard-99/ESPaperPlay_99.kicad_sch
python hardware/devboard-99/tools/check_compact_layout.py \
  --board hardware/devboard-99/ESPaperPlay_99.kicad_pcb \
  --baseline hardware/devboard-r0/ESPaperPlay_Devboard.kicad_pcb \
  --netlist hardware/devboard-99/review-r12/netlist.xml \
  --report hardware/devboard-99/review-r12/layout-validation.json
python hardware/devboard-99/tools/check_operation_envelopes.py \
  --board hardware/devboard-99/ESPaperPlay_99.kicad_pcb \
  --output hardware/devboard-99/review-r12/operation-envelopes.json
```

`check_compact_layout.py` 不导入布局生成器；逐个比较焊盘相对几何/网络/DNP、模组本地库和制造规则，并检查裸板、庭院及原有禁布区。它明确要求零走线/零过孔/零铺铜，是 **r12 布局阶段**检查器；r13 新增的 U101 实际 PTH 与钢网须使用上述 r13 检查器，不应覆盖 r12 历史结果。开始布线后也需进入新的阶段检查，不能删除断言把新阶段结果伪装成原阶段结果。

`add_thermal_reservations.py` 接收内存中的 pcbnew BOARD；`add_reservations` 可增补 Dwgs.User 预留图形，不保存 PCB。正式板复核使用只读入口 `check_reservations(board, report_path)`，它核验现有标注和孔位、输出 JSON，不修改内存板。圆圈与真实 via 对象有本质区别，不能输出钻孔或接通 GND。

`check_operation_access.py` 独立核验操作包络及原生 Dwgs.User 标注；`check_manufacturing_negative.py` 在临时工程中插入故意违反制造规则的 via，检验原生 DRC 是否拒绝，不能用这些反例工程制造。实际参数见各脚本 `--help`。

`render_layout.py --board hardware/devboard-99/ESPaperPlay_99.kicad_pcb --output hardware/devboard-99/review-r12` 导出原生顶面、装配和操作空间 SVG/PNG。装配图使用临时副本隐藏重复的 Fab 内部标号；正式 PCB 不变。机械图扩大 SVG 视口显示板外天线和线束空间。

操作包络是基于当前明确方向的工程余量，移动或旋转接口后必须重审脚本中的方向/包络，不可仅重跑后沿用旧假设。正式投产还需布线 DRC、地连通、阻抗/压降复核及全新 CAM，以上工具均不能代替这些检查。
