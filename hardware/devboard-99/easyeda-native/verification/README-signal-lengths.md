# USB / SD / EPD 实际原生长度

`check_native_signal_lengths.py` 只读当前 PCB 源、对应的器件状态和原生工程封装，重新量算 16 条端到端链与 25 条诊断连接，共 68 个同网分段。规则在 `signal-length-rules.json`；不引用工作目录的候选或历史报告。

```sh
export PYTHONPATH=build/dfm-r9/python:build/dfm-r9/stencil/python
python3 hardware/devboard-99/easyeda-native/verification/check_native_signal_lengths.py \
  --source hardware/devboard-99/easyeda-native/source/PCB-layout.epcb \
  --state hardware/devboard-99/easyeda-native/audit/pcb-routing/final-routed-state.json \
  --archive hardware/devboard-99/easyeda-native/ESPaperPlay-99-Native-WIP.epro2 \
  --output hardware/devboard-99/easyeda-native/audit/pcb-routing/signal-lengths.json
python3 hardware/devboard-99/easyeda-native/verification/check_native_signal_lengths.py --self-test
```

每腿必须具有指定网络上的真实实体焊盘，按当前原生 LINE 与 pad/via 接触图选取最短**裸露线长**；保留所经源对象 ID、过孔 ID、最小/最大线宽。焊盘内铜、孔壁和封装内部长度均未计入。电阻、TMUX、缓冲器两侧是分开的同网腿，报告明确列出没有测量的器件内部转换。不存在的路径或指定网络上的非 LINE 铜形返回失败，不能拿候选长度填补。

USB 分 A/B 两组触点到 ESP32，并分别比较 P/N。SD 六路从 MCU 经源电阻和 TMUX 到卡座。EPD 五路从 MCU 经缓冲和串联电阻到屏连接器，BUSY 则反向经 U602 到 MCU。另保留诊断排针、上下拉、USB DNP 电容相关端子间测量；诊断端子距离不冒充整个悬空支路长度。

这个一致的裸露线长口径与早期“中心线加焊盘中心跨度”的候选表不同，不能交叉比较后断言物理线路缩短。它也不是完整传播延迟、USB 90Ω 证明或屏幕延长线长度。已通过的完整原生拓扑/CAM、相邻 GND 参考面、换层回流和首板波形测试仍各自必要。

六个自测覆盖：最短长度与最低电阻路线的区别、悬空分支不计入端到端长度、实际空隙保持断开、不同层无孔不连接、真实同网过孔连接并计数、异网桥不连接。底层 helper 默认仍按电阻选路，旧电源 24 条结果已逐字段完全回归一致；新增长度模式不会更改电源审查结果。
