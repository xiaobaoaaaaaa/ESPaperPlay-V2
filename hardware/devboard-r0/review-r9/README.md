# r9 制造及自行装配审查证据

审查日期2026-11-11。PCB保持r8；原理图绘图r6/电气r5。r9是制造审查与钢网装配变体，不是新的电气或PCB修订。源板SHA为 `1a4556d866cc1352a2c45b674c94d2f233edf28c3e003bd96c8f6caf1e630681`。

当前结论与后续工艺条件见[主报告](../../../docs/v2/hardware/manufacturing-review-r9.md)，实际输出见[审查包](../output/manufacturing/r9-review/README.md)。本地审查已完成，工厂工艺签认与实物性能未验证；不是制造放行。

| 证据 | 覆盖内容 |
|---|---|
| [drc.json](drc.json)、[independent-board-check.json](independent-board-check.json) | KiCad 10.0.8，0错误、0未连接、0原理图差异；236器件/774逻辑引脚/804编号焊盘、38封装库检查；1条既有U301绘图警告 |
| [cam-readback.json](cam-readback.json)、[drill-report.txt](drill-report.txt) | Gerbonara独立读取实际制板输出，663孔逐一匹配、4段板框中心线与9图层清单 |
| [process-review.md](process-review.md)、[process-sources.json](process-sources.json) | 常规四层工艺、两类焊区内孔、阻抗、孔铜假设边界 |
| [impedance-calculator-review.json](impedance-calculator-review.json) | 官方计算器真实输入/输出，线宽差与阻抗误差的区别；未宣称工厂确认 |
| [native-process-inventory.json](native-process-inventory.json) | 原生最窄线0.18mm、孔/槽/孔距及尺寸清单 |
| [stencil-review.md](stencil-review.md)、[stencil-audit.json](stencil-audit.json) | 实际阻焊/焊膏布尔几何、孔暴露、203位DIY钢网、铜/孔/阻焊保持断言 |
| [special-hole-register.csv](special-hole-register.csv) | 23个焊区内孔与44个邻近孔的UUID/坐标、实际阻焊暴露和印膏重叠 |
| [stencil-microphone.png](stencil-microphone.png) | 麦克风钢网加桥前后，来自实际Gerber，不是示意猜测 |
| [mechanical-assembly-review.md](mechanical-assembly-review.md)、[mechanical-review.json](mechanical-review.json) | 240封装间距、7接口通道、孔/天线/声道与自装工序 |
| [mechanical-population.json](mechanical-population.json) | 独立原生字段/坐标及分组清单 |
| [assembly-export-validation.json](assembly-export-validation.json)、[cross-check.json](cross-check.json) | 装配字段/分组/坐标、导出重复性及独立交叉检查 |
| [verification-r8-before.json](verification-r8-before.json) | 更新前原始验证清单，历史文件不改写 |

回读器接受全部图层和钻孔；其G90 header位置、RoundRect多参数、裸板无paste提示已记录。这不等于Gerber完整铜网络电气DRC或工厂CAM认证。CAM正反面预览已目检板框、连接器、焊盘、孔和丝印；可见位置与原板一致，不能证明孔内填充或隐藏焊点质量。

复现需要系统KiCad CLI和Python `pcbnew`（本轮10.0.8、Python3.15.2）。额外Python依赖：`gerbonara==1.6.2`、`shapely==2.2.0`、`matplotlib==3.11.2`；PNG预览还需要系统PyGObject/Rsvg与pycairo。可安装到独立依赖目录并通过PYTHONPATH加载；脚本本身不安装软件。本地依赖目录不随Git分发。

从仓库根目录运行（`/path/to/dependencies`替换为已有依赖目录；不能复用Python ABI不匹配的旧build目录）：

```sh
PYTHONPATH=/path/to/dependencies python3 tools/export_manufacturing_r9.py --render
PYTHONPATH=/path/to/dependencies python3 tools/prepare_stencil_r9.py
python3 tools/export_assembly_r9.py
python3 tools/package_manufacturing_r9.py
PYTHONPATH=/path/to/dependencies python3 hardware/devboard-r0/review-r9/mechanical-check.py --output-directory build/dfm-r9/mechanical-recheck
python3 hardware/devboard-r0/review-r9/process-check.py --output build/dfm-r9/process-recheck.json
```

钢网派生PCB仅存于build目录，不是编辑源。导出器固定来源哈希，源板改变后需复审脚本/规则，不能直接沿用r9的工艺结论。KiCad输出含生成时间，重新导出后需重新回读并更新文件哈希；已有交付文件的完整性用仓库根目录 `python3 tools/verify_repository.py` 检查。
