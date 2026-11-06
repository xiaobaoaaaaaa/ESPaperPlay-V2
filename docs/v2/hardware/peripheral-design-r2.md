# 外设电路设计 r2

更新：2026-11-02。对应[KiCad开发验证板](../../../hardware/devboard-r0/README.md)中的EPD_DISPLAY、STORAGE_SD、AUDIO页。主要功能电路已落图，器件仍是设计候选；封装、采购和实物验证没有冻结。现用核心板固件保持原样，新板必须使用独立board profile。

## 电子纸

J601按GDEY075T7-T01的24个信号触点定义：15/16同接EPD_3V3，18为内部稳压节点，仅接C606，不能与3.3 V短接；1/4/19 NC，未用外温接口6/7开放，8接地选择4线SPI。固定焊脚不计入24针。最终FPC料号、接触面、插入方向和实际样品仍需核对。[屏幕资料](panel-reference.md)

升压遵循原厂p38：L601接EPD_3V3至SW，Q601源极经0.47Ω采样电阻到地；C602接FLY与SW而非地。D601阴极FLY/阳极VGL，D602阴极GND/阳极FLY，D603阴极VGH/阳极SW。Q601选Vishay Si1308EDL-T1-GE3候选，不能按旧工程同名器件默认等同厂商；D601–603选onsemi MBR0530候选，其原厂430mV指标的条件是500mA、25°C。具体生命周期仍需采购确认。

L601暂为10µH、≥1A设计目标，封装/料号、饱和与RMS电流未冻结；屏厂图与表的电流描述不一致，不能直接当成完整电感选型。高压电容保留原厂名义容值，50 V是初始降额候选，须核偏压后的有效容量。R602脉冲/热额定与Kelvin走线、高压纹波和刷新波形均需验证。

五路MCU写信号经EPD供电的SN74LVC541A，再经33Ω候选串阻到面板；CS默认高，RESET/CLK/MOSI/DC默认低。BUSY经AON供电的SN74LVC1G125返回，面板侧下拉使断电/拔屏读到LOW，表示忙或无效，不能视作就绪。当前单向SDI缓冲不支持寄存器/OTP回读。掉电保护规格不等于整个供电坡度期间都保证高阻，仍需保持安全信号、完成刷新并休眠后再关轨。

## microSD

J701为Hirose DM3AT-SF-PEJM5候选。8个卡触点为DAT2/DAT3/CMD/VDD/CLK/GND/DAT0/DAT1；机械检测与卡的DAT3/CD不是同一信号。Hirose把检测触点称为A/B，KiCad将这个无极性触点对编号9/10：无卡开放、插卡闭合。现有库封装是候选，A/B物理位置、四个SH固定脚、弹出空间和样品贴合仍是机械审查项。

六根总线通过U701/U706两颗TMUX1511，供电取R405后的SD_3V3。四个加两个SEL接独立SD_IO_EN；另外两路SEL接地、S/D明确NC。IOX P01仍控制供电，**P13新增为SD_IO_EN，不增加ESP32 GPIO**。五个10k上拉全部在卡侧、接SD_3V3，即使1-bit运行也保留DAT1–3上拉。CLK弱下拉，串阻起点CLK=22Ω、CMD/DAT=0Ω。[乐鑫上拉要求](https://docs.espressif.com/projects/esp-idf/en/latest/esp32s3/api-reference/peripherals/sd_pullup_requirements.html)

开机顺序为信号隔离→开SD电源→等待经台架确认的稳定时间→接通信号→初始化。关机为禁止新请求→排空/关闭/卸载→停止SDMMC→隔离→关电源；卸载超时不直接断轨。当前没有独立SD电压ADC/PGOOD，不能用“已发出使能”假定电压有效。初始400kHz初始化、4-bit 20MHz运行是验证起点，不保证吞吐；不支持1.8 V UHS。

R708=100Ω、C704=10nF配原R216=100k形成约1ms检测滤波，仍需软件去抖。四颗TPD2E2U06覆盖总线、检测和VDD，采用对地保护而非钳到另一供电轨；接口布局和实板ESD仍待验收。卡座0.5A额定还要与最终卡的峰值电流核对。

原8位总线开关候选因信号耐压依赖VCC、在供电塌陷时可能超绝对额定而撤销。TMUX1511避免这一绝对额定限制，但其正常工作范围仍随供电变化：≥1.5 V时信号上限min(2×VDD,5.5 V)，低于1.5 V时为3.6 V；窄过渡区、意外掉电和残压波形仍需验证，不能宣称全程工作有效。[TI TMUX1511](https://www.ti.com/lit/ds/symlink/tmux1511.pdf)

## 音频

保持MIC_3V3与AMP_SYS两个域、GPIO4共同开关、GPIO6独立静音。MAX98357AETE+T使用16脚TQFN加EP17接地，GAIN_SLOT接AMP_SYS为6dB候选；SD_MODE经2k串阻、100k下拉，驱动高选择左声道。播放内容须软件混音/重采样到左槽，不能把接法解释成芯片自动左右平均。8Ω扬声器仍是候选；两线均为BTL输出，不接地，无5 V升压或3 W保证。[ADI MAX98357A](https://www.analog.com/media/en/technical-documentation/data-sheets/MAX98357A-MAX98357B.pdf)

四个MCU输出经MIC域供电的**Nexperia 74LVC125APW,118**：BCLK、WS、播放DATA、静音控制。必须锁定厂家与有Ioff规格的版本，不能仅凭74LVC125A名称换成另一厂家。U805使用带Ioff的SN74LVC1G14施密特反相器，将AUDIO_EN转换为四路/OE，避免大电阻拉高CMOS控制脚产生慢沿。麦克风数据经AON供电SN74LVC1G125返回。输出侧有默认下拉；SD_MODE的2k只是限流，不代表拆断AMP电源后可任意驱动而完全无注入。

麦克风候选为**PUI DMM-4026-B-I2S-R**，官网公开目录仍列售，但尚未获得明确生命周期/供货承诺。其7脚与原ICS-43434不同：LR和CONFIG接地，3为VDD、4为GND、5/6为WS/SCK、7为数据并配100k下拉；底部声孔与专用封装待建立。不得套用旧6脚封装。[PUI原厂资料](https://api.puiaudio.com/filename/DMM-4026-B-I2S-R.pdf)

首测采用48kHz、双32-bit I²S槽、64fs=3.072MHz，录音取左槽24-bit数据，其中18-bit有效精度。32/44.1/48kHz为待验证交集；32kHz的BCLK恰在麦克风正常时钟下界。旧16kHz配置不直接适用于此候选。上电后先保持静音、稳定电源并建立零数据时钟，再丢弃麦克风稳定阶段数据，最后解除静音；手册20ms是参考起点，不是所有状态的实测保证。关闭时先静音，不允许只撤掉LRCLK却继续运行BCLK。MIC/AMP衰减不同，拆R411/R414和异常掉电的注入/爆音必须另测。

## 默认电平与功耗

多路控制输入不能只看典型漏电或内置典型弱下拉。r2将四个外部下拉修正为10k：

| 电阻 | 网络 | 最坏值核算依据 | 输出高时名义电流 |
| --- | --- | --- | --- |
| R215 | TOUCH_IO_EN | 4×2µA SEL漏电+1µA IOX，约0.09 V | 330µA |
| R223 | SD_IO_EN | 6×2µA SEL漏电+1µA IOX，约0.13 V | 330µA |
| R306 | AMP_SHUTDOWN | Nexperia输入漏电125°C上界20µA，约0.20 V；不等于整板工作温度保证 | 330µA |
| R416 | AUDIO_EN | 1G14保守10µA+两TPS22918各0.1µA，约0.102 V；另留MCU/板漏电裕量 | 330µA |

这些电流属于相应使能为高的活动状态，不能直接加入使能低的软关机预算。新增AON回传缓冲的静态电流、各未供电I/O泄漏、有效上拉和时钟动态功耗仍要逐项计入实际测量。P01≤200µA继续是目标，尚未上板验证。[TI TMUX1511](https://www.ti.com/lit/ds/symlink/tmux1511.pdf)、[TI TPS22918](https://www.ti.com/lit/ds/symlink/tps22918.pdf)、[TI SN74LVC1G14](https://www.ti.com/lit/ds/symlink/sn74lvc1g14.pdf)

J301–303在r2默认DNP，保留MCU侧高阻探测位置；不能再接另一块外设模块或注入电源，否则会绕过板上隔离或造成输出竞争。各域外部注电还须处理原有QOD泄放和跨域路径。

下一阶段先核实BOM与封装：TPS63802 DLA、麦克风声孔/焊盘、EPD/触摸连接器接触面、USB插座、扬声器接口、电感/采样电阻/MLCC额定及候选生命周期。完成这些后才进入布局；电池容量/保护/NTC温区未确定前，R108充电装配连接仍为DNP。
