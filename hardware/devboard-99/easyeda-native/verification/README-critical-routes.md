# 原生关键网络全端子与返回检查

`check_native_critical_routes.py` 是原工作脚本 `review_critical_native_routes.py` 的正式参数化副本。只使用本目录的 `native_source_geometry.py` 和仓库已跟踪的原生归档解析工具；不会导入 ignored build 脚本。输入允许来自任意路径，但必须是同版原生 source/state/archive 和当前原生短网名网表。

```sh
python3 hardware/devboard-99/easyeda-native/verification/check_native_critical_routes.py \
  --source FINAL.epcb --state FINAL-state.json --archive FINAL.epro2 \
  --netlist FINAL-native-schematic.enet \
  --before-netlist hardware/devboard-99/easyeda-native/audit/pcb-layout/native-pcb.enet \
  --output critical-routes.json
```

`--before-netlist` 必须为 SD 等价通道交换**之前**的已核对历史原生网表，不应随着当前网表被覆盖。仓库原布局阶段 `audit/pcb-layout/native-pcb.enet` 是可复现的历史基线。工具逐针比较当前 236 器件 / 803 实体 pad / 792 逻辑 pin，并单独验证 U701/U706 的 12 个交换 pin、允许变化集合与通道配对双射；不允许网络别名放宽。

保留原脚本的全部 SD/EPD/音频/shared 网络、每个端子和每片孤立源铜检查，另外明确加入 4 个 USB 数据网络。当前检查范围为 79 个网络；实际端子/过孔数量均从输入计算，不把历史计数硬编码成通过条件。参考面、实际 Gerber 铜及整板制造间距仍由各自工具检查，不能把源 POUR 轮廓当作连通铜。

返回统计继续包含信号 VIA，并增加真正同时接 Top 和 Bottom 走线的 PTH。例如 J303.6 MIC_DATA 是主路径换层点，应与过孔一样具备近邻 GND 返回；仅接单层的调试排针末端不误算板内换层。近邻地孔只是原生源证据；实际两内层孔壁接触由 `check_native_reference_planes.py` / `check_native_cam_connectivity.py` 证明。

所有原间隙/接触阈值和 1 mm 优选、2 mm 项目返回筛查保持。`--contact-tolerance-mm` 默认 0.0001 mm，用于原生源坐标取整接触；不应加大它来掩盖未连通。工具把未布网络、孤岛铜、错针、非授权交换、源铜短接和 >2 mm 返回偏差分别列出，有任何一项会返回非零。已明确记录的项目偏好偏差不会被工具自动抹去；它也不是板级制造放行或时序/SI测试。
