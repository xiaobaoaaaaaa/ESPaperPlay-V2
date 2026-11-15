# ESPaperPlay 99 mm 开发验证板

**r12：99 × 99 mm、四层、顶面装配的 KiCad 布局基线；尚未布线，不可投产。**

用 KiCad 10 打开本目录的 [ESPaperPlay_99.kicad_pro](ESPaperPlay_99.kicad_pro)，再打开同名 PCB。本目录包含独立的根原理图、10 张子页、符号/封装库和规则文件，不会从工程入口打开旧 r10 板。

本版从 `../devboard-r0/` 的 r10 派生，保留 240 个封装、236 个电气器件、774 个逻辑引脚和 181 个网络。所有元件仍在顶面，五个按键和全部调试/测流接口保留。原 r10 PCB、嘉立创迁移工程及制造包未修改。

| 项目 | 当前结果与边界 |
|---|---|
| 外形 | Edge.Cuts 中心线 99.000 × 99.000 mm；四角 M3 安装孔中心距板边 5 mm |
| 制造规则 | 最小钻孔 0.30、过孔铜盘 0.60、孔环 0.15、线宽/间距 0.15、铜到板边 0.30、孔边到孔边 0.25 mm；禁止盲孔、埋孔、微孔 |
| 模组封装 | U301 十二个实际 PTH 从 Ø0.20 改为 Ø0.30，铜盘仍 Ø0.60；项目内封装与 PCB 一致，EP 保持不印膏 |
| 原理图 | 电路、器件型号及 DNP 状态不变，仅 U301 使用新的本地封装 ID；符号 ID 保持原值 |
| 布局检查 | 见 [审查报告](review-r12/layout-review.md)、[独立检查](review-r12/layout-validation.json)及 [KiCad DRC](review-r12/native-drc.json) |
| 接口操作 | 21 个插线、FFC 锁扣、按键和安装柱预留包络已画在 Dwgs.User；这是工程预留，不是外壳/线束三维认证 |
| 热孔 | Dwgs.User 的 12 个双圆只是后续布线预留；没有钻孔或电气连接效果。见 [热孔报告](review-r12/thermal-review.md) |
| 充电 | 仍默认禁充：R108 DNP、J105 开放；设定电流约 0.701 A。电池 NTC 曲线假设和首板验证要求延续 r10 |

## 制造与免费券边界

裸板尺寸已经满足 10 × 10 cm 内的目标，常规过孔按 ≥0.30 mm 设计。**U101 仍需四个填平盖帽的盘中热孔，不能据此宣称整板免费工艺已闭合。** 四层板的该工艺官方列为收费；若坚持全免费，需另行完成可被工厂接受的散热/焊接方案。U802 外移地孔方案还需首板热测。

项目暂保留原四层 1.6 mm 名义叠层与 ENIG 表面处理参考；最终须匹配实际券种（沉金或 OSP）、厂方叠层和报价。没有要求 ±10% 阻抗保证，KiCad 的介质厚度强制约束已关闭；USB/SD 净类名与线宽仅是布线起点，不是已经验证的阻抗结果。

按用户确认的流程，先完成此 KiCad 版本的布线和验证，再在嘉立创EDA**新建原理图、转 PCB 并参考 KiCad 重新设计**。旧导入工程不作为 EDA 专用券设计依据。本阶段没有创建新的嘉立创工程、提交工厂或下单。

## 文件与复核

- [顶面预览](review-r12/front-layout.png)、[装配参考图](review-r12/assembly-layout.png)：均来自当前原生 PCB。
- [机械审查](review-r12/mechanical-review.md)、[操作包络](review-r12/operation-envelopes.json)、[热孔预留坐标](review-r12/thermal-reservations.json)。
- [元件坐标与功能分组](review-r12/placements.json)、[本版网表](review-r12/netlist.xml)、[ERC](review-r12/native-erc.json)。
- [来源与制造参数说明](review-r12/manufacturing-constraints.md)、[复核命令](tools/README.md)。

下一阶段先完成电源/热孔及地平面，再布 USB、SD、音频和显示信号；完成真实连通性、压降、回流路径与 DRC 检查后才能重新生成 CAM、钢网及装配文件。旧 r10 的 Gerber、钻孔、钢网和贴片坐标不能用于本版。
