# 99 mm KiCad 复核工具

## 当前 r14：布线、地平面及实际 CAM 复核

命令从仓库根目录执行。依赖 KiCad 10 的 `kicad-cli` 与同版本 Python `pcbnew`，以及 NumPy、Shapely、Gerbonara；局部图像预览另需 CairoSVG。Python 环境必须能导入上述模块。以下工具读取现有布线和已保存的铺铜，不负责自动布线或修改正式 CAD；报告和 CLI 导出物统一写入 `build/`。

| 工具 | 检查范围 |
| --- | --- |
| `check_r14_structure.py` | 对照 r13 保留器件、封装、位置、焊盘及电气分配；检查 99 × 99 mm 外形、四层结构、制造规则、真实热孔、实际内层 GND 连通和原生 DRC 结果。 |
| `audit_via_manufacturing.py` | 普通过孔孔口到正反面焊盘阻焊开窗的名义距离，以及全部圆孔、槽孔之间的孔边距。封装内有意设置的 PTH 单独列出，不把普通热过孔排除在检查之外。 |
| `check_reference_planes.py` | 检查关键走线在实际已填充 GND 上的投影、局部参考面边缘和换层回流连接；按实际铜环与两内层的接触计入 GND PTH，不只检查铺铜轮廓。 |
| `analyze_display_paths.py` | 分别量取显示信号 MCU 到缓冲器、MCU 到调试排针及排针到缓冲器的路径，并记录换层和调试支路。 |
| `check_u101_r14_cam.py` | 在临时副本导出真实 Gerber / Excellon，与 r13 比较 U101 四个普通开孔、正反面阻焊及钢网形状；复核钢网公差包络和两内层 GND 实连。仅复用 r13 几何函数，不执行旧阶段主检查。 |
| `../../devboard-r0/tools/analyze_signal_paths.py` | 复用已有路径分析器检查 USB、六条 SD 主路径及调试支路。 |
| `../../devboard-r0/tools/check_power_route_budget.py` | 使用本目录 `power-route-rules-r14.json` 复核 24 条电源路径的线宽、细颈、估算电阻与压降预算。必须显式指定 r14 规则，不能沿用工具的默认旧规则。 |

### 准备独立项目副本及 r13 基线

r13 基线为 Git `83b7d6b`。必须同时保留基线 PCB、同修订的 `.kicad_pro` 和 `.kicad_dru`；也可使用用户提供、已确认来源的完整 r13 工程，记录其来源与文件 hash，并修改下文 `r14_baseline`。不要用当前设置文件拼接历史 PCB。

原生 CLI 可能保存项目设置，因此 ERC、DRC、网表及 CAM 导出必须在 `build/` 内的完整项目副本执行。副本应包含全部子原理图、本地库、库表、PCB、项目和规则文件。下面保留整个工程目录；工作目录已存在时停止，复跑请换一个新的目录名。

```sh
set -eu
r14_work=build/pcb-99/r14-recheck
test ! -e "$r14_work"
mkdir -p "$r14_work/reports" "$r14_work/baseline"
cp -a hardware/devboard-99 "$r14_work/project"
git archive 83b7d6b hardware/devboard-99 | tar -x -C "$r14_work/baseline"
r14_project="$r14_work/project/ESPaperPlay_99"
r14_baseline="$r14_work/baseline/hardware/devboard-99/ESPaperPlay_99.kicad_pcb"
sha256sum hardware/devboard-99/ESPaperPlay_99.kicad_pcb \
  hardware/devboard-99/ESPaperPlay_99.kicad_pro \
  hardware/devboard-99/ESPaperPlay_99.kicad_dru \
  > "$r14_work/source-cad.sha256"
```

以下代码块在同一 shell 中依次执行，沿用上述变量。如果只运行某一块，先重新设置这三个路径变量。

### 原生电气及布线检查

```sh
kicad-cli sch export netlist --format kicadxml \
  --output "$r14_work/reports/netlist.xml" "$r14_project.kicad_sch"
kicad-cli sch erc --format json \
  --output "$r14_work/reports/native-erc.json" "$r14_project.kicad_sch"
kicad-cli pcb drc --format json --schematic-parity \
  --output "$r14_work/reports/native-drc.json" "$r14_project.kicad_pcb"
```

必须读取 JSON 中的实际违规、未连接及原理图一致性结果；CLI 进程成功退出本身不能证明零违规。不要通过修改正式 `.kicad_pro` 的检查级别、加入忽略项或放宽规则来消除报告。

### 独立只读检查

这些工具直接读取正式 PCB，结合副本导出的网表和 DRC 结果；它们不保存 PCB，也不会为掩盖过期铺铜而自动重填。

```sh
python hardware/devboard-99/tools/check_r14_structure.py \
  --board hardware/devboard-99/ESPaperPlay_99.kicad_pcb \
  --baseline "$r14_baseline" \
  --netlist "$r14_work/reports/netlist.xml" \
  --drc "$r14_work/reports/native-drc.json" \
  --report "$r14_work/reports/structure.json"
python hardware/devboard-99/tools/audit_via_manufacturing.py \
  --input hardware/devboard-99/ESPaperPlay_99.kicad_pcb \
  --output "$r14_work/reports/via-manufacturing.json"
python hardware/devboard-99/tools/check_reference_planes.py \
  --board hardware/devboard-99/ESPaperPlay_99.kicad_pcb \
  --return-target-mm 2.0 \
  --report "$r14_work/reports/reference-planes.json"
python hardware/devboard-r0/tools/analyze_signal_paths.py \
  hardware/devboard-99/ESPaperPlay_99.kicad_pcb \
  --output "$r14_work/reports/signal-paths.json"
python hardware/devboard-99/tools/analyze_display_paths.py \
  --board hardware/devboard-99/ESPaperPlay_99.kicad_pcb \
  --report "$r14_work/reports/display-paths.json"
python hardware/devboard-r0/tools/check_power_route_budget.py \
  --board hardware/devboard-99/ESPaperPlay_99.kicad_pcb \
  --rules hardware/devboard-99/tools/power-route-rules-r14.json \
  --output "$r14_work/reports/power-budget.json"
python hardware/devboard-99/tools/check_u101_r14_cam.py \
  --board "$r14_project.kicad_pcb" \
  --baseline "$r14_baseline" \
  --work-dir "$r14_work/u101-cam" \
  --report "$r14_work/reports/u101-cam.json"
sha256sum --check "$r14_work/source-cad.sha256"
```

`check_u101_r14_cam.py` 将输入 PCB 及其项目/规则文件复制到独立 CAM 临时目录，再调用原生 CLI；不回写输入工程。它仅检查 U101 局部 CAM，不能代替整板制造文件复核。复现报告应保留输入 hash、工具版本、原生报告和生成的 CAM。

路径长度按铜线中心线、焊盘中心接入及名义板厚的过孔/PTH 孔筒计入，不包含芯片封装内部、缓冲器延迟或外部屏幕延长线。电源预算采用规则文件中的铜厚、温度及电流假设，不等于实测压降或温升。

### 结果解释及例外

`errors` 与 `reviews` 含义不同：零 DRC、零未连接及几何 PASS 只表示指定模型下的 CAD 检查通过，**不是实板功能、信号完整性、回流焊质量或工厂工艺认证**，也不保证免费券适用。U101 的局部印刷每轴 ≤ 0.03 mm、钢网边缘误差 ≤ 0.02 mm，以及孔径/孔位公差包络均为有条件的验收假设；有放大设备不代表这些精度已经实测达标。

回流孔距离 ≤ 2 mm 是工程审查目标，不是制造 DRC 硬门槛。参考面边缘及具体例外统一记录在 [r14 复核说明](../review-r14/README.md)：新增回流孔搜索采用铜盘边到 USB 线边 ≥0.5 mm；USB 一处保留既有地孔与约 2.273 mm 的回流距离，最近既有地孔铜盘边到 USB 线边约 0.350 mm，不能把新增孔搜索条件当作全板既有孔的统一间距；低频控制和电源网络的较远回流孔保留为 `review`，不能通过调大阈值隐藏。参考面检查使用已保存的实际填充和明确的自身反焊盘包络，不把所有投影空白都算成缺陷，也不把任意空白豁免为合格。

## 历史 r13：U101 普通热孔与钢网

下面保留历史复现命令，仅适用于对应 r13 工程快照。历史章节的路径以当时仓库根目录为准；应在 `build/` 内的独立历史工程副本运行，不要在当前已布线的 r14 正式工程上运行旧阶段检查或覆盖历史报告。

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
