# ESPaperPlay V2 r10：嘉立创EDA最终CAM复核版

2026-11-15。**本次设计侧CAM复核通过，严格DRC 0；工厂生产稿、实际叠层/阻抗及填孔工艺仍待确认。未提交、未下单。**

本目录取代 `../r10-checked/` 作为当前嘉立创工程和CAM入口；旧目录保留检查历史。原KiCad r10与原制造ZIP均未修改。
客户端工程仍名为 `ESPaperPlay-V2-r10-migrated`，本次修改已保存。工程UUID `5f78098564b143419750286dad7b1c42`，PCB `52caa9452ee66dee`。

| 文件 | 用途 |
|---|---|
| [原生工程](ESPaperPlay-V2-r10-CAM-final.epro2) | 最新嘉立创EDA工程备份；包含原理图、PCB和项目库 |
| [裸板审核包](ESPaperPlay-V2-r10-EasyEDA-board-REVIEW_ONLY.zip) | 5片PCB；4铜层、2阻焊、2丝印、板框、组合PTH与NPTH、11孔填盖清单 |
| [专用DIY钢网](ESPaperPlay-r10-DIY-stencil-REVIEW_ONLY.zip) | 1张无框钢片；原r10专用钢网逐字节保留，203位/636开口 |
| [加工要求](production-request.txt) | 5片板、先焊2片；280×380×0.10mm无框钢网，胶带铰链定位 |
| [CAM报告](CAM_REVIEW.md) | 修复项目、数值检查和已分类差异 |
| [正面](previews/cam-top.png)、[背面](previews/cam-bottom.png)、[内层1](previews/cam-inner1.png)、[内层2](previews/cam-inner2.png) | 实际最终Gerber与钻孔回读渲染；背面按板底视角镜像 |
| [装配资料](../../manufacturing/r10-review/assembly/assembly-map.html) | 位置与分组未改，继续使用原203回流/27手焊/6DNP资料 |

`Gerber-full-audit-only.zip` 仅为完整输出证据：含重复via-only钻孔、通用锡膏等，不应整包提交工厂。
裸板ZIP已经排除重复钻孔和锡膏；钢网只能使用上表的专用包，不能使用通用GTP。

`review/` 保存量化检查；`snapshots.zip` 保存最终及对照输入；`reproduce/README.md` 给出复现方法。
`SHA256SUMS` 校验本目录每个文件；仓库根部 `repository-manifest.json` 覆盖Git跟踪文件。

后续在嘉立创工程继续修改时，应同时保存新的epro2、重新导出CAM、复核并更新校验清单；不要运行历史KiCad生成脚本覆盖迁移成果。两套CAD不会自动同步。
