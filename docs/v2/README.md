# ESPaperPlay v2 设计与开发记录

> 最新硬件（2026-11-14）：[r10制造整改](hardware/pcb-dfm-r10.md)已移动64孔并完成实际CAM/钢网复核，明确11个热孔填平盖帽，USB/SD官方名义窗口通过。原理图仍为r6绘图/r5电气；尚未下单或上电。

设计起始日期：2026-11-01；硬件状态更新：2026-11-14。当前为独立的 `ESPaperPlay-V2` 仓库，默认分支为 `main`；原仓库的 `refactor/v2-platform` 是迁移前的本地工作分支。

## 已确定的基线

- 多应用电子纸平台，阅读、媒体与网络功能共用平台服务。
- 保持 ESP32-S3-WROOM-1-N16R8、16 MB Flash、8 MB PSRAM，不升级到 N32R16V。
- 复用现有 GDEY075T7-T01 7.5 英寸屏幕与触摸总成，重新设计主板。
- 独立控制屏幕、触摸、SD、音频电源，规划 Power Path 充电、升降压、电量计和正常电源键。
- 无蓝牙耳机计划；首版 USB 按设备端设计。
- 首块新 PCB 采用尺寸宽松、接口与测流点充分的开发验证板，验证后再收紧外形。
- 电池选定755570、4000mAh、单节3.7V、带保护和三线10kΩ NTC；r5按假设曲线设计约0.7A充电与硬件温窗，实际电池匹配仍待核，保持初装禁充。扬声器选3525腔体8Ω2W，以提示音/有声书及功耗优先。十一页KiCad原理图为r6 DRAWING（r5电气设计），PCB已完成r10近孔整改、布线和制造文件静态检查；尚未冻结制造BOM或上电验证。
- 器件型号为候选，实际 GPIO、BOM 与电源参数须经过原理图及实板验证。

## 文档与工程入口

| 内容 | 入口 |
| --- | --- |
| 软件总体设计与接口约束 | [architecture.md](architecture.md) |
| 阶段目标与验收 | [roadmap.md](roadmap.md) |
| 硬件方案与开发验证板 | [hardware/README.md](hardware/README.md) |
| 开发板电源规格与关断要求 | [hardware/power-design-spec.md](hardware/power-design-spec.md) |
| KiCad原理图r6、PCB布线r8与检查结果 | [hardware/devboard-r0/README.md](../../hardware/devboard-r0/README.md) |
| BOM、封装与条件闭合 | [hardware/closure-review-r4.md](hardware/closure-review-r4.md) |
| 屏幕、SD与音频电路细节 | [hardware/peripheral-design-r2.md](hardware/peripheral-design-r2.md) |
| 旧板六页静态电路审查 | [hardware/review/README.md](hardware/review/README.md) |
| 独立工程、构建和测试方法 | [v2/README.md](../../v2/README.md) |
| M0 历史本地检查记录（2026-11-01） | [validation.md](validation.md) |

## 仓库组织

本仓库独立管理 V2：`v2/` 是固件工程，`hardware/` 保存 KiCad 工程与审查资料，`docs/v2/` 保存设计文档，`outputs/` 保存已有 BOM 审查工作簿。迁移保留这些相对路径，确保硬件校验与文档引用连续。旧版工程保留在原仓库，参考起点为 [`0f6d7c3`](https://github.com/xiaobaoaaaaaa/ESPaperPlay/tree/0f6d7c349afdbbeb962a736d84036ce7f8487174)。

当前已完成 M0 的首批代码和本地验证。GUI、驱动迁移、后台工作队列、音频、网络、真实休眠和 OTA 下载将按路线逐步接入；没有进行实机烧录或 PCB 制造。

r6绘图沿用r5电气设计，包含一张索引和十张功能页，236个位置、181条网络，全部774个引脚连接和封装编号检查通过，ERC为0违规；234个位置有候选料号，两个USB调谐DNP有意不选料。r7已完成160×110mm四层板的236个电气器件与4个安装孔布局。r8已完成全部连接、双内层铺地、USB/SD长度和电源铜路径检查。r10已整改近焊盘过孔并明确热孔工艺，下一步按最终文件确认工厂生产稿，按样机计划验证温窗、电池匹配和动态性能；[r4报告](hardware/closure-review-r4.md)保留为历史。
