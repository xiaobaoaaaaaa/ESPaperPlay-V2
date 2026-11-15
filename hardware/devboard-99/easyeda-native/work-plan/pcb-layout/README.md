# 布局与封装实施依据

这些文件保留位置计算、原厂图纸引用和实施前调查。最终实现以 source/PCB-layout.epcb、source/footprints/ 和 audit/pcb-layout/ 实际 CAM 报告为准，不可直接重放计划覆盖当前工程。

native-placement-proposal.json 仅由参考焊盘中心匹配原生器件位置与旋转；未导入 KiCad 铜线或封装。随后 J501 按实际 GCT 板边基准内移，SW301–SW305 在网络修正后旋转，最终位置见 audit/pcb-layout/final-layout-state.json。

switch-native-audit.json 是实施前错误调查；五个开关1/2信号、3/4地的修正现已完成，孔径采用1.0mm。j501-npth-manufacturing-review.md 是分析依据，最终J501 CAM以独立报告为准。F501实际型号为Littelfuse1812L200/16DR，保留历史参考元件记录不会将其采购型号改回旧Bourns。
