# 99 mm 原生 PCB 布线复核

> 当前布线检查记录；最终完整验证已完成，电气工程偏好仍需首板验证。本文没有制造放行效力。

原生 PCB 已完成布线。标准叠层、保存重开、铺铜后的原生 DRC 空列表已取证；当前为 0 连接错误、0 其他错误。最终完整 21 项 runner 结果为 `COMPLETE_GEOMETRY_CHECKS_WITH_RECORDED_ENGINEERING_REVIEWS`，`scope=complete_set`、运行期间输入未变、未解决检查失败为 0；关键线和参考面两项原始退出码仍为 1，并按精确身份保留工程审查项。旧布局阶段 771 项连接错误和参考叠层保存失败仅作为历史保留。当前运行时源为 236 器件、803 个 PAD_NET、2779 条铜 LINE、647 个 VIA、13 条物理层记录。

## 同版证据与审查范围

| 项目 | 最终结果 | 证据 |
|---|---|---|
| 归档与 CAM | 当前冻结文件已核验；归档实体、规则、叠层与快照一致 | 下列 SHA256；`verification-run/verification-summary.json` 保存本轮输入和工具哈希 |
| 保存、关闭、重开、重铺铜及原生 DRC | 原生 DRC 空列表；连接/其他错误均为 0 | `native-board-check.json`、`verification-run/native-drc-export-check.json` |
| 236 器件、792 逻辑 pin、803 实体 pad | 三份逐针检查均通过 | `verification-run/{schematic-logical-pins,pcb-logical-pins,physical-pad-net-check}.json` |
| 12 页原理图、PCB、八个整改封装与完整归档一致 | 原理图归档 PASS；PCB/封装/规则/叠层为 GEOMETRY_RULES_STACK_SNAPSHOT_MATCH | `verification-run/{schematic-archive-coherence,pcb-archive-coherence}.json` |
| 全部铜岛、孔壁跨层、GND 与短路 | PASS_NATIVE_CAM_COPPER_TOPOLOGY；GND 单岛，0 错误/未归属铜 | `verification-run/cam-connectivity.json` |
| 板边、24 禁区、NPTH、孔间距、非热孔邻盘、22 热孔/11 地线保持 | PASS_SCOPED_ROUTING_BOUNDARIES | `verification-run/boundaries.json` |
| 特殊封装、通用 SMD 锡膏及 J501 | 特殊封装与 J501 均通过；通用 SMD 未发现漏膏 | `verification-run/{special-cam,smd-paste,j501-cam-review}.json` |
| USB/SD/EPD/I²S 端子、串阻、PTH 换层与参考面 | 关键 79 网/269 端子无开短；EPD/TOUCH 返回偏好保留；606 LINE/294 GND 参考面无新增硬错误；68 段端子路径已测量 | `verification-run/{critical-routes,reference-planes,signal-lengths,i2s-paths}.json` |
| 电源 24 条路径与累计细颈 | 24/24 线段 R20 筛查达标；8 条宽度/累计细颈目标偏差保留 | `verification-run/power-paths.json` |
| 最终丝印、装配方向、生产稿 | 位号和新增引线通过；原生轮廓修正后整层开窗、板外和须避让孔的交叠为零，装配定位见首板资料 | `../silkscreen/final-silkscreen-review.json`、`../silkscreen/native-outline-revision.json`、`../assembly-review/README.md` |

本轮归档为 2,022,159 字节，SHA256 `cee685540aeb93956d07d2a631c10255449b86a64c73f82a99a69c1ea0d3de19`，CAM 为 493,307 字节，SHA256 `ea5a5bd372a14b925143cd4c57ba2770e01fa16d94b33b5cdc35903242372474`。当前源 SHA256 为 `2a1cffb14d0b4b8e7f7a6841dc08b4b72d591e465cb707a8a4efbf93bb9d6e1e`，state 为 `29960dc357eca29afd5e763de61bfc5078ce66ff7e5b44f96104f98a6ff74d5a`。

首轮未闭合报告及原输入保留在 `verification-history/before-archive-cleanup/`，`475f5f5` 布线阶段归档清理证据见 `archive-cleanup-proof.json`；历史报告没有改哈希冒充复跑。当前归档核验严格比较实体、网络、规则、封装与层叠，仅对派生铺铜缓存已识别路径的有界浮点表示差异作比较投影，字段与拓扑仍严格一致，原始差异保留，实际 CAM 独立检查。

最终重跑仅跳过已在首轮完成的 J501 13 项反例；当前 J501 实际 CAM 仍重新检查，反例历史见 `verification-history/before-archive-cleanup/j501-cam-review.json`。

完整 runner 检查集合及分类见 `../../verification/README-final-runner.md`。它核对实际空 DRC 导出，但不在客户端执行 DRC。输入或工具哈希在运行期间改变会中止；部分运行不能记为完整通过。`COMPLETE_GEOMETRY_CHECKS_WITH_RECORDED_ENGINEERING_REVIEWS` 表示完整检查没有未解决的硬错误、仍有明确记录的工程审查项，既不删除原始非零退出码，也不代表制造放行。

## 原生层叠与制造边界

GUI 标准预设为 **JLC04161H-7628**，标称 1.6 mm、四层。保存前后 13 条 `LAYER_PHYS` 记录一致，完整归档也保存这 13 条；CAD 厚度字段合计 **1.5861538 mm**。外层铜厚字段 1.378 mil、内层 0.598 mil，介质为两个 8.283 mil 预浸料层及 41.929 mil 芯板记录。这是 CAD 中已保存的标准选择，不代替工厂生产稿、实际厚度/材料公差或受控阻抗确认。

Top/Bottom 走线，两个内层用于 GND。普通通孔采用 Ø0.30/Ø0.60 mm，最小铜间距/线宽 0.15 mm、全局板边/NPTH/槽铜距 0.30 mm；MIC 声孔使用已经验证的局部 0.20 mm 规则。新非热孔还检查与 SMD 铜盘的至少 0.15 mm 间隔、孔边至少 0.25 mm；不得通过屏蔽真实 DRC 或扩大豁免来实现“通过”。实际制造参数与免费券资格仍由用户提交时的工厂工艺审核确定。

## 本轮局部设计决策

**U202 控制与 R227。** 左侧控制、下拉和地线按实际原生网表恢复。最终 state 读回 R227 位置约为 `(46.8, −31.9) mm / 0°`；SP17 出口及普通地孔随局部方案调整，R227 接地已经纳入最终 CAM 的单一 GND 连通体。保留 U202/C203 去耦供电支路；22 热孔与 11 段原地线保护基线亦经最终边界检查确认。

**SD_CD_N。** 已应用的新卡检测支路中心线合计 **166.754 mm / 12 个新增普通信号孔**；它连接到既有同网铜，不能等同为整网全部暴露铜长度。该网为静态/低速卡检测，较长走线用于避让供电、GPIO、SD/I²S/EPD 已布主干。全部六个端子 `U202.9 / R216.2 / J206.5 / J302.9 / C704.1 / R708.1` 与所有保留铜在最终 source 和 CAM 上同岛。首板检查插拔电平、去抖、上电默认态，以及 Wi-Fi、音频、SD 访问、EPD 刷新、充电活动下的误触发；该长度决策不适用于 SD 时钟/数据的时序判断。

**EPD 返回距离。** EPD_PAD_SCLK 的信号孔 `773d5373a5cbe8af` 到地贯通点 `a903fd929074af60` 为 **2.246160 mm**，比 2 mm 项目偏好多 0.246160 mm。仅对相同孔 ID、坐标与距离记录该偏差；制造间距没有放宽，实际两内层 GND 接触与附近通道仍按 CAM 检查。EPD 起步 1 MHz，再按实测验证 4 MHz，不宣称完整 SI。

**TOUCH_IO_EN 返回偏好。** 最终关键网检查另报告信号孔 `ffe9ee8ae2cc196e` 到最近地贯通点 `8fe8f0e0cc4c73a1` 为 **2.504406127 mm**。这是静态隔离使能线的返回偏好项，单独保留实际孔 ID 和距离进行分类，不套用 EPD 孔的身份限定分类；2 mm 原始偏好、原始非零退出码和制造间距均保持。首板检查默认态、隔离切换与并发活动下的噪声，不宣称高频或完整信号完整性资格。

**备用 GPIO 返回偏好。** 最终源中的信号孔 `d7475b9eb55316cc` 位于约 `(48.65, −43.5) mm`，到地孔 `ecbe0f72b19d894c` 的中心距为 **2.977414534 mm**。0.025 mm 网格的有限局部搜索没有找到满足铜距 0.1502 mm、孔距 0.2502 mm 且距离 ≤1.9999 mm 的新地孔位置；这只证明已搜索范围无候选，不是全空间数学不可行证明。保留静态备用 GPIO 的这一返回偏好限制，制造间距/全铜连通和最终实际 GND 平面检查独立执行；不沿用 EPD 的身份限定分类，也不把它描述成制造 DRC 豁免。布线阶段记录的孔 ID、坐标与距离见 `spare-gpio-return-review.json`；首板仍需噪声/默认态测试。

**F501 丝印。** 原生库仅修改两条外形丝印线，各移 1.016 mm；库、板及规则证据需随最终归档保存。[F501 原生库证据](../silkscreen/f501-library-silk-persisted-check.json)的 19 项检查通过；实际 CAM 物理图元比较表明全部非丝印图元逐项零容差一致，三组原生规则完全未变。[实际丝印差分](../silkscreen/f501-actual-silk-delta-review.json)记录两条实际丝印距阻焊开窗约 0.178205 mm、其它 GTO 图元及 GBO 不变，并附 5 项等价/变异自检。正式 `../../source/footprints/F501.efoo` 来自保存归档直接提取的 `F501-silk-saved.efoo`，其余七份关键封装在当时的专项修改中未动。这些修改前后比较属于历史现场证据，部分旧输入位于 ignored `build/`；当前正式丝印检查可独立复跑，边界见 `../../verification/README-silkscreen.md`。比较依据是实际物理图元及孔，不是对 Gerber 文本整段做哈希相等要求；未使用到的 aperture 定义变化不产生实际铜差异。早期只按命令文本比较产生的差异已有这份物理图元证明；保留比较方法、零容差和原始证据，不用删除真实形状差异换取通过。F501 专项报告的阶段 DRC 数字不是最终整板状态。

**电源路径。** 同版 `verification-run/power-paths.json` 已测量全部 24 条固定路径，包括连续累加的细颈长度；24/24 线段 R20 筛查在参考限值内，仍有 8 条宽度/累计细颈目标偏差。R20 只计算所选 LINE 路径，未包括孔桶、焊盘/接触电阻、并联分流、自热或实际铜厚偏差；不能据此批准载流和温升。USB VBUS、SYS、3V3_MAIN、EPD 分支等具体偏差保留在最终报告，首板加载测压降与温升。

**I²S。** 同版 `verification-run/i2s-paths.json` 覆盖 13 相关网、39 实体端子、26 端子对、38 信号换层及 6 条链路，全部端子连通；J303 为主干通过，并非新增 T 形调试支路。MIC BCLK/WS 的暴露走线几何长度差为 11.219237 mm，AMP BCLK/WS/DIN 最大差为 20.580224 mm，均超过 10 mm 参考目标，不能写成时序通过。38 个换层返回均在 2 mm 内，其中 10 个超过 1 mm 偏好；缓冲输出到三串阻的源端路径约 2.797346、2.484741、0.919090 mm。初测 48 kHz / 3.072 MHz，在接收端验证占空比、建立/保持、录放音质量及 Wi-Fi/SD/EPD 并行影响。MIC BCLK 孔维持封装本体外，声孔、密封环和膏窗按原专项检查。

**其他信号与参考面。** 同版 `verification-run/signal-lengths.json` 测量 39 网的 68 段端子路径：USB 两插入方向的板级暴露 P/N 长度差约 0.000567 mm；SD 六路主链最大差 4.553432 mm；EPD 五路前向主链最大差 7.968603 mm。这些计算不包含器件内部和连接器/孔桶延迟，也不证明 USB 90 Ω 阻抗或接口时序。`reference-planes.json` 检查 606 条选定信号 LINE 和 294 个两内层已核实 GND 贯通点，没有新增硬错误；两项 EPD_PAD_SCLK 端部参考面审查及七项 CAM 量化尺度残差按各自身份保留，不能泛化成任意参考面缺口豁免。

## 丝印和装配识别范围

本轮在 9 个共享封装中修改或增补 46 个丝印图元，156 个已放置器件随库更新。两类 0603 封装使用短线标识，所有修正均保存在封装中。7 个早期封装经编辑器重新序列化后存在焊盘、填充等字段表现差异。逐库对照修改前的编辑器几何，并逐图元比较两次 CAM 导出，四层铜、阻焊、锡膏、钻孔、板框和底层丝印的实际几何均一致。 [归档与制造图元对照](../silkscreen/native-outline-revision.json)

同版 CAM 的 236 个位号均达到 0.8 mm 的最小实际字高目标，实测最小为 0.83834 mm。全层墨迹与阻焊开窗、板外、非完全盖油孔的相交面积均为零，51 个封装的其余孔投影仅落在完全盖油的原生 VIA 上。[几何复核](../silkscreen/final-silkscreen-review.json) · [本轮差分及制造几何复核](../silkscreen/native-outline-revision.json)

在修改前的 `475f5f5` 中，19 个器件涉及 32 片开窗交叠，U301 的丝印超出板边，U203 的丝印接触两个裸露孔。另有 J205 的 e5 轮廓压到一个部分开窗的过孔。以上为本轮修正的依据。装配图给出 D501 的阴极、U203 和两个连接器的 1 脚方向。[首板装配复核](../assembly-review/README.md)

嘉立创公开的标准能力列出焊盘到丝印至少 0.15 mm、文字高度至少 1.0 mm。以实际阻焊开窗边界筛查，本版有 1047 个顶层丝印绘制图元距开窗小于 0.15 mm，最小 0.00927 mm，位于 J701 的外形。该数量按绘制图元统计，开窗与焊盘边界可能有差异。236 个位号均距开窗至少 0.27944 mm，原生标称字高 1.2 mm，实际墨迹高 0.838–0.904 mm。板厂可能裁剪靠近焊盘的丝印，需按工厂稿和首板核对文字及方向标记。 D501 阴极条到最近开窗为 0.17190 mm，U203 的 1 脚环为 0.16542 mm。 [丝印间距复核](../silkscreen/silk-mask-clearances.json) · [嘉立创制造能力](https://jlcpcb.com/capabilities/pcb-capabilities) · [字符处理说明](https://jlcpcb.com/blog/character-design-specifications)

## 默认禁充与首板条件

**R108 DNP、J105 开路保持默认禁充。** 路由闭合不授权启用充电。单节受保护、带 NTC 的电池资料、NTC 温阻曲线假设、热/冷阈值、约 0.7 A 充电方案、USB 输入限流和温升必须分别验证，不能把估计曲线写成已验证电池特性。

首批 5 PCB / 先装 2 板；无框钢网以胶带铰链手工定位，放大设备检查，接口和排针手焊。U101 约 ±0.03 mm 局部对位、开放热孔吸锡、U301 中央零锡膏的热表现、MIC 声道与密封需首板检查。C501/C502 DNP、R602 原规格保持。本轮未代用户提交工厂、询价或下单；生产 BOM、钢网、坐标与工厂审核须使用最终原生版本。

器件模板历史属性 `DesignStage=SCHEMATIC_VERIFIED_PCB_PENDING` 保留不改。本轮没有为更新标签批量修改器件属性，当前阶段由检查点和最终输入哈希界定。

## 发布顺序

保存重开/铺铜 → 原生 DRC 与规则读回 → 同版源/state/全部原理图与网表/归档/CAM → 完整只读 runner → CAM 目视与工程审查 → 当前检查点/文档/哈希索引 → 有选择地暂存正式材料并重建仓库 manifest。历史 `audit/pcb-layout/` 保留历史语义，不能只改旧报告哈希充当新结果。
