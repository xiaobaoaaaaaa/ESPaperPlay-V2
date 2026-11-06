# 原理图模块化重排 r6

日期：2026-11-05。用户要求将分散的去耦、上下拉和配置器件直接连到主要器件，并按功能划分模块。本轮已重排全部十张功能页，保持一张索引、十张功能页的结构。

电气设计仍是[r5充电与温控方案](charging-design-r5.md)。没有更改器件数量、数值、候选MPN、封装、DNP、组件/引脚UUID或电气连接，也没有进行PCB布局或实物测试。BOM继续使用[review-r5/bom-review.json](../../../hardware/devboard-r0/review-r5/bom-review.json)。

[打开原生工程](../../../hardware/devboard-r0/ESPaperPlay_Devboard.kicad_pro) · [十一页模块化原理图](../../../hardware/devboard-r0/output/pdf/ESPaperPlay_Devboard_Modules_r6.pdf)

## 绘图方式

- 每页用带标题的虚线框划出功能模块；主要电源及信号路径用连续导线表示。
- 去耦、反馈、配置电阻及上下拉放在所属芯片附近，以支线接入真实网络。
- 跨页、跨模块端口保留网名；复杂总线不强行画成穿越整页的交叉线。
- 导线连接处用圆点明确；没有圆点的普通交叉保持不连接。
- 原有DNP与NC标记保留。图上的位置只表达阅读关系，不等于PCB放置或实际走线距离。

| 页 | 主要模块 |
| --- | --- |
| 2 充电与输入 | BQ24074及设置电阻、电池/SYS路径、默认禁充/维护、USB输入检测 |
| 3 主稳压与控制 | TPS63802及电感/反馈、GPIO扩展器及默认电阻、电量计、测试接口 |
| 4 MCU | 模组及去耦、EN/BOOT、用户按键、DNP调试头 |
| 5 USB | USB-C、CC保护、D±保护与串阻、PTC/TVS/选源 |
| 6 分域电源 | 五路各自完整的输入电容、负载开关、CT/QOD、测流与输出电容电路 |
| 7 触摸 | TMUX至GT911接口的四条信号、上下拉、局部电源旁路 |
| 8 墨水屏 | 升压回路、面板储能电容、输出缓冲与默认电阻、BUSY返回 |
| 9 microSD | 六线隔离、卡侧上拉及去耦、机械检测RC、ESD |
| 10 音频 | 输出缓冲/使能、功放与BTL扬声器、麦克风及数据返回 |
| 11 温控 | NTC及冷热分压、双比较器、两条正反馈和TS接口 |

## 检查

最终仍为236个器件位置、181条网络、774个引脚连接。ERC为0错误、0警告、0排除；原电气检查链和r5 BOM/封装契约继续适用。新增[绘图等价检查器](../../../hardware/devboard-r0/tools/check_drawing_r6.py)核对完整元件元数据、每个具名网络和NC、组件/引脚UUID以及符号定义。它使用[冻结的r5基线](../../../hardware/devboard-r0/review-r6/electrical-baseline-r5.json)，不依赖临时重排脚本。

预览已逐页渲染检查，修正了旋转器件文字、标签压线及模块边框避让。机器报告、视觉记录和当前文件哈希见[verification.json](../../../hardware/devboard-r0/verification.json)。r5原生备份位于本机 `build/redraw-r6/intake/`；旧r5 PDF和审查结果保留。

后续继续在原生KiCad文件上手工编辑。临时绘图脚本不是工程唯一源，不能运行旧r0生成器覆盖当前工程。约0.7A充电、假设NTC曲线、R108默认DNP及所有原有样机验证边界均保持不变。
