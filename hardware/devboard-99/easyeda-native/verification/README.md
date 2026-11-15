# 原生布局 CAM 复核

此目录保存可离线复跑的只读检查器、Gerber/Excellon 几何辅助代码及三份物理目标计划。它们不调用嘉立创EDA/KiCad，不修改设计；只读取指定输入并写入 `--report`。目标 JSON 中的初始来源和过程说明属于历史取证，不能作为实时封装导入指令。

依赖为 **Gerbonara 1.6.2、Shapely 2.2.0**，本机验证使用 Python 3.15.2。可在独立 Python 环境安装这两个版本，或通过 `PYTHONPATH` 指向已有依赖目录；未把 venv/第三方包纳入工程。本机已准备的环境可这样使用：

```sh
# 从仓库根目录运行；已有 venv 提供 Shapely，PYTHONPATH 提供 Gerbonara。
export PYTHONPATH="$PWD/build/dfm-r9/python${PYTHONPATH:+:$PYTHONPATH}"
build/easyeda-native99/pcb-plan/.venv/bin/python \
  hardware/devboard-99/easyeda-native/verification/check_native_special_cam.py \
  --zip hardware/devboard-99/easyeda-native/audit/pcb-layout/NOT-FOR-MANUFACTURE-layout-cam.zip \
  --state hardware/devboard-99/easyeda-native/audit/pcb-layout/final-layout-state.json \
  --report /tmp/espaperplay-native-special-cam-check.json

build/easyeda-native99/pcb-plan/.venv/bin/python \
  hardware/devboard-99/easyeda-native/verification/check_native_smd_paste.py \
  --zip hardware/devboard-99/easyeda-native/audit/pcb-layout/NOT-FOR-MANUFACTURE-layout-cam.zip \
  --state hardware/devboard-99/easyeda-native/audit/pcb-layout/final-layout-state.json \
  --source hardware/devboard-99/easyeda-native/source/PCB-layout.epcb \
  --report /tmp/espaperplay-native-smd-paste-check.json
```

在另一台机器上，安装依赖后将上述解释器路径换成该环境的 `python` 即可；检查器自身不依赖被 Git 忽略的 `build/` 目录。报告输出目录须已存在。

| 检查器 | 本次布局的核查范围 |
|---|---|
| `check_native_special_cam.py` | U101/U203/U802/U301/U803 共 153 项实际 CAM 几何：焊盘、圆角、锡膏开口、22 个热孔/铜盘，以及各自指定的铜、阻焊和声道约束。U101 包含连续孔位/印刷公差包络。 |
| `check_native_smd_paste.py` | 236 器件中的 677 个已装配 SMD 焊盘锡膏存在性/低覆盖筛查。排除原生 DNP 31、PTH 70、U301 中央零膏 9、J501 的 16 个焊盘。 |

J501 由 `audit/pcb-layout/j501-final-cam-review.json` 单独复核。通用筛查将其标为 `NOT_EVALUATED_HERE_USE_SEPARATE_CAM_REVIEW`，不再称它尚未整改，也不会生成未经本脚本检验的 J501 PASS。153/677 是本次输入对应的数量，不是接受器件清单发生任意变化的保证。

几何代码采用原生/Gerber 的 +Y 向上坐标，圆弧逼近误差 0.00001 mm、形状比较容差 0.00006 mm，阈值保持原检查器不变。宏内明暗操作局部组合；原生 G85 槽孔仅在内存展开成等价直线铣槽。综合 PTH 与 VIA-only 钻孔文件出现的同一命中，只有在几何及类型精确匹配后才作为两种输出视图合并，并保留报告记录。没有 B.Paste 文件按空层处理，其他必要层缺失会终止。

退出码 0 代表所列范围通过，1 代表发现不满足项；特殊封装脚本在 ZIP/state 尚未提供时返回 2。报告记录输入和检查脚本 SHA256。应对同一个最终冻结版本复跑，不能仅替换旧报告中的哈希。

这些结果只验证布局/封装 CAM。主信号布线、完整平面和最终丝印尚未完成，不证明全板连通或可生产。U101 印刷精度/钢网边缘/孔位分析条件、开孔吸锡、回流空洞与温升、MIC 声学密封仍保留首板验证条件；全板 no-via 区域的独立几何检查也不在这两份脚本中。
