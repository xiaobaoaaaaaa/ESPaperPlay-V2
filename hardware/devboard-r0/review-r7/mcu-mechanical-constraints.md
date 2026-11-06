# MCU、接口与独立 PCB 审查输入

日期：2026-11-06。只读检查现有 r6 电气设计；本文件是布局工作输入，不修改正式工程。

## 模组放置

- U301 为 ESP32-S3-WROOM-1-N16R8，现有 native footprint `RF_Module:ESP32-S3-WROOM-1`。
- 封装 0° 时天线朝 -Y。现有 all-copper-layer rule area 为 x=-24..24、y=-27.75..-6.75 mm，禁止铜区、走线、过孔、焊盘和其他封装；不得在导入/克隆时丢失。
- 模组本体约 x=-9..9、y=-12.75..12.75 mm。原生大 bounding box 包含 15 mm 天线净空；不能将 48 mm 宽误认为实体尺寸，也不能将整个 bounding box 当作必须放入板内的器件外形。
- 顶边出天线推荐：U301 原点 y=顶板边+6.75 mm，天线区域伸出基板约6 mm，铜焊盘留在板内。也可等价旋转至其他板边。使用完整地平面支持屏蔽罩/模组GND侧，不让开关电感、金属接口或外接线束占据天线净空。
- U301 有多个同号41接地/散热焊盘及0.2 mm孔；所有41均应赋GND。无编号焊膏开口不可误当电气引脚。
- C301(10u)/C302(100n)靠模组3V3输入脚2；R301/C303复位RC靠EN脚3，SW301可放到可操作位置。USB MCU脚13/14位于模组左下侧（0°时）。

## USB 与 SD 布局通道

- R503/R504=22R和C501/C502 DNP位置靠模组USB引脚；U501数据ESD靠J501；USB线从接口经ESD到串阻再到MCU，避免岔长支线。
- 预留连续GND参考的USB差分走廊；目标90Ω±10%，同层等长，必要换层配回流GND孔。当前阶段不声称已实现阻抗。
- SD CMD/DAT0–3需双向，不能在摆放时误当固定输出。优先让MCU—TMUX—SD卡线路总长短，目标控制在50.8mm以内，供后续50Ω与等长布线（相对CLK±1.27mm）审查。
- 不把裸ESP32芯片的晶振/RF匹配元件建议机械套用于已集成模组；现有原理图/封装不增加模组内部元件。

## 接口朝向与操作空间

以下均是0°封装局部坐标，旋转时要一起变换。

- J501 USB4105：信号焊盘在y=-3.68mm，插口朝+Y。板边安排在插口侧；不要让屏蔽壳/固定孔跨出导致无法焊接。USB4105-GF-A固定脚0.95mm与1.6mm板的工艺条件保持待验证。
- J701 DM3AT：信号触点在y=-7.725mm，卡插拔朝+Y；固定外壳前缘约y=8.325mm，F.Fab有伸出卡轮廓至约y=13.7mm。五个F.Cu规则禁布区必须保留；卡退卡操作区不可被排针、螺钉头遮挡。机械detect pad9/10不可交换。
- J601 EPD FPC：信号落点y=0，壳体向+Y，0°时pin1在x=-5.75mm；伸出/锁扣操作区向+Y。24Pin编号及两个SH不可按外观镜像。
- J406 touch FPC：信号落点y=0，壳体向+Y，0°时pin1在x=+1.25mm（和J601相反）；保留正面开锁空间，不能根据同为0.5mm间距推断pin1方向相同。
- J102/J103/J801 Phoenix 1751248：本体7.5×7.3mm，高8.5mm，3.5mm针距；沿板边排布并提供接线和螺丝刀操作空间，邻近支撑点辅助拧紧。极性丝印要位于器件外侧仍可见。
- 外接电池/扬声器/屏幕不占PCB贴装面，连接器和线束出口仍占操作空间；各类跳帽和测流断点需要镊子/探针可达。

## 后续独立核对清单

1. 236个电气位号逐个出现一次；6个DNP保持；安装孔等机械位号另计且不得误列制造电气BOM。
2. 所有组件value、封装ID、候选MPN、DNP与r6一致；sheet/symbol UUID路径正确供KiCad更新PCB使用。
3. PCB每个编号pad的net与XML相同；重复号铜焊盘全部覆盖；NC不增加任何连接；若采用KiCad单引脚unconnected命名网络须保持其独立性；所有181网络按导出契约保留。
4. 4铜层配置与布局说明一致；正式走线/铜区未完成时明确保留未连接DRC，不通过关掉unconnected检查伪造通过。
5. 原生封装规则区完整；天线禁布没有其他封装/铜/孔，SD五块禁布保留，麦克风声孔按专项约束。
6. 板框单一闭合，不自交；机械孔到板边和器件留余量；插口方向朝外、卡/FPC锁扣/端子工具空间合理。
7. 所有实装器件courtyard不相交、无焊盘短接；边缘接口仅机械外壳允许伸出，实际焊盘/固定孔在板内。
8. 去耦/反馈/高di/dt组件距离按各专项约束；MCU电源、USB RC、ESD等有明确靠近对象。
9. DRC运行默认全严重度，另做 --schematic-parity。布局阶段报告把未布线与真正布局问题分开统计，不批量排除。
10. 顶面/底面2D与3D视图人工检查标号、方向、可插拔及天线；缺失3D模型不影响电气验证，但不能当作真实机械完整性证明。

## 原厂与本地证据

- Espressif PCB layout guidelines（2026-11-06在线复核）：https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html ，重点模块放置、USB、SDIO章节；本地归档 `hardware/reference/mcu-usb/esp32s3-usb-layout-guidelines.html`。
- 现有封装 `/usr/share/kicad/footprints/RF_Module.pretty/ESP32-S3-WROOM-1.kicad_mod` 及对应USB/SD标准库文件；本地库J601/J406/Phoenix及 `hardware/devboard-r0/review-r4/mechanical/review.json`。
- 当前电气网表 `hardware/devboard-r0/output/validation/peripheral-r6.net.xml`。

## 当前工具能力

- KiCad CLI / pcbnew版本10.0.7-1.fc44；pcbnew可加载封装和板、设NETINFO_ITEM、PCB_SHAPE、ZONE、保存native board。导入会出现已知三条PROPERTY_ENUM no-choice诊断，但API调用可成功。
- CLI PCB DRC支持 `--schematic-parity --format json --severity-all --exit-code-violations`。
- CLI `pcb render`支持top/bottom/透视等PNG；`pcb export`支持SVG/PDF/STEP等导出。
- 原生封装规则区检查API：`GetDoNotAllowTracks/Vias/Pads/ZoneFills/Footprints`。注意没有`GetDoNotAllowCopperPour`方法。
