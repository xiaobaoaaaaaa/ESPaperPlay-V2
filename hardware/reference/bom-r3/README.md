# BOM r3 原厂资料归档

2026-11-02，合并 audio_epd、power、interconnect、root 的 source/review JSON。仅处理原厂文件和原厂网页证据。`sources.json` 共 77 个 URL 记录，含 12 份本轮新下载 PDF、20 份现有参考 PDF 的原路径引用，以及 44 个没有本地原始文件的网页/下载尝试记录。同一个本地 PDF 可支持多个 URL 记录，文件本体按 SHA-256 去重。

本目录已归档实际文件；PDF 不纳入 Git，可按 `sources.json` 中 URL 获取并核对哈希。厂商在线文档可能更新，应保留本轮已核对的版本。

- `local_files[].local_path` 是预定正式仓库相对路径；新文件用 `hardware/reference/bom-r3/files/…`，已有文件保持原 `hardware/reference/…` 路径。
- `archive_relative_path` 可在当前目录直接定位待复制文件。
- `original_path` 和 `records` 是来源追溯信息，记录输入文件位置；迁移后读取原厂资料不依赖 scratch。
- 每份真实存在的 PDF 记录实算 SHA-256 和字节数；只含 URL 的记录没有伪造哈希。
- 原厂 URL 域名经过 allowlist 检查；Good Display 官网链接的 CDN 单独标注。经销商线索列入 `excluded_nonprimary_leads`，不作为原厂机械证据。
- 失败下载只保留访问记录，不因此产生规格已核验的结论。

100 nF 候选以 **TDK C1608X7R1H104K080AA** 为准；原厂页面 Production 及 50 V/X7R/±10%/0603 证据来自主任务当日核验。旧 Murata 100 nF 下载尝试保留为历史追溯，明确标记不选用。

运行 `python3 hardware/reference/bom-r3/verify_sources.py` 可核对所有已归档与复用 PDF 的文件头、字节数、SHA-256、目录清单、去重及在线项无伪造文件哈希。此脚本也支持当前位置直接运行。

原厂资料版权属于相应厂商，不因存放在项目内成为 MIT 内容。归档不是采购库存、可生产性或供货期限保证。
