# 最终原生验证 runner

`run_final_verification.py` 把 21 项只读检查串行运行，逐项保留退出码、耗时、日志、结果状态及输入/工具哈希。只写报告；不会调用实时API、编辑CAD、更新Git或上传工厂。默认输入全部来自正式 `easyeda-native/`，不存在 build 工作目录代码依赖。

```sh
# 本机现有 Python 依赖；别处安装 Shapely 2.x / Gerbonara 后无需此行。
export PYTHONPATH=build/dfm-r9/python:build/dfm-r9/stencil/python
python3 hardware/devboard-99/easyeda-native/verification/run_final_verification.py --plan-only
python3 hardware/devboard-99/easyeda-native/verification/run_final_verification.py
```

默认正式文件对应 `final-promotion-plan` 的路径：`source/PCB-layout.epcb`、顶层 `ESPaperPlay-99-Native-WIP.epro2`、`audit/pcb-routing/final-routed-state.json`、`native-pcb.enet`、`native-board-check.json`、`NOT-FOR-MANUFACTURE-routed-cam.zip`，以及现有 `audit/` 中当前原理图源网表/DRC/针脚映射/别名和全部 source 页面、8个整改封装。`audit/pcb-layout/native-pcb.enet` 保留为 SD 等价交换前的历史基线，不要覆盖。

默认输出 `audit/pcb-routing/verification-run/`。`verification-summary.json` 记录本轮确实执行的检查；每份子报告必须在本轮写出，旧残留报告不算新结果。源码、规则、封装、原理图或输入文件在运行中变化会立即停止后续检查并返回非零，防止混合版本。正常失败不会被吞掉，仍继续运行其它独立只读检查收集完整证据。

`--only cam-self-test,power-self-test,reference-self-test,signal-length-self-test,review-classifier-self-test` 可单独复现 61 项几何与分类自测；其它 job 名在 `--plan-only` 输出。`--output-dir PATH` 可指定另一报告目录，`--native-dir PATH` 可指定另一份已经按同样目录结构冻结的正式工程。默认 J501 包含13个真实CAM内存负例；已有同版本证据、仅复跑其它数据时可显式用 `--skip-j501-negative-tests` 跳过这些重复变异，J501真实CAM检查始终保留。

完整顺序包含原生DRC导出为空、SCH和PCB逻辑针脚、803实体pad、原理图归档、PCB/封装/叠层归档、5组自测、制造边界、5关键封装专项、通用SMD膏、J501、实际CAM拓扑、79关键网络/真正PTH换层、实际相邻参考面、电源24路径、I²S全端子及6路径、USB/SD/EPD 16条端到端链与25条诊断连接。它不包含实时DRC执行或目视丝印审查；原生执行时启用的规则/忽略项证据仍须主线程独立保留，空的旧DRC文件不能替代最终实时复核。

任何未布、错针、短路、CAM 或新参考面问题仍归入 `UNRESOLVED_CHECK_FAILURES`。确切已记录的 EPD_PAD_SCLK 返回孔 2.246160 mm，以及静态触摸隔离使能 TOUCH_IO_EN 返回孔 2.504406127 mm，超出项目 2 mm 偏好，会单列为工程审查项。TOUCH_IO_EN 仅可由 critical-routes 的精确锚点分类；其实际 GND 孔同时接触两内层的证据保存在 `../audit/pcb-routing/touch-io-en-return-review.json`，这不会豁免新的相邻参考面问题。明确的微小数值残差也单列；孔 ID、GND ID、位置和距离必须匹配 `engineering-review-items.json`，实际相邻平面接触仍须证明。长槽、破损 GND 通道或未知返回孔绝不被这一分类接纳。电源细颈/宽度目标和 I²S 长度参考偏差也会列入摘要。

完整检查没有硬错误而存在上述记录时，状态为 `COMPLETE_GEOMETRY_CHECKS_WITH_RECORDED_ENGINEERING_REVIEWS`；部分运行有明确 `SELECTED_` 前缀。这不是制造 DRC 失败，也不是制造放行。子报告、原始阈值及退出码全部保留，runner 仍因原始非零结果返回非零，防止 CI 静默放行。全部子命令退出0也只表示所选检查成功；目视、装配条件和硬件资格仍独立。

已对 runner 自身验证：子进程退出7会被保留、无效JSON不能算新报告、被监视输入中途变化会终止、实际仍有17个连接项的原生导出不能通过最终空DRC检查。最终正式资料尚未提升前，`--plan-only` 会列出缺少文件；不应把中间样本的旧报告改哈希伪装最终成功。

PCB 归档检查把 `POURED` 作为关联现有 `POUR` 的派生缓存单独核验。仅缓存的已识别路径坐标允许最多 1 ULP、ARC 角度允许最多 1e-10° 的数值表示差，逐值保留两侧原数值及差额；缓存填充 ID、字段、拓扑、宽度和其它值仍精确比较。`POUR` 定义与全部实体、规则、叠层不使用此公差，也不把缓存一致当成实际 CAM 铜几何证明。组件角度不做归一化。独立 26 项归档正反例包含额外/缺失微段、1 ULP 实体改动、2 ULP 缓存坐标、缓存角度和填充 ID 等，复现命令如下（不计入上述 21 个 job）：

```sh
python3 tools/test_easyeda_native_pcb_archive.py --output hardware/devboard-99/easyeda-native/audit/pcb-routing/archive-checker-self-test.json
```
