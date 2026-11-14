# ESPaperPlay r10 制造与自行装配审查包

日期2026-11-14，**REVIEW ONLY：工艺审核资料，尚未下单或获得工厂生产确认。** 当前PCB为r10；原理图r6绘图/r5电气保持。详细改变及边界见[r10记录](../../../../../docs/v2/hardware/pcb-dfm-r10.md)。

| 文件 | 用途 |
|---|---|
| [裸板ZIP](ESPaperPlay-r10-board-REVIEW_ONLY.zip) | 4层铜、双面阻焊/丝印、板框、钻孔及11孔填孔盖帽清单；不含paste |
| [钢网ZIP](ESPaperPlay-r10-DIY-stencil-REVIEW_ONLY.zip) | 仅已审查DIY正面焊膏图及说明，不包含原始r10默认paste |
| [装配查位图](assembly/assembly-map.html) | 离线搜索位号/候选料号、筛选工序、点击查看；不是1:1贴装模板 |
| [BOM](assembly/bom-fitted.csv)、[回流定位](assembly/reflow-positions.csv) | 230实装位置、203回流；候选MPN未采购冻结，未计采购余量 |
| [后手焊](assembly/hand-solder.csv)、[DNP](assembly/dnp.csv) | J406/J501/J601/J701加23个通孔位置后手焊；6个DNP不印膏不装 |
| [完整清单](assembly/population.csv)、[来源与坐标规则](assembly/assembly-summary.json) | 240位置，含4个机械孔 |
| [正面CAM](previews/cam-top.png)、[背面CAM](previews/cam-bottom.png) | 由实际Gerber/Excellon回读生成；背面按从板底观察镜像显示 |
| [artifact-index.json](artifact-index.json) | 文件与ZIP的SHA-256 |

裸板仍为160×110mm四层，绝对CAM坐标X=KiCadX、Y=−KiCadY，单位mm。CSV单独采用板左下角原点X=KiCadX−50、Y=160−KiCadY；角度为原生封装角度，不是供料机角度。钻孔图仅供查看，以DRL加工。板框取0.05mm线的中心；其包围盒160.05×110.05mm不是物理板框尺寸。

普通近孔已移动，538个非热孔两面孔边至实际阻焊开口≥0.20mm。11个保留IC热孔明确要求树脂填平、电镀盖帽≥10µm和可焊ENIG，不能用普通盖油替代。工厂可能要求扩大过孔处理范围，需对照生产稿；95个普通组件孔、7个NPTH不可堵。当前固定叠层和阻抗为设计要求，尚未工厂签认。

钢网仅为203位回流器件印膏，U301中央不印膏；麦克风四桥、钢片厚0.10mm仍需首板试印和焊接验证。R108保持DNP、J105开放。复现入口为仓库根目录 `tools/export_manufacturing_r10.py`，见[检查索引](../../../review-r10/README.md)。
