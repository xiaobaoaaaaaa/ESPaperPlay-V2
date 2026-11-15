# 嘉立创EDA 99 mm 原生工程

**2026-11-16：12 页原生原理图已完成连线、可读性与电气复核；PCB 尚待布局、布线及制造复核，不可用于投板。**

客户端工程名为 `ESPaperPlay V2 99mm Native`。独立备份为 [ESPaperPlay-99-Native-WIP.epro2](ESPaperPlay-99-Native-WIP.epro2)，已检查 ZIP 完整性和归档中的原理图内容。[检查点](audit/checkpoint-status.json)记录 UUID、状态和备份 SHA-256。恢复既有工作时优先打开客户端当前工程，避免重复导入产生多个同名副本。

## 本轮结果

- 236 个物理器件、237 个符号单元；U901 两单元共用同一物理器件。均来自嘉立创EDA既有库，未导入 KiCad 符号或封装。
- 原来的 10 页拆分为 12 页：稳压/电量计与 IO 控制分开，墨水屏逻辑与偏压/FPC 接口分开。按功能块直接连线，跨块使用明确网络标签。
- 792 个原生逻辑引脚中，767 个应连接引脚、25 个有意 NC 均与参考设计一致；156 个实际连接网络的别名映射无碰撞。原生原理图 DRC **0 错误、0 警告**。
- 12 页实际导线几何审查和导出图目视检查均通过。MCU 去耦轨已移出符号本体，器件文字、标题栏和局部重复网络标签已整理。几何工具对普通器件边界仍有推断，不能取代目视检查。
- `Name` 恢复原生库的标准表达式，`CircuitLabel` 负责显示阻值、电压、短型号和接口功能，避免辅助说明造成商城属性不匹配。**采购以 Manufacturer Part、Supplier Part 和装配状态为准。** J302 使用与既有符号/封装完全相同的正式商城记录补全属性，仍为 DNP。
- R602 保留 **WFMB2010R4700FEA、0.47Ω、3W、1%**，只借用既有 2010 几何，商城料号为空。C501/C502 保持未选值、DNP，MPN/商城料号为空。六个 DNP 为 C501、C502、J301、J302、J303、R108。
- 默认禁充条件保持：R108 DNP、J105 默认开路。电池/NTC 和首板实测条件未由此次 CAD 检查替代。

完整结果见 [电气比对](audit/electrical-comparison.json)、[原生 DRC](audit/native-schematic-drc.json)、[目视复核](audit/visual-review.json)、[导线几何](audit/geometry-summary.json)。[全部原生 SVG](preview/schematic-svg.zip)及 `preview/` 下 12 张 PNG 对应当前检查点。

## PCB 下一步

原生 PCB **当前只有 99×99 mm 板框、四层启用状态和初始规则，0 个器件、无走线**；层叠、规则及制造参数均须在 PCB 阶段再次核实。KiCad r14 仅作为独立参考，其 DRC/CAM 结论不代表本工程通过。

先依据[原生封装实施清单](audit/native-footprint-next-step.md)闭合 U101/U802 焊盘差异，再完成原理图到 PCB 同步、器件布局、热过孔、U803 实际声孔、U301 天线禁布、锡膏开口、布线及最终原生 DRC/CAM。审查还发现旧 U301“不印膏”文字与当前 KiCad r14 的九个中央锡膏窗不一致，必须在原生设计中明确选择并验证，不能直接沿用旧说明。

本轮未修改 KiCad r14，也未向工厂提交、询价或下单。

## 文件与复核

`source/` 是官方 API 导出的 12 页 `.esch` 和仅板框 `.epcb`；归档用于完整恢复。`audit/` 保存网表、原生库来源、检查结果及关键取证。`work-plan/` 保存已实施的连线几何计划；其中名称仍可采用参考网名，以 `audit/native-net-aliases.json` 为准。计划文件不包含全部最终文字调整，**不能直接重放覆盖已复核图纸**。

从仓库根目录执行：

```sh
python3 tools/check_easyeda_native99.py \
  hardware/devboard-99/easyeda-native/audit/native-schematic.enet \
  hardware/devboard-99/easyeda-native/audit/native-pin-map.json \
  hardware/devboard-99/easyeda-native/audit/reference-components.json \
  --aliases hardware/devboard-99/easyeda-native/audit/native-net-aliases.json

python3 tools/check_easyeda_native_archive.py \
  hardware/devboard-99/easyeda-native

python3 tools/check_schematic_geometry.py \
  hardware/devboard-99/easyeda-native/audit/geometry/MCU_CORE-actual.json \
  hardware/devboard-99/easyeda-native/audit/native-pin-map-short-names.json
```

API 实测记录：

- 不再使用整页原理图 `autoLayout` / `autoRouting`。用户已指出其严重交叉问题。
- 每批操作先打开并确认页 UUID；页面切换、保存和网表导出存在缓存，需等待后读回核对。
- 原生 `getState_Line()` 平铺数组按每四个数为独立线段；创建折线时则是连续顶点。原理图 API 与源文档的 Y 轴符号相反。
- `createNetLabel()` 可能返回 `undefined` 但实际已经创建；WIRE 的重复 NET 属性即使隐藏，也可能在保存后恢复显示。当前每个 WIRE 仅保留一份明确标签。
- 修改 `OtherProperty` 会自动重排器件属性文字。应先完成元数据，再设置显示标签及位号位置，最后从保存源和导出图验证。
- `sch_PrimitiveText.modify()` 的视图/源缓存与完整工程归档曾出现位置不同；本检查点通过官方 `setDocumentSource()` 固化 AUDIO 标题位置，并检查归档内容。九个旧标题的 API 删除未进入归档，已改为空白文字记录，避免恢复后重现；见 `audit/archived-text-workaround.json`。最终归档与源图纸的器件、导线、属性和文字均通过对照，12 张重导出预览与审核图逐像素相同。仅看屏幕或 API 返回值不足以证明保存成功。
- `build/easyeda-native99/` 是本机临时脚本/请求日志，未纳入 Git。桥接当前保持运行，仅监听本机 IPv4，并经本机 IPv6 转发连接；重启后需恢复桥接及网关连接。
