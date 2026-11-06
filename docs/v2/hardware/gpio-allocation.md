# GPIO 分配表

状态：原理图候选，未烧录到新板。2026-11-02 已在[KiCad外设草案r2](../../../hardware/devboard-r0/README.md)落图并核对模组实际焊盘和跨页网表。表中的 GPIO 数字均为 ESP32-S3 GPIO 编号，不是模组焊盘编号。

## 可用引脚与设计取舍

WROOM-1 引出最多 36 个 GPIO；N16R8 使用的 Octal PSRAM 占用 GPIO35/36/37，这三个脚不用于外设。USB 固定保留 GPIO19/20，BOOT 使用 GPIO0；新板避免将 GPIO3/45/46 用于外设，以简化绑带电平与下载恢复。这样留下 27 个普通业务 GPIO。[模组数据手册](https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf)、[原理图设计指南](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/schematic-checklist.html)

下面的候选方案使用这 27 个引脚，保持全部高速数据、触摸复位/中断、正常电源键和音频静音直连。EPD/SD/触摸使能、充电控制和卡检测转到 TCA9539；GPIO42 专门复位扩展器。GPIO2/44 交换原候选用途，使 USB 在位信号可以唤醒。引脚预算和实际焊盘网表核对已闭合，上电/复位/掉电等实物电气验证尚未完成。

## 当前固件配置与新板候选

方向以 MCU 为参照。`I/O` 包含协议双向或初始化期间方向切换。旧配置列来自现有固件，不能直接当作归档 PCB 接线：用户已确认当前核心板有 LED 占脚，因此 SD 使用调整后的单线配置。归档 PCB 的 SD_D0=GPIO48、SD_D1=GPIO47；下表旧配置为 D0=47、D1=48，属于不同板卡目标。详见 [SD 审查与用户说明](review/legacy-mcu-usb-sd.md)。新板候选尚未冻结，不受核心板 LED 占脚限制。

| 信号 | 旧配置 GPIO | 新板候选 GPIO | 方向 | 电气/运行约束 |
| --- | --- | --- | --- | --- |
| EPD SCLK | 16 | 16 | O | SPI2；上电后再建立总线 |
| EPD MOSI | 15 | 15 | O | 屏幕断电前处理信号电平 |
| EPD CS | 17 | 17 | O | 默认不选中，拉电阻归属需避免倒灌 |
| EPD DC | 18 | 18 | O | 与屏幕供电域协调 |
| EPD RESET | 8 | 8 | O | 按实际面板时序，不沿用未核对的延时值 |
| EPD BUSY | 9 | 9 | I | 直接采样，可留中断能力 |
| I²C SDA | 10 | 10 | I/O | 常供电侧连接扩展器/电量计；触摸支路独立隔离 |
| I²C SCL | 13 | 13 | O/I | 上拉、电容与掉电隔离共同核算 |
| GT911 INT | 3 | **1** | I/O | 脱离 GPIO3 绑带脚；初始化时允许输出，运行时输入；具备 RTC GPIO 功能 |
| GT911 RESET | 14 | 14 | O | MCU直控、经TMUX隔离；复位与地址选择不能由异步页面操作控制 |
| SD CLK | 38 | 38 | O | SDMMC，布线按 4-bit 校验 |
| SD CMD | 39 | 39 | I/O | 上拉归属 SD 域，掉电时不倒灌 |
| SD D0 | 47 | 47 | I/O | 同上 |
| SD D1 | 48 | 48 | I/O | 同上 |
| SD D2 | 41 | 41 | I/O | 同上 |
| SD D3 | 40 | 40 | I/O | 同上 |
| SD 卡检测 | 无 | **IOX P05** | I | 机械检测触点，外部稳定默认电平；首版轮询，不直接深睡唤醒 |
| IOX RESET_N | 无 | **42** | O | 独立硬件复位，外部下拉；软件重启/hold 行为另验 |
| I²S BCLK | 12 | 12 | O | 共享 TX/RX 时钟，采样率由音频服务统一管理 |
| I²S WS | 7 | 7 | O | 同上 |
| MIC DATA | 11 | 11 | I | 掉电高阻与格式取决于最终麦克风 |
| SPEAKER DATA | 43 | 43 | O | GPIO43 不同时作为 UART0 TX |
| AUDIO ENABLE | 4 | 4 | O | 外部默认关断；控制音频供电，不由 I²C 扩展器代替 |
| AMP SHUTDOWN | 6 | 6 | O | 外部默认静音，供电切换前先静音 |
| 音量/翻页 + | 2 | **44** | I | 不要求独立深睡唤醒；GPIO2 让给 VBUS |
| 音量/翻页 − | 5 | 5 | I | 同上 |
| 正常电源键 | 旧 SW1 接 EN | **21** | I | RTC GPIO，短按唤醒/待机，长按请求保存后软关机 |
| USB 电源在位 | 用充电状态推断 | **2** | I | RTC GPIO；低有效VBUS_SENSE_N由AON侧上拉的开漏/掉电隔离检测提供；AON=0也不得倒灌；检测USB保护后支路；PTC断开可能撤掉指示，插拔/故障唤醒待测 |
| USB D− / D+ | 19 / 20 保留 | **19 / 20** | USB | 原生 USB，保留下载与调试；ESD/CC/阻抗按接口设计 |
| BOOT | 0 | **0** | I | 维修下载键；上电绑带默认正常启动 |
| RESET | EN | **EN** | I | 独立维护入口，不计入 GPIO 数量 |
| 旧电池 ADC | 1 | 不分配 | — | GPIO1 改作触摸；电量计承担测量，辅助 ADC 需另开变体分配 |
| 旧共轨 POWER EN | 21 | 不使用 | — | GPIO21 改作正常电源键；三个外设使能见扩展器 |
| 旧 CHRG / STDBY | 44 / 42 | 不直接沿用 | — | 电源在位与充电状态分离 |

GPIO0、1、2、5、21 位于 S3 的 RTC GPIO 范围内；正常电源键、VBUS 与触摸 INT 有直接深睡唤醒条件。软关机只使用电源键和VBUS，触摸唤醒属于阅读待机配置；实际电平、hold、竞争事件和误唤醒仍须实测。[ESP-IDF 睡眠与唤醒](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/system/sleep_modes.html)

## 候选 GPIO 扩展器

本轮选择 **TCA9539** 作为原理图候选：16-bit、带RESET，A0/A1接地时7-bit地址 **0x74**；MAX17048为0x36，GT911为0x5D或0x14。替代原TCA9534候选以容纳完整控制和复位；不能沿用其地址/寄存器。下表使用芯片实际端口名，第二组从 **P10** 开始，不叫P8。[TCA9539 原厂资料](https://www.ti.com/lit/ds/symlink/tca9539.pdf)

| 端口 | 候选功能 | 默认电气状态 | 说明 |
| --- | --- | --- | --- |
| IOX P00 | EPD_EN | 外部下拉，关 | 不用于面板 RESET/BUSY |
| IOX P01 | SD_EN | 外部下拉，关 | 关闭文件并卸载后才正常断电 |
| IOX P02 | TOUCH_EN | 外部下拉，关 | 配合独立信号隔离 |
| IOX P03 | PGOOD_N | 输入，上拉到AON | BQ24074有效输入状态，不等于USB协议授权 |
| IOX P04 | CHG_N | 输入，上拉到AON | 状态解码含暂停/超时，不直接等同电流 |
| IOX P05 | SD_CD_N | 输入，上拉到AON | 机械卡检测，释放原GPIO42 |
| IOX P06 | USB_EN1 | 外部下拉 | BQ24074限流控制位1 |
| IOX P07 | CHARGE_ALLOW | 外部下拉，禁充 | 通过MOS拉低CE_N，高才允许充电；CE_N在SYS侧可靠上拉 |
| IOX P10 | TOUCH_IO_EN | 10k下拉，隔离 | TMUX1511四路SEL，控制SDA/SCL/RESET/INT |
| IOX P11 | USB_EN2 | 外部下拉 | BQ24074限流控制位2；改档经00，正常切档不反复翻转CE |
| IOX P12 | FUEL_ALERT（可选） | 输入，上拉到AON | 首版可轮询，不宣称能直接唤醒MCU |
| IOX P13 | SD_IO_EN | 10k下拉，信号隔离 | 独立控制SD总线开关；先电源稳定后接通，先隔离后断轨 |
| IOX P14–P17 | 保留 | 输入，定义电平 | 后续RTC/检测扩展；不驱动负载 |

扩展器由 `3V3_AON` 供电；它不控制自身供电、主稳压器使能、正常电源键或音频实时信号。端口不能驱动负载本身，只控制负载开关。

GPIO42独立控制RESET_N，不能仅把它接ESP32 EN后声称覆盖所有看门狗复位。TCA9539复位为全输入、输出锁存全1；先写安全锁存再设方向，不能反过来。启动主动复位并重建状态；正常I²C故障先处理存储等活动，不能直接RESET切掉正在写入的SD。无USB软关机可保持RESET低；充电深睡需保持高、保留IOX控制并验证hold。详见[时序契约](power-design-spec.md)。

GT911的SDA/SCL/RESET/INT通过TMUX1511四路双向开关隔离，开关供电在TOUCH域；SD六根总线采用另外两颗TMUX1511，供电在SD域，SD_IO_EN来自IOX P13。两者均在掉电前先断开信号。AON上拉、TOUCH侧上拉、总线电容与复位选址一并核算。屏幕五路输出经EPD域缓冲，BUSY回传经AON缓冲；I²S四路输出经MIC域缓冲，麦克风回传经AON缓冲。器件掉电规格不能替代供电过渡和实际漏电测试。

## 可选 RTC 与调试接口

低功耗外部RTC首版允许不装配。只读时钟可共享I²C；若需要专用深睡唤醒，可另建变体：音量−移至IOX P14，释放RTC GPIO5接RTC INT。GPIO2已被VBUS占用，不能再沿用旧候选RTC分配；不能将两路输出直接短接。

GPIO43/44已用于音频和音量+，不能同时声明完整UART0保留。原生USB是默认维护通道；ROM UART可通过可断开的0 Ω连接/测试焊盘在断开外设后使用。GPIO39～42用于SD/IOX复位，不默认保留外部JTAG；调试优先USB Serial/JTAG。

GPIO3/45/46 保留，不因为表中“未使用”就加外部上拉或接外设。GPIO35/36/37 为 N16R8 内存专用。GPIO22～34 不作为该模组可分配引脚使用。

## 定稿检查

1. 把 GPIO 编号转换为 N16R8 实际模组焊盘并检查封装。
2. 对每个输入输出检查上电、下载、复位、外设关断和深睡时的电平。
3. 对全部 I²C 器件核对地址冲突、上拉电源和掉电隔离。
4. 核对 SDMMC 4-bit、USB、EPD FPC 与 I²S 信号完整性，再确定总线速率。
5. 在板级 profile 中区分现用核心板、归档 PCB、新板候选与可选 RTC 变体；未知 profile 不允许驱动 GPIO。
