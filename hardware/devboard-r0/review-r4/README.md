# r4 条件闭合审查记录

> 后续设计决策见[2026-11-04补充记录](decisions-2026-11-04.json)。本目录原BOM、分项审查和导出件为r4历史快照；延长件信息门槛已按用户确认取消，充电默认状态未变。

当前工作源为上一级原生 KiCad 工程。这里保存 [逐位号候选BOM](bom-review.json)、[r3连接基线](electrical-baseline-r3.json)和[明确允许的r4差异](allowed-r3-r4-delta.json)。原 r3 审查目录保持不变。

检查：[ERC](erc-r4.json)、[660项关键引脚](netlist-check-r4.json)、[原生封装与BOM](bom-footprint-check-r4.json)、[PDF视觉检查](pdf-visual-review.json)、[工作簿验证](workbook-qa.json)、[FPC/端子独立集成检查](mechanical/final-integration-review.json)。

分项资料按 power / capacitors / audio_boost / mechanical 保存。分项原始记录中的 scratch 路径保留作创建时出处，实际可复用源文件以 [来源映射](source-archive-map.json) 和 [正式来源索引](../../reference/closure-r4/sources.json) 为准。独立电源报告记录修正前计算输入；其建议的外阻温漂已合入当前 power/power-bounds.json。

原生工程包含222位置、6DNP、178网络；全222位置有封装候选，220个有准确料号候选。新增SH接地有明确白名单，不宣称全部网络逐字不变。材料候选齐全不表示充电、机械插接、电容有效容量或制造资格已通过。完整结论见 [r4报告](../../../docs/v2/hardware/closure-review-r4.md)。

`power/calculate_bounds.py`可独立复算设计假设，输出同目录power-bounds.json；不是实测报告。工作簿脚本是记录用副本，运行条件见 [归档说明](workbook/archive-manifest.json)。不要运行旧原理图生成器覆盖当前十页工程。
