# ESPaperPlay-V2

基于 **ESP32-S3-WROOM-1-N16R8 + 7.5 英寸电子纸**的多功能平台，逐步实现阅读、音频和网络应用。

这是从 [ESPaperPlay](https://github.com/xiaobaoaaaaaa/ESPaperPlay) 拆分的独立重构仓库。旧版代码的参考起点为 [`0f6d7c3`](https://github.com/xiaobaoaaaaaa/ESPaperPlay/tree/0f6d7c349afdbbeb962a736d84036ce7f8487174)。本库从当前 V2 基线建立新的提交历史，不包含旧固件工程。

## 当前状态

- **固件：M0 骨架。** 应用宿主、活动租约、休眠准备契约、板级配置检查、双槽分区和串口演示已经实现；外设驱动、图形界面和网络应用尚待接入。
- **硬件：r10 PCB 制造整改完成。** 已移动64个近焊盘过孔，538个普通孔的双面阻焊间距达到≥0.20mm，11个IC热孔指定填平盖帽；官方USB/SD名义阻抗窗口检查通过。原理图r6/r5保持，DRC为0错误、0未连接；已更新独立制板、DIY钢网及203位回流/27位手焊文件，尚未下单或上电。见 [r10记录](docs/v2/hardware/pcb-dfm-r10.md)和[文件包](hardware/devboard-r0/output/manufacturing/r10-review/README.md)。
- **首批准备r11：** 已按5块PCB、先焊2块及无框钢片整理[工厂审核规格、64种备料表与首板工作单](hardware/devboard-r0/output/manufacturing/r10-first-batch/README.md)。PCB保持r10，工厂回复、来料容量和实测仍待完成；现有M0不具备分域维护功能。
- **嘉立创迁移：** [当前工程备份](hardware/devboard-r0/output/easyeda/r10-checked/ESPaperPlay-V2-r10-migration-final.epro2)及[迁移检查记录](hardware/devboard-r0/output/easyeda/r10-checked/CHECK_REPORT.txt)已纳入版本管理。迁移检查严格DRC为0，原KiCad r10与制造包保留作对照；迁移输出尚未替换制造交付包。
- 未进行新板烧录或上电验证。硬件的充电默认禁用状态、温窗假设及待验证项见硬件文档。

## 目录与入口

| 目录 | 内容 |
| --- | --- |
| [v2/](v2/README.md) | 独立 ESP-IDF 固件、主机测试及板级元数据 |
| [docs/v2/](docs/v2/README.md) | 架构、路线和软硬件设计记录 |
| [hardware/devboard-r0/](hardware/devboard-r0/README.md) | KiCad r10基线、嘉立创迁移工程、项目库、检查器和评审记录 |
| [hardware/reference/](hardware/reference/) | 原厂来源、版本与 SHA-256；原始下载文件仅本地保存 |
| [outputs/](outputs/) | 已审查的 BOM 工作簿 |

迁移暂时保留 `v2/`、`docs/v2/` 和 `devboard-r0` 路径，使原有工程、检查器及证据链接继续有效；这些目录名不表示当前硬件仍是 r0。

## 验证

主机测试不需要 ESP-IDF：

```sh
cmake -S v2/tests -B v2/build/host -G Ninja \
  -DCMAKE_C_COMPILER=clang -DCMAKE_BUILD_TYPE=Debug
cmake --build v2/build/host
ctest --test-dir v2/build/host --output-on-failure
```

激活 ESP-IDF 6.1 后构建 N16R8 固件：

```sh
idf.py -C v2 -B build/esp32s3 build
```

固件详细说明见 [v2/README.md](v2/README.md)。硬件检查命令见 [开发板说明](hardware/devboard-r0/README.md)；公开文件完整性可运行 `python3 tools/verify_repository.py`。原厂 PDF 不随 Git 分发，重新计算依赖 PDF 的温窗模型前，须按相应 `sources.json` 恢复资料。

## 版本管理

`main` 保存已提交的阶段成果，功能开发使用短期分支。硬件设计修订号与 Git 标签分别管理，r5/r6/r7 的历史报告不是对应的历史提交。迁移来源、检查结果和当前基线见 [迁移记录](docs/v2/repository-migration.md)。

嘉立创工程入口及历史快照见[迁移目录](hardware/devboard-r0/output/easyeda/README.txt)，KiCad r10保留为迁移对照基线。两种工程不会自动双向同步；每次变更须注明所编辑的工程及来源版本，同步更新导出、检查报告与校验清单。历史生成脚本不能覆盖已经手工修改的原理图或PCB。

本项目原创代码与文档沿用 [MIT License](LICENSE)。KiCad 库内容及原厂资料的归属见 [第三方说明](THIRD_PARTY_NOTICES.md)。
