# r3 审查记录

`bom-review.json` 是最终逐位号候选表，与当前原生 KiCad 属性对应；`root/`、`power/`、`audio_epd/`、`interconnect/` 是分项审查证据。分项中的委托、待定或建议文字属于审查过程，最终选择以总表和原生工程为准。记录内 `build/bom-review-r3/…` 路径只表示本轮资料出处，不是打开工程的依赖。

本地13种封装安装在上一级 `ESPaperPlay.pretty`，用项目相对 `fp-lib-table` 引用。原厂图纸、在线资料及实际字节哈希统一索引在 `../../reference/bom-r3/sources.json`；在线记录没有伪造本地PDF哈希。全部32种封装的实际几何/哈希快照包含在最终封装检查报告中。

`inventory-r2-before.json`、`electrical-baseline-r2.json` 和 `verification-r2-before.json` 保留本轮开始前的器件/连接/校验记录。基线连接快照来自前轮真实 XML，允许检查器在没有本机旧导出文件时比较电气连接、器件UUID、值和DNP状态。

本轮222个位置包括6个DNP；215个封装候选、184个候选MPN均不表示制造放行。还需闭合7个空封装、38个未定MPN以及已选候选的工艺/电气/机械条件；具体原因见总表和 `docs/v2/hardware/bom-footprint-review-r3.md`。
