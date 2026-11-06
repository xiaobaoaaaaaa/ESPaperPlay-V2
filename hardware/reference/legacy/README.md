# 旧版嘉立创工程原始归档

接收日期：2026-11-01。用户提供的原文件为 `/home/xiaobao/下载/ProPrj_ESPaperPlay_2026-11-01.epro2`。

本目录保留同名、逐字节一致的本机副本，原文件未修改。文件大小 2,509,680 字节，SHA-256：

```text
aa9540b138b95a9e4e70a56337f4366901f3e5233e9a12d55d852e55732ef614
```

- [sources.json](sources.json)：来源、归档内容哈希、可读取的工程清单、官方格式参考。
- [SHA256SUMS](SHA256SUMS)：本机校验清单；在本目录执行 `sha256sum -c SHA256SUMS`。
- [旧工程接收与兼容性记录](../../../docs/v2/hardware/legacy-project.md)：有效图页、PCB、层信息差异及后续导入路径。
- [审查证据](review-evidence.json)：103 个器件、352 个唯一引脚网络及 29 项 GPIO 宏对照，保留原始记录行号。SD 差异已按用户说明标为核心板适配，不认定为 PCB 错误。
- [六页静态审查](../../../docs/v2/hardware/review/README.md)：保留、修改、待验证项目及依据。

原始归档由本目录 `.gitignore` 排除，仅在本机保留；这里的副本不是异地备份，也未上传。临时解包和只读解析结果位于仓库已忽略的 `build/legacy-intake/`，没有执行归档中的内容。

本次接收没有转换或覆盖旧设计，没有完成电气检查，也没有据此冻结新版元件或布局。
