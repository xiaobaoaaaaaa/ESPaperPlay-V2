历史快照：本目录已由 ../r10-checked/ 取代，请打开其中的最终工程备份。
以下内容记录本目录生成时的状态，不能代表当前客户端工程。

ESPaperPlay V2 r10 — 嘉立创EDA迁移待审工程
日期：2026-11-14
状态：MIGRATION_REVIEW_ONLY_NOT_MANUFACTURING_VALIDATED

打开方式
嘉立创EDA个人空间：ESPaperPlay-V2-r10-migrated
工程UUID：5f78098564b143419750286dad7b1c42
本地备份：ESPaperPlay-V2-r10-migrated.epro2，可用“导入嘉立创EDA专业版”打开。
三个不完整中间工程已移入“ESPaperPlay_导入调试_不可用于生产”文件夹。

本次完成
1. 使用官方 easyeda-api + Run API Gateway 导入KiCad r10。
2. PCB网络字符串转旧式数字引用；KiCad pcbnew逐项验证副本语义与原板相同。
3. 修复334个全局标签误转局部端口；去除9个ERC-only PWR_FLAG及错误导线NET属性。
4. 原理图11页、236实际器件、774引脚、181网络连接分区完全匹配（局部网允许重命名）。
5. PCB的240元件、804带网络焊盘、549过孔、181网络、4铜层匹配。
6. 恢复原锁定状态，补回微段并保存；编辑器保存时仍会自动整理极短线段。

尚未闭合，禁止按此工程直接投板
- 2335源走线最终变成2256条；47条源线段存在微小中心线缺口，总长0.0393991mm，最大单处0.0069mm。
- 两个GND内层铺铜的网络/所在层匹配，但填充形状没有证明等价，DRC有大量间距和GND连接问题。
- 规则未完成迁移校准，过孔尺寸规则及网表比较仍有报错；未以放宽规则消除错误。
- 原理图与PCB的局部网络名、Unique ID/ECO映射仍需核对，勿直接执行“更新PCB”并接受所有变更。
- 封装内部全部物理焊盘几何及制造输出尚未复核。
- 原KiCad工程与现有r10制造ZIP没有修改，制造依据仍为其已审查版本。

最终嘉立创DRC分类计数
Clearance Error / Copper Region(Filled) to Prohibited Region: 2
Clearance Error / SMD Pad to Via: 2
Clearance Error / Copper Region(Filled) to Via: 438
Clearance Error / Copper Region(Filled) to TH Pad: 140
Clearance Error / Copper Region(Filled) to Hole: 14
Clearance Error / Hole to Hole: 1
Clearance Error in the same footprint / SMD Pad to TH Pad: 1
Physical Error / Via Diameter: 549
Connection Error / GND: 464
Netlist Error / Netlist Error: 1

复现与证据
review/保留网表比较、PCB几何审查及原始DRC结果。
reproduce/保留原KiCad打包、转换与核对脚本、最终PCB源码。
make-kicad-net-compat.py使用系统/usr/bin/python3及pcbnew，需要先将原KiCad ZIP解压到脚本相邻的source/目录。
fix_imported_schematic.py接收INPUT OUTPUT --source source；输入为兼容KiCad包经嘉立创官方导入后导出的epro2。
审查脚本与本次转换日志原工作目录：/home/xiaobao/Projects/ESPaperPlay-V2/build/easyeda-import-r10

原PCB SHA256：e7be650716b6b75f3b8d33ccc13a1d7717db9a022a3d4e6a25f0df748bae1a24
