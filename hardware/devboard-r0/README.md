# ESPaperPlay 开发验证板：PCB 布局 r7

更新日期：2026-11-06。**已建立160×110mm四层开发板，完成236个电气器件及4个机械孔的布局。** 十一页原理图仍为r6模块化绘图，电气设计保持r5的约0.7A充电、独立ITERM及硬件温窗。236个器件位置（6个DNP）、181条网络，236个有封装候选、234个有MPN。目录沿用 `devboard-r0`。本轮仅器件布局，尚未布线、铺铜、上电或冻结制造BOM。

当前工作见[PCB布局r7](../../docs/v2/hardware/pcb-layout-r7.md)、[原生PCB](ESPaperPlay_Devboard.kicad_pcb)和[布局检查](review-r7/)。屏幕、电池、扬声器外接，四个M3安装孔为机械项，不改变电气BOM。板层与制造规则是开发候选，USB/SD阻抗线宽须在实际工厂叠层确定后计算。

原理图见[模块化绘图r6](../../docs/v2/hardware/schematic-layout-r6.md)。电气依据仍见[充电设计r5](../../docs/v2/hardware/charging-design-r5.md)和[逐位号BOM](review-r5/bom-review.json)。温窗按用户授权的Honeywell 175-103LAE-301 Rev.B曲线假设设计，尚未证实电池实际NTC相同；R108继续DNP。此前[保守电池预算与纯延长连接](../../docs/v2/hardware/design-assumptions-2026-11-04.md)仍适用。

[r4审查报告](../../docs/v2/hardware/closure-review-r4.md)、[r4工作簿](../../outputs/espaperplay-bom-r4/ESPaperPlay_BOM_Review_r4.xlsx)为历史，未纳入r5的新值。全套绘图版本为r6；候选器件属性沿用r4/r5审查记录。当前结果以本页和verification.json为准。

## 打开与查看

打开 [ESPaperPlay_Devboard.kicad_pro](ESPaperPlay_Devboard.kicad_pro)，进入PCB编辑器查看当前布局；原理图编辑器中双击根页功能框。也可直接打开[PCB](ESPaperPlay_Devboard.kicad_pcb)或[根原理图](ESPaperPlay_Devboard.kicad_sch)。

| 页 | 内容 |
| --- | --- |
| 1 | 工程索引、装配默认状态与当前边界 |
| 2 [POWER_INPUT_CHARGER](POWER_INPUT_CHARGER.kicad_sch) | BQ24074、保护后电池/NTC、默认禁充、输入档位、USB支路检测 |
| 3 [POWER_3V3_CONTROL](POWER_3V3_CONTROL.kicad_sch) | TPS63802、反馈与测流、TCA9539、MAX17048 |
| 4 [MCU_CORE](MCU_CORE.kicad_sch) | N16R8实际焊盘、去耦、EN/BOOT、正常电源/翻页键、功能调试头 |
| 5 [USB_INPUT](USB_INPUT.kicad_sch) | USB-C设备端、独立CC下拉、数据/CC保护、PTC/TVS、单跳帽选源 |
| 6 [POWER_DOMAINS](POWER_DOMAINS.kicad_sch) | EPD、SD、TOUCH、MIC、AMP五路TPS22918、测流断点与泄放 |
| 7 [TOUCH_ISOLATION](TOUCH_ISOLATION.kicad_sch) | TMUX1511四路隔离、GT911功能接口、上电/掉电和注电约束 |
| 8 [EPD_DISPLAY](EPD_DISPLAY.kicad_sch) | 原厂升压拓扑、24针FPC、五路写缓冲与BUSY返回 |
| 9 [STORAGE_SD](STORAGE_SD.kicad_sch) | microSD插座、六线隔离、卡侧上拉、检测和ESD保护 |
| 10 [AUDIO](AUDIO.kicad_sch) | I²S缓冲、施密特输出使能、MAX98357A、PUI麦克风候选 |
| 11 [CHARGE_TEMP](CHARGE_TEMP.kicad_sch) | TLV1822冷热温窗、正反馈滞回、真实NTC输入、TS暂停充电 |

[本地十一页PDF预览](output/pdf/ESPaperPlay_Devboard_Modules_r6.pdf)由当前原生工程导出，未纳入Git，可按下方命令重建。旧r0–r5 PDF为历史。

已用KiCad **10.0.7**解析、导出并检查。初始文件使用兼容格式，首次用编辑器保存时可能提示升级格式。**原生文件是后续手工编辑的工作源，不应运行生成器覆盖。** `tools/generate_power_schematic.py`保留最初r0两页草稿；其余生成脚本只生成各自分组草稿，均不是完整r2工程的再生成命令。实验输出必须放在空的临时目录。

## 电路与默认状态

| 项目 | 实际实现 / 初始状态 |
| --- | --- |
| 选源 | J502仅装一个跳帽：1–2 USB、2–3台架，拔除则断开充电器输入。断电后换档，不能短接两路源；不是自动电源切换电路 |
| USB输入 | J501→F501→USB_5V_PROTECTED→J502；D501从保护后节点到地。CC1/CC2各自5.1k下拉；无PD、Host、CC电流识别 |
| 台架输入 | 原J101接BENCH_5V，仅使用已知稳压、限流5 V电源。该支路不经过USB的PTC/TVS，不保证反接或错误电压保护 |
| USB数据 | D−=GPIO19/模组焊盘13，D+=GPIO20/焊盘14；两组正反插接点合并，22Ω串阻靠MCU；C501/C502为真实DNP调谐预留 |
| 电池 | 用户选定ZON.CELL 755570、4000mAh、1S三线10kΩ NTC电池；J102接保护后正负端，J103接NTC，主板侧用Phoenix1751248开发端子。商业线束极性/线径/NTC阻温仍待核 |
| 系统测流 | R102测整个BAT支路；R101分开SYS_RAW/SYS；R203分开3V3_REG/3V3_AON；8个电源测流连接采用Bourns CRF0805金属低阻跳线候选，整板电流和温升仍待核 |
| 充电禁止 | R108 `CHG_ARM` **DNP**；Q101栅极100k下拉。R106从芯片侧SYS_RAW上拉CE_N，拔R101不会撤掉禁充上拉 |
| 输入档位 | EN1/EN2外部下拉，默认00=100 mA；不能因VBUS有电或有CC下拉就升档。整口还要计入绕过BQ限流的检测/保护电流 |
| 充电参数 | R104/R113=1.27k，约0.701A/30mA；R103=1.62k、R105=68k保留。轻载、供电能力确认后适用；计时仍可能先于满充截止，不自动续时 |
| 温控 | TLV1822直接拉低TS暂停；标称约14.8–40.1°C，330k正反馈形成滞回。真实NTC仍接J103；10k TS偏置不取消温控；模型/实物边界见r5报告 |
| 主电源 | J202单跳帽1–2运行、2–3关闭；开路由R205默认关闭。关掉主稳压后不能靠GPIO21普通按键重新供电 |
| 维护恢复 | J105默认开放。只有合格电池/NTC、主电源及音频关闭、已知来源时才强制CE低；NTC/ISET/TMR仍有效 |
| 反馈 | R201=51.1k、R202=9.10k，均0.1%/25ppm；计算PWM误差预算3.249–3.367V，PFM/瞬态仍待测。分压比保持，较r3增加约49.34µA。C202、上臂和VOUT均在R203前 |
| 扩展器 | TCA9539地址0x74，GPIO42独立控制RESET；P13为SD_IO_EN且10k下拉；P14–P17各100k下拉并保持输入；先写安全锁存再设输出方向 |
| 电量计 | MAX17048 VDD/CELL接BAT_PROT；R217/R218只是调试断开点，不能证明电池断开时Ioff合格或可靠判定电池存在 |
| USB检测 | R221取USB_5V_PROTECTED，即PTC之后、选源之前；Q201开漏拉低GPIO2表示USB支路有电。PTC跳脱可能撤掉指示，不等于检测物理插头；PGOOD表示选中输入有效 |
| 主控 | N16R8，GPIO35/36/37为内存保留，3/45/46不接外设；USB为默认调试通道，43/44已分配音频/按键，不能再常接UART0 |
| 用户按键 | GPIO21正常电源键，GPIO44/5翻页或音量；EN/BOOT是独立维护键，软件去抖/唤醒仍待固件实现和实测 |
| 音频默认 | GPIO4经R416=10k下拉使MIC与AMP两路默认关；GPIO6经R306=10k下拉默认静音。AMP取SYS，不使用5 V升压；录音时MIC和AMP供电会一起开启 |

ERC按逻辑连接工作，**不模拟DNP、跳帽状态、电源能力、时序、保护动作或温度**。R108、C501/C502及J301–303的DNP真实存在于KiCad属性和PDF中。原理图的PWR_FLAG只描述正常RUN且测流连接已装配状态，不是保护器件。

J201/J205含AON电源；外部3.3 V注入前断R203，不能并联核心板稳压器。J205依次为AON/GND/SDA/SCL/IOX_RESET/VBUS；J206为控制信号接口。J301/302/303在r2默认DNP，保留MCU侧高阻探测位置。板上EPD/SD/音频负载已连接，不得再接外设模块或通过这些接口注入电源。

## 分域测量与触摸隔离

| 域 | 输入 / 使能 | 输出 | 测流断点 | QOD泄放电阻 |
| --- | --- | --- | --- | --- |
| EPD | AON / IOX P00 | EPD_3V3 | R402 | R401 |
| SD | AON / IOX P01 | SD_3V3 | R405 | R404 |
| TOUCH | AON / IOX P02 | TOUCH_3V3 | R408 | R407 |
| MIC | AON / GPIO4 | MIC_3V3 | R411 | R410 |
| AMP | SYS / GPIO4 | AMP_SYS | R414 | R413 |

五路CT暂定4.7nF、QOD外阻330Ω，输入/输出电容仍需随实际负载校核。测流连接只计下游负载，不含上游开关自身静态电流。**QOD接在测流之后：仅拆0Ω并不完全隔离输出轨。** 外部注电须同时断开QOD并处理跨域信号；上游无电时也不能假定快速泄放有效。低压轨关断后1 s内低于0.2 V只是测试目标，不包含墨水屏高压节点。TPS22918不提供精确限流或反向电流阻断。

TMUX1511及触摸侧上拉/去耦全部在R408后；四个SEL均接TOUCH_IO_EN，由IOX P10控制，R215=10k默认拉低。隔离SDA、SCL、RESET、双向INT，J406六针功能顺序为GND/VCC/RESET/INT/SDA/SCL；**LAILAN 6针条件封装已指定，SH固定焊盘接GND**。保留现有通用0.5mm FP6纯延长链，针序、接触面和尺寸按原厂图纸配置，实物检查归入常规装配验收。AON侧4.7k与触摸侧10k接通时约3.20k，须加上屏幕自带上拉/电容再核算。掉电先隔离再关轨；上电执行完整GT911选址/复位流程。

## 新增外设与时序

完整连接说明见[外设电路设计r2](../../docs/v2/hardware/peripheral-design-r2.md)。

- **EPD**：原厂p38升压，J601第18脚仅接内部稳压电容；五路写信号经EPD供电SN74LVC541A，BUSY经AON供电SN74LVC1G125返回。断电时BUSY低表示忙/无效。当前不支持SDI读回。
- **SD**：两个TMUX1511隔离六根总线，P01开供电、P13独立接通信号；CMD/DAT0–3均有卡侧10k上拉。上电先等供电稳定再接通；关闭先卸载、停总线、隔离再断电。400kHz初始化、4-bit 20MHz为验证目标。
- **音频**：明确采用有Ioff规格的Nexperia 74LVC125APW，不能直接换成TI同名系列；SN74LVC1G14施密特反相器驱动四个/OE。MAX98357A接左声道、6dB候选增益，BTL两根扬声器线均不接地。
- **麦克风**：PUI DMM-4026-B-I2S-R为3.3 V、7焊盘候选，生命周期/采购仍待确认。首测48kHz、双32-bit槽、64fs；旧16kHz配置不适用，现有固件没有改动。已建立镜像脚序、铜环和0.60mm NPTH声孔候选；钢网、声道与贴装仍须验证。
- **复位默认**：R215/R223/R306/R416均改为10k，按多输入最坏漏电核算；使能高时每个约330µA，属于活动电流。新增两颗AON返回缓冲的静态电流须纳入睡眠实测。

这些缓冲/模拟开关的掉电规格不能替代电源坡度、残压、注入电流和热插拔验证。J601/J406保留现有FP24/FP6纯延长件，按文档对应针号连接，不另设转接功能或信息门槛。SD旧版原厂图核实了pad9=B、pad10=A，仍须实物检查推入/弹出空间。扬声器已选3525腔体8Ω2W，初测以≤0.5W为输出限制目标，未承诺低电量时达到2W。

## 符号、封装与资料

本地[符号库](ESPaperPlay.kicad_sym)含15种符号（r5新增TLV1822D），覆盖电源、扩展器、模拟开关、显示接口与音频；r4新增GT911带SH符号并给24针EPD符号补SH。[sym-lib-table](sym-lib-table)通过相对路径引用。其他符号嵌入标准库副本。MAX98357A的EP17按原厂定义作为接地散热焊盘；两个1G125符号仅绘图几何不同。

- [本地封装库](ESPaperPlay.pretty)含20种候选（包含r5的TI SOIC-8），经[fp-lib-table](fp-lib-table)相对引用。新增两款FPC、Phoenix开发端子、PUI声孔、Vishay SC70原厂焊盘与WFM2010采样电阻封装。TPS63802的DLA0010A为非对称10焊盘，8脚宽PGND，没有第11脚中央EP。
- TCA9539用PW24脚序；MAX17048用G+ TDFN8加EP9；TPS22918为DBV6，TMUX1511为PW14。所填封装为候选，PCB前还要核实实物/机械图。
- USB插座采用GCT USB4105-GF-A、按键采用Omron B3F-1002-G候选。GF-A焊脚长0.95mm，1.6mm板的焊接浸润/固定强度待装配确认。R602选WFMB2010R4700FEA，其2W额定以端子≤110°C为条件；限定电阻自身验证包络，不冒充整套升压能力。
- D601–603已改为单独核对过的onsemi MBR0530T1G，不能沿用旧MBR0530的数据手册。16个100nF位置选TDK C1608X7R1H104K080AA候选；6个4.7µF/50V高压电容改用1206候选，仍需DC偏压有效容量证据。
- F501由r3的110改为MF-MSMF200/16X-2，同Style2焊盘、最大高度1.60mm。50°C/60°C保持电流1.68A/1.48A，高于加入外阻温漂及5mA支路分配后的约1.085A正常预算；不等于短路/TVS配合已验证。默认100mA不变，高档仍须合格USB来源。
- 30个原空白MLCC位置已选准确候选，C102/C103/C201由0805改1206；CT改明确C0G±5%。C102/C103/C201/C202工作偏压下的验收门槛已量化，但有效容量保证证据尚缺；高压C602必须检查两端差分应力，C610 VCOM也属于高压审核。
- Q101/Q201为AOS AO3400A NMOS，1G/2S/3D。D501为AOS单向SMAJ6.0A，KiCad焊盘1是阴极接USB保护后电压，2是阳极接地。
- [电源原厂资料与哈希](../reference/power/README.md)、[主控/USB原厂资料与哈希](../reference/mcu-usb/README.md)、[屏幕资料](../reference/good-display/README.md)、[新增外设资料与哈希](../reference/peripherals/README.md)。标准KiCad库采用CC-BY-SA 4.0及电子设计例外，见本机`/usr/share/licenses/kicad/LICENSE-symbols.md`。
- [r3原厂资料索引](../reference/bom-r3/README.md)含77个URL记录、12份新下载PDF及20份原有PDF引用；在线页面不冒充已归档原始文件。
- [r4资料索引](../reference/closure-r4/README.md)含32条来源记录，其中18条有实际文件校验、8份新文件；[用户截图资料](../reference/user-selected-r4/selected-components.json)记录电池/扬声器和保留延长链的决定。

## 验证与复现

- 十一页原生解析、PDF/XML导出通过；ERC 0错误、0警告、0排除。
- 原检查链668项关键连接通过；r5独立检查精确覆盖全部774个引脚连接、允许变更、旧UUID和DNP。见[连接差异契约](review-r5/allowed-r4-r5-delta.json)。
- 全部236个封装位置、38种封装经过原生加载和引脚编号匹配；新增U901封装按原厂D0008A示例铜图核对。
- r6全部十张功能页按有线模块重排；十一页PDF逐页渲染目检。与r5相比所有236个组件、774个pin连接及NC、UUID、候选属性保持；符号定义未改。见[绘图等价检查](review-r6/drawing-equivalence.json)。r5充电与温窗计算继续适用。
- r7新增PCB布局与原生DRC，236个电气元件、774逻辑引脚/804实际编号焊盘与原理图一致，4个机械孔另计。未连接项保留；U301板外天线丝印移到Dwgs.User产生一条已说明的库差异警告。详见[布局说明](../../docs/v2/hardware/pcb-layout-r7.md)。
- 尚未布线/铺铜/上电实测；NTC实际曲线、动态/热/USB/功耗和外设功能在样机验收。ERC不模拟DNP、跳帽、模拟阈值或热。

R221=10k/R222=47k，在USB选通且只计现有约4.8µF时名义RC约0.27 s；BENCH选源、电容容差/寄生、PTC状态会改变响应，不能把计算当实测插拔延迟。USB H05测试覆盖两种选源及保护动作。验证快照和源文件哈希见[verification.json](verification.json)。

从仓库根目录依次运行：

```sh
mkdir -p build/devboard-r6
kicad-cli sch erc --format json --severity-all --exit-code-violations \
  -o build/devboard-r6/erc.json hardware/devboard-r0/ESPaperPlay_Devboard.kicad_sch
kicad-cli sch export netlist --format kicadxml -o build/devboard-r6/peripheral.net.xml \
  hardware/devboard-r0/ESPaperPlay_Devboard.kicad_sch
python3 hardware/devboard-r0/tools/check_peripheral_netlist.py \
  build/devboard-r6/peripheral.net.xml --erc build/devboard-r6/erc.json
python3 hardware/devboard-r0/tools/check_charging_r5.py \
  build/devboard-r6/peripheral.net.xml --output build/devboard-r6/bom-footprint-check.json
python3 hardware/devboard-r0/tools/check_drawing_r6.py \
  build/devboard-r6/peripheral.net.xml --output build/devboard-r6/drawing-equivalence.json
python3 hardware/devboard-r0/review-r5/power/calculate_bounds.py
python3 hardware/devboard-r0/review-r5/temperature/analyze_temperature_window.py
mkdir -p hardware/devboard-r0/output/pdf
kicad-cli sch export pdf -o hardware/devboard-r0/output/pdf/ESPaperPlay_Devboard_Modules_r6.pdf \
  hardware/devboard-r0/ESPaperPlay_Devboard.kicad_sch
```

PCB布局复核（需要KiCad 10 CLI与Python pcbnew）：

```sh
mkdir -p build/devboard-r7
python3 hardware/devboard-r0/tools/check_pcb_layout_r7.py \
  --output build/devboard-r7/independent-board-check.json
kicad-cli pcb drc --format json --severity-all --schematic-parity \
  -o build/devboard-r7/drc.json hardware/devboard-r0/ESPaperPlay_Devboard.kicad_pcb
```

当前DRC为499个未连接项、1个U301绘图差异警告、0个原理图一致性问题；这不是布线完成的DRC通过结果。[二维布局预览](output/pcb/ESPaperPlay_Placement_r7.png)和[装配图](output/pcb/ESPaperPlay_Assembly_r7.svg)供查看，后续编辑以原生PCB为准。

[r4逐引脚基线](review-r5/electrical-baseline-r4.json)和差异契约可在其他机器复核。原生工程是编辑源，旧生成脚本不能覆盖它。r4原BOM检查器/报告保留为历史，不能拿r4固定器件数量直接验证r5。

下一步从r7原生PCB继续关键回路、USB/SD和电源地布线，核对真实叠层及MLCC偏压数据。正式下单前完成布线、完整DRC和制造检查，实物功能/热试验在样机阶段进行。电池容量已定4000mAh，电流与温窗已按假设落图，NTC实物、CV/保护和热仍需样机验证。
