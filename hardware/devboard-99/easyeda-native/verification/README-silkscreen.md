# 原生 CAM 丝印检查与预览

这两个入口只读嘉立创EDA导出的工程和 CAM，不调用实时 API，不修改铜、阻焊、钢网或器件位置，也不依赖 `build/` 下的工具代码。几何依赖与本目录其他检查器相同：Gerbonara 1.6.2、Shapely 2.2.0。PNG 预览另需 PyGObject、Cairo 和 librsvg 的 `Rsvg 2.0` 接口。

## 实际丝印检查

```sh
python3 hardware/devboard-99/easyeda-native/verification/check_native_silkscreen.py \
  --source FINAL.epcb --state FINAL-state.json --archive FINAL.epro2 \
  --zip FINAL-cam.zip --output silkscreen-review.json \
  --minimum-ink-height-mm 0.8
```

工程源、引脚状态、库归档和 CAM 应来自同一冻结版本。可用 `--text-baseline-report REPORT.json` 显式指定已验证的文字几何基线；默认使用相邻正式 `audit/silkscreen/` 中保存的基线。基线只提供旧字形包围框，经当前字号、旋转和中心位置变换后限制文字归属范围，避免把邻近位号或库轮廓错误归入该位号。现版的墨迹、实际字高、字符分离数、阻焊开窗、钻孔及板边交叠仍从本次 CAM 原始几何读取，不使用基线替代现版测量。

默认基线为 `../audit/silkscreen/validated-glyph-baseline.json`，SHA256 为 `d8a5f6703b2b3328da15f99251d0166bb10a226168f9326c8563a706a00985ad`。它保留旧版 236 个实际位号的字形边界，文字归属错误与位号几何问题均为 0；旧报告的库轮廓问题并未因此被宣称通过。报告内的历史输入路径仅作来源记录，不是运行时文件依赖。

检查器分别报告：

- 位号缺失、字符粘连或归属不明，以及文字与开窗、孔和板边的实际交叠。
- 原生库轮廓或标记与裸露阻焊开窗、板边的交叠。这些仍需调整或明确工厂裁剪处理，不能直接视为已通过。
- 封装轮廓压到完全盖油的通孔过孔时，按投影单独记录。判定要求 Excellon 孔已镀铜、孔形与唯一原生 VIA 匹配，并且该侧整个孔与阻焊开窗完全分离。部分开窗孔、元件孔及未匹配孔的投影仍须复核。位号文字的可读性检查继续检查所有孔投影。
- 整层 Gerber 墨迹与阻焊开窗、板外和上述须复核孔的相交均计入检查结果，范围包括板级引线、自定义标记和封装外形。
- 实际墨迹字高与 `--minimum-ink-height-mm` 的比较。原生标称字号不等于实际印刷墨迹高度。

存在文字、轮廓、归属或字高待复核项时，状态为 `SILKSCREEN_REVIEW_REQUIRED`，并返回非零退出码。这表示需要丝印工程复核；不能把所有类别都称为制造硬错误，也不能将待裁剪轮廓包装成 PASS。没有这些待复核项才返回 `ACTUAL_SILKSCREEN_GEOMETRY_SCREEN_PASS`。该状态不代替电气、制造和最终实物验证。

实心圆孔径的弧按 Gerber 的中心弧和圆形端帽计算。中心线离散误差上限为 0.000001 mm，圆帽每象限取 256 段，以覆盖弧端的实际墨迹。

字符连通分量计数不是 OCR。实际字符、1 脚标记、极性及装配可读性仍须结合原生源、装配资料和渲染图人工复核。检查器不承诺工厂丝印裁剪、印刷对位公差或实物可读性。

## 当前复跑与历史差分证据

当前丝印检查可只用仓库中的正式源、state、完整归档、CAM 和字形基线独立复跑。例如从仓库根目录执行，结果另写入 `build/`：

```sh
python3 hardware/devboard-99/easyeda-native/verification/check_native_silkscreen.py \
  --source hardware/devboard-99/easyeda-native/source/PCB-layout.epcb \
  --state hardware/devboard-99/easyeda-native/audit/pcb-routing/final-routed-state.json \
  --archive hardware/devboard-99/easyeda-native/ESPaperPlay-99-Native-WIP.epro2 \
  --zip hardware/devboard-99/easyeda-native/audit/pcb-routing/NOT-FOR-MANUFACTURE-routed-cam.zip \
  --output build/native-final-silkscreen-review.json \
  --minimum-ink-height-mm 0.8
```

`audit/silkscreen/f501-library-silk-persisted-check.json`、`f501-actual-silk-delta-review.json` 和 `final-leaders-and-copper-review.json` 则包含修改前后差分的历史现场证据：前两份限定 F501 两条库丝印的修改，后一份限定位号/四组引导线及非丝印实际 CAM 不变。部分修改前的输入、临时脚本或执行记录保存在 ignored `build/` 路径，正式仓库保留其哈希与结果，但不承诺仅凭当前 checkout 重建全部历史差分过程。

这些差分记录不能替代上述当前丝印检查。当前 `final-silkscreen-review.json` 用同版正式输入重新检查墨迹与开窗/孔/板边，`final-silkscreen-visual-review.json` 记录对应渲染图的人工复核；制造、载流、信号完整性和印刷质量仍属独立验收范围。

本次 9 个共享封装的轮廓修订以 `475f5f5` 为比较起点。[归档与实际层差分](../audit/silkscreen/native-outline-revision.json)和[逐图元归属](../audit/silkscreen/actual-outline-delta.json)对应本次 CAM。`final-leaders-and-copper-review.json`、`final-cluster-detail.png` 及两份 F501 报告记录此前布线阶段。当前的装配方向和间距证据分别见[四处装配定位](../audit/assembly-review/README.md)及[实际丝印间距](../audit/silkscreen/silk-mask-clearances.json)。

## 四层 CAM 预览

```sh
python3 hardware/devboard-99/easyeda-native/verification/render_native_cam.py \
  --cam FINAL-cam.zip --output cam-preview
```

该工具读取 Top、Inner1、Inner2、Bottom 四个实际铜层，以及丝印、阻焊、顶层钢网和板框；输出 `top-pretty`、`bottom-pretty`、`top-silk`、`bottom-silk` 的 SVG 与 2600×2600 PNG。上下视图遵循 Gerbonara 的显示约定，内层读入并不表示在这些外观图上叠画内层铜。视口固定为本项目 99×99 mm 板及四周 1 mm 范围。

渲染器合并 `Drill_PTH_Through.DRL` 与 `Drill_PTH_Through_Via.DRL`，同时保留独立 NPTH；不会遗漏普通过孔钻孔。G85 槽按原始起止坐标转换为等价的铣槽绘制语句，输入文件保持不变。缺少或重复的必需 CAM 层、钻孔文件会报错，不静默省略。

预览用于目视复核，不证明四层导通、参考面连续、孔壁镀铜、阻抗或工艺放行；这些由独立的原生 DRC、实际 CAM 拓扑及制造检查负责。
