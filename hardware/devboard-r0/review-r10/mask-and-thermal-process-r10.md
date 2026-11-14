# r10 阻焊与热孔工程选择

2026-11-14。基于 r8 源板（SHA-256 `1a4556d866cc1352a2c45b674c94d2f233edf28c3e003bd96c8f6caf1e630681`）进行只读分析；本子任务未改源板，也未接触生产服务。`mask-options.json`、`thermal-hole-process-spec.json` 和 `thermal-via-fill-spec.csv` 为具体工程输入，不能当作厂商订单确认。

## 本轮选择

1. **保留现有阻焊扩展，不做全板扩大。** 全局0与已有局部偏置保持；移开贴近开窗的普通过孔来取得实际几何余量。
2. **11个IC焊区内孔明确指定树脂填孔、平整化、电镀封帽，表面仍为可焊ENIG。** 保留焊盘/孔铜/地平面/焊膏，避免以取消热孔或涂阻焊覆盖热焊盘来迁就普通工艺。盖帽铜厚设计要求≥10µm。
3. U301中心EPAD沿用不印膏，12个模块热孔不新增强制填孔要求；其余538个native过孔按供图盖油。必须保持95个普通组件孔和7个NPTH开通，尤其Ø0.60mm声孔。
4. 11孔是设计上需要平整可焊封口的最小集合，不承诺板厂能够仅处理或仅收费11孔。若其订单工艺要求扩大到全板过孔，可另审核实际处理范围；不能按“小孔全部填”误封组件孔。

## 纠正r9对零扩展的表述

嘉立创[当前国内能力页](https://www.jlc.com/portal/vtechnology.html)说明，LDI升级后新板可按焊盘与阻焊开窗1:1加工；[阻焊设计说明](https://www.jlc.com/portal/server_guide_34402.html)还说明过大开窗可能按焊盘缩回。因此“零扩展没有额外几何余量”是描述，**不能据此单独判定制造不合格，或作为全板改+.025mm的理由**。r9的近孔0.00498mm问题不因此消失：它是孔口与相邻大开窗之间的极小空间，而非普通焊盘必须有正扩展的问题。

当前局部非零扩展完整清单如下，不能再写“只有U101/U201”：

- +0.05mm：U101、U201、Q101、Q201、L201、F501，以及R101/R102/R203/R402/R405/R408/R411/R414，共53个编号SMD焊盘对象。
- +0.025mm：U803，共7个。
- 其余637个编号SMD焊盘对象为0；总计697个。

U101/U201的TI封装图偏好NSMD；已有+.05mm处于其示例所列单边上限内。U803已有+.025mm。为保持这些已审查图形，制造说明应明确保留指定局部开窗，生产稿不能未经复核一律缩为1:1，也不能一律扩大。ADI通用QFN指南偏好NSMD，说明可以针对U203/U802评估局部外扩，**不是**当前JLC的1:1工艺能力不存在的证据；没有必要在本轮同时改这两个封装、钢网与近孔几何。

## 开窗扩大反事实计算

使用只读原生焊盘多边形和有效局部扩展，检查全板不同网络SMD焊盘开窗。下表是假设方案比较，没有导出为最终Gerber；不含实际对位/蚀刻/钻偏模拟。

| 方案 | 最窄异网开窗间隙 | <0.10mm对数 | <0.13mm对数 |
|---|---:|---:|---:|
| 保留现有 | 0.150000mm，U201.1/2 | 0 | 0 |
| 仅零扩展位置变+.025mm | 0.126777mm，U802角部 | 0 | 4 |
| 仅零扩展位置变+.050mm | 0.076777mm，U802角部 | 4 | 44 |

嘉立创1oz普通彩色油墨设计桥下限为0.10mm，黑/白为0.13mm；仍优先绿色。当前最窄关键桥0.15mm有设计空间，统一+.05会破坏它。不能将这些焊盘间隙当作实际阻焊对位公差。

**孔边至实际mask开口≥0.20mm是本项目布局目标。** 本次公开页面未提供可用于闭合最坏情况的数值型阻焊对位公差，不能把0.20mm声明成工厂保证。国际能力页的塞油条件还要求与其他开窗保持≥0.35mm；因此0.20mm并不证明可采用油墨塞孔。此处普通移孔采用名义盖油，11个焊区孔采用填孔盖帽，不能混写。

## 四个IC的保留依据

| 部位 | 孔数 | 原厂依据与选择 |
|---|---:|---|
| U101 BQ24074 pad17 | 4 | 热焊盘同时承担主地连接，必须焊接；TI封装图对膏口下孔提出填/塞/盖等处理。保留热路径，选平整填孔盖帽满足本次自装需求。 |
| U201 TPS63802 pad8 | 2 | pad8是较宽的PGND端子，不是额外中心EP。保留0.10mm钢网示例的分窗和地连接；现有孔填平，避免从这两个膏口吸锡。 |
| U203 MAX17048 pad9 | 1 | TDFN EP按数据手册接地；低功耗不意味着可以套用模块EPAD不焊。保留EPAD焊接及现有分窗。 |
| U802 MAX98357A pad17 | 4 | EP内部未接电路，但原厂要求连实心地平面散热；不删除EPAD/热孔，保留约66%分窗膏口。 |

这些选择保留既有热路径，不宣称已通过温升或空洞实测。树脂本身不作为导电介质，导电/导热路径仍依赖已保留的孔铜和盖帽。铜浆填充是可选更高导热工艺，本次没有必须升级为铜浆的证据。

精确11孔的UUID/绝对KiCad坐标/孔径在 `thermal-via-fill-spec.csv`；Y向下，与Gerber的Y符号不同。加工输入应写明填平后的可焊表面、盖帽铜≥10µm、保留所有网表/铜连接和开窗；不接受用普通阻焊油墨遮住热焊盘代替。所选厂商还需给出实际凹陷/凸起标准以适配0.10mm钢网；通用“POFV”选项名称不能代替表面平整度约定。国内与国际公开盖帽质量条件不同，本设计采用国内≥10µm铜盖帽要求，而不混称全球统一规格。

## 可复制的制造备注草稿

> 保持4层、1.6mm、外铜1oz/内铜0.5oz、绿油、ENIG和已指定层叠。11个IC焊区内Ø0.20mm孔按附UUID/坐标表树脂填充、平整化并电镀封帽，盖帽铜厚至少10µm、表面可焊；不得删孔铜、删热焊盘或用阻焊替代。其余过孔按供图盖油；若填孔工艺实际需覆盖更多过孔，生产稿列明范围后复核。普通组件孔95个及NPTH7个必须开通。阻焊按提交文件及局部扩展表保留，尤其U101/U201和U803，不自动全板缩放。钢网另按203回流位置的专用文件，不使用原始r8默认F.Paste。

这是可审查的工程备注，不是已经发送的订单。局部移孔完成后，所附11孔表已经逐项与最终r10板核对；本轮mask-options.json也已针对最终板复算。

## 证据与复现

- `process-sources.json`：本次原厂网页URL、访问日期、原始HTML/PDF缓存SHA；整页HTML留在忽略的build目录。
- `jlc-capabilities-2026-11-14.html`、`jlc-mask-guide-2026-11-14.html`：真实抓取原始网页，含LDI说明；未伪称浏览器截图。
- `bq-landpattern.png`、`tps-package-36.png`、`tps-package-37.png`、`max17048-pins.png`、`max98357-pins.png`：由本地原厂PDF渲染并逐页目检。BQ p53、TPS p36/37、MAX17048 p6、MAX98357A p15。
- `tools/check_mask_options_r10.py` / `mask-options.json`：只读几何比较；`PYTHONPATH=build/dfm-r9/stencil/python:build/dfm-r9/python python3 tools/check_mask_options_r10.py --output build/dfm-r10/mask-options-recheck.json`。

芯片原厂入口：[BQ24074](https://www.ti.com/lit/ds/symlink/bq24074.pdf)、[TPS63802](https://www.ti.com/lit/ds/symlink/tps63802.pdf)、[MAX17048](https://www.analog.com/media/en/technical-documentation/data-sheets/MAX17048-MAX17049.pdf)、[MAX98357A](https://www.analog.com/media/en/technical-documentation/data-sheets/MAX98357A-MAX98357B.pdf)、[ADI QFN装配指南](https://www.analog.com/en/resources/app-notes/smt-assembly-and-pcb-design-guidelines-for-maxims-standard-wirebonded-quad-flatpack.html)。工艺边界：[JLC国际能力](https://jlcpcb.com/capabilities/pcb-capabilities)、[孔处理说明](https://jlcpcb.com/help/article/pcb-via-covering)。
