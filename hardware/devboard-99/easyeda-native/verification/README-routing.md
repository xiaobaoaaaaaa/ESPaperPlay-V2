# 原生布线、制造边界与实际 CAM 连通性复核

本目录新增的检查器只读取指定原生快照、官方 `.epro2` 和 CAM，不调用嘉立创EDA，不修改工程或库。原有 `check_native_special_cam.py`、`check_native_smd_paste.py` 及其几何辅助代码保持原样。新增代码不依赖被 Git 忽略的 `build/` 文件；运行依赖仍为 Gerbonara 1.6.2、Shapely 2.2.0。

从仓库根目录运行，先在独立 Python 环境安装上述依赖。以下四个变量必须对应**同一保存、重开后冻结版本**；归档还须通过 `tools/check_easyeda_native_pcb_archive.py` 的独立一致性检查。路径只作参数示例，旧布局 CAM 不能证明最终布线通过。

```sh
VERIFY=hardware/devboard-99/easyeda-native/verification
PCB=hardware/devboard-99/easyeda-native/source/PCB-layout.epcb
STATE=hardware/devboard-99/easyeda-native/audit/pcb-layout/final-layout-state.json
ARCHIVE=hardware/devboard-99/easyeda-native/ESPaperPlay-99-Native-WIP.epro2
CAM=hardware/devboard-99/easyeda-native/audit/pcb-layout/NOT-FOR-MANUFACTURE-layout-cam.zip
mkdir -p /tmp/espaperplay-routing-review

python "$VERIFY/check_native_routing_boundaries.py" \
  --source "$PCB" --state "$STATE" --archive "$ARCHIVE" \
  --output /tmp/espaperplay-routing-review/boundaries.json

python "$VERIFY/check_native_routed_special_cam.py" \
  --source "$PCB" --state "$STATE" --archive "$ARCHIVE" --zip "$CAM" \
  --report /tmp/espaperplay-routing-review/special-cam.json

python "$VERIFY/check_native_cam_connectivity.py" \
  --source "$PCB" --state "$STATE" --archive "$ARCHIVE" --zip "$CAM" \
  --output /tmp/espaperplay-routing-review/copper-connectivity.json
```

| 入口 | 核查内容与边界 |
|---|---|
| `check_native_routing_boundaries.py` | 原生走线和过孔对 24 个四层禁区、0.30 mm 板边、普通 NPTH/槽 0.30 mm、MIC NPTH 局部 0.20 mm；过孔钻孔边距 0.25 mm；除既有 22 热孔外，过孔铜环至所有 SMD 铜盘至少 0.15 mm。两内层显式铜只允许 GND，检查 13 条物理层记录、顺序和启用的四个铜层，并核对原有 22 热孔/11 条 GND 线未变。 |
| `check_native_routed_special_cam.py` | 保留 U101/U802/U203/U301/U803 焊盘、锡膏、热孔、声孔及声学内环的严格几何检查。U802/U203 局部区域内新增孔须逐个与当前原生源位置、孔径和电镀类型匹配，不能凭区域内数量一律拒绝或接受。MIC 环外新增 GND 铜只能由同一原生源中的显式 GND 走线/孔解释；环内声道尺寸仍严格不变。 |
| `check_native_cam_connectivity.py` | 按 Gerber 明暗极性计算实际四层铜，扣除实际钻孔/槽孔轮廓，只有经源文件与 Excellon 唯一匹配的电镀孔才能连接不同铜层。检查所有源网络的铜岛数量、异网短接、NC 独立隔离、源铜缺失、未归属铜岛，以及实际铺铜对四层禁区和 0.30 mm 板边的侵入。 |

`native_source_geometry.py` 解析原生 PCB 与官方归档中的库，复用仓库正式归档校验器的 ticket/client/tombstone 合并规则。原生毫米坐标为 mil × 0.0254，+Y 向上；原生弧最大采样步长 0.25°。不支持的铜图元、陈旧的元件位置/引脚状态、底层元件或无法解释的孔形会明确失败。`POURED` 运行时缓存的内部比例没有被猜测，缓存不计作铜或电气连通；实际铺铜必须由 CAM 入口检查。

`native_exact_smd.py` 使用原生库的精确焊盘尺寸、位置、RECT 圆角百分比及 PCB 实例变换，避免引脚 API 的 0.1 mil 显示取整影响过孔邻盘判断。边界比较容差是 **0.0001 mm**；不是放宽 0.15 mm 标称间距。Gerber 曲线误差保持 **0.00001 mm**、局部形状比较容差 **0.00006 mm**，全板钻孔形状匹配容差 **0.00015 mm**；没有通过膨胀铜岛跨越实际铜间隙来认定连接。

`thermal-feature-baseline.json` 固定保存布线前批准的 22 个热过孔与 11 条 GND 铜线及来源 SHA256。这样正式 `PCB-layout.epcb` 更新成最终布线后，新增普通地孔也不会被误当作热孔豁免。`--baseline` 可显式指定原始 `.epcb` 或同 schema 的 JSON；器件数不符合 22/11 会失败。`routing-net-classes.json` 仅用于长度报告分类，不修改线宽、间距规则，也不将有分支的中心线长度总和冒充端到端长度。

三个入口退出码 0 表示各自范围通过，1 表示发现不满足项；特殊封装入口输入 ZIP/state 缺失返回 2。报告含输入 SHA256，不能把旧报告哈希替换成新版本复用。Native DRC、原理图/PCB 逐针网络对照、归档与源快照一致性、24 条电源路径电阻/窄颈预算及高速信号端到端指标仍需独立核验。实际制造、焊接、声学密封、热性能和带载测试不在离线检查范围内。
