# r9 制造与自行装配审查包

2026-11-11，**REVIEW ONLY：供工艺审核，尚未制造放行。** PCB、电气版本仍为 r8 / r5；源板未修改。用户自行钢网回流，接口、排针及按钮后手焊。工艺条件见[主报告](../../../../../docs/v2/hardware/manufacturing-review-r9.md)。

| 目录/文件 | 用途 |
|---|---|
| [裸板审查ZIP](ESPaperPlay-r8-board-r9-REVIEW_ONLY.zip)、[钢网审查ZIP](ESPaperPlay-r8-DIY-stencil-r9-REVIEW_ONLY.zip) | 分开打包的加工审核输入；压缩包内保留REVIEW ONLY说明 |
| [board/](board/) | 4层铜、双面阻焊/丝印、板框、PTH/NPTH钻孔、钻孔图和KiCad job；**不含焊膏层** |
| [stencil/](stencil/) | 仅本次DIY修正版正面钢网；无背面印膏工序 |
| [assembly/bom-fitted.csv](assembly/bom-fitted.csv) | 230个实装位置的分组候选BOM，不含采购余量，尚未采购冻结 |
| [assembly/reflow-positions.csv](assembly/reflow-positions.csv) | 203个回流位置，用于人工查位 |
| [assembly/hand-solder.csv](assembly/hand-solder.csv) | 4个SMD接口＋23个通孔器件，均回流后手焊 |
| [assembly/dnp.csv](assembly/dnp.csv) | 6个不装位置；R108保持DNP |
| [离线装配查位图](assembly/assembly-map.html) | 搜索位号/料号、筛选回流或手焊位置，点击查看属性；不是1:1定位模板 |
| [assembly/population.csv](assembly/population.csv) | 240个位置的完整属性/工序表，含4个机械孔 |
| [assembly/assembly-summary.json](assembly/assembly-summary.json) | 来源哈希、分组、坐标规则及产物哈希 |
| [previews/cam-top.png](previews/cam-top.png)、[背面](previews/cam-bottom.png) | 独立读取实际Gerber/Excellon生成的预览；背面按从板底看镜像显示 |

制板与钢网分包，避免将原始r8焊膏层用于本次自装。不要直接使用KiCad默认F.Paste输出：它仍包含C501/C502/R108的DNP开孔、手焊接口开孔及无支撑的麦克风环形开孔。

正式源板SHA-256：`1a4556d866cc1352a2c45b674c94d2f233edf28c3e003bd96c8f6caf1e630681`。本包使用KiCad 10.0.8导出；[回读校验](../../../review-r9/cam-readback.json)对663个孔逐一核对坐标/孔径/镀孔属性，4段板框中心线及层清单一致；[原生检查](../../../review-r9/independent-board-check.json)为0错误/0未连接/0原理图差异，保留1个既有U301绘图警告。

CAM坐标采用KiCad绝对原点，Gerber/钻孔Y为KiCad Y的负值。装配CSV另用板左下角原点：`X=KiCadX−50, Y=160−KiCadY`；原生封装锚点不一定等于物体重心，角度不是供料角度。本包没有外部PCBA委托格式。

板框物理尺寸取线中心 **160×110 mm**。0.05mm板框线的外包围盒及KiCad job可能显示160.05×110.05mm，不能据此扩大外形。

工艺审核需确认：指定层叠的USB/SD阻抗；11个IC焊区内孔及邻近孔处理；阻焊开窗、桥宽和对位；0.10mm钢网与麦克风0.15mm支撑桥的可加工性。首板印膏/回流及电气实测在样板阶段进行，不是假定已完成。U301仅外周脚印膏，中心EPAD不印膏；其他IC热焊盘保留。初装J105保持开放，充电仍禁用。

复现脚本与依赖见[审查索引](../../../review-r9/README.md)。[artifact-index.json](artifact-index.json)保存本目录产物SHA-256；两份ZIP已解包逐文件核验。已生成的审查包不是订单，也未向板厂上传。
