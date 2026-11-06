# 旧板 MCU、USB 与 SD 审查

日期：2026-11-01。对象为归档工程的 `MCU`、`SD` 页以及 `POWER` 页的 USB 输入部分；与当前固件作接口对照。结论仅针对归档设计，当前使用的核心板是另一硬件目标。

## 证据与方法

- 原件与哈希见 [旧工程接收记录](../legacy-project.md)。以下 `L数字` 指从该归档提取的 `ESPaperPlay.epru` 的 1-based 行号。
- 已目视 `IMAGE/52c20ec4ca8ffa5f.webp`（MCU）、`db9398b04b68f561.webp`（SD）、`04311314e3f2f32d.webp`（POWER）；关键器件及网络与最终记录、PCB `PAD_NET` 交叉一致。预览是归档内缓存，不能替代原软件 ERC 或完整原理图/PCB 一致性检查。
- [结构化证据](../../../../hardware/reference/legacy/review-evidence.json) 保存了器件位号、参数、网络、来源行和 GPIO 对照。352 个唯一器件引脚网络由 385 条 `PAD_NET` 记录归并得到；同号多个焊盘不重复计算逻辑引脚。
- 软件对照为原 ESPaperPlay 仓库固定提交的 [板级配置](https://github.com/xiaobaoaaaaaa/ESPaperPlay/blob/0f6d7c349afdbbeb962a736d84036ce7f8487174/components/board/include/espaperplay_config.h)、[SD 驱动](https://github.com/xiaobaoaaaaaa/ESPaperPlay/blob/0f6d7c349afdbbeb962a736d84036ce7f8487174/components/drivers/sd/src/espaperplay_sd.c) 和 [电源服务](https://github.com/xiaobaoaaaaaa/ESPaperPlay/blob/0f6d7c349afdbbeb962a736d84036ce7f8487174/components/services/power/src/espaperplay_power.c)。本次未改固件。

## MCU 与启动状态

### MCU-01：BOOT 电容应修改，实际启动影响待测

**事实：** U3 是 ESP32-S3-WROOM-1-N16R8。模块 pin27/GPIO0 接 `SW_BOOT`；R28=10kΩ 上拉 3V3，C36=1µF 对地，SW2 按下接地。证据：MCU 图右上；C36 器件 L13317；PCB C36 L19321–19326、R28 L19675–19680、U3 pin27 L19795。EN 另有 R27=10kΩ、C27=1µF，两个 RC 不应被当成同一类按键去抖设计。

**判断：** BOOT 的名义 RC 为 10ms。乐鑫要求在复位释放附近满足 strapping 时序，并明确建议避免 GPIO0 上的大电容；该电容可能影响冷上电、慢电源上升或按键释放时的启动模式。不能仅据 RC 计算认定现有板必然启动失败。[乐鑫启动与 strapping 指南](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/schematic-checklist.html#strapping-pins)

**修改：** 新版 BOOT 去抖以软件为主，重新确定该脚的电容配置；保留 EN 的独立复位延时。用示波器同时观察 3V3、EN、GPIO0，并测试冷上电、慢升压、复位、BOOT 下载组合。固件头文件称按键为 100nF 滤波，而归档 C36/C37/C38 均为 1µF，须按板卡分别维护说明。

### MCU-02：主控与受限引脚可保留，触摸 INT 另见专页

U3 的 3V3 有 C25=10µF 与 C26=100nF，EN 有 10kΩ/1µF 及复位键，GPIO35/36/37 在归档中未接外设。N16R8 的这些引脚被内部存储器占用，维持不使用；GPIO19/20 留给 USB。模块引脚定义按原厂手册表 3-1 核对。[ESP32-S3-WROOM-1 数据手册](https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf)

GPIO3 接触摸 INT，属于 strapping 引脚；其影响是启动配置相关风险，不应简单写成必定不能启动。上拉及唤醒条件见 [显示与触摸审查](legacy-display-touch.md)。天线净空、地回流、去耦实际距离和电源瞬态未由本轮原理图检查验收。

## SD：明确区分当前核心板与归档 PCB

### SD-01：引脚差异已由用户解释，属于板卡适配

按模块物理脚号和原厂表 3-1 对照，29 项固件 GPIO 宏中 27 项与归档 PCB 相同，差异为：

| 信号 | 归档 PCB | 当前固件配置 |
| --- | --- | --- |
| SD_D0 | U3 pin25 / GPIO48 → CARD1 pin7 | GPIO47 |
| SD_D1 | U3 pin24 / GPIO47 → CARD1 pin8 | GPIO48；1-bit 模式下未使用 |
| 总线宽度 | CMD、CLK、DAT0–DAT3 均布线 | 默认 1-bit |

证据：MCU/SD 图；U3 pin24、25 的 PCB `PAD_NET` L19792、L19793；CARD1 pin7、8 的 L19341、L19340。**用户已说明：当前使用的核心板有相关引脚被 LED 占用，因此调整固件使用单线。该差异不认定为 PCB 接线错误或现用固件错误。** 当前核心板的准确型号、LED 具体占脚及实际接线没有在本次审查中补全，不能仅凭常见开发板型号猜测。

**后续处理：** 建立独立的板卡配置：现用核心板的 1-bit 接线、归档 PCB 接线、新版开发验证板接线分别维护。现有 `v2/boards/legacy_n16r8.json` 继承的是固件映射，不能据名称当成该 PCB 的已验收映射。本轮不直接修改任何配置，也不将核心板 LED 限制带入采用独立模组的新主板。

### SD-02：保留四线与外部上拉，新增卡检测和独立电源

**已确认：** CARD1 pin1/2/3/5/7/8 分别为 DAT2/DAT3/CMD/CLK/DAT0/DAT1；R6–R10 均为 10kΩ，从 DAT2、DAT3、CMD、DAT0、DAT1 上拉到 `3V3_PER`；卡座有 C14=10µF、C15=100nF。这与乐鑫对 SD 总线外部上拉的要求相符；1-bit 模式也不意味着可以去掉其余数据脚上拉。[SD 上拉要求](https://docs.espressif.com/projects/esp-idf/en/latest/esp32s3/api-reference/peripherals/sd_pullup_requirements.html)

**修改：** 卡座 CD 明确未接（图上 NC、PCB L19348）；驱动也配置 `SDMMC_SLOT_NO_CD`。新板接入卡检测并定义拔卡处置。各信号当前没有串联调试电阻，布局时预留匹配位置；实际阻值由信号完整性测试决定。不要仅凭完整四线布线就宣称已验证 4-bit/40MHz。

### SD-03：关轨前的软件收尾需要补全

当前 `espaperplay_power_enter_sleep()` 在音频停止、EPD 睡眠和 Wi-Fi 暂停后关闭共享 `3V3_PER`；该路径没有调用现有 `espaperplay_storage_unmount()`，也没有在此建立阻止新 SD 请求、等待在途事务结束、处理总线电平的完整屏障。全仓库搜索未见该卸载函数被业务调用。

**风险推断：** 若关机时有写入或文件系统缓存，可能丢数据；断电外设仍被 GPIO/内部上拉驱动时，还需排查倒灌。不能由代码静态检查推算漏电大小或认定已发生文件系统损坏。此处是软硬件关断契约问题。

**修改与验收：** 新版存储服务先拒绝新请求、等待并结束事务/文件持有者，再卸载文件系统、释放控制器并设置安全 IO，最后关闭独立 SD 电源。测量关断残压和电流；在持续写入、播放读取、异常拔卡及关机交叠场景验证恢复和数据完整性。

## USB 输入与下载接口

### USB-01：基本连接可保留，加入调试余量

**已确认的连接：**

- USB1 的 CC1(A5)、CC2(B5) 分别经 R12、R11=5.1kΩ 下拉到 GND，并非两个 CC 共用一个电阻（PCB L19868、L19874、L19573–L19584）。
- A6/B6 合为 D+，A7/B7 合为 D-；经 D5 的两个通道接 U3 GPIO20/19；USB1 两组 VBUS 合并，外壳脚接 GND。
- D5 实际库料是 **TECH PUBLIC USBLC6-2SC6 / C2827654**。已核对该制造商手册 p1：pin1–6 是同一 I/O 通道，pin3–4 是另一通道，pin2=GND、pin5=VBUS；PCB L19381–L19386 与其一致。不能仅因保护器两端网名不同就误判 USB 断路。[TECH PUBLIC 原厂手册（分销商托管）](https://atta.szlcsc.com/upload/public/pdf/source/20210810/FBD75DE717D6D97BAC6DD7F2B5C09DCD.pdf)

**修改与待验证：** 当前 D+/D- 未串联电阻。新板可按乐鑫指南预留靠近主控的串阻/电容调试位置；不能据此认定旧板 USB 必然不工作。检查正反插枚举、下载、数据传输、带载插拔、走线阻抗及 ESD 回流。器件手册给出的 ESD 等级不等于整板通过 ESD 测试。

USB 供电允许电流、输入浪涌、充电电流与系统负载之和、VBUS 检测和电池回灌是电源问题，统一见 [电源审查](legacy-power.md)。本次没有测量 USB 电气波形或运行合规测试。

## 归纳

| 分类 | 项目 |
| --- | --- |
| 保留 | N16R8 模组、EN 复位结构、USB 原生下载、独立 CC 下拉、USB 双通道 ESD 拓扑、SD 四线与五路外部上拉 |
| 修改 | BOOT 电容方案、板卡配置区分、SD 卡检测与独立电源、关机存储收尾、USB/SD 信号调试位置、与实际参数不一致的注释 |
| 待验证 | 当前核心板准确型号/接线、归档 PCB 对应实板版本、启动波形、USB 枚举与带载插拔、SD 4-bit 性能/插拔/关机数据完整性、天线与实际布线 |
