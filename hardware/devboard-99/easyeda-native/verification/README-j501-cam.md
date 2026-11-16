# J501 与镀通孔实际接触检查

两个入口只读原生工程和 CAM，不调用嘉立创EDA、不改设计，也不依赖 ignored `build/` 中的工具代码。Python 环境须有 Gerbonara 和 Shapely 2.x，安装方式沿用本目录 README；如使用本机既有环境，设置 `PYTHONPATH=build/dfm-r9/python:build/dfm-r9/stencil/python`。

```sh
python3 hardware/devboard-99/easyeda-native/verification/check_native_j501_cam.py \
  --source FINAL.epcb --state FINAL-state.json --archive FINAL.epro2 \
  --zip FINAL-cam.zip --output j501-cam-review.json --negative-tests

python3 hardware/devboard-99/easyeda-native/verification/check_native_cam_connectivity.py --self-test
python3 hardware/devboard-99/easyeda-native/verification/check_native_cam_connectivity.py \
  --source FINAL.epcb --state FINAL-state.json --archive FINAL.epro2 \
  --zip FINAL-cam.zip --output cam-connectivity.json
```

四份输入必须来自同一已保存、重新打开并重建铺铜的检查点。中间布线版本出现未连网络时，连通性检查器正确返回非零；不能把中间结果改成 PASS。J501 专项通过只代表局部检查通过，不代表整个 PCB 可制造。

`j501-cam-target.json` 冻结 GCT USB4105-GF-A 和此前审查的项目避孔修正，记录来源哈希；不会从被测工程重新生成期望值。J501 有 20 个原生 PAD（16 个 SMT + 4 个镀槽），对应 16 个物理连片铜落盘和 12 个锡膏开口。检查逐个铜 primitive，并确认最终极性合成铜没有将它清除；因此合法新增走线不会被误认成焊盘形状变化，反之走线也不能代替缺失的完整焊盘。还检查双面阻焊、零背面/零 shell 锡膏、2 个定位 NPTH、4 个镀槽/环宽、板边、20 个独立预期 pin/net、局部实际铜的错网络短接，以及每个新增孔与同版本原生源的一一对应。

原修正报告把 `default_NPTH_rule_mm=0.30` 与 `J501_relief_design_minimum_mm=0.31` 分开。0.31 mm 是六个逻辑焊盘 heel 的圆弧避让设计值，并同步用于锡膏；它不是 GCT 原图或板厂规定的全层 0.31 mm 规则。因此继续按原精确铜/膏几何和 ≥0.3099 mm CAM 接受值检查这些落盘，其他实际走线/平面严格按全板已有 ≥0.30 mm 规则。历史布局检查把尚未铺铜的内层也套入 ≥0.3099 mm，现明确修正这个检查范围。critical 样本两内层实测约 0.302537 mm，Top 约 0.309996 mm，报告保留这些数值。此澄清不降低制造要求，也不改变任何 CAD 几何。

CAM 连通性检查先减掉实际 Excellon 孔，再将实际铜多边形作为节点。只有源标识和形状/镀铜属性均匹配的实际孔，且每个参与节点确实与该孔壁共享正长度边界，才允许跨层合并。没有膨胀、点吸附或跨缝连接。`--self-test` 保留原面积阈值、切孔和孤岛反例，并新增外侧孤立碎铜不能借名义 via 包络跨层连通、点接触不算孔壁连接、真实镀槽孔壁正例。

`--negative-tests` 在已通过的实际 J501 CAM 观察结果上执行内存变异，覆盖铜 primitive 遗漏/后续擦铜、锡膏窗遗漏/额外 shell 膏、阻焊遗漏、定位孔/镀槽遗漏及错误镀铜属性、错误 pin/net、NC 被接网、错误网络进入铜、真实数据网短桥与内层 NPTH 让空遗漏。原文件和 CAD 不被改动；不删除现有其他检查器的反例。

仍须独立完成整板原生 DRC、SCH/PCB 网表等价、全板 CAM 连通/制造间隙、高速信号参考平面、装配和样机验证。几何检查不证明实物孔镀层、铜厚、阻抗、温升或焊接质量。
