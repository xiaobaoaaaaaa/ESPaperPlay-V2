# r10 设计整改与制造复核

2026-11-14。当前[r10 PCB](../ESPaperPlay_Devboard.kicad_pcb)已调整64个近焊盘过孔；原理图r6/r5、器件和网络保持。[设计说明](../../../docs/v2/hardware/pcb-dfm-r10.md)与[审查文件包](../output/manufacturing/r10-review/README.md)是本轮入口，r8/r9资料保留历史。

| 证据 | 内容 |
|---|---|
| [design-baseline.json](design-baseline.json) | r10来源、PCB/项目SHA、保留11热孔UUID及标签变化 |
| [r8-to-r10-via-delta.json](r8-to-r10-via-delta.json) | 64个via/67个原线段端点的完整改动，R213/R214改为既有小孔规格 |
| [drc.json](drc.json)、[independent-board-check.json](independent-board-check.json) | 当前原生DRC与原理图/库/UUID/编号核对 |
| [delta-validation.json](delta-validation.json) | 独立逐对象差异、非目标铜保持及平面重填边界 |
| [signal-paths.json](signal-paths.json)、[power-paths.json](power-paths.json) | 当前信号长度及21条电源路径模型 |
| [signal-power-comparison.json](signal-power-comparison.json)、[return-via-comparison.csv](return-via-comparison.csv) | 21条电源路径和USB保持、SD D0微变；219个非GND via回流距离无新增超标 |
| [negative-control.json](negative-control.json) | 非目标USB线段移动与无关平面缺口会被独立校验拒绝 |
| [cam-readback.json](cam-readback.json) | 实际制板CAM的9图层、663钻孔及4段板框回读 |
| [stencil-audit.json](stencil-audit.json)、[all-via-mask-clearance.csv](all-via-mask-clearance.csv) | 全549via两面实际阻焊余量；203位DIY钢网与源板不变检查 |
| [thermal-via-fill-spec.csv](thermal-via-fill-spec.csv)、[thermal-hole-process-spec.json](thermal-hole-process-spec.json) | 11IC孔的明确树脂填平/镀铜盖帽工艺，普通组件孔/NPTH保持开通 |
| [mask-and-thermal-process-r10.md](mask-and-thermal-process-r10.md)、[mask-options.json](mask-options.json) | 保留阻焊的依据、697焊盘分组、统一扩窗的反事实比较 |
| [process-sources.json](process-sources.json) | 原厂网页/PDF来源及实际本地缓存哈希，不分发原厂全文 |
| [impedance-review-r10.md](impedance-review-r10.md)、[impedance-window-r10.json](impedance-window-r10.json) | 官方四点线宽窗口；界面数据转录，非厂商生产签核 |
| [verification-r9-before.json](verification-r9-before.json) | 更改前验证清单 |

阻焊图形未改。新板零扩展符合JLC现行1:1 LDI能力，不把它单独认定为制造缺陷；近孔余量通过移孔解决。首板试印、填孔平整度、回流/热/声学/电气验证尚未发生；未下单或上电。R108 DNP、J105开放保持。

复现环境沿用KiCad10.0.8/系统pcbnew、Python3.15.2，额外包gerbonara1.6.2、shapely2.2.0、matplotlib3.11.2；PNG另需系统Rsvg/pycairo。脚本复用版本化r9的几何函数，不修改历史报告。原始r8基线可从提交7e27d82读取到临时目录，不能用旧生成器覆盖当前正式板。

```sh
PYTHONPATH=/path/to/dependencies python3 tools/export_manufacturing_r10.py --render
python3 hardware/devboard-r0/tools/check_pcb_routing_r8.py \
  --drc hardware/devboard-r0/review-r10/drc.json --output build/dfm-r10/independent-recheck.json
python3 tools/check_pcb_dfm_r10.py --baseline build/dfm-r10/intake/ESPaperPlay_Devboard.kicad_pcb \
  --candidate hardware/devboard-r0/ESPaperPlay_Devboard.kicad_pcb \
  --contract hardware/devboard-r0/review-r10/r10-delta-contract.json --output build/dfm-r10/delta-recheck.json
python3 tools/verify_repository.py
```

`--stage board|stencil|assembly|package`可单独重建；省略时依序全部执行。源板与项目必须匹配design-baseline固定哈希。导出包含时间戳，重新导出后必须同步审计和哈希，不可混用旧ZIP与新PCB。文件包的坐标/钢网/填孔要求以其README为准。

原始r8基线若本机没有，可在临时目录用 `git show 7e27d82:hardware/devboard-r0/ESPaperPlay_Devboard.kicad_pcb` 恢复；[apply_via_delta.py](apply_via_delta.py)只允许将差异重放到正式工程树外，默认差异表为本目录r8-to-r10-via-delta.json。重放得到铜几何候选，r10标题/日期/两条丝印变化另记在design-baseline.json。历史r9导出器仍锁定原r8 SHA，不能直接对当前r10运行。
