# 相邻实际 GND 参考面检查

`check_native_reference_planes.py` 是只读原生源/CAM 几何筛查。它不通过整板 GND 单岛、源 POUR 边界、总覆盖率或“附近有地孔”推断信号下方已有连续参考面。

```sh
python3 hardware/devboard-99/easyeda-native/verification/check_native_reference_planes.py \
  --self-test --output reference-plane-self-test.json
python3 hardware/devboard-99/easyeda-native/verification/check_native_reference_planes.py \
  --source FINAL.epcb --state FINAL-state.json --archive FINAL.epro2 \
  --zip FINAL-cam.zip --output reference-planes.json --svg reference-planes.svg
```

四输入必须同版；依赖 Gerbonara 与 Shapely 2.x，依赖环境说明同本目录其他工具。本机可设置 `PYTHONPATH=build/dfm-r9/python:build/dfm-r9/stencil/python`，代码没有 build 目录依赖。

工具先验证实际原生铜层顺序为 Top / Inner1 / Inner2 / Bottom，才采用 Top→Inner1、Bottom→Inner2 的相邻关系。它按实际 Gerber 极性合成铜并减去实际 Excellon 孔。一个内层铜多边形必须接触与源 GND 匹配的真实镀通孔孔壁，才会被识别为 GND；不能仅因它面积最大或被标称 GND zone 包围就算 GND。用作返回的地孔/PTH 必须实际接触两层内层铜。

检查范围是 USB 四个数据网、SD 六路的原始/串阻后/卡端网络、13 个 I²S/音频逻辑网络及 EPD 六主网/缓冲输出/连接器网。每条源 LINE 的切孔后铜包络须在 CAM 铜内可见，只有源/CAM格式往返误差使用既有 0.00006 mm 容差；对参考 GND 不做膨胀、吸附或跨缝连接。投影面积使用实际外层 CAM 铜与源 LINE 包络的交集。原生线路中心线的每个未参考区间都保留长度、坐标、所属连通空白区、孔标识和网络。

对中途穿越空白区，工具在 0.25 / 0.5 / 1 / 2 / 4 / 8 mm 的逐级局部窗口内裁切真实 GND，要求进、出口两个正面积探针被同一块实际 GND 覆盖。窗口只限制观察范围，不填铜。这可以识别“跨越长度不足 1 mm，但垂直方向的多孔反焊盘链很长，实际返回需远绕”的情况。报告的半径是可建立局部连通的最小被测空间范围，并非返回路径长度或电流仿真。

过孔和真正从 Top 换到 Bottom 的 PTH 同样检查当地 GND 返回，包含 J303.6 这种位于主路径中的排针孔；不能只统计 VIA 图元。仅单层接入的调试排针末端则单列，避免误称它一定在板内换层。通过孔返回的 2 mm 上限及局部绕行 1 mm 范围是项目筛查目标，不是厂商制造硬约束或 SI 保证。报告保留超过目标的原始数值，须明确决定修正或记录项目偏差。

`--self-test` 包含 11 个正反例：完整参考面、普通局部反焊盘、全局仍连通但需远绕的长槽、短距离跨越的长孔链、真实平面分裂、无返回的端部、不能跨越真实窄缝、单层 PTH 调试末端、真正 PTH 换层不得豁免以及其近/远 GND 返回，另检查实际GND孔隙宽度和正面积净空，禁止只有一条边界线而无实际铜面的假通道。原始铜拓扑/孔壁检查器的 16 个反例继续单独保留。

低于 CAM 几何/格式分辨能力的残差会单列 `numerical_scale_review_events`，不会悄悄填平或被计入完整参考。`physical_review_events` 列出需要工程决定的孔链/局部返回问题。存在任一待复核项时，工具返回非零和 `GEOMETRIC_REFERENCE_REVIEW_REQUIRED`，不能自行把它改成板级制造 PASS。SVG 仅显示简化 1 µm 的几何以控制文件大小；所有测量和判断都使用未简化实际 CAM。

此检查只覆盖已经存在的路由；没有 LINE 的网络另列，不能据此宣称所有网络已布完。仍须完成原生 DRC、SCH/PCB 全端子一致、完整 CAM 拓扑/短路、制造间隙和最终局部 CAM 复核。它不计算电磁返回电流分布、阻抗、串扰、EMI、信号边沿、时序、实物铜厚或孔镀层。

`reference-plane-corridors.json` 另外冻结 J303.7 与邻近两只 EPD_DC 反焊盘的专项验收：两层均须分成不同实际空白区、边界间距离 ≥0.15 mm，边界之间无其他空白打断，且中点直径0.15 mm的正面积圆形探针完全位于实际GND。原三孔相连会失败；不靠源封装包络预测最终铺铜通道。
