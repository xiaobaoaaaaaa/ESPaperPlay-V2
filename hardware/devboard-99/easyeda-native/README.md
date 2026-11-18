# 嘉立创EDA 99 mm 原生工程

**99×99 mm 四层原生 PCB 已完成布线，保存重开及铺铜后的原生 DRC 为 0 连接错误、0 其他错误。标准叠层已持久保存。最终完整 21 项检查已完成，输入无变化、未解决检查失败为 0，结果为 `COMPLETE_GEOMETRY_CHECKS_WITH_RECORDED_ENGINEERING_REVIEWS`；返回距离、电源与 I²S 路径偏差仍需首板实测。当前不是制造放行。**

客户端工程名为 `ESPaperPlay V2 99mm Native`。完整备份为 [ESPaperPlay-99-Native-WIP.epro2](ESPaperPlay-99-Native-WIP.epro2)，本轮结果与哈希见 [PCB 布线复核](audit/pcb-routing/pcb-routing-review.md)及[当前检查点](audit/checkpoint-status.json)。恢复工作优先打开客户端当前工程，避免重复导入同名副本。KiCad r14 仅作为电路与位置参考；本工程使用嘉立创EDA既有器件、原生封装和原生走线，未导入 KiCad 库或铜图形。

## 工程与检查范围

- 99×99 mm 板框、四个 Ø3.2 mm 安装孔、236 个器件、12 页原理图、792 个逻辑引脚和 803 个物理焊盘；最终运行时源包含 2779 条铜 LINE、647 个 VIA 和 13 条物理层记录。保留 22 个既有 Ø0.30/Ø0.60 mm 热过孔及 11 段局部 GND 铜线；这些是专项保护基线，并非最终整板的孔、线总数。
- Top/Bottom 承担信号与电源，两个内层作为 GND。实际接地、跨孔孔壁及参考平面连续性以同一冻结版本的原生 DRC 和实际 CAM 报告为准，不能只凭铺铜外框认定连通。
- GUI 已选用标准四层预设 `JLC04161H-7628`，13 条物理层记录在保存重开及完整归档中保留。CAD 记录的厚度合计为 1.5861538 mm，对应标称 1.6 mm 预设；这不等于工厂实际压合厚度公差、材料批次或 USB 阻抗认证。旧 API 参考叠层未持久化的情况仅保留为历史。
- 原生关键封装已按资料整改：U101/U203/U802 铜盘、锡膏与热孔，U301 中央接地铜及零锡膏，U803 声孔与密封环，J501 铜盘/孔槽、F501 及按键孔径。布局阶段依据见 [历史布局复核](audit/pcb-layout/layout-review.md)，当前几何须以 [布线阶段专项检查](audit/pcb-routing/verification-run/verification-summary.json)为准。
- SD 等价通道交换及 SW301–SW305 内部常通端子映射已同时反映到原理图、PCB 和逐针映射。最终逻辑引脚、重复实体焊盘、归档与全铜连通均重新检查；不能用较早的布局网表代替当前版本。

F501 已在原生库中只调整两条外形丝印线，各移动 1.016 mm。19 项专项检查已通过，修正前后全部非丝印实际 CAM 物理图元以零容差逐项一致，原生规则、网络规则与区域规则三组完全未变。实际两条新丝印距阻焊开窗约 0.178205 mm；5 项等价/变异自检覆盖未使用 aperture、实际 aperture/坐标及极性。正式 F501 封装已保存为 [source/footprints/F501.efoo](source/footprints/F501.efoo)，来自保存归档提取快照；[19 项检查](audit/silkscreen/f501-library-silk-persisted-check.json)与[物理丝印差分](audit/silkscreen/f501-actual-silk-delta-review.json)保留历史现场证据。未使用到的 aperture 定义差异不等同于实际铜形状变化。

当前归档 SHA256 为 `cee685540aeb93956d07d2a631c10255449b86a64c73f82a99a69c1ea0d3de19`（2,022,159 字节），复核 CAM 为 `ea5a5bd372a14b925143cd4c57ba2770e01fa16d94b33b5cdc35903242372474`（493,307 字节）。同版 21 项检查覆盖引脚映射、铜层连通性、制造边界和归档一致性。工程偏好及其原始检查结果见 [完整检查摘要](audit/pcb-routing/verification-run/verification-summary.json)。

两类共享 0603 封装改用短线标识，9 个共享封装的更新涉及 156 个已放置器件。顶、底层实际丝印与阻焊开窗、板外和须避让的钻孔交叠均为零。236 个位号的最小实际字高为 0.83834 mm。51 个封装轮廓仍经过完全盖油的过孔投影，已单独列出。首批两块板使用剔除手焊接口和空贴位开口的专用顶层钢网。装配图标出了 D501、U203、J601、J406 的方向。[丝印几何复核](audit/silkscreen/final-silkscreen-review.json) · [装配复核](audit/assembly-review/README.md)

嘉立创公开的标准能力列出焊盘到丝印至少 0.15 mm、文字高度至少 1.0 mm。以实际阻焊开窗边界筛查，本版有 1047 个顶层丝印绘制图元距开窗小于 0.15 mm，最小 0.00927 mm，位于 J701 的外形。该数量按绘制图元统计，开窗与焊盘边界可能有差异。236 个位号均距开窗至少 0.27944 mm，原生标称字高 1.2 mm，实际墨迹高 0.838–0.904 mm。板厂可能裁剪靠近焊盘的丝印，需按工厂稿和首板核对文字及方向标记。 [整板丝印间距](audit/silkscreen/silk-mask-clearances.json) · [嘉立创制造能力](https://jlcpcb.com/capabilities/pcb-capabilities) · [字符处理说明](https://jlcpcb.com/blog/character-design-specifications)

按实际顶层阻焊开窗向外 0.15 mm 模拟裁剪，236 个位号、D501 阴极条、U203 和 J406 的 1 脚标记都保留完整。J701 最近的一段外框约保留 81% 的墨迹面积。J601 的 1 脚位置请按顶视装配图辨认。[裁剪模拟](audit/silkscreen/simulated-015mm-mask-clipping.json) · [J701 局部对照](audit/silkscreen/j701-015mm-clip-comparison.png) · [首板装配图和钢网](audit/assembly-review/README.md)

## 保留的工程条件

充电仍默认禁用：**R108 DNP、J105 开路**。原电池/NTC 曲线假设和约 0.7 A 充电方案需按首板电源、温度门限及电池资料验证后再启用。R602 保持 **WFMB2010R4700FEA、0.47 Ω、3 W、1%**，商城料号为空；C501/C502 继续 DNP 且未选值。

SD_CD_N 的新卡检测支路约 166.754 mm，属于静态/低速控制信号，不能作为 SD 时钟或数据线合格的依据；首板需检查卡插拔电平、去抖及 Wi-Fi/音频/屏幕/充电活动下的误触发。R227 就近移位并恢复接地，原 I²C 换层的附近接地孔同时重新核对，未修改 U202/C203 去耦供电支路。

EPD_PAD_SCLK 有一处返回贯通点距离 2.246160 mm，超过项目 2 mm 偏好 0.246160 mm。只有已记录的孔/地孔身份、坐标与距离一致时才按该工程偏差报告，制造间距和实际 GND 平面接触检查均不放宽。TOUCH_IO_EN 静态隔离使能另有一处返回距离 2.504406 mm，按该孔身份独立记录，并保留默认态、隔离切换和噪声实测条件。另有 IOX_SP16 备用 GPIO 门的最近 GND 返回距离约 2.977415 mm；有限局部搜索未找到满足全部几何约束的 ≤2 mm 位置，按低速备用线的返回偏好限制独立记录，不能称为制造 DRC 例外。最终报告保留 8 条电源宽度/累计细颈目标偏差及 I²S 几何长度偏差；它们不是载流、温升、时序或完整信号完整性认证。

首批仍为 5 块 PCB、先装 2 块；自行无框钢网、胶带铰链定位回流，接口/排针手焊。U101 约 ±0.03 mm 局部钢网对位、开放热孔吸锡、U301 中央零膏的散热表现和 MIC 密封均需实物验证。本轮未代用户提交工厂、询价或下单，后续由用户自行提交。

## 当前文件与复现

- `source/PCB-layout.epcb` 保留兼容文件名，现为当前完整布线 PCB；`source/*.esch` 和 `source/footprints/*.efoo` 为同一冻结版本的原理图及八个整改封装。
- `audit/pcb-routing/` 保存当前布线 state、网表、原生 DRC/规则、实际 CAM、检查报告及输入哈希；`NOT-FOR-MANUFACTURE-routed-cam.zip` 继续用于复核。
- `audit/pcb-layout/` 是历史布局检查点，其连接错误数、孔/线数量及旧叠层结论不能描述当前版本。
- 当前实际 CAM 预览：[顶面](preview/routed/top-pretty.png)、[底面](preview/routed/bottom-pretty.png)、[顶层丝印](preview/routed/top-silk.png)、[底层丝印](preview/routed/bottom-silk.png)；`preview/PCB-layout.png` 也是当前顶面图。`preview/STORAGE_SD.png` 为 SD 等价通道交换前的历史图，当前 SD 原理图须读正式 `.esch` 与 geometry/网表报告；其余保留旧原理图图片沿用原审查范围，本轮未宣称全部重导出。带 `before-pcb-layout` 名称的 SVG 包同样为历史。

从仓库根目录使用 [完整验证入口](verification/README-final-runner.md)：

```sh
python3 hardware/devboard-99/easyeda-native/verification/run_final_verification.py --plan-only
python3 hardware/devboard-99/easyeda-native/verification/run_final_verification.py
```

本次 21 项重跑仅跳过重复的 J501 13 项反例：首轮全部通过的结果和当时输入保存在 [历史验证报告](audit/pcb-routing/verification-history/before-archive-cleanup/j501-cam-review.json)，本次仍重新检查当前 J501 实际 CAM。上面的默认完整命令会执行反例。

依赖 Python 3、Shapely 和 Gerbonara；工具代码不依赖 ignored `build/` 目录。runner 不执行实时原生 DRC，不代替最后一次保存重开/铺铜后的客户端检查或 CAM 目视。已记录工程偏好仍保留原始子报告、阈值和退出码；未知开路、短路、孔槽或参考面问题保持失败，不能将 runner 摘要解释成制造批准。

器件模板中的 `DesignStage=SCHEMATIC_VERIFIED_PCB_PENDING` 保留为历史生成属性，本轮没有为刷新标签批量改动器件；当前工程阶段以 `audit/checkpoint-status.json` 及其同版证据为准。

API 焊盘孔径 getter 曾出现十倍比例差异，实际尺寸以原生源与 Excellon 为准。封装、叠层或源文件修改后应保存重开并核对归档，不以单次 API 返回成功作为持久化证据。
