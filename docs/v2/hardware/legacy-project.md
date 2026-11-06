# 旧版嘉立创工程接收记录

日期：2026-11-01。状态：原始归档已保存并完成结构检查；已开展六页静态电路审查，见 [审查报告](review/README.md)。尚未在原软件运行 ERC/DRC，也未完成 KiCad 导入。

用户补充：当前固件运行于核心板，相关 GPIO 被 LED 占用，因此 SD 使用调整后的单线配置。归档 PCB 与当前实物不是同一硬件目标；其 SD 四线接线与固件差异不自动视为接线错误，详见 [板卡适配记录](review/legacy-mcu-usb-sd.md)。

## 原文件与可追溯性

用户将旧版工程另存到下载目录：`/home/xiaobao/下载/ProPrj_ESPaperPlay_2026-11-01.epro2`。已保留原文件，并在 [本机参考目录](../../../hardware/reference/legacy/README.md) 保存同名副本。原件和副本 SHA-256 一致；完整条目、大小和哈希见 [sources.json](../../../hardware/reference/legacy/sources.json)。

归档大小为 2,509,680 字节，是 ZIP 容器：21 个条目（含一个目录），解压总大小 9,936,501 字节。内容包括 `project2.json`、`ESPaperPlay.epru` 和 18 张 WebP 图片。`project2.json` 中工程名为 `ESPaperPlay`，编辑器版本为 `4.1.93`。

只在 `build/legacy-intake/` 提取用于读取；提取前检查路径、符号链接和总大小。读取未修改源归档，也没有执行其中内容。

## 工程清单

`.epru` 使用 `DOCHEAD`、`META` 等日志记录。按原厂说明读取文档标识和删除标志；相同记录按 ticket/client 规则选择最终记录。原厂说明此格式会保留删除历史，不能直接把所有图页头都计入有效设计。[嘉立创官方格式说明](https://github.com/easyeda/easyeda-file-format)

可可靠识别的当前结构：

| 内容 | 归档记录 |
| --- | --- |
| 原理图 | 1 套 `Schematic1`，关联 `Board1` |
| 未删除的原理图页 | 6 页：`MCU`、`EPD`、`TOUCH`、`SD`、`POWER`、`AUDIO` |
| PCB | 1 个 `PCB1`，关联 `Board1` |
| PCB 元件实例记录 | 103 个非空 `COMPONENT` 记录；不等同于采购 BOM 或已装配元件数量 |
| 其他容器 | `Board2` 没有本次识别到的原理图/PCB 关联；`Panel1` 仅有元数据和画布记录 |
| 删除历史 | 5 个 `SCH_PAGE` 明确标记 `DELETE_DOC.isDelete=true`，名称涉及 `POWER`、`POWER_BACKUP`、`POWER_REDRAW` |

不能用原理图 `COMPONENT` 记录总数计算采购数量，因为其中也包含电源符号、网络标识等对象。嵌入库数量也不等于实际使用元件数量。

### PCB 层信息需要复核

`PCB1` 的逻辑 `LAYER` 记录将 `Top Layer`、`Bottom Layer`、`Inner1`、`Inner2` 设为 `use=true`；但 `LAYER_PHYS` 物理叠层记录只包含顶底铜层及一个 FR4 介质，没有对应的两个内层物理记录。因此，当前不能仅据这些字段认定旧实板是四层板。

需在嘉立创 EDA 的图层/叠层管理器及旧制板输出中确认实际铜层、板厚和介质配置。这项差异不改变新版开发验证板采用四层设计的既定方向。

## KiCad 兼容性与后续路径

嘉立创官方将 `.epro2` 定义为 V3 及后续版本的新归档格式。本文件确实是 `project2.json` 加 `.epru` 日志结构。KiCad 10.0 文档列出的 EasyEDA Pro 工程导入扩展名为 `.epro`、`.zip`；开发文档描述的是 `project.json`、`.esch`、`.epcb` 等结构。本次没有验证 `.epro2` 可以直接导入，不能把修改文件后缀视为格式转换。[KiCad 10.0 导入说明](https://docs.kicad.org/10.0/en/kicad/kicad.html#importing_a_project_from_another_eda_tool)、[KiCad EasyEDA 格式说明](https://dev-docs.kicad.org/en/import-formats/easyeda/)

当前原文件已经足够保留工程和开始只读梳理，不需要重新导出才能保存本次工作。需要尝试 KiCad 导入时，先在嘉立创 EDA 打开副本，使用“文件 → 另存为本地”，选择旧版兼容的 **`.epro` / V2.2** 格式，保留当前 `.epro2` 原件。官方确认 V3 支持导出 V2.2 的 `.epro`，且可能存在格式细节差异。[嘉立创客户端说明](https://prodocs.lceda.cn/cn/faq/client/)、[V3.1.x 更新说明](https://prodocs.lceda.cn/cn/release-note/v3.1.x/)

随后把兼容归档导入独立目录，逐项对照六页原理图、元件位号与封装、引脚和网络、板框、铜层、规则、铺铜和 3D 模型。迁移成功需要这些对照及 ERC/DRC 结果，不能以“软件能打开”替代。若暂不迁移旧 PCB，原软件导出的原理图 PDF、BOM 和网表也可作为新版重绘的参考输入。

接收阶段仅做完整性与结构检查；后续静态电路审查另见上述报告。没有修改旧设计、运行其 ERC/DRC、确认原理图与实板一致性，或将任何旧器件定为新版 BOM。
