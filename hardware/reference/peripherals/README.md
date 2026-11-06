# EPD、microSD 与音频原厂资料

归档核对日期：2026-11-02，用于开发验证板 r2 DRAFT。器件仍是设计候选；资料核对不代表整板已经过功耗、信号完整性、ESD 或制造验证。

[sources.json](sources.json)合并本轮三部分的原厂来源、修订、使用范围与已知限制。20 条来源中，14 份本地文件保存实际字节数和 SHA-256；其中 8 份新文件保存在本目录，6 份复用已有参考目录。其余 6 条仅保存真实 URL 和访问说明，不填造本地文件或哈希。所有 `local_path` 相对于仓库根目录，不依赖临时构建目录。

原厂 PDF/HTML 保持原样并忽略 Git，版权属于各原厂，不适用本仓库 MIT 许可。刚从 Git 克隆时，须按原厂 URL 取得本地文件；若官网修订变化导致哈希不同，应重新核对，不能沿用旧结论。

| 资料与候选 | 本轮用途与保存位置 |
| --- | --- |
| Good Display GDEY075T7-T01 | 复用 `../good-display/` 的总成规格书，核对第 6、7、38 页的 24-pin 接口和升压电路；FPC 配套连接器料号、接触面及样品方向尚未冻结 |
| TI SN74LVC541APWR、SN74LVC1G125DBVR | 本目录；EPD 五路单向写入缓冲、BUSY 返回以及音频麦克风 SD 返回；不支持 EPD SDI 反向读回 |
| Vishay Si1308EDL-T1-GE3、onsemi MBR0530 | 本目录；EPD 升压 MOSFET 和三只整流二极管，按准确制造商资料核对 |
| TI TMUX1511PW、TCA9539 | 复用 `../power/`；SD 六路隔离和 SEL 默认低电平计算。两个 TMUX 由 SD_3V3 供电，未用 SEL 接地 |
| Hirose DM3AT-SF-PEJM5 | 原厂产品页和目录的在线证据；本地 PDF 下载返回 403。A/B 检测触点无卡开路、插卡闭合；KiCad 9/10 是非极性触点对的库编号，实际 A/B 位置和机械封装仍须核样 |
| TI TPD2E2U06DCKR | 复用 `../mcu-usb/`；SD 六条数据线、检测触点与电源的对地 ESD 保护候选 |
| ADI MAX98357A | 复用 `../power/`；扬声器功放、SD_MODE、增益、采样率及静音时序 |
| PUI DMM-4026-B-I2S-R | 本目录；七焊盘麦克风、CONFIG/LR 接法及 I2S 时钟边界 |
| Nexperia 74LVC125APW、TI SN74LVC1G14 | 前者仅原厂在线 PDF 提取，未取得原始文件；后者 PDF 在本目录。用于音频信号隔离和施密特 OE 控制 |
| Nexperia 74CBTLV3245PW | 仅保留原厂在线来源和弃选理由：VSW 绝对最大值为 VCC+0.5 V，AON 塌陷而 SD 残电时可能超限；VCC=0 的 Ioff 条件不足以覆盖过渡阶段 |
| TI SN74LVC125A、TDK T5848 | 本目录保存比较资料，不是本版装配候选。前者没有据此确认与 Nexperia 相同的 Ioff 保证；后者需要 1.8 V 电源及相应电平处理 |

同名器件必须区分厂家。旧工程中台舟/TECHPUBLIC 的 SI1308EDL 不能用 Vishay 手册替代证明；旧 R+O 二极管与本版 onsemi MBR0530 的压降条件也不能混用。本版 onsemi 手册给出 500 mA、25°C 条件下最大 430 mV，不能推导成其他温度、电流或 MBR0530T1G 型号的统一保证。TI SN74LVC125A 与 Nexperia 74LVC125APW 同样不能仅凭系列名称互换。

TI 两款 EPD 缓冲的 ACTIVE 状态按本轮官方产品页／订购附录记录。Vishay Si1308EDL 的明确生命周期字段、onsemi MBR0530 的供货生命周期以及 PUI 麦克风的生产状态仍须在 BOM 冻结前确认；官网有规格书或产品条目不等于已经确认可采购。其他候选也须按准确订货号复核，不能把这份档案当作实时库存清单。

SD 与 TOUCH 的 TMUX SEL 默认下拉改为 10k：不把典型 6 MΩ 内部下拉计入保证；SD 六路每路 2 µA，再加有效供电时 IOX 的 1 µA，得到约 0.13 V，低于 SEL 的 0.45 V 低电平上限。该计算不证明 IOX 在掉电或棕断时的行为。TMUX 的 S/D 绝对最大值为 6 V；推荐信号范围仍随 VDD 变化，供电过渡、隔离漏电及 20 MHz SD 总线需要实测。

在本目录执行 `sha256sum -c SHA256SUMS` 可核对全部 14 份本地文件，包括相邻参考目录。执行 `python verify_sources.py` 还会检查清单中的字节数、路径和在线来源没有伪造本地哈希。KiCad 库的哈希只是本轮环境观察，未作为原厂机械批准或归档验证的必备依赖。
