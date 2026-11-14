# r10 首批制板与备料

用户确认：**5块PCB，先焊2块；无框钢片，胶带铰链手工定位。** 本目录为r11准备记录，源板和制造包仍是r10。尚未对外提交、采购、下单或上电。

| 用途 | 文件 |
|---|---|
| 板厂/钢网审核要求 | [production-request.txt](production-request.txt)：可直接用于审核；5板+1张完整280×380×0.10mm无框电解抛光钢片 |
| 裸板文件 | [r10裸板ZIP](../r10-review/ESPaperPlay-r10-board-REVIEW_ONLY.zip)，含11孔工艺表，不含钢网 |
| 钢网文件 | [r10独立DIY钢网ZIP](../r10-review/ESPaperPlay-r10-DIY-stencil-REVIEW_ONLY.zip)，只用这一份膏口 |
| 工厂回复 | [factory-reply-template.json](factory-reply-template.json)，所有未收到项为null，不代表接受或零费用 |
| 两板备料 | [可搜索/打印表](procurement-plan.html)、[完整数据](procurement-plan.json)：64种，净需求460件，可选备料198件；不含库存抵扣/MOQ |
| 装配查位 | [原r10装配图](../r10-review/assembly/assembly-map.html)：203位回流+27位手焊/板 |
| 首板工作单 | [具体接线与流程](../../../review-r11/first-board-checklist.md)、[两板测量模板](../../../review-r11/first-board-measurements.json) |
| 工艺及关键电容证据 | [工厂审查](../../../review-r11/factory-capability-review.md)、[电容审查](../../../review-r11/component-closure.md) |

采购按准确厂商+完整候选MPN+封装合并，保留所有位号。电阻/电容可选备料为`max(5, ceil(净需求×10%))`，其他物料每种+1，ESP32模组不预加。这是可按库存调整的工程备料策略，不是供应商起订量或已确认订单。另需4个2.54mm跳帽（可备2个），只用于J202/J502；J105保持开放。现有屏幕和延长件、扬声器可逐板复用。

R108及另5个DNP位号不装。关键电容证据在器件/上电阶段闭合；工厂生产稿在制造阶段确认。现有M0不具备分域维护功能。两块板的测量记录分别填写，空值不能标为通过。

从仓库根目录运行 `python3 tools/prepare_first_batch_r11.py` 可复现备料JSON/HTML；脚本先核对原r10 PCB及31个制造包文件的哈希，发生变化即停止。当前清单不修改r10原包，后续设计变化需重新审查来源与本批规格。
