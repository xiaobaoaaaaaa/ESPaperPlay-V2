# ESPaperPlay-V2

基于 **ESP32-S3-WROOM-1-N16R8 + 7.5 英寸电子纸**的多功能平台，逐步实现阅读、音频和网络应用。

这是从 [ESPaperPlay](https://github.com/xiaobaoaaaaaa/ESPaperPlay) 拆分的独立重构仓库。旧版代码的参考起点为 [`0f6d7c3`](https://github.com/xiaobaoaaaaaa/ESPaperPlay/tree/0f6d7c349afdbbeb962a736d84036ce7f8487174)。本库从当前 V2 基线建立新的提交历史，不包含旧固件工程。

## 当前状态

- **固件：M0 骨架。** 应用宿主、活动租约、休眠准备契约、板级配置检查、双槽分区和串口演示已经实现；外设驱动、图形界面和网络应用尚待接入。
- **硬件：r8 PCB 已布线，r9 制造与自装审查已完成。** 160 × 110 mm 四层开发验证板，236 个电气位置、4 个安装孔。原理图仍为 r6 绘图、r5 电气设计，PCB 源文件未变；KiCad 10.0.8 复查为 0 错误、0 未连接。已准备制板 CAM、修正后的自装钢网、203 个回流及 27 个手焊位置清单，均为审查版，尚未制造放行。见 [r9 审查与待确认条件](docs/v2/hardware/manufacturing-review-r9.md)及[文件包](hardware/devboard-r0/output/manufacturing/r9-review/README.md)。
- 未进行新板烧录或上电验证。硬件的充电默认禁用状态、温窗假设及待验证项见硬件文档。

## 目录与入口

| 目录 | 内容 |
| --- | --- |
| [v2/](v2/README.md) | 独立 ESP-IDF 固件、主机测试及板级元数据 |
| [docs/v2/](docs/v2/README.md) | 架构、路线和软硬件设计记录 |
| [hardware/devboard-r0/](hardware/devboard-r0/README.md) | 原生 KiCad 工程、项目库、检查器和评审记录 |
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

继续硬件工作时直接编辑原生 KiCad 工程；历史生成脚本不能覆盖已经手工修改的原理图或 PCB。设计变更后同步更新相应检查报告与校验清单。

本项目原创代码与文档沿用 [MIT License](LICENSE)。KiCad 库内容及原厂资料的归属见 [第三方说明](THIRD_PARTY_NOTICES.md)。
