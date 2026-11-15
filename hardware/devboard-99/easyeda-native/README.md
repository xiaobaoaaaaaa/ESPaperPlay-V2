# 嘉立创EDA 99 mm 原生工程

**2026-11-16：已完成 236 个器件的原生 PCB 布局及关键封装复核。主信号布线、完整铺铜和最终丝印尚未完成；叠层保存问题待解决，不可投板。**

客户端工程名为 `ESPaperPlay V2 99mm Native`。完整备份为 [ESPaperPlay-99-Native-WIP.epro2](ESPaperPlay-99-Native-WIP.epro2)，状态及哈希见 [检查点](audit/checkpoint-status.json)。恢复工作优先打开客户端当前工程，避免重复导入同名副本。KiCad r14 仅作为电路、位置参考，未导入其符号、封装或走线。

## 本轮结果

- 99×99 mm 板框、四个 Ø3.2 mm 安装孔、236 个器件、803 个物理焊盘。已添加 22 个 Ø0.30/Ø0.60 mm 普通热过孔和 11 段局部 GND 连接，以及天线、麦克风声道和螺钉占位禁布区。
- 修正项目内既有原生封装：U101、U203、U802 的焊盘及显式锡膏窗口，U301 中央接地铜/零锡膏，U803 唯一声孔/密封环，J501 USB-C 焊盘/孔槽，F501 保险丝及五个按键的孔径。详细依据和限制见 [布局复核](audit/pcb-layout/layout-review.md)。
- 发现并修正 SW301–SW305 内部端子组映射：1/2 接对应信号，3/4 接 GND；修正原理图、映射表和 PCB 网络，保留原生引脚编号。原错误会造成信号被内部常通触点接地。
- 12 页原理图、792 个逻辑引脚及 803 个 PCB 焊盘网络一致。原理图 DRC 无错误；PCB 原生 DRC 无非连接类错误，仍有 **771 项未布线连接错误**，不代表 771 个网络。
- 实际 CAM 的关键封装检查 153 项通过；677 个已装 SMD 焊盘未发现漏膏或低于 25% 的覆盖。J501 单独核对通过。此处只证明所列布局阶段几何，不证明整板可制造或已连通。
- MIC 声孔局部 0.20 mm 规则已通过阈值反例并保存；全局板边/槽孔仍为 0.30 mm。客户端不能可靠强制区域内禁止过孔，当前已独立检查全部过孔；布线后必须重查。

R602 保持 **WFMB2010R4700FEA、0.47Ω、3W、1%**，商城料号为空。C501/C502 保持未选值且 DNP。充电仍默认禁用：**R108 DNP、J105 开路**。此次未改变电池/NTC 与首板实测条件。

## 尚待完成

**叠层没有闭合。** 对称 1.6 mm CAD 参考值在修改后可以读回，但关闭并重开 PCB 后恢复为默认约 1.693672 mm；官方物理叠层 API 在当前 4.1.93 客户端返回无配置/写入失败。完整归档与运行时默认补层也存在差异。四个铜层启用状态已保留，但不能据此宣称板厚、厂家压合结构或 USB 阻抗已经确认。候选叠层仅作参考资料，不应用于阻抗计算或下单。

下一步先解决叠层的原生持久保存并核对厂家标准结构，再完成电源/信号布线、完整 GND 平面、回流路径、丝印整理及最终 DRC/CAM。U101 手工印刷对位、开放热孔吸锡、U301 中央不印膏的散热效果及麦克风密封仍需首板验证。此阶段未提交工厂、询价或下单。

## 文件和复核

- `source/`：12 页原理图、当前 `PCB-layout.epcb` 以及 8 个修改后原生封装快照；旧板框源已由 Git 历史保留。
- `audit/pcb-layout/`：网表核对、布局快照、规则、CAM 和机械检查。`NOT-FOR-MANUFACTURE-layout-cam.zip` 仅供复核。
- `preview/`：当前 PCB 布局和原理图 PNG。MCU/USB 两页已用原生画布重新审查；完整 SVG 导出超时，`schematic-svg-before-pcb-layout.zip` 明确保留为旧版，不能当作当前原理图。
- `work-plan/`：实施计划，不能直接重放覆盖最终图纸；历史审查中的候选值以当前源文件及布局复核为准。

从仓库根目录运行：

```sh
python3 tools/check_easyeda_native99.py \
  hardware/devboard-99/easyeda-native/audit/native-schematic.enet \
  hardware/devboard-99/easyeda-native/audit/native-pin-map.json \
  hardware/devboard-99/easyeda-native/audit/reference-components.json \
  --aliases hardware/devboard-99/easyeda-native/audit/native-net-aliases.json
python3 tools/check_easyeda_native_archive.py hardware/devboard-99/easyeda-native
python3 tools/check_easyeda_native_pcb_archive.py hardware/devboard-99/easyeda-native
```

原理图归档检查不覆盖 PCB。新增 PCB/封装检查保留叠层差异，不能把“几何和规则一致”解释为叠层通过。关键 CAM 的复现说明见 `verification/`。

API 读回注意：焊盘孔径 getter 在该客户端存在 10 倍比例问题，应以源文件/Excellon 为准；修改项目封装后需保存并重新打开 PCB 才能刷新缓存；物理叠层不能只凭一次 `setDocumentSource` 返回值判定保存成功。当前桥接只在本机运行，重启后需重新建立连接。
