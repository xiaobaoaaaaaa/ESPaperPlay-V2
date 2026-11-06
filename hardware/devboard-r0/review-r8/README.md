# r8 布线审查

2026-11-07，KiCad 10.0.7。正式源为上级目录的 [PCB](../ESPaperPlay_Devboard.kicad_pcb) 和 [工程](../ESPaperPlay_Devboard.kicad_pro)。本记录覆盖开发验证板布线阶段，不是制造或实板性能放行。

## 结果

| 检查 | 最终结果 |
| --- | --- |
| 原生 DRC | 0 错误，0 未连接，0 原理图一致性问题 |
| 保留警告 | 1：U301 天线伸出板外的丝印已在 r7 移至 Dwgs.User，产生库绘图差异；焊盘、禁布区与库一致，未增加排除项 |
| 原生独立核对 | PASS；236 个电气器件、4 个机械孔、181 条网络、774 个逻辑引脚、804 个实际编号焊盘 |
| 布线 | 2335 段线、549 个通孔；信号/电源仅 F.Cu 和 B.Cu |
| 内层地 | In1/In2 各一个已填充且连续的 GND 区域，均覆盖板框面积约 96.0%；无内层信号线 |
| USB | 主接触路径成对匹配；另一组 Type-C 接触路径也分别核对 |
| SD | 六路主路径均 ≤50.8 mm，相对 CLK 最大差约 0.806 mm；主干 0.35 mm |
| 电源 | 21 条预设路径全部连通；线宽例外保留在报告中，USB 四个 VBUS 焊盘另行复核 |
| 身份保留 | r6 十一张原理图、符号/封装库、电气 BOM、固件未变；器件/焊盘 UUID、网名、DNP 与属性保持 |

新增 148 个地回流过孔；现有及新增过孔共同覆盖换层处的邻近回流目标。USB_DP_PORT 在 (108.25,57.6) 的最近地孔约 2.29 mm，超过本轮 2 mm 的几何目标，已显式保留记录。这个距离目标及连续地平面检查都不能替代高频回流或阻抗仿真。

SD 的 D0/D1 调试支线仍约 19.21/13.55 mm，保留原 DNP 排针电气连接。主链长度合格不等于完整信号完整性验收；样机必须验证 SD 时钟、卡型号和调试探头负载条件。六路仍有 2–4 次换层，没有声称完全满足原厂避免换层的推荐。

## 证据与复核入口

- [原生 DRC](drc.json)、[独立身份/库/平面检查](independent-board-check.json)、[r7 冻结身份](layout-r7-identity.json)。
- [USB/SD 路径明细](signal-paths.json) 与 [信号审查](signal-integrity-review.md)。
- [21 条电源路径](power-paths.json)、[USB 四脚补充](usb-power-paths.json) 与 [电源审查](power-routing-review.md)。
- [实际线宽/长度统计](route-widths.json)、[名义线宽](nominal-widths.json)、[层叠与阻抗估算](stackup-impedance.json)。
- [回流孔记录](ground-return-vias.json)、[焊接区内孔清单](vip-manufacturing-inventory.json)、[两处非散热孔修正](vip-remediation-delta.json)。
- [位置及参考标注变更](placement-delta.json)、[电源优化差分](power-optimization-delta.json)、[SD 优化差分](sd-optimization-delta.json)、[布线方法](routing-method.json)。
- [上阶段校验快照](verification-r7-before.json) 保留原 249 条输入哈希；当前完整校验为 [verification.json](../verification.json)。

复现当前板结构/电气检查的命令见 [开发板说明](../README.md)。部分优化差分的源文件属于本地中间产物，保留作审查记录；最终原生 PCB 是编辑源，不应运行历史生成器覆盖。

## 预览与制造边界

已检查原生导出的 [正面布线](../output/pcb/ESPaperPlay_Routing_r8_front.png)、[背面布线](../output/pcb/ESPaperPlay_Routing_r8_back.png)、[内层一](../output/pcb/ESPaperPlay_Routing_r8_ground1.png)、[内层二](../output/pcb/ESPaperPlay_Routing_r8_ground2.png) 和 [3D 预览](../output/pcb/ESPaperPlay_Routing_r8_3d.png)。背面布线图保持从板顶观察的坐标，没有镜像。3D 仅反映已具备的模型，不替代连接器/线束实物装配检查。

保留的焊接区内孔共 23 个（11 个 IC 热/地过孔、12 个 U301 封装内 PTH）。需单独确认填孔、封帽、阻焊及钢网方案；不要把连接器和测试排针的普通通孔一并填掉。USB/SD 工厂阻抗、MLCC 偏压、电源/充电温升、NTC 匹配、音频和无线并发仍须对应阶段验证。R108 保持 DNP，初装禁充；本轮没有采购、制板、烧录或上电。
