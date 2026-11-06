# V2 独立仓库迁移

迁移日期：2026-11-06（Asia/Shanghai）。新仓库为 `xiaobaoaaaaaa/ESPaperPlay-V2`，公开，默认分支 `main`。

## 来源与保留范围

源目录为 `/home/xiaobao/Projects/ESP32`，源分支 `refactor/v2-platform`，其 HEAD 仍为旧工程提交 `0f6d7c349afdbbeb962a736d84036ce7f8487174`。当时 V2 固件、文档和硬件尚未提交；本次按当前实际文件建立新仓库初始基线，没有伪造 r5/r6/r7 的历史提交。旧目录与旧仓库提交不变，作为迁移参考副本。

新工作目录为 `/home/xiaobao/Projects/ESPaperPlay-V2`。迁移 `v2/`、`docs/v2/`、`hardware/`、`outputs/` 以及 V2 CI，保留相对目录结构。旧版固件和根目录 `dependencies.lock` 不属于迁移内容。

原生 KiCad 工程、11 张原理图、PCB、符号与封装库逐字节保留；固件源代码也未改动。文档中指向旧组件的链接改为旧仓库固定提交，当前入口改为独立仓库与 r7 布局状态。历史审查中的绝对路径和日期保留为其原始记录。

## 公开内容与本地参考

- 收录原创源码、设计文档、KiCad 工程与项目库、检查工具、历史审查记录、已审查图纸/布局预览/网表及 BOM 工作簿。
- 构建缓存、工作站设置、锁文件、生成的 `sdkconfig` 不收录。
- 原厂下载 PDF/网页/图片/压缩包、旧嘉立创原始归档继续只保留本地副本；公开来源索引和哈希。相关说明见 [第三方内容](../../THIRD_PARTY_NOTICES.md)。

迁移前的 245 项硬件校验清单完整保存在 `hardware/devboard-r0/review-migration/verification-r7-before.json`。当前硬件 `verification.json` 保留全部来源哈希，并仅更新因迁移说明而变化的文档哈希；其中明确列出本地参考文件，完整校验仍需要这些下载文件。

仓库根目录的 `repository-manifest.json` 单独覆盖实际提交的公开文件。`python3 tools/verify_repository.py` 可以在干净克隆中检查公开内容，不会将未下载的原厂资料判作已经复核。依赖 Honeywell PDF 的温窗重算须先恢复原始参考文件及 `pdftotext`。

## 本次验证

- 新目录从零配置主机测试，ASan/UBSan 启用，5/5 项通过。
- 新目录使用 ESP-IDF 6.1 生成 ESP32-S3 固件，应用镜像为 177344 字节，适配现有 5 MiB 应用分区；未连接或烧录设备。
- 独立 PCB 检查在新目录通过：236 个电气器件、4 个机械孔、181 条网络、774 个逻辑引脚、804 个实际编号焊盘；PCB 字节及其 r7 DRC 结论未变。
- PCB 仍未布线；499 个未连接项、1 条已说明的天线绘图库差异警告保持。迁移不构成制造或充电放行。

迁移复查记录见 `hardware/devboard-r0/review-migration/`。远端 CI 的实际运行结果以 GitHub Actions 为准，不用本地结果冒充云端运行。

## 后续提交

在新目录继续开发。修改后先完成相关构建或硬件检查，再同步当前审查清单，执行：

```sh
git add <本次改动的文件>
python3 tools/verify_repository.py --update
git add repository-manifest.json
python3 tools/verify_repository.py
git commit
```

`main` 保留已提交阶段基线；较大变更使用短期分支，例如 `codex/pcb-routing`。硬件标签表示实际阶段，不把器件布局标签当成已布线或可制造版本。
