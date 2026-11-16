# 原生电源与 I²S 路径指标

这两个入口只读取同一保存重开版本的原生 PCB、引脚状态和官方 `.epro2` 库。它们复用本目录的 `native_source_geometry.py`、`native_exact_smd.py` 和仓库正式归档解析器，不依赖被忽略的 `build/` 代码，不调用实时 API。运行依赖为 Python 3 和 Shapely 2.x；本机已有环境可通过 `PYTHONPATH=build/dfm-r9/stencil/python` 使用，干净环境可安装 `shapely==2.2.0`。

```sh
VERIFY=hardware/devboard-99/easyeda-native/verification
python "$VERIFY/check_native_power_paths.py" --self-test

python "$VERIFY/check_native_power_paths.py" \
  --source "$PCB" --state "$STATE" --archive "$ARCHIVE" \
  --output /tmp/espaperplay-power-paths.json

python "$VERIFY/check_native_i2s_paths.py" \
  --source "$PCB" --state "$STATE" --archive "$ARCHIVE" \
  --output /tmp/espaperplay-i2s-paths.json
```

`PCB`、`STATE`、`ARCHIVE` 应设置成当前冻结版本的实际路径，不能混用旧布局和新布线。输入全部附 SHA256。正式归档与源一致性仍须由独立归档检查器验证。

`power-path-rules.json` 保存既有 24 条电源路径的端子 ID、线宽目标、累计窄颈长度预算和 R20 复核限值；没有降低原阈值。默认外层铜厚 35 µm，可用 `--copper-um` 指定已确认厚度。线宽分类的 0.00025 mm 容差只用于原生宽度数值量化，不放宽间距。输出同时生成 Markdown 表。退出码 0 表示 24 条路径均可量化且线段 R20 低于工程复核限值；线宽/窄颈目标偏差仍逐项保留，不能解读为全部设计目标或制造放行通过。缺路径或电阻超过限值返回 1，输入无法解析返回 2。

`i2s-path-rules.json` 保存 13 个网络和 6 条完整信号链。检查器枚举所有实际端子，报告逐段路径、调试排针中心的入射走线，并移除排针及其局部铜反向验证它确在主干上；另报告 U801 到三个源端电阻的实际中心线长度、全部信号过孔到 GND 贯通过孔/PTH 的距离。GND PTH 必须具有四铜层贯通属性才能计入。首测模式为 48 kHz、双 32-bit slot、3.072 MHz BCLK。退出码 0 仅表示这些网络端子全部接通且各信号换层点的回流贯通点距离不超过 2 mm；1 mm 偏好目标和 10 mm 几何长度差参考值的偏差仍要审阅。该距离不证明接地过孔已接入两内层实际铺铜。

`native_trace_path_metrics.py` 沿实际 LINE、焊盘和过孔接触建立图。只接受真实铜包络相交的接触，不把相邻但有铜隙的对象连通；不计入无法解释的 FILL/POURED 缓存。中心线因原生取整产生小偏移时，只有铜实际相交才可桥接，偏移桥长度按较窄线宽计费。窄颈长度沿完整选定路径累计，不因 LINE 被拆分而清零。源 SMD 铜形状来自官方归档中的实际封装与 PCB 实例变换。

R20 不含焊盘扩散、电镀孔桶壁、连接接触和温升影响，也没有求解并联支路分流，属于线段电阻下界。信号的暴露走线长度不含焊盘内部、器件内部和垂直孔桶长度，不能代替完整传播延迟。缓冲器延迟、时钟占空比、MCU IO 矩阵、反射以及接收端建立/保持时间尚需单独核验。最后仍须原生 DRC、原理图/PCB 网表、实际 CAM 铜岛/参考平面以及带载硬件测试。
