# 嘉立创EDA 99 mm 原生重建：重启前检查点

**状态：未完成，不可用于投板或制造。** 2026-11-15，用户要求当前工作收尾后停止，以便重启系统。恢复工作须等待用户的新指令。

工程名为 `ESPaperPlay V2 99mm Native`。打开客户端最近工程即可继续；独立备份为 `ESPaperPlay-99-Native-WIP.epro2`。备份已完成 ZIP 完整性检查。`audit/checkpoint-status.json` 记录工程/原理图/PCB UUID、逐页网络差异及备份 SHA-256。

## 已保存内容

- 236 个物理器件，均从嘉立创EDA既有器件库放置。U901 使用两单元符号、共享同一个物理器件；未导入 KiCad 符号或封装。KiCad r14 保留为独立设计参考。
- R602 经用户确认，借用既有 2010 电阻符号/封装，保留 **WFMB2010R4700FEA，0.47Ω，3W，1%**，商城料号已清空；不能按借用库器件的 0.5Ω 规格采购。C501/C502 保持未选值、DNP，MPN 和商城料号为空。
- 默认禁充意图保持：R108 DNP，J105 维护短接口默认开路。六个 DNP 为 C501、C502、J301、J302、J303、R108。
- 触摸页已按隔离芯片、接口、去耦、上下拉重排。实际快照的几何审查无异网交叉/错误引脚接触；34 个相关引脚网络比对无差异，并已目视检查标签。预览见 `preview/touch-reviewed.png`。
- 充电输入、3.3V 控制、MCU 页虽曾通过网络比对，但自动布局/布线存在严重交叉，不视为完成。其余页仍待连线或修复；准确差异数见检查点报告。
- 原生 PCB 当前仅有 99×99 mm 板框、四层设置和初始规则，没有元件布局及走线。KiCad r14 的 DRC/CAM 结论不能用于该原生工程。

## 恢复时的工作顺序

1. 确认当前工程 UUID；如从备份恢复，先保全客户端已有修改，避免建立多个混淆版本。
2. **不要再执行整页 `autoLayout` / `autoRouting`。** 用户已指出严重交叉；按 `work-plan/` 的功能小块手工/API重排。块内直接短线连接，跨块使用明确的原生网络标签，局部电源/地不画全页总线。EPD 页计划建议拆成两页，目前尚未执行。
3. 每页同时通过网络比对、实际导线几何检查、导出图目视检查。不能用网表通过替代图纸可读性检查。大部分页面尚不满足这些条件。
4. 整理全部 25 个有意 NC 引脚及原生 DRC；然后再原理图→PCB同步、布局、布线、制造复核。
5. 原生 U101 散热焊盘/锡膏/通孔、U802 暴露焊盘、U803 声孔、U301 地焊盘/天线净空均需依据实际原生封装重新检查。不得直接套用旧版制造结论。

## 验证与技术记录

`source/` 是客户端官方 `getDocumentSource()` 的原生快照；`audit/native-schematic.enet` 是官方导出的当前网表。原生重建尚未通过全工程电气检查，报告中的 FAIL 是未完成状态的真实记录，不应忽略。

从仓库根目录执行：

```sh
python3 tools/check_easyeda_native99.py \
  hardware/devboard-99/easyeda-native/audit/native-schematic.enet \
  hardware/devboard-99/easyeda-native/audit/native-pin-map.json \
  hardware/devboard-99/easyeda-native/audit/reference-components.json

python3 tools/check_schematic_geometry.py \
  hardware/devboard-99/easyeda-native/audit/touch-actual-state.json \
  hardware/devboard-99/easyeda-native/audit/native-pin-map.json
```

API 实测注意事项：

- 原生 `getState_Line()` 平铺数组按每四个数字一段解析，创建折线时则是连续顶点。原理图 API Y 与文档源码 Y 符号相反。
- 4.1.93 中 `createNetLabel()` 曾返回 `undefined` 但实际上创建了 NET 属性，不应盲目重试；`sch_PrimitiveAttribute.getAll(wireId)` 未返回这些属性。触摸页通过官方 `setDocumentSource()` 仅整理原生 NET 属性位置及重复标签，没有改写符号/封装或电气网络。
- 对同一 WIRE 保留多份 NET 属性并设置隐藏，会在保存后重新变为可见。触摸页已删除重复的 NET 属性，只保留一份明确标签。
- 原生网表导出对刚修改的属性可能暂有缓存；保存后再次导出读回确认。R602/C501/C502 的规格字段已复核。
- `build/easyeda-native99/` 保留本机详细请求日志、阶段备份和临时脚本（不纳入 Git）；不能直接重复执行非幂等放置脚本。
- API 桥接此前为 localhost IPv6 问题增加了仅本机 IPv6→IPv4转发。重启后需重新启动官方桥接与必要的本机转发，再连接网关扩展。不要把服务绑定到外网地址。
