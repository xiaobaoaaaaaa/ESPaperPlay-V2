# r11 首批准备审查索引

日期2026-11-14。**r11是准备记录，正式PCB仍r10，原理图r6绘图/r5电气。** 用户确认5块裸板、先焊2块，无框钢片胶带铰链定位。此次没有制造文件变更、实物测试或工厂签认。

| 记录 | 内容 |
|---|---|
| [factory-capability-review.md](factory-capability-review.md) | 国内生产模型差异、±10%阻抗、填孔、钢网原样加工与报价回复项 |
| [factory-capability-sources.json](factory-capability-sources.json)、[stencil-ui-transcription.txt](stencil-ui-transcription.txt) | 官方来源、280×380mm无框钢片真实页面核对；未提交 |
| [factory-geometry-check.json](factory-geometry-check.json) | 当前板实际孔距、槽孔与线宽的补充只读核对 |
| [component-closure.md](component-closure.md)、[component-closure.json](component-closure.json) | 56个电容/10种MPN、四个关键容量门槛与来料测量路径；尚未闭合实测 |
| [first-board-checklist.md](first-board-checklist.md)、[first-board-measurements.json](first-board-measurements.json) | 当前网表端子针序、跳帽、单源限流及分域步骤；两板各13项均待测 |
| [verification-r10-before.json](verification-r10-before.json) | 本轮前的完整硬件校验快照 |
| [final-consistency.json](final-consistency.json) | 原设计/31个制造包文件保持、两板物料分组与数量、空白记录核对 |

[本批可用文件](../output/manufacturing/r10-first-batch/README.md)包含具体加工要求、两份原r10 ZIP入口、工厂回复模板和64种备料表。阶段说明见[首批准备r11](../../../docs/v2/hardware/first-batch-preparation-r11.md)。当前的“待工厂回复”“待实测”必须由对应证据完成，不能用本地检查替代。
